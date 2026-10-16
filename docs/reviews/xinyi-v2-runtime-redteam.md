# XinyiV2 UE5.8 runtime gate — hostile architecture review

Date: 2026-09-26  
Review branch: `codex/issue8-runtime-redteam`  
Base reviewed: `feat/xinyi-unreal-v2` at `6d20beeaf1798e109a55030044adb53c469875b1`  
Disposition: **STOP before HLOD, cook, or performance acceptance**

## Review boundary and evidence quality

This is a deliberately adversarial review. A green commandlet, an actor count, or an attractive
capture is not treated as runtime evidence unless the test observes the behavior it names.

Codex Cloud does not contain the 29 original untracked Unreal files, the generated `_WP` map,
external actor packages, Saved receipts, or a Windows UE5.8 runtime. No runtime gate was run here,
and this review makes **no** streaming, collision, cook, HLOD, memory, or performance PASS claim.
Issue #8 and Draft PR #9 were requested through both `gh` and GitHub HTTPS, but this checkout has no
GitHub credentials and outbound access returned authentication/CONNECT failures. Their repository
representation was therefore reviewed through the Issue/PR references, current branch history,
tracked documentation, scripts, workflows, and source at the stated base SHA. This limitation must
not be misreported as having reviewed comments that were unavailable.

The validated building geometry, MOI terrain truth, coordinate mapping, surveyed elevations, and
accepted source map are outside the mutation scope. The 25-tile representation is a **candidate**,
not a conclusion.

## Executive verdict

The current gate proves useful editor facts: an isolated conversion produced a partitioned map;
target descriptors existed; editor-native predicates returned true; and the source map survived the
conversion attempt. It does **not** yet prove runtime spatial loading, Landscape proxy ownership,
collision semantics, HLOD fitness, cook reachability, packaged persistence, or a performance budget.

The central false-PASS risk is category substitution: testing editor capability predicates and
package existence, then naming the result as runtime behavior. `CanStream()` is a capability answer,
not evidence that a streaming source caused the intended cells and only those cells to transition.
Likewise, one convex body per 500 m tile is measurable collision data, not usable city collision.

| Severity | Count |
|---|---:|
| BLOCKER | **5** |
| HIGH | **9** |
| MEDIUM | **8** |
| LOW | **4** |

## BLOCKER findings

### B1 — No runtime streaming transition has been observed

**Repository evidence.** The native bridge returns `IsInitialized`, `SupportsStreaming`,
`IsStreamingEnabled`, `IsStreamingEnabledInEditor`, and `CanStream`. The Python audit accepts these
when they merely have Boolean types; it does not require their truth or sample loaded runtime cells.
The PowerShell conversion wrapper requires only `enable_streaming` and `can_stream`, descriptor
counts, and map existence. The result document explicitly says source-driven load/unload remains.
See `XinyiWorldPartitionAuditLibrary.cpp:22-33`,
`audit_xinyi_v2_world_partition.py:194-215`,
`create_isolated_wp_test.ps1:140-171`, and
`docs/xinyi-unreal-v2-world-partition-result.md:69-75`.

**Why it matters.** An initialized partition can retain all target actors loaded, use an unintended
grid/loading range, or ignore the intended source. This is the difference between a barometer saying
“weather exists” and measuring the storm: the predicate is real, but it answers the wrong question.

**What could falsely pass.** A commandlet/editor world where all 25 tiles are loaded; an oversized
loading range covering the district; a source that never activates; an editor-only loaded-region
state; or actors marked non-spatial could still satisfy the existing conversion checks.

**Exact workstation test.** In a Development packaged build (repeat in PIE only as diagnostics),
disable editor region loading and place one scripted `WorldPartitionStreamingSourceComponent` on a
fixed, versioned route: outside-west -> centers of all 25 tiles in serpentine order -> outside-east.
At each dwell point wait for streaming completion with a hard timeout, then record timestamp,
source transform/range/target state, runtime cell GUID/state/bounds/grid, actor descriptor GUID,
tile actor loaded/unloaded callbacks, and loaded target labels. Run twice from a clean process and
compare normalized receipts. Include a control point far enough away that no building tile is loaded.

