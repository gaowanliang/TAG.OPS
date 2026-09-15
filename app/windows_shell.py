"""Explorer-style folder selection through the Windows Common Item Dialog."""
from __future__ import annotations

import ctypes as ct
import logging
import os
from pathlib import Path
import threading
import uuid


log = logging.getLogger(__name__)


class _GUID(ct.Structure):
    _fields_ = [("data", ct.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _method(obj, slot, *args):
    vtable = ct.cast(obj, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    return ct.WINFUNCTYPE(ct.c_int32, ct.c_void_p, *args)(vtable[slot])


def _check(hr):
    if hr < 0:
        raise OSError(f"Windows folder dialog failed: HRESULT 0x{hr & 0xffffffff:08x}")


def _check_stage(hr, stage: str):
    if hr < 0:
        log.error("Folder picker stage=%s failed hr=0x%08x", stage, hr & 0xffffffff)
        raise OSError(f"Windows folder dialog failed at {stage}: HRESULT 0x{hr & 0xffffffff:08x}")
    log.debug("Folder picker stage=%s succeeded hr=0x%08x", stage, hr & 0xffffffff)
    return hr


def pick_folder(title: str, initial_path: str = "") -> str | None:
    """Own COM initialization on the backend worker thread; Cancel returns None."""
    log.info(
        "Folder picker start pid=%s tid=%s title=%r initial_path=%r",
        os.getpid(), threading.get_ident(), title, initial_path,
    )
    ole = ct.WinDLL("ole32")
    shell = ct.WinDLL("shell32")
    user = ct.WinDLL("user32")
    ole.CoInitializeEx.argtypes = [ct.c_void_p, ct.c_uint32]
    ole.CoInitializeEx.restype = ct.c_int32
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    ole.CoCreateInstance.argtypes = [ct.POINTER(_GUID), ct.c_void_p, ct.c_uint32,
                                   ct.POINTER(_GUID), ct.POINTER(ct.c_void_p)]
    ole.CoCreateInstance.restype = ct.c_int32
    ole.CoTaskMemFree.argtypes = [ct.c_void_p]
    ole.CoTaskMemFree.restype = None
    shell.SHCreateItemFromParsingName.argtypes = [ct.c_wchar_p, ct.c_void_p,
                                                ct.POINTER(_GUID), ct.POINTER(ct.c_void_p)]
    shell.SHCreateItemFromParsingName.restype = ct.c_int32
    user.GetForegroundWindow.argtypes = []
    user.GetForegroundWindow.restype = ct.c_void_p

    # The request runs in a worker thread. Shell dialogs require an STA apartment.
    _check_stage(ole.CoInitializeEx(None, 2), "CoInitializeEx(STA)")
    log.debug("Folder picker COM apartment initialized")
    dialog = ct.c_void_p()
    try:
        clsid = _GUID.parse("dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7")
        iid = _GUID.parse("d57c7288-d4ad-4768-be02-9d969532d960")
        _check_stage(ole.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(dialog)),
                     "CoCreateInstance(CLSID_FileOpenDialog)")
        log.debug("Folder picker IFileOpenDialog created ptr=%s", dialog.value)
        flags = ct.c_uint32()
        _check_stage(_method(dialog, 10, ct.POINTER(ct.c_uint32))(dialog, ct.byref(flags)),
                     "GetOptions")
        # FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR
        new_flags = flags.value | 0x20 | 0x40 | 0x800 | 0x8
        log.debug("Folder picker options old=0x%08x new=0x%08x", flags.value, new_flags)
        _check_stage(_method(dialog, 9, ct.c_uint32)(dialog, new_flags), "SetOptions")
        _check_stage(_method(dialog, 17, ct.c_wchar_p)(dialog, title), "SetTitle")
        if initial_path:
            if not Path(initial_path).is_dir():
                log.warning("Folder picker initial_path is not an existing directory: %r", initial_path)
        if initial_path and Path(initial_path).is_dir():
            folder = ct.c_void_p()
            item_iid = _GUID.parse("43826d1e-e718-42ee-bc55-a1e261c37bfe")
            resolved_initial = str(Path(initial_path).resolve())
            _check_stage(shell.SHCreateItemFromParsingName(resolved_initial, None,
                                                          ct.byref(item_iid), ct.byref(folder)),
                         "SHCreateItemFromParsingName(initial_path)")
            log.debug("Folder picker initial folder item created ptr=%s path=%r", folder.value,
                      resolved_initial)
            try:
                _check_stage(_method(dialog, 12, ct.c_void_p)(dialog, folder), "SetFolder")
            finally:
                _method(folder, 2)(folder)
                log.debug("Folder picker initial folder item released")

        # Use the real foreground window as owner, never a transparent hidden Form.
        owner = user.GetForegroundWindow()
        log.debug("Folder picker owner foreground_hwnd=%s", owner)
        hr = _method(dialog, 3, ct.c_void_p)(dialog, owner)
        if hr & 0xffffffff == 0x800704c7:  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
            log.info("Folder picker cancelled by user hr=0x%08x", hr & 0xffffffff)
            return None
        _check_stage(hr, "Show")
        item = ct.c_void_p()
        _check_stage(_method(dialog, 20, ct.POINTER(ct.c_void_p))(dialog, ct.byref(item)), "GetResult")
        log.debug("Folder picker result item created ptr=%s", item.value)
        try:
            path = ct.c_void_p()
            _check_stage(_method(item, 5, ct.c_uint32, ct.POINTER(ct.c_void_p))(
                item, 0x80058000, ct.byref(path)), "GetDisplayName(SIGDN_FILESYSPATH)")
            try:
                selected = ct.wstring_at(path)
                log.info("Folder picker selected path=%r", selected)
                return selected
            finally:
                ole.CoTaskMemFree(path)
                log.debug("Folder picker result path memory released")
        finally:
            _method(item, 2)(item)
            log.debug("Folder picker result item released")
    except Exception:
        log.exception("Folder picker failed")
        raise
    finally:
        if dialog:
            _method(dialog, 2)(dialog)
            log.debug("Folder picker dialog released")
        ole.CoUninitialize()
        log.debug("Folder picker COM apartment uninitialized")
