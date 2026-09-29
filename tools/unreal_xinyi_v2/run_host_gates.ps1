param(
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [ValidateSet("snapshot", "ownership", "streaming", "collision", "cook", "performance")][string]$Through = "snapshot",
    [string]$RunId = ""
)
$ErrorActionPreference = "Stop"
$Snapshot = Join-Path $PSScriptRoot "snapshot_host_state.ps1"
& $Snapshot -EngineRoot $EngineRoot -RunId $RunId
if ($LASTEXITCODE -ne 0) { throw "Snapshot prerequisite failed." }
if ($Through -eq "snapshot") { return }
throw "Stage '$Through' requires UE5.8 workstation implementation/verification. Snapshot is preserved; no runtime PASS emitted. See docs/architecture/xinyi-unreal-v2-host-gates.md."
