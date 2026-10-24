param([string]$SourceRoot = 'D:\Users\EDDY\Documents\GitHub\air-combat-world')
$ErrorActionPreference = 'Stop'
$target = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$allowed = 'C:\Users\EDDY\Desktop\M1A2\xinyi-material-ue58-round1'
if ($target -ne $allowed -or $SourceRoot -eq $target) { throw 'Unexpected staging destination' }
$env:GIT_OPTIONAL_LOCKS = '0'
$ledger = @()
$paths = @(
    'unreal\Content\XinyiV2',
    'unreal\Content\__ExternalActors__\XinyiV2',
    'unreal\Saved\XinyiUnrealV2Contract',
    'unreal\Plugins\XinyiLandscapeBridge\Binaries\Win64'
)
$look = Join-Path $SourceRoot 'unreal\Saved\XinyiLook'
# Clouds are OFF for this comparison; no cloud build is needed.
$paths += @(Get-ChildItem -LiteralPath $look | Where-Object {
    $_.Name -notin @('logs', 'evidence', 'unreal', 'preview', 'clouds')
} | ForEach-Object { 'unreal\Saved\XinyiLook\' + $_.Name })
foreach ($relative in $paths) {
    $src = Join-Path $SourceRoot $relative
    if (-not (Test-Path -LiteralPath $src)) { throw "Missing source: $src" }
    $files = if (Test-Path -LiteralPath $src -PathType Container) {
        @(Get-ChildItem -LiteralPath $src -Recurse -File)
    } else { @(Get-Item -LiteralPath $src) }
    foreach ($file in $files) {
        $rel = $file.FullName.Substring($SourceRoot.Length + 1)
        $dest = [IO.Path]::GetFullPath((Join-Path $target $rel))
        if (-not $dest.StartsWith($allowed + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Destination escaped isolation root' }
        $sha = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        if (Test-Path -LiteralPath $dest) {
            if ((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -ne $sha) { throw "Refusing overwrite: $dest" }
        } else {
            New-Item -ItemType Directory -Force ([IO.Path]::GetDirectoryName($dest)) | Out-Null
            Copy-Item -LiteralPath $file.FullName -Destination $dest
        }
        if ((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -ne $sha) { throw "Copy hash mismatch: $dest" }
        $ledger += [ordered]@{ relative_path = $rel; bytes = $file.Length; source_sha256 = $sha.ToLowerInvariant(); source_last_write_utc = $file.LastWriteTimeUtc.ToString('o') }
    }
}
$out = Join-Path $target 'investigation'
New-Item -ItemType Directory -Force $out | Out-Null
$ledger | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'staged-inputs.json') -Encoding utf8
Write-Output "Staged $($ledger.Count) files, $([math]::Round(($ledger | ForEach-Object { $_.bytes } | Measure-Object -Sum).Sum / 1MB, 2)) MiB, all copy hashes verified."
