param(
    [string]$EngineRoot = "C:\\Program Files\\Epic Games\\UE_5.8",
    [string]$UnrealCmd = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$Project = Join-Path $RepoRoot "unreal\\AirCombatWorld.uproject"
$Audit = Join-Path $RepoRoot "adapters\\unreal\\audit_xinyi_v2_world_partition.py"
$Saved = Join-Path $RepoRoot "unreal\\Saved\\XinyiUnrealV2"
$Report = Join-Path $Saved "ue_world_partition_audit.json"
$Log = Join-Path $Saved "world-partition-audit.log"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe"
}

if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (-not (Test-Path $Audit)) { throw "audit script not found: $Audit" }

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before the read-only partition audit."
}

New-Item -ItemType Directory -Force -Path $Saved | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue $Report

$env:ACW_XINYI_V2_WP_AUDIT_REPORT = $Report

Write-Host "Auditing persisted XinyiV2 World Partition / streaming ownership..."
& $UnrealCmd $Project "-ExecutePythonScript=$Audit" -unattended -nopause -nosound "-abslog=$Log"
if ($LASTEXITCODE -ne 0) {
    throw "World Partition audit failed ($LASTEXITCODE). See $Log"
}

if (-not (Test-Path $Report)) {
    throw "World Partition audit report was not written: $Report"
}

$receipt = Get-Content $Report -Raw | ConvertFrom-Json
if ($receipt.status -ne "PASS_WORLD_PARTITION_AUDIT") {
    Write-Host ($receipt | ConvertTo-Json -Depth 12)
    throw "XinyiV2 World Partition audit receipt is not PASS_WORLD_PARTITION_AUDIT."
}

Write-Host ""
Write-Host "XINYI_V2_WORLD_PARTITION_AUDIT_OK"
Write-Host "Level:              $($receipt.level)"
Write-Host "Partition present:  $($receipt.world_partition.present)"
Write-Host "Streaming enabled:  $($receipt.world_partition.enable_streaming)"
Write-Host "Decision input:     $($receipt.decision_input)"
Write-Host "Runtime tiles:      $($receipt.target_counts.loaded_runtime_building_tiles)"
Write-Host "Actor descriptors:  $($receipt.target_actor_descriptor_count)"
Write-Host "Descriptor error:   $($receipt.actor_descriptor_error)"
Write-Host "Report:             $Report"
Write-Host "Log:                $Log"
