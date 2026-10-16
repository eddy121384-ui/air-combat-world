param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [int]$RunIndex = 1,
    [string]$PlanName = '10-collision-plan.json',
    [string]$PackageExecutable = '',
    [int]$TimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
if ($RunId -notmatch '^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$' -or $RunIndex -lt 1) { throw 'Invalid run identity.' }
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Run = Join-Path $Repo "unreal\Saved\XinyiHostGates\$RunId"
$Snapshot = Join-Path $Run '00-snapshot.json'
$Plan = Join-Path $Run $PlanName
$Manifest = Join-Path $Repo 'unreal\Saved\XinyiUnrealV2\ue_runtime_world.json'
foreach ($path in @($Snapshot,$Plan,$Manifest)) { if (-not (Test-Path -LiteralPath $path)) { throw "Missing prerequisite: $path" } }
$snap = Get-Content -LiteralPath $Snapshot -Raw | ConvertFrom-Json
$planData = Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
if ($snap.status -ne 'PASS_SNAPSHOT' -or $snap.run_id -ne $RunId -or
    $planData.status -ne 'PLAN_ONLY' -or @($planData.steps).Count -lt 60) { throw 'Invalid snapshot or plan.' }
if (-not $PackageExecutable) {
    $PackageExecutable = Join-Path $Run 'packaged-development\Windows\AirCombatWorld\Binaries\Win64\AirCombatWorld.exe'
}
$PackageExecutable = (Resolve-Path -LiteralPath $PackageExecutable).Path
$Raw = Join-Path $Run "30-collision-$RunIndex.raw.json"
$Log = Join-Path $Run "30-collision-$RunIndex.log"
$Receipt = Join-Path $Run "31-collision-$RunIndex-host.json"
foreach ($path in @($Raw,$Log,$Receipt)) { if (Test-Path -LiteralPath $path) { throw "Refusing to overwrite: $path" } }
if (Get-Process UnrealEditor,UnrealEditor-Cmd -ErrorAction SilentlyContinue) { throw 'Close existing Unreal Editor processes before packaged validation.' }
$arguments = @(
    '/Game/XinyiV2/L_XinyiV2_Contract_WP', '-NullRHI','-nosound','-unattended','-nopause',
    ('-XinyiCollisionPlan="{0}"' -f $Plan),
    ('-XinyiCollisionManifest="{0}"' -f $Manifest),
    ('-XinyiCollisionOutput="{0}"' -f $Raw),
    "-XinyiCollisionRunId=$RunId", ('-abslog="{0}"' -f $Log)
)
$started=(Get-Date).ToUniversalTime()
$launch=[guid]::NewGuid().ToString()
$process=Start-Process -FilePath $PackageExecutable -WorkingDirectory (Split-Path $PackageExecutable) `
    -ArgumentList $arguments -PassThru -WindowStyle Hidden
Write-Host "COLLISION_PACKAGED_START index=$RunIndex pid=$($process.Id) launch=$launch"
$timedOut=-not $process.WaitForExit($TimeoutSeconds*1000)
if ($timedOut) { try { $process.Kill() } catch {} ; try { $process.WaitForExit() } catch {} }
$finished=(Get-Date).ToUniversalTime()
$value=[ordered]@{
    schema='xinyi-collision-launch/v1'; run_id=$RunId; run_index=$RunIndex
    launch_id=$launch; process_id=[string]$process.Id
    started_utc=$started.ToString('o'); finished_utc=$finished.ToString('o')
    elapsed_seconds=($finished-$started).TotalSeconds
    exit_code=$process.ExitCode; timed_out=$timedOut
    executable_sha256=(Get-FileHash -LiteralPath $PackageExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
    plan_sha256=(Get-FileHash -LiteralPath $Plan -Algorithm SHA256).Hash.ToLowerInvariant()
    snapshot_sha256=(Get-FileHash -LiteralPath $Snapshot -Algorithm SHA256).Hash.ToLowerInvariant()
    manifest_sha256=(Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    raw_sha256=if (Test-Path -LiteralPath $Raw) { (Get-FileHash -LiteralPath $Raw -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
    log_sha256=if (Test-Path -LiteralPath $Log) { (Get-FileHash -LiteralPath $Log -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
    command_arguments=$arguments
}
$stream=[System.IO.File]::Open($Receipt,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
try {
    $writer=[System.IO.StreamWriter]::new($stream,[System.Text.UTF8Encoding]::new($false))
    $writer.WriteLine(($value|ConvertTo-Json -Depth 8));$writer.Flush()
} finally { if ($writer) { $writer.Dispose() } else { $stream.Dispose() } }
if ($timedOut -or $process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Raw)) { throw "Packaged collision process failed; preserve $Receipt and $Log." }
Write-Host "COLLISION_PACKAGED_COMPLETE index=$RunIndex raw=$Raw"
