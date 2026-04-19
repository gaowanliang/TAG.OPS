"""WD14 / Camie-Tagger-v2 ONNX 模型下载与加载。"""
from __future__ import annotations

import gc
import json
import logging
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..config import HF_CACHE_DIR, MODELS_DIR, PROVIDER_LABEL
from ..hardware import preferred_providers
from ..network import apply_endpoint_env, detect_region
from .registry import MODEL_REGISTRY, model_files, model_kind, modelscope_id_for

log = logging.getLogger(__name__)

MODELSCOPE_CACHE_DIR = MODELS_DIR / "_ms_cache"


@dataclass
class LoadedModel:
    name: str
    session: object  # onnxruntime.InferenceSession
    input_size: int
    provider: str
    kind: str = "wd14"                 # wd14 | camie_v2
    input_layout: str = "NHWC"         # NHWC (wd14) | NCHW (camie_v2)
    device_id: Optional[int] = None
    # WD14
    tags: Optional[pd.DataFrame] = None
    # Camie v2
    idx_to_tag: Optional[Dict[str, str]] = None
    tag_to_category: Optional[Dict[str, str]] = None
    metadata: Optional[dict] = None


_lock = threading.Lock()
_current: Optional[LoadedModel] = None


# ------------------------------------------------------------- 目标目录
def _local_dir_for(cfg: dict) -> Path:
    """按 HF repo_id 规则在本地落地模型文件，跨 channel 复用同一目录。"""
    repo_id = cfg["repo_id"]
    local_dir = MODELS_DIR.joinpath(*repo_id.split("/"))
    rev = cfg.get("revision")
    if rev:
        local_dir = local_dir / f"revision-{re.sub(r'[^A-Za-z0-9._-]', '_', rev)}"
    local_dir.mkdir(parents=True, exist_ok=True)
    return local_dir


def _copy_files(local_dir: Path, src_files: List[Path]) -> List[Path]:
    out: List[Path] = []
    for src in src_files:
        dst = local_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        out.append(dst)
    return out


# ------------------------------------------------------------- 下载通道
def _download_from_modelscope(name: str, cfg: dict) -> List[Path]:
    """通过魔搭 (ModelScope) 下载模型。需要已安装 modelscope。"""
    try:
        from modelscope import snapshot_download  # type: ignore
    except ImportError:
        raise RuntimeError(
            "未安装 modelscope，请执行: pip install modelscope"
        )

    ms_id = modelscope_id_for(cfg)
    files = model_files(cfg)
    MODELSCOPE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log.info("[ModelScope] downloading %s : %s", ms_id, files)
    local_repo = Path(snapshot_download(
        ms_id,
        cache_dir=str(MODELSCOPE_CACHE_DIR),
        allow_patterns=files,
    ))
    src_files: List[Path] = []
    for fname in files:
        src = local_repo / fname
        if not src.exists():
            raise FileNotFoundError(
                f"ModelScope 仓库缺少 {fname}: {local_repo}"
            )
        src_files.append(src)
    return _copy_files(_local_dir_for(cfg), src_files)


def _download_from_huggingface(name: str, cfg: dict) -> List[Path]:
    """通过 HuggingFace（或 hf-mirror）下载模型。"""
    apply_endpoint_env()  # 国内环境会自动切到 hf-mirror.com
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
    log.info("[HF] endpoint=%s, downloading %s", endpoint, cfg["repo_id"])

    from huggingface_hub import hf_hub_download
    kwargs = {
        k: v for k, v in cfg.items()
        if v is not None and k not in ("modelscope_id", "kind", "files")
    }
    kwargs["cache_dir"] = str(HF_CACHE_DIR)

    src_files = [
        Path(hf_hub_download(**kwargs, filename=fname))
        for fname in model_files(cfg)
    ]
    return _copy_files(_local_dir_for(cfg), src_files)


def _download(name: str) -> List[Path]:
    """下载模型文件；已存在则直接返回。

    通道选择：
      1. 本地已经有 → 直接用
      2. 国内 (region=cn) → 优先魔搭，失败回落到 hf-mirror
      3. 海外 → 直连 HF
    """
    cfg = MODEL_REGISTRY[name]
    local_dir = _local_dir_for(cfg)
    files = model_files(cfg)
    local_files = [local_dir / f for f in files]
    if all(p.exists() for p in local_files):
        return local_files

    region = detect_region().get("region", "global")

    if region == "cn":
        try:
            return _download_from_modelscope(name, cfg)
        except Exception as e:
            log.warning("[ModelScope] failed, falling back to hf-mirror: %s", e)

    return _download_from_huggingface(name, cfg)


# ------------------------------------------------------------- 元数据解析
def _infer_input_size(session, fallback: int = 448) -> Tuple[int, str]:
    """从 ONNX 输入形状推断尺寸与布局。"""
    shape = session.get_inputs()[0].shape  # e.g. [N,H,W,3] or [N,3,H,W]
    # NHWC: 最后一维是 3；NCHW: 第二维是 3
    if len(shape) == 4 and shape[-1] == 3:
        size = shape[1] or fallback
        return int(size), "NHWC"
    if len(shape) == 4 and shape[1] == 3:
        size = shape[2] or fallback
        return int(size), "NCHW"
    # 未知布局，回退
    for dim in shape[1:]:
        if isinstance(dim, int) and dim > 16:
            return int(dim), "NHWC"
    return fallback, "NHWC"