**PASS.** Every expected tile becomes available before its observation point, tiles outside the
declared range unload after hysteresis, the far-away control loads zero building tiles, the two runs
produce the same ordered state transitions, and no tile disappears while inside its required range.

**FAIL / stop.** No transition; all tiles always loaded; any missing tile; non-deterministic cell
membership; timeout; editor-only success not reproduced packaged; or a source/grid/range mismatch.

**Architecture mutation?** **No** to instrument and test. **Yes, human approval required** if actor
granularity, grid assignment, loading range, or World Partition policy must change.

### B2 — Converted local packages are neither source-controlled nor reproducibly materialized

**Repository evidence.** The accepted `_WP` map and external actor packages are explicitly local,
untracked state. The conversion wrapper refuses to run if the converted map already exists and does
not produce a content-addressed inventory of every new package. The current Cloud checkout cannot
inspect those packages. See `docs/xinyi-unreal-v2-world-partition-result.md:25-37` and
`create_isolated_wp_test.ps1:40-46`.

**Why it matters.** The architecture under test is hidden in one workstation. A later streaming,
cook, or HLOD result cannot be tied confidently to the accepted source map or regenerated after disk
loss. External actor packages are part of the world, not disposable commandlet exhaust.

**What could falsely pass.** Auditing stale `_WP` files from an older source; converting successfully
while omitting a package from backup/cook; or publishing receipts whose map/package bytes cannot be
recovered.

**Exact workstation test.** Before mutation, snapshot SHA-256, size, package name, actor GUID and
source-control status for the source map and all Xinyi assets. Convert into a new empty staging copy.
Inventory `_WP.umap`, external actors/objects, Landscape-related packages and referenced meshes.
Archive the inventory and packages. Delete the staging output, restore/regenerate it from the
documented inputs, and require the same semantic package/descriptor inventory. Open in a fresh
process before and after restore.

**PASS.** Every actor descriptor resolves to an existing archived package; no descriptor/package is
orphaned; the regenerated semantic inventory is identical; the original 29-file snapshot remains
byte-identical; and the restored world passes the same fresh audit.

**FAIL / stop.** Missing/unresolved package, stale package accepted, GUID churn without explanation,
source mutation, or success dependent on files outside the archived manifest.

**Architecture mutation?** **Yes.** A human must choose whether generated WP state is committed,
artifact-managed, or deterministically regenerated and promoted.

### B3 — Landscape partition ownership and runtime collision are unproven

**Repository evidence.** The conversion audit expects one terrain descriptor labelled
`Terrain_Xinyi_MOI2025`; it does not enumerate `LandscapeStreamingProxy`, per-component ownership,
runtime cells, or Landscape collision components. The pre-conversion contract is one Landscape with
25 components, while the result claims only one terrain descriptor. See
`audit_xinyi_v2_world_partition.py:170-190,217-239`,
`docs/xinyi-unreal-v2-world-partition-result.md:12-23`, and the 5x5 contract in
`docs/xinyi-unreal-v2-contract-result.md:31-45`.

**Why it matters.** Conversion may keep a monolithic always-loaded Landscape, create proxies with
unexpected cell ownership, or decouple render and collision streaming. Matching 500 m components to
500 m source tiles does not guarantee matching runtime cells.

**What could falsely pass.** The root Landscape descriptor exists while proxies/collision are absent,
always loaded, assigned to another grid, or saved in unresolved packages.

**Exact workstation test.** In a clean editor process enumerate the Landscape root, every streaming
proxy, component, heightfield collision component, outer package, actor descriptor GUID, spatial flag,
runtime grid and runtime-cell bounds. Traverse component-center and border points in a packaged
build, logging render-proxy and collision availability. Perform downward traces at a deterministic
sample set containing all 25 component centers, shared edges/corners, steep terrain, and out-of-bounds
controls; compare Z against the accepted heightfield tolerance.

**PASS.** All 25 component regions have exactly one unambiguous runtime owner; render and collision
load before use and unload outside policy; seam samples are continuous; all expected Landscape
packages resolve after fresh reopen and cook; controls miss.

**FAIL / stop.** Monolithic always-loaded terrain contrary to budget, ownership gaps/overlaps,
duplicate collision, seam misses, unexpected grid, unresolved packages, or editor/package divergence.

