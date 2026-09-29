# Issue #8 packaged collision subgate (UE 5.8)

**Landscape collision: PASS. Current building collision policy: FAIL.** This is a correctness result for the existing `_WP` test world, not an overall Issue #8 pass or a replacement collision design. HLOD, gameplay collision changes, materials, and wider Taipei work remain outside this gate.

The run began on `codex/issue8-host-gate-tooling` at `8170d8c480e81ef99fa53c55df5b4cf11bdd3632`. The immutable host run is `20260929T013849Z-8170d8c4`. A UE5.8 Windows Development `BuildCookRun` succeeded with an explicit `/Game/XinyiV2/L_XinyiV2_Contract_WP` map and 638 cooked packages. The final measurement launched a fresh packaged game process, waited for source-driven World Partition completion at all 101 positions, and wrote a host-hash-attested runtime receipt. The original `/Game/XinyiV2/L_XinyiV2_Contract` and isolated `_WP` source packages were not edited. A final post-run source immutability re-check passed for all 107 protected file rows.

Review evidence: [final deterministic plan](evidence/xinyi-host-collision-20260929/collision-plan.json), [packaged runtime gate](evidence/xinyi-host-collision-20260929/packaged-collision.json), and [source immutability result](evidence/xinyi-host-collision-20260929/source-immutability.json). Full package, raw runtime JSON, process launch receipt, and logs remain under `unreal/Saved/XinyiHostGates/20260929T013849Z-8170d8c4` on the validation host and are intentionally uncommitted. The previous complex-only diagnostic process is preserved there; its query mode was not explicit in its raw schema, so the final decision uses the second package and process, which attests both simple and complex modes.

## Landscape ownership and collision

The packaged world exposed one persistent Landscape root in the `_WP` map package and four `LandscapeStreamingProxy` actors in generated World Partition packages. Across the route, those proxies owned 25 distinct `LandscapeComponent` render components and 25 `LandscapeHeightfieldCollisionComponent` collision components, distributed 16 + 4 + 4 + 1. Every terrain trace recorded the hit actor and component class and ignored building actors. `AActor` spatial-loading/grid accessors are editor-only in this UE5.8 packaged target, so the receipt records runtime proxy presence and generated package identity instead of inventing a grid value; the prior accepted streaming gate supplies descriptor/cell evidence.

| Deterministic terrain samples | Count | Result |
| --- | ---: | --- |
| Component centers | 25 | 25 Landscape collision hits |
| Shared component edges | 8 | 8 hits; no seam miss |
| Exact heightfield vertices on both sides of those edges | 16 | 16 hits; eight paired height differences match the R16 differences within 0.010849 cm |
| Shared corners | 4 | 4 hits; no corner miss |
| Southeast/Xiangshan slope | 1 | Hit |
| Terrain/building transition | 1 | Hit with building actors ignored |
| Outside west/east/north/south bounds | 4 | No Landscape hit |

For the 55 in-bounds probes, the maximum absolute Z error against exact accepted R16 vertices was **0.052524 cm**. The plan fixed a **2.0 cm tolerance before execution**: the accepted encoding has a 1.5625 cm quantization step (0.78125 cm half-step), with the remainder covering float and Chaos collision rounding; it does not imply the 20 m source DTM is centimetre-accurate. No in-bounds miss, tolerance outlier, measured edge/corner discontinuity, or out-of-bounds false hit was observed. The primary packaged traces used `ECC_Visibility` with `bTraceComplex=false`; companion complex traces were recorded separately. Terrain actor/component identity was required, so a building hit could not count as terrain.

## Building policy and representative hits

All **25/25** imported runtime tile `StaticMesh` actors were observed and audited in the packaged process. Every tile had collision enabled as `QueryAndPhysics` (enum 3), `ECC_Visibility` response `Block` (enum 2), `ECollisionTraceFlag::CTF_UseSimpleAndComplex` (enum 1), and **one convex simple primitive**, with no box, sphere, capsule, or tapered-capsule primitive. BodySetup paths and GUIDs are in the receipt. The complex counterpart is observable in the paired per-triangle queries; no tile-specific policy variance was found.

