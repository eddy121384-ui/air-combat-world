# Forest performance A/B batch (exploratory, Intel UHD 770 only): for each named configuration, set the map state with
# adapters/unreal/ntwforest/nf_perfcfg.py, then one fixed-step perf run (-benchmark -fps=15) of LS_NF_Perf_P (3 stills + hero flight).
#   run_ab.ps1 -Plan ab_plan.json [-Prefix ab1] [-Frames 2150]
# ab_plan.json: [{"tag": "c49", "cfg": {...nf_perfcfg...}, "exec": "foliage.MaxEndCullDistance 260000"}, ...]  (applied in order;
# every cfg should be complete because the map keeps the previous state)
param([Parameter(Mandatory)][string]$Plan, [string]$Prefix = 'ab1', [int]$Frames = 2150)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$steps = Get-Content $Plan -Raw -Encoding utf8 | ConvertFrom-Json
foreach ($s in $steps) {
    $env:ACW_NF_CFG = ($s.cfg | ConvertTo-Json -Compress -Depth 5)
    & powershell -ExecutionPolicy Bypass -File (Join-Path $here 'run_nf.ps1') -Script nf_perfcfg.py -Name "cfg_$($s.tag)" -Expect nf_perfcfg.report.json -Extra '-nullrhi'
    if ($LASTEXITCODE -ne 0) { throw "config $($s.tag) failed" }
    Copy-Item (Join-Path $here '..\..\..\unreal\TreeLookdev\Saved\NorthForest\reports\nf_perfcfg.report.json') (Join-Path $here "..\..\..\unreal\TreeLookdev\Saved\NorthForest\reports\nf_perfcfg_$($s.tag).report.json") -Force
    $ex = if ($s.exec) { $s.exec } else { 'r.VSync 0' }   # never pass an empty -ExecCmds (PowerShell drops it)
    & powershell -ExecutionPolicy Bypass -File (Join-Path $here 'run_nf_perf.ps1') -Tag "${Prefix}_$($s.tag)" -Frames $Frames -FixedFps 15 -ExecCmds $ex -ExtraArgs $(if ($s.args) { $s.args } else { '-nosplash' })
}
