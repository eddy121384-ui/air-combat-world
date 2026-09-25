# Xinyi World Pipeline Runbook — Blender to Unreal Engine 5.8

Status: living production runbook  
Last updated: 2026-09-24  
Scope: Xinyi district building geometry, terrain, Unreal runtime materialization, persistence, and visual QA

This document records the complete path that turned the validated Xinyi building
dataset into a persisted Unreal Engine 5.8 world with MOI terrain and deterministic
visual QA.

It is intentionally both:

1. a **retrospective** — what was tried, what failed, and why; and
2. a **runbook** — the order to repeat for another district without rediscovering
   the same failure modes.

The central rule is simple:

> **Do not let downstream tools repair upstream truth.**

Blender validates exported geometry. Terrain adds elevation. Unreal consumes
already-validated inputs. Visual QA makes the result human-readable. None of those
layers is allowed to silently rewrite the previous layer to make a screenshot
look better.

---

## 1. Canonical pipeline

The production path that survived all current Xinyi gates is:

```text
projected building source
-> EPSG:3826 / projected-coordinate truth
-> GEOS repair
-> deterministic 500 m tile ownership
-> tile-local coordinates
-> float32 serialization-space quantization
-> GEOS revalidation
-> GEOS constrained Delaunay triangulation
-> trimesh extrusion / GLB
-> strict numerical QA
-> actual GLB reload
-> Blender 5.2 headless imported-mesh QA
-> building-only district preview

official MOI 2025 bare-earth 20 m DTM
-> provenance/source audit
-> Xinyi ENU alignment
-> one global vertical-datum offset
-> terrain/building-ground regression checks
-> Blender terrain + building preview

validated buildings + accepted DTM
-> deterministic Unreal offline contract
-> 631 x 631 uint16 Landscape heightfield
-> 5 x 5 Landscape components
-> editor-only ALandscape::Import bridge
-> fresh-reopen Landscape persistence gate
-> 25 staged runtime building tile meshes
-> 25 UE StaticMesh assets
-> 25 placed runtime tile actors
-> fresh-reopen world persistence gate
-> SceneCapture2D visual QA
-> only then streaming / HLOD / collision / cook / performance
```

Do not skip forward because a screenshot looks plausible.

---

# Part I — Building geometry

## 2. Why the building pipeline starts in projected coordinates

The production building source is the projected WFS dataset.

Locked production source SHA-256:

`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`

The old pinned EPSG:4326 snapshot remains useful forensic evidence, but it is not
the production source. Large city coordinates and float32 serialization do not
mix safely if the geometry is allowed to travel through an unnecessarily coarse
or numerically fragile representation.

The validated route is:

```text
EPSG:3826
-> pyproj
-> local ENU / WorldModel frame
-> deterministic tile-local coordinates
```

### Lesson

Keep precision while the coordinates are still geographically meaningful, then
move to a small local frame before float32 export.

### Never repeat

- Do not switch production back to the coarse EPSG:4326 snapshot.
- Do not triangulate directly in large world coordinates and only cast to
  float32 afterward.
- Do not assume a mesh that looks correct in Python will survive GLB float32
  serialization unchanged.

---

## 3. Serialization-space geometry was a real failure mode

An early representative gate reached only **76 / 80** valid cases when geometry
was triangulated first and cast to float32 afterward.

That failure established an important rule:

> Geometry must be made valid in the coordinate space that will actually be
> serialized.

The successful ordering became:

```text
repair footprint
-> assign deterministic 500 m tile
-> subtract tile origin
-> cast / quantize horizontal coordinates through float32
-> reconstruct / revalidate polygon in GEOS
-> triangulate the quantized polygon
```

This is why tile-local coordinates are not merely a runtime optimization. They
are part of the geometry correctness contract.

### Historical evidence

- `3b963a4`: 76/80 after post-triangulation float32 cast.
- `cc057996...`: representative serialization-space gate reached 80/80 using
  the then-current triangulation path.

---

## 4. Earcut passed numerical QA and still failed Blender

The first Full-Xinyi earcut-based cloud run looked healthy numerically, but
Blender exposed **five degenerate sliver triangles** after real import.

That was the point where “our numerical checks passed” stopped being considered
sufficient evidence.

The production cap triangulator was changed to:

