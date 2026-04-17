"""后台批量识别任务 + 单图同步识别。"""
from __future__ import annotations

import io
import json
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

from . import db
from .hashing import hash_file
from .models import interrogate, load_model, postprocess_tags


# --------------------------------------------------------------- 数据结构
@dataclass
class Job:
    id: str
    total: int
    done: int = 0
    status: str = "pending"  # pending | running | finished | error
    message: str = ""
    results: List[dict] = field(default_factory=list)
    # path / 文件名 → results 列表中的索引，便于详情页懒查
    by_key: Dict[str, int] = field(default_factory=dict)


@dataclass
class BatchOptions:
    """图片参数。model 必填；其余均有默认。"""
    model: str
    threshold: float = 0.35
    replace_underscore: bool = True
    sort_alphabetical: bool = False
    max_tags: Optional[int] = None
    device_id: Optional[int] = None


@dataclass
class FolderBatchOptions(BatchOptions):
    """文件夹批量特有：是否落盘与格式。"""
    save_format: str = "none"       # none | txt | json
    save_dir_name: str = "tagging_results"
    recursive: bool = False
    skip_existing: bool = False     # 跳过 tagging_results 里已有哈希匹配的图片


# --------------------------------------------------------------- 注册表
_jobs: Dict[str, Job] = {}
_jobs_lock = threading.Lock()


