# Skyfront Free Flight v1: package the TreeLookdev project (North Taiwan / Yangmingshan forest map + SkyfrontFreeFlight module) as a
# sideloadable Android APK: arm64, Vulkan only, ASTC cook, Development config, cooked data inside the APK (one file to install).
# Toolchain (Android_SDK.json of UE 5.8): SDK platform android-34, build-tools 35.0.1, NDK r27c 27.2.12479018, CMake 3.22.1, JDK 17.
# Environment variables are set for this process only. Requires the "Android" target platform of UE 5.8 (Epic Games Launcher option).
#   package_android.ps1 [-Sdk C:\Android\Sdk] [-Jdk <jdk17 dir>] [-Config Development] [-Log <path>]
param([string]$Sdk = 'C:\Android\Sdk', [string]$Jdk = '', [string]$Config = 'Development', [string]$Log = '',
      [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
if (-not (Test-Path (Join-Path $EngineRoot 'Engine\Build\Android\Java'))) { throw 'UE 5.8 Android target platform is not installed (Engine\Build\Android\Java missing)' }
if (-not $Jdk) { $Jdk = (Get-ChildItem 'C:\Program Files\Microsoft' -Directory -Filter 'jdk-17*' | Sort-Object Name -Descending | Select-Object -First 1).FullName }
$ndk = Join-Path $Sdk 'ndk\27.2.12479018'
foreach ($p in @($Jdk, $ndk, (Join-Path $Sdk 'platforms\android-34'), (Join-Path $Sdk 'build-tools\35.0.1'))) { if (-not (Test-Path $p)) { throw "missing $p" } }
$env:JAVA_HOME = $Jdk; $env:ANDROID_HOME = $Sdk; $env:ANDROID_SDK_ROOT = $Sdk; $env:NDKROOT = $ndk; $env:NDK_ROOT = $ndk
$env:PATH = "$Jdk\bin;$Sdk\platform-tools;$env:PATH"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$proj = Join-Path $RepoRoot 'unreal\TreeLookdev'
$archive = Join-Path $proj 'Saved\Skyfront\android_archive'
if (-not $Log) { $Log = Join-Path $proj 'Saved\Skyfront\logs\buildcookrun_android.log' }
New-Item -ItemType Directory -Force -Path (Split-Path $Log), $archive | Out-Null
$sw = [Diagnostics.Stopwatch]::StartNew()
& (Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat') BuildCookRun "-project=$(Join-Path $proj 'TreeLookdev.uproject')" `
    "-unrealexe=$(Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe')" -noP4 -platform=Android -cookflavor=ASTC `
    "-clientconfig=$Config" -build -cook -stage -pak -package -archive "-archivedirectory=$archive" `
    -map=/Game/NorthForest/Maps/L_NF_Yangmingshan -unattended -utf8output *>&1 | Tee-Object -FilePath $Log | Out-Null
$code = $LASTEXITCODE
Write-Host "BUILDCOOKRUN exit=$code $([int]$sw.Elapsed.TotalMinutes) min log=$Log"
Get-ChildItem $archive -Recurse -Include *.apk, *.obb | ForEach-Object { '{0}  {1:N1} MB' -f $_.FullName, ($_.Length / 1MB) }
exit $code
