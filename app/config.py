"""全局配置与路径。"""
from __future__ import annotations

import sys
from pathlib import Path

# ---- 服务配置
HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"

# ---- 路径
#   开发运行：ROOT = 项目根目录
#   PyInstaller：ROOT = 可执行文件所在目录（数据/模型放在 exe 旁边，可写）
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
HF_CACHE_DIR = MODELS_DIR / "_hf_cache"
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

DATA_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# ---- ONNX Runtime provider 优先级（越靠前越优先）
PROVIDER_PRIORITY = (
    "DmlExecutionProvider",
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "CPUExecutionProvider",
)

PROVIDER_LABEL = {
    "DmlExecutionProvider": "DirectML (GPU)",
    "CUDAExecutionProvider": "CUDA (NVIDIA GPU)",
    "ROCMExecutionProvider": "ROCm (AMD GPU)",
    "CPUExecutionProvider": "CPU",
}
