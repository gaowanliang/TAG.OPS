"""Real DirectML validation: CPU reference, auto, and every DXGI GPU in isolated processes.

Run with a DirectML-only environment:
    python scripts/validate_directml.py
Reports and raw score arrays are saved under logs/directml-validation.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import numpy as np
    from PIL import Image
    from unittest.mock import patch
    from contextlib import nullcontext
    from app.models.loader import load_model
    from app.models.interrogator import interrogate

    started = time.monotonic()
    provider = "DmlExecutionProvider"
    if args.worker == "cpu":
        provider = "CPUExecutionProvider"
    scope = patch("app.models.loader.preferred_providers", return_value=[provider]) \
        if args.worker == "cpu" else nullcontext()
    device = None if args.worker in ("cpu", "auto") else int(args.worker)
    with scope:
        model = load_model(args.model, device_id=device)
    loaded = time.monotonic()
    vectors = []
    names = None
    for path in [args.images[0], args.images[1], args.images[0]]:
        with Image.open(path) as image:
            ratings, tags = interrogate(model, image)
        scores = {**ratings, **tags}
        if names is None:
            names = list(scores)
        vectors.append(np.asarray([scores[name] for name in names], dtype=np.float64))
    values = np.stack(vectors)
    np.save(args.output / f"{args.worker}.npy", values)
    check = model.device_check
    report = {
        "mode": args.worker, "model": args.model, "provider": model.provider,
        "load_seconds": loaded - started, "total_seconds": time.monotonic() - started,
        "device_check": check,
        "finite": bool(np.isfinite(values).all()),
        "different_image_max_delta": float(np.max(np.abs(values[0] - values[1]))),
        "repeat_max_delta": float(np.max(np.abs(values[0] - values[2]))),
        "top_tags": [[names[i] for i in np.argsort(row)[-10:][::-1]] for row in values[:2]],
    }
    (args.output / f"{args.worker}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="wd-eva02-large-tagger-v3")
    parser.add_argument("--output", type=Path, default=ROOT / "logs/directml-validation")
    parser.add_argument("--images", nargs=2, default=[str(ROOT / "img/icon.png"), str(ROOT / "img/screenshot.jpeg")])
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.worker is not None:
        worker(args)
        return

    import numpy as np
    import onnxruntime as ort
    from app.hardware import list_provider_gpus, largest_gpu
    if "DmlExecutionProvider" not in ort.get_available_providers():
        parser.error("Run this script using onnxruntime-directml")
    devices = list_provider_gpus("DmlExecutionProvider")
    if not devices:
        parser.error("No DirectML adapters were enumerated")
    modes = ["cpu", "auto", *[str(g["id"]) for g in devices]]
    reports = []
    for mode in modes:
        print(f"Testing {mode} ...", flush=True)
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", mode,
                   "--model", args.model, "--output", str(args.output), "--images", *args.images]
        with (args.output / f"{mode}.log").open("w", encoding="utf-8") as log:
            try:
                run = subprocess.run(command, cwd=ROOT, stdout=log, stderr=log, timeout=300)
                if run.returncode:
                    raise RuntimeError(f"Worker exited {run.returncode}; see {mode}.log")
                report = json.loads((args.output / f"{mode}.json").read_text(encoding="utf-8"))
                scores = np.load(args.output / f"{mode}.npy")
                baseline = np.load(args.output / "cpu.npy")
                report["cpu_max_abs_delta"] = float(np.max(np.abs(scores - baseline)))
                report["cpu_close"] = bool(np.allclose(scores, baseline, atol=1e-3, rtol=1e-2))
                target = largest_gpu(devices) if mode == "auto" else next(
                    (g for g in devices if str(g["id"]) == mode), None
                )
                check = report["device_check"]
                execution = check.get("preflight", {}).get("execution_check", {})
                report["execution_profile_ok"] = (
                    execution.get("status") == ("cpu_only" if mode == "cpu" else "provider_observed")
                )
                identity_ok = mode == "cpu" or (
                    report["provider"] == "DmlExecutionProvider"
                    and check.get("expected_device", {}).get("id") == target["id"]
                    and check["status"] == "verified"
                    and check["preflight"]["status"] == "verified"
                )
                report["passed"] = bool(identity_ok and report["execution_profile_ok"]
                    and report["finite"] and report["cpu_close"]
                    and report["different_image_max_delta"] > 1e-4
                    and report["repeat_max_delta"] < 1e-5)
                print(f"{mode}: passed={report['passed']}, check={check['status']}, "
                      f"CPU max delta={report['cpu_max_abs_delta']:.6g}", flush=True)
            except Exception as exc:
                report = {"mode": mode, "passed": False, "error": str(exc)}
                print(f"{mode}: {exc}", flush=True)
            reports.append(report)
    summary = {"ort_version": ort.__version__, "providers": ort.get_available_providers(),
               "devices": devices, "images": args.images, "results": reports}
    (args.output / "report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report: {args.output / 'report.json'}", flush=True)
    if not all(r["passed"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
