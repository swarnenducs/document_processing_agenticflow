# Start FastAPI + Gradio UI together (Windows PowerShell).
# Prefers Python script so it works without uv on PATH.
# Usage:
#   .\run.ps1
#   .\run.ps1 --api-only
#   .\run.ps1 --ui-only

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-PythonRunner {
    param([string[]]$RunnerArgs)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 run_both.py @RunnerArgs
        return $LASTEXITCODE
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python run_both.py @RunnerArgs
        return $LASTEXITCODE
    }
    return $null
}

$code = Invoke-PythonRunner -RunnerArgs $args
if ($null -ne $code) {
    exit $code
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv run doc-app @args
    exit $LASTEXITCODE
}

Write-Error @"
Neither Python nor uv found on PATH.
Install Python 3.11+ then:
  pip install -r requirements.txt
  python run_both.py
Or install uv: https://docs.astral.sh/uv/getting-started/installation/
"@
exit 1