**Architecture mutation?** **Possibly.** Instrumentation is not mutation; proxy/grid/collision policy
changes require approval because they alter runtime ownership.

### B4 — Current building collision blocks streets and courtyards by construction

**Repository evidence.** Each 500 m tile has exactly one convex simple shape and the default trace
flag; the repository correctly warns this cannot preserve gaps. The baseline audit declares PASS when
the properties are readable, not when collision is correct. See
`audit_xinyi_v2_collision.py:34-90` and
`docs/xinyi-unreal-v2-world-partition-result.md:58-67`.

**Why it matters.** A convex hull around many disconnected buildings can turn most of a tile into an
invisible wall. A few “hit building” traces would pass while flyable gaps, streets, courtyards, and
rooftop clearance are catastrophically wrong.

**What could falsely pass.** Testing only rays aimed at roofs/facades, counting one simple shape as
present, or accepting any blocking hit without validating hit distance and negative-space misses.

**Exact workstation test.** Freeze a representative trace corpus derived independently from the
validated geometry: vertical roof hits; facade-normal hits at several heights; street/courtyard/gap
misses; tile-border pairs; terrain-only hits; and above-roof controls. Include dense core, sparse tile,
tall/slender buildings, holes, multipart footprints and Taipei 101 suppression vicinity. Run the same
queries in editor and packaged Development with unique collision channels for terrain/buildings.
Record expected hit/miss, actor/component, impact point/normal, face index when applicable, and error.

**PASS.** All positive and negative samples meet fixed global tolerances; gaps remain traversable;
tile borders introduce neither walls nor holes; packaged results equal editor results.

**FAIL / stop.** Any false blocker in a certified gap, systematic misses, tile-hull hit instead of the
intended building, terrain/building channel confusion, or packaged divergence.

**Architecture mutation?** **Yes.** Replacing the convex-per-tile baseline with authored proxies,
partitioned collision, or complex collision is a runtime architecture decision. Do not silently
enable complex-as-simple: it can inflate memory/cook cost and has physics limitations.

### B5 — No cook/package reachability proof exists

**Repository evidence.** The plugin is Editor-only and enabled in the project; `DefaultGame.ini`
adds `GameFeatureData` scanning only to suppress commandlet startup failure, with `CookRule=Unknown`.
The generated `_WP` content is local/untracked. There is no cook/package workflow or runtime entry-map
configuration for Xinyi; `DefaultEngine.ini` still names the Taipei greybox as editor startup map.
See `XinyiLandscapeBridge.uplugin:10-16`, `AirCombatWorld.uproject:8-25`,
`DefaultGame.ini:14-16`, `DefaultEngine.ini:5-8`, and
`docs/xinyi-unreal-v2-world-partition-result.md:47-49,69-75`.

**Why it matters.** Commandlet exit 0 can coexist with an uncooked Xinyi map, stripped external actor
packages, missing mesh references, or a build that starts elsewhere. Editor-only bridge code is fine
for creation only if no runtime asset/class depends on it.

**What could falsely pass.** A cook that never includes `_WP`; an editor launch masquerading as a
runtime launch; loose local files satisfying references; or an Asset Registry scan that finds assets
which were not staged.

**Exact workstation test.** From a clean staging directory, explicitly cook the promoted `_WP` map
for the target platform, stage/package it, and fail on warnings for missing packages/soft references.
Inspect cook manifest, Asset Registry and IoStore/PAK contents for the map, all external actors,
Landscape data/collision and 25 meshes. Rename/move the uncooked project Content directory, then
launch the packaged executable directly into the Xinyi map. Traverse the streaming route and collision
corpus; capture runtime asset/package names and unresolved-load logs.

**PASS.** The packaged executable loads the intended `_WP` map without editor/plugin modules or loose
content; all 25 building references and Landscape regions survive; streaming and collision behavior
matches receipts; zero missing package/class/reference errors.

**FAIL / stop.** Xinyi absent from cook, fallback map, dependency on Editor module, missing external
actor/Landscape/mesh package, loose-file dependency, or commandlet success with runtime load failure.

