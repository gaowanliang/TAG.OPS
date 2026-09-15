[English](README.md) | [中文](README_zh.md)

# TAG.OPS

<p align="center">
  <img src="img/icon.png" alt="TAG.OPS icon" width="120" />
</p>

A local-first anime image auto-tagging workbench. Easily drop a folder or images to generate tags using WD14 and Camie-tagger-v2 models, organize them, and save the results.

<p align="center">
  <img src="img/screenshot.jpeg" alt="TAG.OPS screenshot" style="max-width:100%;width:900px;" />
</p>

Runs entirely local using ONNX Runtime. Supports DirectML, CUDA, and CPU fall-back.

---

## Features

- **Ready to Use**: One-click launcher that automatically opens a local Web UI at `http://127.0.0.1:8765`.
- **Smart Tagging & Organization**:
  - **Flexible Import**: Point to a directory (with optional recursion) or drop your images straight into the UI.
  - **Hash-based Caching**: Images are hashed via `xxh3_64`. Re-running a folder will skip previously tagged files based on content hash, completely ignoring renames or moves.
  - **Easy Export**: Save tagging results as `.txt` or `.json` for dataset preparation or indexing.
  - **Category View & Management**: Automatically cluster images by their Top-N tags. Includes built-in file operations to quickly copy/move categorized files.
- **Hardware Aware**: Automatically detects DirectML, CUDA, and ROCm providers. Lists available GPUs and allows you to pin a specific backend. Smart model downloading with mirror fallbacks.
- **Better UX**: SQLite-backed history tracking, seamless i18n toggles, and clean modal dialogs instead of raw browser alerts.

## Installation & Usage

1. **Install uv and Sync the DirectML Environment**

```bash
pip install uv
uv sync --extra directml
```

Windows releases use DirectML by default. Use `uv sync --extra cpu` for CPU
only, or `uv sync --extra cuda` for a separate NVIDIA CUDA environment.
These runtime extras are mutually exclusive.

2. **Start the Application**

```bash
uv run --extra directml python main.py
```

Your browser will automatically open `http://127.0.0.1:8765`.
_Models will be downloaded automatically to the `models/` directory on the first run._

## Build the Windows Executable

PyInstaller is isolated in uv's `build` dependency group. Build the DirectML
release with:

```powershell
.\scripts\build.ps1
```

The script builds `dist\TagOps\TagOps.exe` and creates
`dist\TagOps-1.1-DirectML-win64.zip`, including editable `data/tags_tr.yaml`
translations and release notes. Distribute the complete ZIP; `_internal`
contains the runtime libraries. Models, logs, and history remain next to the
executable. Other runtime builds require an explicit `-Backend cuda` or
`-Backend cpu` option.

## Project Structure

```text
├── main.py                 # Application entrypoint
├── pyproject.toml          # Project metadata and dependency definitions
├── uv.lock                 # Reproducible dependency lockfile
├── TagOps.spec             # PyInstaller build definition
├── scripts/build.ps1       # Reproducible backend-aware build command
├── data/
│   ├── tags_tr.yaml        # Editable tag translations
│   ├── stg.csv             # Legacy translation fallback
│   └── history.db          # Generated SQLite history tracking
├── models/                 # Auto-created directory for model weights
└── app/                    # Core application logic
    ├── config.py           # App configuration
    ├── models/             # Model loading and ONNX inference
    └── web/                # FastHTML views and API routes
```

## Tech Stack

- **Backend**: Python 3.11–3.13, [python-fasthtml](https://pypi.org/project/python-fasthtml/), Uvicorn, ONNX Runtime, huggingface_hub
- **Frontend**: Vanilla JS/CSS (no Node or build steps required)
- **Supported Models**: WD14 family (SmilingWolf), camie-tagger-v2 (Camais03)

## License & Credits

- Tag translation data originates from `data/stg.csv`.
- Model checkpoints and licenses belong to their respective creators (SmilingWolf / Camais03).
- Feel free to adapt and contribute!
