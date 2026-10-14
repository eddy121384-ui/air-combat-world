# TreeLookdev: run one Unreal stage (editor Python) in a fresh UnrealEditor-Cmd process (copied from ForestSpike run_stage.ps1).
#   run_tl.ps1 -Script tl_build.py -Name build -Expect tl_build.report.json [-Env @{K="v"}]
# Fails if UnrealEditor is already running (overlapping UE sessions double frame times - capture-harness lesson).
param(
    [Parameter(Mandatory)][string]$Script,
    [Parameter(Mandatory)][string]$Name,
    [hashtable]$Env = @{},
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string[]]$Extra = @(),
    [string]$Expect = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\TreeLookdev\TreeLookdev.uproject"
$Adapters = Join-Path $RepoRoot "adapters\unreal\treelookdev"
$Out = Join-Path $RepoRoot "unreal\TreeLookdev\Saved\TreeLookdev"
$Logs = Join-Path $Out "logs"
New-Item -ItemType Directory -Force -Path $Out, $Logs, (Join-Path $Out "reports") | Out-Null
for ($w = 0; $w -lt 30 -and (Get-Process UnrealEditor* -ErrorAction SilentlyContinue); $w++) { Start-Sleep -Seconds 2 }
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw "an UnrealEditor process is already running" }
$exe = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$env:ACW_REPO_ROOT = $RepoRoot
$env:ACW_TL_OUT = $Out
$env:ACW_TL_GAME = Join-Path $RepoRoot "out\treegen\machilus_game"
foreach ($k in $Env.Keys) { Set-Item -Path "Env:$k" -Value $Env[$k] }
$log = Join-Path $Logs "$Name.log"
$args2 = @($Project, "-ExecutePythonScript=$(Join-Path $Adapters $Script)", "-unattended", "-nopause", "-nosound", "-abslog=$log") + $Extra
$started = Get-Date
$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath $exe -ArgumentList $args2 -Wait -PassThru -NoNewWindow
Write-Host ("[{0}] exit={1} {2:N0}s log={3}" -f $Name, $proc.ExitCode, $sw.Elapsed.TotalSeconds, $log)
if ($Expect) {
    $rp = Join-Path $Out (Join-Path "reports" $Expect)
    if (-not (Test-Path $rp)) { Write-Host "[$Name] FAIL: receipt missing: $rp"; exit 2 }
    if ((Get-Item $rp).LastWriteTime -lt $started) { Write-Host "[$Name] FAIL: receipt is stale: $rp"; exit 2 }
    $st = (Get-Content $rp -Raw | ConvertFrom-Json).status
    Write-Host "[$Name] receipt status: $st"
    if ($st -notlike "PASS*") { exit 2 }
}
exit 0
