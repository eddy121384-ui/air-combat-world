# Taipei City Pipeline Findings

Last updated: 2026-09-20

This document records durable, evidence-backed findings from the Taipei/Xinyi city-pipeline work so future agents and workstations do not repeat the same experiments.

## Scope and product framing

- **Xinyi is a production-method test tile, not the final gameplay map.**
- The intended playable theater is the **Taipei Basin**. At fighter-aircraft speed, a ~2×2 km Xinyi tile is only a short traversal.
- Any production workflow chosen from the Xinyi experiments must have a credible path to scale across the Taipei Basin without manual district-by-district reconstruction.
- The target is not street-level GTA fidelity everywhere. The goal is geographically convincing, gameplay-usable Taipei at air-combat viewing distances, with selectively higher fidelity for important combat/recognition zones and hero landmarks.

## Assets and foundations worth preserving

The following work remains valuable regardless of the final geometry-generation tool:

- Taipei WFS/GIS acquisition and source-data handling.
- Surveyed building heights.
- WorldModel abstraction and theater-local ENU meter coordinates.
- Taipei 101 hero metadata, real-world placement and 508 m validation target.
- Xinyi bounds/scale validation.
- UE5.8 import, level-build and fresh-reopen verification workflow.
- Mobile-first raster rendering direction.
- Official Unreal MCP / Blender MCP workflow for independent validation and inspection.

## Current Xinyi data counts

Pinned sample observations:

- Source features: **11,132**
- Hero-suppressed features around Taipei 101: **8**
- Buildings currently extruded: **5,819**
  - low: 3,289
  - mid: 2,250
  - high: 280
- Approximately **5,296** inputs are reported as `zero_area` skips.
- The `zero_area` discrepancy is **unresolved** and must be audited separately from winding/normal repair.

## Proven geometry findings

### 1. Original cap winding was wrong

The custom geometry path in `tools/compiler/geo.py::extrude()` authored roof/base cap orientation incorrectly for the majority of normal real-data footprints.

Observed effect:

- roofs could face downward,
- bases could face upward,
- standard back-face culling then made buildings look like open cardboard/paper sculpture from aerial views.

This is an upstream geometry-authoring problem. Blender and Unreal correctly expose the authored geometry; they are not the demonstrated primary cause.

Evidence:
- Issue #2: https://github.com/eddy121384-ui/air-combat-world/issues/2
- Draft PR #3: https://github.com/eddy121384-ui/air-combat-world/pull/3

### 2. Simple fixture tests are insufficient

A minimal global cap-order repair makes rectangle/L-shaped unit fixtures pass, but **real GIS data still contains failures**.

On the repaired branch / draft PR #3:

- 18/18 compiler tests pass.
- Yet independent Blender/raw-GLB inspection still finds:
  - 190 downward-facing roof triangles,
  - 190 upward-facing base triangles,
  - 20 zero-area triangles.
- The global swap fixes most roofs but flips the small subset that were previously oriented the other way.

Therefore:

> Passing simple synthetic tests does not prove the real-data city mesh is robust.

### 3. Low-rise visual geometry still shows folded/triangular artifacts

Blender inspection of the regenerated Xinyi GLB shows many low-rise masses that visually read as triangular/folded rather than clean building solids.

This indicates that the remaining problem is not merely Unreal material sidedness or lighting. The likely risk area remains the custom polygon processing chain:

`_clean_ring() → triangulate()/ear clipping → extrude() → GLB`

The exact source of all residual visual failures is not yet proven.

### 4. Flat-shaded export duplicates vertices

The current GLB export path duplicates vertices per triangle for flat shading.

Therefore, raw index-edge incidence cannot be used directly to claim a mesh is non-manifold. Position welding (within an explicit tolerance) is required before using edge-pair counts as a topology test.

## Known custom-pipeline risk areas

The current hand-built geometry stack includes:

- ring cleanup / duplicate removal,
- hole bridging,
- custom ear clipping,
- special bow-tie handling,
- extrusion,
- flat-shaded GLB export.

These areas are now considered **production risk**, especially when applied to messy real-world GIS footprints.

The project should not continue expanding custom computational-geometry logic merely because it is possible. Mature city/GIS geometry workflows should be preferred when they satisfy the product requirements.

## Unreal / import lessons already paid for

The following UE5.8 automation gotchas are established project knowledge:

- Unreal Interchange may enable Nanite on imported meshes by default.
- Clean/mobile-path assets must explicitly keep Nanite off.
- Same-session success is not sufficient persistence proof; use a fresh-process reopen verification gate.
- `EditorLevelLibrary.new_level()` can log a failure for an existing destination without raising a Python exception.
- Positional `unreal.Rotator(...)` construction caused incorrect sun orientation in prior automation; explicit attribute assignment/read-back verification was required.
- Do not enable SM6, Nanite, Lumen or VSM merely to hide geometry/import problems.
- Do not use two-sided materials as a workaround for upstream winding defects.

## Architecture / production direction

### Preserve

- GIS/WFS source truth.
- WorldModel.
- ENU coordinate model.
- hero-building metadata.
- UE validation/import knowledge.

### Re-evaluate

The custom `clean → triangulate → extrude → GLB` geometry generator should be treated as a **baseline / fallback / research implementation**, not assumed to be the Taipei Basin production generator.

### Principle

> **Do not reinvent mature city-generation geometry workflows unless the product truly requires it.**

The next production-path evaluation should compare established workflows rather than immediately extending the custom triangulator.

Candidate paths include:

1. repaired/custom compiler as baseline,
2. Houdini procedural-city workflow,
3. CityEngine/GIS procedural workflow.

No winner has been selected yet.

## Scaling requirement

Every candidate workflow must answer:

> Can this scale from the Xinyi test tile to the full Taipei Basin without manual district-by-district reconstruction?

A workflow that produces a beautiful 2×2 km demo but cannot economically scale across the basin is not suitable for Skyfront production.

## Tool roles

Provisional role split:

- **GIS / WorldModel:** source truth and spatial metadata.
- **Procedural city generator:** bulk ordinary-city geometry.
- **Blender:** hero-building work, cleanup, inspection and mesh QA — not the master scene for the entire Taipei Basin.
- **Unreal Engine:** playable world assembly, rendering, materials, HLOD/streaming, collision, PCG dressing, lighting and gameplay.
- **AI agents:** orchestration, technical-art assistance, rule authoring, QA and hero-asset assistance — not manual per-building reconstruction of the entire city.

## Unresolved work

Separate future investigations:

1. Residual real-data cap/triangulation failures in draft PR #3.
2. Why 11,132 source features result in only 5,819 extrusions / ~5,296 `zero_area` skips.
3. Production-path bake-off using a representative Xinyi subset.
4. Only after a scalable geometry path is selected: facade, rooftop, hero-building and visual-fidelity work.

## Current review state

- Issue #2 is open.
- PR #3 is intentionally **Draft / Do Not Merge** while the raw-geometry gate fails.
- Do not proceed to Unreal reimport from PR #3 until the raw GLB geometry gate is resolved.
