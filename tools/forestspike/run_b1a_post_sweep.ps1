param([Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$folder=Join-Path $repo 'unreal\ForestSpike\Saved\ForestSpike\b1a'
$reopen=Join-Path $folder 'reopen02\receipt.json'
$plan=Get-Content (Join-Path $folder 'schedule.json') -Raw | ConvertFrom-Json
if ($plan.runs.Count -ne 80) { throw 'Formal plan is incomplete' }
foreach ($row in $plan.runs) {
 $path=Join-Path $folder "perf\$($row.tag)\run.json"
 if (-not (Test-Path -LiteralPath $path) -or (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json).status -ne 'PASS_FS_B1A_RUN') { throw "Formal sweep not complete: $($row.tag)" }
}
if ((Get-Content (Join-Path $folder 'resolution\resolution01\dimensions_only.json') -Raw | ConvertFrom-Json).status -ne 'PASS_FS_B1A_VIEWPORT_DIMENSIONS_ONLY') { throw 'Viewport dimensions not verified' }
foreach ($view in @('V3','V5')) {
 foreach ($group in @('A0','A1','B0','B1')) {
  $tag="dynamic_${group}_${view}_01";$run=Join-Path $folder "perf\$tag\run.json"
  if (Test-Path -LiteralPath $run) { if ((Get-Content -LiteralPath $run -Raw | ConvertFrom-Json).status -ne 'PASS_FS_B1A_RUN') { throw 'Retained failed dynamic run' };continue }
  & (Join-Path $PSScriptRoot 'run_b1a_capture.ps1') -Group $group -View $view -Tag $tag -ReopenReceipt $reopen -Python $Python
  if ($LASTEXITCODE -ne 0) { throw "Failed dynamic capture $tag retained" }
 }
}
$registered=Get-Content (Join-Path $PSScriptRoot 'b1a\registered.json') -Raw | ConvertFrom-Json
foreach ($pose in $registered.static_poses) {
 foreach ($group in @('A1','B1')) {
  $tag="runtime_lod_$($pose.id)_${group}_01"
  & (Join-Path $PSScriptRoot 'run_b1a_runtime_lod.ps1') -Group $group -View $pose.id -Tag $tag -ReopenReceipt $reopen -Python $Python
  if ($LASTEXITCODE -ne 0) { throw "Runtime LOD diagnostic failed: $tag" }
 }
}
foreach ($group in @('A0','A1','B0','B1')) {
 $tag="native_${group}_V3_03"
 if (-not (Test-Path -LiteralPath (Join-Path $folder "movies\$tag\process.json"))) {
  & (Join-Path $PSScriptRoot 'run_b1a_mrq.ps1') -Tag $tag -ConfigReceipt (Join-Path $folder 'movie_configs03\receipt.json')
 }
 & $Python (Join-Path $PSScriptRoot 'b1a\validate_movie.py') --dir (Join-Path $folder "movies\$tag") --out (Join-Path $folder "movies\$tag\validated.json")
 if ($LASTEXITCODE -ne 0) { throw "Native V3 output gate failed: $tag" }
}
foreach ($group in @('A0','A1','B0','B1')) {
 $tag="clip_${group}_V5_01"
 & (Join-Path $PSScriptRoot 'run_b1a_mrq.ps1') -Tag $tag -ConfigReceipt (Join-Path $folder 'clip_configs01\receipt.json')
 & $Python (Join-Path $PSScriptRoot 'b1a\validate_movie.py') --dir (Join-Path $folder "movies\$tag") --out (Join-Path $folder "movies\$tag\validated.json")
 if ($LASTEXITCODE -ne 0) { throw "Native V5 output gate failed: $tag" }
}
& (Join-Path $PSScriptRoot 'run_b1a_stage.ps1') -Script fs_b1a_stills.py -Tag stills01 -Env @{}
if ($LASTEXITCODE -ne 0) { throw 'Native still/temporal capture incomplete' }
Write-Output 'PASS_FS_B1A_POST_SWEEP_CAPTURES'
