# North Taiwan forest world v1: native Movie Render Queue frames of one config (standalone -game; recipe of tools/forest/run_hf_mrq.ps1).
#   run_nf_mrq.ps1 -Rev 01 -Tag nf_flight_01      (configs from adapters/unreal/ntwforest/nf_mrq_configs.py)   Host: Intel UHD 770 only.
param([Parameter(Mandatory)][string]$Rev, [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
      [string]$ExecCmds = '', [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$rec = Get-Content (Join-Path $RepoRoot "unreal\TreeLookdev\Saved\NorthForest\reports\nf_mrq_configs_$Rev.report.json") -Raw -Encoding utf8 | ConvertFrom-Json
if ($rec.status -ne 'PASS_NF_MRQ_CONFIGS') { throw 'MRQ configs not built' }
$cfg = @($rec.configs | Where-Object tag -eq $Tag)
if ($cfg.Count -ne 1) { throw 'unknown Tag' }; $cfg = $cfg[0]
$out = Split-Path $cfg.output_directory
$log = Join-Path $out 'engine.log'
if (Test-Path -LiteralPath $log) { throw 'attempt already exists' }
$a = @("`"$(Join-Path $RepoRoot 'unreal\TreeLookdev\TreeLookdev.uproject')`"", $cfg.map, '-game', '-windowed', '-RenderOffscreen', '-ResX=1920', '-ResY=1080', '-ForceRes', '-nosound', '-nosplash',
    '-NoScreenMessages', '-unattended', "-MoviePipelineConfig=$($cfg.config)", "-LevelSequence=$($cfg.sequence)",
    '-MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelineInProcessExecutor', "-abslog=`"$log`"")
if ($ExecCmds) { $a += "-ExecCmds=`"$ExecCmds`"" }
@{ tag = $Tag; config = $cfg; args = $a; started = (Get-Date).ToString('o') } | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'request.json') -Encoding utf8
$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $a -WindowStyle Hidden -Wait -PassThru
$n = @(Get-ChildItem -LiteralPath $cfg.output_directory -Filter '*.png' -Recurse -ErrorAction SilentlyContinue).Count
@{ exit_code = $proc.ExitCode; png_count = $n; expected = $cfg.frames; seconds = [int]$sw.Elapsed.TotalSeconds } | ConvertTo-Json | Set-Content (Join-Path $out 'process.json') -Encoding utf8
Write-Host "$Tag exit=$($proc.ExitCode) PNG=$n/$($cfg.frames) $([int]$sw.Elapsed.TotalSeconds)s"
