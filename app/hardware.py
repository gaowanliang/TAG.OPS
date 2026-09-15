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


def list_provider_gpus(provider: str) -> List[dict]:
    """Enumerate in the selected runtime's ID namespace; never guess from WMI."""
    try:
        if provider == "DmlExecutionProvider":
            from .dxgi import enumerate_adapters
            return [g for g in enumerate_adapters()
                    if not g["software"] and not _is_virtual_gpu(g["name"])]
        if provider in ("CUDAExecutionProvider", "ROCMExecutionProvider"):
            import torch
            # torch.cuda also exposes HIP devices in a ROCm build.
            if bool(torch.version.hip) != (provider == "ROCMExecutionProvider"):
                return []
            return [{"id": i, "name": torch.cuda.get_device_name(i),
                     "memory_bytes": torch.cuda.get_device_properties(i).total_memory}
                    for i in range(torch.cuda.device_count())]
    except Exception:
        log.warning("Cannot enumerate devices for %s; use automatic selection", provider,
                    exc_info=True)
    return []


def largest_gpu(devices: List[dict]) -> dict | None:
    """Prefer dedicated/total device memory, not shared system RAM; ties keep order."""
    return max(devices, key=lambda g: g.get("memory_bytes", 0), default=None)


def preferred_providers(available: List[str], device_id: int | None = None) -> List:
    """返回过滤后按优先级排列的 provider 列表，供 InferenceSession 使用。

    手动 ID 只属于首选后端，不能传给其他后端使用。
    """
    chosen = [p for p in PROVIDER_PRIORITY if p in available]
    if not chosen:
        chosen = ["CPUExecutionProvider"]
    provider = chosen[0]
    devices = list_provider_gpus(provider)
    if device_id is None:
        device = largest_gpu(devices)
        if device is None:
            if provider != "CPUExecutionProvider":
                log.warning("GPU memory enumeration unavailable; retaining runtime default")
            return chosen
        device_id = device["id"]
    if device_id not in [g["id"] for g in devices]:
        raise ValueError("所选 GPU 不可用，请刷新页面后重新选择显卡或使用自动选择。")
    device = next(g for g in devices if g["id"] == device_id)
    log.info("Selected %s device_id=%s: %s", provider, device_id, device["name"])
    return [(provider, {"device_id": int(device_id)}), "CPUExecutionProvider"]


def detect_hardware() -> Dict[str, object]:
    """检测可用的 ONNX Runtime 执行提供器、显卡与下载通道。"""
    gpus = list_windows_gpus()
    info: Dict[str, object] = {
        "providers": [],
        "gpus": gpus,
        "gpus_indexed": [],
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
        info["gpus_indexed"] = list_provider_gpus(info["selected"])
        info["auto_device"] = largest_gpu(info["gpus_indexed"])
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
                " Sync a matching uv runtime extra:"
                " directml (Windows/generic GPU), cuda (NVIDIA CUDA),"
                " or cpu. Current providers=%s",
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
