# Hillside forest look-dev: free disk by deleting the native MRQ PNG frame folders (regenerable; videos / sheets / json are committed evidence).
# Run AFTER hillside_frames.py / hillside_lod1_recovery.py have consumed the frames. Dry run unless -Delete is given.
#   prune_hf_movies.ps1 [-Keep m1,m2,m7] [-Delete]      # keeps every movie folder whose revision tag is in -Keep (e.g. the baselines used as masks)
param([string[]]$Keep = @(), [switch]$Delete)
$ErrorActionPreference = 'Stop'
$Keep = @($Keep | ForEach-Object { $_ -split ',' } | Where-Object { $_ })   # "-File ... -Keep m1,m2" arrives as one string
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is running (it may be writing frames)' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$movies = Join-Path $RepoRoot 'unreal\TreeLookdev\Saved\TreeLookdev\hillside\movies'
$total = 0
foreach ($d in Get-ChildItem $movies -Directory -ErrorAction SilentlyContinue) {
    # folder names: hf_<stills|flight>_<forest|empty>_<rev>_<nn>
    $rev = if ($d.Name -match '_([rm][0-9]+)_[0-9]+$') { $Matches[1] } else { '' }
    if ($Keep -contains $rev) { "keep   {0}" -f $d.Name; continue }
    $gb = [math]::Round((Get-ChildItem $d.FullName -Recurse -File | Measure-Object Length -Sum).Sum / 1GB, 2)
    $total += $gb
    if ($Delete) { Remove-Item -LiteralPath $d.FullName -Recurse -Force; "deleted {0,-34} {1,5} GB" -f $d.Name, $gb } else { "would delete {0,-28} {1,5} GB" -f $d.Name, $gb }
}
"{0}: {1:N2} GB {2}" -f $(if ($Delete) { 'freed' } else { 'dry run, would free' }), $total, $(if ($Delete) { '' } else { '(add -Delete)' })
