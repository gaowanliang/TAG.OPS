[English](README.md) | [中文](README_zh.md)

# TAG.OPS

<p align="center">
  <img src="img/icon.png" alt="TAG.OPS 图标" width="120" />
</p>

本地化的动漫图片自动打标工作台。支持快速扫描文件夹或拖拽图片，基于 WD14 及 Camie-tagger-v2 模型自动生成分类标签。

<p align="center">
  <img src="img/screenshot.jpeg" alt="TAG.OPS 截图" style="max-width:100%;width:900px;" />
</p>

完全在本地运行，支持 DirectML / CUDA / CPU 加速，所有数据不上云，保护隐私。

---

## 特性

- **开箱即用**：一键启动，自动打开本地 Web UI (`http://127.0.0.1:8765`)。
- **智能识别与管理**：
  - **双模式导入**：支持指定文件夹（含递归扫描）或直接拖拽图片。
  - **哈希去重**：利用 `xxh3_64` 算法对图片进行哈希计算。不论文件移动或重命名，均可跳过已处理图片，实现极速重扫。
  - **多样化导出**：打标结果一键保存为 `.txt` 或 `.json`，方便后续训练或管理。
  - **Top-N 智能聚类**：支持按置信度最高的标签对图片进行分类，并内置系统文件管理器，可直接复制/剪切图片到目标文件夹。
- **硬件智能感应**：自动探测 DirectML / CUDA / ROCm 及各 GPU 设备，支持手动切换推理后端。国内网络环境自动切换至 ModelScope 或 HF 镜像源进行模型下载。
- **其他沉浸式体验**：历史记录本地 SQLite 存储随时回溯、中英全屏双语无缝切换、现代化弹窗交互。

## 安装与启动

1. **安装 uv 并同步 DirectML 环境**

```bash
pip install uv
uv sync --extra directml
```

Windows 默认使用 DirectML。纯 CPU 环境可使用 `uv sync --extra cpu`；如需专用
NVIDIA CUDA 构建，可使用 `uv sync --extra cuda`。这些运行时选项互斥，不能同时启用。

2. **启动应用**

```bash
uv run --extra directml python main.py
```

启动后，浏览器会自动打开 `http://127.0.0.1:8765`。
_初次运行会自动下载所需的模型文件至 `models/` 目录下。_

## 打包 Windows 可执行程序

PyInstaller 单独放在 uv 的 `build` 依赖组中。默认构建 DirectML 版：

```powershell
.\scripts\build.ps1
```

构建其他运行时可显式传入 `-Backend cuda` 或 `-Backend cpu`。产物位于
`dist\TagOps\TagOps.exe`。分发时必须打包整个 `dist\TagOps` 目录；其中
`_internal` 保存 exe 所需的 Python、ONNX Runtime 和 CUDA 运行库。模型、日志及
可写的历史数据库仍位于 exe 同级目录，并在运行时自动创建。

## 目录结构简介

```text
├── main.py                 # 入口文件
├── pyproject.toml          # 项目元数据与依赖声明
├── uv.lock                 # 可复现的依赖锁文件
├── TagOps.spec             # PyInstaller 打包定义
├── scripts/build.ps1       # 可复现、可选后端的打包脚本
├── data/
│   ├── stg.csv             # 中文标签翻译表
│   └── history.db          # 本地运行历史数据库 (SQLite)
├── models/                 # 模型权重存放目录 (自动生成)
└── app/                    # 核心代码
    ├── config.py           # 配置与寻径
    ├── models/             # 模型推理与加载
    └── web/                # FastHTML Web 服务面板
```

## 技术栈

- **后端**: Python 3.11–3.13, [python-fasthtml](https://pypi.org/project/python-fasthtml/), Uvicorn, ONNX Runtime, huggingface_hub
- **前端**: 原生 HTML/JS/CSS，无 Node 依赖，轻量级
- **模型支持**: WD14 家族 (SmilingWolf), camie-tagger-v2 (Camais03)

## 协议与鸣谢

- 标签翻译表参考 `data/stg.csv` 原出处。
- 模型权重版权归属原作者 (SmilingWolf / Camais03)。
- 本项目开源免费使用，欢迎提交 PR 完善本工具。
