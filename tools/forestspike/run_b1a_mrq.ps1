param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
 [Parameter(Mandatory)][string]$ConfigReceipt)
$ErrorActionPreference='Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'Unreal already running' }
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$receipt=Get-Content -LiteralPath $ConfigReceipt -Raw | ConvertFrom-Json
if ($receipt.status -ne 'PASS_FS_B1A_MOVIE_CONFIGS') { throw 'Unverified MRQ configuration' }
$cfg=@($receipt.configs | Where-Object tag -eq $Tag)
if ($cfg.Count -ne 1) { throw 'Unknown native movie Tag' };$cfg=$cfg[0]
if ($cfg.game_overrides_enabled -or $cfg.force_lod_zero -or $cfg.cinematic_quality) { throw 'Movie quality overrides forbidden' }
$out=Join-Path $repo "unreal\ForestSpike\Saved\ForestSpike\b1a\movies\$Tag"
if ((Test-Path -LiteralPath (Join-Path $out 'request.json')) -or (Test-Path -LiteralPath (Join-Path $out 'engine.log'))) { throw 'Movie attempt already exists' }
$log=Join-Path $out 'engine.log';$start=[DateTimeOffset]::UtcNow
$args2=@("`"$(Join-Path $repo 'unreal\ForestSpike\ForestSpikeB1a.uproject')`"",$cfg.map,'-game','-windowed','-RenderOffscreen','-ResX=1920','-ResY=1080','-ForceRes','-nosound','-nosplash','-NoScreenMessages','-unattended','-benchmark','-fps=60',
 "-MoviePipelineConfig=$($cfg.config)","-LevelSequence=$($cfg.sequence)",'-MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelineInProcessExecutor',"-abslog=`"$log`"")
@{tag=$Tag;started_utc=$start.ToString('o');config=$cfg;args=$args2;scope='Native MRQ deferred frames; disabled cinematic/game/forced-LOD overrides; not a performance run'} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
$proc=Start-Process -FilePath 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' -ArgumentList $args2 -WindowStyle Hidden -Wait -PassThru
$count=@(Get-ChildItem -LiteralPath $cfg.output_directory -Filter '*.png' -Recurse -ErrorAction SilentlyContinue).Count
@{exit_code=$proc.ExitCode;png_count=$count;expected_count=$cfg.frames;completed_utc=[DateTimeOffset]::UtcNow.ToString('o');scope='Process observed; independent output gate required'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'process.json') -Encoding utf8
Write-Output "$Tag UE_exit=$($proc.ExitCode) PNG=$count"
