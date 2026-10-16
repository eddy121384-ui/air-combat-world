param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [Parameter(Mandatory=$true)][ValidateSet('Baseline','ComplexAsSimple')][string]$Mode,
    [string]$PlanName = '10-collision-plan.json',
    [string]$PackageExecutable = '',
    [int]$TimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
if ($RunId -notmatch '^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$') { throw 'Invalid RunId.' }
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Run = Join-Path $Repo "unreal\Saved\XinyiHostGates\$RunId"
$Snapshot = Join-Path $Run '00-snapshot.json'
$Plan = Join-Path $Run $PlanName
$Manifest = Join-Path $Repo 'unreal\Saved\XinyiUnrealV2\ue_runtime_world.json'
foreach ($path in @($Snapshot,$Plan,$Manifest)) { if (-not (Test-Path -LiteralPath $path)) { throw "Missing prerequisite: $path" } }
$snapshotData=Get-Content -LiteralPath $Snapshot -Raw | ConvertFrom-Json
$planData=Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
if ($snapshotData.status -ne 'PASS_SNAPSHOT' -or $snapshotData.run_id -ne $RunId -or
    $planData.status -ne 'PLAN_ONLY' -or @($planData.steps).Count -ne 101) { throw 'Invalid snapshot or exact corpus.' }
if (-not $PackageExecutable) {
    $PackageExecutable=Join-Path $Run 'packaged-candidate\Windows\AirCombatWorld\Binaries\Win64\AirCombatWorld.exe'
}
$PackageExecutable=(Resolve-Path -LiteralPath $PackageExecutable).Path
$slug=$Mode.ToLowerInvariant()
$Raw=Join-Path $Run "30-complex-$slug.raw.json"
$Log=Join-Path $Run "30-complex-$slug.log"
$Receipt=Join-Path $Run "31-complex-$slug-host.json"
foreach ($path in @($Raw,$Log,$Receipt)) { if (Test-Path -LiteralPath $path) { throw "Refusing to overwrite: $path" } }
if (Get-Process UnrealEditor,UnrealEditor-Cmd -ErrorAction SilentlyContinue) { throw 'Close Unreal Editor processes before packaged validation.' }
$arguments=@(
    '/Game/XinyiV2/L_XinyiV2_Contract_WP','-NullRHI','-nosound','-unattended','-nopause',
    ('-XinyiComplexCandidatePlan="{0}"' -f $Plan),
    ('-XinyiComplexCandidateManifest="{0}"' -f $Manifest),
    ('-XinyiComplexCandidateOutput="{0}"' -f $Raw),
    "-XinyiComplexCandidateRunId=$RunId","-XinyiComplexCandidateMode=$Mode",
    ('-abslog="{0}"' -f $Log)
)
$started=(Get-Date).ToUniversalTime();$launch=[guid]::NewGuid().ToString()
$process=Start-Process -FilePath $PackageExecutable -WorkingDirectory (Split-Path $PackageExecutable) `
    -ArgumentList $arguments -PassThru -WindowStyle Hidden
Write-Host "COMPLEX_CANDIDATE_START mode=$Mode pid=$($process.Id) launch=$launch"
$peakWorking=0L;$peakPrivate=0L;$samples=0;$deadline=(Get-Date).AddSeconds($TimeoutSeconds)
while (-not $process.HasExited -and (Get-Date) -lt $deadline) {
    try {
        $process.Refresh()
        $peakWorking=[Math]::Max($peakWorking,$process.WorkingSet64)
        $peakPrivate=[Math]::Max($peakPrivate,$process.PrivateMemorySize64)
        $samples++
    } catch {}
    Start-Sleep -Milliseconds 100
}
$timedOut=-not $process.HasExited
if ($timedOut) { try { $process.Kill() } catch {}; try { $process.WaitForExit() } catch {} }
else { $process.WaitForExit() }
$finished=(Get-Date).ToUniversalTime()
$packageRoot=(Resolve-Path -LiteralPath (Join-Path (Split-Path $PackageExecutable) '..\..\..')).Path
$packageBytes=(Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Measure-Object Length -Sum).Sum
$packagePayloadBytes=(Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Where-Object { $_.FullName -notmatch '\\Saved\\' } | Measure-Object Length -Sum).Sum
$pak=Join-Path $packageRoot 'AirCombatWorld\Content\Paks\AirCombatWorld-Windows.pak'
$value=[ordered]@{
    schema='xinyi-complex-as-simple-launch/v1';run_id=$RunId;mode=$Mode
    launch_id=$launch;process_id=[string]$process.Id
    started_utc=$started.ToString('o');finished_utc=$finished.ToString('o')
    elapsed_seconds=($finished-$started).TotalSeconds;exit_code=$process.ExitCode;timed_out=$timedOut
    executable_sha256=(Get-FileHash -LiteralPath $PackageExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
    plan_sha256=(Get-FileHash -LiteralPath $Plan -Algorithm SHA256).Hash.ToLowerInvariant()
    snapshot_sha256=(Get-FileHash -LiteralPath $Snapshot -Algorithm SHA256).Hash.ToLowerInvariant()
    manifest_sha256=(Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    raw_sha256=if(Test-Path -LiteralPath $Raw){(Get-FileHash -LiteralPath $Raw -Algorithm SHA256).Hash.ToLowerInvariant()}else{''}
    log_sha256=if(Test-Path -LiteralPath $Log){(Get-FileHash -LiteralPath $Log -Algorithm SHA256).Hash.ToLowerInvariant()}else{''}
    memory_sample_count=$samples;peak_working_set_bytes=$peakWorking;peak_private_bytes=$peakPrivate
    package_total_bytes=$packageBytes;package_payload_bytes_excluding_runtime_saved=$packagePayloadBytes
    pak_bytes=if(Test-Path -LiteralPath $pak){(Get-Item -LiteralPath $pak).Length}else{0}
    command_arguments=$arguments
}
$stream=[System.IO.File]::Open($Receipt,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
try {
    $writer=[System.IO.StreamWriter]::new($stream,[System.Text.UTF8Encoding]::new($false))
    $writer.WriteLine(($value|ConvertTo-Json -Depth 8));$writer.Flush()
} finally { if($writer){$writer.Dispose()}else{$stream.Dispose()} }
if ($timedOut -or $process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Raw)) { throw "Packaged $Mode process failed; preserve $Receipt and $Log." }
Write-Host "COMPLEX_CANDIDATE_COMPLETE mode=$Mode raw=$Raw"
