# DirectML 实机验证（2026-09-15）

本轮以 DirectML 为主要验证后端，使用独立环境 `tmp/dml-test-env`，安装锁文件中的 `onnxruntime-directml 1.24.4`，没有安装 CUDA 版 ORT 或 PyTorch。现有开发环境未切换。

实测设备：

- DXGI 0：NVIDIA GeForce RTX 4060 Laptop GPU，专用显存 8,343,519,232 字节。
- DXGI 1：AMD Radeon 780M Graphics，专用显存 536,870,912 字节。

测试 `wd-eva02-large-tagger-v3` 和 `camie-tagger-v2`。每个模型分别在 CPU、自动模式、手动设备 0、手动设备 1 的独立进程中运行，合计 8 组测试。

## 结果

全部通过：

- 自动模式显式选择专用显存更大的 NVIDIA 设备 0。
- 手动设备 0 和设备 1 均实际使用 DirectML，没有回退 CPU。
- 载入先验和首张图片自检均为 `verified`：本进程的 GPU Compute/3D 计数器活动对应所选显卡的 DXGI LUID。
- DirectML 未回报 `device_id`；设备验证依据实际 GPU 活动，而不是把传入参数当作成功证据。
- 每组测试使用 `img/icon.png`、`img/screenshot.jpeg` 两张图片，并重复第一张。输出均非空、有限；不同输入的分数不同，同图重复分数最大差异为 0。
- 使用同一 DirectML 版 ORT 的 CPUExecutionProvider 作为数值基准。

| 模型 | NVIDIA 与 CPU 最大分数差异 | AMD 与 CPU 最大分数差异 |
| --- | ---: | ---: |
| WD EVA02 large v3 | 0.000003219 | 0.000218451 |
| Camie v2 | 0.000001490 | 0.000017375 |

数值比较使用 `numpy.allclose(atol=1e-3, rtol=1e-2)`；自动模式与手动 NVIDIA 的结果一致。这是设备映射、推理可执行性和数值一致性的冒烟测试，不是标签准确率评测。本机没有 Intel GPU，未覆盖原报告的 Intel UHD / RTX 4050 / 独显直连环境。

## 复现

在项目根目录运行 PowerShell：

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'tmp/dml-test-env'
uv sync --extra directml --frozen
tmp/dml-test-env/Scripts/python.exe -m unittest discover -s tests
tmp/dml-test-env/Scripts/python.exe scripts/validate_directml.py
tmp/dml-test-env/Scripts/python.exe scripts/validate_directml.py --model camie-tagger-v2 --output logs/directml-validation-camie
```

28 项自动化测试也已在这个 DirectML 环境下通过。脚本默认使用本地已下载的模型；模型缺失时会走应用现有下载逻辑。可通过 `--images 图片1 图片2` 换用复现样本。

完整报告、原始分数和日志分别位于 `logs/directml-validation/` 与 `logs/directml-validation-camie/`。每个进程限时 300 秒；设备不一致、回退、缺少活动证据、数值异常或超时均报告失败，脚本以非零退出码结束。
