param(
    [Parameter(Mandatory=$true)]
    [string]$InputRoot,

    [string]$UnrealCmd = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$Probe = Join-Path $RepoRoot "adapters\unreal\xinyi_v2_api_probe.py"
$Import = Join-Path $RepoRoot "adapters\unreal\import_xinyi_v2_buildings.py"
$Verify = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_building_import.py"

$InputRoot = (Resolve-Path $InputRoot).Path
$Contract = Join-Path $InputRoot "unreal\Saved\XinyiUnrealV2Contract\xinyi_unreal_v2_contract.json"
$BuildingDir = Join-Path $InputRoot "unreal\Saved\XinyiV2Full\run-01\tiles"

$Saved = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2"
New-Item -ItemType Directory -Force -Path $Saved | Out-Null
$ProbeOut = Join-Path $Saved "ue58_api_probe.json"
$ImportReport = Join-Path $Saved "ue_building_import.json"

if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (-not (Test-Path $Contract)) { throw "contract not found: $Contract" }
if (-not (Test-Path $BuildingDir)) { throw "building tile directory not found: $BuildingDir" }

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before the XinyiV2 import gate so asset saves cannot be held by file locks."
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

# Phase A: discover the actual promoted UE5.8 Python surface before Landscape code.
$env:ACW_XINYI_V2_PROBE_OUT = $ProbeOut
Invoke-UEPython -Script $Probe -LogName "01-api-probe.log"
if (-not (Test-Path $ProbeOut)) { throw "API probe did not write $ProbeOut" }

# Phase B: verified-SHA asset import only. No placement yet.
$env:ACW_XINYI_V2_CONTRACT = $Contract
$env:ACW_XINYI_V2_BUILDING_DIR = $BuildingDir
$env:ACW_XINYI_V2_IMPORT_REPORT = $ImportReport
Invoke-UEPython -Script $Import -LogName "02-building-import.log"
if (-not (Test-Path $ImportReport)) { throw "Building import did not write $ImportReport" }

$importReceipt = Get-Content $ImportReport -Raw | ConvertFrom-Json
if ($importReceipt.status -ne "PASS_ASSET_IMPORT") {
    throw "Building import receipt is not PASS_ASSET_IMPORT"
}

# Phase C: separate fresh process proves the saved assets actually persisted.
Invoke-UEPython -Script $Verify -LogName "03-building-fresh-reopen.log"

Write-Host ""
Write-Host "XINYI_V2_LOCAL_STAGE_OK"
Write-Host "API probe:       $ProbeOut"
Write-Host "Building report: $ImportReport"
Write-Host "Logs:            $Saved"
