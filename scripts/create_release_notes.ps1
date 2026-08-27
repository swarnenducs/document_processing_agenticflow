#Requires -Version 5.1
<#
.SYNOPSIS
  Write a markdown release note for each deployable component (and optional shared).

.EXAMPLE
  .\scripts\create_release_notes.ps1
  .\scripts\create_release_notes.ps1 api ui maf
  $env:BASE = "v1.0.0"; .\scripts\create_release_notes.ps1
  $env:OUT_DIR = ".\filechange_20260828_041422"; .\scripts\create_release_notes.ps1
#>
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
Set-Location $Root

$Dir = @{
    ui       = "UI"
    api      = "ip_api"
    document = "document-processing-mcp"
    voice    = "voice_enable_mcp"
    maf      = "central-agentic-flow"
    shared   = ""
}

$Label = @{
    ui       = "UI (Gradio)"
    api      = "ip_api (gateway API)"
    document = "document-processing-mcp"
    voice    = "voice_enable_mcp"
    maf      = "central-agentic-flow (MAF)"
    shared   = "shared (docs, scripts, samples, prompts)"
}

function Resolve-Name([string]$arg) {
    switch ($arg.ToLowerInvariant()) {
        { $_ -in @("ui", "ui-app") } { return "ui" }
        { $_ -in @("api", "ip_api", "ip-api") } { return "api" }
        { $_ -in @("document", "document-processing-mcp", "document-mcp") } { return "document" }
        { $_ -in @("voice", "voice_enable_mcp", "voice-mcp") } { return "voice" }
        { $_ -in @("maf", "central-agentic-flow", "central_agentic_flow") } { return "maf" }
        { $_ -in @("shared", "root", "docs", "scripts") } { return "shared" }
        default { throw "Unknown component: $arg" }
    }
}

function Get-PyprojectVersion([string]$file) {
    if (-not (Test-Path -LiteralPath $file)) { return "" }
    $m = Select-String -Path $file -Pattern '^version = "([^"]+)"' | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value }
    return ""
}

function Test-Git {
    try {
        $out = git -C $Root rev-parse --is-inside-work-tree 2>$null
        return ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "true")
    } catch {
        return $false
    }
}

function Get-GitText([string[]]$gitArgs) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $text = & git -C $Root @gitArgs 2>$null | Out-String
    $ErrorActionPreference = $prev
    return $text.TrimEnd()
}

$names = @()
if ($args.Count -eq 0 -or ($args.Count -eq 1 -and $args[0] -eq "all")) {
    $names = @("ui", "api", "document", "voice", "maf", "shared")
} else {
    foreach ($a in $args) { $names += (Resolve-Name $a) }
}

$stamp = $env:STAMP
if (-not $stamp) { $stamp = Get-Date -Format "yyyyMMdd_HHmmss" }
$outDir = $env:OUT_DIR
if (-not $outDir) { $outDir = Join-Path $Root "dist\release-notes\$stamp" }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$inGit = Test-Git
$branch = ""
$head = ""
$baseRef = $env:BASE
if ($inGit) {
    $branch = (Get-GitText @("rev-parse", "--abbrev-ref", "HEAD"))
    $head = (Get-GitText @("rev-parse", "--short", "HEAD"))
    if (-not $baseRef) {
        $baseRef = Get-GitText @("describe", "--tags", "--abbrev=0")
    }
    if (-not $baseRef) {
        git -C $Root rev-parse --verify origin/main 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $baseRef = "origin/main" }
    }
    if (-not $baseRef) {
        git -C $Root rev-parse --verify main 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $baseRef = "main" }
    }
}

