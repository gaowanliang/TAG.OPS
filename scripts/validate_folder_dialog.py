"""Windows integration test: open real Explorer folder dialogs via HTTP and select/cancel.

The two test windows are automatically closed; no manual interaction is needed.
"""
from pathlib import Path
import ctypes as ct
from ctypes import wintypes as wt
import os
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient
from app.web import create_app


def main():
    user = ct.WinDLL("user32")
    user.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
    user.FindWindowW.restype = wt.HWND
    user.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
    user.IsWindowVisible.argtypes = [wt.HWND]
    user.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    with TestClient(create_app()[0], base_url="http://127.0.0.1:8765") as client:
        for action in (2, 1):  # IDCANCEL, IDOK
            title = "TAG.OPS Explorer test " + uuid.uuid4().hex
            observed = []

            def interact():
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    hwnd = user.FindWindowW("#32770", title)
                    pid = wt.DWORD()
                    if hwnd:
                        user.GetWindowThreadProcessId(hwnd, ct.byref(pid))
                    if hwnd and pid.value == os.getpid() and user.IsWindowVisible(hwnd):
                        observed.append(True)
                        # Allow the Shell view to finish navigation before accepting.
                        time.sleep(0.8)
                        user.PostMessageW(hwnd, 0x111, action, 0)
                        return
                    time.sleep(0.05)

            helper = threading.Thread(target=interact, daemon=True)
            helper.start()
            response = client.post("/api/dialog", json={
                "kind": "folder", "title": title, "initial_path": str(ROOT),
            })
            helper.join(timeout=1)
            assert observed, "No visible Explorer dialog was observed"
            assert response.status_code == 200, response.text
            result = response.json()["path"]
            if action == 2:
                assert result is None, result
            else:
                assert Path(result).resolve() == ROOT, result
            print(f"{'Cancel' if action == 2 else 'Select'}: visible native dialog, HTTP result={result!r}", flush=True)


if __name__ == "__main__":
    main()
