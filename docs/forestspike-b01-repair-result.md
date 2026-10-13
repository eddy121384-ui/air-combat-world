# ForestSpike B0.1 repair — 2026-10-13

**The two B0.1 repair gates pass within the evidence scope below. Stop for review; B1a is not started or authorized by this result. PR #24 remains Draft.**

Addresses review [5497750104](https://github.com/eddy121384-ui/air-combat-world/pull/24#pullrequestreview-5497750104).
Work started on `spike/ac7-forest-b0-preflight` at full HEAD
`d7fa5f87703ecec0dacf701c60a92976172fce58`, confirmed locally and remotely.
The existing Windows project and worktrees were inventoried before mutation. UE is
5.8.0 CL55116800, D3D12 SM5, i7-12700 / Intel UHD Graphics 770, driver 31.0.101.4502.
All performance data is **Intel UHD 770 only**. Moving GPU data is diagnostic and is not ranked.

| Gate | B0.1 result | Practical limit |
|---|---|---|
| Saved camera binding survives process close/reopen | PASS, both new A/B maps | Original broken maps remain unchanged |
| 120-frame warm hold + complete V3 flight | PASS, one successful smoke per arm | 18 seconds of fixed-step sequence time; no 60fps real-time claim |
| Per-frame position, forward/up, travel and endpoint | PASS, both 1,264-row CSVs | Smoke integrity, not five-round performance or temporal visual acceptance |
| Exact world/tag/ID/frames/columns/finalized output | PASS, both smokes, observed exit 0 | CSV completion and motion are separate gates |
| Common automatic LOD policy + 50m/200m selection | PASS, controlled render gate | Native submitted counts plus color readback; not standalone per-instance visibility telemetry |
| HISM culling independently controlled | PASS, 450m/550m × cull on/off | Does not resolve material fade or the visible switch ring |
| Existing source/hash/count preservation | PASS | Original GLBs, maps and data retained; report addendum explicitly recorded |
| Permission to proceed to B1a | **WAIT FOR REVIEW** | No B1a branch, sweep, B1b, B2, production change or merge |

## Durable moving fixture and actual CSV motion

New final fixtures are `/Game/ForestSpike/B01_20261013d/Perf/L_FSP_B01_20261013d_{A,B}_V3`
and their `LS_` sequences. Their meshes reference new policy copies under
`/Game/ForestSpike/B01_20261013c/Meshes/`; none of the original meshes is edited.
The failed/intermediate `a`, `b`, `c` namespaces also remain locally.

The construction error is now reproducible: `EditorLoadingAndSavingUtils.save_map(world, new_path)`
writes a Save-As copy but leaves the template world active. Binding its camera still records
the template package. The repair saves the new copy, explicitly **loads the new map**, checks
its world path, reacquires its camera, creates possessable/camera-cut bindings, and saves only
the new current level. A separate Unreal process then loads both maps and uses
`MovieSceneSequenceExtensions.locate_bound_objects` to verify the exact camera object before
and after full process close/reopen. Each resolves one expected object; each actor references
the intended new sequence. Final build/reopen and both successful game-mode runs exit 0.

The 60Hz sequence holds the initial V3 t14 pose through frame 120, follows all ten registered
t14…t32 poses over 1,080 intervals, then holds the endpoint through playback end 1,261.
`FORCE_KEEP_STATE` prevents reverting to the start when playback completes. This matters:
the first new A smoke moved correctly but reverted to its initial pose in the last three CSV
rows. Its timing CSV passed integrity, while the motion gate correctly **failed**. It was
preserved, and the repair uses new `d` maps rather than overwriting the `c` fixtures.

| Successful smoke | A `b01_A_smoke02` | B `b01_B_smoke01` |
|---|---:|---:|
| CSV frames / invalid boot rows | 1,264 / 1 | 1,264 / 1 |
| First 120 valid world-view samples | CSV 1–120, stationary | CSV 1–120, stationary |
| Maximum warm displacement | 0.000008m | 0.000008m |
| Flight sample range, inclusive | CSV 120–1200 | CSV 120–1200 |
| Flight samples / intervals | 1,081 / 1,080 | 1,081 / 1,080 |
| Verified path times | t14 to t32, 18.0s | t14 to t32, 18.0s |
| Measured / registered travel | 546.787541 / 546.787531m | 546.787541 / 546.787531m |
| Nonmonotonic inbound steps | 0 | 0 |
| Maximum position error | 0.000099m | 0.000099m |
| Maximum forward / up error | 0.003222° / 0.001051° | 0.003222° / 0.001051° |
| Endpoint error / following hold samples | 0.000020m / 63 | 0.000020m / 63 |
| CSV completion + motion / exit | PASS + PASS / 0 | PASS + PASS / 0 |

CSV frame 120 is the **shared boundary sample**: the last stationary warm observation and the
flight's t14 endpoint. The next 1,080 intervals contain the entire flight. The first boot row
is explicitly invalid and excluded. The registered allowable startup phase is only 0 or 1
sequence frame; both successful runs read phase 1. No arbitrary speed/offset fitting is used.
18.0s refers to fixed-step animation time, not wall-clock execution duration or achieved frame rate.
The timing validator's generic cold window is not used to define the flight interval.

The published successful per-frame traces include position, forward/up vectors, segment/time labels,
per-frame position/angular errors, step distance and cumulative flight distance. Exact CSV
names, hashes, metadata and completion receipts link each trace back to its raw engine CSV.
Both successful CSVs pass the original fail-closed capture validator with an explicit isolated
world path. Its old default path behavior is unchanged.

Evidence: [fresh reopen](evidence/forestspike-b01/runs/b01_reopen_d/receipt.json),
[A motion](evidence/forestspike-b01/runs/b01_A_smoke02/motion.json),
[A trace](evidence/forestspike-b01/runs/b01_A_smoke02/camera_trace.csv),
[B motion](evidence/forestspike-b01/runs/b01_B_smoke01/motion.json),
[B trace](evidence/forestspike-b01/runs/b01_B_smoke01/camera_trace.csv),
[retained failed A motion](evidence/forestspike-b01/runs/b01_A_smoke01/motion.json),
[offline final-validator recheck of the same three CSVs](evidence/forestspike-b01/final_motion_recheck.json).

**All six historical 900-row “moving” captures remain stationary/historical.** Their old timing
numbers are unchanged, and no flight, shimmer, motion-variance or geometry-complexity conclusion
is restored from those runs. B0.1 has three smoke attempts: one failed A, then one successful B
and one successful A. There is no five-round sweep or new CPU/GPU A/B ranking.

## Automatic LOD policy, actual render choice and culling

A's old builder explicitly requested screen thresholds `1.0 / 0.12 / 0.04`, disabling automatic
screen computation. B imported authored LODs without an explicit screen policy. The installed
UE5.8 `StaticMesh.cpp` sets auto LOD0 screen size to 2.0 and, when `MaxDeviation <= 0`, later
screens to `pow(0.75, LODIndex)`: precisely B's observed `2.0 / 0.75 / 0.5625`.
This is an engine-code explanation consistent with the import path and readback; private
`MaxDeviation` itself is not independently exposed by Python. These are screen-size
thresholds, not meters. They made old B 200m views overwhelmingly LOD2, invalidating a
simple “28 triangles versus 100–120 triangles” explanation of the old timing difference.

The common proposed B1a policy was registered **before the smokes and LOD render trials**:
`1.0 / 0.08 / 0.03`, automatic selection (`foliage.ForceLOD=-1`, `r.ForceLOD=-1`, component
forced model 0), all LOD/distance scales 1, random LOD range 0, cull 500m. These screen
thresholds are unchanged across registrations `a` through `d`; later registrations repair
map construction and completion behavior, not policy or motion tolerances. A uses its actual
28/28/28 geometry; B retains dense 120/36/20, tiered 112/38/20, vase 102/40/20 and columnar
108/38/20. Fresh reopen reads back every copied mesh's thresholds, counts and debug slots.

At this 91.4928° horizontal / 60° vertical FOV, an isolated unit-scale sphere's approximate
normalized projected diameter is `sqrt(3) * R / distance`. Thus the rule retains LOD0 above
8%, LOD1 from 3–8%, and LOD2 below 3%, subject to normal HISM traversal and culling.
It preserves meaningful authored tiers at 50m and 200m without assuming altitude determines
LOD. HISM uses all-LOD render bounds, cluster root scale and cluster near/far bounds;
the formula is a transition bracket, not a promise of an exact per-instance cutoff.

The diagnostic copies assign red/green/blue unlit materials to LOD0/1/2 sections, preserving
geometry and policy. Probes change components only in memory and never save the original map or assets. Native `foliage.RebuildFoliageTrees` synchronously rebuilds clusters for
each case, and `foliage.LogFoliageFrame` records real automatic render submissions. Primary
`shadow:0` entries are separated from shadow cascades; each triangle count must equal its
submitted instance count × the read-back mesh LOD triangles. Native 1920×1080 PNG colors
independently show which LODs reached visible pixels. No forced LOD or frozen traversal is used.

| 500m normal cull view | Native submitted instances LOD0 / 1 / 2 | Submitted triangles LOD0 / 1 / 2 |
|---|---:|---:|
| A legacy, 50m | 354 / 1,532 / 4,012 | 9,912 / 42,896 / 112,336 |
| B legacy, 50m | 235 / 47 / 7,202 | 26,026 / 1,880 / 144,040 |
| A legacy, 200m | 0 / 294 / 4,601 | 0 / 8,232 / 128,828 |
| B legacy, 200m | 0 / 0 / 6,587 | 0 / 0 / 131,740 |
| A common policy, 50m | 708 / 2,417 / 2,773 | 19,824 / 67,676 / 77,644 |
| B common policy, 50m | 1,556 / 3,196 / 2,732 | 171,282 / 120,154 / 54,640 |
| A common policy, 200m | 0 / 1,414 / 3,481 | 0 / 39,592 / 97,468 |
| B common policy, 200m | 95 / 3,483 / 3,009 | 9,978 / 131,906 / 60,180 |

These are **submitted** instances/triangles in one primary diagnostic view, not unique visible
instance IDs, not pixel counts and not performance measurements. Occlusion can prevent a
submitted triangle from contributing pixels. B 200m's 95 submitted LOD0 instances contribute
only 1,378 red pixels; it is predominantly LOD1/2. Larger bounds, pooled scales and conservative
cluster selection mean “200m must contain no LOD0” would be an invalid acceptance assumption.
The full forest does not have an exact standalone per-instance LOD trace. The allowed
controlled-instance alternative is used with this confidence limit stated explicitly.

Final gate: **81 cases PASS** = 16 full-forest policy/legacy/altitude/cull cases, 25 unit-instance
80/240/480m cases at 50m/200m, 20 near/far boundary brackets, and 20 independent 450m/550m
cull controls. All five tree meshes select LOD0 at 80m, LOD1 at 240m and LOD2 at 480m in the
applicable unit controls. Each 0→1 and 1→2 boundary bracket selects the predicted tier.
At 450m all cull controls remain visible; at 550m normal cull removes them and cull-off
restores them, with automatic LOD still enabled. Forest cull-off adds distant LOD2 rather
than demonstrating a different near LOD policy.

The first two LOD batches are retained as **FAIL analyses**, despite complete PNG exports.
Batch 01 lacked native synchronous-build confirmation and had three boundary color mismatches.
Batch 02 confirmed native rebuild/draws but reproduced those three mismatches. Root cause:
`StaticMesh.get_bounds()` returns editor cached LOD0 bounds, whereas HISM reads an all-LOD
`RenderData.Bounds` union. Dense LOD1 radius is 515.560cm versus cached 481.253cm; vase LOD2
is 662.363cm versus cached 612.922cm. Source-derived all-LOD union math plus installed engine
code corrected **test placement**, not screen thresholds, tolerances or tree geometry.
Batch 03 repeats only all 20 boundary controls with that correction. The final analysis
explicitly combines batch 02's 61 non-boundary controls with batch 03's 20 boundary controls;
it does not rewrite or relabel the previous failed batches.

Batch 03 has a fresh complete 20-image receipt and normal final log closure, but the observed
process exit is `-1073741819`. Capture completeness, PNG hashes, native draw identity, fresh
timestamps and all independent selection checks pass; **shutdown health does not pass**.
This is disclosed separately, never inferred from merely finding output files. Both actual
game-mode motion smoke runs and the final fixture build/reopen exit normally.

Evidence: [registered final policy](../tools/forestspike/b01_registered_d.json),
[final 81-case native/color analysis](evidence/forestspike-b01/lod_analysis_release.json),
[failed batch 01](evidence/forestspike-b01/lod_analysis_01.json),
[failed batch 02](evidence/forestspike-b01/lod_analysis_02.json),
[source-derived bounds receipt](evidence/forestspike-b01/render_bounds.json),
[read-only installed-engine source references/hashes](evidence/forestspike-b01/engine_source_refs.json).

| Native diagnostic PNGs | 50m | 200m |
|---|---|---|
| A common policy | [LOD colors](evidence/forestspike-b01/native/forest_A_policy_v1_agl50_p15_cull500.png) | [LOD colors](evidence/forestspike-b01/native/forest_A_policy_v1_agl200_p10_cull500.png) |
| B common policy | [LOD colors](evidence/forestspike-b01/native/forest_B_policy_v1_agl50_p15_cull500.png) | [LOD colors](evidence/forestspike-b01/native/forest_B_policy_v1_agl200_p10_cull500.png) |

These images were visually inspected. They are ID diagnostics with terrain/AA/postprocessing
disabled, not final shaded forest quality comparisons or F9/F10/F11 visual acceptance.

## Retained attempts, preservation and validation

| Attempt | Outcome retained |
|---|---|
| build a | FAIL, missing receipt, UE exit 3; duplicating a UWorld left a standalone world that LoadLevel could not collect |
| build b | FAIL receipt, exit -1073741819; Save-As left old world active and later save collided with the new map |
| build c / reopen c | Completed receipts, abnormal exits -1073741819; subsequently rejected for final motion due to end restore |
| A smoke01 on c | CSV PASS / motion FAIL / combined FAIL, exit 0; end-of-sequence jump retained |
| build d / reopen d | PASS, exit 0; new maps keep endpoint state and reuse verified c mesh copies |
| B smoke01 / A smoke02 on d | PASS CSV + motion, exit 0; one successful smoke per arm |
| LOD01 / LOD02 | Complete 81-image captures, exit 0, but separate selection analyses FAIL |
| LOD03 | Complete 20-image capture, independent boundary selection PASS, abnormal process exit disclosed |
| Regression test addition | First new nonfinite-vector test exposed an exception-only receipt path; failed test log retained, final structured FAIL receipt fix passes |

[Stage outcomes](evidence/forestspike-b01/stage_outcomes.json) and per-stage requests/receipts/
filtered native logs preserve these distinctions. All raw engine logs, all three new CSVs,
all 182 diagnostic PNGs/sidecars and all intermediate assets remain in unique local folders.
[New local output manifest](evidence/forestspike-b01/new_local_outputs.json) records paths,
byte sizes and SHA-256. Public completion exports redact only `metadata.loginid`, explicitly
marked; raw local receipts and their hashes are retained.

Before and after reporting, all **540** inventoried pre-B0.1 artifact files match their baseline
hashes. Separately, the intentional report addendum to `forestspike-b0-integrity-correction.md`
retains its entire original byte content verbatim as its historical suffix and as a separate
snapshot. [The final check](evidence/forestspike-b01/preservation_final.json) records both scopes. No old timing number,
CSV, failure record, GLB, mesh or map is rewritten. Original PR #18 checkout and NTW worktree
HEADs remain unchanged; accepted Xinyi, whitebox and Northern Taiwan content is untouched.

Validation is **34 regression tests PASS** (27 capture-integrity + 7 motion), plus both new
PowerShell runners' syntax checks. A final offline recheck preserves failed/successful motion
classification on the same three raw CSVs; it is not another engine run. No broad city build
or unrelated test suite was run.

Reproduce only with **new Tags/namespaces/output filenames**. Build with `fs_b01_build.py`
and a new registration, then run `fs_b01_reopen.py` in a separate process. Use
`run_b01_smoke.ps1 -Arm A|B -Tag <new> -ReopenReceipt <fresh receipt> -Python <python>`.
LOD diagnostics use `fs_b01_lod_probe.py` through `run_b01_stage.ps1`, with registration,
build receipt and a newly generated `bounds_integrity.py` receipt passed via the environment.
The exact successful command/environment arguments are retained in each stage's `request.json`.
`analyze_b01_lods.py --base-dir <lod02> --dir <lod03> --out <new>` reproduces the explicit
61+20 composition, provided original fresh timestamps and raw log files remain available.

The known ground-S/HISM per-instance fade remains unfinished. A visible switch ring is a
defect: **F9/F10 are not PASS**. Actual camera motion now passes, but **F11 temporal shimmer
visual acceptance remains unmeasured**. This repair does not establish B1b readiness, AC7
visual parity or PS5/discrete-GPU/mobile performance. Stop on PR #24 for review.
