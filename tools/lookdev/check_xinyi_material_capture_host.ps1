param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8',
    [string[]]$SourceRoots = @(
        'C:\Users\EDDY\Desktop\M1A2\air-combat-world',
        'C:\Users\EDDY\Documents\GitHub\air-combat-world',
        'D:\Users\EDDY\Documents\GitHub\air-combat-world'
    ),
    [string]$OutputDirectory = '',
    [string]$SnapshotName = 'preflight'
)

# Read-only host inspection. This does NOT launch UE, import, build, or capture.
# Run in native Windows PowerShell: sandbox-projected paths/CIM are incomplete.
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $RepoRoot 'unreal\Saved\XinyiMaterialCaptureHost'
}
if ($SnapshotName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid SnapshotName' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$env:GIT_OPTIONAL_LOCKS = '0'
$env:GIT_NO_LAZY_FETCH = '1'

function Read-Git([string]$Root, [string[]]$GitArgs) {
    $safeRoot = $Root.Replace('\', '/')
    $lines = @(& git -c "safe.directory=$safeRoot" -C $Root @GitArgs 2>&1 | ForEach-Object { "$_" })
    if ($LASTEXITCODE -ne 0) { throw "git failed for ${Root}: $($lines -join ' ')" }
    return $lines
}

$roots = [System.Collections.Generic.List[string]]::new()
$registries = @()
foreach ($source in $SourceRoots) {
    $listing = @(Read-Git $source @('worktree', 'list', '--porcelain'))
    $registries += [ordered]@{ repository = $source; listing = $listing }
    foreach ($line in $listing) {
        if ($line.StartsWith('worktree ')) {
            $candidate = $line.Substring(9).Replace('/', '\')
            if (-not $roots.Contains($candidate)) { $roots.Add($candidate) }
        }
    }
}
if (-not $roots.Contains($RepoRoot)) { $roots.Add($RepoRoot) }

$worktrees = @()
$assets = @()
foreach ($root in $roots) {
    $content = Join-Path $root 'unreal\Content'
    $look = Join-Path $content 'XinyiLook'
    $map = Join-Path $look 'L_XinyiLook_Hero.umap'
    $bridge = Join-Path $root 'unreal\Plugins\XinyiLandscapeBridge\Binaries\Win64\UnrealEditor-XinyiLandscapeBridge.dll'
    $worktrees += [ordered]@{
        root = $root
        head = @(Read-Git $root @('rev-parse', 'HEAD'))[0]
        status = @(Read-Git $root @('status', '--porcelain=v1', '--branch'))
        xinyi_look_directory_exists = Test-Path -LiteralPath $look -PathType Container
        required_scene = $map
        required_scene_exists = Test-Path -LiteralPath $map -PathType Leaf
        landscape_bridge_binary_exists = Test-Path -LiteralPath $bridge -PathType Leaf
    }
    # Hash the Content of the three existing source clones only. Never save UE assets.
    if ($SourceRoots -contains $root) {
        foreach ($file in @(Get-ChildItem -LiteralPath $content -Recurse -File | Sort-Object FullName)) {
            $assets += [ordered]@{
                path = $file.FullName
                bytes = $file.Length
                sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    }
}

$historical = @()
foreach ($source in $SourceRoots) {
    foreach ($relative in @(
        'unreal\Saved\Autosaves\Game\XinyiLook\L_XinyiLook_Hero_Auto1.umap',
        'unreal\Saved\Autosaves\Game\XinyiLook\L_XinyiLook_Hero_Auto2.umap',
        'unreal\Saved\XinyiLook\unreal\look_capture.report.json'
    )) {
        $path = Join-Path $source $relative
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $file = Get-Item -LiteralPath $path
            $historical += [ordered]@{
                path = $path; bytes = $file.Length; last_write_time_utc = $file.LastWriteTimeUtc.ToString('o')
                sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                used_for_this_capture = $false
            }
        }
    }
}

$engineVersion = Join-Path $EngineRoot 'Engine\Build\Build.version'
$version = if (Test-Path -LiteralPath $engineVersion) { Get-Content -LiteralPath $engineVersion -Raw | ConvertFrom-Json } else { $null }
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'Unreal|ShaderCompile|LiveCoding|CrashReport|MSBuild'
} | Select-Object ProcessId, Name, CommandLine)
$sceneFound = @($worktrees | Where-Object { $_.required_scene_exists }).Count -gt 0
$receipt = [ordered]@{
    schema_version = 1
    recorded_at_utc = [DateTime]::UtcNow.ToString('o')
    status = if ($sceneFound) { 'SCENE_FILE_FOUND' } else { 'SCENE_FILE_MISSING' }
    unreal_launched_by_this_script = $false
    ue_screenshots_generated_by_this_script = 0
    engine_root = $EngineRoot
    engine_version = $version
    unreal_cmd_exists = Test-Path -LiteralPath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe') -PathType Leaf
    unreal_editor_exists = Test-Path -LiteralPath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe') -PathType Leaf
    disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, Size, FreeSpace)
    graphics = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion)
    unreal_related_processes = $processes
    worktree_registries = $registries
    worktrees = $worktrees
    protected_content_hashes = $assets
    historical_files_not_used = $historical
    source_roots = $SourceRoots
    notes = @(
        'Required map must exist with its complete dependency closure before UE capture.',
        'Finding a map alone does not prove its dependencies or plugin compatibility.',
        'This inspector does not recover autosaves, rebuild, import, Cook, or launch Unreal.',
        'No image or historical capture is an output of this inspector.'
    )
}
$output = Join-Path $OutputDirectory "$SnapshotName.json"
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $output -Encoding utf8
Write-Output "Receipt: $output"
Write-Output "Status: $($receipt.status)"
Write-Output "Checked worktrees: $($worktrees.Count); protected Content files: $($assets.Count)"
if (-not $sceneFound) { exit 2 }
