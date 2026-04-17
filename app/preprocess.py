"""图像预处理：WD14 与 Camie-Tagger-v2。"""
from __future__ import annotations

import numpy as np
from PIL import Image


# ------------------------------------------------------------- WD14
def _make_square(img: np.ndarray, target: int) -> np.ndarray:
    h, w = img.shape[:2]
    desired = max(h, w)
    dh = (desired - h) // 2
    dw = (desired - w) // 2
    padded = np.full((desired, desired, 3), 255, dtype=np.uint8)
    padded[dh : dh + h, dw : dw + w] = img
    return padded


def _smart_resize(img: np.ndarray, size: int) -> np.ndarray:
    pil = Image.fromarray(img)
    pil = pil.resize((size, size), Image.BICUBIC)
    return np.asarray(pil)


def preprocess(image: Image.Image, target: int) -> np.ndarray:
    """WD14：转成 (1, H, W, 3) uint8→float32（BGR，白色 padding）。"""
    image = image.convert("RGBA")
    bg = Image.new("RGBA", image.size, "WHITE")
    bg.paste(image, mask=image)
    arr = np.asarray(bg.convert("RGB"))
    arr = arr[:, :, ::-1]  # RGB -> BGR
    arr = _make_square(arr, target)
    arr = _smart_resize(arr, target)
    return np.expand_dims(arr.astype(np.float32), 0)


# ------------------------------------------------------------- Camie v2
# ImageNet 均值/方差（RGB）
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
# 使用 ImageNet 均值作为 padding 颜色 (round(mean*255))
_IMAGENET_PAD = (124, 116, 104)


def preprocess_camie(image: Image.Image, target: int = 512) -> np.ndarray:
    """Camie-Tagger-v2：保持宽高比缩放、ImageNet 均值 padding、ImageNet 归一化。

    返回 (1, 3, target, target) float32。
    """
    if image.mode in ("RGBA", "P", "LA"):
        image = image.convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    w, h = image.size
    if w <= 0 or h <= 0:
        raise ValueError("invalid image size")
    ratio = w / h
    if ratio > 1:
        new_w = target
        new_h = max(1, int(round(target / ratio)))
    else:
        new_h = target
        new_w = max(1, int(round(target * ratio)))

    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target, target), _IMAGENET_PAD)
    canvas.paste(resized, ((target - new_w) // 2, (target - new_h) // 2))

    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD  # HWC
    arr = np.transpose(arr, (2, 0, 1))            # CHW
    return np.expand_dims(arr, 0).astype(np.float32)
