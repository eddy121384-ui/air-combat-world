param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [string]$Contract = ""
)
$ErrorActionPreference = "Stop"
if ($RunId -notmatch "^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$") { throw "Invalid RunId." }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunRoot = Join-Path $RepoRoot "unreal\Saved\XinyiHostGates\$RunId"
$SnapshotPath = Join-Path $RunRoot "00-snapshot.json"
$Out = Join-Path $RunRoot "10-streaming-route.json"
if (-not (Test-Path $SnapshotPath)) { throw "Snapshot missing: $SnapshotPath" }
if (Test-Path $Out) { throw "Route already exists; refusing overwrite: $Out" }
$Snapshot = Get-Content $SnapshotPath -Raw | ConvertFrom-Json
if ($Snapshot.status -ne "PASS_SNAPSHOT" -or $Snapshot.run_id -ne $RunId) { throw "Passing snapshot for this RunId is required." }
$Candidates = @($Snapshot.files | Where-Object { $_.category -eq "offline_contracts" })
if (-not $Contract) {
    if ($Candidates.Count -ne 1) { throw "Expected exactly one inventoried offline contract; specify -Contract from the snapshot file list." }
    $Contract = Join-Path $RepoRoot $Candidates[0].path
}
$Resolved = (Resolve-Path $Contract).Path
$Matches = @($Candidates | Where-Object {
    $Path = if ([System.IO.Path]::IsPathRooted($_.path)) { $_.path } else { Join-Path $RepoRoot $_.path }
    [System.IO.Path]::GetFullPath($Path) -eq $Resolved
})
if ($Matches.Count -ne 1) { throw "Selected contract is not in the snapshot inventory." }
$ActualHash = (Get-FileHash -Algorithm SHA256 $Resolved).Hash.ToLowerInvariant()
if ($Matches[0].sha256 -ne $ActualHash) { throw "Contract bytes changed since snapshot." }
& python (Join-Path $PSScriptRoot "prepare_streaming_route.py") `
    --contract $Resolved `
    --definitions (Join-Path $PSScriptRoot "host_gate_definitions.json") `
    --out $Out
if ($LASTEXITCODE -ne 0) { throw "Route preparation failed; no runtime gate ran." }
Write-Host "XINYI_ROUTE_PLAN_ONLY points=27 path=$Out"
