"""硬件与 ONNX Runtime 执行提供器检测。"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, List

from .config import PROVIDER_LABEL, PROVIDER_PRIORITY


def list_windows_gpus() -> List[str]:
    """用 wmic / PowerShell 列出 Windows 上的显卡名称。非 Windows 返回空列表。"""
    if os.name != "nt":
        return []
    try:
        out = subprocess.check_output(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode(errors="ignore")
        names = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
        if names:
            return names
    except Exception:
        pass
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
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []


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
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        info["providers"] = providers
        info["selected"] = select_provider(providers)
        info["accelerator"] = PROVIDER_LABEL.get(info["selected"], info["selected"])
        info["ok"] = True
    except Exception as e:
        info["error"] = f"onnxruntime 未安装: {e}"

    # 下载通道探测（首次会发一个 2s HEAD 请求，之后走缓存）
    try:
        from .network import detect_region
        net = detect_region()
        info["network"] = net
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

    return info
