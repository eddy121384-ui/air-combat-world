param([Parameter(Mandatory)][ValidateSet('import','capture')][string]$Stage,
      [ValidateSet('before','r1','r2')][string]$Variant='r1',
      [ValidatePattern('^[a-zA-Z0-9_-]*$')][string]$CaptureRun='')
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
if($repo -ne 'C:\Users\EDDY\Desktop\M1A2\xinyi-material-ue58-round1'){throw 'Wrong worktree'}
if(Get-Process UnrealEditor,UnrealEditor-Cmd,ShaderCompileWorker -ErrorAction SilentlyContinue){throw 'Unreal is busy'}
$branch=git -c safe.directory=C:/Users/EDDY/Desktop/M1A2/xinyi-material-ue58-round1 -C $repo branch --show-current
if($branch -ne 'feat/xinyi-walkup-exemplar-269873'){throw 'Exemplar branch required'}
if($Stage -eq 'import' -and $Variant -eq 'before'){throw 'Before has no import'}
$env:ACW_REPO_ROOT=$repo
$env:ACW_EXEMPLAR_REVISION=$Variant
$env:ACW_EXEMPLAR_VARIANT=$Variant
$env:ACW_EXEMPLAR_CAPTURE_RUN=$CaptureRun
$out=Join-Path $repo 'unreal\Saved\XinyiExemplar\Walkup269873'
if($CaptureRun){
    if($Stage -ne 'capture'){throw 'CaptureRun is for fresh capture receipts, not reimport'}
    $out=Join-Path $out ('runs\'+$CaptureRun)
}
New-Item -ItemType Directory -Path $out -Force | Out-Null
$script=Join-Path $repo ('adapters\unreal\lookdev\exemplars\walkup_'+$(if($Stage -eq 'import'){'build'}else{'capture'})+'.py')
$log=Join-Path $out ($Stage+'-'+$Variant+'-'+(Get-Date -Format 'yyyyMMddTHHmmss')+'.log')
$receipt=if($Stage -eq 'import'){Join-Path $out ('import_'+$Variant+'.json')}else{Join-Path $out ('captures\'+$Variant+'\look_capture.report.json')}
if(Test-Path -LiteralPath $receipt){throw 'Existing receipt: preserve this attempt; use a new revision for art changes'}
& 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' (Join-Path $repo 'unreal\AirCombatWorld.uproject') "-ExecutePythonScript=$script" -unattended -nopause -nosound -nop4 "-abslog=$log"
$code=$LASTEXITCODE
$r=if(Test-Path -LiteralPath $receipt){Get-Content -LiteralPath $receipt -Raw|ConvertFrom-Json}else{$null}
$processReceipt=[pscustomobject]@{Stage=$Stage;Variant=$Variant;ExitCode=$code;Log=$log;Receipt=$receipt;Status=$r.status}
$processReceipt|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $out ('process-'+$Stage+'-'+$Variant+'.json')) -Encoding utf8
$processReceipt|ConvertTo-Json
if($code -ne 0 -or -not $r -or $r.status -notmatch '^PASS_'){throw 'Exemplar stage failed; preserve log'}
