param(
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string]$UnrealCmd = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$Script = Join-Path $RepoRoot "adapters\unreal\capture_xinyi_v2_views.py"
$CaptureDir = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2\Captures"
$Report = Join-Path $CaptureDir "capture_report.json"
$Log = Join-Path $RepoRoot "unreal\Saved\XinyiUnrealV2\capture-views.log"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
}

if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (-not (Test-Path $Script)) { throw "capture script not found: $Script" }

$gui = Get-Process UnrealEditor -ErrorAction SilentlyContinue
if ($gui) {
    throw "UnrealEditor GUI is running. Close it before deterministic capture."
}

New-Item -ItemType Directory -Force -Path $CaptureDir | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $CaptureDir "*.png")
Remove-Item -Force -ErrorAction SilentlyContinue $Report

$env:ACW_XINYI_V2_CAPTURE_DIR = $CaptureDir

Write-Host "Capturing deterministic XinyiV2 QA views..."
& $UnrealCmd $Project "-ExecutePythonScript=$Script" -unattended -nopause -nosound "-abslog=$Log"
if ($LASTEXITCODE -ne 0) {
    throw "Unreal screenshot process failed ($LASTEXITCODE). See $Log"
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
Write-Host "XINYI_V2_CAPTURE_OK"
Write-Host "Capture directory: $CaptureDir"
$pngs | ForEach-Object {
    Write-Host ("  {0}  {1:N0} bytes" -f $_.Name, $_.Length)
}

Start-Process explorer.exe $CaptureDir
