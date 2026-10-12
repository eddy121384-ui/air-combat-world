# Run one capture spec (tools/forestspike/make_spec.py <set>) in a fresh UnrealEditor-Cmd process.
param([Parameter(Mandatory)][string]$Set)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$spec = Join-Path $RepoRoot "unreal\ForestSpike\Saved\ForestSpike\specs\$Set.json"
if (-not (Test-Path $spec)) { throw "spec not found (run make_spec.py $Set first): $spec" }
$env:ACW_FS_SPEC = $spec
& (Join-Path $PSScriptRoot "run_stage.ps1") -Script fs_capture.py -Name "capture_$Set" -Expect "fs_capture.$Set.report.json"
exit $LASTEXITCODE
