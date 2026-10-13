param([Parameter(Mandatory)][string]$ReopenReceipt,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$spec=Get-Content (Join-Path $PSScriptRoot 'b1a\registered.json') -Raw | ConvertFrom-Json
$plan=@()
for ($round=0;$round -lt 5;$round++) {
 for ($j=0;$j -lt 4;$j++) {
  $pose=$spec.static_poses[($j+$round)%4]
  foreach ($group in $spec.static_capture.order[$round]) {
   $tag='r{0:d2}_{1}_{2}' -f ($round+1),$pose.id,$group
   $plan+=@{round=$round+1;group=$group;view=$pose.id;tag=$tag}
  }
 }
}
$folder=Join-Path $repo 'unreal\ForestSpike\Saved\ForestSpike\b1a'
$planPath=Join-Path $folder 'schedule.json'
if (-not (Test-Path -LiteralPath $planPath)) { @{runs=$plan;registered_rounds=5;scope='Four arms across four altitudes; 500/1000m S effects only'} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $planPath -Encoding utf8 }
foreach ($row in $plan) {
 $result=Join-Path $folder "perf\$($row.tag)\run.json"
 if (Test-Path -LiteralPath $result) {
  $old=Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
  if ($old.status -ne 'PASS_FS_B1A_RUN') { throw "Retained failed attempt $($row.tag); repair/re-register a complete paired block before resuming" }
  Write-Output "RESUME preserved $($row.tag)"
 } else {
  & (Join-Path $PSScriptRoot 'run_b1a_capture.ps1') -Group $row.group -View $row.view -Tag $row.tag -ReopenReceipt $ReopenReceipt -Python $Python
  if ($LASTEXITCODE -ne 0) { throw "Failed attempt retained: $($row.tag)" }
 }
 @{latest_tag=$row.tag;round=$row.round;updated_utc=[DateTimeOffset]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder 'schedule_progress.json') -Encoding utf8
}
Write-Output 'PASS_FS_B1A_STATIC_SCHEDULE_80'