**Architecture mutation?** **Possibly.** Adding deterministic cook inclusion is expected; changing
Asset Manager/Game Feature strategy or runtime classes requires human approval.

## HIGH findings

### H1 — A deterministic streaming test can deterministically prove nothing

**Evidence.** The stated next step is a deterministic source traversal, but no specification requires
a far-away zero-loaded control, actor lifecycle observations, cell IDs, or packaged execution
(`docs/xinyi-unreal-v2-world-partition-result.md:69-75`).

**Why / false PASS.** Replaying camera coordinates while all actors remain resident is perfectly
deterministic. Sampling only actor visibility can also confuse rendering with object residency.

**Workstation test and thresholds.** Use B1's instrumented route with explicit negative control,
transition ordering, timeouts, cell/actor lifecycle, memory deltas, and two clean packaged runs.
**PASS:** exact expected transitions and zero target tiles at the control. **FAIL:** static residency,
visibility-only changes, no unload, or run-to-run divergence.

**Architecture mutation?** No for test instrumentation; yes if loading policy fails.

### H2 — Runtime grid and loading range are not recorded

**Evidence.** Actor and descriptor rows record `runtime_grid`, but the audit records no grid object,
cell size, loading range, priority, block-on-slow-streaming policy or source target grids
(`audit_xinyi_v2_world_partition.py:101-144,299-337`).

**Why / false PASS.** Empty/default grid strings may be legitimate but leave effective policy
unknown; a range larger than 2.5 km can make the entire test world resident.

**Workstation test.** Export authoritative runtime hash grid definitions and streaming-source
configuration, then map actor bounds to actual cells. **PASS:** versioned values, bounded overlap and
measured unloading. **FAIL:** implicit/unrecorded values, all-district range, or unexpected grid.

**Architecture mutation?** Possibly; changing cell/range policy needs approval.

### H3 — Actor bounds may defeat 500 m ownership

**Evidence.** Placement creates one `StaticMeshActor` per concatenated tile and validates only actor
translation/reference after reopen. It does not assert world bounds remain within the tile ownership
envelope or record cell membership (`place_xinyi_v2_runtime_tiles.py:41-88`;
`verify_xinyi_v2_runtime_world_reopen.py:38-68`).

**Why / false PASS.** Geometry touching/crossing a boundary or an oversized imported bound can place
one actor in multiple cells, an unexpected cell, or keep it resident longer than intended while all
locations still match.

**Workstation test.** Export component and actor world AABBs, compare against contract tile bounds
with a documented seam epsilon, then record actual runtime cell memberships during traversal.
**PASS:** bounded expected seam contact and deliberate membership. **FAIL:** unexplained overhang,
huge bounds, ownership ambiguity or placement drift.

**Architecture mutation?** Only if bounds show 500 m actors are unsuitable; then yes.

### H4 — Fresh-reopen validation trusts a mutable receipt and checks too little

**Evidence.** The reopen gate consumes the prior local JSON, checks labels, locations and mesh paths,
but not mesh hashes/bounds, spatial flags, GUIDs, packages, transform rotation/scale, collision or
descriptor ownership (`verify_xinyi_v2_runtime_world_reopen.py:23-75`).

**Why / false PASS.** A stale or co-mutated receipt can bless the wrong world; duplicate labels are
collapsed by a dictionary; matching references do not prove package persistence or runtime policy.

**Workstation test.** Anchor the expected receipt to the offline contract hash and source-map hash;
fresh-process compare actor GUID/package, complete transform, bounds, asset content hash, spatial/grid
flags and descriptor identity. **PASS:** unique 1:1 closed join. **FAIL:** duplicate label, stale hash,
missing field or mismatch.

**Architecture mutation?** No; this is gate hardening.

### H5 — HLOD has no valid prerequisite state or acceptance budget

**Evidence.** No HLOD layer is assigned in the target audit beyond reporting a path; the result says
HLOD remains pending (`audit_xinyi_v2_world_partition.py:90-113,265-309`;
`docs/xinyi-unreal-v2-world-partition-result.md:69-75`).

