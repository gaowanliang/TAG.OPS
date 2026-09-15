param(
    [ValidateSet("cuda", "directml", "cpu")]
    [string]$Backend = "directml"
)

$ErrorActionPreference = "Stop"

uv sync --extra $Backend --group build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

uv run --extra $Backend --group build pyinstaller `
    --clean `
    --noconfirm `
    TagOps.spec
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Build complete: dist\TagOps\TagOps.exe"