def _build_wd14(name: str, session, local_files: List[Path], provider: str,
                device_id: Optional[int]) -> LoadedModel:
    # WD14：model.onnx + selected_tags.csv
    tags_path = next((p for p in local_files if p.suffix == ".csv"), None)
    if tags_path is None:
        raise FileNotFoundError("WD14 模型缺少 selected_tags.csv")
    size, layout = _infer_input_size(session, fallback=448)
    tags_df = pd.read_csv(tags_path)
    return LoadedModel(
        name=name, session=session, input_size=size, provider=provider,
        kind="wd14", input_layout=layout, device_id=device_id, tags=tags_df,
    )


def _build_camie_v2(name: str, session, local_files: List[Path], provider: str,
                    device_id: Optional[int]) -> LoadedModel:
    meta_path = next((p for p in local_files if p.suffix == ".json"), None)
    if meta_path is None:
        raise FileNotFoundError("camie-tagger-v2 模型缺少 metadata.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 兼容新旧两种 metadata 结构
    if "dataset_info" in metadata:
        ds = metadata["dataset_info"]
        tag_mapping = ds["tag_mapping"]
        idx_to_tag = dict(tag_mapping["idx_to_tag"])
        tag_to_category = dict(tag_mapping["tag_to_category"])
    else:
        idx_to_tag = dict(metadata.get("idx_to_tag", {}))
        tag_to_category = dict(metadata.get("tag_to_category", {}))

    # 优先用 metadata 记录的 img_size；否则从 ONNX shape 推断
    model_info = metadata.get("model_info", {}) if isinstance(metadata, dict) else {}
    meta_size = model_info.get("img_size")
    shape_size, layout = _infer_input_size(session, fallback=512)
    size = int(meta_size) if meta_size else shape_size
    if layout != "NCHW":
        # camie-tagger-v2 使用 NCHW + ImageNet 归一化
        layout = "NCHW"

    return LoadedModel(
        name=name, session=session, input_size=size, provider=provider,
        kind="camie_v2", input_layout=layout, device_id=device_id,
        idx_to_tag=idx_to_tag, tag_to_category=tag_to_category,
        metadata=metadata,
    )


# ------------------------------------------------------------- load / unload
def load_model(name: str, device_id: Optional[int] = None) -> LoadedModel:
    """确保指定模型已加载（线程安全）；切换模型或 device_id 时重新创建 session。"""
    global _current
    if name not in MODEL_REGISTRY:
        raise ValueError(f"未知模型: {name}")
    with _lock:
        if (_current and _current.name == name
                and _current.device_id == device_id):
            return _current
        if _current is not None:
            del _current.session
            _current = None
            gc.collect()

        local_files = _download(name)
        main_onnx = local_files[0]

        import onnxruntime as ort

        available = ort.get_available_providers()
        providers = preferred_providers(available, device_id)
        requested_names = [p[0] if isinstance(p, tuple) else p for p in providers]
        log.info(
            "Loading ONNX: %s | device_id=%s | requested providers=%s | available=%s",
            main_onnx.name, device_id, requested_names, available,
        )

        so = ort.SessionOptions()
        # session 级日志也调到 INFO，方便排查 DML/CUDA 回落 CPU 的原因
        so.log_severity_level = 1
        try:
            session = ort.InferenceSession(str(main_onnx), so, providers=providers)
        except Exception as e:
            log.exception(
                "Failed to create session with providers=%s; retrying with CPU only",
                requested_names,
            )
            so_cpu = ort.SessionOptions()
            so_cpu.log_severity_level = 1
            session = ort.InferenceSession(
                str(main_onnx), so_cpu, providers=["CPUExecutionProvider"]
            )
            _ = e  # 保留异常以便在日志中查阅

        active = session.get_providers()
        used_info = active[0]
        log.info(
            "Session active providers=%s (%s)",
            active, PROVIDER_LABEL.get(used_info, used_info),
        )

        # 请求了 GPU provider，但实际被 ORT 静默回落到 CPU —— 这就是客户看到的现象
        wanted_gpu = any(
            p in ("DmlExecutionProvider", "CUDAExecutionProvider", "ROCMExecutionProvider")
            for p in requested_names
        )
        if wanted_gpu and used_info == "CPUExecutionProvider":
            log.error(
                "GPU provider was silently downgraded to CPU by ONNX Runtime."
                " Common causes: (1) onnxruntime build mismatched with installed"
                " CUDA/DirectML runtime; (2) outdated GPU driver;"
                " (3) requested device_id=%s does not exist;"
                " (4) missing DLLs (DirectML.dll / cudnn / cublas)."
                " Requested providers=%s, available providers=%s",
                device_id, requested_names, available,
            )

        kind = model_kind(MODEL_REGISTRY[name])
        if kind == "camie_v2":
            _current = _build_camie_v2(name, session, local_files, used_info, device_id)
        else:
            _current = _build_wd14(name, session, local_files, used_info, device_id)
        return _current


def current_model() -> Optional[LoadedModel]:
    return _current


def unload_all() -> bool:
    global _current
    with _lock:
        if _current is None:
            return False
        del _current.session
        _current = None
        gc.collect()
        return True
