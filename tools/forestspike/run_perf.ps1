# ForestSpike B0: one standalone-game perf run of a saved perf level under the CSV profiler.
#   run_perf.ps1 -Level L_FSP_A_S1_v1_agl200_p10 -Tag r1 [-Frames 480]
# -game (no editor viewport / UI), fixed 60 fps timeline (-benchmark -fps=60: deterministic sequence frames, frame
# times are real), vsync off, 1920x1080 windowed, screen percentage 100. Output CSV is copied to
# unreal/ForestSpike/Saved/ForestSpike/perf/<Tag>__<Level>.csv together with a small metadata json.
# Frame times are for THIS host only (see the GPU line in the metadata); they are not a platform budget.
param(
    [Parameter(Mandatory)][string]$Level,
    [Parameter(Mandatory)][string]$Tag,
    [int]$Frames = 480,
    [switch]$Shot,          # also request one HighResShot (view check: proves the CameraActor / sequence drives the player view)
    [string]$EngineRoot = "C:\Program Files\Epic Games\UE_5.8"
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Project = Join-Path $RepoRoot "unreal\ForestSpike\ForestSpike.uproject"
$Saved = Join-Path $RepoRoot "unreal\ForestSpike\Saved"
$PerfOut = Join-Path $Saved "ForestSpike\perf"
$Logs = Join-Path $Saved "ForestSpike\logs"
New-Item -ItemType Directory -Force -Path $PerfOut, $Logs | Out-Null
for ($w = 0; $w -lt 30 -and (Get-Process UnrealEditor* -ErrorAction SilentlyContinue); $w++) { Start-Sleep -Seconds 2 }
if (Get-Process UnrealEditor* -ErrorAction SilentlyContinue) { throw "an UnrealEditor process is already running" }
$csvDir = Join-Path $env:LOCALAPPDATA "UnrealEngine\5.8\Saved\Profiling\CSV"   # UE 5.8 writes the boot-time CSV here for an uproject game run
$before = @(Get-ChildItem $csvDir -Filter *.csv -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
$exe = Join-Path $EngineRoot "Engine\Binaries\Win64\UnrealEditor.exe"
$log = Join-Path $Logs "perf_${Tag}__$Level.log"
$mapPath = "/Game/ForestSpike/Perf/$Level"
$exec = "r.VSync 0,t.MaxFPS 0,r.ScreenPercentage 100,r.MotionBlurQuality 0,r.RayTracing 0"
if ($Shot) { $exec += ",HighResShot 1920x1080" }
$argList = @($Project, $mapPath, "-game", "-windowed", "-ResX=1920", "-ResY=1080", "-nosound", "-nosplash", "-unattended",
    "-benchmark", "-fps=60", "-ExecCmds=`"$exec`"", "-csvCaptureFrames=$Frames", "-ExitAfterCsvProfiling",
    "-csvMetadata=`"tag=$Tag;level=$Level`"", "-abslog=$log")
$started = Get-Date
$proc = Start-Process -FilePath $exe -ArgumentList $argList -Wait -PassThru -NoNewWindow
$new = Get-ChildItem $csvDir -Filter *.csv -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.FullName } |
    Sort-Object LastWriteTime | Select-Object -Last 1
if (-not $new) { Write-Host "[$Tag $Level] FAIL: no CSV written (exit $($proc.ExitCode)); see $log"; exit 2 }
$dest = Join-Path $PerfOut ("{0}__{1}.csv" -f $Tag, $Level)
Copy-Item -Force $new.FullName $dest
$gpu = (Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)
@{ tag = $Tag; level = $Level; frames = $Frames; started = $started.ToString("s"); seconds = ((Get-Date) - $started).TotalSeconds
   exit_code = $proc.ExitCode; csv = $dest; gpu = $gpu; resolution = "1920x1080"; screen_percentage = 100 } |
    ConvertTo-Json | Set-Content -Encoding utf8 ($dest -replace "\.csv$", ".json")
Write-Host ("[{0} {1}] ok exit={2} csv={3}" -f $Tag, $Level, $proc.ExitCode, $dest)
