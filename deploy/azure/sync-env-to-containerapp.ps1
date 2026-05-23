# Pushes variables from repo-root .env into Azure Container App (add/update; does not print values).
# Usage: .\deploy\azure\sync-env-to-containerapp.ps1 [-EnvFile ..\.env]

param(
    [string] $ResourceGroup = "POC_OpenAI",
    [string] $AppName = "verna-mcp-poc",
    [string] $EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$fullPath = Join-Path $RepoRoot $EnvFile

if (-not (Test-Path -LiteralPath $fullPath)) {
    Write-Error "Env file not found: $fullPath"
    exit 1
}

$pairs = [ordered]@{}

Get-Content -LiteralPath $fullPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { return }
    $key = $line.Substring(0, $eq).Trim()
    $val = $line.Substring($eq + 1).Trim()
    if ($key -eq "") { return }
    $pairs[$key] = $val
}

$pairs["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"
$pairs["PYTHONUNBUFFERED"] = "1"

$setArgs = @()
foreach ($key in $pairs.Keys) {
    $setArgs += "$key=$($pairs[$key])"
}

Write-Host "Updating Container App '$AppName' with $($setArgs.Count) environment variables (values hidden)..."

$azArgs = @("containerapp", "update", "--name", $AppName, "--resource-group", $ResourceGroup, "--set-env-vars") + $setArgs
& az @azArgs

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Done. New revision should roll out shortly."
$url = az containerapp show --name $AppName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host "App URL: https://$url"
