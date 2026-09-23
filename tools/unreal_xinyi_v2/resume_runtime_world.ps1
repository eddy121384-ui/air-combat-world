param(
    [string]$InputRoot = "",
    [Nullable[long]]$RunId = $null,
    [string]$Repo = "eddy121384-ui/air-combat-world",
    [string]$Branch = "feat/xinyi-unreal-v2",
    [string]$Workflow = "xinyi-unreal-v2-contract.yml",
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string]$UnrealCmd = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
}
if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }

$InputsBase = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2Inputs"

function Download-InputRun {
    param([Parameter(Mandatory=$true)][long]$SelectedRunId)

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        throw "GitHub CLI (gh) is required to restore missing XinyiV2 inputs."
    }
    & gh auth status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI is not authenticated. Run 'gh auth login' first."
    }

    $dest = Join-Path $InputsBase ("run-" + $SelectedRunId)
    if (Test-Path $dest) {
        Remove-Item -Recurse -Force $dest
    }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null

    Write-Host "Restoring XinyiV2 input artifact from run $SelectedRunId..."
    & gh run download $SelectedRunId --repo $Repo --name "xinyi-unreal-v2-inputs" --dir $dest
    if ($LASTEXITCODE -ne 0) {
        throw "gh run download failed for run $SelectedRunId."
    }
    return $dest
}