def get(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def _register(job: Job) -> None:
    with _jobs_lock:
        _jobs[job.id] = job


# --------------------------------------------------------------- 公共入口
def create_upload_batch_job(
    files: List[Tuple[str, bytes]], options: BatchOptions
) -> Job:
    """上传文件批量（字节流），key = 文件名。"""
    job = Job(id=uuid.uuid4().hex, total=len(files))
    _register(job)
    threading.Thread(
        target=_run_upload, args=(job, files, options), daemon=True
    ).start()
    return job


def create_folder_batch_job(
    paths: List[str], options: FolderBatchOptions
) -> Job:
    """文件夹批量（本地路径），key = 绝对路径。"""
    job = Job(id=uuid.uuid4().hex, total=len(paths))
    _register(job)
    threading.Thread(
        target=_run_folder, args=(job, paths, options), daemon=True
    ).start()
    return job


def interrogate_one(
    path: str, options: BatchOptions
) -> dict:
    """同步识别单张本地图片，返回与 job 结果同构的字典。"""
    model = load_model(options.model, device_id=options.device_id)
    with Image.open(path) as img:
        ratings, raw = interrogate(model, img)
        size = img.size
        mode = img.mode
        fmt = img.format
    processed = postprocess_tags(
        raw,
        threshold=options.threshold,
        replace_underscore=options.replace_underscore,
        sort_alphabetical=options.sort_alphabetical,
        max_tags=options.max_tags,
    )
    try:
        file_size = Path(path).stat().st_size
    except OSError:
        file_size = 0
    return {
        "path": path,
        "file": Path(path).name,
        "tags": processed,
        "tags_string": ", ".join(processed.keys()),
        "ratings": {k: float(v) for k, v in ratings.items()},
        "image_info": {
            "width": size[0], "height": size[1], "mode": mode,
            "format": fmt, "file_size": file_size,
        },
        "provider": model.provider,
    }


# --------------------------------------------------------------- 内部 runner
def _run_upload(
    job: Job, files: List[Tuple[str, bytes]], opts: BatchOptions
) -> None:
    try:
        job.status = "running"
        job.message = f"加载模型 {opts.model} ..."
        model = load_model(opts.model, device_id=opts.device_id)
        job.message = f"已加载 [{model.provider}]，开始识别"

        for i, (fname, data) in enumerate(files):
            try:
                with Image.open(io.BytesIO(data)) as img:
                    ratings, raw = interrogate(model, img)
                    size = img.size
                processed = postprocess_tags(
                    raw,
                    threshold=opts.threshold,
                    replace_underscore=opts.replace_underscore,
                    sort_alphabetical=opts.sort_alphabetical,
                    max_tags=opts.max_tags,
                )
                item = {
                    "file": fname,
                    "tags": processed,
                    "tags_string": ", ".join(processed.keys()),
                    "ratings": {k: float(v) for k, v in ratings.items()},
                    "image_info": {"width": size[0], "height": size[1]},
                }
                job.by_key[fname] = len(job.results)
                job.results.append(item)
            except Exception as e:
                job.results.append({"file": fname, "error": str(e)})
            job.done = i + 1

        job.status = "finished"
        job.message = f"完成 {job.total} 张 · provider={model.provider}"
    except Exception as e:
        job.status = "error"
        job.message = f"{e}\n{traceback.format_exc()}"


def _load_cache_by_hash(save_dir: Path) -> Dict[str, dict]:
    """读取 tagging_results/*.json，按 xxhash 建索引。

    新格式：{"xxhash": "...", "file": ..., "tags": {...}, "ratings": {...}}
    旧格式（裸 tag dict 或 rapidhash 字段）没有 xxhash，跳过。
    """
    cache: Dict[str, dict] = {}
    if not save_dir.is_dir():
        return cache
    for jf in save_dir.glob("*.json"):
        try:
            raw = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        h = raw.get("xxhash")
        if not h or not isinstance(raw.get("tags"), dict):
            continue
        cache[h] = raw
    return cache


def _run_folder(
    job: Job, paths: List[str], opts: FolderBatchOptions
) -> None:
    try:
        job.status = "running"
        job.message = f"加载模型 {opts.model} ..."
        model = load_model(opts.model, device_id=opts.device_id)
        job.message = f"已加载 [{model.provider}]，开始识别"

        # 预扫 tagging_results/，准备哈希缓存（skip_existing 才用到）
        parent = Path(paths[0]).parent if paths else None
        cache_dir = (parent / opts.save_dir_name) if parent else None
        hash_cache: Dict[str, dict] = {}
        if opts.skip_existing and cache_dir:
            hash_cache = _load_cache_by_hash(cache_dir)

        # 确定保存目录（仅当用户显式要求落盘时；默认 none，保存改由 /api/save 触发）
        save_dir: Optional[Path] = None
        if opts.save_format in ("txt", "json") and paths:
            save_dir = Path(paths[0]).parent / opts.save_dir_name
            save_dir.mkdir(exist_ok=True)

        skipped = 0
        for i, p in enumerate(paths):
            try:
                # 先算哈希（即便不跳过，也把 hash 存进结果里，便于后续保存）
                h = hash_file(p) or ""
                cached = hash_cache.get(h) if opts.skip_existing else None

                if cached is not None:
                    # 命中缓存：不跑模型，直接复用历史结果
                    processed = dict(cached.get("tags") or {})
                    ratings = dict(cached.get("ratings") or {})
                    # 补齐 image_info
                    try:
                        with Image.open(p) as img:
                            size = img.size
                            mode = img.mode
                            fmt = img.format
                    except Exception:
                        size = (0, 0)
                        mode = ""
                        fmt = ""
                    item = {
                        "path": p,
                        "file": Path(p).name,
                        "xxhash": h,
                        "cached": True,
                        "tags": processed,
                        "tags_string": ", ".join(processed.keys()),
                        "ratings": {k: float(v) for k, v in ratings.items()},
                        "image_info": {
                            "width": size[0], "height": size[1],
                            "mode": mode, "format": fmt,
                            "file_size": _safe_size(p),
                        },
                    }
                    skipped += 1
                else:
                    with Image.open(p) as img:
                        ratings, raw = interrogate(model, img)
                        size = img.size
                        mode = img.mode
                        fmt = img.format
                    processed = postprocess_tags(
                        raw,
                        threshold=opts.threshold,
                        replace_underscore=opts.replace_underscore,
                        sort_alphabetical=opts.sort_alphabetical,
                        max_tags=opts.max_tags,
                    )
                    item = {
                        "path": p,
                        "file": Path(p).name,
                        "xxhash": h,
                        "cached": False,
                        "tags": processed,
                        "tags_string": ", ".join(processed.keys()),
                        "ratings": {k: float(v) for k, v in ratings.items()},
                        "image_info": {
                            "width": size[0], "height": size[1],
                            "mode": mode, "format": fmt,
                            "file_size": _safe_size(p),
                        },
                    }

                job.by_key[p] = len(job.results)
                job.results.append(item)

                if save_dir is not None:
                    _save_result_json(save_dir, Path(p), item, opts.save_format)
            except Exception as e:
                job.by_key[p] = len(job.results)
                job.results.append({"path": p, "file": Path(p).name, "error": str(e)})
            job.done = i + 1

        job.status = "finished"
        parts = [f"完成 {job.total} 张", f"provider={model.provider}"]
        if skipped:
            parts.append(f"缓存命中 {skipped}")
        if save_dir:
            parts.append(f"已保存到 {save_dir}")
        job.message = " · ".join(parts)

        # 记录到历史 DB（只记文件夹 run）
        try:
            db.record_run(
                path=str(Path(paths[0]).parent) if paths else "",
                model=opts.model,
                total=job.total,
                done=job.done,
                status=job.status,
                settings={
                    "threshold": opts.threshold,
                    "max_tags": opts.max_tags,
                    "replace_underscore": opts.replace_underscore,
                    "sort_alphabetical": opts.sort_alphabetical,
                    "recursive": opts.recursive,
                    "skip_existing": opts.skip_existing,
                    "device_id": opts.device_id,
                },
                results=job.results,
            )
        except Exception:
            pass
    except Exception as e:
        job.status = "error"
        job.message = f"{e}\n{traceback.format_exc()}"


# --------------------------------------------------------------- 工具
def _safe_size(p: str) -> int:
    try:
        return Path(p).stat().st_size
    except OSError:
        return 0


def _save_result(
    save_dir: Path, image_path: Path, tags: Dict[str, float], fmt: str
) -> None:
    # 历史兼容：仅写 tag dict。推荐用 _save_result_json。
    if fmt == "txt":
        (save_dir / f"{image_path.stem}.txt").write_text(
            ", ".join(tags.keys()), encoding="utf-8"
        )
    elif fmt == "json":
        (save_dir / f"{image_path.stem}.json").write_text(
            json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _save_result_json(
    save_dir: Path, image_path: Path, item: dict, fmt: str
) -> None:
    """落盘一条识别结果。JSON 格式带 xxhash；TXT 仅写 tag 列表。"""
    tags = item.get("tags") or {}
    if fmt == "txt":
        (save_dir / f"{image_path.stem}.txt").write_text(
            ", ".join(tags.keys()), encoding="utf-8"
        )
    elif fmt == "json":
        payload = {
            "xxhash": item.get("xxhash") or "",
            "file": item.get("file") or image_path.name,
            "tags": tags,
            "ratings": item.get("ratings") or {},
        }
        (save_dir / f"{image_path.stem}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _clean_save_dir(save_dir: Path) -> int:
    """清空 tagging_results 中的 .txt/.json 文件，返回删除数。目录本身保留。"""
    n = 0
    if not save_dir.is_dir():
        return 0
    for p in list(save_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in (".txt", ".json"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n


def save_job_results(
    job: Job, fmt: str, save_dir_name: str = "tagging_results"
) -> dict:
    """把已完成 job 的结果写到磁盘。仅文件夹 run（结果需含 path）。
    如果目录已存在，先清理旧的 .txt/.json 再重新写入。
    返回 {saved, skipped, removed, save_dir}。"""
    if fmt not in ("txt", "json"):
        raise ValueError(f"不支持的格式: {fmt}")
    if not job.results:
        return {"saved": 0, "skipped": 0, "removed": 0, "save_dir": ""}

    first = next((r for r in job.results if r.get("path")), None)
    if not first:
        raise ValueError("当前任务不是文件夹识别，无法保存到磁盘")

    save_dir = Path(first["path"]).parent / save_dir_name
    save_dir.mkdir(exist_ok=True)
    removed = _clean_save_dir(save_dir)
    saved = skipped = 0
    for item in job.results:
        p = item.get("path")
        tags = item.get("tags")
        if not p or not tags:
            skipped += 1
            continue
        _save_result_json(save_dir, Path(p), item, fmt)
        saved += 1
    return {
        "saved": saved, "skipped": skipped,
        "removed": removed, "save_dir": str(save_dir),
    }


def save_results_payload(
    results: list, fmt: str, save_dir_name: str = "tagging_results"
) -> dict:
    """与 save_job_results 等价，但直接接受 results 数组（用于从历史记录保存）。
    如果目录已存在，先清理旧的 .txt/.json 再重新写入。"""
    if fmt not in ("txt", "json"):
        raise ValueError(f"不支持的格式: {fmt}")
    first = next((r for r in results if r.get("path")), None)
    if not first:
        raise ValueError("记录中不含磁盘路径，无法保存")
    save_dir = Path(first["path"]).parent / save_dir_name
    save_dir.mkdir(exist_ok=True)
    removed = _clean_save_dir(save_dir)
    saved = skipped = 0
    for item in results:
        p = item.get("path")
        tags = item.get("tags")
        if not p or not tags:
            skipped += 1
            continue
        _save_result_json(save_dir, Path(p), item, fmt)
        saved += 1
    return {
        "saved": saved, "skipped": skipped,
        "removed": removed, "save_dir": str(save_dir),
    }
