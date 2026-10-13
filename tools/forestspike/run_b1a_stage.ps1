param(
    [Parameter(Mandatory)][string]$Script,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
    [Parameter(Mandatory)][hashtable]$Env,
    [ValidateSet("ForestSpike.uproject","ForestSpikeB1a.uproject")][string]$ProjectFile="ForestSpike.uproject"
)
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'Unreal is already running' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$out = Join-Path $repo "unreal\ForestSpike\Saved\ForestSpike\b1a\$Tag"
if (Test-Path -LiteralPath $out) { throw 'Choose a new stage Tag; evidence already exists' }
New-Item -ItemType Directory -Path $out | Out-Null
$env:ACW_REPO_ROOT = $repo
$env:ACW_FS_B01_REPORT = Join-Path $out 'receipt.json'
$env:ACW_FS_B1A_REPORT = $env:ACW_FS_B01_REPORT
foreach ($key in $Env.Keys) { Set-Item -Path "Env:$key" -Value $Env[$key] }
$scriptPath = Join-Path $repo "adapters\unreal\forestspike\$Script"
$log = Join-Path $out 'engine.log'
$start = [DateTimeOffset]::UtcNow
$args2 = @("`"$(Join-Path $repo "unreal\ForestSpike\$ProjectFile")`"", "-ExecutePythonScript=`"$scriptPath`"", '-unattended', '-nopause', '-nosound', "-abslog=`"$log`"")
@{script=$Script;tag=$Tag;started_utc=$start.ToString('o');env=$Env;args=$args2} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
$proc = Start-Process -FilePath 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' -ArgumentList $args2 -WindowStyle Hidden -Wait -PassThru
$rp = $env:ACW_FS_B01_REPORT
$valid = $false
$status = 'MISSING_RECEIPT'
if ((Test-Path -LiteralPath $rp) -and (Get-Item -LiteralPath $rp).LastWriteTimeUtc -ge $start.UtcDateTime) {
    $status = (Get-Content -LiteralPath $rp -Raw | ConvertFrom-Json).status
    $valid = $status -like 'PASS_FS_B01*' -or $status -like 'PASS_FS_B1A*'
}
@{status=$status;fresh_receipt=$valid;exit_code=$proc.ExitCode;completion_scope='editor stage receipt, not motion/performance/visual acceptance'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'process.json') -Encoding utf8
Write-Output "$Tag $status UE_exit=$($proc.ExitCode)"
if (-not $valid) { exit 2 }
exit 0
