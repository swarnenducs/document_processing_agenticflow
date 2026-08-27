#Requires -Version 5.1
<#
.SYNOPSIS
  Run each component's package_azure_webapp.ps1 and copy zips to dist\azure-webapp.

.EXAMPLE
  .\scripts\package_azure_webapp_zips.ps1
  .\scripts\package_azure_webapp_zips.ps1 api ui maf
#>
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
Set-Location $Root

$Dir = @{
    ui         = "UI"
    api        = "ipp_agentic_api"
    document   = "document-processing-mcp"
    voice      = "voice_enable_mcp"
    maf        = "central-agentic-flow"
}

function Resolve-Name([string]$arg) {
    switch ($arg.ToLowerInvariant()) {
        { $_ -in @("ui", "ui-app") } { return "ui" }
        { $_ -in @("api", "ip_api", "ip-api", "ipp_agentic_api", "ipp-agentic-api") } { return "api" }
        { $_ -in @("document", "document-processing-mcp", "document-mcp") } { return "document" }
        { $_ -in @("voice", "voice_enable_mcp", "voice-mcp") } { return "voice" }
        { $_ -in @("maf", "central-agentic-flow", "central_agentic_flow") } { return "maf" }
        default { throw "Unknown component: $arg" }
    }
}

$names = @()
if ($args.Count -eq 0 -or ($args.Count -eq 1 -and $args[0] -eq "all")) {
    $names = @("ui", "api", "document", "voice", "maf")
} else {
    foreach ($a in $args) { $names += (Resolve-Name $a) }
}

$outDir = Join-Path $Root "dist\azure-webapp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

foreach ($name in $names) {
    $folder = $Dir[$name]
    $script = Join-Path $Root "$folder\package_azure_webapp.ps1"
    $dest = Join-Path $outDir "$name.zip"
    Write-Host "==> $folder"
    & $script $dest
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host ""
Write-Host "Component scripts (use these after a repo split):"
Write-Host "  UI\package_azure_webapp.ps1"
Write-Host "  ipp_agentic_api\package_azure_webapp.ps1"
Write-Host "  document-processing-mcp\package_azure_webapp.ps1"
Write-Host "  voice_enable_mcp\package_azure_webapp.ps1"
Write-Host "  central-agentic-flow\package_azure_webapp.ps1"
Write-Host "Copied zips: $outDir"
