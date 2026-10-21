# Skyfront Graphics Settings v1: same-view preset comparison in the Windows MOBILE-RENDERER preview (ES3.1 + the [Android DeviceProfile]
# cvars), editor -game offscreen. -ffgfxtest holds the plane at 2 fixed poses and switches Power Saver / Balanced / High / Ultra / Balanced
# LIVE; after streaming + shader compiles finish it samples 5 s of frame / GPU time and takes a HUD screenshot.
#   run_gfx_compare.ps1 -Tag es31_a [-ResX 2560 -ResY 1600] [-Sm5]
# Output: unreal/TreeLookdev/Saved/Skyfront/<Tag>/ (gfx.log, SKYGFXTEST lines, skygfx_*.png). PC iGPU numbers, NOT Tab S11 numbers.
param([string]$Tag = 'gfx', [int]$ResX = 2560, [int]$ResY = 1600, [switch]$Sm5, [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$proj = Join-Path $RepoRoot 'unreal\TreeLookdev'
$out = Join-Path $proj "Saved\Skyfront\$Tag"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$shots = Join-Path $proj 'Saved\Screenshots\WindowsEditor'
if (Test-Path $shots) { Remove-Item (Join-Path $shots 'skygfx_*.png') -ErrorAction SilentlyContinue }
$a = @((Join-Path $proj 'TreeLookdev.uproject'), '/Game/NorthForest/Maps/L_NF_Yangmingshan', '-game', '-RenderOffscreen', "-ResX=$ResX", "-ResY=$ResY",
       '-ForceRes', '-nosound', '-unattended', '-ffgfxtest', "-abslog=$(Join-Path $out 'gfx.log')", '-ExecCmds="r.VSync 0"')
if (-not $Sm5) { $a += '-featureleveles31'; $a += (& (Join-Path $RepoRoot 'tools\ntw\forest_world\mobile_cvars.ps1')) }
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $a -PassThru -Wait
Write-Host "exit=$($p.ExitCode) $([int]$sw.Elapsed.TotalSeconds) s"
if (Test-Path $shots) { Copy-Item (Join-Path $shots 'skygfx_*.png') $out -ErrorAction SilentlyContinue }
Select-String -Path (Join-Path $out 'gfx.log') -Pattern 'SKYGFX' | ForEach-Object { $_.Line -replace '^.*(SKYGFX)', '$1' }
