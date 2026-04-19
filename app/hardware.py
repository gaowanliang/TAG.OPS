"""硬件与 ONNX Runtime 执行提供器检测。"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Dict, List

from .config import PROVIDER_LABEL, PROVIDER_PRIORITY

log = logging.getLogger(__name__)

# 下载通道对应的展示 endpoint（用于 UI 副标题）
_CHANNEL_ENDPOINT = {
    "modelscope": "https://modelscope.cn",
    "hf-mirror": "https://hf-mirror.com",
    "hf": "https://huggingface.co",
}

# 虚拟/远程显示适配器 —— 没有计算能力，不能用于 DML/CUDA 推理。
# 全部小写，用于子串匹配。
_VIRTUAL_GPU_PATTERNS = (
    "virtual display",
    "virtual monitor",
    "virtual adapter",
    "idd driver",            # IddSampleDriver / AskLinkIddDriver / ...
    "asklink",
    "gameviewer",
    "parsec",
    "sunshine",              # Sunshine 流送虚拟显示
    "spacedesk",
    "usb mobile monitor",
    "usb display",
    "remote display",
    "displaylink",           # USB-to-HDMI，渲染仍用主机 GPU，自身无算力
    "splashtop",
    "duet display",
    "idisplay",
    "mirage driver",         # DemoForge Mirage / Miracast 之类
    "miracast",
    "anydesk",
    "todesk",
    "sunlogin",              # 向日葵
    "virtual ",              # "Virtual Audio/Display Device" 之类兜底
    "basic display adapter", # Microsoft Basic Display（驱动没装好时出现）
)


def _is_virtual_gpu(name: str) -> bool:
    n = name.lower()
    return any(p in n for p in _VIRTUAL_GPU_PATTERNS)


def _dedupe_keep_order(names: List[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for n in names:
        key = n.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(n.strip())
    return out


def list_windows_gpus() -> List[str]:
    """用 wmic / PowerShell 列出 Windows 上的物理显卡（过滤虚拟/远程显示适配器）。
    非 Windows 返回空列表。"""
    if os.name != "nt":
        return []
    raw: List[str] = []
    try:
        out = subprocess.check_output(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode(errors="ignore")
        raw = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
    except Exception as e:
        log.debug("wmic query failed: %s", e)
    if not raw:
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
                ],
                stderr=subprocess.DEVNULL,
                timeout=8,
            ).decode(errors="ignore")
            raw = [ln.strip() for ln in out.splitlines() if ln.strip()]
        except Exception as e:
            log.debug("powershell query failed: %s", e)
            return []

    # 先去同名重复，再过滤虚拟显示适配器
    deduped = _dedupe_keep_order(raw)
    real, virtual = [], []
    for n in deduped:
        (virtual if _is_virtual_gpu(n) else real).append(n)
    if virtual:
        log.info("Ignoring virtual/remote display adapters: %s", virtual)
    return real


def select_provider(available: List[str]) -> str:
    """按优先级选择最佳 provider。"""
    for pref in PROVIDER_PRIORITY:
        if pref in available:
            return pref
    return "CPUExecutionProvider"


def preferred_providers(available: List[str], device_id: int | None = None) -> List:
    """返回过滤后按优先级排列的 provider 列表，供 InferenceSession 使用。

    device_id 指定时，DML/CUDA/ROCm provider 会以 (name, options) 形式返回，
    绑定到指定 GPU。
    """
    chosen = [p for p in PROVIDER_PRIORITY if p in available]
    if not chosen:
        return ["CPUExecutionProvider"]
    if device_id is None:
        return chosen
    out: List = []
    for name in chosen:
        if name in ("DmlExecutionProvider", "CUDAExecutionProvider",
                    "ROCMExecutionProvider"):
            out.append((name, {"device_id": int(device_id)}))
        else:
            out.append(name)
    return out


def detect_hardware() -> Dict[str, object]:
    """检测可用的 ONNX Runtime 执行提供器、显卡与下载通道。"""
    gpus = list_windows_gpus()
    info: Dict[str, object] = {
        "providers": [],
        "gpus": gpus,
        # 每张卡带 device_id（DML/CUDA 的索引，顺序参照 wmic）
        "gpus_indexed": [{"id": i, "name": n} for i, n in enumerate(gpus)],
        "selected": "CPUExecutionProvider",
        "accelerator": "CPU",
        "ok": False,
        "error": None,
    }
    log.info("Detected GPUs: %s", gpus or "(none)")

    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        info["providers"] = providers
        info["selected"] = select_provider(providers)
        info["accelerator"] = PROVIDER_LABEL.get(info["selected"], info["selected"])
        info["ok"] = True
        log.info(
            "onnxruntime %s, available providers: %s",
            getattr(ort, "__version__", "?"),
            providers,
        )
        log.info(
            "Preferred provider: %s (%s)", info["selected"], info["accelerator"]
        )
        if gpus and info["selected"] == "CPUExecutionProvider":
            log.warning(
                "GPU detected but no GPU execution provider is available."
                " Install a matching onnxruntime build:"
                " onnxruntime-directml (Windows/generic GPU),"
                " onnxruntime-gpu (NVIDIA CUDA),"
                " onnxruntime-rocm (AMD ROCm). Current providers=%s",
                providers,
            )
    except Exception as e:
        info["error"] = f"onnxruntime 未安装: {e}"
        log.exception("Failed to load onnxruntime")

    # 下载通道探测（首次会发一个 2s HEAD 请求，之后走缓存）
    try:
        from .network import detect_region
        net = detect_region()
        info["network"] = net
        log.info(
            "Network region=%s, hf_reachable=%s, endpoint=%s",
            net.get("region"),
            net.get("hf_reachable"),
            net.get("endpoint"),
        )
        if net["region"] == "cn":
            try:
                import modelscope  # noqa: F401
                info["download_channel"] = "ModelScope (魔搭)"
                info["download_channel_en"] = "ModelScope"
                info["download_channel_tag"] = "modelscope"
            except ImportError:
                info["download_channel"] = net["endpoint_label"]
                info["download_channel_en"] = net.get(
                    "endpoint_label_en", net["endpoint_label"]
                )
                info["download_channel_tag"] = "hf-mirror"
        else:
            info["download_channel"] = "HuggingFace 直连"
            info["download_channel_en"] = "HuggingFace direct"
            info["download_channel_tag"] = "hf"
    except Exception as e:
        info["network"] = {"error": str(e)}
        info["download_channel"] = "未知"
        info["download_channel_en"] = "Unknown"
        info["download_channel_tag"] = "unknown"
        log.exception("Network region detection failed")

    # 用于 UI 的通道 endpoint —— ModelScope 不应显示 hf-mirror
    tag = info.get("download_channel_tag")
    info["channel_endpoint"] = _CHANNEL_ENDPOINT.get(
        tag if isinstance(tag, str) else "",
        (info.get("network") or {}).get("endpoint") or "",  # type: ignore[union-attr]
    )
    log.info(
        "Download channel: %s (%s) -> %s",
        info.get("download_channel"),
        info.get("download_channel_tag"),
        info.get("channel_endpoint"),
    )

    return info
