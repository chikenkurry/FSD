[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.deploy",
    [int]$WaitTimeoutSeconds = 300,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$environmentPath = if ([IO.Path]::IsPathRooted($EnvironmentFile)) {
    $EnvironmentFile
} else {
    Join-Path $root $EnvironmentFile
}
$stateDirectory = Join-Path $root ".local-data\deploy"
$statePath = Join-Path $stateDirectory "state.json"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$evidenceDirectory = Join-Path $stateDirectory "evidence\$timestamp"

function Invoke-Checked {
    param([Parameter(Mandatory)][scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

function Get-EnvironmentValue {
    param([Parameter(Mandatory)][string]$Name)
    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if ($processValue) { return $processValue }
    $line = Get-Content -LiteralPath $environmentPath | Where-Object {
        $_ -match "^$([regex]::Escape($Name))="
    } | Select-Object -Last 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1].Trim()
}

if (-not (Test-Path -LiteralPath $environmentPath)) {
    throw "Missing $environmentPath. Copy .env.deploy.example to .env.deploy and replace its token placeholder."
}

foreach ($command in @("docker", "git")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required but was not found on PATH."
    }
}

$token = Get-EnvironmentValue "INTERNAL_API_TOKEN"
if (-not $token -or $token.Length -lt 16 -or $token -eq "replace-with-a-long-random-token") {
    throw "INTERNAL_API_TOKEN must be replaced with a deployment-specific value of at least 16 characters."
}

Push-Location $root
try {
    Invoke-Checked { docker info --format '{{.ServerVersion}}' | Out-Null }
    $revision = (& git rev-parse --short=12 HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $revision) { throw "Unable to determine the Git revision." }
    if (& git status --porcelain) { $revision = "$revision-dirty" }
    $env:DEPLOY_IMAGE_TAG = $revision

    New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
    $compose = @(
        "compose", "-p", "what2do-poc",
        "--env-file", $environmentPath,
        "-f", (Join-Path $root "compose.integration.yaml"),
        "-f", (Join-Path $root "compose.deploy.yaml")
    )

    Write-Host "Deploying What2Do revision $revision"
    if (-not $SkipBuild) {
        Invoke-Checked { docker @compose build --pull }
    }
    Invoke-Checked { docker @compose up -d --wait --wait-timeout $WaitTimeoutSeconds }

    & (Join-Path $PSScriptRoot "smoke-deployment.ps1") `
        -EnvironmentFile $environmentPath `
        -ImageTag $revision `
        -EvidenceDirectory $evidenceDirectory
    if ($LASTEXITCODE -ne 0) { throw "Deployment smoke checks failed." }

    $previousTag = $null
    if (Test-Path -LiteralPath $statePath) {
        $previousState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $previousTag = $previousState.currentTag
    }
    $state = [ordered]@{
        currentTag = $revision
        previousTag = $previousTag
        deployedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
        evidenceDirectory = $evidenceDirectory
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    docker @compose ps | Tee-Object -FilePath (Join-Path $evidenceDirectory "compose-ps.txt")
    docker @compose images | Tee-Object -FilePath (Join-Path $evidenceDirectory "compose-images.txt")

    Write-Host "Deployment succeeded: http://127.0.0.1:15173"
    Write-Host "Evidence: $evidenceDirectory"
} catch {
    if (Test-Path -LiteralPath $evidenceDirectory) {
        docker @compose logs --no-color --tail 200 2>&1 |
            Set-Content -LiteralPath (Join-Path $evidenceDirectory "failure-logs.txt") -Encoding utf8
    }
    throw
} finally {
    Pop-Location
}
