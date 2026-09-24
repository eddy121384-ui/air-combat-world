param(
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string]$UnrealCmd = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$Prepare = Join-Path $RepoRoot "adapters\unreal\prepare_xinyi_v2_whitebox_materials.py"
$Capture = Join-Path $RepoRoot "adapters\unreal\capture_xinyi_v2_views.py"
$CaptureDir = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2\Captures"
$MaterialsReport = Join-Path $CaptureDir "whitebox_materials_report.json"
$Report = Join-Path $CaptureDir "capture_report.json"
$PrepareLog = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2\prepare-whitebox.log"
$CaptureLog = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2\capture-views.log"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
}

if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (-not (Test-Path $Prepare)) { throw "whitebox material script not found: $Prepare" }
if (-not (Test-Path $Capture)) { throw "capture script not found: $Capture" }

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before deterministic capture."
}

New-Item -ItemType Directory -Force -Path $CaptureDir | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $CaptureDir "*.png")
Remove-Item -Force -ErrorAction SilentlyContinue $MaterialsReport
Remove-Item -Force -ErrorAction SilentlyContinue $Report

$env:ACW_XINYI_V2_CAPTURE_DIR = $CaptureDir

Write-Host "Preparing readable XinyiV2 whitebox materials..."
& $UnrealCmd $Project "-ExecutePythonScript=$Prepare" -unattended -nopause -nosound "-abslog=$PrepareLog"
if ($LASTEXITCODE -ne 0) {
    throw "Whitebox material preparation failed ($LASTEXITCODE). See $PrepareLog"
}
if (-not (Test-Path $MaterialsReport)) {
    throw "Whitebox material report was not written: $MaterialsReport"
}
$materialReceipt = Get-Content $MaterialsReport -Raw | ConvertFrom-Json
if ($materialReceipt.status -ne "PASS_WHITEBOX_MATERIALS") {
    Write-Host ($materialReceipt | ConvertTo-Json -Depth 8)
    throw "XinyiV2 whitebox material receipt is not PASS_WHITEBOX_MATERIALS."
}

Write-Host "Capturing readable XinyiV2 whitebox views..."
& $UnrealCmd $Project "-ExecutePythonScript=$Capture" -unattended -nopause -nosound "-abslog=$CaptureLog"
if ($LASTEXITCODE -ne 0) {
    throw "Unreal screenshot process failed ($LASTEXITCODE). See $CaptureLog"
}

if (-not (Test-Path $Report)) {
    throw "Capture report was not written: $Report"
}

$receipt = Get-Content $Report -Raw | ConvertFrom-Json
if ($receipt.status -ne "PASS_CAPTURE") {
    Write-Host ($receipt | ConvertTo-Json -Depth 8)
    throw "XinyiV2 capture receipt is not PASS_CAPTURE."
}

$pngs = @(Get-ChildItem -File -Filter "*.png" $CaptureDir | Sort-Object Name)
if ($pngs.Count -ne 4) {
    throw "Expected 4 XinyiV2 screenshots, found $($pngs.Count)."
}

Write-Host ""
Write-Host "XINYI_V2_READABLE_WHITEBOX_CAPTURE_OK"
Write-Host "Building material: $($materialReceipt.building.path)"
Write-Host "Terrain material:  $($materialReceipt.terrain.path)"
Write-Host "Capture directory: $CaptureDir"
$pngs | ForEach-Object {
    Write-Host ("  {0}  {1:N0} bytes" -f $_.Name, $_.Length)
}

Start-Process explorer.exe $CaptureDir
