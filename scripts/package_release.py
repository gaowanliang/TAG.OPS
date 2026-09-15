"""Package a built Windows bundle, including editable tag translations."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import runpy
import shutil
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "dist/TagOps")
    parser.add_argument("--backend", choices=("directml", "cuda", "cpu"), default="directml")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    version = runpy.run_path(str(ROOT / "app/version.py"))["APP_VERSION"]
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if metadata["project"]["version"] != version:
        parser.error("Project and application versions differ")
    label = {"directml": "DirectML", "cuda": "CUDA", "cpu": "CPU"}[args.backend]
    output = args.output or ROOT / "dist" / f"TagOps-{version}-{label}-win64.zip"
    bundle = args.bundle.resolve()
    executable = bundle / "TagOps.exe"
    if not executable.is_file() or not (bundle / "_internal").is_dir():
        parser.error("Build the complete TagOps executable bundle first")
    files = [executable, *sorted(p for p in (bundle / "_internal").rglob("*") if p.is_file())]
    if args.backend == "directml":
        if not any(p.name.lower() == "directml.dll" for p in files):
            parser.error("DirectML.dll is missing")
        forbidden = ("cuda", "cudnn", "cublas", "cufft", "cusparse", "torch", "nvrtc")
        if any(p.suffix.lower() == ".dll" and any(s in p.name.lower() for s in forbidden) for p in files):
            parser.error("DirectML release unexpectedly contains CUDA/PyTorch DLLs")
    translation = bundle / "data/tags_tr.yaml"
    translation.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data/tags_tr.yaml", translation)
    files.append(translation)
    notes = ROOT / "docs" / f"release-{version}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, Path("TagOps") / path.relative_to(bundle))
        if notes.is_file():
            archive.write(notes, "TagOps/RELEASE_NOTES.md")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Release ZIP integrity check failed")
        if archive.read("TagOps/data/tags_tr.yaml") != (ROOT / "data/tags_tr.yaml").read_bytes():
            raise RuntimeError("Release tag translations differ from the source")
    with output.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Release: {output}\nSize: {output.stat().st_size / 2**20:.2f} MiB\nSHA256: {digest}")


if __name__ == "__main__":
    main()