**Why / false PASS.** “HLOD build succeeded” can mean zero useful proxies, proxies for always-loaded
actors, or proxies costlier than source meshes. Twenty-five already-merged meshes may be poor HLOD
inputs and can destroy useful near/far granularity.

**Workstation test.** Only after B1-B5: freeze camera route, resolution/scalability and warmup; capture
HLOD off/on proxy count, source actor coverage, generated triangles/materials/textures, disk bytes,
peak build RAM/time, transition distances, holes/double rendering/pops, mesh draws, GPU/CPU frame and
streaming hitch. **PASS:** explicit budget improvement with acceptable silhouette/transition error.
**FAIL:** zero/unowned proxies, increased cost without benefit, visual holes, collisions tied wrongly
to HLOD, unstable build, or material dependency explosion.

**Architecture mutation?** Yes for layer/actor granularity. Human approval required. HLOD may be
rejected; it is not a ritual that must be forced onto a 25-mesh district.

### H6 — One mesh per tile may hide draw, material, memory and update-path costs

**Evidence.** The runbook promotes 25 concatenated runtime GLBs to reduce package/actor overhead but
explicitly defers performance architecture (`xinyi-blender-to-unreal-runbook.md:495-553,935-943`).

**Why / false PASS.** Actor count 25 is not draw-call count 25. Sections/material slots, shadow
passes, distance-field policy, vertex/index buffers, collision and visibility granularity determine
cost. Large meshes can render every triangle when a small part is visible.

**Workstation test.** Record per mesh LOD/section/material count and resource sizes; on a fixed
packaged route use Unreal Insights plus GPU profiling to collect mesh draws, primitives, visible
triangles, game/render/RHI thread, GPU, committed/LLM memory and residency. Compare at least current
25-tile baseline against any proposed change using identical content/cameras. **PASS:** meets a
human-approved target budget with no correctness regression. **FAIL:** budget breach or measurement
only in editor.

**Architecture mutation?** Yes if representation changes; approval required.

### H7 — Collision strategy lacks negative-space authority and channel isolation

**Evidence.** The current audit counts shapes/flags only and reads expected triangles from an import
receipt (`audit_xinyi_v2_collision.py:28-95`).

**Why / false PASS.** Generated simple collision and complex-as-simple fail differently. The former
can seal gaps; the latter can explode memory/cook/time and behave differently for sweeps/simulation.

**Workstation test.** Run B4's frozen positive/negative trace and sweep corpus on separate channels,
plus memory/cook metrics for each candidate policy. **PASS:** correct hits and misses, supported query
types, stable package cost. **FAIL:** any blocked certified gap, missing facade/roof, unsupported
physics use, or unbounded cost.

**Architecture mutation?** Yes; approval required.

### H8 — Commandlet success is contaminated by startup/config concerns

**Evidence.** A `GameFeatureData` rule was added because the conversion operation returned result 0
while the process exited 1; its cook rule remains Unknown
(`docs/xinyi-unreal-v2-world-partition-result.md:47-49`; `DefaultGame.ini:14-16`).

**Why / false PASS.** Suppressing startup failure can make the conversion wrapper green without
proving the intended asset-management/cook contract. Conversely, unrelated startup noise can hide
the meaningful operation result.

**Workstation test.** Separate startup health, operation receipt and postcondition validation; fail on
new errors; inspect Asset Manager primary assets and cook manifest. **PASS:** clean startup, explicit
operation success, verified outputs and deliberate cook rule. **FAIL:** ignored errors, Unknown rule
relied upon implicitly, or assets absent after staging.

**Architecture mutation?** Yes if adopting Game Features/Asset Manager as runtime architecture;
otherwise remove incidental coupling with approval.

### H9 — Performance methodology is not yet decision-grade

**Evidence.** The tracked result leaves memory, draw calls and frame timing pending, and no target
hardware, budgets, packaged configuration, route, warmup, sample window or hitch definition is
versioned (`docs/xinyi-unreal-v2-world-partition-result.md:69-75`).

**Why / false PASS.** Average editor FPS can conceal shader compilation, streaming hitches, tail
latency, memory peaks and packaged-build regressions. A NullRHI commandlet cannot establish GPU cost.

