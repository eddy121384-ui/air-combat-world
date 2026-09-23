param(
    [Parameter(Mandatory=$true)]
    [string]$InputRoot,

    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",

    [string]$UnrealCmd = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$Probe = Join-Path $RepoRoot "adapters\unreal\xinyi_v2_api_probe.py"
$Import = Join-Path $RepoRoot "adapters\unreal\import_xinyi_v2_buildings.py"
$Verify = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_building_import.py"
$BoundsProbe = Join-Path $RepoRoot "adapters\unreal\probe_xinyi_v2_building_bounds.py"
$PlacementPlanner = Join-Path $RepoRoot "adapters\unreal\plan_xinyi_v2_building_placement.py"
$BuildLandscape = Join-Path $RepoRoot "adapters\unreal\build_xinyi_v2_landscape.py"
$VerifyLandscape = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_landscape_reopen.py"
$PlaceSample = Join-Path $RepoRoot "adapters\unreal\place_xinyi_v2_sample_buildings.py"
$VerifySample = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_sample_reopen.py"
$BuildBridge = Join-Path $RepoRoot "tools\unreal_xinyi_v2\build_landscape_bridge.ps1"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
}

$InputRoot = (Resolve-Path $InputRoot).Path
$ContractRoot = Join-Path $InputRoot "unreal\Saved\XinyiUnrealV2Contract"
$Contract = Join-Path $ContractRoot "xinyi_unreal_v2_contract.json"
$BuildingDir = Join-Path $InputRoot "unreal\Saved\XinyiV2Full\run-01\tiles"

$Saved = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2"
New-Item -ItemType Directory -Force -Path $Saved | Out-Null
$ProbeOut = Join-Path $Saved "ue58_api_probe.json"
$ImportReport = Join-Path $Saved "ue_building_import.json"
$BoundsReport = Join-Path $Saved "ue_building_bounds.json"
$PlacementSummary = Join-Path $Saved "ue_building_placement_summary.json"
$PlacementPlan = Join-Path $Saved "ue_building_placement_plan.jsonl.gz"
$LandscapeReport = Join-Path $Saved "ue_landscape_create.json"
$LandscapeReopenReport = Join-Path $Saved "ue_landscape_fresh_reopen.json"
$SampleReport = Join-Path $Saved "ue_building_sample_placement.json"
$SampleReopenReport = Join-Path $Saved "ue_building_sample_fresh_reopen.json"

if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (-not (Test-Path $Contract)) { throw "contract not found: $Contract" }
if (-not (Test-Path $BuildingDir)) { throw "building tile directory not found: $BuildingDir" }
if (-not (Test-Path $BuildBridge)) { throw "landscape bridge build script not found: $BuildBridge" }

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before the XinyiV2 gate so asset/map saves cannot be held by file locks."
}

# The project explicitly enables the editor-only bridge, so compile it before
# the first UnrealEditor-Cmd process. Build products remain ignored/reproducible.
& $BuildBridge -EngineRoot $EngineRoot
if ($LASTEXITCODE -ne 0) {
    throw "XinyiLandscapeBridge build failed."
}

function Invoke-UEPython {
    param(
        [Parameter(Mandatory=$true)][string]$Script,
        [Parameter(Mandatory=$true)][string]$LogName
    )
    $LogPath = Join-Path $Saved $LogName
    Write-Host "=== UnrealEditor-Cmd: $Script ==="
    & $UnrealCmd $Project "-ExecutePythonScript=$Script" -unattended -nopause -nosound "-abslog=$LogPath"
    if ($LASTEXITCODE -ne 0) {
        throw "UnrealEditor-Cmd failed ($LASTEXITCODE). See $LogPath"
    }
}

# Clean disposable XinyiV2 content from interrupted prior local runs before UE starts.
$LegacyBuildingsDir = Join-Path $RepoRoot "unreal\Content\XinyiV2\Buildings"
$RuntimeBuildingsDir = Join-Path $RepoRoot "unreal\Content\XinyiV2\RuntimeBuildings"
if (Test-Path $LegacyBuildingsDir) {
    Write-Host "Removing interrupted legacy per-component import cache..."
    Remove-Item -Recurse -Force $LegacyBuildingsDir
}
if (Test-Path $RuntimeBuildingsDir) {
    Remove-Item -Recurse -Force $RuntimeBuildingsDir
}

# Phase A: record the actual promoted UE5.8 Python surface.
$env:ACW_XINYI_V2_PROBE_OUT = $ProbeOut
Invoke-UEPython -Script $Probe -LogName "01-api-probe.log"
if (-not (Test-Path $ProbeOut)) { throw "API probe did not write $ProbeOut" }

