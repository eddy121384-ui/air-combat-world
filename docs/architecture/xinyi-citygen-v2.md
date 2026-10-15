# Xinyi Citygen v2 — Production Geometry Method

Status: **full Xinyi geometry + cloud Blender gate PASS**.

Current production evidence:
- `docs/xinyi-v2-full-xinyi-cloud-result.md`
- Draft PR #6 / Issue #5
- workflow run `35557915078`
- validated commit `4438d82fe2006710b0fda08e8a06989fba4c09a8`

Historical representative evidence:
- `docs/xinyi-v2-serialization-space-result.md`

This document records the current method so future agents do not regress to earlier source,
precision, triangulation or QA assumptions.

## Why v2 exists

The old Xinyi path mixed several independent failure classes:

1. the pinned EPSG:4326 WFS snapshot exposed coordinates at roughly 0.0001 degree precision,
   collapsing thousands of small building footprints;
2. the old custom geometry stack dropped holes and relied on handwritten cleanup / ear clipping;
3. triangulating high-precision coordinates before the final float32 cast could reverse extremely
   thin cap triangles after GLB serialization;
4. after those problems were fixed, full-Xinyi Blender import still exposed five float32-degenerate
   sliver triangles produced by earcut even though the numerical GLB gate passed;
5. Blender-side signed-volume accumulation against a distant origin could falsely report a tiny
   positive solid as negative because of float32 cancellation.

The current method addresses each class globally. There are no building-ID-specific fixes.

## Validated data route

Use a precision-preserving projected source:

```text
Taipei WFS
-> EPSG:3826 response
-> pyproj / PROJ
-> WorldModel / ENU meters
```

The old pinned EPSG:4326 file remains a forensic regression fixture. It is not valid production
input for ordinary-building reconstruction.

Locked projected-source SHA-256:

`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`

## Geometry libraries

Current production roles:

- Shapely / GEOS: polygon validity, repair, topology, footprint QA **and constrained Delaunay cap triangulation**
- trimesh: extrusion, mesh assembly and GLB export
- pyproj: projected CRS conversion
- mapbox-earcut: retained only to reproduce historical regression behavior in tests/evidence

Do not reintroduce a custom triangulator, hole bridge, validity fixer or manual per-building
reconstruction.

## Deterministic 500 m ownership tiles

For each source polygon part:

1. Determine its owner from the source-part centroid in ENU meters.
2. Tile index is `floor(coord / 500)` independently for east and north.
3. Negative coordinates use mathematical floor, not integer truncation.
4. All repaired components produced from the same source part keep the same owner.
5. Do not clip a building at tile boundaries.
6. Tile origins are exact integer multiples of 500 m.

This preserves stable source ownership while keeping mesh coordinates small.

## Serialization-space meshing

This rule remains mandatory.

Do **not** triangulate a high-precision global footprint and cast the finished mesh to float32.

Use:

```text
GEOS-repaired ENU footprint
-> subtract deterministic tile origin
-> quantize exterior + interior ring XY through float64 -> float32 -> float64
-> GEOS validate
-> if necessary, apply the single documented GEOS repair policy
-> GEOS constrained Delaunay triangulation
-> trimesh extrusion
-> GLB tile-local POSITION
-> deterministic node / tile transform
```

The earlier 76/80 result at `3b963a4` proves why triangulation-before-float32 is unsafe.

## Why production triangulation is GEOS constrained Delaunay

The representative serialization-space sample passed 80/80 using earcut, but the first full-Xinyi
Blender cloud gate exposed five mesh components with one float32-degenerate sliver triangle each.
Those degeneracies also caused 15 non-manifold / inconsistent-edge findings after Blender import.

Switching only the cap triangulation stage to
`shapely.constrained_delaunay_triangles(...)` removed the sliver failure class while preserving:

- locked 80-part representative PASS;
- full source accounting;
- holes / courtyards;
- deterministic tile hashes;
- 25-tile output structure;
- total full-Xinyi triangle count: 485,936.

No triangle deletion, geometry tolerance relaxation or per-building policy was introduced.

The historical earcut regression remains explicitly covered in tests so future agents can see why it
was replaced rather than silently forgetting the old failure.

## Quantized-footprint policy

After tile-local float32 quantization:

- Revalidate with GEOS.
- If invalid, the sole general repair path is
  `make_valid(method="structure", keep_collapsed=False)`.
