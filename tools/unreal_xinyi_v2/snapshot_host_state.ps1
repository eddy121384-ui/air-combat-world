param([string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8", [string]$RunId = "")
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $RunId) {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $short = (& git -C $RepoRoot rev-parse --short=8 HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Unable to resolve repository HEAD." }
    $RunId = "$stamp-$short"
}
$RunRoot = Join-Path $RepoRoot "unreal\Saved\XinyiHostGates\$RunId"
if (Test-Path $RunRoot) { throw "Run directory already exists; refusing overwrite: $RunRoot" }
& python (Join-Path $PSScriptRoot "snapshot_host_state.py") --repo $RepoRoot --engine-root $EngineRoot --run-root $RunRoot --run-id $RunId
if ($LASTEXITCODE -ne 0) { throw "Snapshot failed closed. Originals were not modified." }
Write-Host "XINYI_HOST_SNAPSHOT_OK run_id=$RunId root=$RunRoot"
