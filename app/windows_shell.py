"""Explorer-style folder selection through the Windows Common Item Dialog."""
from __future__ import annotations

import ctypes as ct
from pathlib import Path
import uuid


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


def pick_folder(title: str, initial_path: str = "") -> str | None:
    """Own COM initialization on the backend worker thread; Cancel returns None."""
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
    _check(ole.CoInitializeEx(None, 2))
    dialog = ct.c_void_p()
    try:
        clsid = _GUID.parse("dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7")
        iid = _GUID.parse("d57c7288-d4ad-4768-be02-9d969532d960")
        _check(ole.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(dialog)))
        flags = ct.c_uint32()
        _check(_method(dialog, 10, ct.POINTER(ct.c_uint32))(dialog, ct.byref(flags)))
        # FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR
        _check(_method(dialog, 9, ct.c_uint32)(dialog, flags.value | 0x20 | 0x40 | 0x800 | 0x8))
        _check(_method(dialog, 17, ct.c_wchar_p)(dialog, title))
        if initial_path and Path(initial_path).is_dir():
            folder = ct.c_void_p()
            item_iid = _GUID.parse("43826d1e-e718-42ee-bc55-a1e261c37bfe")
            _check(shell.SHCreateItemFromParsingName(str(Path(initial_path).resolve()), None,
                                                    ct.byref(item_iid), ct.byref(folder)))
            try:
                _check(_method(dialog, 12, ct.c_void_p)(dialog, folder))
            finally:
                _method(folder, 2)(folder)

        # Use the real foreground window as owner, never a transparent hidden Form.
        hr = _method(dialog, 3, ct.c_void_p)(dialog, user.GetForegroundWindow())
        if hr & 0xffffffff == 0x800704c7:  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
            return None
        _check(hr)
        item = ct.c_void_p()
        _check(_method(dialog, 20, ct.POINTER(ct.c_void_p))(dialog, ct.byref(item)))
        try:
            path = ct.c_void_p()
            _check(_method(item, 5, ct.c_uint32, ct.POINTER(ct.c_void_p))(
                item, 0x80058000, ct.byref(path)))  # SIGDN_FILESYSPATH
            try:
                return ct.wstring_at(path)
            finally:
                ole.CoTaskMemFree(path)
        finally:
            _method(item, 2)(item)
    finally:
        if dialog:
            _method(dialog, 2)(dialog)
        ole.CoUninitialize()