**Workstation test.** Define target hardware and packaged Development/Shipping settings; use one
versioned cold-start and traversal script. Collect startup-to-ready, p50/p95/p99 frame time, worst
streaming hitch, game/render/RHI/GPU times, draw/primitive counts, CPU working set/commit, GPU memory,
IO bytes, asset residency and crash/OOM. Repeat cold and warm runs; HLOD A/B changes one variable.
**PASS:** all pre-approved budgets in packaged runtime with repeatability. **FAIL:** any budget miss,
editor-only/average-only data, shader compilation in one arm, or unequal routes/settings.

**Architecture mutation?** No to establish methodology; yes for optimizations selected from results.

## MEDIUM findings

1. **M1 — Audit fallback defaults hide inaccessible properties.** `_prop(..., False)` turns API
   absence into a real-looking false value. The native fields fix only partition predicates, not actor
   metadata. Receipts need `available/value/error` rather than silent defaults.
2. **M2 — Descriptor matching is label-based.** Labels are mutable and not stable identity. Join on
   actor GUID/package/contract tile ID and separately assert labels.
3. **M3 — Loaded actor enumeration can perturb evidence.** Loading a level in an editor commandlet may
   load actors the runtime would stream. Descriptor inventory and runtime lifecycle must remain
   separate datasets.
4. **M4 — Conversion logs are not semantically gated.** Exit code and output existence do not reject
   important warnings. Maintain an allowlist and fail on missing-package, invalid descriptor,
   Landscape and external-actor errors.
5. **M5 — Resume selects newest local inputs by directory number.** It does not prove they match the
   current source/branch unless the internal contract hashes are rejoined to the local assets. Resume
   receipts should bind all stages cryptographically.
6. **M6 — Resume replaces evidence directories.** Artifact restoration deletes an existing run
   directory. Use immutable content-addressed directories and atomic promotion so failed downloads
   cannot destroy the last known-good input.
7. **M7 — Placement is destructive before full validation.** Existing runtime actors are destroyed
   before every new tile has passed and before save. Operate on a copy/new level or transact with a
   pre-mutation manifest and rollback.
8. **M8 — No explicit tile-border visual/placement regression.** Actor locations can pass while bounds
   overlap/gap. Add contract-derived border probes and world-bounds comparisons without modifying
   geometry.

## LOW findings

1. **L1 — Terminology overstates evidence.** `PASS_WORLD_PARTITION_AUDIT` is acceptable for a static
   audit, but surrounding text should avoid “active streaming” until transitions are observed.
2. **L2 — Startup map is unrelated to Xinyi.** This is not wrong, but packaged test commands must name
   the Xinyi map explicitly and prove it, rather than relying on project defaults.
3. **L3 — Runtime budgets have no receipt schema.** Define units and provenance before first capture
   to prevent hand-curated screenshots/stat snippets becoming the record.
4. **L4 — Report timestamps alone are weak provenance.** Include engine build/CL, project commit,
   target platform/RHI, command line, map package hash and machine profile in every host receipt.

## Landscape-specific conclusions

- A 631x631 heightfield with 5x5 components is a valid offline topology contract; it does not prove
  the conversion creates the desired World Partition Landscape proxy/cell topology.
- The terrain actor, rendering components, streaming proxies and heightfield collision are different
  ownership surfaces and must be inventoried separately.
- Component-center checks alone miss seam and corner defects. Test shared edges/corners and controls
  beyond the Landscape bounds.
- Do not change the accepted DTM, global datum alignment or building Z authority to repair partition
  behavior. If conversion produces an unacceptable topology, change downstream architecture only.

## HLOD measurement and rejection rule

Before generating HLOD, freeze the current no-HLOD baseline and its package hashes. For each HLOD
candidate record:

- generated proxy count and source-actor coverage (including zero/duplicate coverage);
- proxy triangles, sections, materials, textures, Nanite state and disk/cook bytes;
- peak generation time/RAM and deterministic rebuild identity;
- silhouette/depth error at fixed cameras and transition distances;
- missing geometry, double rendering, shadow discontinuity and transition hitch;
- packaged mesh draws, frame-time distribution, GPU/CPU memory and IO versus baseline.