if (-not $InputRoot) {
    $candidates = @(
        Get-ChildItem -Directory -Path $InputsBase -Filter "run-*" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^run-(\d+)
$ContractRoot = Join-Path $InputRoot "unreal\Saved\XinyiUnrealV2Contract"
$Contract = Join-Path $ContractRoot "xinyi_unreal_v2_contract.json"
$RuntimeBuildingDir = Join-Path $ContractRoot "building_runtime_tiles"
if (-not (Test-Path $Contract)) { throw "contract not found: $Contract" }
if (-not (Test-Path $RuntimeBuildingDir)) {
    throw "runtime building tile directory not found: $RuntimeBuildingDir"
}
$runtimeGlbs = @(Get-ChildItem -File -Filter "*.glb" $RuntimeBuildingDir)
if ($runtimeGlbs.Count -ne 25) {
    throw "Expected 25 runtime tile GLBs in restored inputs, found $($runtimeGlbs.Count)."
}
Write-Host "XINYI_V2_RESUME_INPUT_OK root=$InputRoot runtime_glbs=$($runtimeGlbs.Count)"

$PluginDll = Join-Path $RepoRoot "unreal\Plugins\XinyiLandscapeBridge\Binaries\Win64\UnrealEditor-XinyiLandscapeBridge.dll"
if (-not (Test-Path $PluginDll)) {
    throw "Compiled XinyiLandscapeBridge DLL is missing. Run the full local gate once first."
}

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before resume so saved packages are not file-locked."
}

$Saved = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2"
New-Item -ItemType Directory -Force -Path $Saved | Out-Null

$VerifyExisting = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_runtime_tiles_existing.py"
$PlaceRuntime = Join-Path $RepoRoot "adapters\unreal\place_xinyi_v2_runtime_tiles.py"
$VerifyRuntime = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_runtime_world_reopen.py"

$RuntimeImportReport = Join-Path $Saved "ue_runtime_tile_import.json"
$RuntimeWorldReport = Join-Path $Saved "ue_runtime_world.json"
$RuntimeWorldReopenReport = Join-Path $Saved "ue_runtime_world_fresh_reopen.json"

function Invoke-UEPython {
    param(
        [Parameter(Mandatory=$true)][string]$Script,
        [Parameter(Mandatory=$true)][string]$LogName
    )
    $LogPath = Join-Path $Saved $LogName
    Write-Host "=== UnrealEditor-Cmd resume: $Script ==="
    & $UnrealCmd $Project "-ExecutePythonScript=$Script" -unattended -nopause -nosound "-abslog=$LogPath"
    if ($LASTEXITCODE -ne 0) {
        throw "UnrealEditor-Cmd failed ($LASTEXITCODE). See $LogPath"
    }
}

$env:ACW_XINYI_V2_CONTRACT = $Contract
$env:ACW_XINYI_V2_CONTRACT_ROOT = $ContractRoot
$env:ACW_XINYI_V2_RUNTIME_IMPORT_REPORT = $RuntimeImportReport

# A. Inspect the 25 already-saved StaticMesh assets. No reimport, no bridge rebuild.
Invoke-UEPython -Script $VerifyExisting -LogName "resume-01-runtime-existing-verify.log"
$runtimeImportReceipt = Get-Content $RuntimeImportReport -Raw | ConvertFrom-Json
if ($runtimeImportReceipt.status -ne "PASS_RUNTIME_TILE_IMPORT") {
    Write-Host ($runtimeImportReceipt | ConvertTo-Json -Depth 8)
    throw "Persisted runtime tile validation is not PASS_RUNTIME_TILE_IMPORT."
}

# B. Place exactly 25 runtime building tile actors over the already-persisted Landscape.
$env:ACW_XINYI_V2_WORLD_REPORT = $RuntimeWorldReport
Invoke-UEPython -Script $PlaceRuntime -LogName "resume-02-runtime-world-place.log"
$runtimeWorldReceipt = Get-Content $RuntimeWorldReport -Raw | ConvertFrom-Json
if ($runtimeWorldReceipt.status -ne "PASS_RUNTIME_WORLD") {
    Write-Host ($runtimeWorldReceipt | ConvertTo-Json -Depth 8)
    throw "Runtime world placement is not PASS_RUNTIME_WORLD."
}

# C. Fresh process confirms Landscape + 25 building tile actors persist.
$env:ACW_XINYI_V2_WORLD_REOPEN_REPORT = $RuntimeWorldReopenReport
Invoke-UEPython -Script $VerifyRuntime -LogName "resume-03-runtime-world-fresh-reopen.log"
$runtimeWorldReopenReceipt = Get-Content $RuntimeWorldReopenReport -Raw | ConvertFrom-Json
if ($runtimeWorldReopenReceipt.status -ne "PASS_RUNTIME_WORLD_FRESH_REOPEN") {
    Write-Host ($runtimeWorldReopenReceipt | ConvertTo-Json -Depth 8)
    throw "Runtime world fresh-reopen is not PASS_RUNTIME_WORLD_FRESH_REOPEN."
}

Write-Host ""
Write-Host "XINYI_V2_RUNTIME_RESUME_OK"
Write-Host "Input root:           $InputRoot"
Write-Host "Runtime import:       $RuntimeImportReport"
Write-Host "Runtime world:        $RuntimeWorldReport"
Write-Host "Runtime world reopen: $RuntimeWorldReopenReport"
 } |
        Sort-Object { [long]($_.Name.Substring(4)) } -Descending
    )

    if ($RunId.HasValue) {
        $wanted = Join-Path $InputsBase ("run-" + $RunId.Value)
        if (Test-Path $wanted) {
            $InputRoot = (Resolve-Path $wanted).Path
        }
        else {
            $InputRoot = Download-InputRun -SelectedRunId $RunId.Value
        }
    }
    elseif ($candidates.Count -gt 0) {
        $InputRoot = $candidates[0].FullName
    }
    else {
        $json = & gh run list --repo $Repo --workflow $Workflow --branch $Branch --status success --limit 1 --json databaseId
        if ($LASTEXITCODE -ne 0) {
            throw "No local inputs and unable to query a successful XinyiV2 contract run."
        }
        $runs = @($json | ConvertFrom-Json)
        if ($runs.Count -eq 0) {
            throw "No local inputs and no successful XinyiV2 contract run found."
        }
        $InputRoot = Download-InputRun -SelectedRunId ([long]$runs[0].databaseId)
    }
}
else {
    $InputRoot = (Resolve-Path $InputRoot).Path
}

$ContractRoot = Join-Path $InputRoot "unreal\Saved\XinyiUnrealV2Contract"
$Contract = Join-Path $ContractRoot "xinyi_unreal_v2_contract.json"
if (-not (Test-Path $Contract)) { throw "contract not found: $Contract" }

$PluginDll = Join-Path $RepoRoot "unreal\Plugins\XinyiLandscapeBridge\Binaries\Win64\UnrealEditor-XinyiLandscapeBridge.dll"
if (-not (Test-Path $PluginDll)) {
    throw "Compiled XinyiLandscapeBridge DLL is missing. Run the full local gate once first."
}

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before resume so saved packages are not file-locked."
}

