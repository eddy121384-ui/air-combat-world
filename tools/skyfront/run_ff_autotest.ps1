# Skyfront Free Flight v1: desktop smoke flight. Runs the scripted -ffautotest flight (synthetic touches through the real touch handling,
# telemetry line per second, HUD screenshots at t = 3 7 13 19 23 27 31 s, quit at 34 s) in the editor -game, offscreen.
#   run_ff_autotest.ps1 -Tag es31 [-Mobile] [-ExtraArgs "-ffcrash -ini:Game:[...]:StartLocation=(X=..,Y=..,Z=..)"]        -Mobile = ES3.1 mobile renderer + the [Android DeviceProfile] cvars (mobile_cvars.ps1)
# Output: unreal/TreeLookdev/Saved/Skyfront/<Tag>/ (log + screenshots copied from Saved/Screenshots).
param([string]$Tag = 'sm5', [switch]$Mobile, [int]$ResX = 2560, [int]$ResY = 1600, [string]$ExtraArgs = '', [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$proj = Join-Path $RepoRoot 'unreal\TreeLookdev'
$out = Join-Path $proj "Saved\Skyfront\$Tag"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$shots = Join-Path $proj 'Saved\Screenshots\WindowsEditor'
if (Test-Path $shots) { Remove-Item (Join-Path $shots 'ffauto_*.png') -ErrorAction SilentlyContinue }
$a = @((Join-Path $proj 'TreeLookdev.uproject'), '/Game/NorthForest/Maps/L_NF_Yangmingshan', '-game', '-RenderOffscreen', "-ResX=$ResX", "-ResY=$ResY",
       '-ForceRes', '-nosound', '-unattended', '-ffautotest', "-abslog=$(Join-Path $out 'ff.log')", '-ExecCmds="r.VSync 0"')
if ($ExtraArgs) { $a += ($ExtraArgs -split ' ') }
if ($Mobile) { $a += '-featureleveles31'; $a += (& (Join-Path $RepoRoot 'tools\ntw\forest_world\mobile_cvars.ps1')) }
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $a -PassThru -Wait
Write-Host "exit=$($p.ExitCode) $([int]$sw.Elapsed.TotalSeconds) s"
if (Test-Path $shots) { Copy-Item (Join-Path $shots 'ffauto_*.png') $out -ErrorAction SilentlyContinue }
Select-String -Path (Join-Path $out 'ff.log') -Pattern 'FFAUTO' | ForEach-Object { $_.Line -replace '^.*FFAUTO ', '' }
