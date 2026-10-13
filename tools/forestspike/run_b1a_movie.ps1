param([Parameter(Mandatory)][ValidateSet('A0','A1','B0','B1')][string]$Group,
 [Parameter(Mandatory)][ValidateSet('V3','V5')][string]$PathId,
 [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
 [Parameter(Mandatory)][string]$ReopenReceipt,[int]$EndFrame=-1)
$ErrorActionPreference='Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'Unreal already running' }
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$spec=Get-Content (Join-Path $PSScriptRoot 'b1a\registered.json') -Raw | ConvertFrom-Json
$reopen=Get-Content -LiteralPath $ReopenReceipt -Raw | ConvertFrom-Json
if ($reopen.status -ne 'PASS_FS_B1A_REOPEN') { throw 'Reopen gate failed' }
$cfg=@($reopen.maps | Where-Object {$_.group -eq $Group -and $_.view -eq $PathId})[0]
if (-not $cfg.pass) { throw 'Invalid movie fixture' }
if ($EndFrame -lt 0) { $EndFrame=120+$spec.paths.($PathId).flight_intervals+1 }
$out=Join-Path $repo "unreal\ForestSpike\Saved\ForestSpike\b1a\movies\$Tag"
if (Test-Path -LiteralPath $out) { throw 'Movie evidence already exists' }
New-Item -ItemType Directory -Path $out | Out-Null
$framesOut=Join-Path $out 'frames';$log=Join-Path $out 'engine.log';$start=[DateTimeOffset]::UtcNow
$exec='r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.RayTracing 0,foliage.ForceLOD -1,r.ForceLOD -1,foliage.LODDistanceScale 1,foliage.RandomLODRange 0,r.ViewDistanceScale 1'
$args2=@("`"$(Join-Path $repo 'unreal\ForestSpike\ForestSpike.uproject')`"",$cfg.world_path,'-game','-windowed','-RenderOffscreen','-ResX=1920','-ResY=1080','-ForceRes','-nosound','-nosplash','-NoScreenMessages','-unattended','-benchmark','-fps=60',
 '-MovieSceneCaptureType=/Script/MovieSceneTools.AutomatedLevelSequenceCapture',"-LevelSequence=$($cfg.sequence_path)","-MovieFolder=`"$framesOut`"",'-MovieFormat=PNG','-MovieName=frame.{frame}','-MovieFrameRate=60','-MovieStartFrame=0',"-MovieEndFrame=$EndFrame",'-MovieWarmUpFrames=0','-MovieDelayBeforeWarmUp=0','-MovieOverwriteExisting=false','-MovieRelativeFrames=false',"-ExecCmds=`"$exec`"",'-LogCmds="LogMovieSceneCapture Verbose"',"-abslog=`"$log`"")
@{tag=$Tag;group=$Group;path_id=$PathId;world_path=$cfg.world_path;sequence_path=$cfg.sequence_path;started_utc=$start.ToString('o');end_frame_exclusive=$EndFrame;fps=60;args=$args2;scope='Native Unreal viewport sequence frames; separate from timing CSV run'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
$proc=Start-Process -FilePath 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' -ArgumentList $args2 -WindowStyle Hidden -Wait -PassThru
$count=@(Get-ChildItem -LiteralPath $framesOut -Filter '*.png' -ErrorAction SilentlyContinue).Count
@{exit_code=$proc.ExitCode;png_count=$count;expected_count=$EndFrame;completed_utc=[DateTimeOffset]::UtcNow.ToString('o');scope='Process observed; independent frame continuity/hash/resolution/visual gate required'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'process.json') -Encoding utf8
Write-Output "$Tag UE_exit=$($proc.ExitCode) PNG=$count"
