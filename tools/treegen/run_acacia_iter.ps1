# 相思樹 look-dev iteration: build + Cycles preview renders of tools/treegen/acacia_confusa.py into out/treegen/acacia/<Tag>.
#   run_acacia_iter.ps1 -Tag it2 [-Res 960x540] [-Samples 24] [-Views front,oblique,top] [-Params path.json]
param([Parameter(Mandatory)][string]$Tag, [string]$Res = '960x540', [int]$Samples = 24, [string]$Views = 'front,oblique,top', [string]$Params = '')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$b = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
$out = Join-Path $RepoRoot "out\treegen\acacia\$Tag"
if ($Params) { $env:ACW_TG_PARAMS = (Resolve-Path $Params).Path } else { Remove-Item Env:ACW_TG_PARAMS -ErrorAction SilentlyContinue }
& $b -b --factory-startup -noaudio --python (Join-Path $PSScriptRoot 'acacia_confusa.py') -- $out --res $Res --samples $Samples --views $Views --tag $Tag 2>&1 |
    Select-String -Pattern 'STATS|RENDERED|RENDER_S|Error|Traceback|line \d+' | ForEach-Object { $_.Line }
