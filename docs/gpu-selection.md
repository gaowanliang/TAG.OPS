# GPU 选择与自检

自动模式在当前推理后端可枚举的显卡中，选择显存容量最大的设备，并显式传入该后端的设备 ID。DirectML 比较 DXGI 专用显存，CUDA/ROCm 比较运行时报告的设备总显存；不把集显的共享系统内存算作显存。容量相同则保留枚举顺序。手动选择优先于自动策略。设备枚举失败时保留运行时默认选择，并在日志中说明无法按显存排序。

界面显示显卡名称、显存容量和自动模式的目标显卡。GPU 编号属于当前推理后端，不保证与任务管理器编号一致。

每次创建模型会话后，先检查实际启用的后端和 ORT 返回的设备 ID（部分后端不提供 ID），再用固定生成的测试图片执行载入先验：验证推理能完成、输出非空且不含 NaN/Inf，并核验 GPU 活动。发现设备不一致或推理失败时停止加载。首张真实图片另行核验，保留载入先验结果供对照。

`get_providers()` 只表明会话注册了哪些后端，不代表模型算子实际交给了哪个后端。载入先验现在同时开启 ORT profiling，记录实际执行的节点，并在先验结束（包括推理失败）时停止记录。原始 JSON 保存在程序目录 `logs/ort-profiles/`，日志和 `device_check.preflight.execution_check` 提供每个后端的节点数、算子类型和 CPU 上的卷积/矩阵乘法等计算算子。若会话注册了 GPU，但完整执行记录表明模型算子全在 CPU（GPU 上只有复制节点也不算计算），则明确报错并停止加载。缺失或不完整的执行记录不推断为 CPU 回退。

部分形状处理等算子在 CPU 上执行并不代表 GPU 未参与。节点数量不能换算为计算量占比，profile 的 `host_duration_us` 是主机侧调用耗时，不能当作 GPU 硬件耗时。即使记录到 DirectML 执行算子，也仍需下面的物理设备活动证据才能确认是哪张显卡。

两次检查均通过 Windows GPU 性能计数器比较本进程的计算/图形引擎累计运行时间，并按物理适配器 LUID 对照所选显卡。接受 `3D`、`Compute`、`Graphics`、`CUDA` 及其数字后缀（例如 `Graphics_1`、`Compute_0`），大小写不敏感，按完整引擎名称匹配。这里的 `CUDA` 是驱动的引擎名称，不表示启用了 CUDA 推理后端。自检结果在硬件面板、批量状态 API 和单图识别 API 中提供，成功消息同时标明有活动的引擎。

不同驱动可能将 DirectML 计算记在不同引擎上。GTX 1660 SUPER 的测试日志中，`Graphics_1` 累计时间在推理前后增加，而 `3D` 和 `Compute_*` 保持为零；早期仅识别 Compute/3D 的代码因此漏报。仅复制/视频处理活动仍不能证明模型计算；出现未知引擎活动时报告未验证，不再把未知活动一概描述为复制等非计算活动。任务管理器可点击图表标题切换到有活动的引擎，见 [Microsoft GPU 引擎说明](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/)。

- **已观测到所选显卡计算**：采样期间只有目标显卡出现本进程计算活动。
- **显卡核验不一致**：ORT 返回不同的设备 ID，或只观测到其他显卡计算。
- **推理后端已回退**：例如 GPU 初始化失败后使用 CPU。
- **尚未验证实际显卡**：计数器不可用、没有足够计算活动、存在多卡活动，或无法唯一识别物理设备。不会把这些情况显示为成功。

CUDA/ROCm 暂通过唯一显卡名称关联 DXGI 的 LUID；同名多卡无法唯一对应时，显示未验证。非 Windows 环境仍能按显存选择设备、检查 ORT 配置，但不提供 Windows GPU 活动验证。

每个会话在载入和首张真实图片推理时各检查一次。每次先采集基线，再以至少一秒间隔查询推理后的计数器；没有计算活动时至多再查询一次，总共最多三次查询。补采计数器不会重复执行图片。后续图片直接推理。原始计数器、PID、LUID、查询耗时、引擎类型、时间增量和明确的未验证原因均写入日志；模型加载时还记录模型路径、大小、ORT 版本、目标设备和系统/驱动版本。

此检查验证采样期间本进程在哪张 GPU 上执行计算，不能证明所有算子均在 GPU 上，也不验证标签语义正确性。后续推理禁用 ORT 的自动后端切换，运行失败会报告错误，避免已验证的会话悄悄换卡。Python Tee 不能捕获直接写原生 stderr 的 ORT C++ 日志；持久保存的算子 profile 用于补充这一诊断缺口。

收到 `unverified` 报告时，需对照同一次运行的 `.log` 和 `logs/ort-profiles/` 下的 JSON：`no_process_counters` 表示没有本进程计数器，`no_compute_delta` 表示没有计算时间增量，`non_compute_activity` 表示只有已知的非计算活动，`unrecognized_engines` 表示存在未知引擎活动，`multiple_devices_active` 才表示多卡计算。不要仅凭后端列表或空 `observed_devices` 判断 GPU 已工作或已回退 CPU。

依据：[ORT profiling 文档](https://onnxruntime.ai/docs/performance/tune-performance/profiling-tools.html)、[ORT 1.24.4 执行记录实现](https://github.com/microsoft/onnxruntime/blob/v1.24.4/onnxruntime/core/framework/sequential_executor.cc)、[Windows 性能计数器采集间隔说明](https://learn.microsoft.com/en-us/windows/win32/perfctrs/about-performance-counters)。

验证：`python -m unittest discover -s tests -v`；前端：`node tests/test_frontend.cjs`。

DirectML 实机矩阵、结果和复现命令见 [DirectML 验证记录](directml-validation.md)。
