# ForestSpike B0 preflight — result (Issue #19, Phase B0)

> **2026-10-13 correction: B1a NO-GO.** Read
> [`forestspike-b0-integrity-correction.md`](forestspike-b0-integrity-correction.md) first.
> The original timing numbers and evidence below are preserved, but the six historical
> "moving" CSVs actually show a stationary camera at V3 t14; both saved sequences have
> unresolved camera bindings. All four B meshes' three render LOD counts and all 14 source
> hashes now match PR #18, while expected standalone LOD selection remains incomplete.
> The conditional GO and moving-path interpretation below are superseded. The revised
> CSV/completion validator passed a new static test; B1a/B1b/B2 remain stopped.

Branch `spike/ac7-forest-b0-preflight`, base `feat/opus55-xinyi-visual-quality` @ `ede7960d8ec05b2aa521b1e4c65b5bbd667c456d`.
Scope: harness + measurement-method preflight only. **Not** the 24-configuration sweep, not B1a/B1b/B2, no Northern-Taiwan
forest, no change to the Xinyi scene, accepted geometry, PR #18 or PR #20. No PR was merged. Research findings that belong
in the Phase A document are in the separate research branch (PR #20), not here.

## 1. Verdict

| Item | Status |
|---|---|
| Isolated UE 5.8 project / harness runs on this host | **PASS** |
| 1 km core + 6 km shared context, deterministic, reproducible from one seed | **PASS** |
| ID + slant-range debug pass (core/context, forest/open, tree arm, distance) | **PASS** (exact codes; range matches analytic ray cast, median error 0.00 m) |
| Observable N -> S switch in real test cameras | **PASS** (sheet in section 6) |
| Top-down canopy coverage measured in Unreal; coverage-matching method | **PASS** (70 % target hit within 0.4 points for arm A and B) |
| Core/context pixel-origin gate and frozen `d_S` / `w_S` | **PASS with a hard limitation** (section 5): one `d_S` cannot serve all four altitudes |
| CPU/GPU frame-time workflow (standalone game, CSV profiler, interleaved A/B) | **PASS as a workflow**; **no A/B difference resolved** (section 7) |
| Authored LOD import for arm B (`import_lod` of PR #18 LOD1/LOD2 GLBs) | **PARTIAL**: engine reports 3 LODs per archetype; per-LOD triangle counts **NOT VERIFIED** |
| F9 (pop) / F10 (seam) / F11 (temporal) rubric scores | **NOT MEASURED** (only observability was a B0 goal) |
| VRAM / texture memory / triangle counts per configuration | **NOT MEASURED** |
| PS5, PC discrete GPU, phone | **NOT MEASURED** (this host only) |
| Cold streaming beyond the boot window, packaged build | **NOT MEASURED** |

**B1a: GO, with the conditions in section 9.** On this host B1a can resolve only large effects; it cannot rank arms whose true
difference is below roughly 1 ms (static) or 4-12 ms (moving).

## 2. Environment (as read from the engine log, not assumed)

- UE 5.8.0, changelist 55116800, project `unreal/ForestSpike` (standalone; Python plugin only).
- RHI D3D12 at feature level **SM5** (adapter supports 12_1 / SM 6.7, **atomic64 unsupported**, so no virtual shadow maps / Nanite).
- GPU **Intel UHD Graphics 770**, 128 MB dedicated + ~8 GB shared system memory, UMA, driver 31.0.101.4502 (2023-06-15).
- CPU i7-12700 (12C/20T), 15.6 GB RAM, Windows 11. The iGPU shares package power with the CPU: **every timing here is "UHD 770 only"**.
- Renderer pinned in `unreal/ForestSpike/Config/DefaultEngine.ini` (no GI/reflection methods, cascaded shadow maps, manual exposure,
  no bloom/motion blur/AO); lighting rig copied from the accepted XinyiLook "day" calibration (`adapters/unreal/forestspike/fs_rig.py`).
- Accepted Xinyi assets, maps, shaders, `/Game/XinyiLook`, PR #18 and the working-tree of other branches were not touched.
  PR #18's 14 GLBs were **copied** to `assets/forestspike/b0/models/`; all 14 SHA-256 equal PR #18's own manifest
  (`pr18_manifest.json`, baseline `e05a959`).

## 3. Test world (synthetic fixture, not Taipei terrain)

`tools/forestspike/fs_world.py` (closed-form terrain and forest field, seed 20261012) -> `build_inputs.py`:

| Item | Value |
|---|---|
| Core / context | 1 km x 1 km core, 6 km x 6 km context; terrain meshes 81,600 / 177,800 triangles (identical in every configuration) |
| Core terrain | relief 130 m, mean slope 12.8 deg, p90 20.9 deg, forest fraction 74.9 % (road, power corridor, clearings carve it) |
| Field textures | 512^2 core (1.95 m/texel), 1024^2 context (5.86 m/texel); texture-to-world alignment verified (section 4) |
| Instance pool | 95,401 candidates in the core forest mask, fixed random priority rank (run of n = first n; nested) |
| Meshes | arm A = 28-triangle Xinyi reference (`xinyi_reference_preview_lod0.glb`, engine auto LOD 50 %/25 %); arm B = four PR #18 archetypes (mix 40/20/20/20), LOD0 + imported LOD1/LOD2 |
| Materials | one Custom-node HLSL file (`shaders/fs_forest.hlsl`); trees share one opaque vertex-colour material for both arms; far canopy layer **S** and understory **U** are material parameters |

## 4. Debug / measurement methods validated

**ID + slant-range pass** (`fs_capture.py`, `fs_ids.py`): unlit emissive code per pixel, R = class x 40, G/B = range x 7 (16 bit).
Calibration finding: with post-processing off, `SCS_FINAL_COLOR_LDR` writes the linear value straight into the 8-bit target, so the
encoder must **not** apply an sRGB curve (`id_gamma = 0`). Result: 100 % of pixels carry an exact class code. Range was compared with
an independent analytic ray cast on a 10-pixel grid at two viewpoints: median error **0.002 m / 0.000 m**, p5/p95 about +-0.6 m
(silhouette outliers up to 567 m exist at grazing horizon pixels). This also confirms camera pose and the 91.5 deg horizontal / 60 deg
vertical field of view. Sky pixels match the analytic "no hit" exactly.

**Top-down coverage** (orthographic ID capture, 2048^2, camera 1,000 m above; a camera at 3,000 m rendered nothing, the ortho far
plane): forest-mask alignment is exact (instance + visible forest-ground pixels = 99.8 % of the analytic mask pixels).
Coverage = tree pixels inside the mask / mask pixels. Compared with two geometric models:

| arm | n | measured | ellipse model | Poisson model |
|---|---:|---:|---:|---:|
| A | 8,000 / 16,000 / 26,000 / 40,000 / 60,000 | 25.1 / 44.9 / 63.6 / 80.8 / 93.7 % | 25.7 / 45.8 / 64.6 / 81.6 / 94.2 % | 25.3 / 44.1 / 61.2 / 76.7 / 88.7 % |
| B | 8,000 / 16,000 / 26,000 / 40,000 / 60,000 | 25.7 / 45.7 / 64.1 / 80.5 / 92.9 % | 32.7 / 55.9 / 74.8 / 89.1 / 97.4 % | 32.5 / 54.4 / 72.1 / 86.0 / 94.7 % |

The PR #18 archetypes fill their bounding ellipses only about 80 %, so a geometric formula over-predicts arm B by up to 10 points
(the earlier Phase A figure of "~68 %" for the *old* hill-forest clumps was likewise a model estimate). Coverage must be measured.
Procedure used: measure a curve, interpolate -ln(1 - cover) to the target, **verify with a fresh capture**:
**A: 30,200 trees -> 69.60 %; B: 30,100 trees -> 69.77 %** (target 70 %). Tree pixels outside the mask (crown overhang): 16,887 / 20,045 px of 4.19 M.
Counts and curve: `data/coverage_curve.json`, `data/calibration.json`.

## 5. Core / context pixel-origin gate (answers review 5493961033)

Rendering of all instances without cull; classification for any candidate `(d_S, w_S)` is done offline from the range channel
(`analyze_ids.py`). Shares are fractions of the **forest pixels** in the frame. 103 registered poses, 62 + 49 ID passes (arm A; arm B at the V1 stills,
and the arm-A and arm-B tree-pixel shares at the V1 stills differ by at most 0.04).

`d_S` / `w_S` = 500 / 100 m, arm A (`tools/forestspike/gate_markdown.py`; column N = core trees + core forest ground nearer than d_S - w_S,
T = core forest in the fade band, S core = core forest beyond d_S with instances culled, S surround = shared context forest):

| viewpoint | forest % of screen | core share | N | T | S core | S surround |
|---|---:|---:|---:|---:|---:|---:|
| agl50_p15 | 73 | 0.97 | 0.96 | 0.01 | 0.01 | 0.03 |
| agl50_p5 | 60 | 0.97 | 0.95 | 0.01 | 0.01 | 0.03 |
| agl200_p10 | 55 | 0.66 | 0.42 | 0.09 | 0.15 | 0.34 |
| agl200_p25 | 78 | 0.74 | 0.56 | 0.06 | 0.11 | 0.26 |
| agl500_p15 | 51 | 0.31 | 0.00 | 0.00 | 0.31 | 0.69 |
| agl500_p35 | 77 | 0.44 | 0.00 | 0.02 | 0.42 | 0.56 |
| agl1000_p20 | 48 | 0.07 | 0.00 | 0.00 | 0.07 | 0.93 |
| agl1000_p45 | 75 | 0.23 | 0.00 | 0.00 | 0.23 | 0.77 |

| pass (500/100) | frames | core share | N | T | S core | frames with N >= 10 % |
|---|---:|---|---|---|---|---:|
| V3 inbound dolly (200 m AGL, 30 m/s, 1,414 m to the centre) | 25 | 0.07-0.69 | 0.00-0.47 | 0.00-0.17 | 0.07-0.19 | 10/25 |
| V5 inward orbit 200 m (r = 330 m, looking at the centre) | 12 | 0.46-0.68 | 0.13-0.50 | 0.05-0.16 | 0.09-0.24 | 12/12 |
| V5 inward orbit 500 m | 12 | 0.44-0.57 | 0.00 | 0.00-0.04 | 0.44-0.55 | 0/12 |

**Findings (the reviewer's identifiability concern is confirmed by measurement):**

1. At 1,000 m AGL only 7-23 % of forest pixels come from the variable core; 77-93 % are the shared surround. At 500 m the core supplies 31-44 %
   and **no tree instance is ever inside `d_S`**. A single `d_S` makes the arm-specific geometry (N) invisible at 500/1,000 m, while at 50 m the
   ring is barely visible (S + T <= 2 % of forest pixels).
2. The first V3/V5 poses were registered before this check and looked mostly outside the core (V5 tangent: core share 10-37 %, N at most 0.21 at 200 m and 0 at 500 m for d_S = 500;
   V3 outbound: core share 0 after 36 s). They were **replaced** by an inbound V3 and an inward-looking V5 (same yaw rate: 26 deg/s at 150 m/s, r = 330 m);
   the original poses remain in `viewpoints.json` as groups `V3o` / `V5t`. The replacement was made after seeing this data; it is a design correction, not a blind pre-registration.
3. Pre-registered rule, **written after the first candidate table was seen** (so it is a transparent selection rule, not a blind pre-registration):
   (i) >= 8 V3 frames with T >= 5 %; (ii) V3 has frames with N >= 40 % and frames with core-S >= 10 %; (iii) V1 agl200_p10 has N, T, S each >= 5 %.
   Candidates 200/40 ... 1200/240: only **500/100 and 600/120 pass**; 400/80 fails (ii, max N 0.34); 800/160 fails (i, 3/25 frames). Smallest passing = **`d_S` = 500 m, `w_S` = 100 m (frozen for B1a)**.
4. Consequence for design, as the review allowed ("split the experiments by viewpoint"): at the frozen ring, **N (A vs B) is identifiable only at 50 m and 200 m
   viewpoints, the inbound V3 and the inward V5 at 200 m**. 500 m and 1,000 m viewpoints test the far layer S and the shared context only; arms A and B render identical
   pixels there (all instances are beyond `d_S`), so any timing difference there is bookkeeping, not rendering. F9/F10 may only be claimed where in-core transition
   pixels exist (T >= 5 %): V3 inbound frames t = 14-48 s and V5 inward 200 m.

Full tables: `data/gate_table.json`, `data/gate2_table.json`; maps: `docs/evidence/forestspike-b0/origin_map_v1.jpg`.

## 6. Visual evidence (all frames are this harness's own renders)

- `docs/evidence/forestspike-b0/ring_switch_sheet.jpg`: V3 inbound frames at t = 14/18/22/30 s, S off / S on / pixel-origin map (green N, yellow fade band, red core S, blue shared S).
  The switch ring is visible in the S-on row where instanced crowns end and the canopy layer begins.
- `arms_s_sheet.jpg`: arms A and B x S off/on at agl50_p15, agl200_p10, agl500_p35, agl1000_p45 (d_S 500 / w_S 100, 70 % cover).
- `origin_map_v1.jpg`: pixel-origin maps at the eight V1 stills; `native_crop_agl200_A_S1.png`: unchanged native 640 x 360 pixels.
- Standalone-game check: a game-mode `HighResShot` showed the same composition as the SceneCapture frame (camera actor drives the view). It was taken in the first frames, so
  materials were still the grey default while shaders compiled; this proves the view, not the look, and is why the first 120 frames are treated as cold.

Visual observations that B1 should keep in mind (not B0 failures): the far canopy layer S is darker and blurrier than the instanced crowns, so the hand-over band is visible;
the shared context S looks smeared at very close range (camera beside the context terrain); with S off and understory off the forest is plain green "felt", as in the Xinyi baseline;
the egg-carton look of the synthetic terrain is an artefact of the plane-wave height function.
Default in these captures: understory **U off** (a single fixed state across S, so S is an independent factor).

## 7. Performance workflow and results (UHD 770 only)

Method: `-game` standalone process (no editor viewport), 1920 x 1080 windowed, screen percentage 100, vsync off, `-benchmark -fps=60` (fixed 60 fps timeline, so the
Level-Sequence camera is frame-deterministic while frame times stay real), UE CSV profiler (`FrameTime`, `GameThreadTime`, `RenderThreadTime`, `RHIThreadTime`, `GPUTime`).
Frames 0-119 = cold/boot window (the CSV is a boot-time capture; one frame of 65-88 s is level load + shader compile, reported separately); frames >= 120 = warmed window.
Configs: arm A vs arm B, S on, d_S 500 / w_S 100, 70 % coverage (30,200 / 30,100 trees). Static = locked pose v1_agl200_p10 (480 frames, 360 warmed);
moving = 18 s of the V3 inbound path, 10 poses, linear (900 frames, 780 warmed). Three rounds, **order alternated** (A,B / B,A / A,B). Analysis: `analyze_perf.py`, `analyze_perf_pairs.py`.
All 12 runs completed with a CSV and receipt (one extra earlier A-only static run, `static_r1`, GPU median 30.89 ms, is excluded from the pairs).

**Static pose (warmed GPU time, ms)**

| round (order) | A median / p95 | B median / p95 | B - A median | B - A p95 |
|---|---|---|---:|---:|
| 1 (A,B) | 31.65 / 34.68 | 30.86 / 34.64 | -0.79 | -0.04 |
| 2 (B,A) | 30.96 / 33.80 | 31.03 / 36.40 | +0.07 | +2.60 |
| 3 (A,B) | 32.02 / 36.02 | 30.77 / 35.79 | -1.25 | -0.23 |

Paired mean B - A: -0.66 ms (median), signs inconsistent. The **same configuration** moved by 1.06 ms (A) and 0.26 ms (B) between rounds. Frame time (median) A 33.5 / 32.8 / 33.8, B 32.6 / 32.9 / 32.6; CPU game thread 2.7-2.9 ms in both arms (not the limit); median draw calls ~56.
**Conclusion: no A/B difference is resolved at this pose.** The host is GPU-bound at about 31 ms either way. A single 30.9 ms run says nothing about A vs B.

**Moving path (warmed GPU time, ms)**

| round (order) | A median / p95 | B median / p95 | B - A median | B - A p95 |
|---|---|---|---:|---:|
| 1 (A,B) | 29.84 / 32.51 | 30.17 / 34.87 | +0.33 | +2.36 |
| 2 (B,A) | 33.76 / 39.53 | 42.23 / 45.10 | +8.47 | +5.57 |
| 3 (A,B) | 32.01 / 38.64 | 29.74 / 33.68 | -2.27 | -4.96 |

The paired deltas span -2.3 to +8.5 ms with inconsistent sign; the same configuration moved by 3.9 ms (A) and **12.5 ms (B)** between rounds (round 2, B ran with a 42 ms median; cause not diagnosed, consistent with the known iGPU/CPU shared-power drift but not proven).
A also had a 115 ms single-frame hitch (game thread 85 ms) in round 3. **No A/B conclusion can be drawn for the moving path; the host's noise floor (>= 4-12 ms) exceeds any plausible effect.**
Per-run numbers (cold vs warm, median/p95/p99/max for all five metrics): `data/perf_summary_all.json`, `data/pairs_pst.json`, `data/pairs_ppa.json`. CSV files (13 x ~1.2 MB) are not committed; they regenerate with the commands below.

## 8. Defects / limitations found while building (all disclosed)

- `UnrealEditor` often exits with an access violation at shutdown **after** the script finished. The runner therefore checks a fresh receipt file with status `PASS_*`, not the exit code. A first perf schedule aborted for this reason (stale `$LASTEXITCODE`); it was fixed (`exit 0`) and the whole schedule re-run.
- `-ExecutePythonScript` is not available in `-game`; frame timing therefore uses saved levels + Level Sequence + CSV, not scripted cameras.
- A first capture-spec run silently failed because of a wrong environment path and its old frames were briefly mistaken for new ones; caught by checking sidecar metadata, receipt checking was added.
- The ID transfer curve (sRGB vs linear) was wrong in the first draft and was found by decoding the first captures (`id_gamma` 0).
- Authored LOD import for arm B returned LOD indices 1/2 and the engine reports 3 LODs; **per-LOD triangle counts were not read back**, so "authored LODs preserved" is not yet proven.
- One 0-byte file with a comment fragment as its name was created in the repo root by a failed shell command; it was confirmed empty and untracked and deleted.
- Terrain is a synthetic analytic fixture; the field-texture resolution at the core is 1.95 m, fine for the 70 % cover metric but not for sub-crown detail.

## 9. B1a Go / No-Go

**GO**, conditions:

1. Freeze `d_S` = 500 m, `w_S` = 100 m, U off, d_S identical for all N (instances end-cull at `d_S` whether S is on or off), counts 30,200 (A) / 30,100 (B).
2. Compare N (A vs B) **only** at agl50 (p5, p15), agl200 (p10, p25), V3 inbound frames t = 14-48 s and V5 inward 200 m. At agl500 / agl1000 / V5 inward 500 m report only the S effect (S off vs on); do not present A-vs-B there.
3. Before the 4 configurations, verify the arm-B authored LOD triangle counts (per LOD, per archetype) and stop if they do not equal PR #18's manifest.
4. Timing: require >= 5 interleaved rounds per config pair, report paired deltas, treat anything below ~1 ms (static) as not resolved; do **not** use the 18 s moving path on this iGPU for ranking (noise floor 4-12 ms). Prefer more short static poses plus ID-pass image metrics; move ranking to a named discrete-GPU host before any platform statement.
5. F9/F10/F11 only where the ID map shows in-core transition pixels; no claim of parity with AC7.

## 10. Reproduction (project venv `D:\Users\EDDY\.venvs\acw-xinyi`; UE at `C:\Program Files\Epic Games\UE_5.8`)

```powershell
python tools/forestspike/build_inputs.py            # terrain, fields, pool, bounds, PR #18 hash check
python tools/forestspike/viewpoints.py
powershell -File tools/forestspike/run_stage.ps1 -Script fs_build_assets.py -Name assets -Expect fs_assets.report.json
powershell -File tools/forestspike/run_stage.ps1 -Script fs_build_level.py  -Name level  -Expect fs_level.report.json
python tools/forestspike/make_spec.py coverage; powershell -File tools/forestspike/run_capture.ps1 -Set coverage
python tools/forestspike/analyze_coverage.py --out unreal/ForestSpike/Saved/ForestSpike/reports/coverage_curve.json
python tools/forestspike/make_spec.py gate; python tools/forestspike/make_spec.py gate2   # + run_capture.ps1 for each
python tools/forestspike/analyze_ids.py --set gate ; python tools/forestspike/analyze_ids.py --set gate2 --out .../gate2_table.json
python tools/forestspike/gate_markdown.py ; python tools/forestspike/make_sheets.py
python tools/forestspike/make_perf.py pilot; powershell -File tools/forestspike/run_stage.ps1 -Script fs_build_perf_levels.py -Name perf_levels -Expect fs_perf_levels.report.json
powershell -File tools/forestspike/run_perf_schedule.ps1 -Levels L_FSP_A_S1_v1_agl200_p10,L_FSP_B_S1_v1_agl200_p10 -Rounds 3 -Frames 480 -Prefix pst
python tools/forestspike/analyze_perf_pairs.py --prefix pst
```

Generated content (`unreal/ForestSpike/Content`, `Saved`) is git-ignored; scripts, small data and evidence are committed.
