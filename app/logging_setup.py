"""集中式日志配置：控制台 + logs/YYYYMMDD-HHMMSS.log。

- Python 侧：root logger 同时写到原 stderr 与文件。
- 原生侧（ONNX Runtime 的 C++ 日志、print、traceback）通过 Tee 劫持
  sys.stdout / sys.stderr，一并落盘。
- ONNX Runtime 默认日志等级调到 INFO，便于排查 DML/CUDA 回落 CPU 的原因。
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, Optional

from .config import ROOT

LOG_DIR = ROOT / "logs"

_STATE: dict = {
    "configured": False,
    "log_path": None,
    "file": None,
}


class _Tee:
    """把 write 同时发到原流 (stdout/stderr) 与日志文件。

    用来捕获 ONNX Runtime C++ 端写到 stderr 的日志、第三方库的 print 等
    无法通过 Python logging 截获的输出。
    """

    def __init__(self, original: Optional[IO], file: IO) -> None:
        self._orig = original
        self._file = file

    def write(self, data) -> int:
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8", errors="replace")
            except Exception:
                data = str(data)
        if self._orig is not None:
            try:
                self._orig.write(data)
                self._orig.flush()
            except Exception:
                pass
        try:
            self._file.write(data)
            self._file.flush()
        except Exception:
            pass
        return len(data) if isinstance(data, str) else 0

    def flush(self) -> None:
        for s in (self._orig, self._file):
            if s is None:
                continue
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        try:
            return bool(self._orig) and self._orig.isatty()
        except Exception:
            return False

    def fileno(self) -> int:
        if self._orig is None:
            raise OSError("no original stream")
        return self._orig.fileno()

    def __getattr__(self, name):
        return getattr(self._orig, name)


def setup_logging(level: int = logging.INFO) -> Path:
    """配置根 logger + Tee stdout/stderr + ORT 详细日志。返回日志文件路径。"""
    if _STATE["configured"]:
        return _STATE["log_path"]  # type: ignore[return-value]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pid = os.getpid()
    log_path = LOG_DIR / f"{stamp}-{pid}.log"
    fh = open(log_path, "a", encoding="utf-8", buffering=1)

    # 1) Tee stdout/stderr —— 捕获 ORT / 第三方 print
    if sys.stdout is not None:
        sys.stdout = _Tee(sys.stdout, fh)  # type: ignore[assignment]
    if sys.stderr is not None:
        sys.stderr = _Tee(sys.stderr, fh)  # type: ignore[assignment]

    # 2) Python logging —— 走 Tee 后的 stderr，即控制台 + 文件都能看到
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    for name in (
        "onnxruntime",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "starlette",
    ):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = True

    # 3) ONNX Runtime C++ 日志等级（0=VERBOSE 1=INFO 2=WARNING 3=ERROR 4=FATAL）
    try:
        import onnxruntime as ort
        ort.set_default_logger_severity(1)
    except Exception:
        pass

    _STATE.update(configured=True, log_path=log_path, file=fh)

    logging.getLogger(__name__).info("Log file: %s", log_path)
    return log_path


def get_log_path() -> Optional[Path]:
    return _STATE.get("log_path")
