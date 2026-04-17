"""本地文件系统扫描。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass
class ImageEntry:
    path: str
    name: str
    size: int


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def scan_folder(folder: str | Path, recursive: bool = False) -> List[ImageEntry]:
    """扫描目录下的图片文件。recursive=True 时包括子目录。"""
    base = Path(folder)
    if not base.is_dir():
        raise FileNotFoundError(f"目录不存在: {folder}")

    iterator = base.rglob("*") if recursive else base.iterdir()
    results: List[ImageEntry] = []
    for p in iterator:
        if is_image(p):
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            results.append(ImageEntry(str(p), p.name, size))
    results.sort(key=lambda e: e.path.lower())
    return results
