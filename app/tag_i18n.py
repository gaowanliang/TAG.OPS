"""Load tag translations (zh/en) from stg.csv once per process."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict

from .config import DATA_DIR

_CACHE: Dict[str, Dict[str, str]] | None = None
_CSV = DATA_DIR / "stg.csv"


def _normalize(name: str) -> str:
    # 统一下划线/空格，便于匹配回替换过下划线的 tag
    return name.strip().lower().replace(" ", "_")


def load() -> Dict[str, Dict[str, str]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    table: Dict[str, Dict[str, str]] = {}
    if not _CSV.exists():
        _CACHE = table
        return table
    with _CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("name")
            if not name:
                continue
            entry = {
                "zh": (row.get("name_zh") or "").strip(),
                "category_zh": (row.get("category_zh") or "").strip(),
            }
            table[_normalize(name)] = entry
    _CACHE = table
    return table
