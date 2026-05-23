# Deploys the Verna MCP stack to Azure Container Apps in resource group POC_OpenAI.
# Prerequisites: az CLI, Docker not required locally (build runs in Azure with ACR).
# Set Azure OpenAI (and optional) variables in the shell before running, or add them in the portal afterward.

param(
    [string] $ResourceGroup = "POC_OpenAI",
    [string] $Location = "eastus",
    [string] $AppName = "verna-mcp-poc",
    [string] $EnvironmentName = "verna-mcp-env"
)

# Azure CLI prints progress to stderr; Stop would treat that as a terminating error.
$ErrorActionPreference = "Continue"
# Avoid Azure CLI UnicodeEncodeError when streaming ACR build logs on Windows (cp1252).
$env:AZURE_CORE_NO_COLOR = "true"
$env:NO_COLOR = "1"
$env:PYTHONUTF8 = "1"
try { chcp 65001 | Out-Null } catch {}
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "Repository root: $RepoRoot"
Write-Host "Container runs: supervisord -> python main.py (+ nginx). Rebuild after Dockerfile changes."

az provider register --namespace Microsoft.App --wait 2>$null
az provider register --namespace Microsoft.OperationalInsights --wait 2>$null

$envArgs = @(
    "STREAMLIT_SERVER_ADDRESS=0.0.0.0",
    "PYTHONUNBUFFERED=1"
)

function Add-EnvIfSet([string] $Name) {
    $v = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($v) {
        $script:envArgs += "$Name=$v"
        Write-Host "Including environment variable: $Name"
    }
}

Add-EnvIfSet "AZURE_OPENAI_API_KEY"
Add-EnvIfSet "AZURE_OPENAI_ENDPOINT"
Add-EnvIfSet "AZURE_OPENAI_DEPLOYMENT"
Add-EnvIfSet "YOUTUBE_API_KEY"
Add-EnvIfSet "WEBSHARE_PROXY_USERNAME"
Add-EnvIfSet "WEBSHARE_PROXY_PASSWORD"
Add-EnvIfSet "WEBSHARE_PROXY_LOCATIONS"
Add-EnvIfSet "YOUTUBE_TRANSCRIPT_HTTP_PROXY"
Add-EnvIfSet "YOUTUBE_TRANSCRIPT_HTTPS_PROXY"
Add-EnvIfSet "GOOGLE_API_KEY"
Add-EnvIfSet "GOOGLE_SEARCH_ENGINE_ID"
Add-EnvIfSet "D365_CLIENT_ID"
Add-EnvIfSet "D365_CLIENT_SECRET"
Add-EnvIfSet "D365_TENANT_ID"
Add-EnvIfSet "SLACK_BOT_TOKEN"
Add-EnvIfSet "SLACK_APP_TOKEN"
Add-EnvIfSet "SLACK_TEAM_ID"
Add-EnvIfSet "SLACK_CHANNEL_IDS"

Write-Host "Running az containerapp up (build may take several minutes)..."
# Pass each KEY=VALUE as its own argument; a single joined string only applies the first var.
$upArgs = @(
    "containerapp", "up",
    "--name", $AppName,
    "--resource-group", $ResourceGroup,
    "--location", $Location,
    "--environment", $EnvironmentName,
    "--source", $RepoRoot,
    "--target-port", "8080",
    "--ingress", "external"
)
if ($envArgs.Count -gt 0) {
    $upArgs += "--env-vars"
    $upArgs += $envArgs
}
& az @upArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "az containerapp up failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# containerapp up can drop env vars on update; always sync full .env after deploy.
$syncScript = Join-Path $PSScriptRoot "sync-env-to-containerapp.ps1"
if (Test-Path -LiteralPath (Join-Path $RepoRoot ".env")) {
    Write-Host "Syncing environment variables from .env to Container App..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $syncScript `
        -ResourceGroup $ResourceGroup -AppName $AppName
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "sync-env-to-containerapp.ps1 failed; set secrets in Azure Portal if the app cannot start the agent."
    }
} else {
    Write-Warning "No .env at repo root; skipping env sync. Use sync-env-to-containerapp.ps1 or the portal."
}

Write-Host "Scaling container (2 CPU, 4Gi memory) for MCP workload..."
az containerapp update --name $AppName --resource-group $ResourceGroup --cpu 2 --memory 4Gi
if ($LASTEXITCODE -ne 0) {
    Write-Warning "az containerapp update (scale) failed; check app in portal."
}

$url = az containerapp show --name $AppName --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host ""
Write-Host "Deployed. HTTPS URL: https://$url"
Write-Host "Streamlit UI: https://$url/  |  FastAPI /api: https://$url/api/"
Write-Host "If the app fails health checks, set missing secrets in Azure Portal (Container App -> Secrets / Environment variables)."
