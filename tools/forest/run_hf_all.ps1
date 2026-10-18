# Hillside forest look-dev v1: UE stages + native renders for one revision, in order, one UE process at a time.
#   run_hf_all.ps1 -Rev r3 [-SkipRenders]          (version A: single 紅楠, instances.json)
#   run_hf_all.ps1 -Rev m1 -Instances instances_mix.json   (mix v0 = Mix D: form A on the D balanced chain)
#   run_hf_all.ps1 -Rev a2 -Instances instances_acacia.json -AChain T   (相思樹 mix: form C = 相思樹, its own materials)
#   run_hf_all.ps1 -Rev m2 -Instances instances_mix.json -AChain C -Renders stills_forest,stills_empty,flight_forest,flight_empty   (Mix C)
# 1 hf_build (content + maps)  2 hf_verify (fresh process, fail-closed persisted-material gate)  3 hf_mrq_configs  4 MRQ renders
# NOTE: native frames are ~0.3-1.5 GB per movie folder; D: filled up once (see tools/forest/prune_hf_movies.ps1 - run it after the analysis scripts).
param([Parameter(Mandatory)][ValidatePattern('^[rmaj][0-9]+$')][string]$Rev, [string]$Instances = 'instances.json',
      [ValidateSet('C', 'D', 'S', 'T')][string]$AChain = 'D', [string[]]$Renders = @('stills_forest', 'stills_empty', 'flight_forest'), [string]$SunAz = '', [string]$SunEl = '', [string]$ViewsFile = 'views.json', [string]$CMesh = '', [string]$CLeaf = '', [switch]$SkipRenders)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$e = @{ ACW_HF_DIR = (Join-Path $RepoRoot 'out\forest\hillside'); ACW_HF_REV = $Rev; ACW_HF_INSTANCES = $Instances; ACW_HF_A_CHAIN = $AChain;
        ACW_HF_MRQ_ONLY = ($Renders -join ','); ACW_HF_VIEWS = $ViewsFile }
if ($CMesh) { $e['ACW_HF_C_MESH'] = $CMesh }
if ($CLeaf) { $e['ACW_HF_C_LEAF'] = $CLeaf }   # 相思樹 LOD chain (form C) other than the first import
if ($SunAz) { $e['ACW_HF_SUN_AZ'] = $SunAz; $e['ACW_HF_SUN_EL'] = $SunEl }   # lighting check revisions only
$tl = Join-Path $RepoRoot 'tools\treegen\run_tl.ps1'
& $tl -Script hf_build.py -Name "hf_build_$Rev" -Env $e -Expect hf_build.report.json; if ($LASTEXITCODE -ne 0) { throw 'hf_build failed' }
& $tl -Script hf_verify.py -Name "hf_verify_$Rev" -Env $e -Expect hf_verify.report.json; if ($LASTEXITCODE -ne 0) { throw 'hf_verify FAILED: no renders from unverified content' }
& $tl -Script hf_mrq_configs.py -Name "hf_mrq_cfg_$Rev" -Env $e -Expect hf_mrq_configs.report.json; if ($LASTEXITCODE -ne 0) { throw 'hf_mrq_configs failed' }
if ($SkipRenders) { return }
foreach ($k in $Renders) { & (Join-Path $PSScriptRoot 'run_hf_mrq.ps1') -Tag "hf_${k}_${Rev}_01" }