Reject HLOD rather than force it when it cannot reduce a named bottleneck, increases total runtime or
disk cost beyond budget, produces unacceptable silhouette/transition errors, cannot build
deterministically, or conflicts with 500 m actor/cell ownership. “HLOD exists” has zero architectural
value by itself.

## Performance evidence rules

| Measurement | Required environment | Misleading substitute |
|---|---|---|
| Cook/staged bytes, reference survival | clean target-platform cook + packaged launch | editor Asset Registry query |
| Startup/load time | cold packaged process, explicit Xinyi map | already-open editor |
| Streaming hitch and IO | packaged traversal, fixed source/route | teleporting editor camera after warm cache |
| Game/render/RHI/GPU frame time | packaged runtime, fixed resolution/settings | average editor FPS |
| GPU memory | target RHI packaged run | NullRHI or editor total |
| CPU memory/peak commit | process-level + LLM in packaged run | asset size sum |
| Mesh draws/primitives | packaged captured frames | actor or StaticMesh asset count |
| Collision cost/correctness | packaged trace/sweep corpus | shape-count audit |
| HLOD benefit | controlled packaged A/B | HLOD build success |

## Recovery and reproducibility audit

| Stage | Current resumability | Corruption risk | Required protection |
|---|---|---|---|
| Offline contract | Regenerable and hash-checked | Low | retain immutable workflow artifact/digests |
| Landscape/runtime asset import | Resume script reuses assets | Stale asset/receipt join | bind receipt to contract, engine and asset hashes |
| Actor placement | Reruns after destroying labelled actors | Partial mutation before failure | operate on copied world; pre/post inventory; atomic promotion |
| WP conversion | Refuses overwrite; isolated suffix | Unique local result can be lost/stale | immutable package archive + content-addressed manifest |
| Streaming test | Not implemented | Test may mutate/editor-load state | packaged read-only harness; new Saved run directory |
| Collision candidates | Baseline read-only; mutations undefined | asset collision rebuild can overwrite evidence | duplicate assets/world per candidate; hash originals |
| HLOD build | Not implemented | generated packages can contaminate next arm | separate clean A/B workspaces and cook outputs |
| Cook/package | Not implemented | stale staged files can create false success | delete staging only, never source; clean cook manifests |
| Performance | Not implemented | warm caches/shaders contaminate comparison | fixed order, cold/warm labels, immutable trace files |

Every stage should write to a new run ID, verify inputs before mutation, write a failure receipt on
error, and promote a `latest-passing` pointer only after postconditions pass. Successful expensive
stages should not rerun unless an input hash, engine build, policy or dependent asset changed.

## Potential false PASS conditions

- `SupportsStreaming()`/`CanStream()` is true but no target runtime cell ever unloads.
- Editor region state or level loading keeps all 25 actors resident during the “streaming” route.
- An oversized source range covers all Xinyi at every sample.
- Visibility changes while actor/package residency never changes.
- One root Landscape descriptor hides missing, duplicated or always-loaded proxies/collision.
- Actor labels/counts match while GUIDs, external packages, bounds, grid or spatial flags are wrong.
- A stale `_WP` map is audited instead of the map generated from the current source hash.
- A deterministic camera route repeats a deterministic no-op.
- Roof/facade traces hit the tile convex hull while streets/courtyards are silently blocked.
- Cook exits zero but never includes the Xinyi map or its external actors.
- The packaged launch falls back to Taipei greybox and is mistaken for a Xinyi launch.
- Loose editor content satisfies references that are absent from IoStore/PAK.
- HLOD command succeeds while producing zero useful proxies or increasing cost.
- Editor FPS looks stable because content is preloaded and shaders/caches are warm.
- Average frame time passes while p99 streaming hitch, peak commit, or startup time fails.

## Do not proceed to HLOD until...

1. The accepted source and isolated `_WP` package sets are content-addressed, restorable, and joined
   to the current contract/engine build.
2. A clean packaged build loads the intended `_WP` map with no loose-content or Editor-module
   dependency.
3. The deterministic source traversal proves real cell and actor load **and unload**, including a
   far-away zero-loaded control.
4. Runtime grid, cell size/loading range, actor bounds, descriptor GUID/package and spatial flags are
   recorded and accepted.
