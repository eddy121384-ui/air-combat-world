param(
    [Parameter(Mandatory)][ValidateSet('assets','level','smoke','baseline','candidate-build','candidate')][string]$Stage,
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8'
)
# Same UnrealEditor-Cmd / Python / SceneCapture stages as run_xinyi_look.ps1.
# Deliberately never invokes the offline all-city build or Cook.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($repo -ne 'C:\Users\EDDY\Desktop\M1A2\xinyi-material-ue58-round1') { throw 'Isolation guard failed' }
if (Get-Process UnrealEditor,UnrealEditor-Cmd -ErrorAction SilentlyContinue) { throw 'Another Unreal editor is running' }
$env:ACW_REPO_ROOT = $repo
$env:ACW_XINYI_LOOK_TOD = 'day'
$env:ACW_XINYI_LOOK_CLOUDS = 'off'
$env:ACW_XINYI_LOOK_SHOTS = 'f_rooftops_wuxing'
$env:ACW_XINYI_LOOK_PERF = ''
$env:ACW_XINYI_MATERIAL_VARIANT = $Stage
$scripts = @{
    'assets' = 'xinyi_look_build_assets.py'
    'level' = 'xinyi_look_build_level.py'
    'smoke' = 'xinyi_look_capture.py'
    'baseline' = 'xinyi_material_ab_capture.py'
    'candidate-build' = 'xinyi_material_ab_build.py'
    'candidate' = 'xinyi_material_ab_capture.py'
}
$receipts = @{
    'assets' = @('look_assets.report.json', 'PASS_LOOK_ASSETS')
    'level' = @('look_level.report.json', 'PASS_LOOK_LEVEL')
    'smoke' = @('look_capture.report.json', 'PASS_LOOK_CAPTURE')
    'baseline' = @('look_capture.report.json', 'PASS_LOOK_CAPTURE')
    'candidate-build' = @('material_ab_build.report.json', 'PASS_MATERIAL_AB_BUILD')
    'candidate' = @('look_capture.report.json', 'PASS_LOOK_CAPTURE')
}
$reports = Join-Path $repo 'unreal\Saved\XinyiLook\unreal'
$logs = Join-Path $repo 'investigation'
New-Item -ItemType Directory -Force $reports,$logs | Out-Null
$report = Join-Path $reports $receipts[$Stage][0]
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
if (Test-Path -LiteralPath $report) {
    Move-Item -LiteralPath $report -Destination (Join-Path $logs "$Stage-before-$stamp.json")
}
$log = Join-Path $logs "$Stage-$stamp.log"
$script = Join-Path $repo ('adapters\unreal\lookdev\' + $scripts[$Stage])
& (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') (Join-Path $repo 'unreal\AirCombatWorld.uproject') "-ExecutePythonScript=$script" -unattended -nopause -nosound -nop4 "-abslog=$log"
if ($LASTEXITCODE -ne 0) { throw "UE exited $LASTEXITCODE; see $log" }
if (-not (Test-Path -LiteralPath $report)) { throw "No receipt: $report; see $log" }
$r = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
Copy-Item -LiteralPath $report -Destination (Join-Path $logs "$Stage-$stamp.report.json")
if ($r.status -ne $receipts[$Stage][1]) { throw "Stage failed: $($r.status); see $report" }
Write-Output "$Stage : $($r.status)"
