#Requires -Version 5.1
<#
.SYNOPSIS
  Load AZURE_SQL_PASSWORD from Azure Key Vault into this PowerShell session.

.DESCRIPTION
  Dot-source so the password stays in the current session. `.\run.ps1` and
  `python run_all_components.py` already fetch the secret when
  AZURE_KEY_VAULT_NAME (or AZURE_KEY_VAULT_URL) is set in .env.

  Requires: `az login` (tenant that owns the vault), or
  AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET.

.EXAMPLE
  az login
  . .\scripts\load_sql_password_from_keyvault.ps1
  python run_all_components.py
#>

$ErrorActionPreference = "Stop"

if ($MyInvocation.InvocationName -ne '.') {
    Write-Host @"
Dot-source this script so the password stays in your session:
  . .\scripts\load_sql_password_from_keyvault.ps1
Or just run: python run_all_components.py   (or .\run.ps1)
"@
    exit 2
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not [string]::IsNullOrWhiteSpace($env:AZURE_SQL_PASSWORD)) {
    Write-Host "AZURE_SQL_PASSWORD is already set; skipping Key Vault."
    return
}

function Get-RepoPython {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    return $null
}

function Get-SqlPasswordFromAz {
    $vault = ($env:AZURE_KEY_VAULT_NAME | ForEach-Object { $_.Trim() })
    if ([string]::IsNullOrWhiteSpace($vault)) {
        $url = $env:AZURE_KEY_VAULT_URL
        if ([string]::IsNullOrWhiteSpace($url)) {
            $url = $env:AZURE_KEYVAULT_URL
        }
        if (-not [string]::IsNullOrWhiteSpace($url) -and $url -match "https?://([^.]+)\.vault\.azure\.net") {
            $vault = $Matches[1]
        }
    }
    if ([string]::IsNullOrWhiteSpace($vault)) {
        throw "Set AZURE_KEY_VAULT_NAME or AZURE_KEY_VAULT_URL to fetch the SQL password."
    }
    $secret = $env:AZURE_SQL_PASSWORD_SECRET_NAME
    if ([string]::IsNullOrWhiteSpace($secret)) {
        $secret = "azure-sql-password"
    }
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI (az) is not on PATH. Install it, then run az login."
    }
    $value = az keyvault secret show --vault-name $vault --name $secret --query value -o tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
        throw "Failed to load secret '$secret' from Key Vault '$vault'. Run az login and check access."
    }
    return $value.Trim()
}

$python = Get-RepoPython
$loader = Join-Path $Root "scripts\load_sql_password_from_keyvault.py"
$password = $null

if ($python -and (Test-Path $loader)) {
    if ($python -eq "py") {
        $password = & py -3 $loader --stdout
    }
    else {
        $password = & $python $loader --stdout
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load AZURE_SQL_PASSWORD from Key Vault (exit $LASTEXITCODE)."
    }
}
else {
    $password = Get-SqlPasswordFromAz
}

$env:AZURE_SQL_PASSWORD = "$password"
Write-Host "AZURE_SQL_PASSWORD is set from Key Vault (not printed)."
