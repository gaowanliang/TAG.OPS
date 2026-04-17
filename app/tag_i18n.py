"""Load tag translations (zh/en) from data/tags_tr.yaml.

YAML schema (grouped by Chinese category):

    评级:
      rating_general: 一般
      rating_sensitive: 敏感
    人物数量:
      1girl: 1个女孩

At runtime we flatten into the legacy shape::

    { normalized_english_name: {"zh": "...", "category_zh": "..."} }

which is what ``/api/tag-i18n`` and the frontend expect.

If the YAML is missing, we fall back to ``data/stg.csv`` so existing
installs keep working during the migration window.
"""
from __future__ import annotations

import csv
from typing import Dict

import yaml

from .config import DATA_DIR

_CACHE: Dict[str, Dict[str, str]] | None = None
_YAML = DATA_DIR / "tags_tr.yaml"
_CSV = DATA_DIR / "stg.csv"


def _normalize(name: str) -> str:
    # 统一下划线/空格，便于匹配回替换过下划线的 tag
    return name.strip().lower().replace(" ", "_")


def _load_yaml() -> Dict[str, Dict[str, str]]:
    table: Dict[str, Dict[str, str]] = {}
    try:
        raw = yaml.safe_load(_YAML.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return table
    except Exception:
        return table
    if not isinstance(raw, dict):
        return table
    for cat_zh, group in raw.items():
        if not isinstance(group, dict):
            continue
        cat_str = str(cat_zh)
        for name, zh in group.items():
            if name is None or zh is None:
                continue
            # PyYAML 可能把 `no` / `yes` 等 key 解析成 bool；强制转回字符串
            nm = str(name)
            zh_str = str(zh)
            table[_normalize(nm)] = {"zh": zh_str, "category_zh": cat_str}
    return table


def _load_csv() -> Dict[str, Dict[str, str]]:
    table: Dict[str, Dict[str, str]] = {}
    if not _CSV.exists():
        return table
    with _CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("name")
            if not name:
                continue
            table[_normalize(name)] = {
                "zh": (row.get("name_zh") or "").strip(),
                "category_zh": (row.get("category_zh") or "").strip(),
            }
    return table


def load() -> Dict[str, Dict[str, str]]:
    """Return the translation table; cache per-process."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    table = _load_yaml() if _YAML.exists() else _load_csv()
    _CACHE = table
    return table


def reload() -> Dict[str, Dict[str, str]]:
    """Force a re-read (useful after editing the YAML in place)."""
    global _CACHE
    _CACHE = None
    return load()
