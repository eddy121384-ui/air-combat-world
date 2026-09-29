param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8"
)
$ErrorActionPreference = "Stop"
if ($RunId -notmatch "^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$") { throw "Invalid RunId." }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunRoot = Join-Path $RepoRoot "unreal\Saved\XinyiHostGates\$RunId"
$Snapshot = Join-Path $RunRoot "00-snapshot.json"
$Out = Join-Path $RunRoot "90-source-immutability.json"
if (-not (Test-Path $Snapshot)) { throw "Snapshot missing: $Snapshot" }
if (Test-Path $Out) { throw "Verification receipt exists; refusing overwrite: $Out" }
& python (Join-Path $PSScriptRoot "verify_snapshot_unchanged.py") `
    --repo $RepoRoot --engine-root $EngineRoot --snapshot $Snapshot --out $Out
if ($LASTEXITCODE -ne 0) { throw "Host source files changed or inventory failed. See $Out" }
Write-Host "XINYI_SOURCE_IMMUTABILITY_OK receipt=$Out"
