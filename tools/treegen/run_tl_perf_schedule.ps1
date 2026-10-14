# TreeLookdev: interleaved tree / empty perf schedule (order alternates each round), then summary.
#   run_tl_perf_schedule.ps1 -Prefix p1 -Rounds 2 [-Views front,close,agl50,agl200] [-Frames 600]
param([Parameter(Mandatory)][string]$Prefix, [int]$Rounds = 2, [string[]]$Views = @('front', 'close', 'agl50', 'agl200'), [int]$Frames = 600)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
for ($r = 1; $r -le $Rounds; $r++) {
    foreach ($v in $Views) {
        $order = if ($r % 2 -eq 1) { @('tree', 'empty') } else { @('empty', 'tree') }
        foreach ($variant in $order) {
            & (Join-Path $PSScriptRoot 'run_tl_perf.ps1') -Level "L_TLP_${v}_$variant" -Tag "${Prefix}r$r" -Frames $Frames
        }
    }
}
& 'D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe' (Join-Path $PSScriptRoot 'analyze_tl_perf.py') `
    (Join-Path $RepoRoot 'unreal\TreeLookdev\Saved\TreeLookdev\perf') (Join-Path $RepoRoot "unreal\TreeLookdev\Saved\TreeLookdev\reports\perf_$Prefix.json")
