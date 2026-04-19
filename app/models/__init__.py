"""模型相关：注册表、下载、加载、推理。"""
from .interrogator import interrogate, postprocess_tags
from .loader import LoadedModel, current_model, load_model, unload_all
from .registry import MODEL_REGISTRY, is_downloaded, list_models, models_info

__all__ = [
    "MODEL_REGISTRY",
    "LoadedModel",
    "current_model",
    "interrogate",
    "is_downloaded",
    "list_models",
    "load_model",
    "models_info",
    "postprocess_tags",
    "unload_all",
]
