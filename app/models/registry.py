"""WD14 模型注册表。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

# name -> {repo_id, revision?, modelscope_id?, kind?, files?}
# - kind: "wd14" (默认) | "camie_v2" —— 用于区分输入布局、输出解析、tag/类别映射来源
# - files: 该模型需要下载的文件名列表（默认 ["model.onnx", "selected_tags.csv"]）
# 未显式提供 modelscope_id 时，自动映射为 fireicewolf/<hf 仓库尾段>
MODEL_REGISTRY: Dict[str, Dict[str, Optional[str]]] = {
    "camie-tagger-v2": {
        "repo_id": "Camais03/camie-tagger-v2",
        "modelscope_id": "gaowanliang/camie-tagger-v2",
        "kind": "camie_v2",
        "files": ["camie-tagger-v2.onnx", "camie-tagger-v2-metadata.json"],
    },
    "wd-eva02-large-tagger-v3": {"repo_id": "SmilingWolf/wd-eva02-large-tagger-v3"},
    "wd-vit-large-tagger-v3": {"repo_id": "SmilingWolf/wd-vit-large-tagger-v3"},
    "wd-vit-v3": {"repo_id": "SmilingWolf/wd-vit-tagger-v3"},
    "wd-swinv2-v3": {"repo_id": "SmilingWolf/wd-swinv2-tagger-v3"},
    "wd-convnext-v3": {"repo_id": "SmilingWolf/wd-convnext-tagger-v3"},
    "wd14-convnextv2-v2": {
        "repo_id": "SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
        "revision": "v2.0",
    },
    "wd14-moat-v2": {
        "repo_id": "SmilingWolf/wd-v1-4-moat-tagger-v2",
        "revision": "v2.0",
    },
    "wd14-vit-v2": {
        "repo_id": "SmilingWolf/wd-v1-4-vit-tagger-v2",
        "revision": "v2.0",
    },
    "wd14-convnext-v2": {
        "repo_id": "SmilingWolf/wd-v1-4-convnext-tagger-v2",
        "revision": "v2.0",
    },
    "wd14-swinv2-v2": {
        "repo_id": "SmilingWolf/wd-v1-4-swinv2-tagger-v2",
        "revision": "v2.0",
    },
}


# 选型提示（来源：项目 test.md，2026 年推荐分级）
MODEL_META: Dict[str, Dict[str, str]] = {
    "camie-tagger-v2": {
        "tier": "S",
        "hint": "全新架构 · 多类别精细标签（general/character/copyright/artist/meta/year/rating）。",
        "hint_en": "New architecture · fine-grained multi-category tags "
                   "(general/character/copyright/artist/meta/year/rating).",
    },
    "wd-eva02-large-tagger-v3": {
        "tier": "S",
        "hint": "最高准确率，最吃显存；显存充足时优先。",
        "hint_en": "Highest accuracy; VRAM-hungry — prefer when VRAM is plentiful.",
    },
    "wd-swinv2-v3": {
        "tier": "A+",
        "hint": "官方推荐 · 泛化强；默认主力首选。",
        "hint_en": "Officially recommended · strong generalization; default workhorse.",
    },
    "wd-vit-large-tagger-v3": {
        "tier": "A+",
        "hint": "更高精度但更慢；愿意以速度换精度可选。",
        "hint_en": "Higher precision but slower; choose when accuracy > speed.",
    },
    "wd-vit-v3": {
        "tier": "A",
        "hint": "下载量高、适用面广，通用稳妥选择。",
        "hint_en": "Popular and versatile; a safe general-purpose pick.",
    },
    "wd-convnext-v3": {
        "tier": "B+",
        "hint": "擅长局部特征，适合服饰/细节补充。",
        "hint_en": "Strong on local features; good for clothing/detail enrichment.",
    },
    "wd14-moat-v2": {
        "tier": "B+",
        "hint": "v2 平衡款，适合旧工作流。",
        "hint_en": "Balanced v2 model; fits legacy workflows.",
    },
    "wd14-swinv2-v2": {
        "tier": "B+",
        "hint": "v2 里的速度/精度平衡方案。",
        "hint_en": "Speed/accuracy balance within the v2 family.",
    },
    "wd14-convnextv2-v2": {
        "tier": "B",
        "hint": "旧版 F1 0.6862，兼容老流程。",
        "hint_en": "Legacy F1 0.6862; compatible with older pipelines.",
    },
    "wd14-vit-v2": {
        "tier": "B",
        "hint": "v1.4 细粒度打标，复现旧项目。",
        "hint_en": "v1.4 fine-grained tagging; for reproducing old projects.",
    },
    "wd14-convnext-v2": {
        "tier": "B-",
        "hint": "旧版通用基础款，纯兼容用。",
        "hint_en": "Legacy general-purpose baseline; compatibility only.",
    },
}

# 推荐顺序（越靠前越推荐）
MODEL_ORDER: List[str] = [
    "camie-tagger-v2",
    "wd-swinv2-v3",
    "wd-eva02-large-tagger-v3",
    "wd-vit-large-tagger-v3",
    "wd-vit-v3",
    "wd-convnext-v3",
    "wd14-moat-v2",
    "wd14-swinv2-v2",
    "wd14-convnextv2-v2",
    "wd14-vit-v2",
    "wd14-convnext-v2",
]


def modelscope_id_for(cfg: Dict[str, Optional[str]]) -> str:
    """得到魔搭上的仓库 ID。默认 fireicewolf/<HF 仓库尾段>。"""
    explicit = cfg.get("modelscope_id")
    if explicit:
        return explicit
    tail = cfg["repo_id"].split("/")[-1]
    return f"fireicewolf/{tail}"


def list_models() -> list[str]:
    ordered = [n for n in MODEL_ORDER if n in MODEL_REGISTRY]
    tail = sorted(n for n in MODEL_REGISTRY if n not in MODEL_ORDER)
    return ordered + tail


def model_files(cfg: Dict[str, Optional[str]]) -> List[str]:
    """该模型需要下载的文件列表（主 ONNX 放在第一位）。"""
    files = cfg.get("files")
    if files:
        return list(files)
    return ["model.onnx", "selected_tags.csv"]


def model_kind(cfg: Dict[str, Optional[str]]) -> str:
    """模型架构/加载方式（影响预处理与输出解析）。"""
    return str(cfg.get("kind") or "wd14")


def _local_model_file(name: str) -> Optional[Path]:
    """计算该模型本地缓存主 ONNX 的预期路径（与 loader._local_dir_for 保持一致）。"""
    cfg = MODEL_REGISTRY.get(name)
    if not cfg:
        return None
    from ..config import MODELS_DIR
    local_dir = MODELS_DIR.joinpath(*cfg["repo_id"].split("/"))
    rev = cfg.get("revision")
    if rev:
        local_dir = local_dir / f"revision-{re.sub(r'[^A-Za-z0-9._-]', '_', rev)}"
    return local_dir / model_files(cfg)[0]


def is_downloaded(name: str) -> bool:
    p = _local_model_file(name)
    return bool(p and p.exists())


def models_info() -> list[dict]:
    """返回带元信息的模型列表（保持推荐顺序）。"""
    out = []
    for name in list_models():
        meta = MODEL_META.get(name, {})
        out.append({
            "name": name,
            "tier": meta.get("tier", ""),
            "hint": meta.get("hint", ""),
            "hint_en": meta.get("hint_en", meta.get("hint", "")),
            "downloaded": is_downloaded(name),
        })
    return out
