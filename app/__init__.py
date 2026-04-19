"""Anime Image Classification Evaluation Tool 的核心包。"""
from PIL import Image

from .config import HOST, PORT, URL

# PIL 的 DecompressionBomb 保护是为服务器场景准备的（防用户上传炸弹 PNG）。
# 本工具是本地桌面应用，用户自己在识别自己的高分辨率动漫插图，1 亿像素
# 很正常，默认 89M 的阈值只会在 stderr 刷警告，超过 178M (2x) 还会直接
# 抛 DecompressionBombError 中断批处理。设为 None 关掉两道检查。
Image.MAX_IMAGE_PIXELS = None

__all__ = ["HOST", "PORT", "URL"]
