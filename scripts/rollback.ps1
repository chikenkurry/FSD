[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.deploy",
    [int]$WaitTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$statePath = Join-Path $root ".local-data\deploy\state.json"
$environmentPath = if ([IO.Path]::IsPathRooted($EnvironmentFile)) {
    $EnvironmentFile
} else {
    Join-Path $root $EnvironmentFile
}
if (-not (Test-Path -LiteralPath $statePath)) { throw "No deployment state exists to roll back." }
if (-not (Test-Path -LiteralPath $environmentPath)) { throw "Missing $environmentPath." }

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if (-not $state.previousTag) { throw "No previous successful deployment is recorded." }
$targetTag = $state.previousTag
$env:DEPLOY_IMAGE_TAG = $targetTag
$compose = @(
    "compose", "-p", "what2do-poc",
    "--env-file", $environmentPath,
    "-f", (Join-Path $root "compose.integration.yaml"),
    "-f", (Join-Path $root "compose.deploy.yaml")
)

Push-Location $root
try {
    Write-Host "Rolling back from $($state.currentTag) to $targetTag"
    docker @compose up -d --no-build --wait --wait-timeout $WaitTimeoutSeconds
    if ($LASTEXITCODE -ne 0) { throw "Compose rollback failed." }
    & (Join-Path $PSScriptRoot "smoke-deployment.ps1") -EnvironmentFile $environmentPath -ImageTag $targetTag
    if ($LASTEXITCODE -ne 0) { throw "Rollback smoke checks failed." }

    $rolledBackFrom = $state.currentTag
    $state.currentTag = $targetTag
    $state.previousTag = $rolledBackFrom
    $state.deployedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    Write-Host "Rollback succeeded: $targetTag is running."
} finally {
    Pop-Location
}
