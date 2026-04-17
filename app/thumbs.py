"""图片缩略图生成与缓存。"""
from __future__ import annotations

import io
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Tuple

from PIL import Image

_CACHE_MAX = 512
_cache: "OrderedDict[Tuple[str, int, float], bytes]" = OrderedDict()
_lock = Lock()


def _get_cached(key: Tuple[str, int, float]) -> bytes | None:
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _put_cached(key: Tuple[str, int, float], data: bytes) -> None:
    with _lock:
        _cache[key] = data
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def get_thumbnail(path: str | Path, size: int = 200) -> bytes:
    """返回 JPEG 编码的缩略图字节；内部按 (路径, 大小, mtime) 做 LRU 缓存。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")

    try:
        mtime = p.stat().st_mtime
    except OSError:
        mtime = 0.0
    key = (str(p.resolve()), size, mtime)

    cached = _get_cached(key)
    if cached is not None:
        return cached

    with Image.open(p) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=82, optimize=True)
        data = buf.getvalue()

    _put_cached(key, data)
    return data


def clear_cache() -> None:
    with _lock:
        _cache.clear()