- Requantize polygonal repair output once, then require valid, area-bearing, disjoint parts.
- Reject unacceptable collapse or fidelity loss.
- Never search through per-building repair recipes.
- Preserve hole / courtyard count and topology under the documented global numerical budget.

## Coordinate / export policy

- GLB POSITION values are tile-local.
- World placement is carried by deterministic node / tile transforms.
- Preserve the established ENU -> glTF Y-up convention.
- Actual exported/reloaded GLB buffers are part of acceptance.
- Do not treat a pre-export float64 mesh as proof of final correctness.

## Strict geometry QA

Every accepted component must satisfy the current strict gate:

- finite vertices / valid indices;
- zero degenerate triangles;
- watertight topology;
- consistent winding;
- positive signed volume;
- expected base and roof elevation;
- roof normals up / base normals down;
- outward wall direction, including courtyard walls;
- volume consistent with footprint area × surveyed height;
- roof/base footprint coverage;
- no missing / excess / overlapping cap area outside the global numerical budget;
- hole / courtyard count retained and hole cores empty;
- actual GLB export/reload passes the same invariants;
- reconstructed ENU placement matches the tile transform.

Watertight + positive volume alone are insufficient.

## Blender cloud QA

Official Blender 5.2.0 LTS is run headlessly in GitHub Actions after the full numerical gate.

The full-Xinyi audit imports all generated tile GLBs with geometry unmodified and checks every mesh
component. It is not a small sample gate.

Validated result at workflow `35557915078`:

- tiles: 25 / 25
- imported mesh components: 11,130
- imported triangles: 485,936
- failed meshes: 0
- nonfinite vertices: 0
- non-triangle faces: 0
- zero-area triangles: 0
- wrong roof triangles: 0
- wrong base triangles: 0
- nonvertical wall triangles: 0
- non-manifold edges: 0
- inconsistent edges: 0
- nonpositive volume: 0
- wrong tile transform: 0

Three overview renders are also emitted as CI artifacts.

### Blender signed-volume numerical policy

Blender mesh coordinates are float32. For very small solids far from the local origin, directly
summing scalar triple products against `(0,0,0)` can catastrophically cancel.

The Blender QA therefore translates vertices around their own centroid **only for the signed-volume
calculation**, then performs the same orientation-sensitive volume sum. Closed-mesh volume is
translation invariant, so this is numerical stabilization rather than a relaxed tolerance or a
geometry repair.

## Full-Xinyi validated result

At commit `4438d82fe2006710b0fda08e8a06989fba4c09a8`:

- source features: 11,132
- ordinary source polygon parts: 11,128
- hero-suppressed polygon parts: 8
- failures: 0
- tiles: 25
- triangles: 485,936
- GLB bytes: 14,853,448
- manifest SHA-256:
  `bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`
- run 1: 107.06 s, peak RSS ~329.5 MB
- run 2: 106.50 s, peak RSS ~325.8 MB
- source hash, accounting, tile manifest, individual tile hashes, triangle counts and byte counts:
  identical across both full runs

Blender 5.2.0 LTS then imported all outputs and passed the full imported-buffer gate.

## Next gate: Unreal XinyiV2

Geometry research is no longer the next task.

The next isolated, reversible phase is an Unreal XinyiV2 import/performance spike:

1. freeze the current generator commit, source hash and tile manifest;
2. import to a separate `XinyiV2` asset path without overwriting legacy assets;
3. validate tile transforms and whole-district placement;
4. measure asset/actor count, import time, editor memory, visible triangles, draw calls and streaming;
5. test fresh-editor reload / cook stability;
6. evaluate World Partition / HLOD strategy;
7. keep the target rendering constraints explicit; do not use engine features to conceal geometry defects.

Only after Unreal Xinyi passes should the same production tile method expand toward wider Taipei.

## Scaling to Taipei

Do not make one giant Taipei mesh and do not invent a new geometry algorithm merely because the
coverage is larger.

Scale the validated unit:

```text
precision-preserving projected source
-> deterministic 500 m tiles
-> serialization-space footprint
-> GEOS constrained Delaunay
-> trimesh extrusion
-> strict numerical / GLB gate
-> Blender headless cloud gate
-> Unreal streaming / performance validation
```

Xinyi is now the production template. Taipei expansion should primarily expand source coverage,
caching, incremental regeneration and streaming orchestration—not reopen solved geometry problems.
