# North Taiwan forest runtime gate: launch the PACKAGED Win64 game (staged by BuildCookRun) and record one real-time run.
# The map's NF_PerfSequence auto-plays LS_NF_Perf_P (3 held stills x 4 s, then the 117 s / 240 m/s hero flight).
#   run_packaged.ps1 -Tag pk_perf1 [-Frames 2600] [-ResX 1920 -ResY 1080] [-ExecCmds "..."] [-DumpMovie] [-ExtraArgs "..."]
# -DumpMovie: the engine writes every rendered frame (real time, not fixed step) to Saved/Screenshots (video evidence run; slower).
param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_]+$')][string]$Tag, [int]$Frames = 2600, [int]$ResX = 1920, [int]$ResY = 1080,
      [string]$ExecCmds = 'r.VSync 0', [switch]$DumpMovie, [string]$ExtraArgs = '')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stage = Join-Path $RepoRoot 'unreal\TreeLookdev\Saved\StagedBuilds\Windows'
$exe = Get-Item (Join-Path $stage 'TreeLookdev\Binaries\Win64\TreeLookdev.exe')   # the real game process (the staged root exe is a launcher stub)
if (-not $exe) { throw "no staged game exe under $stage" }
$out = Join-Path $RepoRoot "unreal\TreeLookdev\Saved\NorthForest\gate\runs\$Tag"
if (Test-Path -LiteralPath $out) { throw "exists: $out" }
New-Item -ItemType Directory -Path $out | Out-Null
$exec = "$ExecCmds,csv.Category Memory 1,r.GPUCsvStatsEnabled 1"
$a = @('TreeLookdev', '-windowed', "-ResX=$ResX", "-ResY=$ResY", '-ForceRes', '-nosound', '-nosplash', '-unattended', "-ExecCmds=`"$exec`"",
       "-csvCaptureFrames=$Frames", '-ExitAfterCsvProfiling', '-llm', "-abslog=`"$(Join-Path $out 'game.log')`"")
if ($DumpMovie) { $a += '-dumpmovie' }
if ($ExtraArgs) { $a += $ExtraArgs }
@{ tag = $Tag; exe = $exe.FullName; args = $a; started = (Get-Date).ToString('o') } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $out 'request.json') -Encoding utf8
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe.FullName -ArgumentList $a -PassThru
$peak = 0; $peakPriv = 0
while (-not $p.HasExited) { try { $p.Refresh(); $peak = [math]::Max($peak, $p.PeakWorkingSet64); $peakPriv = [math]::Max($peakPriv, $p.PrivateMemorySize64) } catch {}; Start-Sleep -Seconds 1 }
$csv = Get-ChildItem (Join-Path $stage 'TreeLookdev\Saved\Profiling\CSV') -Filter '*.csv' -ErrorAction SilentlyContinue | Where-Object LastWriteTime -gt $p.StartTime | Sort-Object LastWriteTime | Select-Object -Last 1
if ($csv) { Copy-Item $csv.FullName (Join-Path $out 'profile.csv') }
@{ exit_code = $p.ExitCode; seconds = [int]$sw.Elapsed.TotalSeconds; peak_working_set_mb = [int]($peak / 1MB); peak_private_mb = [int]($peakPriv / 1MB); csv = [bool]$csv } |
    ConvertTo-Json | Set-Content (Join-Path $out 'process.json') -Encoding utf8
Write-Host "PK_RUN $Tag exit=$($p.ExitCode) csv=$([bool]$csv) peakWS=$([int]($peak/1MB))MB $([int]$sw.Elapsed.TotalSeconds)s"