Five source-triangle-derived representative cases covered a documented **10.43 m low-rise building**, a high-rise, a dense urban tile, the Taipei 101/hero-suppression neighborhood, and a tile-boundary building. Each used roof-from-above, exterior-wall, and horizontal building-mass traces. **15/15 simple positive traces hit the expected tile**. In the complex reference, 14/15 hit the expected tile; a 30 m boundary approach hit the adjacent `+000_+000` tile before the intended `+001_+000` tile. This adjacent hit is recorded rather than silently credited to the intended building. The shorter boundary wall and roof probes hit the intended tile.

## Certified negative space: current policy fails

Negative XY points were accepted only after exclusion from **every one of the 11,130 source building component world AABBs**, expanded by a 500 cm clearance. The final validator independently repeated that exclusion for all 27 samples and hash-verified the placement manifest against the accepted offline contract. This conservative test certifies that a point is outside all source building solids without depending on a visual screenshot or a later collision result. The final plan includes 25 in-tile open-space points, one explicit tile-border empty point, and one gap between two source buildings; the gap lies 534 cm and 564 cm from their respective AABBs.

At these **27 certified empty-space points**, the simple downward building query was blocked **17 times**: 16/25 open-space samples and 1/1 building-gap sample. The tile-border control stayed clear. Companion complex queries, through the same positions with the same Landscape actors ignored, were clear **27/27**. In the central building gap the simple trace hit tile `+000_+000` at the trace start height of 25,000 cm, despite the sample being outside all accepted building AABBs. This is a false obstruction from the tile-wide convex simple collision volume, not a terrain hit or a surveyed placement correction. A courtyard/hole-specific negative was not certified; the already decisive open-space and inter-building-gap failures stop this policy gate.

**CURRENT COLLISION POLICY = FAIL.** The one-convex-per-tile simple representation seals known empty space. No visual mesh, surveyed building Z, terrain heightfield, source `_WP` package, or collision policy was modified to make the gate pass. Selecting a replacement representation requires a separate architecture decision.

## Isolation, cost, and diagnostics

Building queries ignored all Landscape actors and required `StaticMeshActor` tile identity; terrain queries ignored building actors and required `LandscapeHeightfieldCollisionComponent` identity. The accepted prior 27-point streaming gate recorded no missing references or actor placement drift; this collision run observed all 25 expected assets and completed streaming at every route point. The collision tool does not re-measure actor transform drift, so the prior result is the placement evidence.

The current policy contains **25 simple convex primitives**. The packaged `UBodySetup::GetResourceSizeBytes(Exclusive)` total was **25,169,660 bytes** across 25 tiles. This is a UObject resource-size observation, **not cooked collision bytes**; the latter were not exposed by the packaged API used here. The main packaged PAK was 10,705,822 bytes, but its collision-specific share is not isolated. No process-memory delta or performance budget is claimed. The 101 source stops reported streaming-completion waits from 251 to 330 ms; no completion timeout occurred. The runtime log had zero `Error:` and zero `Warning:` records. Four optional profiling/GPU-capture DLL load attempts were logged without affecting the run.

## Resume boundary

`tools/unreal_xinyi_v2/prepare_collision_plan.py` makes a hash-checked, write-once plan from accepted R16, placement, and GLB inputs. `run_packaged_collision.ps1` launches one fresh packaged Development process into write-once raw/log/host receipts. `validate_packaged_collision.py` verifies plan order, explicit simple/complex mode, process/file hashes, source identity isolation, hit expectations, and all 25 BodySetup policies, then writes a path-free gate receipt. The three tools default to `10-collision-plan.json` for a new run; this immutable exploratory run's final plan is `14-collision-plan.json`, explicitly named in its host receipt. Use a **new snapshot/run ID and package archive** for a changed probe or architecture; do not overwrite this run. The architecture decision and any new policy validation are separate follow-up work.
