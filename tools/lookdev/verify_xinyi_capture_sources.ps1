param([string]$SourceRoot = 'D:\Users\EDDY\Documents\GitHub\air-combat-world')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ledger = Get-Content -LiteralPath (Join-Path $repo 'investigation\staged-inputs.json') -Raw | ConvertFrom-Json
$changed = @()
$changedCopies = @()
foreach ($row in $ledger) {
    $source = Join-Path $SourceRoot $row.relative_path
    $copy = Join-Path $repo $row.relative_path
    if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.source_sha256) {
        $changed += $row.relative_path
    }
    if (-not (Test-Path -LiteralPath $copy -PathType Leaf) -or
        (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.source_sha256) {
        $changedCopies += $row.relative_path
    }
}
$result = [ordered]@{
    status = if ($changed.Count -eq 0 -and $changedCopies.Count -eq 0) { 'PASS_SOURCE_IMMUTABILITY' } else { 'FAIL_SOURCE_IMMUTABILITY' }
    recorded_at_utc = [DateTime]::UtcNow.ToString('o')
    source_root = $SourceRoot
    compared_files = $ledger.Count
    source_changed = $changed
    staged_input_copies_changed = $changedCopies
    disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, FreeSpace)
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $repo 'investigation\source-immutability.json') -Encoding utf8
Write-Output "$($result.status): $($ledger.Count) source files and staged copies compared."
if ($changed.Count -gt 0 -or $changedCopies.Count -gt 0) { exit 2 }
