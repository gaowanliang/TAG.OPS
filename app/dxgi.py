"""DirectML device IDs use DXGI adapter order, never WMI display order."""
from __future__ import annotations

import ctypes as ct
import os
import uuid


class _GUID(ct.Structure):
    _fields_ = [("data", ct.c_ubyte * 16)]


class _LUID(ct.Structure):
    _fields_ = [("low", ct.c_uint32), ("high", ct.c_int32)]


class _AdapterDesc1(ct.Structure):
    _fields_ = [
        ("description", ct.c_wchar * 128),
        ("vendor_id", ct.c_uint32), ("device_id", ct.c_uint32),
        ("subsys_id", ct.c_uint32), ("revision", ct.c_uint32),
        ("video_memory", ct.c_size_t), ("system_memory", ct.c_size_t),
        ("shared_memory", ct.c_size_t), ("luid", _LUID),
        ("flags", ct.c_uint32),
    ]


def _method(obj, slot, result, *args):
    vtable = ct.cast(obj, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    return ct.WINFUNCTYPE(result, ct.c_void_p, *args)(vtable[slot])


def _check(hr):
    if hr < 0:
        raise OSError(f"DXGI failed: HRESULT 0x{hr & 0xffffffff:08x}")


def enumerate_adapters() -> list[dict]:
    """Return original DXGI indices, names and software flags (including gaps)."""
    if os.name != "nt":
        return []
    dxgi = ct.WinDLL("dxgi.dll")
    create = dxgi.CreateDXGIFactory1
    create.argtypes = [ct.POINTER(_GUID), ct.POINTER(ct.c_void_p)]
    create.restype = ct.c_int32
    iid = _GUID.from_buffer_copy(uuid.UUID("770aae78-f26f-4dba-a829-253c83d1b387").bytes_le)
    factory = ct.c_void_p()
    _check(create(ct.byref(iid), ct.byref(factory)))
    adapters = []
    try:
        # IDXGIFactory1::EnumAdapters1 has the same order as EnumAdapters.
        enum = _method(factory, 12, ct.c_int32, ct.c_uint32, ct.POINTER(ct.c_void_p))
        index = 0
        while True:
            adapter = ct.c_void_p()
            hr = enum(factory, index, ct.byref(adapter))
            if hr & 0xffffffff == 0x887a0002:  # DXGI_ERROR_NOT_FOUND
                break
            _check(hr)
            try:
                desc = _AdapterDesc1()
                get_desc = _method(adapter, 10, ct.c_int32, ct.POINTER(_AdapterDesc1))
                _check(get_desc(adapter, ct.byref(desc)))
                adapters.append({
                    "id": index, "name": desc.description,
                    "software": bool(desc.flags & 2),
                    "memory_bytes": desc.video_memory,
                    "luid": f"{desc.luid.high & 0xffffffff:08x}:{desc.luid.low:08x}",
                })
            finally:
                _method(adapter, 2, ct.c_uint32)(adapter)
            index += 1
    finally:
        _method(factory, 2, ct.c_uint32)(factory)
    return adapters
