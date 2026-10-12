# Interleaved perf schedule: for each round the config order alternates (A,B / B,A / ...) so a systematic host drift
# (thermal / shared package power on the UHD 770 iGPU) is not attributed to a configuration.
#   run_perf_schedule.ps1 -Levels L_FSP_A_S1_v1_agl200_p10,L_FSP_B_S1_v1_agl200_p10 -Rounds 3 -Frames 480 -Prefix static
param(
    [Parameter(Mandatory)][string[]]$Levels,
    [int]$Rounds = 3,
    [int]$Frames = 480,
    [string]$Prefix = "run"
)
$ErrorActionPreference = "Stop"
for ($r = 1; $r -le $Rounds; $r++) {
    $order = if ($r % 2 -eq 1) { $Levels } else { $Levels[($Levels.Length - 1)..0] }
    foreach ($lv in $order) {
        & (Join-Path $PSScriptRoot "run_perf.ps1") -Level $lv -Tag ("{0}_r{1}" -f $Prefix, $r) -Frames $Frames
        if ($LASTEXITCODE -ne 0) { throw "perf run failed: $lv round $r" }
    }
}
