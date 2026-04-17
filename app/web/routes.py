"""HTTP 路由。"""
from __future__ import annotations

import traceback
from dataclasses import asdict
from pathlib import Path
from typing import List, Tuple

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from .. import fs, jobs, thumbs
from ..clustering import categorize_by_top_n
from ..fs import is_image
from ..hardware import detect_hardware
from ..jobs import BatchOptions, FolderBatchOptions
from ..models import MODEL_REGISTRY, list_models, models_info
from .. import tag_i18n
from .views import home_page


# ------------------------------------------------------------------ helpers
def _parse_int(val, default=None):
    try:
        return int(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _parse_float(val, default):
    try:
        return float(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _parse_bool(val, default=False):
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


def _job_snapshot(job: jobs.Job, include_results: bool = True) -> dict:
    data = {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "done": job.done,
        "total": job.total,
    }
    if include_results:
        data["results"] = job.results
    return data


# ------------------------------------------------------------------ register
def register(app, rt):
    """把所有路由挂到 FastHTML app 上。"""

    # ---- page ----
    @rt("/")
    def _home():
        return home_page()

    # ---- basic info ----
    @rt("/api/hardware")
    def _hardware():
        return JSONResponse(detect_hardware())

    @rt("/api/models")
    def _models():
        return JSONResponse({"models": list_models(), "info": models_info()})

    @rt("/api/tag-i18n")
    def _tag_i18n():
        return JSONResponse(tag_i18n.load())

    # ---- filesystem ----
    @rt("/api/browse")
    def _browse(path: str = ""):
        """列出目录下的子目录。Windows 下 path 为空时返回盘符列表。"""
        import os
        import string

        try:
            # 空路径：Windows 列盘符；其它平台从根目录开始
            if not path:
                if os.name == "nt":
                    drives = []
                    for letter in string.ascii_uppercase:
                        d = f"{letter}:\\"
                        if Path(d).exists():
                            drives.append({"name": f"{letter}:", "path": d})
                    return JSONResponse({
                        "path": "", "parent": None, "entries": drives,
                    })
                path = "/"

            base = Path(path).resolve()
            if not base.is_dir():
                return JSONResponse({"error": "不是有效目录"}, status_code=400)

            entries = []
            try:
                for p in base.iterdir():
                    try:
                        if p.is_dir():
                            entries.append({"name": p.name, "path": str(p)})
                    except OSError:
                        continue
            except PermissionError:
                return JSONResponse({"error": "无权访问该目录"}, status_code=403)

            entries.sort(key=lambda e: e["name"].lower())

            # 计算父目录；Windows 下盘符根（C:\）的父设为空串以便回到盘符列表
            parent = None
            if os.name == "nt" and len(str(base)) <= 3 and str(base).endswith(":\\"):
                parent = ""
            else:
                pp = base.parent
                if pp != base:
                    parent = str(pp)
            return JSONResponse({
                "path": str(base), "parent": parent, "entries": entries,
            })
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    @app.post("/api/scan")
    async def _scan(request: Request):
        try:
            body = await request.json()
            path = body.get("path", "").strip()
            recursive = bool(body.get("recursive", False))
            if not path:
                return JSONResponse({"error": "未提供路径"}, status_code=400)
            entries = fs.scan_folder(path, recursive=recursive)

            # 检测 tagging_results 目录（仅看顶层父目录），统计可用哈希缓存
            import json as _json
            save_dir = Path(path) / "tagging_results"
            cache_hashes = 0
            if save_dir.is_dir():
                for jf in save_dir.glob("*.json"):
                    try:
                        raw = _json.loads(jf.read_text(encoding="utf-8"))
                        if isinstance(raw, dict) and raw.get("xxhash") \
                                and isinstance(raw.get("tags"), dict):
                            cache_hashes += 1
                    except Exception:
                        continue

            return JSONResponse({
                "path": path,
                "count": len(entries),
                "files": [asdict(e) for e in entries],
                "has_tagging_results": save_dir.is_dir(),
                "cached_hashes": cache_hashes,
            })
        except FileNotFoundError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    @rt("/api/thumb")
    def _thumb(path: str, size: int = 200):
        p = Path(path)
        if not is_image(p):
            return Response(status_code=404)
        try:
            data = thumbs.get_thumbnail(p, size=size)
        except Exception:
            return Response(status_code=500)
        return Response(data, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})

    @rt("/api/image")
    def _image(path: str):
        p = Path(path)
        if not is_image(p):
            return Response(status_code=404)
        return FileResponse(str(p))

    # ---- batch (upload) ----
    @app.post("/api/batch")
    async def _batch(request: Request):
        try:
            form = await request.form()
            model_name = form.get("model")
            if model_name not in MODEL_REGISTRY:
                return JSONResponse(
                    {"error": f"未知模型: {model_name}"}, status_code=400
                )
            uploads = form.getlist("files")
            if not uploads:
                return JSONResponse({"error": "未收到文件"}, status_code=400)
            files: List[Tuple[str, bytes]] = [
                (up.filename, await up.read()) for up in uploads
            ]
            opts = BatchOptions(
                model=model_name,
                threshold=_parse_float(form.get("threshold"), 0.35),
                replace_underscore=_parse_bool(form.get("replace_underscore"), True),
                sort_alphabetical=_parse_bool(form.get("sort_alphabetical"), False),
                max_tags=_parse_int(form.get("max_tags"), None),
                device_id=_parse_int(form.get("device_id"), None),
            )
            job = jobs.create_upload_batch_job(files, opts)
            return JSONResponse({"job_id": job.id, "total": job.total})
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    # ---- batch (folder) ----
    @app.post("/api/batch/folder")
    async def _batch_folder(request: Request):
        try:
            body = await request.json()
            model_name = body.get("model")
            if model_name not in MODEL_REGISTRY:
                return JSONResponse(
                    {"error": f"未知模型: {model_name}"}, status_code=400
                )
            folder = body.get("path", "").strip()
            if not folder:
                return JSONResponse({"error": "未提供路径"}, status_code=400)
            recursive = bool(body.get("recursive", False))
            entries = fs.scan_folder(folder, recursive=recursive)
            if not entries:
                return JSONResponse({"error": "目录下无图片"}, status_code=400)

            opts = FolderBatchOptions(
                model=model_name,
                threshold=_parse_float(body.get("threshold"), 0.35),
                replace_underscore=_parse_bool(body.get("replace_underscore"), True),
                sort_alphabetical=_parse_bool(body.get("sort_alphabetical"), False),
                max_tags=_parse_int(body.get("max_tags"), None),
                device_id=_parse_int(body.get("device_id"), None),
                save_format=(body.get("save_format") or "none").lower(),
                save_dir_name=body.get("save_dir_name") or "tagging_results",
                recursive=recursive,
                skip_existing=_parse_bool(body.get("skip_existing"), False),
            )
            paths = [e.path for e in entries]
            job = jobs.create_folder_batch_job(paths, opts)
            return JSONResponse({"job_id": job.id, "total": job.total})
        except FileNotFoundError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    # ---- job status ----
    @rt("/api/status")
    def _status(id: str, slim: int = 0):
        job = jobs.get(id)
        if not job:
            return JSONResponse({"error": "job 不存在"}, status_code=404)
        # slim=1 时不回传 results（进度轮询时减负）
        return JSONResponse(_job_snapshot(job, include_results=not slim))

    # ---- single image (lazy detail) ----
    @app.post("/api/interrogate")
    async def _interrogate(request: Request):
        try:
            body = await request.json()
            model_name = body.get("model")
            path = body.get("path", "").strip()
            if model_name not in MODEL_REGISTRY:
                return JSONResponse(
                    {"error": f"未知模型: {model_name}"}, status_code=400
                )
            if not path or not is_image(Path(path)):
                return JSONResponse({"error": "无效路径"}, status_code=400)
            opts = BatchOptions(
                model=model_name,
                threshold=_parse_float(body.get("threshold"), 0.35),
                replace_underscore=_parse_bool(body.get("replace_underscore"), True),
                sort_alphabetical=_parse_bool(body.get("sort_alphabetical"), False),
                max_tags=_parse_int(body.get("max_tags"), None),
                device_id=_parse_int(body.get("device_id"), None),
            )
            return JSONResponse(jobs.interrogate_one(path, opts))
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    # ---- save finished job to disk ----
    @app.post("/api/save")
    async def _save(request: Request):
        try:
            body = await request.json()
            job_id = body.get("job_id")
            fmt = (body.get("format") or "").lower()
            history_id = body.get("history_id")

            if history_id is not None:
                from .. import db as _db
                row = _db.get_run(int(history_id))
                if not row:
                    return JSONResponse(
                        {"error": "历史记录不存在"}, status_code=404
                    )
                info = jobs.save_results_payload(row["results"], fmt)
                return JSONResponse(info)

            job = jobs.get(job_id) if job_id else None
            if not job:
                return JSONResponse({"error": "job 不存在"}, status_code=404)
            if job.status not in ("finished", "error"):
                return JSONResponse(
                    {"error": "任务尚未完成"}, status_code=400
                )
            info = jobs.save_job_results(job, fmt)
            return JSONResponse(info)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    # ---- history (persistent DB of folder runs) ----
    @rt("/api/history/list")
    def _history_list(limit: int = 200):
        from .. import db as _db
        return JSONResponse({"runs": _db.list_runs(int(limit))})

    @rt("/api/history/get")
    def _history_get(id: int, rescan: int = 1):
        from .. import db as _db
        row = _db.get_run(int(id))
        if not row:
            return JSONResponse({"error": "历史记录不存在"}, status_code=404)

        folder = Path(row.get("path") or "")
        folder_exists = folder.is_dir() if str(folder) else False
        row["folder_exists"] = folder_exists

        if not rescan or not folder_exists:
            # 非重扫：只过滤仍然存在的 path
            results = row.get("results") or []
            alive, missing = [], 0
            for r in results:
                p = r.get("path")
                if p and Path(p).is_file():
                    alive.append(r)
                else:
                    missing += 1
            row["results"] = alive
            row["missing"] = missing
            row["rescanned"] = False
            return JSONResponse(row)

        # 重扫：按 xxhash 把结果对齐到当前磁盘上的文件
        from ..hashing import hash_file
        from ..fs import scan_folder as _scan_folder
        settings = row.get("settings") or {}
        recursive = bool(settings.get("recursive"))

        try:
            entries = _scan_folder(str(folder), recursive=recursive)
        except Exception:
            entries = []

        # 当前盘上文件：hash → path
        hash_to_path: dict = {}
        path_set = set()
        for e in entries:
            p = getattr(e, "path", None) or (e.get("path") if isinstance(e, dict) else None)
            if not p:
                continue
            path_set.add(p)
            h = hash_file(p)
            if h:
                hash_to_path.setdefault(h, p)

        results = row.get("results") or []
        alive, missing = [], 0
        for r in results:
            old_h = r.get("xxhash") or ""
            new_path = None
            # 优先：哈希命中
            if old_h and old_h in hash_to_path:
                new_path = hash_to_path[old_h]
            # 其次：原路径仍然存在
            elif r.get("path") and r["path"] in path_set:
                new_path = r["path"]
            elif r.get("path") and Path(r["path"]).is_file():
                new_path = r["path"]

            if new_path:
                r = dict(r)
                r["path"] = new_path
                r["file"] = Path(new_path).name
                alive.append(r)
            else:
                missing += 1

        row["results"] = alive
        row["missing"] = missing
        row["rescanned"] = True
        return JSONResponse(row)

    @app.post("/api/history/delete")
    async def _history_delete(request: Request):
        from .. import db as _db
        body = await request.json()
        ok = _db.delete_run(int(body.get("id")))
        return JSONResponse({"deleted": ok})

    # ---- file transfer (copy/move selected files to a destination) ----
    @app.post("/api/files/transfer")
    async def _files_transfer(request: Request):
        import shutil
        try:
            body = await request.json()
            paths = body.get("paths") or []
            dest_raw = (body.get("dest") or "").strip()
            mode = (body.get("mode") or "copy").lower()
            if mode not in ("copy", "move"):
                return JSONResponse({"error": "mode 必须为 copy 或 move"}, status_code=400)
            if not paths or not isinstance(paths, list):
                return JSONResponse({"error": "未选择任何文件"}, status_code=400)
            if not dest_raw:
                return JSONResponse({"error": "未指定目标目录"}, status_code=400)
            dest = Path(dest_raw).expanduser().resolve()
            if not dest.is_dir():
                return JSONResponse(
                    {"error": f"目标不是有效目录: {dest}"}, status_code=400
                )

            done = 0
            errors: list = []
            for p in paths:
                try:
                    src = Path(p)
                    if not src.is_file():
                        errors.append({"path": p, "error": "源文件不存在"})
                        continue
                    if src.resolve().parent == dest:
                        errors.append({"path": p, "error": "源与目标相同"})
                        continue
                    target = dest / src.name
                    # 冲突时自动加后缀
                    if target.exists():
                        stem, suffix = src.stem, src.suffix
                        i = 1
                        while True:
                            cand = dest / f"{stem} ({i}){suffix}"
                            if not cand.exists():
                                target = cand
                                break
                            i += 1
                    if mode == "copy":
                        shutil.copy2(str(src), str(target))
                    else:
                        shutil.move(str(src), str(target))
                    done += 1
                except Exception as e:
                    errors.append({"path": p, "error": str(e)})
            return JSONResponse({
                "mode": mode,
                "dest": str(dest),
                "done": done,
                "total": len(paths),
                "errors": errors,
            })
        except Exception as e:
            return JSONResponse(
                {"error": f"{e}\n{traceback.format_exc()}"}, status_code=500
            )

    # ---- categorize ----
    @rt("/api/categorize")
    def _categorize(
        job_id: str = "", history_id: int = 0,
        top_n: int = 3, min_images: int = 2,
    ):
        results = None
        if history_id:
            from .. import db as _db
            row = _db.get_run(int(history_id))
            if not row:
                return JSONResponse({"error": "历史记录不存在"}, status_code=404)
            results = row["results"]
        elif job_id:
            job = jobs.get(job_id)
            if not job:
                return JSONResponse({"error": "job 不存在"}, status_code=404)
            results = job.results
        else:
            return JSONResponse(
                {"error": "需要 job_id 或 history_id"}, status_code=400
            )

        results_by_key = {}
        for item in results:
            if "tags" in item and item.get("tags"):
                key = item.get("path") or item.get("file")
                if key:
                    results_by_key[key] = item
        categories = categorize_by_top_n(
            results_by_key, top_n=int(top_n), min_images=int(min_images)
        )
        return JSONResponse({
            "categories": {
                name: [
                    {
                        "path": it.get("path") or it.get("file") or "",
                        "confidence": float(it["confidence"]),
                        "tag_count": len(it["tags"]),
                    }
                    for it in items
                ]
                for name, items in categories.items()
            },
            "total_categories": len(categories),
            "total_images": sum(len(v) for v in categories.values()),
        })