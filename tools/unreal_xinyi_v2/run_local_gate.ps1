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
$BuildLandscape = Join-Path $RepoRoot "adapters\unreal\build_xinyi_v2_landscape.py"
$VerifyLandscape = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_landscape_reopen.py"
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
$LandscapeReport = Join-Path $Saved "ue_landscape_create.json"
$LandscapeReopenReport = Join-Path $Saved "ue_landscape_fresh_reopen.json"

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

# Phase A: record the actual promoted UE5.8 Python surface. This is evidence,
# even though the C++ bridge is now the expected from-zero Landscape route.
$env:ACW_XINYI_V2_PROBE_OUT = $ProbeOut
Invoke-UEPython -Script $Probe -LogName "01-api-probe.log"
if (-not (Test-Path $ProbeOut)) { throw "API probe did not write $ProbeOut" }

# Phase B: verified-SHA building asset import only. No placement yet.
$env:ACW_XINYI_V2_CONTRACT = $Contract
$env:ACW_XINYI_V2_BUILDING_DIR = $BuildingDir
$env:ACW_XINYI_V2_IMPORT_REPORT = $ImportReport
Invoke-UEPython -Script $Import -LogName "02-building-import.log"
if (-not (Test-Path $ImportReport)) { throw "Building import did not write $ImportReport" }

$importReceipt = Get-Content $ImportReport -Raw | ConvertFrom-Json
if ($importReceipt.status -ne "PASS_ASSET_IMPORT") {
    throw "Building import receipt is not PASS_ASSET_IMPORT"
}

# Phase C: separate fresh process proves building assets actually persisted.
Invoke-UEPython -Script $Verify -LogName "03-building-fresh-reopen.log"

# Phase D: materialize the accepted uint16 height contract as a real ALandscape.
$env:ACW_XINYI_V2_CONTRACT_ROOT = $ContractRoot
$env:ACW_XINYI_V2_LANDSCAPE_REPORT = $LandscapeReport
Invoke-UEPython -Script $BuildLandscape -LogName "04-landscape-create.log"
if (-not (Test-Path $LandscapeReport)) { throw "Landscape build did not write $LandscapeReport" }

$landscapeReceipt = Get-Content $LandscapeReport -Raw | ConvertFrom-Json
if ($landscapeReceipt.status -ne "PASS_LANDSCAPE_CREATED") {
    throw "Landscape receipt is not PASS_LANDSCAPE_CREATED"
}

# Phase E: another new process proves .umap + ALandscape components persisted.
$env:ACW_XINYI_V2_LANDSCAPE_REOPEN_REPORT = $LandscapeReopenReport
Invoke-UEPython -Script $VerifyLandscape -LogName "05-landscape-fresh-reopen.log"
if (-not (Test-Path $LandscapeReopenReport)) { throw "Landscape reopen did not write $LandscapeReopenReport" }

$reopenReceipt = Get-Content $LandscapeReopenReport -Raw | ConvertFrom-Json
if ($reopenReceipt.status -ne "PASS_LANDSCAPE_FRESH_REOPEN") {
    throw "Landscape fresh-reopen receipt is not PASS_LANDSCAPE_FRESH_REOPEN"
}

Write-Host ""
Write-Host "XINYI_V2_LOCAL_STAGE_OK"
Write-Host "API probe:              $ProbeOut"
Write-Host "Building import report: $ImportReport"
Write-Host "Landscape report:       $LandscapeReport"
Write-Host "Landscape reopen:       $LandscapeReopenReport"
Write-Host "Logs:                   $Saved"
