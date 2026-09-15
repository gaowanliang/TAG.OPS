param(
    [ValidateSet("cuda", "directml", "cpu")]
    [string]$Backend = "directml",
    [string]$DistPath = "dist",
    [string]$WorkPath = "build"
)

$ErrorActionPreference = "Stop"

uv sync --locked --extra $Backend --group build
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

uv run --locked --extra $Backend --group build pyinstaller `
    --clean `
    --noconfirm `
    --distpath $DistPath `
    --workpath $WorkPath `
    TagOps.spec
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

uv run --locked --extra $Backend --group build python scripts/package_release.py `
    --backend $Backend --bundle (Join-Path $DistPath "TagOps")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Build and release package complete."