**GEOS constrained Delaunay triangulation via Shapely**

Trimesh remained responsible for extrusion, mesh assembly, and GLB export.

### Production result

Validated building geometry commit:

`4438d82fe2006710b0fda08e8a06989fba4c09a8`

Full-Xinyi workflow:

`35557915078`

Accepted Full-Xinyi accounting:

- 11,132 source features
- 11,128 ordinary polygon parts
- 8 hero-suppressed source parts
- 11,130 emitted mesh components
- 25 deterministic 500 m tiles
- 485,936 triangles
- Blender 5.2 imported all tiles/components
- zero non-manifold failures
- zero inconsistent winding failures
- zero zero-area failures
- zero failed meshes

Full building tile manifest SHA-256:

`bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`

### Lesson

A triangulator is not accepted because its Python-side output looks valid.
Production geometry must survive:

```text
export
-> reload
-> real Blender import
-> Blender-space topology QA
```

### Never repeat

- Do not silently restore mapbox-earcut as the production triangulator.
- Do not delete the five bad triangles.
- Do not add building-ID-specific exceptions.
- Do not weaken QA tolerances after seeing the failing features.

---

## 5. Why Blender stayed in the pipeline

Blender is not the production runtime, but it caught failures that pure numerical
QA did not.

Its role is:

- import the actual exported GLBs;
- inspect the geometry as a downstream DCC really receives it;
- check mesh topology, winding, degenerate faces, bounds, and volume;
- render district-level overviews;
- later, validate terrain/building placement independently of Unreal.

A Blender failure is not automatically a source-data failure, but it is a hard
signal that exported geometry has not yet earned the right to enter Unreal.

### Numerical stability detail

Blender signed volume is accumulated after recentering vertices around a local
reference origin. That is a translation-invariant numerical stabilization, not
a tolerance relaxation.

---

# Part II — Terrain

## 6. The first terrain source was wrong for the job

The first terrain prototype used **Copernicus GLO-30 DSM**.

The data itself was not “bad”; the semantic choice was bad.

DSM includes roofs, trees, and other above-ground surfaces. When compared with
surveyed WFS building ground elevations in dense Taipei, the prototype terrain
sat roughly **+17 m above surveyed building ground at the median**.

That produced exactly the visual symptom one would expect:

> buildings appeared district-wide buried into terrain.

### Critical lesson

Do not solve a semantic terrain-source error with geometry hacks.

Rejected “fixes” included:

- lift every building to the DSM;
- delete terrain underneath buildings;
- flatten terrain per building;
- deform building meshes;
- create building-ID-specific Z corrections.

All of those would hide the source error instead of fixing it.

---

## 7. Accepted terrain source

The accepted semantic source is:

**2025 Taiwan MOI 20 m bare-earth DTM**

Dataset:

`2025年版全臺灣20公尺網格數值地形模型DTM資料`

The GitHub runner could not fetch the TGOS raw download directly because the
request was blocked with HTTP 403. The cloud pipeline therefore uses a
provenance-recorded derivative mirror:

`yhzkiki/taiwan-dtm-2025-terrarium-z13`

The mirror is treated as a derivative transport of the official MOI DTM, not as
an unrelated terrain source.

### Terrain candidate gate

Passing terrain workflow:

`35575152984` (run #29)

Terrain manifest SHA-256:

`3f6b5f319fee237113864ceb67d30b59ff2914f8125e7a819d83eb8c70381176`

The raw DTM-to-WFS comparison established one global vertical alignment:

`+0.3419554143768595 m`

After alignment:

- median DTM - WFS ground: 0 m
- median absolute residual: ~0.173 m
- P95 absolute residual: ~1.403 m

The old +17 m DSM signature disappeared.

### Lesson

Use one documented global datum alignment if justified by the source comparison.
Do not turn residual outliers into per-building “corrections.”

---

## 8. Building Z authority

For ordinary buildings:

**WFS `ground_elev_m` remains the building-base authority.**

The terrain is not allowed to redefine a building's source elevation.

In Blender preview QA, each imported object's world-space base was measured,
then translated by:

```text
surveyed_ground_z - measured_imported_base_z
```

The result was remeasured and failed closed if base error exceeded the global
tolerance.

This established a useful design pattern later reused in Unreal:

> Measure the importer result, compare it with the expected contract, then apply
> one deterministic transform rule. Do not guess how the importer handled the
> source frame.

---

# Part III — Unreal offline contract

## 9. Do not hand Unreal a vague “terrain mesh”

The Blender terrain preview GLB is evidence and visualization, not the production
runtime terrain.

Unreal gets the same accepted elevation contract as a Landscape-compatible
heightfield.

The chosen Landscape topology is:

- heightmap: **631 x 631**
- components: **5 x 5**
- sections/component: **2 x 2**
- quads/section: **63**
- quads/component: **126**
- physical component size: **500 m**
- XY scale: **396.825396825 cm**
- Z scale: **200**

This makes each Unreal Landscape component correspond exactly to one existing
500 m Xinyi tile.

The source MOI DTM remains 20 m resolution. Sampling it into a 631 x 631 Unreal
heightfield satisfies Landscape topology; it does **not** magically increase
terrain accuracy.

### Offline contract PASS

Initial passing Unreal contract run:

`35676287874`

Later deterministic component-contract run:

`35677590649`

The uint16 height representation achieved a maximum round-trip height error of
about **7.8 mm**, safely below terrain-source accuracy.

### Lesson

Separate:

```text
source accuracy
from
runtime representation resolution
```

A denser Unreal heightfield is not a claim of denser source truth.

---

# Part IV — UE5.8 Landscape creation

## 10. Python could inspect Landscape, but not reliably create the required one

The promoted UE5.8 Python surface could interact with Landscape-related classes,
but a reliable from-zero, component-bearing Landscape creation path was not
available through Python alone.

Trying to force the whole workflow through editor UI automation would have made
the pipeline fragile and hard to verify.

The adopted solution is intentionally narrow:

`unreal/Plugins/XinyiLandscapeBridge`

This is an **Editor-only C++ bridge** around the engine's real
`ALandscape::Import` path.

Python still owns:

- source/provenance;
- CRS;
- ENU transform;
- sampling;
- uint16 encoding;
- topology;
- vertical alignment;
- hashes.

C++ only materializes the already-validated contract as a real Landscape.

---

## 11. UE5.8 API drift: `bCanHaveLayersContent`

The first real Windows bridge compile reached C++ compilation successfully and
then failed on:

```text
ALandscape::bCanHaveLayersContent
```

In UE5.8 that old direct member access was no longer valid.

The correct response was not to blame Visual Studio or invent another setter.

The bridge was updated to the UE5.8 edit-layer path:

- remove obsolete `bCanHaveLayersContent`;
- use `ELandscapeImportAlphamapType::Layered`;
- seed component topology before `Import`;
- let `ALandscape::Import` establish LandscapeInfo;
- fail if valid LandscapeInfo is absent.

### Operational lesson

A generic wrapper error originally said a compatible C++ toolchain might be
missing. That was misleading because UBT/UHT and MSVC had already proved the
toolchain worked.

Error messages should distinguish:

```text
toolchain discovery failure
from
C++ API compilation failure
```

---

## 12. Fresh reopen is mandatory

A successful save in the current Unreal process is not considered persistence
evidence.

For Landscape, the gate is:

```text
create Landscape
-> inspect component count / extent / transform
-> save
-> exit UnrealEditor-Cmd
-> start a new UnrealEditor-Cmd
-> load the map
-> re-inspect
```

The accepted Landscape must retain:

- 25 components;
- valid LandscapeInfo;
- extent [0, 0, 630, 630];
- locked world location;
- locked scale;
- expected 2.5 km Xinyi footprint.

This same “fresh process” rule is used for building runtime state.

---

# Part V — Unreal building representation

## 13. The 11,130-StaticMesh import path was a runtime architecture failure

The first UE building import attempt preserved the upstream 11,130 mesh
components as individual StaticMesh packages.

The result on a 16 GB Windows host was obvious:

- continuous Importing dialogs;
- continuous Saving Package activity;
- severe memory pressure / paging;
- extremely poor iteration behavior.

This was not a geometry failure.

It was a **runtime representation failure**.

The validated 11,130 components remain upstream truth, but that does not mean
Unreal should persist them as 11,130 independent content packages.

### Lesson

Source granularity and runtime granularity are different contracts.

---

## 14. Accepted current runtime candidate: 25 building tiles

The downstream runtime representation was changed to:

```text
11,130 validated ordinary components
-> apply surveyed ground-Z placement transforms
-> group by existing deterministic 500 m tile
-> concatenate within each tile
-> 25 tile-local runtime GLBs
-> 25 Unreal StaticMesh assets
-> 25 runtime tile actors
```

Important: this does **not** erase the per-component truth contract.

The offline contract still records expected Unreal world bounds for all 11,130
components.

The 25-tile representation is a runtime staging decision.

### Why this is better

It reduces:

- package count;
- import overhead;
- save churn;
- actor/content-management overhead;

while preserving:

- deterministic tile ownership;
- triangle accounting;
- source provenance;
- the ability to regenerate a tile from the upstream component set.

---

## 15. UE5.8 Python API drift: `get_extended_bounds()`

The 25 runtime GLBs actually imported successfully, but the post-import validation
failed 25/25 with the same Python exception:

```text
AttributeError:
'StaticMesh' object has no attribute 'get_extended_bounds'
```

The correct UE5.8 API was:

`StaticMesh.get_bounds()`

This was a validation-code bug, not an import failure.

### Lesson

When every tile fails with the identical post-import exception, do not immediately
rebuild source data. Identify the exact gate that failed.

The pipeline was improved with a resume path so expensive successful stages did
not have to be repeated.

---

## 16. Resume instead of restart

After the bounds API fix, the already-imported 25 StaticMesh assets and persisted
Landscape were reused.

The resume path validates existing assets, places them, saves, and fresh-reopens
the world.

Key script:

`tools/unreal_xinyi_v2/resume_runtime_world.ps1`

A later resume bug assumed the old downloaded artifact directory still existed.
The script was updated to restore the required artifact automatically from a
known successful workflow run when necessary.

### Lesson

Long multi-stage engine gates need resumability.

Every expensive stage should emit a receipt that allows the next stage to prove:

- which inputs it is resuming from;
- which prior state is trusted;
- what it is *not* repeating.

---

## 17. Runtime world persistence PASS

The successful local run ended with:

`XINYI_V2_RUNTIME_RESUME_OK`

That established, in the real installed UE5.8 environment:

- accepted MOI Landscape exists;
- 25 runtime building StaticMesh assets validate;
- 25 runtime building tile actors are placed;
- the world saves;
- a new UnrealEditor-Cmd process reopens the level;
- terrain + building actor locations + mesh references persist.

That is the point where Xinyi stopped being only an offline contract and became
a persisted Unreal world candidate.

---

# Part VI — Visual QA and screenshot backend

## 18. First screenshots were useful but misleadingly ugly

The first automated captures were gray-on-gray with a black background.

They were still useful for checking:

- broad placement;
- terrain shape;
- footprint layout;
- obvious district-wide burying/floating;
- tile-scale alignment.

But they were poor for human inspection of:

- building height hierarchy;
- slopes;
- shadows;
- silhouettes.

A readable whitebox pass added temporary QA materials:

- buildings: light/cool;
- terrain: darker green-gray.

This improved semantic separation, but the images still appeared nearly flat.

---

## 19. The trap: trying to fix lighting while the capture backend was effectively unlit

Several sensible presentation changes were tried:

- movable directional light;
- SkyLight;
- SkyAtmosphere;
- fixed exposure;
- height fog;
- forced Lit viewport mode.

The images remained nearly flat.

When the unattended editor-viewport path was forced harder into Lit mode, the
screenshot process crashed with Windows exit code:

`-1073741819`

At that point the editor-viewport screenshot backend was rejected.

### Important lesson

When presentation changes repeatedly fail to affect output, question the capture
path itself before continuing to tune lights/materials.

Do not spend hours “fixing lighting” if the renderer producing the evidence is
not the renderer you think it is.

---

## 20. Accepted visual QA backend: SceneCapture2D

The working replacement is:

```text
SceneCapture2D
-> TextureRenderTarget2D (RTF_RGBA8)
-> SCS_FINAL_COLOR_LDR
-> capture_scene()
-> export_render_target()
-> PNG validation
```

This route does not depend on editor viewport Lit/Unlit/debug state.

The capture owns its own:

- camera pose;
- FOV;
- render target;
- transient materials;
- movable sun;
- SkyAtmosphere;
- SkyLight;
- fog;
- manual exposure;
- final PNG export.

The output finally showed:

- real lit/shadowed building faces;
- readable height hierarchy;
- terrain relief;
- mountains;
- a non-black sky/background;
- a usable aerial footprint view.

Capture backend commit:

`9e24809c34b385e79df07b17ec32751c916e11cc`

### Rule going forward

Do not restore `AutomationLibrary.take_high_res_screenshot()` as the default
unattended Xinyi QA backend.

Use SceneCapture2D unless a separately validated capture path replaces it.

---

# Part VII — Failure patterns and how to diagnose them

## 21. Symptom -> likely cause

### Buildings district-wide buried by roughly the same large amount

Suspect terrain semantics or vertical datum first.

Do not immediately modify buildings.

For Xinyi, this symptom exposed DSM-vs-DTM misuse.

---

### A handful of pathological triangles only after Blender import

Suspect serialization-space triangulation / downstream representation.

Do not delete the triangles.

For Xinyi, this led from earcut to GEOS constrained Delaunay.

---

### Thousands of Importing / Saving Package operations

Suspect runtime asset granularity.

Do not accept “source component count == Unreal package count” as a requirement.

For Xinyi, 11,130 packages were replaced by 25 deterministic runtime tiles.

---

### Every imported tile fails on exactly the same Python AttributeError

Suspect validation API drift, not source data.

For Xinyi:

`get_extended_bounds()` -> `get_bounds()`

---

### Lighting changes produce almost no visible difference

Suspect the capture/render backend or view mode.

Do not keep tuning intensity indefinitely.

---

### Unreal save appears to succeed

Not enough evidence.

Require a separate fresh process to reopen and remeasure.

---

### Wrapper says “toolchain problem” after UBT/UHT clearly compiled code

Fix the wrapper error message.

Do not reinstall Visual Studio because a C++ API symbol changed.

---

# Part VIII — Non-negotiable guardrails

## 22. Things we do not do

Do not:

- repair production geometry inside Unreal;
- create per-building source exceptions;
- delete failing triangles;
- weaken tolerances after observing failures;
- lift buildings to a DSM;
- delete terrain beneath buildings;
- sculpt production terrain to fit buildings;
- infer terrain truth from pretty screenshots;
- infer geometry correctness from pretty screenshots;
- treat Blender preview meshes as Unreal production terrain;
- use 11,130 upstream components as 11,130 Unreal packages by default;
- trust same-process save success as persistence;
- restart a long engine gate when a safe resume is possible;
- use viewport screenshot automation as production QA evidence after its Xinyi
  failure history.

---

# Part IX — Repeatable playbook for the next district

## 23. Expansion checklist

When expanding beyond Xinyi, use this order.

### A. Freeze inputs

Record:

- source URL / dataset identity;
- CRS;
- source SHA;
- height semantics;
- dependency versions.

If any of these drift, rerun representative regression before trusting expansion.

### B. Representative geometry

Run a difficult representative set first:

- multipart;
- holes/courtyards;
- small/sliver shapes;
- large shapes;
- awkward repaired polygons.

Do not start full-city generation until serialization-space QA passes.

### C. Full-area building generation

Require:

- deterministic tile ownership;
- full source-part accounting;
- no silent skips;
- GLB reload;
- strict numerical QA;
- Blender imported-mesh QA.

### D. Terrain semantic validation

Before generating pretty terrain:

- prove the source is bare-earth if that is what placement needs;
- compare it against surveyed building ground;
- inspect median and tails;
- document any global datum offset.

Reject the source if its semantics are wrong.

### E. Independent Blender integration preview

Combine:

- immutable validated building GLBs;
- accepted terrain;
- measured building-base placement.

Use this to catch coordinate and elevation mistakes before Unreal.

### F. Build Unreal offline contract

Do not hand Unreal ad-hoc assets.

Emit:

- heightfield;
- topology;
- scale;
- extent;
- hashes;
- building runtime inputs;
- expected transforms / bounds.

Make the contract byte-deterministic where practical.

### G. Materialize in Unreal

Keep the engine-specific bridge narrow.

No source processing in C++.

### H. Fresh reopen

Every important saved state must survive a new editor process.

### I. Choose runtime granularity from evidence

Do not pre-decide package/actor count from source granularity.

Measure import behavior and host/runtime cost.

### J. Visual QA

Use a deterministic independent capture backend.

For current UE5.8 Xinyi work:

**SceneCapture2D is the accepted path.**

### K. Only then performance architecture

Proceed to:

- World Partition;
- streaming;
- HLOD;
- collision;
- cook;
- memory;
- draw calls;
- frame time.

---

# Part X — Current Xinyi state

## 24. What is solved

As of 2026-09-24:

### Building source/geometry

**PASS**

Production geometry contract is stable under the locked source and dependency
assumptions.

### Terrain source/integration

**PASS candidate**

MOI 2025 bare-earth DTM derivative path removed the old DSM burial signature and
passes current Xinyi alignment gates.

### Unreal offline contract

**PASS**

Deterministic Landscape and building runtime inputs are generated.

### Unreal Landscape materialization

**PASS in real UE5.8**

The Editor-only C++ bridge compiles against the installed engine and the
Landscape survives fresh reopen.

### Unreal building runtime representation

**PASS candidate**

25 deterministic 500 m runtime building tiles replace the rejected 11,130-package
path.

### Unreal world persistence

**PASS**

Landscape + 25 runtime building actors survive a fresh process.

### Visual QA capture

**PASS**

SceneCapture2D produces readable lit 1920 x 1080 QA views.

---

## 25. What is not solved yet

Do not interpret the current visual success as a complete runtime architecture
PASS.

Still pending:

- World Partition ownership / streaming behavior;
- HLOD strategy;
- collision policy;
- cook validation;
- runtime memory;
- draw-call / GPU cost;
- frame timing;
- production material/facade strategy;
- wider-Taipei scaling.

The next engineering question is no longer:

> “Can we get Xinyi into Unreal?”

It is:

> **“Can this persisted Xinyi world stream, collide, cook, and run within the
> target performance budget without breaking the validated world contract?”**

---

# Part XI — Reference map

## 26. Key repository references

Building geometry:

- `docs/architecture/xinyi-citygen-v2.md`
- `docs/architecture/xinyi-citygen-guardrails.md`
- `docs/xinyi-v2-full-xinyi-cloud-result.md`

Blender / preview:

- `docs/architecture/xinyi-whitebox-preview-pipeline.md`
- `docs/xinyi-v2-whitebox-preview-status.md`

Terrain:

- `docs/architecture/xinyi-terrain-integration-plan.md`
- `docs/xinyi-terrain-v0-dtm-result.md`

Unreal contract:

- `docs/architecture/xinyi-unreal-v2-contract.md`
- `docs/xinyi-unreal-v2-contract-result.md`
- `docs/architecture/xinyi-unreal-v2-landscape-bridge.md`
- `docs/xinyi-unreal-v2-stage1-result.md`

Primary Unreal local commands:

```powershell
# Full / fresh engine gate
powershell -ExecutionPolicy Bypass -File tools/unreal_xinyi_v2/fetch_and_run_local_gate.ps1

# Resume persisted 25-tile runtime world work
powershell -ExecutionPolicy Bypass -File tools/unreal_xinyi_v2/resume_runtime_world.ps1

# Deterministic readable visual QA
powershell -ExecutionPolicy Bypass -File tools/unreal_xinyi_v2/capture_views.ps1
```

Current tracking:

- Issue #8 — Unreal XinyiV2 runtime gate
- Draft PR #9 — Unreal XinyiV2 validated world runtime gate

---

## 27. The most important meta-lesson

Most of the expensive failures in this pipeline came from confusing two different
questions:

1. **Is the underlying world data/geometry correct?**
2. **Is the current tool/runtime representation appropriate?**

Examples:

- DSM burial was a data-semantics problem, not a building-placement problem.
- Blender sliver triangles were an export/triangulation problem, not an Unreal
  problem.
- 11,130 Saving Package events were a runtime-granularity problem, not a building
  geometry problem.
- flat gray captures were a capture-backend problem, not a lighting or terrain
  problem.

Before changing the world, identify which layer actually failed.

That discipline is the main reason the current Xinyi result can now be reproduced,
audited, and safely extended.