# Phase B: materialize accepted MOI terrain first; no building import yet.
$env:ACW_XINYI_V2_CONTRACT = $Contract
$env:ACW_XINYI_V2_CONTRACT_ROOT = $ContractRoot
$env:ACW_XINYI_V2_LANDSCAPE_REPORT = $LandscapeReport
Invoke-UEPython -Script $BuildLandscape -LogName "02-landscape-create.log"
if (-not (Test-Path $LandscapeReport)) { throw "Landscape build did not write $LandscapeReport" }
$landscapeReceipt = Get-Content $LandscapeReport -Raw | ConvertFrom-Json
if ($landscapeReceipt.status -ne "PASS_LANDSCAPE_CREATED") {
    throw "Landscape receipt is not PASS_LANDSCAPE_CREATED"
}

# Phase C: fresh process proves Landscape persistence.
$env:ACW_XINYI_V2_LANDSCAPE_REOPEN_REPORT = $LandscapeReopenReport
Invoke-UEPython -Script $VerifyLandscape -LogName "03-landscape-fresh-reopen.log"
if (-not (Test-Path $LandscapeReopenReport)) { throw "Landscape reopen did not write $LandscapeReopenReport" }
$reopenReceipt = Get-Content $LandscapeReopenReport -Raw | ConvertFrom-Json
if ($reopenReceipt.status -ne "PASS_LANDSCAPE_FRESH_REOPEN") {
    throw "Landscape fresh-reopen receipt is not PASS_LANDSCAPE_FRESH_REOPEN"
}

# Phase D: import the 25 staged runtime building tiles only.
$RuntimeImport = Join-Path $RepoRoot "adapters\unreal\import_xinyi_v2_runtime_tiles.py"
$PlaceRuntime = Join-Path $RepoRoot "adapters\unreal\place_xinyi_v2_runtime_tiles.py"
$VerifyRuntime = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_runtime_world_reopen.py"
$RuntimeImportReport = Join-Path $Saved "ue_runtime_tile_import.json"
$RuntimeWorldReport = Join-Path $Saved "ue_runtime_world.json"
$RuntimeWorldReopenReport = Join-Path $Saved "ue_runtime_world_fresh_reopen.json"

$env:ACW_XINYI_V2_RUNTIME_IMPORT_REPORT = $RuntimeImportReport
Invoke-UEPython -Script $RuntimeImport -LogName "04-runtime-tile-import.log"
if (-not (Test-Path $RuntimeImportReport)) { throw "Runtime tile import did not write $RuntimeImportReport" }
$runtimeImportReceipt = Get-Content $RuntimeImportReport -Raw | ConvertFrom-Json
if ($runtimeImportReceipt.status -ne "PASS_RUNTIME_TILE_IMPORT") {
    throw "Runtime tile import is not PASS_RUNTIME_TILE_IMPORT"
}

# Phase E: place exactly 25 building tile actors over the validated terrain.
$env:ACW_XINYI_V2_WORLD_REPORT = $RuntimeWorldReport
Invoke-UEPython -Script $PlaceRuntime -LogName "05-runtime-world-place.log"
if (-not (Test-Path $RuntimeWorldReport)) { throw "Runtime world placement did not write $RuntimeWorldReport" }
$runtimeWorldReceipt = Get-Content $RuntimeWorldReport -Raw | ConvertFrom-Json
if ($runtimeWorldReceipt.status -ne "PASS_RUNTIME_WORLD") {
    throw "Runtime world placement is not PASS_RUNTIME_WORLD"
}

# Phase F: one more process proves the 25 actors + Landscape persisted.
$env:ACW_XINYI_V2_WORLD_REOPEN_REPORT = $RuntimeWorldReopenReport
Invoke-UEPython -Script $VerifyRuntime -LogName "06-runtime-world-fresh-reopen.log"
if (-not (Test-Path $RuntimeWorldReopenReport)) { throw "Runtime world reopen did not write $RuntimeWorldReopenReport" }
$runtimeWorldReopenReceipt = Get-Content $RuntimeWorldReopenReport -Raw | ConvertFrom-Json
if ($runtimeWorldReopenReceipt.status -ne "PASS_RUNTIME_WORLD_FRESH_REOPEN") {
    throw "Runtime world fresh-reopen is not PASS_RUNTIME_WORLD_FRESH_REOPEN"
}

Write-Host ""
Write-Host "XINYI_V2_LOCAL_STAGE_OK"
Write-Host "API probe:              $ProbeOut"
Write-Host "Landscape report:       $LandscapeReport"
Write-Host "Landscape reopen:       $LandscapeReopenReport"
Write-Host "Runtime import:         $RuntimeImportReport"
Write-Host "Runtime world:          $RuntimeWorldReport"
Write-Host "Runtime world reopen:   $RuntimeWorldReopenReport"
Write-Host "Logs:                   $Saved"
