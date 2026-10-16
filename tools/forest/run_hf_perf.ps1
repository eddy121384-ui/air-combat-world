# Hillside forest look-dev v1: EXPLORATORY GPU cost (standalone -game 1080p, UE CSV profiler, fixed 60 fps step). Not a benchmark.
# Per round: for each still view (static camera) and the flyover (auto-play sequence) one forest and one empty-forest run of the same map
# pair; the order inside a pair reverses every round (capture-harness lesson: "layer on first" reads +1-2 ms of fake cost).
# -MixRev adds a condition "mix" (the forest maps of that revision, e.g. the mix v0 build m1); -ExtraRevs adds one condition per revision
# ("x<rev>", e.g. xm3), all interleaved in the same session.
#   run_hf_perf.ps1 -Rev r3 -Prefix p1 -Rounds 2 [-Views agl50,flight] [-MixRev m1] [-ExtraRevs m3,m7]
# Host: Intel UHD 770 only. One UE process at a time; nothing else heavy running (shared package power).
param([Parameter(Mandatory)][ValidatePattern('^[rm][0-9]+$')][string]$Rev, [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9]+$')][string]$Prefix,
      [int]$Rounds = 2, [int]$StillFrames = 260, [string[]]$Views = @('agl50', 'agl200', 'agl500', 'flight'),
      [ValidatePattern('^([rm][0-9]+)?$')][string]$MixRev = '', [string[]]$ExtraRevs = @(), [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.8')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$project = Join-Path $RepoRoot 'unreal\TreeLookdev\TreeLookdev.uproject'
$exe = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$exec = 'r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.GPUCsvStatsEnabled 1'
$V = Get-Content (Join-Path $RepoRoot 'out\forest\hillside\views.json') -Raw | ConvertFrom-Json
$plan = @(@('agl50', 'L_HFP_agl50', $StillFrames), @('agl200', 'L_HFP_agl200', $StillFrames), @('agl500', 'L_HFP_agl500', $StillFrames),
          @('flight', 'L_HF_Flight', ($V.flight.frames + 40)))
$base = @('empty', 'forest') + $(if ($MixRev) { @('mix') } else { @() }) + @($ExtraRevs | ForEach-Object { "x$_" })
for ($r = 1; $r -le $Rounds; $r++) {
    foreach ($p in @($plan | Where-Object { $Views -contains $_[0] })) {
        $conds = [string[]]$base.Clone()
        if ($r % 2 -eq 0) { [array]::Reverse($conds) }
        foreach ($c in $conds) {
            if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw 'An UnrealEditor process is already running' }
            $level = if ($c -eq 'mix') { "$MixRev/$($p[1])_forest" } elseif ($c -like 'x*') { "$($c.Substring(1))/$($p[1])_forest" } else { "$Rev/$($p[1])_$c" }
            $out = Join-Path $RepoRoot "unreal\TreeLookdev\Saved\TreeLookdev\hillside\perf\${Prefix}r${r}__${Rev}__$($p[0])__$c"
            if (Test-Path -LiteralPath $out) { throw "Refusing to overwrite prior run: $out" }
            New-Item -ItemType Directory -Path $out | Out-Null
            $log = Join-Path $out 'engine.log'
            $a = @("`"$project`"", "/Game/HillsideForest/$level", '-game', '-windowed', '-ResX=1920', '-ResY=1080', '-nosound', '-nosplash', '-unattended',
                '-benchmark', '-fps=60', "-ExecCmds=`"$exec`"", "-csvCaptureFrames=$($p[2])", '-ExitAfterCsvProfiling', "-abslog=`"$log`"")
            $proc = Start-Process -FilePath $exe -ArgumentList $a -WindowStyle Hidden -Wait -PassThru
            $m = [regex]::Matches((Get-Content -LiteralPath $log -Raw), 'Capture Ended\. Writing CSV to file : ([^\r\n]+)')
            if ($m.Count -ne 1) { Write-Host "FAIL: no CSV ($out)"; continue }
            Copy-Item -LiteralPath ([IO.Path]::GetFullPath((Join-Path (Split-Path $exe) $m[0].Groups[1].Value.Trim()))) -Destination (Join-Path $out 'profile.csv')
            Write-Host "HF_PERF_OK $level r$r exit=$($proc.ExitCode)"
        }
    }
}
