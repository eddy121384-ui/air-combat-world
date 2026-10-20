# North Taiwan forest world v1: EXPLORATORY real-time performance run (standalone -game, UE CSV profiler). Not a benchmark.
# The map's NF_PerfSequence auto-plays LS_NF_Perf in REAL TIME (6 stills x 8 s, then the 117 s flight at 240 m/s), so World Partition
# streaming and frame times are what a player would get on this host. One UE process at a time; nothing else heavy running.
#   run_nf_perf.ps1 -Tag pc_r1 [-ExecCmds "r.MaterialQualityLevel 0"] [-ResX 1920 -ResY 1080] [-Frames 6000]
param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_]+$')][string]$Tag, [string]$ExecCmds = '', [int]$ResX = 1920, [int]$ResY = 1080,
      [int]$Frames = 6000, [int]$FixedFps = 0, [string]$ExtraArgs = '', [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
for ($w = 0; $w -lt 60 -and (Get-Process UnrealEditor* -ErrorAction SilentlyContinue); $w++) { Start-Sleep -Seconds 2 }   # previous session still exiting
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$project = Join-Path $RepoRoot 'unreal\TreeLookdev\TreeLookdev.uproject'
$exe = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$out = Join-Path $RepoRoot "unreal\TreeLookdev\Saved\NorthForest\perf\$Tag"
if (Test-Path -LiteralPath $out) { throw "Refusing to overwrite prior run: $out" }
New-Item -ItemType Directory -Path $out | Out-Null
$exec = 'r.VSync 0,t.MaxFPS 0,r.MotionBlurQuality 0,r.GPUCsvStatsEnabled 1,csv.Category Memory 1'
if ($ExecCmds) { $exec = "$exec,$ExecCmds" }
$log = Join-Path $out 'engine.log'
$a = @("`"$project`"", '/Game/NorthForest/Maps/L_NF_Yangmingshan', '-game', '-windowed', "-ResX=$ResX", "-ResY=$ResY", '-ForceRes', '-nosound', '-nosplash',
       '-unattended', "-ExecCmds=`"$exec`"", "-csvCaptureFrames=$Frames", '-ExitAfterCsvProfiling', "-abslog=`"$log`"")
if ($ExtraArgs) { $a += $ExtraArgs }   # e.g. -dpcvars=r.Velocity.EnableVertexDeformation=0 (startup-time cvars)
if ($FixedFps -gt 0) { $a += @('-benchmark', "-fps=$FixedFps") }   # fixed step: every configuration renders the same frames
@{ tag = $Tag; args = $a; started = (Get-Date).ToString('o') } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'request.json') -Encoding utf8
$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath $exe -ArgumentList $a -WindowStyle Hidden -PassThru
$peak = 0
while (-not $proc.HasExited) { try { $proc.Refresh(); $peak = [math]::Max($peak, $proc.PeakWorkingSet64) } catch {}; Start-Sleep -Seconds 2 }
$m = [regex]::Matches((Get-Content -LiteralPath $log -Raw), 'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
if ($m.Count -eq 1) { Copy-Item -LiteralPath ([IO.Path]::GetFullPath((Join-Path (Split-Path $exe) $m[0].Groups[1].Value.Trim()))) -Destination (Join-Path $out 'profile.csv') }
@{ exit_code = $proc.ExitCode; seconds = [int]$sw.Elapsed.TotalSeconds; peak_working_set_mb = [int]($peak / 1MB); csv = ($m.Count -eq 1) } |
    ConvertTo-Json | Set-Content (Join-Path $out 'process.json') -Encoding utf8
Write-Host "NF_PERF $Tag exit=$($proc.ExitCode) csv=$($m.Count -eq 1) peakWS=$([int]($peak/1MB))MB $([int]$sw.Elapsed.TotalSeconds)s"
