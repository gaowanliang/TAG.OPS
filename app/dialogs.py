"""Backend-owned native Windows dialogs; no browser modal is required."""
from __future__ import annotations

import ctypes
import logging
import os
import threading

_dialog_lock = threading.Lock()
log = logging.getLogger(__name__)

def show_native_dialog(kind: str, title: str, message: str = "", initial_path: str = "") -> dict:
    if kind not in ("alert", "confirm", "folder"):
        raise ValueError("不支持的对话框类型")
    if os.name != "nt":
        raise OSError("系统对话框当前仅支持 Windows")
    with _dialog_lock:
        if kind == "folder":
            from .windows_shell import pick_folder
            log.info("Opening Windows Explorer folder picker, initial_path=%r", initial_path)
            path = pick_folder(title, initial_path)
            log.info("Windows folder picker %s", "selected a folder" if path else "cancelled")
            return {"path": path}
        show = ctypes.WinDLL("user32", use_last_error=True).MessageBoxW
        show.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        show.restype = ctypes.c_int
        # TOPMOST | SETFOREGROUND; confirm defaults to Cancel, including Escape/close.
        flags = 0x40000 | 0x10000 | 0x40 | (0x1 | 0x100 if kind == "confirm" else 0)
        result = show(None, message, title, flags)
        if result == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return {"accepted": result == 1}
