# Start FastAPI + Gradio UI together (Windows PowerShell).
# Usage:
#   .\run.ps1
#   .\run.ps1 --api-only
#   .\run.ps1 --ui-only

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed or not on PATH. Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

& uv run doc-app @args
exit $LASTEXITCODE
