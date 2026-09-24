param(
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string]$UnrealCmd = "",
    [int]$CommandletTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$ContentDir = Join-Path $RepoRoot "unreal\Content\XinyiV2"
$SourceMap = Join-Path $ContentDir "L_XinyiV2_Contract.umap"
$ConvertedMap = Join-Path $ContentDir "L_XinyiV2_Contract_WP.umap"
$Audit = Join-Path $RepoRoot "adapters\unreal\audit_xinyi_v2_world_partition.py"
$Saved = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2"
$ReportOnlyLog = Join-Path $Saved "wp-convert-report-only.log"
$ConvertLog = Join-Path $Saved "wp-convert-isolated.log"
$SourceAuditLog = Join-Path $Saved "wp-source-postconvert-audit.log"
$ConvertedAuditLog = Join-Path $Saved "wp-converted-fresh-audit.log"
$SourceAuditReport = Join-Path $Saved "ue_world_partition_source_postconvert.json"
$ConvertedAuditReport = Join-Path $Saved "ue_world_partition_converted.json"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
}

if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (-not (Test-Path $SourceMap)) { throw "source XinyiV2 map not found: $SourceMap" }
if (-not (Test-Path $Audit)) { throw "World Partition audit script not found: $Audit" }

$editorProcesses = @(
    Get-Process UnrealEditor, UnrealEditor-Cmd -ErrorAction SilentlyContinue
)
if ($editorProcesses.Count -gt 0) {
    $names = ($editorProcesses | ForEach-Object { "$($_.ProcessName)[$($_.Id)]" }) -join ", "
    throw "An Unreal process is already running: $names . Close/wait for it before isolated World Partition conversion."
}

if (Test-Path $ConvertedMap) {
    throw "Isolated converted map already exists: $ConvertedMap . This gate will not overwrite/delete prior evidence."
}

New-Item -ItemType Directory -Force -Path $Saved | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue $SourceAuditReport
Remove-Item -Force -ErrorAction SilentlyContinue $ConvertedAuditReport

function Invoke-UnrealCommandlet {
    param(
        [Parameter(Mandatory=$true)][string[]]$ArgumentList,
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$LogPath
    )

    $process = Start-Process -FilePath $UnrealCmd -ArgumentList $ArgumentList -PassThru -NoNewWindow
    $finished = $process.WaitForExit($CommandletTimeoutSeconds * 1000)
    if (-not $finished) {
        try { $process.Kill() } catch {}
        try { $process.WaitForExit() } catch {}
        throw "$Name timed out after $CommandletTimeoutSeconds seconds. See $LogPath"
    }

    $exitCode = $process.ExitCode
    if ($exitCode -ne 0) {
        throw "$Name failed ($exitCode). See $LogPath"
    }

    return $exitCode
}

Write-Host "=== A. World Partition report-only preflight via UnrealEditor-Cmd (non-rendering, timeout $CommandletTimeoutSeconds s) ==="
$reportArgs = @(
    ('"{0}"' -f $Project),
    "-run=WorldPartitionConvertCommandlet",
    ('"{0}"' -f $SourceMap),
    "-ReportOnly",
    "-SCCProvider=None",
    "-Verbose",
    ('-abslog="{0}"' -f $ReportOnlyLog)
)
[void](Invoke-UnrealCommandlet -ArgumentList $reportArgs -Name "World Partition report-only preflight" -LogPath $ReportOnlyLog)

Write-Host "=== B. Isolated conversion via UnrealEditor-Cmd with _WP suffix; source map remains intact ==="
$convertArgs = @(
    ('"{0}"' -f $Project),
    "-run=WorldPartitionConvertCommandlet",
    ('"{0}"' -f $SourceMap),
    "-ConversionSuffix",
    "-SCCProvider=None",
    "-Verbose",
    ('-abslog="{0}"' -f $ConvertLog)
)
[void](Invoke-UnrealCommandlet -ArgumentList $convertArgs -Name "World Partition isolated conversion" -LogPath $ConvertLog)

if (-not (Test-Path $ConvertedMap)) {
    throw "Expected converted _WP map was not created: $ConvertedMap"
}

function Invoke-WPAudit {
    param(
        [Parameter(Mandatory=$true)][string]$Level,
        [Parameter(Mandatory=$true)][string]$Report,
        [Parameter(Mandatory=$true)][string]$Log
    )

    $env:ACW_XINYI_V2_AUDIT_LEVEL = $Level
    $env:ACW_XINYI_V2_WP_AUDIT_REPORT = $Report
    $auditArgs = @(
        $Project,
        "-ExecutePythonScript=$Audit",
        "-unattended",
        "-nopause",
        "-nosound",
        "-abslog=$Log"
    )
    & $UnrealCmd @auditArgs
    if ($LASTEXITCODE -ne 0) {
        throw "World Partition audit failed for $Level ($LASTEXITCODE). See $Log"
    }
    if (-not (Test-Path $Report)) {
        throw "World Partition audit report was not written: $Report"
    }
    return (Get-Content $Report -Raw | ConvertFrom-Json)
}

Write-Host "=== C. Prove the accepted source map is still non-partitioned ==="
$source = Invoke-WPAudit -Level "/Game/XinyiV2/L_XinyiV2_Contract" -Report $SourceAuditReport -Log $SourceAuditLog

if ($source.world_partition.present -ne $false) {
    throw "Source contract world changed unexpectedly; expected non-partitioned source."
}
if ($source.target_counts.loaded_runtime_building_tiles -ne 25) {
    throw "Source contract world no longer exposes 25 runtime tile actors."
}

Write-Host "=== D. Fresh-process audit of isolated _WP world ==="
$converted = Invoke-WPAudit -Level "/Game/XinyiV2/L_XinyiV2_Contract_WP" -Report $ConvertedAuditReport -Log $ConvertedAuditLog

if ($converted.status -ne "PASS_WORLD_PARTITION_AUDIT") {
    Write-Host ($converted | ConvertTo-Json -Depth 14)
    throw "Converted _WP world audit did not pass."
}
if ($converted.world_partition.present -ne $true) {
    throw "Converted _WP world does not expose World Partition."
}
if ($converted.target_counts.descriptor_terrain -ne 1) {
    throw "Converted _WP world does not contain exactly one terrain actor descriptor."
}
if ($converted.target_counts.descriptor_runtime_building_tiles -ne 25) {
    throw "Converted _WP world does not contain exactly 25 runtime tile actor descriptors."
}

Write-Host ""
Write-Host "XINYI_V2_ISOLATED_WP_MIGRATION_OK"
Write-Host "Source preserved:       /Game/XinyiV2/L_XinyiV2_Contract"
Write-Host "Partition test world:   /Game/XinyiV2/L_XinyiV2_Contract_WP"
Write-Host "WP present:             $($converted.world_partition.present)"
Write-Host "Streaming enabled:      $($converted.world_partition.enable_streaming)"
Write-Host "All actor descriptors:  $($converted.all_actor_descriptor_count)"
Write-Host "Terrain descriptors:    $($converted.target_counts.descriptor_terrain)"
Write-Host "Tile descriptors:       $($converted.target_counts.descriptor_runtime_building_tiles)"
Write-Host "Source audit:           $SourceAuditReport"
Write-Host "Converted audit:        $ConvertedAuditReport"
Write-Host "Next: deterministic streaming-source load/unload measurement; do not add HLOD yet."
