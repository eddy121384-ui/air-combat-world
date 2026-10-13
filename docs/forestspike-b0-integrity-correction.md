# ForestSpike B0 integrity — B0.1 repair update, 2026-10-13

**B0.1 repair gates PASS within the controlled evidence scope; stop for review. B1a remains on hold and PR #24 remains Draft.**

Latest response to review [5497750104](https://github.com/eddy121384-ui/air-combat-world/pull/24#pullrequestreview-5497750104):
[complete B0.1 repair report](forestspike-b01-repair-result.md).

| Current repair gate | Result |
|---|---|
| New A/B sequences survive save, process close and reopen | PASS; one exact camera binding per new fixture |
| Warm hold and real V3 motion | PASS; one successful smoke per arm, 120 stationary valid world views then all 1,080 flight intervals / 18s sequence time |
| Per-frame position/orientation/travel/endpoint plus capture integrity | PASS; 1,264 rows per smoke, 546.787541m travel, correct identities/finalized output, both exit 0 |
| Automatic LOD policy and 50m/200m choice | PASS for controlled native draw/color evidence; common 1.0/0.08/0.03 policy, no forced LOD; 81 independent controls |
| HISM culling separated from LOD selection | PASS; synchronous native tree rebuild, 450m/550m cull on/off controls |
| Preservation | All 540 inventoried artifact files unchanged; this separate report addendum retains the original bytes verbatim |
| B1a / visual acceptance / platform inference | WAIT FOR REVIEW; no B1a branch or sweep. Fade ring remains a defect; F9/F10 not PASS, F11 visual shimmer unmeasured. Intel UHD 770 only |

Evidence includes a retained CSV-PASS/motion-FAIL A attempt and two failed LOD analyses.
The corrected final 20-boundary LOD capture has complete fresh outputs but an abnormal
shutdown exit, disclosed separately; it is not marked as a healthy engine shutdown.
34 focused regression tests and both PowerShell syntax checks pass.
[Final preservation check](evidence/forestspike-b01/preservation_final.json) and
[all stage outcomes](evidence/forestspike-b01/stage_outcomes.json) are included.

The entire original d7fa5f8 report follows unchanged as historical evidence. Its old six
moving captures remain stationary/historical; no old timing numbers or failures are rewritten.

---

# ForestSpike B0 measurement-integrity correction — 2026-10-13

**B1a NO-GO. Stop after this B0 correction.** This addendum supersedes the conditional GO and
moving-path interpretation in `forestspike-b0-preflight-result.md` at `7d94d6e`.
The original CSVs, sidecars, summaries, maps, imported meshes and images are retained.
The old timing numbers have not been edited. No B1a branch, B1b, B2 or production integration was started.

Reviewed: Issue #19; Draft PR #24 and review [5497152466](https://github.com/eddy121384-ui/air-combat-world/pull/24#pullrequestreview-5497152466);
PR #20 at `2dcbf82683cd7e1cd60d584f065164eadedf8b54`; PR #18 at
`e05a959aa9b6a751e72def07c2781d4709dd2b67`; local `AGENTS.md`.

## Current gates

| Required gate | Result |
|---|---|
| Engine render-data triangles and PR #18 GLB hashes | **PASS** for counts/hashes; all four trees, all three LODs; all 14 GLBs |
| Expected LOD actually selected throughout the tested views/path | **PARTIAL / NOT VERIFIED**; 200m ID diagnostic agrees with forced LOD2, 50m remains unresolved; no standalone per-instance LOD trace |
| Real camera path and valid moving measurement interval | **FAIL**; both saved moving sequences resolve no camera; all six historical moving CSVs are stationary at V3 t14 |
| Hardened CSV/completion validation | **PASS for static capture integrity**; 25 regression tests plus one new UE5.8 480-frame run; incomplete first attempt retained as FAIL |
| Overall first stage / permission to begin B1a | **NOT PASSED / NO-GO** |

Host scope for every timing: **Intel UHD 770 only**. UE 5.8.0 CL 55116800, D3D12 SM5,
Intel UHD Graphics 770 / i7-12700. This correction makes no PS5, discrete-GPU PC or mobile claim.

## Environment and preservation

The existing working checkout is `D:\Users\EDDY\Documents\GitHub\air-combat-world`, branch
`spike/ac7-forest-b0-preflight`, confirmed clean at full HEAD
`7d94d6e0f96ecbd0f6e9572c7a5b32b4f7cc1bbc` before changes. Its separate NTW worktree was left alone.
The desktop checkout at `C:\Users\EDDY\Desktop\M1A2\air-combat-world` is the clean PR #18
checkout, used read-only as the original GLB/manifest reference.

The existing project `unreal/ForestSpike/ForestSpike.uproject`, generated `/Game/ForestSpike/`
assets, original 13 CSVs, sidecars, capture evidence and engine logs were found and reused.
No build-assets/build-level/perf-level regeneration was run. The readback and LOD probes load
existing maps and make transient changes only; they do not save assets or levels.

[`preserved_inventory.json`](evidence/forestspike-b0-integrity/preserved_inventory.json) records
paths, byte sizes and SHA-256 for the original perf files/logs, ForestSpike Content, reports and
committed B0 evidence. A final hash check confirms all 107 inventoried original files are unchanged;
all 91 per-run metric summaries (cold and warm windows) also match the original 13-run summary.
New raw outputs remain in unique local folders under `Saved/ForestSpike/`; the new-output manifest
records their paths/hashes. Public receipts omit only the host login identifier, explicitly marked;
raw receipts remain intact locally.

## 1. Actual imported LOD readback

`fs_verify_lods.py` calls UE5.8 `StaticMesh.get_num_lods()` and
`StaticMesh.get_num_triangles(lod)` on the existing imported meshes. These are render-data
counts, not GLB-only counts or `import_lod` return values. It also reads screen sizes,
vertices, reduction settings and import-data identity. The API semantics are documented by
[Epic](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/StaticMesh?application_version=5.7)
and confirmed in this host's UE5.8 `Engine/Classes/Engine/StaticMesh.h`.

| Existing mesh | Expected PR #18 LOD0/1/2 | Actual UE render LOD0/1/2 | Screen-size thresholds |
|---|---:|---:|---|
| Dense rounded | 120 / 36 / 20 | 120 / 36 / 20 | 2.0 / 0.75 / 0.5625 |
| Horizontal tiered | 112 / 38 / 20 | 112 / 38 / 20 | 2.0 / 0.75 / 0.5625 |
| Open vase | 102 / 40 / 20 | 102 / 40 / 20 | 2.0 / 0.75 / 0.5625 |
| Tall columnar | 108 / 38 / 20 | 108 / 38 / 20 | 2.0 / 0.75 / 0.5625 |
| A reference | 28 at LOD0 | 28 / 28 / 28 | 1.0 / 0.12 / 0.04 |

All 14 copied GLBs match both the preserved PR #18 manifest and the original PR #18 files.
The manifest also matches byte-for-byte. A's requested 50%/25% automatic reductions did **not**
reduce the read-back triangle counts. The old report's percentages describe requested settings,
not achieved counts. B has imported LODs but very different default screen thresholds from A.

Evidence: [`lod_readback_02.json`](evidence/forestspike-b0-integrity/lod_readback_02.json),
[`source_hashes_all14.json`](evidence/forestspike-b0-integrity/source_hashes_all14.json).
The private `source_models` property is not available through the Python API on this build;
persisted per-LOD source filenames are therefore not claimed independently verified.
Source hashes, import receipt and render counts are recorded as separate evidence.

### Selection probe and remaining limitation

Sixteen fresh 1920x1080 ID diagnostic renders compare automatic `foliage.ForceLOD=-1` with
forced LOD0/1/2 at 50m, 200m, V3 t18 and inward V5 200m. Every force setting was read back
from the console variable. Full-frame equality is invalid: forced LOD bypasses normal HISM
cluster culling and exposes additional distant trees. The comparison therefore reports both
full-frame differences and the automatic tree pixels with measured slant range <=350m,
inside the normal 500m cull.

| View | Auto tree pixels <=350m | Different vs forced LOD2 within that mask |
|---|---:|---:|
| V1 200m p10 | 346,545 | 0 |
| V3 t18 | 43,184 | 0 |
| V5 inward 200m a000 | 478,384 | 0 |
| V1 50m p15 | 1,169,031 | 371,212 |

The 200m diagnostic pixels agree exactly with LOD2 and differ strongly from forced LOD0/1.
The 50m result is not a verified LOD histogram; cluster traversal/LOD/cull behavior remains
unresolved. These transient ID captures are not per-instance telemetry from the standalone
timing runs. Consequently the expected-LOD selection gate is **not passed**, and this report
does not pretend that old B timings measured its 102–120-triangle LOD0 crowns.

Evidence: [`lod_selection_comparison_02.json`](evidence/forestspike-b0-integrity/lod_selection_comparison_02.json),
the complete spec and local capture receipt. All 16 PNGs/sidecars are retained locally; four
native diagnostic PNGs are included in `evidence/forestspike-b0-integrity/native/` for review.
These are ID/range diagnostics, not final shaded visual comparisons:

| View | Automatic | Forced LOD2 |
|---|---|---|
| V1 50m p15 | [1920x1080 PNG](evidence/forestspike-b0-integrity/native/probe_v1_agl50_p15_lod-1.png) | [1920x1080 PNG](evidence/forestspike-b0-integrity/native/probe_v1_agl50_p15_lod2.png) |
| V1 200m p10 | [1920x1080 PNG](evidence/forestspike-b0-integrity/native/probe_v1_agl200_p10_lod-1.png) | [1920x1080 PNG](evidence/forestspike-b0-integrity/native/probe_v1_agl200_p10_lod2.png) |

The diagnostic editor exited with an access violation after its fresh 16-capture completion
receipt; that is recorded separately and is not a performance PASS.

## 2. Moving timing correction: the camera did not move

The planned sequence has 10 keys, t14 through t32, separated by 120 frames at 60fps:
1080 intervals = 18 seconds, playback range [0,1081). The historical CSVs contain 900 frames;
after discarding [0,120), only 780 frames remain. This arithmetic alone would allow at most
15/13 nominal timeline seconds, not a full 18-second flight.

The stronger result comes from the **actual CSV `View/PosX/Y/Z` columns**, matched per frame
against the piecewise-linear path in the original `perf_pilot.json`. In all six A/B moving runs:

- CSV frame 0 is a boot/no-view sample at (0,0,0), outside the intended trajectory.
- Frames 1–899 remain at (-70301.5, 70301.5, 32400.3008) UE cm, matching V3 **t14** within 0.02m.
- All 780 warm samples remain at t14. Observed warm path range is **[14.0,14.0] seconds**.
- **Zero seconds of path traversal is verified.** The 780 warm samples are a stationary starting-pose
  exposure; they must not be described as 13 seconds of flight, an 18-second path, or a motion/shimmer test.

Fresh reopen of both existing moving maps confirms that their `FS_PerfCamera` actors exist,
but the Level Sequence's possessable camera bindings resolve **zero objects** in those saved
worlds. Both sequence playback ranges are 0–1081. This establishes the broken binding;
the likely construction cause is binding before the original `save_map` renames the world,
but that construction explanation remains an inference.

Evidence: [`historical_csv_audit.json`](evidence/forestspike-b0-integrity/historical_csv_audit.json),
[`historical_camera_trace.csv`](evidence/forestspike-b0-integrity/historical_camera_trace.csv)
(all 5,400 moving-run rows, including the invalid boot rows), and `sequence_audit` in the readback receipt.

The original `ppa` tables and 42.23ms/115ms failures remain unchanged as historical timings.
Their interpretation as **moving-path** performance and motion-induced variance is withdrawn.
No GPU ranking is made from them. A corrected metadata-only reanalysis reproduces every
cold/warm timing statistic for all 13 runs exactly.

The revised runner refuses any catalogued level with a nonzero sequence duration. It cannot
turn the broken saved moving maps into a fresh moving PASS. A future repair must use a new
isolated map/sequence name, establish a camera binding that survives save/reopen, hold the
starting pose during a separately recorded warm-up, then verify the complete path from
per-frame view/sequence receipts. Increasing `Frames` alone does not repair the binding or
prevent warm-up from consuming an autoplay path. None of the original maps was overwritten.

## 3. Fail-closed CSV and completion validation

`run_perf.ps1` now creates an exclusive per-tag/level directory in `Saved/ForestSpike/perf_v2/`,
assigns a fresh run ID, and uses UE5.8's actual comma-delimited metadata grammar:
`tag=...,level=...,run_id=...`. The parser explicitly decodes historical semicolon metadata,
marks it historical, and refuses it as a new capture. UE's final unescaped command-line tail
and large boot EVENTS field are handled without shifting required numeric columns.

The runner copies the **exact output named in the current engine log**. It validates:

- Fresh CSV and log, matching tag/level/run ID and CSV capture ID.
- The expected `/Game/ForestSpike/Perf/<Level>` really entered play.
- Exact expected frame count in both the CSV and engine completion log.
- All five required frame/CPU/GPU timing columns, numeric finite samples, positive warm timings,
  nonempty warm window, fixed 1080p/60 timeline/vsync metadata and the named UHD 770 host.
- CSV finalization followed by the profiler's exit request; no fatal error before completion.
- The observed process exit, preserving abnormal shutdown after otherwise validated completion
  without allowing an arbitrary new CSV to imply success.

The completion receipt includes CSV/log hashes and `PASS_FS_PERF_CAPTURE` only for this scope.
It **never** means LOD selection, camera motion, F9/F10/F11 or B1a passed. The analyzers keep
legacy runs `HISTORICAL_ONLY_UNVERIFIED`, reject a changed CSV after its receipt, pair by
metadata, and refuse to overwrite old summary files or silently pair different views/states.

Validation:

- 25 standard-library regression tests: valid completion, missing completion, early crash,
  allowed post-completion abnormal exit, stale files, wrong map/tag/ID/frame count/resolution,
  missing/duplicate fields, NaN/zero warm GPU, truncated data, mixed legacy metadata,
  late optional columns, full command-line preservation, and analyzer receipt/hash checks.
- `b0fix_static01`: **FAIL / incomplete**. No completed CSV was produced and the process exit
  was not observed. Its request, log and failure receipt are retained; no crash cause is inferred.
- `b0fix_static02`: **PASS_FS_PERF_CAPTURE**, existing A/S-on static 200m map, 480 frames,
  120 excluded + 360 valid warm samples, separate metadata fields, matched finalized engine
  output, exit 0. This is a runner validation only, not an A/B experiment or new ranking.

New requests/receipts, raw-output hashes and the new capture summary are included in the
evidence folder. The original 13 CSVs and summaries remain in their original locations.
The public static02 receipt is an explicitly labelled offline recheck using the corrected
command-line parser. It validates the same CSV/log, original start time and observed exit 0;
it is not an additional engine run. Both original and recheck receipts remain intact locally.

## Reproduction without overwriting evidence

Use a new Tag and output filename each time. The existing `run_stage`/build reproduction
section in the historical result is not an instruction to rebuild accepted artifacts.

```powershell
$py = 'D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe'
& $py -m unittest discover -s tools/forestspike -p test_perf_integrity.py -v
& $py tools/forestspike/audit_history.py --repo . --out <new-audit-directory>
& tools/forestspike/run_perf.ps1 -Level L_FSP_A_S1_v1_agl200_p10 `
  -Tag <new-tag> -Frames 480 -Cold 120 -Python $py
& $py tools/forestspike/analyze_perf.py `
  --dir unreal/ForestSpike/Saved/ForestSpike/perf_v2 --out <new-summary.json>
```

For readback, set `ACW_REPO_ROOT`, `ACW_FS_PR18_ROOT`, `ACW_FS_RUN_ID`, and a **new**
`ACW_FS_LOD_REPORT` path, optionally `ACW_FS_AUDIT_SEQUENCES=1`, then run
`adapters/unreal/forestspike/fs_verify_lods.py` using UnrealEditor-Cmd's
`-ExecutePythonScript`. Record the new log path and process exit. A `PARTIAL_*` receipt is not PASS.

## Stop report and next repair

The B0 branch now contains the focused integrity fixes and the blocker evidence. B1a remains
stopped because expected standalone LOD selection is not fully verified and no valid moving
camera capture exists. No new factorial branch or Draft PR was opened; PR #24 remains Draft.

Before another B1a attempt: repair a new saved moving fixture's durable binding/warm hold,
verify actual per-frame camera travel and the full measurement interval, and establish/read
back the intended per-instance LOD selection in the effective 50m/200m views. Keep the original
fixtures/results for comparison. Only then rerun the three first-stage gates.

The known ground-S/HISM handoff still lacks guaranteed matching per-instance fade. The visible
switch ring remains a defect; F9/F10 are not PASS and F11 temporal motion is not measured.
Nothing in this correction supports B1b, B2, AC7 visual parity or platform extrapolation.
