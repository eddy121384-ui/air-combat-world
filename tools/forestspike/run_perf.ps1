# Append-only B0 CSV-integrity check. A capture PASS does not clear LOD/path gates.
param(
    [Parameter(Mandatory)][ValidatePattern('^L_FSP_[A-Za-z0-9_]+$')][string]$Level,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Tag,
    [ValidateRange(1,100000)][int]$Frames = 480,
    [ValidateRange(0,99999)][int]$Cold = 120,
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [Parameter(Mandatory)][string]$Python,
    [switch]$Shot
)
$ErrorActionPreference = 'Stop'
if ($Cold -ge $Frames) { throw 'Cold frames must leave a nonempty measurement window' }
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Project = Join-Path $RepoRoot 'unreal\ForestSpike\ForestSpike.uproject'
$levelReceipt = Join-Path $RepoRoot 'unreal\ForestSpike\Saved\ForestSpike\reports\fs_perf_levels.report.json'
$catalog = Get-Content -LiteralPath $levelReceipt -Raw | ConvertFrom-Json
$entry = @($catalog.levels | Where-Object { $_.level -eq "/Game/ForestSpike/Perf/$Level" })
if ($catalog.status -ne 'PASS_FS_PERF_LEVELS' -or $entry.Count -ne 1) { throw 'Level missing from build receipt' }
if ($entry[0].sequence_frames -ne 0) {
    throw 'Moving measurement BLOCKED: saved B0 camera is stationary; requires a new isolated level, warm hold and validated per-frame trajectory before capture'
}
$exe = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$engineBin = Split-Path $exe
$csvDir = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'UnrealEngine\5.8\Saved\Profiling\CSV'))
$out = Join-Path $RepoRoot "unreal\ForestSpike\Saved\ForestSpike\perf_v2\${Tag}__$Level"
if (Test-Path -LiteralPath $out) { throw "Refusing to overwrite prior run: $out; choose a new Tag" }
New-Item -ItemType Directory -Path $out | Out-Null
$runId = [Guid]::NewGuid().ToString('N')
$log = Join-Path $out 'engine.log'
$receipt = Join-Path $out 'completion.json'
$started = [DateTimeOffset]::UtcNow
$exec = 'r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.RayTracing 0'
if ($Shot) { $exec += ',HighResShot 1920x1080' }
$mapPath = "/Game/ForestSpike/Perf/$Level"
$argList = @("`"$Project`"", $mapPath, '-game', '-windowed', '-ResX=1920', '-ResY=1080', '-nosound', '-nosplash',
    '-unattended', '-benchmark', '-fps=60', "-ExecCmds=`"$exec`"", "-csvCaptureFrames=$Frames", '-ExitAfterCsvProfiling',
    "-csvMetadata=`"tag=$Tag,level=$Level,run_id=$runId`"", "-abslog=`"$log`"")
@{schema='forestspike.perf_request/1';tag=$Tag;level=$Level;run_id=$runId;frames=$Frames;cold=$Cold;
  started_utc=$started.ToString('o');host_scope='Intel UHD 770 only';args=$argList} |
  ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
$proc = Start-Process -FilePath $exe -ArgumentList $argList -WindowStyle Hidden -Wait -PassThru
$dest = Join-Path $out 'MISSING.csv'
if (Test-Path -LiteralPath $log) {
    $text = Get-Content -LiteralPath $log -Raw
    $outputs = [regex]::Matches($text, 'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
    if ($outputs.Count -eq 1) {
        $source = [IO.Path]::GetFullPath((Join-Path $engineBin $outputs[0].Groups[1].Value.Trim()))
        if ((Split-Path $source) -ne $csvDir) { throw "Unexpected engine CSV directory: $source" }
        $dest = Join-Path $out (Split-Path $source -Leaf)
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $dest }
    }
}
& $Python (Join-Path $PSScriptRoot 'perf_integrity.py') --csv $dest --log $log --tag $Tag --level $Level `
    --run-id $runId --frames $Frames --cold $Cold --exit-code $proc.ExitCode `
    --started-epoch ($started.ToUnixTimeMilliseconds() / 1000.0) --receipt $receipt
$validationCode = $LASTEXITCODE
if ($validationCode -ne 0) { Write-Host "FAIL: retained output and errors at $out"; exit 2 }
$result = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
if ($result.status -ne 'PASS_FS_PERF_CAPTURE' -or $result.run_id -ne $runId) { throw 'Invalid completion receipt' }
Write-Host "PASS_FS_PERF_CAPTURE (CSV integrity only): $receipt; UE exit=$($proc.ExitCode)"
exit 0