5. Landscape root/proxy/component/collision ownership and seam traces pass in packaged runtime.
6. A collision policy passes both positive hits and certified negative-space misses.
7. The no-HLOD packaged baseline, budgets, camera route, scalability, RHI and target hardware are
   frozen.

If any item is missing, HLOD output would optimize an architecture that has not yet been shown to be
correct. That is how a performance experiment becomes a very expensive fog machine.

## Recommended workstation execution order

This order minimizes repeated UE work and protects the only accepted local world:

1. **Quiesce and snapshot.** Close all Unreal processes. Hash and archive the 29 original files,
   source map, current `_WP` map, external actors/objects, runtime meshes, plugin binary, Saved
   receipts and engine build identity. Do not mutate this snapshot.
2. **Recover Issue/PR context.** With authenticated GitHub access, export Issue #8 and Draft PR #9
   body/comments/review state into the run evidence; confirm this review did not miss a later policy.
3. **Clean static/fresh audit.** Run existing host-script/static tests, then audit source and `_WP`
   maps in fresh processes. Emit the expanded grid/bounds/GUID/package/Landscape ownership inventory.
4. **Reproducibility drill.** In a copied workspace, regenerate/restore `_WP` and compare the semantic
   package and descriptor inventory. Stop if it depends on unmanifested local state.
5. **Clean explicit cook.** Cook and stage only from the copied accepted state, explicitly including
   the `_WP` map. Inspect Asset Registry and container manifests. Stop on missing references.
6. **Packaged smoke launch.** Hide loose Content, launch directly into `_WP`, prove map/package
   identity and terrain/building reference survival.
7. **Packaged streaming traversal — highest priority.** Run the versioned outside-to-outside route,
   collect cell/actor load-unload transitions twice, and enforce the far-away zero-loaded control.
8. **Landscape ownership/collision.** Run component-center, seam/corner and out-of-bounds terrain
   traces while streaming.
9. **Building collision corpus.** Run positive and negative-space traces/sweeps against the current
   baseline. Expect the one-convex-per-tile candidate to fail; do not reinterpret that as geometry
   failure.
10. **Freeze no-HLOD performance baseline.** Collect cold/warm startup, memory, IO, p50/p95/p99 frame
    timing, worst hitch, mesh draws/primitives and GPU data on target hardware.
11. **Architecture decision checkpoint.** Humans approve grid/range, collision and any change to the
    25-tile representation. Re-run affected correctness gates.
12. **Only now HLOD A/B.** Build in an isolated copy, verify proxy ownership/visual transitions/cook,
    then compare identical packaged routes. Reject it if it does not improve the named bottleneck.

The **single most important next test** is step 7: a clean packaged deterministic streaming-source
route that proves target cell/actor load and unload, with a far-away zero-loaded control.

## Architecture changes requiring human approval

- promoting, committing, artifact-managing, or regenerating `_WP` and external actor packages;
- changing World Partition runtime grid, cell size, loading range, priority or spatial-loading flags;
- splitting/merging the 25 building tile actors or altering their runtime bounds/ownership;
- changing Landscape root/proxy/component partition or collision ownership;
- replacing the one-convex-per-tile collision policy, including complex-as-simple;
- adding HLOD layers, proxy generation policy, materials or source actor participation;
- adopting Game Features/Asset Manager cook rules or changing the packaged entry-map strategy;
- enabling Nanite, distance fields, new LOD generation, or other representation-changing features;
- changing target hardware/performance budgets after results are visible.

None of those decisions may change the validated source geometry, MOI terrain, coordinate model,
surveyed building elevations, hero suppression or upstream manifests.

## Safe Cloud checks performed / retained

Cloud-safe evidence is intentionally limited to source inspection and static parsing:

- compile all Xinyi Unreal Python adapters with `py_compile`;
- parse all PowerShell gate scripts with PowerShell's AST parser when `pwsh` is available;
- run the existing Python test suite that does not require Unreal;
- validate JSON descriptors and confirm the plugin remains Editor-only;
- inspect the tracked diff for scope violations.

These checks can prevent syntax/configuration regressions. They cannot validate any host runtime
claim and must never update Issue #8 runtime PASS checkboxes.
