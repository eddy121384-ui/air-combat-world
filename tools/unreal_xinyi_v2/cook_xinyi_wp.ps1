param(
    [Parameter(Mandatory=$true)][string]$RunId,
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string]$TargetPlatform = "Windows"
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunRoot = Join-Path $RepoRoot "unreal\Saved\XinyiHostGates\$RunId"
$Snapshot = Join-Path $RunRoot "00-snapshot.json"
if (-not (Test-Path $Snapshot)) { throw "Snapshot prerequisite missing: $Snapshot" }
$Out = Join-Path $RunRoot "cook"
if (Test-Path $Out) { throw "Cook output exists; refusing to overwrite: $Out" }
New-Item -ItemType Directory -Path $Out | Out-Null
$Project = Join-Path $RepoRoot "unreal\AirCombatWorld.uproject"
$Cmd = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$Log = Join-Path $Out "cook.log"
$Receipt = Join-Path $RunRoot "20-cook-commandlet.json"
if (-not (Test-Path $Cmd)) { throw "UnrealEditor-Cmd not found: $Cmd" }
$args = @($Project, "/Game/XinyiV2/L_XinyiV2_Contract_WP", "-run=Cook", "-TargetPlatform=$TargetPlatform", "-unattended", "-nopause", "-abslog=$Log")
$started = (Get-Date).ToUniversalTime()
& $Cmd @args
$exitCode = $LASTEXITCODE
$finished = (Get-Date).ToUniversalTime()
$errors = @()
if (Test-Path $Log) {
    $errors = @(Select-String -Path $Log -Pattern "Missing package|Can't find file|Failed to load|LogCook: Error|Fatal error" | ForEach-Object { $_.Line })
}
$status = if ($exitCode -eq 0 -and $errors.Count -eq 0) { "PASS_COOK_COMMANDLET" } else { "FAIL_COOK_COMMANDLET" }
$value = [ordered]@{
    schema = "xinyi-host-gate/v1"; receipt_type = "cook_commandlet"; status = $status
    runtime_validation = $false; created_utc = $finished.ToString("o"); run_id = $RunId
    explicit_map = "/Game/XinyiV2/L_XinyiV2_Contract_WP"; target_platform = $TargetPlatform
    started_utc = $started.ToString("o"); elapsed_seconds = ($finished - $started).TotalSeconds
    exit_code = $exitCode; log = $Log; detected_errors = $errors
    packaged_runtime_tested = $false
}
$json = $value | ConvertTo-Json -Depth 8
$stream = [System.IO.File]::Open($Receipt, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
try {
    $writer = New-Object System.IO.StreamWriter($stream, [System.Text.UTF8Encoding]::new($false))
    $writer.WriteLine($json); $writer.Flush()
} finally { if ($writer) { $writer.Dispose() } else { $stream.Dispose() } }
if ($status -ne "PASS_COOK_COMMANDLET") { throw "Xinyi _WP cook failed closed. See $Receipt" }
Write-Host "XINYI_WP_COOK_COMMANDLET_OK runtime_not_tested=true receipt=$Receipt"
