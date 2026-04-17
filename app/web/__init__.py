"""FastHTML 应用组装。"""
from __future__ import annotations

from fasthtml.common import fast_app

from ..config import STATIC_DIR
from . import routes
from .views import head_links


def create_app():
    """创建并配置 FastHTML app。"""
    app, rt = fast_app(
        pico=False,
        hdrs=head_links(),
        static_path=str(STATIC_DIR),
    )
    routes.register(app, rt)
    return app, rt


__all__ = ["create_app"]
