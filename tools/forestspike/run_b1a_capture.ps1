param([Parameter(Mandatory)][ValidateSet('A0','A1','B0','B1')][string]$Group,
 [Parameter(Mandatory)][string]$View,[Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
 [Parameter(Mandatory)][string]$ReopenReceipt,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'Unreal already running' }
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$specPath=Join-Path $PSScriptRoot 'b1a\registered.json'
$spec=Get-Content -LiteralPath $specPath -Raw | ConvertFrom-Json
$reopen=Get-Content -LiteralPath $ReopenReceipt -Raw | ConvertFrom-Json
if ($reopen.status -ne 'PASS_FS_B1A_REOPEN') { throw 'New fixture reopen gate failed' }
$cfg=@($reopen.maps | Where-Object {$_.group -eq $Group -and $_.view -eq $View})
if ($cfg.Count -ne 1 -or -not $cfg[0].pass) { throw 'Unknown verified fixture' };$cfg=$cfg[0]
$out=Join-Path $repo "unreal\ForestSpike\Saved\ForestSpike\b1a\perf\$Tag"
if (Test-Path -LiteralPath $out) { throw 'Output already exists; new Tag required' }
New-Item -ItemType Directory -Path $out | Out-Null
$runId=[Guid]::NewGuid().ToString('N');$log=Join-Path $out 'engine.log';$started=[DateTimeOffset]::UtcNow
$frames=$spec.static_capture.frames;$cold=$spec.static_capture.cold
if ($cfg.path_id) { $frames=$spec.paths.($cfg.path_id).capture_frames;$cold=120 }
$exec='r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.RayTracing 0,foliage.ForceLOD -1,r.ForceLOD -1,foliage.LODDistanceScale 1,foliage.RandomLODRange 0,r.ViewDistanceScale 1'
$args2=@("`"$(Join-Path $repo 'unreal\ForestSpike\ForestSpike.uproject')`"",$cfg.world_path,'-game','-windowed','-ResX=1920','-ResY=1080','-nosound','-nosplash','-unattended','-benchmark','-fps=60',"-ExecCmds=`"$exec`"","-csvCaptureFrames=$frames",'-ExitAfterCsvProfiling',"-csvMetadata=`"tag=$Tag,level=$($cfg.name),run_id=$runId`"","-abslog=`"$log`"")
@{tag=$Tag;group=$Group;view=$View;level=$cfg.name;world_path=$cfg.world_path;run_id=$runId;frames=$frames;cold=$cold;started_utc=$started.ToString('o');args=$args2;registration_sha256=(Get-FileHash -LiteralPath $specPath -Algorithm SHA256).Hash;reopen_receipt_sha256=(Get-FileHash -LiteralPath $ReopenReceipt -Algorithm SHA256).Hash;host_scope='Intel UHD 770 only'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
$exe='C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$proc=Start-Process -FilePath $exe -ArgumentList $args2 -WindowStyle Hidden -Wait -PassThru
$csv=Join-Path $out 'MISSING.csv'
if (Test-Path -LiteralPath $log) {
 $outputs=[regex]::Matches((Get-Content -LiteralPath $log -Raw),'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
 if ($outputs.Count -eq 1) {
  $source=[IO.Path]::GetFullPath((Join-Path (Split-Path $exe) $outputs[0].Groups[1].Value.Trim()))
  $expected=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'UnrealEngine\5.8\Saved\Profiling\CSV'))
  if ((Split-Path $source) -ne $expected) { throw 'Unexpected CSV output folder' }
  $csv=Join-Path $out (Split-Path $source -Leaf)
  if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $csv }
 }
}
& $Python (Join-Path $PSScriptRoot 'perf_integrity.py') --csv $csv --log $log --tag $Tag --level $cfg.name --world-path $cfg.world_path --run-id $runId --frames $frames --cold $cold --exit-code $proc.ExitCode --started-epoch ($started.ToUnixTimeMilliseconds()/1000.) --receipt (Join-Path $out 'completion.json')
$capturePass=$LASTEXITCODE -eq 0;$motionPass=$false
if ($capturePass) {
 & $Python (Join-Path $PSScriptRoot 'b1a\integrity.py') --csv $csv --spec $specPath --reopen $ReopenReceipt --group $Group --view $View --out (Join-Path $out 'motion.json') --trace (Join-Path $out 'camera_trace.csv')
 $motionPass=$LASTEXITCODE -eq 0
}
$passed=$capturePass -and $motionPass -and $proc.ExitCode -eq 0
$status=if ($passed) {'PASS_FS_B1A_RUN'} else {'FAIL_FS_B1A_RUN'}
@{status=$status;group=$Group;view=$View;capture_pass=$capturePass;motion_pass=$motionPass;exit_code=$proc.ExitCode;host_scope='Intel UHD 770 only';moving_gpu_ranking_allowed=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'run.json') -Encoding utf8
Write-Output "$Tag $status"
if (-not $passed) { exit 2 }
