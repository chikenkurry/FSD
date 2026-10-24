[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.deploy",
    [string]$ImageTag = "manual",
    [string]$EvidenceDirectory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$environmentPath = if ([IO.Path]::IsPathRooted($EnvironmentFile)) {
    $EnvironmentFile
} else {
    Join-Path $root $EnvironmentFile
}
$env:DEPLOY_IMAGE_TAG = $ImageTag
$compose = @(
    "compose", "-p", "what2do-poc",
    "--env-file", $environmentPath,
    "-f", (Join-Path $root "compose.integration.yaml"),
    "-f", (Join-Path $root "compose.deploy.yaml")
)
$checks = @(
    @{ Name = "Frontend"; Url = "http://127.0.0.1:15173/health" },
    @{ Name = "Planning"; Url = "http://127.0.0.1:18080/health" },
    @{ Name = "Participation"; Url = "http://127.0.0.1:13002/health/ready" }
)
$results = [System.Collections.Generic.List[object]]::new()

foreach ($check in $checks) {
    try {
        $response = Invoke-WebRequest -Uri $check.Url -UseBasicParsing -TimeoutSec 15
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
            throw "HTTP $($response.StatusCode)"
        }
        $results.Add([ordered]@{ check = $check.Name; url = $check.Url; status = "pass" })
        Write-Host "PASS $($check.Name): $($check.Url)"
    } catch {
        $results.Add([ordered]@{ check = $check.Name; url = $check.Url; status = "fail"; error = $_.Exception.Message })
        throw "Smoke check failed for $($check.Name): $($_.Exception.Message)"
    }
}

$unexpectedExited = @(docker @compose ps --status exited --services | Where-Object { $_ -and $_ -ne "decision-migrate" })
if ($LASTEXITCODE -ne 0) { throw "Could not inspect Compose service status." }
if ($unexpectedExited.Count -gt 0) {
    throw "Services exited unexpectedly: $($unexpectedExited -join ', ')"
}
$results.Add([ordered]@{ check = "Compose services"; status = "pass" })

if ($EvidenceDirectory) {
    New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
    [ordered]@{
        checkedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
        imageTag = $ImageTag
        result = "pass"
        checks = $results
    } | ConvertTo-Json -Depth 4 | Set-Content `
        -LiteralPath (Join-Path $EvidenceDirectory "smoke-results.json") -Encoding utf8
}

Write-Host "All deployment smoke checks passed."
