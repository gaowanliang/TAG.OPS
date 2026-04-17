"""网络环境检测与 HuggingFace 镜像切换。"""
from __future__ import annotations

import os
import threading
import urllib.request
from typing import Dict

HF_HOST = "https://huggingface.co"
HF_MIRROR_CN = "https://hf-mirror.com"

_region_lock = threading.Lock()
_region_cache: Dict[str, object] = {}


def _probe(url: str, timeout: float = 2.0) -> bool:
    """HEAD/GET 探测 URL；成功（<500）视为可达。"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def detect_region(force: bool = False) -> Dict[str, object]:
    """探测是否能直连 HuggingFace，决定是否切到国内镜像。

    返回: {region, endpoint, endpoint_label, hf_reachable, mirror}
    第一次调用后缓存；force=True 重新探测。
    """
    with _region_lock:
        if _region_cache and not force:
            return dict(_region_cache)

    hf_ok = _probe(HF_HOST)
    if hf_ok:
        info = {
            "region": "global",
            "endpoint": HF_HOST,
            "endpoint_label": "HuggingFace 直连",
            "endpoint_label_en": "HuggingFace direct",
            "hf_reachable": True,
            "mirror": False,
        }
    else:
        mirror_ok = _probe(HF_MIRROR_CN)
        info = {
            "region": "cn",
            "endpoint": HF_MIRROR_CN if mirror_ok else HF_HOST,
            "endpoint_label": (
                "国内镜像 hf-mirror.com" if mirror_ok
                else "HuggingFace (不可达)"
            ),
            "endpoint_label_en": (
                "CN mirror hf-mirror.com" if mirror_ok
                else "HuggingFace (unreachable)"
            ),
            "hf_reachable": False,
            "mirror": mirror_ok,
        }

    with _region_lock:
        _region_cache.clear()
        _region_cache.update(info)
    return dict(info)


def apply_endpoint_env() -> str:
    """根据检测结果把 HF_ENDPOINT 注入到环境变量，供 huggingface_hub 使用。
    返回实际使用的 endpoint。"""
    # 尊重用户已手动设置的 HF_ENDPOINT
    existing = os.environ.get("HF_ENDPOINT")
    if existing:
        return existing
    info = detect_region()
    os.environ["HF_ENDPOINT"] = str(info["endpoint"])
    return str(info["endpoint"])