function Write-Component([string]$name) {
    $folder = $Dir[$name]
    $label = $Label[$name]
    $outfile = Join-Path $outDir "$name.md"
    $pathspec = @()
    $version = ""
    if ($name -eq "shared") {
        $version = Get-PyprojectVersion (Join-Path $Root "pyproject.toml")
        $pathspec = @("docs", "scripts", "samples", "prompts", "postman", "README.md", ".env.example", "uv.lock", "pyproject.toml")
    } else {
        $version = Get-PyprojectVersion (Join-Path $Root "$folder\pyproject.toml")
        $pathspec = @($folder)
    }

    $when = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add("# Release notes — $label")
    [void]$lines.Add("")
    [void]$lines.Add("| Field | Value |")
    [void]$lines.Add("|-------|-------|")
    [void]$lines.Add("| Generated | $when |")
    [void]$lines.Add("| Stamp | $stamp |")
    [void]$lines.Add("| Component | ``$name`` |")
    if ($folder) { [void]$lines.Add("| Folder | ``$folder/`` |") }
    $verShow = if ($version) { $version } else { "n/a" }
    [void]$lines.Add("| Version (pyproject) | $verShow |")
    if ($inGit) {
        [void]$lines.Add("| Branch | ``$branch`` |")
        [void]$lines.Add("| HEAD | ``$head`` |")
        $baseShow = if ($baseRef) { $baseRef } else { "n/a" }
        [void]$lines.Add("| Compare from | ``$baseShow`` |")
    } else {
        [void]$lines.Add("| Git | not a git work tree |")
    }
    [void]$lines.Add("")
    [void]$lines.Add("## Summary")
    [void]$lines.Add("")
    [void]$lines.Add("Changes for this component since the compare ref (tags / origin/main / main), plus uncommitted files.")
    [void]$lines.Add("")

    if ($inGit) {
        [void]$lines.Add("## Commits")
        [void]$lines.Add("")
        $hasBase = $false
        if ($baseRef) {
            git -C $Root rev-parse --verify $baseRef 2>$null | Out-Null
            $hasBase = ($LASTEXITCODE -eq 0)
        }
        if ($hasBase) {
            $log = Get-GitText (@("log", "--pretty=format:- ``%h`` %ad %s", "--date=short", "$baseRef..HEAD", "--") + $pathspec)
        } else {
            $log = Get-GitText (@("log", "-20", "--pretty=format:- ``%h`` %ad %s", "--date=short", "--") + $pathspec)
        }
        if ($log) { [void]$lines.Add($log) } else { [void]$lines.Add("_No commits for these paths._") }
        [void]$lines.Add("")
        [void]$lines.Add("## Files changed (committed range)")
        [void]$lines.Add("")
        if ($hasBase) {
            $files = Get-GitText (@("diff", "--name-status", "$baseRef...HEAD", "--") + $pathspec)
            if ($files) {
                [void]$lines.Add('```')
                [void]$lines.Add($files)
                [void]$lines.Add('```')
            } else {
                [void]$lines.Add("_None._")
            }
        } else {
            [void]$lines.Add("_No compare ref; skipped._")
        }
        [void]$lines.Add("")
        [void]$lines.Add("## Uncommitted (staged, unstaged, untracked)")
        [void]$lines.Add("")
        $dirty = Get-GitText (@("status", "--short", "--") + $pathspec)
        if ($dirty) {
            [void]$lines.Add('```')
            [void]$lines.Add($dirty)
            [void]$lines.Add('```')
        } else {
            [void]$lines.Add("_Clean._")
        }
    } else {
        [void]$lines.Add("## Files in folder")
        [void]$lines.Add("")
        [void]$lines.Add('```')
        if ($name -eq "shared") {
            [void]$lines.Add(($pathspec -join "`n"))
        } else {
            Get-ChildItem -Path (Join-Path $Root $folder) -Recurse -File |
                Where-Object { $_.FullName -notmatch '\\(\.venv|__pycache__|dist|\.git)\\' } |
                ForEach-Object { $_.FullName.Substring($Root.Length + 1).Replace('\', '/') } |
                Sort-Object |
                ForEach-Object { [void]$lines.Add($_) }
        }
        [void]$lines.Add('```')
    }
    [void]$lines.Add("")
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($outfile, ($lines -join "`n"), $utf8)
    Write-Host "Wrote $outfile"
}

$indexPath = Join-Path $outDir "INDEX.md"
$when = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$idx = New-Object System.Collections.Generic.List[string]
[void]$idx.Add("# Release notes index")
[void]$idx.Add("")
[void]$idx.Add("Generated $when  ")
[void]$idx.Add("Stamp: ``$stamp``  ")
[void]$idx.Add("Output: ``$outDir``")
[void]$idx.Add("")
[void]$idx.Add("| Component | File |")
[void]$idx.Add("|-----------|------|")

foreach ($name in $names) {
    Write-Component $name
    $lab = $Label[$name]
    [void]$idx.Add("| $lab | [``$name.md``]($name.md) |")
}

$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($indexPath, ($idx -join "`n"), $utf8)

Write-Host ""
Write-Host "Release notes: $outDir"
Write-Host "Index: $indexPath"
