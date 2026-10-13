# ForestSpike B0: run one Unreal stage (editor Python) in a fresh UnrealEditor-Cmd process.
#   run_stage.ps1 -Script fs_env_check.py -Name env [-Env @{K="v"}] [-Game] [-Map /Game/..] [-Extra "-ResX=1920"]
# Writes logs under unreal/ForestSpike/Saved/ForestSpike/logs. Fails if UnrealEditor is already running
# (overlapping UE sessions double frame times - project capture-harness lesson).
param(
    [Parameter(Mandatory)][string]$Script,
    [Parameter(Mandatory)][string]$Name,
    [hashtable]$Env = @{},
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8",
    [string[]]$Extra = @(),
    [string]$Expect = "",       # report file (under Saved/ForestSpike/reports) this stage must (re)write with status PASS_*
    [string]$Map = "/Game/ForestSpike/L_ForestSpike_B0",
    [switch]$Game
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\ForestSpike\ForestSpike.uproject"
$Adapters = Join-Path $RepoRoot "adapters\unreal\forestspike"
$Out = Join-Path $RepoRoot "unreal\ForestSpike\Saved\ForestSpike"
$Logs = Join-Path $Out "logs"
New-Item -ItemType Directory -Force -Path $Out, $Logs, (Join-Path $Out "reports") | Out-Null
for ($w = 0; $w -lt 30 -and (Get-Process UnrealEditor* -ErrorAction SilentlyContinue); $w++) { Start-Sleep -Seconds 2 }   # let a crashing previous session finish
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw "an UnrealEditor process is already running" }
$exe = if ($Game) { Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor.exe" } else { Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor-Cmd.exe" }
$env:ACW_REPO_ROOT = $RepoRoot
$env:ACW_FS_OUT = $Out
foreach ($k in $Env.Keys) { Set-Item -Path "Env:$k" -Value $Env[$k] }
$log = Join-Path $Logs "$Name.log"
$args2 = @($Project) + $(if ($Game) { @($Map, "-game") } else { @() }) + @(
    "-ExecutePythonScript=$(Join-Path $Adapters $Script)", "-unattended", "-nopause", "-nosound", "-abslog=$log") + $Extra
$started = Get-Date
$sw = [Diagnostics.Stopwatch]::StartNew()
# UnrealEditor.exe is a GUI-subsystem binary: `&` would return at once, so wait explicitly (Cmd works with either).
$proc = Start-Process -FilePath $exe -ArgumentList $args2 -Wait -PassThru -NoNewWindow
$code = $proc.ExitCode
Write-Host ("[{0}] exit={1} {2:N0}s log={3}" -f $Name, $code, $sw.Elapsed.TotalSeconds, $log)
# UnrealEditor often dies with an access violation at shutdown AFTER the script finished; trust the receipt, not the exit code.
if ($Expect) {
    $rp = Join-Path $Out (Join-Path "reports" $Expect)
    if (-not (Test-Path $rp)) { Write-Host "[$Name] FAIL: receipt missing: $rp"; exit 2 }
    if ((Get-Item $rp).LastWriteTime -lt $started) { Write-Host "[$Name] FAIL: receipt is stale (script did not run?): $rp"; exit 2 }
    $st = (Get-Content $rp -Raw | ConvertFrom-Json).status
    Write-Host "[$Name] receipt status: $st"
    if ($st -notlike "PASS*") { exit 2 }
    exit 0
}
if ($code -ne 0) { exit $code }
