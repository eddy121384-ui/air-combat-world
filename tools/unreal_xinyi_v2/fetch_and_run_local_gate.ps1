param(
    [string]$Repo = "eddy121384-ui/air-combat-world",
    [string]$Branch = "feat/xinyi-unreal-v2",
    [string]$Workflow = "xinyi-unreal-v2-contract.yml",
    [Nullable[long]]$RunId = $null,
    [string]$EngineRoot = "C:\\Program Files\\Epic Games\\UE_5.8"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$LocalGate = Join-Path $PSScriptRoot "run_local_gate.ps1"
$InputsBase = Join-Path $RepoRoot "unreal\\Saved\\XinyiUnrealV2Inputs"

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    throw "GitHub CLI (gh) is required. Install it and authenticate with 'gh auth login'."
}

& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run 'gh auth login' first."
}

if (-not $RunId.HasValue) {
    $json = & gh run list --repo $Repo --workflow $Workflow --branch $Branch --status success --limit 1 --json databaseId,headSha,conclusion,createdAt
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to query successful XinyiV2 contract runs."
    }

    $runs = @($json | ConvertFrom-Json)
    if ($runs.Count -eq 0) {
        throw "No successful $Workflow run found on $Branch."
    }
    $RunId = [long]$runs[0].databaseId
    Write-Host "Using latest successful contract run $RunId ($($runs[0].headSha))."
}
else {
    Write-Host "Using requested contract run $RunId."
}

$InputRoot = Join-Path $InputsBase ("run-" + $RunId.Value)
if (Test-Path $InputRoot) {
    Remove-Item -Recurse -Force $InputRoot
}
New-Item -ItemType Directory -Force -Path $InputRoot | Out-Null

Write-Host "Downloading xinyi-unreal-v2-inputs from run $RunId..."
& gh run download $RunId.Value --repo $Repo --name "xinyi-unreal-v2-inputs" --dir $InputRoot
if ($LASTEXITCODE -ne 0) {
    throw "gh run download failed for run $RunId."
}

$Contract = Join-Path $InputRoot "unreal\\Saved\\XinyiUnrealV2Contract\\xinyi_unreal_v2_contract.json"
$BuildingDir = Join-Path $InputRoot "unreal\\Saved\\XinyiV2Full\\run-01\\tiles"
if (-not (Test-Path $Contract)) {
    throw "Downloaded artifact is missing the contract: $Contract"
}
if (-not (Test-Path $BuildingDir)) {
    throw "Downloaded artifact is missing building tiles: $BuildingDir"
}

$glbs = @(Get-ChildItem -File -Filter "*.glb" $BuildingDir)
if ($glbs.Count -ne 25) {
    throw "Expected 25 validated building GLBs, found $($glbs.Count)."
}

Write-Host "XINYI_V2_INPUT_DOWNLOAD_OK run=$($RunId.Value) glbs=$($glbs.Count)"
Write-Host "Starting local UE5.8 gate..."

& $LocalGate -InputRoot $InputRoot -EngineRoot $EngineRoot
if ($LASTEXITCODE -ne 0) {
    throw "XinyiV2 local UE gate failed."
}

Write-Host ""
Write-Host "XINYI_V2_FETCH_AND_LOCAL_GATE_OK"
Write-Host "Input run: $($RunId.Value)"
Write-Host "Inputs:    $InputRoot"
