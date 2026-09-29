param(
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string]$UnrealCmd = "",
    [string]$Python = "python",
    [string]$Tod = "day,dusk,night",
    [string]$Shots = "",
    [switch]$SkipOffline,
    [switch]$CaptureOnly
)

# XinyiLook: Taipei visual layer over the validated XinyiV2 world.
#   1. offline  python tools/lookdev/build_all.py   (restores locked inputs from
#               data/lookdev_cache, re-runs the unchanged accepted pipeline only
#               where outputs are missing, then builds look-dev assets)
#   2. assets   materials (shared HLSL) + imports under /Game/XinyiLook
#   3. level    /Game/XinyiLook/L_XinyiLook_Hero (duplicate of the contract level)
#   4. capture  fresh-process reopen check + SceneCapture2D hero shots
# /Game/XinyiV2 and L_XinyiV2_Contract are never written.

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$Adapters = Join-Path $RepoRoot "adapters\unreal\lookdev"
$Reports = Join-Path $RepoRoot "unreal\Saved\XinyiLook\unreal"
$Logs = Join-Path $RepoRoot "unreal\Saved\XinyiLook\logs"

if (-not $UnrealCmd) {
    $UnrealCmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
}
if (-not (Test-Path $UnrealCmd)) { throw "UnrealEditor-Cmd not found: $UnrealCmd" }
if (-not (Test-Path $Project)) { throw "uproject not found: $Project" }
if (Get-Process UnrealEditor -ErrorAction SilentlyContinue) {
    throw "UnrealEditor GUI is running. Close it before the unattended XinyiLook stages."
}
New-Item -ItemType Directory -Force -Path $Reports, $Logs | Out-Null
$env:ACW_REPO_ROOT = $RepoRoot
$env:ACW_XINYI_LOOK_TOD = $Tod
$env:ACW_XINYI_LOOK_SHOTS = $Shots

function Invoke-Stage {
    param([string]$Name, [string]$Script, [string]$Report, [string]$Pass)
    $log = Join-Path $Logs ("$Name.log")
    $reportPath = Join-Path $Reports $Report
    Remove-Item -Force -ErrorAction SilentlyContinue $reportPath
    Write-Host "[$Name] UnrealEditor-Cmd $Script"
    & $UnrealCmd $Project "-ExecutePythonScript=$(Join-Path $Adapters $Script)" -unattended -nopause -nosound "-abslog=$log"
    if ($LASTEXITCODE -ne 0) { throw "[$Name] UnrealEditor-Cmd exited $LASTEXITCODE. See $log" }
    if (-not (Test-Path $reportPath)) { throw "[$Name] no receipt written: $reportPath (see $log)" }
    $r = Get-Content $reportPath -Raw | ConvertFrom-Json
    if ($r.status -ne $Pass) {
        Write-Host ($r | ConvertTo-Json -Depth 6)
        throw "[$Name] receipt status $($r.status), expected $Pass"
    }
    Write-Host "[$Name] $Pass"
}

if (-not $SkipOffline -and -not $CaptureOnly) {
    Write-Host "[offline] $Python tools/lookdev/build_all.py"
    Push-Location $RepoRoot
    try {
        & $Python "tools/lookdev/build_all.py"
        if ($LASTEXITCODE -ne 0) { throw "offline look-dev build failed ($LASTEXITCODE)" }
    } finally { Pop-Location }
}

if (-not $CaptureOnly) {
    Invoke-Stage -Name "assets" -Script "xinyi_look_build_assets.py" -Report "look_assets.report.json" -Pass "PASS_LOOK_ASSETS"
    Invoke-Stage -Name "level" -Script "xinyi_look_build_level.py" -Report "look_level.report.json" -Pass "PASS_LOOK_LEVEL"
}
Invoke-Stage -Name "capture" -Script "xinyi_look_capture.py" -Report "look_capture.report.json" -Pass "PASS_LOOK_CAPTURE"

$caps = Join-Path $Reports "captures"
Write-Host ""
Write-Host "XINYI_LOOK_OK"
Write-Host "Level:    /Game/XinyiLook/L_XinyiLook_Hero"
Write-Host "Captures: $caps"
Get-ChildItem -File -Filter "*.png" $caps | Sort-Object Name | ForEach-Object {
    Write-Host ("  {0}  {1:N0} bytes" -f $_.Name, $_.Length)
}
Start-Process explorer.exe $caps
