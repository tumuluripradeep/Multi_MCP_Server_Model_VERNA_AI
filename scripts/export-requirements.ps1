# Export installed packages from a local Python venv into requirements.txt (Option 1: pip freeze).
# Usage (from repo root):
#   .\scripts\export-requirements.ps1
#   .\scripts\export-requirements.ps1 -VenvPath "C:\path\to\.venv"
# Does not activate your shell globally; calls that venv's pip directly.

param(
    [string] $VenvPath = "",
    [string] $OutputFile = "requirements.txt"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $RepoRoot $OutputFile

if (-not $VenvPath) {
    foreach ($candidate in @(".venv", "venv", "env")) {
        $p = Join-Path $RepoRoot $candidate
        $pipTest = Join-Path $p "Scripts\pip.exe"
        if (Test-Path -LiteralPath $pipTest) {
            $VenvPath = $p
            break
        }
    }
}

if (-not $VenvPath) {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "No .venv/venv with Scripts\pip.exe found; using uv pip freeze from repo root."
        Set-Location $RepoRoot
        & uv pip freeze | Set-Content -LiteralPath $out -Encoding utf8
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $skip = @('^asyncio==', '^win32-setctime==')
        (Get-Content -LiteralPath $out) | Where-Object {
            $line = $_
            $drop = $false
            foreach ($p in $skip) { if ($line -match $p) { $drop = $true; break } }
            -not $drop
        } | Set-Content -LiteralPath $out -Encoding utf8
        $lines = (Get-Content -LiteralPath $out).Count
        Write-Host "Done. $lines packages pinned in $OutputFile. Commit and redeploy so Docker matches this venv."
        exit 0
    }
    Write-Error "No venv found. Create one (e.g. python -m venv .venv) or pass -VenvPath, or install uv."
    exit 1
}

$pip = Join-Path $VenvPath "Scripts\pip.exe"
$py = Join-Path $VenvPath "Scripts\python.exe"

Write-Host "Using venv: $VenvPath"
Write-Host "Writing: $out"

$freezeOk = $false
if (Test-Path -LiteralPath $pip) {
    & $pip freeze | Set-Content -LiteralPath $out -Encoding utf8
    if ($LASTEXITCODE -eq 0) { $freezeOk = $true }
}
if (-not $freezeOk -and (Test-Path -LiteralPath $py)) {
    & $py -m pip freeze 2>$null | Set-Content -LiteralPath $out -Encoding utf8
    if ($LASTEXITCODE -eq 0) { $freezeOk = $true }
}
if (-not $freezeOk) {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "pip not usable in venv; using: uv pip freeze (project env)"
        Push-Location $RepoRoot
        try {
            & uv pip freeze | Set-Content -LiteralPath $out -Encoding utf8
            if ($LASTEXITCODE -eq 0) { $freezeOk = $true }
        } finally {
            Pop-Location
        }
    }
}
if (-not $freezeOk) {
    Write-Error "Could not run pip freeze. Install pip in the venv or install uv (https://astral.sh/uv)."
    exit 1
}

# Strip packages that break or are irrelevant on Linux (Docker / Azure)
$skip = @('^asyncio==', '^win32-setctime==')
(Get-Content -LiteralPath $out) | Where-Object {
    $line = $_
    $drop = $false
    foreach ($p in $skip) { if ($line -match $p) { $drop = $true; break } }
    -not $drop
} | Set-Content -LiteralPath $out -Encoding utf8

$lines = (Get-Content -LiteralPath $out).Count
Write-Host "Done. $lines packages pinned in $OutputFile. Commit and redeploy so Docker matches this venv."
