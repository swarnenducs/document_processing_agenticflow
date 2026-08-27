#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot Windows setup: install uv, Python, all workspace deps, and scaffold .env files.

.DESCRIPTION
  Run from the repo root (or this script will cd there):

    powershell -ExecutionPolicy Bypass -File .\install.ps1
    .\install.ps1
    .\install.ps1 -Run

  After it finishes, put API keys in .env, then start everything with:

    python run_all_components.py
    # or: .\install.ps1 -Run

.PARAMETER Run
  After install, start all components (document MCP, voice MCP, MAF, API, UI).

.PARAMETER SkipEnvCopy
  Do not copy .env.example files.

.PARAMETER SkipUvInstall
  Do not download uv if it is missing (fail instead).
#>
[CmdletBinding()]
param(
    [switch]$Run,
    [switch]$SkipEnvCopy,
    [switch]$SkipUvInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = $PSScriptRoot
Set-Location $RepoRoot

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Refresh-UserPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $extra = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin")
    )
    $parts = @($env:Path, $machine, $user) + $extra
    $env:Path = ($parts | Where-Object { $_ } | ForEach-Object { $_.TrimEnd(";") }) -join ";"
}

function Ensure-Uv {
    Refresh-UserPath
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "uv already on PATH: $((Get-Command uv).Source)"
        return
    }
    if ($SkipUvInstall) {
        throw "uv is not on PATH. Install from https://docs.astral.sh/uv/ or omit -SkipUvInstall."
    }
    Write-Step "Installing uv (Astral)"
    irm https://astral.sh/uv/install.ps1 | iex
    Refresh-UserPath
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv installed but still not on PATH. Open a new PowerShell window and re-run .\install.ps1"
    }
}

function Copy-EnvExample([string]$ExamplePath, [string]$DestPath) {
    if (-not (Test-Path $ExamplePath)) {
        return
    }
    if (Test-Path $DestPath) {
        Write-Host "keep existing $DestPath"
        return
    }
    Copy-Item $ExamplePath $DestPath
    Write-Host "created $DestPath (fill in API keys)"
}

Write-Host "Document Processing Agentic Flow — Windows install"
Write-Host "Repo: $RepoRoot"

Ensure-Uv
uv --version

Write-Step "Ensuring Python 3.12 via uv"
uv python install 3.12

Write-Step "Syncing workspace packages (ip_api, MAF, document MCP, voice MCP, UI)"
uv sync --all-packages

if (-not $SkipEnvCopy) {
    Write-Step "Scaffolding .env files from examples (existing files are left alone)"
    Copy-EnvExample (Join-Path $RepoRoot ".env.example") (Join-Path $RepoRoot ".env")
    $components = @(
        "document-processing-mcp",
        "voice_enable_mcp",
        "central-agentic-flow",
        "ipp_agentic_api",
        "UI"
    )
    foreach ($name in $components) {
        $example = Join-Path $RepoRoot $name ".env.example"
        $dest = Join-Path $RepoRoot $name ".env"
        Copy-EnvExample $example $dest
    }
}

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Expected venv python at $python after uv sync."
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Edit .env and add OPENAI_API_KEY / GROQ_API_KEY / Azure keys as needed."
Write-Host "  2. Start all services:"
Write-Host "       uv run python run_all_components.py"
Write-Host "     or:  $python run_all_components.py"
Write-Host "     or:  .\run.ps1"
Write-Host "     or:  .\install.ps1 -Run"
Write-Host "  SQL password from Key Vault: set AZURE_KEY_VAULT_NAME in .env, az login,"
Write-Host "  then the launcher fetches it. One-off: . .\scripts\load_sql_password_from_keyvault.ps1"
Write-Host ""
Write-Host "Ports: API :8000  document MCP :8001  voice MCP :8002  MAF :8003  UI :7860"

if ($Run) {
    Write-Step "Starting all components"
    & $python (Join-Path $RepoRoot "run_all_components.py")
    exit $LASTEXITCODE
}
