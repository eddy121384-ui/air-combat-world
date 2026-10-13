param(
    [Parameter(Mandatory)][ValidateSet('A','B')][string]$Arm,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
    [Parameter(Mandatory)][string]$ReopenReceipt,
    [Parameter(Mandatory)][string]$Python,
    [string]$Registration = (Join-Path $PSScriptRoot 'b01_registered_d.json')
)
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'Unreal already running' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$specPath = (Resolve-Path -LiteralPath $Registration).Path
$spec = Get-Content -LiteralPath $specPath -Raw | ConvertFrom-Json
$reopen = Get-Content -LiteralPath $ReopenReceipt -Raw | ConvertFrom-Json
if ($reopen.status -ne 'PASS_FS_B01_REOPEN') { throw 'Reopen gate has not passed' }
$map = @($reopen.maps | Where-Object arm -eq $Arm)
if ($map.Count -ne 1 -or -not $map[0].pass -or $map[0].world_path -notlike "$($spec.asset_root)/*") { throw 'Invalid new map gate' }
$map = $map[0]
$out = Join-Path $repo "unreal\ForestSpike\Saved\ForestSpike\b01\$Tag"
if (Test-Path -LiteralPath $out) { throw 'Existing smoke evidence; choose new Tag' }
New-Item -ItemType Directory -Path $out | Out-Null
$runId = [Guid]::NewGuid().ToString('N')
$log = Join-Path $out 'engine.log'
$frames = $spec.capture_frames
$started = [DateTimeOffset]::UtcNow
$exec = 'r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.RayTracing 0,foliage.ForceLOD -1,r.ForceLOD -1,foliage.LODDistanceScale 1,foliage.RandomLODRange 0,r.ViewDistanceScale 1'
$args2 = @("`"$(Join-Path $repo 'unreal\ForestSpike\ForestSpike.uproject')`"",$map.world_path,'-game','-windowed','-ResX=1920','-ResY=1080','-nosound','-nosplash','-unattended','-benchmark','-fps=60',"-ExecCmds=`"$exec`"","-csvCaptureFrames=$frames",'-ExitAfterCsvProfiling',"-csvMetadata=`"tag=$Tag,level=$($map.name),run_id=$runId`"","-abslog=`"$log`"")
@{tag=$Tag;arm=$Arm;level=$map.name;world_path=$map.world_path;run_id=$runId;frames=$frames;warm_world_frames=120;started_utc=$started.ToString('o');args=$args2;registration_sha256=(Get-FileHash -LiteralPath $specPath -Algorithm SHA256).Hash;reopen_receipt_sha256=(Get-FileHash -LiteralPath $ReopenReceipt -Algorithm SHA256).Hash;host_scope='Intel UHD 770 only'} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
$exe = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$proc = Start-Process -FilePath $exe -ArgumentList $args2 -WindowStyle Hidden -Wait -PassThru
$csv = Join-Path $out 'MISSING.csv'
if (Test-Path -LiteralPath $log) {
    $outputs = [regex]::Matches((Get-Content -LiteralPath $log -Raw),'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
    if ($outputs.Count -eq 1) {
        $source = [IO.Path]::GetFullPath((Join-Path (Split-Path $exe) $outputs[0].Groups[1].Value.Trim()))
        $expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'UnrealEngine\5.8\Saved\Profiling\CSV'))
        if ((Split-Path $source) -ne $expected) { throw 'Unexpected CSV output folder' }
        $csv = Join-Path $out (Split-Path $source -Leaf)
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $csv }
    }
}
$capture = Join-Path $out 'completion.json'
& $Python (Join-Path $PSScriptRoot 'perf_integrity.py') --csv $csv --log $log --tag $Tag --level $map.name --world-path $map.world_path --run-id $runId --frames $frames --cold 120 --exit-code $proc.ExitCode --started-epoch ($started.ToUnixTimeMilliseconds()/1000.0) --receipt $capture
$capturePass = $LASTEXITCODE -eq 0
$motionPass = $false
if ($capturePass) {
    & $Python (Join-Path $PSScriptRoot 'motion_integrity.py') --csv $csv --spec $specPath --trace (Join-Path $out 'camera_trace.csv') --receipt (Join-Path $out 'motion.json')
    $motionPass = $LASTEXITCODE -eq 0
}
$status = if ($capturePass -and $motionPass) { 'PASS_FS_B01_SMOKE' } else { 'FAIL_FS_B01_SMOKE' }
@{status=$status;arm=$Arm;capture_pass=$capturePass;motion_pass=$motionPass;exit_code=$proc.ExitCode;host_scope='Intel UHD 770 only';scope='one repair smoke; GPU diagnostic only, no A/B ranking'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'smoke.json') -Encoding utf8
Write-Output "$Tag $status"
if ($status -ne 'PASS_FS_B01_SMOKE') { exit 2 }
exit 0
