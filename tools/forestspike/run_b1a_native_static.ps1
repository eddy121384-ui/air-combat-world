param([Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$folder=Join-Path $repo 'unreal\ForestSpike\Saved\ForestSpike\b1a'
$receipt=Join-Path $folder 'native_static_reopen01\receipt.json'
$configs=(Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json).configs
if ($configs.Count -ne 16) { throw 'Incomplete native-static plan' }
foreach ($cfg in $configs) {
 $out=Join-Path $folder "movies\$($cfg.tag)"
 & (Join-Path $PSScriptRoot 'run_b1a_mrq.ps1') -Tag $cfg.tag -ConfigReceipt $receipt
 & $Python (Join-Path $PSScriptRoot 'b1a\validate_movie.py') --dir $out --out (Join-Path $out 'validated.json')
 if ($LASTEXITCODE -ne 0) { throw "Native static gate failed: $($cfg.tag)" }
}
Write-Output 'PASS_FS_B1A_NATIVE_STATIC_CAPTURE_SET'
