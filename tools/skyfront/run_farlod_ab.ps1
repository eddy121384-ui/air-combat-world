# Far-LOD research A/B in the Windows MOBILE-RENDERER preview (ES3.1 + the [Android DeviceProfile] cvars), editor -game offscreen.
#   run_farlod_ab.ps1 -Tag ab1 [-Views 0,1,2,3] [-ResX 2560 -ResY 1600] [-Sm5]          same-view configs, both orders (-fffarlodtest)
#   run_farlod_ab.ps1 -Tag fly1 -Fly [-FlyCfgs 0,1] [-FlyFrames 360] -ResX 1280 -ResY 800   frame-indexed 300 m/s flight, a PNG per frame
# Output: unreal/TreeLookdev/Saved/Skyfront/<Tag>/ (farlod.log, SKYFL / SKYFLFLY lines, fl_*.png / fly_*.png). PC iGPU numbers only.
param([string]$Tag = 'farlod', [string]$Views = '0,1,2,3', [int]$ResX = 2560, [int]$ResY = 1600, [switch]$Sm5, [switch]$Fly,
      [switch]$Profile, [string]$FlyCfgs = '0,1', [int]$FlyFrames = 360, [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$proj = Join-Path $RepoRoot 'unreal\TreeLookdev'
$out = Join-Path $proj "Saved\Skyfront\$Tag"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$shots = Join-Path $proj 'Saved\Screenshots\WindowsEditor'
if (Test-Path $shots) { Remove-Item (Join-Path $shots 'fl*_*.png') -ErrorAction SilentlyContinue }
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'an UnrealEditor process is already running' }
$a = @((Join-Path $proj 'TreeLookdev.uproject'), '/Game/NorthForest/Maps/L_NF_Yangmingshan', '-game', '-RenderOffscreen', "-ResX=$ResX", "-ResY=$ResY",
       '-ForceRes', '-nosound', '-unattended', "-abslog=$(Join-Path $out 'farlod.log')", '-ExecCmds="r.VSync 0, r.ProfileGPU.ShowUI 0"')
if ($Fly) { $a += @('-fffarlodfly', "-flflycfgs=$FlyCfgs", "-flflyframes=$FlyFrames") } else { $a += @('-fffarlodtest', "-flviews=$Views") }
if ($Profile) { $a += '-flprofile' }
if (-not $Sm5) { $a += '-featureleveles31'; $a += (& (Join-Path $RepoRoot 'tools\ntw\forest_world\mobile_cvars.ps1')) }
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -ArgumentList $a -PassThru -Wait
Write-Host "exit=$($p.ExitCode) $([int]$sw.Elapsed.TotalSeconds) s"
if (Test-Path $shots) { Move-Item (Join-Path $shots 'fl*_*.png') $out -Force -ErrorAction SilentlyContinue }
Select-String -Path (Join-Path $out 'farlod.log') -Pattern 'SKYFL ' | ForEach-Object { $_.Line -replace '^.*(SKYFL )', '$1' }


