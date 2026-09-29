param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [string]$PackageExecutable = '',
    [int]$TimeoutSeconds = 1200
)
$ErrorActionPreference = 'Stop'
if ($RunId -notmatch '^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$') { throw 'Invalid RunId.' }
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Run = Join-Path $Repo "unreal\Saved\XinyiHostGates\$RunId"
$Snapshot = Join-Path $Run '00-snapshot.json'
$Route = Join-Path $Run '10-streaming-route.json'
$Manifest = Join-Path $Repo 'unreal\Saved\XinyiUnrealV2\ue_runtime_world.json'
foreach ($path in @($Snapshot,$Route,$Manifest)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing prerequisite: $path" }
}
$snapshotData = Get-Content -LiteralPath $Snapshot -Raw | ConvertFrom-Json
$routeData = Get-Content -LiteralPath $Route -Raw | ConvertFrom-Json
if ($snapshotData.status -ne 'PASS_SNAPSHOT' -or $snapshotData.run_id -ne $RunId -or
    $routeData.status -ne 'PLAN_ONLY' -or @($routeData.streaming.route).Count -ne 27) {
    throw 'Snapshot or route prerequisite failed.'
}
if (-not $PackageExecutable) {
    $archive = Join-Path $Run 'packaged-development'
    $PackageExecutable = Join-Path $archive 'Windows\AirCombatWorld\Binaries\Win64\AirCombatWorld.exe'
    if (-not (Test-Path -LiteralPath $PackageExecutable)) {
        throw "Development game executable absent: $PackageExecutable"
    }
}
$PackageExecutable = (Resolve-Path -LiteralPath $PackageExecutable).Path
if (Get-Process UnrealEditor,UnrealEditor-Cmd -ErrorAction SilentlyContinue) {
    throw 'Close existing Unreal Editor processes before this host run.'
}

function Write-NewJson([string]$path, $value) {
    $json = $value | ConvertTo-Json -Depth 15
    $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $writer.WriteLine($json)
        $writer.Flush()
    } finally {
        if ($writer) { $writer.Dispose() } else { $stream.Dispose() }
    }
}

for ($index=1; $index -le 2; $index++) {
    $raw = Join-Path $Run "20-packaged-$index.raw.json"
    $log = Join-Path $Run "20-packaged-$index.log"
    $hostReceipt = Join-Path $Run "21-packaged-$index-host.json"
    if ((Test-Path -LiteralPath $raw) -and (Test-Path -LiteralPath $log) -and
        (Test-Path -LiteralPath $hostReceipt)) {
        Write-Host "Existing complete run $index preserved; final validator will re-check it."
        continue
    }
    if ((Test-Path -LiteralPath $raw) -or (Test-Path -LiteralPath $log) -or
        (Test-Path -LiteralPath $hostReceipt)) {
        throw "Partial run $index exists; preserve it and use a fresh snapshot RunId."
    }
    $arguments = @(
        '/Game/XinyiV2/L_XinyiV2_Contract_WP', '-NullRHI', '-nosound', '-unattended', '-nopause',
        ('-XinyiHostRoute="{0}"' -f $Route),
        ('-XinyiHostManifest="{0}"' -f $Manifest),
        ('-XinyiHostOutput="{0}"' -f $raw),
        "-XinyiHostRunId=$RunId", ('-abslog="{0}"' -f $log)
    )
    $launchId = [guid]::NewGuid().ToString()
    $started = (Get-Date).ToUniversalTime()
    $process = Start-Process -FilePath $PackageExecutable -WorkingDirectory (Split-Path $PackageExecutable) `
        -ArgumentList $arguments -PassThru -WindowStyle Hidden
    Write-Host "Fresh packaged process $index pid=$($process.Id) launch_id=$launchId"
    $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) {
        try { $process.Kill() } catch {}
        try { $process.WaitForExit() } catch {}
    }
    $finished = (Get-Date).ToUniversalTime()
    $value = [ordered]@{
        schema = 'xinyi-packaged-launch/v1'; run_id = $RunId; run_index = $index
        launch_id = $launchId; process_id = [string]$process.Id
        executable = $PackageExecutable
        executable_sha256 = (Get-FileHash -LiteralPath $PackageExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
        started_utc = $started.ToString('o'); finished_utc = $finished.ToString('o')
        exit_code = $process.ExitCode; timed_out = $timedOut
        route_sha256 = (Get-FileHash -LiteralPath $Route -Algorithm SHA256).Hash.ToLowerInvariant()
        snapshot_sha256 = (Get-FileHash -LiteralPath $Snapshot -Algorithm SHA256).Hash.ToLowerInvariant()
        manifest_sha256 = (Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash.ToLowerInvariant()
        raw_sha256 = if (Test-Path -LiteralPath $raw) { (Get-FileHash -LiteralPath $raw -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
        log_sha256 = if (Test-Path -LiteralPath $log) { (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash.ToLowerInvariant() } else { '' }
        command_arguments = $arguments
    }
    Write-NewJson $hostReceipt $value
    if ($timedOut -or $process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $raw)) {
        throw "Packaged process $index failed; preserve $hostReceipt and $log."
    }
}
$env:Path = 'C:\Users\EDDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\python;' + $env:Path
& python (Join-Path $PSScriptRoot 'validate_packaged_streaming.py') --run-root $Run --out (Join-Path $Run '30-packaged-streaming-gate.json')
if ($LASTEXITCODE -ne 0) { throw "Packaged route failed validation; see $Run\30-packaged-streaming-gate.json" }
Write-Host "XINYI_PACKAGED_STREAMING_PASS run_id=$RunId"
