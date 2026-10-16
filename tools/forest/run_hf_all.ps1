# Hillside forest look-dev v1: UE stages + native renders for one revision, in order, one UE process at a time.
#   run_hf_all.ps1 -Rev r3 [-SkipRenders]          (version A: single 紅楠, instances.json)
#   run_hf_all.ps1 -Rev m1 -Instances instances_mix.json   (mix v0, version B)
# 1 hf_build (content + maps)  2 hf_verify (fresh process, fail-closed persisted-material gate)  3 hf_mrq_configs  4 MRQ: stills forest / empty, flight
param([Parameter(Mandatory)][ValidatePattern('^[rm][0-9]+$')][string]$Rev, [string]$Instances = 'instances.json', [switch]$SkipRenders)
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$e = @{ ACW_HF_DIR = (Join-Path $RepoRoot 'out\forest\hillside'); ACW_HF_REV = $Rev; ACW_HF_INSTANCES = $Instances }
$tl = Join-Path $RepoRoot 'tools\treegen\run_tl.ps1'
& $tl -Script hf_build.py -Name "hf_build_$Rev" -Env $e -Expect hf_build.report.json; if ($LASTEXITCODE -ne 0) { throw 'hf_build failed' }
& $tl -Script hf_verify.py -Name "hf_verify_$Rev" -Env $e -Expect hf_verify.report.json; if ($LASTEXITCODE -ne 0) { throw 'hf_verify FAILED: no renders from unverified content' }
& $tl -Script hf_mrq_configs.py -Name "hf_mrq_cfg_$Rev" -Env $e -Expect hf_mrq_configs.report.json; if ($LASTEXITCODE -ne 0) { throw 'hf_mrq_configs failed' }
if ($SkipRenders) { return }
foreach ($k in 'stills_forest', 'stills_empty', 'flight_forest') { & (Join-Path $PSScriptRoot 'run_hf_mrq.ps1') -Tag "hf_${k}_${Rev}_01" }
