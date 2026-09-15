"""Check session configuration and observe this process's first real GPU inference."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time

log = logging.getLogger(__name__)
CPU = "CPUExecutionProvider"
SAMPLE_INTERVAL = 1.0
MAX_POST_SAMPLES = 2
_ENGINE = re.compile(r"luid_0x([0-9a-f]+)_0x([0-9a-f]+)_.*engtype_(.+)$", re.I)
# Driver labels describe engine families, not the ORT execution provider. NVIDIA
# may record DirectML work on Graphics_1 while its 3D/Compute counters stay zero.
_COMPUTE_ENGINE = re.compile(r"(?:3d|compute|graphics|cuda)(?:_[0-9]+)?", re.I)
_NON_COMPUTE_ENGINE = re.compile(
    r"(?:copy|video(?:decode|encode|processing)|legacyoverlay|security|vr|ofa)(?:_[0-9]+)?", re.I
)


def engine_snapshot() -> dict[str, int]:
    """Windows raw running-time counters, scoped to this PID (not global GPU load)."""
    if os.name != "nt":
        raise OSError("当前系统不支持 Windows GPU 进程计数器")
    script = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
        "Get-CimInstance Win32_PerfRawData_GPUPerformanceCounters_GPUEngine "
        f"-Filter \"Name LIKE 'pid_{os.getpid()}_%'\" | "
        "Select-Object Name,RunningTime | ConvertTo-Json -Compress"
    )
    started = time.monotonic()
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            stderr=subprocess.PIPE, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("utf-8-sig", errors="replace").strip()
    except subprocess.CalledProcessError as exc:
        log.warning("GPU counter query failed: exit=%s stderr=%s", exc.returncode,
                    (exc.stderr or b"").decode("utf-8", errors="replace")[-4000:])
        raise
    rows = json.loads(out) if out else []
    if isinstance(rows, dict):
        rows = [rows]
    # WQL '_' is a wildcard: enforce the complete PID prefix again locally.
    prefix = f"pid_{os.getpid()}_"
    snapshot = {r["Name"].lower(): int(r["RunningTime"]) for r in rows
                if r["Name"].lower().startswith(prefix)}
    log.info("GPU counter snapshot: pid=%s query_ms=%.1f rows=%s own_rows=%s counters=%s",
             os.getpid(), (time.monotonic() - started) * 1000, len(rows), len(snapshot), snapshot)
    return snapshot


def active_adapters(before: dict, after: dict) -> dict[str, int]:
    """Graphics/compute engine deltas by physical LUID; copy-only traffic isn't proof."""
    active = {}
    for name, ticks in after.items():
        match = _ENGINE.search(name)
        if not match or not _COMPUTE_ENGINE.fullmatch(match[3]):
            continue
        delta = ticks - before.get(name, 0)
        if delta > 0:
            luid = f"{int(match[1], 16):08x}:{int(match[2], 16):08x}"
            active[luid] = active.get(luid, 0) + delta
    return active


def _sample_summary(before: dict, after: dict) -> dict:
    engines = {}
    positive = {}
    resets = 0
    unmatched = 0
    for name, ticks in after.items():
        match = _ENGINE.search(name)
        engine = match[3].lower() if match else "unknown"
        unmatched += match is None
        engines[engine] = engines.get(engine, 0) + 1
        delta = ticks - before.get(name, 0)
        if delta > 0:
            positive[engine] = positive.get(engine, 0) + delta
        elif delta < 0:
            resets += 1
    return {"counter_count": len(after), "engine_types": engines,
            "positive_time_100ns": positive, "reset_count": resets,
            "unmatched_count": unmatched,
            "unrecognized_active_engines": [e for e in positive
                if not _COMPUTE_ENGINE.fullmatch(e) and not _NON_COMPUTE_ENGINE.fullmatch(e)]}


def session_check(session, requested_provider: str, device: dict | None) -> dict:
    active = session.get_providers()
    actual = active[0] if active else "unknown"
    result = {
        "status": "pending", "requested_provider": requested_provider,
        "actual_provider": actual, "expected_device": device,
        "registered_providers": active,
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
    started = time.monotonic()
    telemetry = {"pid": os.getpid(), "samples": [], "sample_interval_seconds": SAMPLE_INTERVAL}
    check["telemetry"] = telemetry
    try:
        from .dxgi import enumerate_adapters
        adapters = enumerate_adapters()
        log.info("GPU self-check start: phase=%s pid=%s expected=%s adapters=%s",
                 check.get("phase"), os.getpid(), check.get("expected_device"), adapters)
        before = engine_snapshot()
        sampled_at = time.monotonic()
        telemetry["before_count"] = len(before)
    except Exception as exc:
        telemetry["error"] = str(exc)
        check.update(status="unverified", reason="counters_unavailable",
                     message="GPU 进程计数器不可用，尚未验证实际设备")
        log.warning("GPU self-check telemetry unavailable", exc_info=True)
        log.info("GPU self-check: %s", check)
        return infer()
    # Inference errors must propagate, never execute a second time as a telemetry fallback.
    infer_started = time.monotonic()
    result = infer()
    telemetry["inference_ms"] = round((time.monotonic() - infer_started) * 1000, 1)
    try:
        for _ in range(MAX_POST_SAMPLES):
            # Windows performance counters are not designed for sub-second collection.
            # Re-read delayed counters if needed; NEVER rerun the image to obtain evidence.
            delay = SAMPLE_INTERVAL - (time.monotonic() - sampled_at)
            if delay > 0:
                time.sleep(delay)
            after = engine_snapshot()
            sampled_at = time.monotonic()
            summary = _sample_summary(before, after)
            summary["elapsed_ms"] = round((sampled_at - started) * 1000, 1)
            telemetry["samples"].append(summary)
            activity = active_adapters(before, after)
            if activity:
                break
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
        if summary["unrecognized_active_engines"]:
            check.update(status="unverified", reason="unrecognized_engines",
                         message="存在无法识别的 GPU 引擎活动，详见日志；尚未验证实际显卡")
        elif luid and set(activity) == {luid}:
            engines = ", ".join(e for e in summary["positive_time_100ns"]
                                if _COMPUTE_ENGINE.fullmatch(e))
            check.update(status="verified", reason="selected_device_active",
                         message=f"已观测到所选显卡执行计算：{expected['name']}（{engines}）")
        elif luid and activity and luid not in activity:
            check.update(status="mismatch", reason="other_device_active",
                         message="检测到其他显卡计算活动，未观测到所选显卡，请检查设备选择")
        else:
            if not after:
                reason, message = "no_process_counters", "未采集到本进程的 GPU 引擎计数器"
            elif not activity:
                if summary["unmatched_count"] == len(after):
                    reason, message = "unrecognized_counters", "GPU 计数器名称无法识别，详见日志"
                elif summary["positive_time_100ns"]:
                    reason, message = "non_compute_activity", "仅观测到复制等非计算引擎活动"
                else:
                    reason, message = "no_compute_delta", "GPU 计数器未记录到本次推理的计算时间增量"
            elif not luid:
                reason, message = "device_identity_unknown", "无法唯一对应所选显卡的物理标识"
            else:
                reason, message = "multiple_devices_active", "观测到多张显卡计算，无法唯一确认实际设备"
            check.update(status="unverified", reason=reason, message=message + "；尚未验证实际显卡")
    except Exception as exc:
        telemetry["error"] = str(exc)
        check.update(status="unverified", reason="counter_collection_failed",
                     message="GPU 活动采集失败，核验未完成")
        log.warning("GPU self-check telemetry failed", exc_info=True)
    log.info("GPU self-check: %s", check)
    return result
