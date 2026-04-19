"""标签推理与后处理（支持 WD14 与 Camie-Tagger-v2）。"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
from PIL import Image

from ..preprocess import preprocess, preprocess_camie
from .loader import LoadedModel


def interrogate(
    model: LoadedModel, image: Image.Image
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """对单张图像推理，返回 (ratings, regular_tags)。"""
    if model.kind == "camie_v2":
        return _interrogate_camie(model, image)
    return _interrogate_wd14(model, image)


# ------------------------------------------------------------- WD14
def _interrogate_wd14(
    model: LoadedModel, image: Image.Image
) -> Tuple[Dict[str, float], Dict[str, float]]:
    arr = preprocess(image, model.input_size)
    input_name = model.session.get_inputs()[0].name
    output_name = model.session.get_outputs()[0].name
    confidents = model.session.run([output_name], {input_name: arr})[0]
    assert model.tags is not None
    tags = model.tags[["name"]].copy()
    tags["c"] = confidents[0]
    ratings = dict(tags[:4].values)
    regular = dict(tags[4:].values)
    return ratings, regular


# ------------------------------------------------------------- Camie v2
def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _interrogate_camie(
    model: LoadedModel, image: Image.Image
) -> Tuple[Dict[str, float], Dict[str, float]]:
    arr = preprocess_camie(image, model.input_size)
    input_name = model.session.get_inputs()[0].name
    outputs = model.session.run(None, {input_name: arr})
    # 多输出时使用 refined logits（第二个）；单输出时直接用
    logits = outputs[1] if len(outputs) >= 2 else outputs[0]
    probs = _sigmoid(logits[0]).astype(np.float32)

    idx_to_tag = model.idx_to_tag or {}
    tag_to_cat = model.tag_to_category or {}

    ratings: Dict[str, float] = {}
    regular: Dict[str, float] = {}
    for idx in range(probs.shape[0]):
        tag_name = idx_to_tag.get(str(idx))
        if tag_name is None:
            continue
        p = float(probs[idx])
        if tag_to_cat.get(tag_name) == "rating":
            ratings[tag_name] = p
        else:
            regular[tag_name] = p
    return ratings, regular


# ------------------------------------------------------------- 后处理
def postprocess_tags(
    tags: Dict[str, float],
    threshold: float = 0.35,
    replace_underscore: bool = True,
    sort_alphabetical: bool = False,
    max_tags: int | None = None,
) -> Dict[str, float]:
    """按阈值过滤并可选地替换下划线 / 重新排序 / 限制数量。"""
    out = {t: float(c) for t, c in tags.items() if c >= threshold}
    if replace_underscore:
        out = {t.replace("_", " "): c for t, c in out.items()}
    if sort_alphabetical:
        out = dict(sorted(out.items(), key=lambda i: i[0]))
    else:
        out = dict(sorted(out.items(), key=lambda i: i[1], reverse=True))
    if max_tags is not None and max_tags > 0 and len(out) > max_tags:
        out = dict(list(out.items())[:max_tags])
    return out
