# North Taiwan forest mobile profile: print the phone device-profile cvars as one -dpcvars= argument for the PC ES3.1 preview runs.
# Source of truth: [Android DeviceProfile] in unreal/TreeLookdev/Config/DefaultDeviceProfiles.ini; the [IOS DeviceProfile] block must match.
#   $dp = & tools/ntw/forest_world/mobile_cvars.ps1      ->  -dpcvars=r.DetailMode=0,r.CookOutUnusedDetailModeComponents=1,...
$ErrorActionPreference = 'Stop'
$ini = Join-Path $PSScriptRoot '..\..\..\unreal\TreeLookdev\Config\DefaultDeviceProfiles.ini'
$sec, $cv = $null, @{ Android = @(); IOS = @() }
foreach ($line in Get-Content -LiteralPath $ini -Encoding utf8) {
    if ($line -match '^\[(\w+) DeviceProfile\]') { $sec = $Matches[1]; continue }
    if ($sec -and $cv.ContainsKey($sec) -and $line -match '^\+CVars=(.+)$') { $cv[$sec] += $Matches[1].Trim() }
}
if (-not $cv.Android.Count) { throw 'no [Android DeviceProfile] cvars' }
if (($cv.Android -join ',') -ne ($cv.IOS -join ',')) { throw 'Android and IOS mobile forest cvars differ' }
'-dpcvars=' + ($cv.Android -join ',')
