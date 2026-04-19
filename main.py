"""
Anime Image Classification Evaluation Tool — 启动入口。

    python main.py

浏览器会自动打开 http://127.0.0.1:8765
"""
from __future__ import annotations

import logging
import sys
import threading
import webbrowser

import uvicorn

from app import HOST, PORT, URL
from app.hardware import detect_hardware
from app.logging_setup import get_log_path, setup_logging
from app.web import create_app


# 必须在 import/创建 app 之前配置好日志，才能接到 onnxruntime / uvicorn 的输出
setup_logging()

app, _ = create_app()


def _open_browser_later(delay: float = 1.2) -> None:
    threading.Timer(delay, lambda: webbrowser.open(URL)).start()


def _print_banner() -> None:
    hw = detect_hardware()
    log = logging.getLogger("main")
    bar = "=" * 60
    for line in (
        bar,
        f" Anime Image Classifier  ·  {URL}",
        f" Log file: {get_log_path()}",
        f" ONNX providers: {hw.get('providers')}",
        f" Selected: {hw.get('selected')}  ({hw.get('accelerator')})",
        f" GPUs: {hw.get('gpus')}",
        bar,
    ):
        log.info(line)


def main() -> None:
    _print_banner()
    _open_browser_later()
    # 不要用 fasthtml 的 serve()——它会用字符串 "main:app" 交给 uvicorn 再 import，
    # 在 PyInstaller 冻结后 "main" 不是可 import 的模块。直接传 app 对象即可。
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    # 支持 PyInstaller + 多进程（虽然本项目是单进程，以防万一）
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()
    main()
