# Hillside forest look-dev v1: NATIVE Movie Render Queue frames of one sequence map (standalone -game, fixed 60 fps step).
# Same launch recipe as tools/treegen/run_tlf_mrq.ps1; configs from adapters/unreal/treelookdev/hf_mrq_configs.py.  Host: Intel UHD 770 only.
#   run_hf_mrq.ps1 -Tag hf_stills_forest_r1_01
param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag, [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$rec = Get-Content (Join-Path $RepoRoot 'unreal\TreeLookdev\Saved\TreeLookdev\reports\hf_mrq_configs.report.json') -Raw | ConvertFrom-Json
if ($rec.status -ne 'PASS_HF_MRQ_CONFIGS') { throw 'MRQ configs not built' }
$cfg = @($rec.configs | Where-Object tag -eq $Tag)
if ($cfg.Count -ne 1) { throw 'unknown Tag' }; $cfg = $cfg[0]
if ($cfg.game_overrides_enabled) { throw 'overrides forbidden' }
$out = Split-Path $cfg.output_directory
$log = Join-Path $out 'engine.log'
if (Test-Path -LiteralPath $log) { throw 'attempt already exists' }
$a = @("`"$(Join-Path $RepoRoot 'unreal\TreeLookdev\TreeLookdev.uproject')`"", $cfg.map, '-game', '-windowed', '-RenderOffscreen', '-ResX=1920', '-ResY=1080', '-ForceRes', '-nosound', '-nosplash',
    '-NoScreenMessages', '-unattended', '-benchmark', '-fps=60', "-MoviePipelineConfig=$($cfg.config)", "-LevelSequence=$($cfg.sequence)",
    '-MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelineInProcessExecutor', "-abslog=`"$log`"")
@{ tag = $Tag; config = $cfg; args = $a; started = (Get-Date).ToString('o') } | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'request.json') -Encoding utf8
$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $a -WindowStyle Hidden -Wait -PassThru
$n = @(Get-ChildItem -LiteralPath $cfg.output_directory -Filter '*.png' -Recurse -ErrorAction SilentlyContinue).Count
@{ exit_code = $proc.ExitCode; png_count = $n; expected = $cfg.frames; seconds = [int]$sw.Elapsed.TotalSeconds } | ConvertTo-Json | Set-Content (Join-Path $out 'process.json') -Encoding utf8
Write-Host "$Tag exit=$($proc.ExitCode) PNG=$n/$($cfg.frames) $([int]$sw.Elapsed.TotalSeconds)s"
