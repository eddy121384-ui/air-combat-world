# TreeLookdev moving-camera gate: GPU / frame time WHILE FLYING (standalone -game, 1080p, UE CSV profiler, fixed 60 fps step, the sequence auto-plays from BeginPlay).
# One run per (condition A / D / E=empty, path); order of the conditions reverses every round. Host: Intel UHD 770 only.
#   run_tlf_perf_schedule.ps1 -Prefix fp -Rounds 3
param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Prefix, [int]$Rounds = 3, [string]$Dir = 'FlightF', [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$paths = Get-Content (Join-Path $RepoRoot 'out\treegen\machilus_game\flight_paths.json') -Raw | ConvertFrom-Json
$project = Join-Path $RepoRoot 'unreal\TreeLookdev\TreeLookdev.uproject'
$exe = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$exec = 'r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.GPUCsvStatsEnabled 1'
for ($r = 1; $r -le $Rounds; $r++) {
    foreach ($p in 'P1_250', 'P2_250', 'P2_100', 'P3_250') {
        $conds = if ($r % 2 -eq 1) { @('E', 'A', 'D') } else { @('D', 'A', 'E') }
        $frames = $paths.paths.$p.keys[-1].frame + 40   # + boot rows
        foreach ($c in $conds) {
            if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
            $level = "L_TLF_${c}_$p"
            $out = Join-Path $RepoRoot "unreal\TreeLookdev\Saved\TreeLookdev\flight\perf\${Prefix}r${r}__$level"
            if (Test-Path -LiteralPath $out) { throw "Refusing to overwrite prior run: $out" }
            New-Item -ItemType Directory -Path $out | Out-Null
            $log = Join-Path $out 'engine.log'
            $a = @("`"$project`"", "/Game/TreeLookdev/$Dir/$level", '-game', '-windowed', '-ResX=1920', '-ResY=1080', '-nosound', '-nosplash', '-unattended', '-benchmark', '-fps=60',
                "-ExecCmds=`"$exec`"", "-csvCaptureFrames=$frames", '-ExitAfterCsvProfiling', "-abslog=`"$log`"")
            $proc = Start-Process -FilePath $exe -ArgumentList $a -WindowStyle Hidden -Wait -PassThru
            $m = [regex]::Matches((Get-Content -LiteralPath $log -Raw), 'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
            if ($m.Count -ne 1) { Write-Host "FAIL: no CSV ($out)"; continue }
            Copy-Item -LiteralPath ([IO.Path]::GetFullPath((Join-Path (Split-Path $exe) $m[0].Groups[1].Value.Trim()))) -Destination (Join-Path $out 'profile.csv')
            Write-Host "FLIGHT_PERF_OK $level r$r exit=$($proc.ExitCode) frames=$frames"
        }
    }
}
