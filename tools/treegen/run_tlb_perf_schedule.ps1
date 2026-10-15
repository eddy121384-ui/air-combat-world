# TreeLookdev budget experiment: interleaved empty / candidate perf schedule (order reverses every round), then analysis.
#   run_tlb_perf_schedule.ps1 -Prefix q1 -Rounds 2 [-Frames 600]
# Host scope: Intel UHD 770 only. One UE process at a time; nothing else heavy running.
param([Parameter(Mandatory)][string]$Prefix, [int]$Rounds = 2, [int]$Frames = 260, [int]$FirstRound = 1)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
# (view, kind, candidates) - kind single = the look-dev tree, patch = 10 x 10 same-tree HISM patch
$plan = @(
    @('front', 'single', @('A', 'C', 'D')),
    @('sl150', 'single', @('A', 'C', 'D')),
    @('sl150', 'patch', @('A', 'B', 'C', 'D')),
    @('sl300', 'patch', @('A', 'B', 'C', 'D')),
    @('sl500', 'patch', @('A', 'B', 'C', 'D')),
    @('sl1000', 'patch', @('A', 'B', 'C', 'D'))
)
for ($r = $FirstRound; $r -lt $FirstRound + $Rounds; $r++) {
    $levels = New-Object System.Collections.Generic.List[string]
    foreach ($v in @('front', 'sl150', 'sl300', 'sl500', 'sl1000')) { $levels.Add("L_TLB_${v}_empty") }
    foreach ($p in $plan) { foreach ($c in $p[2]) { $levels.Add("L_TLB_$($p[0])_$($p[1])_$c") } }
    # group by view so each empty brackets its candidates; alternate direction each round
    $byView = [ordered]@{}
    foreach ($l in $levels) { $v = ($l -split '_')[2]; if (-not $byView.Contains($v)) { $byView[$v] = New-Object System.Collections.Generic.List[string] }; $byView[$v].Add($l) }
    foreach ($v in $byView.Keys) {
        $items = @($byView[$v] | Sort-Object { if ($_ -like '*_empty') { 0 } else { 1 } }, { $_ })
        if ($r % 2 -eq 0) { [array]::Reverse($items) }
        foreach ($l in $items) {
            & (Join-Path $PSScriptRoot 'run_tl_perf.ps1') -Level $l -Tag "${Prefix}r$r" -Frames $Frames
        }
    }
}
& 'D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe' (Join-Path $PSScriptRoot 'analyze_budget_perf.py') `
    (Join-Path $RepoRoot 'unreal\TreeLookdev\Saved\TreeLookdev\perf') (Join-Path $RepoRoot "unreal\TreeLookdev\Saved\TreeLookdev\reports\budget_perf_$Prefix.json") $Prefix
