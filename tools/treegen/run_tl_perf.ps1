# TreeLookdev: one standalone -game CSV-profiler run of a perf level (method copied from ForestSpike run_perf.ps1).
#   run_tl_perf.ps1 -Level L_TLP_front_tree -Tag r1a [-Frames 600]
# Host scope: Intel UHD 770 only. Do not run other heavy jobs at the same time (shared package power).
param(
    [Parameter(Mandatory)][ValidatePattern('^L_TL[PB]_[A-Za-z0-9_]+$')][string]$Level,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
    [int]$Frames = 600,
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8'
)
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Project = Join-Path $RepoRoot 'unreal\TreeLookdev\TreeLookdev.uproject'
$exe = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$engineBin = Split-Path $exe
$out = Join-Path $RepoRoot "unreal\TreeLookdev\Saved\TreeLookdev\perf\${Tag}__$Level"
if (Test-Path -LiteralPath $out) { throw "Refusing to overwrite prior run: $out" }
New-Item -ItemType Directory -Path $out | Out-Null
$log = Join-Path $out 'engine.log'
$exec = 'r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.GPUCsvStatsEnabled 1'
$argList = @("`"$Project`"", "/Game/TreeLookdev/Perf/$Level", '-game', '-windowed', '-ResX=1920', '-ResY=1080', '-nosound', '-nosplash',
    '-unattended', '-benchmark', '-fps=60', "-ExecCmds=`"$exec`"", "-csvCaptureFrames=$Frames", '-ExitAfterCsvProfiling', "-abslog=`"$log`"")
$proc = Start-Process -FilePath $exe -ArgumentList $argList -WindowStyle Hidden -Wait -PassThru
$text = Get-Content -LiteralPath $log -Raw
$m = [regex]::Matches($text, 'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
if ($m.Count -ne 1) { Write-Host "FAIL: no CSV in log ($out)"; exit 2 }
$src = [IO.Path]::GetFullPath((Join-Path $engineBin $m[0].Groups[1].Value.Trim()))
Copy-Item -LiteralPath $src -Destination (Join-Path $out 'profile.csv')
Write-Host "PERF_OK $Level $Tag exit=$($proc.ExitCode) -> $out"
