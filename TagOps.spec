# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — TagOps / Anime Image Classification Evaluation Tool.

打包：
    .\\scripts\\build.ps1 -Backend directml

产物：
    dist/TagOps/TagOps.exe

运行布局（分发给客户时用 zip 打包整个 TagOps/ 目录）：
    TagOps/
    ├── TagOps.exe
    ├── _internal/             ← Python、ONNX Runtime 与所选后端 DLL
    ├── data/tags_tr.yaml      ← 可编辑的标签翻译表
    ├── models/                ← 首次下载模型时自动生成
    └── logs/                  ← 首次运行自动生成

默认标签翻译内嵌在 _internal/data；如需覆盖，可把 tags_tr.yaml 放到
exe 同级的 data 目录。分发时应打包整个 dist/TagOps 目录，而不是只复制 exe。
"""

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    copy_metadata,
)

# Qt 绑定与本项目无关；在任何 hook 运行前先禁止 PyInstaller 的 Qt 自动检测，
# 避免 onnxruntime / fasthtml 等 collect_all 意外触发 PyQt/PySide hook。
import os
import runpy
os.environ.setdefault("PYINSTALLER_DISABLE_QT_BINDINGS", "1")

from importlib.util import find_spec
import sys
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

app_version = runpy.run_path(os.path.join(SPECPATH, "app", "version.py"))["APP_VERSION"]
version_parts = (tuple(int(part) for part in app_version.split(".")) + (0, 0, 0, 0))[:4]
windows_version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_parts, prodvers=version_parts,
                     mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", "TAG.OPS"),
            StringStruct("FileVersion", app_version),
            StringStruct("InternalName", "TagOps"),
            StringStruct("OriginalFilename", "TagOps.exe"),
            StringStruct("ProductName", "TAG.OPS"),
            StringStruct("ProductVersion", app_version),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

# ---- 强制带上 _ctypes / ssl 等需要的 Windows 基础 DLL --------------------
# PyInstaller 偶尔会漏 libffi-8.dll，导致 ImportError: DLL load failed
# while importing _ctypes。这里把 Python 的 DLLs 目录里常用的兜底打进去。
binaries = []
_dlls_dir = os.path.join(sys.base_prefix, "DLLs")
for _dll in (
    "libffi-8.dll",
    "libffi-7.dll",
    "libcrypto-3.dll",
    "libssl-3.dll",
    "libcrypto-1_1.dll",
    "libssl-1_1.dll",
    "sqlite3.dll",
):
    _p = os.path.join(_dlls_dir, _dll)
    if os.path.exists(_p):
        binaries.append((_p, "."))

# ---- 需要完整收集（py + data + dynlibs）的包 -----------------------------
_collect_full = [
    "onnxruntime",     # 包含 DirectML/CUDA provider DLL
    "fasthtml",        # 模板 / 静态资源 / 动态导入
    "starlette",
    "uvicorn",
    "huggingface_hub", # 模型下载
    "modelscope",      # 国内模型下载通道
]
datas = []
hiddenimports = []
for pkg in _collect_full:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# ---- 仅收集资源文件 -----------------------------------------------------
datas += collect_data_files("certifi")      # SSL 根证书

# ---- 仅收集二进制 -------------------------------------------------------
binaries += collect_dynamic_libs("xxhash")
binaries += collect_dynamic_libs("PIL")

# CUDA extra 中的 PyTorch cu130 wheel 提供 ORT 所需的 CUDA/cuDNN DLL。
# 保持 torch/lib 目录结构，运行时由 onnxruntime.preload_dlls() 显式加载。
if find_spec("torch") is not None:
    binaries += collect_dynamic_libs("torch")
    try:
        datas += copy_metadata("torch")
    except Exception:
        pass

# ---- 包元数据（部分库运行时会 importlib.metadata 查询） ------------------
for pkg in (
    "certifi",
    "huggingface_hub",
    "modelscope",
    "onnxruntime",
    "onnxruntime-directml",
    "onnxruntime-gpu",
):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# ---- 项目内部资源 -------------------------------------------------------
datas += [
    ("app/web/static", "app/web/static"),
    ("data/tags_tr.yaml", "data"),
]

# ---- 显式 hidden imports ------------------------------------------------
hiddenimports += [
    "app",
    "app.web",
    "app.web.views",
    "app.web.routes",
    "app.models",
    "app.models.loader",
    "app.models.registry",
    "app.models.interrogator",
    "xxhash",
    # onnxruntime provider 动态加载
    "onnxruntime.capi._pybind_state",
]

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 节省体积：这些包若非必要可排除
        "tkinter",
        "matplotlib",
        "pytest",
        "notebook",
        # onnxruntime 的量化子模块需要额外装 onnx 包；我们没用到
        "onnxruntime.quantization",
        "onnx",
        # Qt 绑定——本项目不用任何 GUI 框架，venv 里多半是传递依赖
        # 装上的（onnxruntime 的某些可选插件、或 jupyter 生态）
        "PyQt5",
        "PyQt5.QtCore",
        "PyQt5.QtGui",
        "PyQt5.QtWidgets",
        "PyQt6",
        "PySide2",
        "PySide6",
        "shiboken2",
        "shiboken6",
        "qtpy",
        "qtawesome",
        "IPython",
        "ipykernel",
        "jupyter",
        "jupyter_client",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TagOps",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # DLL 被 upx 压缩有时会被杀软误报，关掉
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,         # 想要无黑框改为 False（无控制台也就看不到启动日志）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="img/icon.png",
    version=windows_version,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TagOps",
)
