# North Taiwan forest: package the TreeLookdev project for Win64 (Development, pak + IoStore) - the PR #52 recipe as a script.
# Requires NF_PerfSequence auto-play ON in the map (nf_autoplay.py ACW_NF_AUTOPLAY=1) so the packaged game flies the perf sequence.
# The editor-only XinyiLandscapeBridge plugin is moved out of Plugins/ for the cook and always moved back.
#   package_win64.ps1 [-Log <path>]
param([string]$Log = '', [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$proj = Join-Path $RepoRoot 'unreal\TreeLookdev'
$plug = Join-Path $proj 'Plugins\XinyiLandscapeBridge'
$park = Join-Path $proj 'Build\_parked_XinyiLandscapeBridge'
if (-not $Log) { $Log = Join-Path $proj 'Saved\NorthForest\logs\buildcookrun.log' }
if (Test-Path -LiteralPath $park) { throw "parked plugin already exists: $park (move it back to Plugins first)" }
New-Item -ItemType Directory -Force -Path (Split-Path $park) | Out-Null
Move-Item -LiteralPath $plug -Destination $park
try {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & (Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat') BuildCookRun "-project=$(Join-Path $proj 'TreeLookdev.uproject')" `
        "-unrealexe=$(Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe')" -noP4 -platform=Win64 -clientconfig=Development `
        -build -cook -stage -pak -iostore -map=/Game/NorthForest/Maps/L_NF_Yangmingshan -unattended -utf8output *>&1 | Tee-Object -FilePath $Log | Out-Null
    $code = $LASTEXITCODE
    Write-Host "BUILDCOOKRUN exit=$code $([int]$sw.Elapsed.TotalMinutes) min log=$Log"
} finally {
    Move-Item -LiteralPath $park -Destination $plug
}
exit $code
