"""Check session configuration and observe this process's first real GPU inference."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess

log = logging.getLogger(__name__)
CPU = "CPUExecutionProvider"


def engine_snapshot() -> dict[str, int]:
    """Windows raw running-time counters, scoped to this PID (not global GPU load)."""
    if os.name != "nt":
        raise OSError("当前系统不支持 Windows GPU 进程计数器")
    script = (
        "$ErrorActionPreference='Stop'; "
        "Get-CimInstance Win32_PerfRawData_GPUPerformanceCounters_GPUEngine "
        f"-Filter \"Name LIKE 'pid_{os.getpid()}_%'\" | "
        "Select-Object Name,RunningTime | ConvertTo-Json -Compress"
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        stderr=subprocess.PIPE, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).decode("utf-8", errors="replace").strip()
    rows = json.loads(out) if out else []
    if isinstance(rows, dict):
        rows = [rows]
    # WQL '_' is a wildcard: enforce the complete PID prefix again locally.
    prefix = f"pid_{os.getpid()}_"
    return {r["Name"]: int(r["RunningTime"]) for r in rows
            if r["Name"].startswith(prefix)}


def active_adapters(before: dict, after: dict) -> dict[str, int]:
    """Compute/3D engine deltas by physical LUID; copy-only traffic isn't proof."""
    active = {}
    for name, ticks in after.items():
        match = re.search(
            r"luid_0x([0-9a-f]+)_0x([0-9a-f]+)_.*engtype_(.+)$", name, re.I
        )
        if not match or not any(k in match[3].lower() for k in ("compute", "3d")):
            continue
        delta = ticks - before.get(name, 0)
        if delta > 0:
            luid = f"{int(match[1], 16):08x}:{int(match[2], 16):08x}"
            active[luid] = active.get(luid, 0) + delta
    return active


def session_check(session, requested_provider: str, device: dict | None) -> dict:
    active = session.get_providers()
    actual = active[0] if active else "unknown"
    result = {
        "status": "pending", "requested_provider": requested_provider,
        "actual_provider": actual, "expected_device": device,
        "reported_device_id": None, "observed_devices": [],
        "message": "等待首张图片推理后核验实际 GPU 活动",
    }
    if actual != requested_provider:
        result.update(status="fallback", message=f"后端已回退：{requested_provider} → {actual}")
        return result
    if actual == CPU:
        result.update(status="cpu", message="当前使用 CPU")
        return result
    try:
        reported = session.get_provider_options().get(actual, {}).get("device_id")
        if reported is not None:
            result["reported_device_id"] = int(reported)
            if device is not None and int(reported) != device["id"]:
                result.update(status="mismatch", message="ORT 返回的设备 ID 与所选显卡不一致")
    except Exception:
        log.debug("Provider does not expose device_id", exc_info=True)
    return result


def observe_inference(check: dict, infer):
    """Run once with telemetry. Missing evidence is explicitly inconclusive."""
    if check.get("status") != "pending":
        return infer()
    try:
        from .dxgi import enumerate_adapters
        adapters = enumerate_adapters()
        before = engine_snapshot()
    except Exception:
        check.update(status="unverified", message="GPU 进程计数器不可用，尚未验证实际设备")
        log.warning("GPU self-check telemetry unavailable", exc_info=True)
        return infer()
    # Inference errors must propagate, never execute a second time as a telemetry fallback.
    result = infer()
    try:
        activity = active_adapters(before, engine_snapshot())
        by_luid = {g["luid"]: g for g in adapters}
        observed = [dict(by_luid.get(luid, {"luid": luid, "name": "Unknown GPU"}),
                         running_time_100ns=ticks) for luid, ticks in activity.items()]
        expected = check.get("expected_device") or {}
        luid = expected.get("luid")
        if not luid:
            # CUDA names can be matched only when unique; identical cards are inconclusive.
            matches = [g for g in adapters if g["name"] == expected.get("name")]
            if len(matches) == 1:
                luid = matches[0]["luid"]
        check["observed_devices"] = observed
        if luid and set(activity) == {luid}:
            check.update(status="verified", message=f"已观测到所选显卡执行计算：{expected['name']}")
        elif luid and activity and luid not in activity:
            check.update(status="mismatch", message="检测到其他显卡计算活动，未观测到所选显卡，请检查设备选择")
        else:
            check.update(status="unverified", message="GPU 活动证据不足或存在多卡活动，尚未确认实际设备")
    except Exception:
        check.update(status="unverified", message="GPU 活动采集失败，核验未完成")
        log.warning("GPU self-check telemetry failed", exc_info=True)
    log.info("GPU self-check: %s", check)
    return result