$Saved = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2"
New-Item -ItemType Directory -Force -Path $Saved | Out-Null

$VerifyExisting = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_runtime_tiles_existing.py"
$PlaceRuntime = Join-Path $RepoRoot "adapters\unreal\place_xinyi_v2_runtime_tiles.py"
$VerifyRuntime = Join-Path $RepoRoot "adapters\unreal\verify_xinyi_v2_runtime_world_reopen.py"

$RuntimeImportReport = Join-Path $Saved "ue_runtime_tile_import.json"
$RuntimeWorldReport = Join-Path $Saved "ue_runtime_world.json"
$RuntimeWorldReopenReport = Join-Path $Saved "ue_runtime_world_fresh_reopen.json"

function Invoke-UEPython {
    param(
        [Parameter(Mandatory=$true)][string]$Script,
        [Parameter(Mandatory=$true)][string]$LogName
    )
    $LogPath = Join-Path $Saved $LogName
    Write-Host "=== UnrealEditor-Cmd resume: $Script ==="
    & $UnrealCmd $Project "-ExecutePythonScript=$Script" -unattended -nopause -nosound "-abslog=$LogPath"
    if ($LASTEXITCODE -ne 0) {
        throw "UnrealEditor-Cmd failed ($LASTEXITCODE). See $LogPath"
    }
}

$env:ACW_XINYI_V2_CONTRACT = $Contract
$env:ACW_XINYI_V2_CONTRACT_ROOT = $ContractRoot
$env:ACW_XINYI_V2_RUNTIME_IMPORT_REPORT = $RuntimeImportReport

# A. Inspect the 25 already-saved StaticMesh assets. No reimport, no bridge rebuild.
Invoke-UEPython -Script $VerifyExisting -LogName "resume-01-runtime-existing-verify.log"
$runtimeImportReceipt = Get-Content $RuntimeImportReport -Raw | ConvertFrom-Json
if ($runtimeImportReceipt.status -ne "PASS_RUNTIME_TILE_IMPORT") {
    Write-Host ($runtimeImportReceipt | ConvertTo-Json -Depth 8)
    throw "Persisted runtime tile validation is not PASS_RUNTIME_TILE_IMPORT."
}

# B. Place exactly 25 runtime building tile actors over the already-persisted Landscape.
$env:ACW_XINYI_V2_WORLD_REPORT = $RuntimeWorldReport
Invoke-UEPython -Script $PlaceRuntime -LogName "resume-02-runtime-world-place.log"
$runtimeWorldReceipt = Get-Content $RuntimeWorldReport -Raw | ConvertFrom-Json
if ($runtimeWorldReceipt.status -ne "PASS_RUNTIME_WORLD") {
    Write-Host ($runtimeWorldReceipt | ConvertTo-Json -Depth 8)
    throw "Runtime world placement is not PASS_RUNTIME_WORLD."
}

# C. Fresh process confirms Landscape + 25 building tile actors persist.
$env:ACW_XINYI_V2_WORLD_REOPEN_REPORT = $RuntimeWorldReopenReport
Invoke-UEPython -Script $VerifyRuntime -LogName "resume-03-runtime-world-fresh-reopen.log"
$runtimeWorldReopenReceipt = Get-Content $RuntimeWorldReopenReport -Raw | ConvertFrom-Json
if ($runtimeWorldReopenReceipt.status -ne "PASS_RUNTIME_WORLD_FRESH_REOPEN") {
    Write-Host ($runtimeWorldReopenReceipt | ConvertTo-Json -Depth 8)
    throw "Runtime world fresh-reopen is not PASS_RUNTIME_WORLD_FRESH_REOPEN."
}

Write-Host ""
Write-Host "XINYI_V2_RUNTIME_RESUME_OK"
Write-Host "Input root:           $InputRoot"
Write-Host "Runtime import:       $RuntimeImportReport"
Write-Host "Runtime world:        $RuntimeWorldReport"
Write-Host "Runtime world reopen: $RuntimeWorldReopenReport"
