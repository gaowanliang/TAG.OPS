"""Persist load-time ORT execution evidence, independently of Windows GPU counters."""
from __future__ import annotations

from collections import Counter
import json
import logging
import os
from pathlib import Path
import uuid

from .logging_setup import LOG_DIR

log = logging.getLogger(__name__)
CPU = "CPUExecutionProvider"
_COPY_OPS = {"Memcpy", "MemcpyFromHost", "MemcpyToHost"}
# These operators warrant attention on CPU; node counts are NOT compute percentages.
_COMPUTE_OPS = {
    "Conv", "FusedConv", "ConvTranspose", "MatMul", "FusedMatMul", "Gemm",
    "FusedMatMulActivation", "Attention", "MultiHeadAttention", "LSTM", "GRU",
}


def enable_profile(options) -> bool:
    """Unique files survive failures and do not depend on the current working directory."""
    try:
        folder = LOG_DIR / "ort-profiles"
        folder.mkdir(parents=True, exist_ok=True)
        options.profile_file_prefix = str(folder / f"load-{os.getpid()}-{uuid.uuid4().hex[:12]}")
        options.enable_profiling = True
        return True
    except Exception:
        log.warning("Cannot enable ORT execution profile", exc_info=True)
        return False


def summarize_profile(events: list, requested_provider: str) -> dict:
    """Read executed kernels, excluding fence events and treating missing data conservatively."""
    providers = {}
    unknown = 0
    runs = 0
    for event in events:
        if event.get("cat") == "Session" and event.get("name") == "model_run":
            runs += 1
        if event.get("cat") != "Node" or not event.get("name", "").endswith("_kernel_time"):
            continue
        args = event.get("args", {})
        provider, op = args.get("provider"), args.get("op_name")
        if not provider or not op:
            unknown += 1
            continue
        group = providers.setdefault(provider, {"node_count": 0, "host_duration_us": 0, "ops": Counter()})
        group["node_count"] += 1
        group["host_duration_us"] += event.get("dur", 0)
        group["ops"][op] += 1
    for group in providers.values():
        group["ops"] = dict(group["ops"])

    non_copy = {provider: sum(n for op, n in group["ops"].items() if op not in _COPY_OPS)
                for provider, group in providers.items()}
    non_copy = {provider: n for provider, n in non_copy.items() if n}
    cpu_ops = providers.get(CPU, {}).get("ops", {})
    summary = {
        "status": "unverified", "requested_provider": requested_provider,
        "completed_runs": runs, "providers": providers, "unknown_node_count": unknown,
        "cpu_compute_ops": {op: n for op, n in cpu_ops.items() if op in _COMPUTE_OPS},
        "message": "算子执行记录不足，尚未确认计算后端",
    }
    if runs and non_copy and not unknown:
        if set(non_copy) == {CPU}:
            summary.update(status="cpu_only", message="本次载入推理的模型算子全部由 CPU 执行")
        elif requested_provider != CPU and non_copy.get(requested_provider):
            summary.update(status="provider_observed", message="已记录所请求后端执行模型算子；物理显卡由活动自检另行核验")
    return summary


def finish_profile(session, requested_provider: str) -> dict:
    """Stop recording after the load probe so batches do not grow an unbounded trace."""
    path = ""
    try:
        path = session.end_profiling()
        if not path:
            raise ValueError("ORT did not return a profile file")
        events = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(events, list):
            raise ValueError("ORT profile is not an event list")
        summary = summarize_profile(events, requested_provider)
        summary["profile_file"] = path
        if summary["cpu_compute_ops"] and requested_provider != CPU:
            log.warning("ORT CPU compute operators: %s", summary["cpu_compute_ops"])
    except Exception as exc:
        log.warning("ORT execution profile unavailable", exc_info=True)
        summary = {"status": "unavailable", "profile_file": path,
                   "message": "算子执行记录不可用", "error": str(exc)}
    log.info("ORT execution check: %s", summary)
    return summary
