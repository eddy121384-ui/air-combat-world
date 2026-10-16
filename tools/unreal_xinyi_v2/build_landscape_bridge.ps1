param(
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PluginRoot = Join-Path $RepoRoot "unreal\Plugins\XinyiLandscapeBridge"
$Plugin = Join-Path $PluginRoot "XinyiLandscapeBridge.uplugin"
$Package = Join-Path $RepoRoot "unreal\Saved\XinyiLandscapeBridgeBuild"
$RunUAT = Join-Path $EngineRoot "Engine\Build\BatchFiles\RunUAT.bat"

if (-not (Test-Path $RunUAT)) { throw "RunUAT.bat not found: $RunUAT" }
if (-not (Test-Path $Plugin)) { throw "plugin descriptor not found: $Plugin" }

if (Test-Path $Package) {
    Remove-Item -Recurse -Force $Package
}

Write-Host "Building XinyiLandscapeBridge against installed UE5.8..."
& $RunUAT BuildPlugin "-Plugin=$Plugin" "-Package=$Package" -TargetPlatforms=Win64 -Rocket
if ($LASTEXITCODE -ne 0) {
    throw "BuildPlugin failed with exit code $LASTEXITCODE. The toolchain was found; inspect the compiler error above or the AutomationTool log for the actual cause."
}

$BuiltBinaries = Join-Path $Package "Binaries"
if (-not (Test-Path $BuiltBinaries)) {
    throw "BuildPlugin succeeded but no Binaries directory was produced: $BuiltBinaries"
}

$DestBinaries = Join-Path $PluginRoot "Binaries"
if (Test-Path $DestBinaries) {
    Remove-Item -Recurse -Force $DestBinaries
}
Copy-Item -Recurse -Force $BuiltBinaries $DestBinaries

$dlls = @(Get-ChildItem -Recurse -Filter "*XinyiLandscapeBridge*.dll" $DestBinaries)
if ($dlls.Count -eq 0) {
    throw "No XinyiLandscapeBridge DLL found after BuildPlugin."
}

Write-Host "XINYI_LANDSCAPE_BRIDGE_BUILD_OK"
$dlls | ForEach-Object { Write-Host $_.FullName }
