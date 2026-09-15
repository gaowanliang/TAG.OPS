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

## GTX 1660 SUPER 测试报告后的诊断验证

收到 `camie-tagger-v2` 在 GTX 1660 SUPER 上没有 GPU 活动的报告后，增加了载入推理的 ORT 算子记录、系统/驱动信息和 GPU 原始计数器日志，并延长计数器采样间隔。仅凭旧日志中的 `actual_provider=DmlExecutionProvider` 不能判断算子实际运行位置；当时尚未确认根因，后续诊断日志的结论见下文。

在上述同一 DirectML 环境重新跑了两个模型的全部 8 组测试，均通过，数值差异与表中一致。新增断言要求 GPU 模式必须有 DirectML 模型算子执行记录，CPU 基准必须记录为全 CPU。Camie v2 的 GPU 模式记录到 420 个 DirectML 节点和 213 个 CPU 节点，卷积和矩阵乘法在 DirectML 执行；节点数量不代表计算量占比。GPU 模式的载入和首图 LUID 检查仍均通过。

42 项 Python 自动化测试与前端检查通过。新增回归覆盖：DML 已注册但模型全在 CPU、DML 仅执行复制、缺失/不完整 profile、延迟计数器、计数器查询失败、精确 PID 过滤，以及自检失败后不重复推理。

本轮报告位于 `logs/directml-report-camie/report.json` 和 `logs/directml-report-wd/report.json`；原始 profile 位于 `logs/ort-profiles/`。未在 GTX 1660 SUPER 或 Intel UHD 上实测，不能据本机结果宣称测试人员的问题已经修复。

诊断包 `dist/TagOps-1.0-DirectML-diagnostics-win64.zip` 已从独立 DML 环境构建，检查无 CUDA/PyTorch DLL，ZIP 校验通过。将 ZIP 解压到中文路径后，直接运行打包的 EXE，通过 API 使用 Camie v2 识别两张不同图片：载入/首图 GPU 活动核验通过，算子 profile 和驱动/原始计数器日志均正确落盘。记录位于 `logs/frozen-gpu-diagnostics.json`。分发包不含测试日志或模型，包内附有复测说明。

## Graphics_1 引擎漏报修正

测试人员回传的 `20260915-160053-18176.log` 显示系统为 Windows 10 build 18363，NVIDIA 驱动版本 `32.0.15.8142`。同一进程（PID 18176）所选 GTX 1660 SUPER 的 LUID 为 `00000000:0000f73d`。载入先验执行了 420 个 DirectML 节点（包括 Conv、MatMul、Gemm）和 213 个 CPU 辅助节点；没有记录到 CPU 卷积/矩阵乘法。

| 阶段 | Graphics_1 累计值（前 → 后，单位 100 ns） | 增量 | 3D / Compute 增量 |
| --- | --- | --- | --- |
| 载入先验 | 778085 → 2619389 | 184.1304 ms | 0 |
| 首张图片 | 2619389 → 4069792 | 145.0403 ms | 0 |

这份日志证明所选 GPU 参与了本次推理。自检误报来自引擎过滤仅识别 Compute/3D，漏掉了该驱动的 `Graphics_1`。修正后识别图形/计算引擎名称及其数字后缀，并保留对复制、视频、未知活动和多卡活动的保守判断。

已将四份原始 GPU 计数器快照提取到 `tests/fixtures/gtx1660_gpu_counters.json`（不含图片、文件路径或完整用户日志）。46 项自动化测试通过，其中这份报告的载入和首图数据回放均核验到正确 LUID 与上述增量；其他显卡活动仍判不一致、多卡/未知活动仍不判成功。这是原始日志回归，不是在本机模拟一张 GTX 1660 SUPER。

同一日志在模型下载期间还出现四次 `[Errno 28] No space left on device`，随后成功加载 788,983,561 字节的 ONNX 文件。该下载问题独立于 GPU 引擎漏报。

修正后的 Camie v2 本机 DirectML 对照测试（CPU、自动、手动 NVIDIA、手动 AMD）四组均通过，分数与 CPU 的最大差异仍分别为 NVIDIA `1.49012e-6`、AMD `1.73748e-5`；载入和首图 LUID 核验均通过。报告位于 `logs/directml-graphics-camie/report.json`，测试人员原始日志回放结果位于 `logs/gtx1660-graphics-replay.json`。

修正版分发包为 `dist/TagOps-1.0-DirectML-gpucheck-fix-win64.zip`（97.85 MiB），已校验无 CUDA/PyTorch DLL。解压到新的中文路径后，打包 EXE 的 Camie v2 双图识别、载入/首图 LUID 自检和日志/profile 落盘均通过，报告位于 `logs/frozen-gpu-graphics-fix.json`。旧诊断包保留供对照。
