# Xinyi v2 full cloud geometry + Blender gate: PASS

Date: 2026-09-21 Asia/Taipei  
Draft PR: #6  
Issue: #5  
Validated commit: `4438d82fe2006710b0fda08e8a06989fba4c09a8`  
GitHub Actions run: `35557915078`

## Result

**Full Xinyi geometry and Blender cloud validation passed. Unreal import is the next gate.**

| Gate | Result |
|---|---:|
| Locked 80-part representative gate | PASS |
| Full Xinyi run 1 | PASS |
| Full Xinyi run 2 | PASS |
| Deterministic source hash / accounting / tile hashes / manifest / triangle / byte counts | PASS |
| Ordinary source polygon parts | 11,128 |
| Hero-suppressed polygon parts | 8 |
| Full-generation failures | 0 |
| 500 m tiles | 25 |
| GLB mesh components imported by Blender | 11,130 |
| Total triangles | 485,936 |
| Total GLB bytes | 14,853,448 |
| Blender failed meshes | 0 |
| Zero-area triangles | 0 |
| Non-manifold edges | 0 |
| Inconsistent edges | 0 |
| Wrong roof / base / wall triangles | 0 / 0 / 0 |
| Nonfinite vertices | 0 |
| Nonpositive volume | 0 |
| Wrong tile transforms | 0 |
| Blender overview renders | 3 / 3 produced |

Full tile manifest SHA-256:

`bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`

Projected WFS source SHA-256:

`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`

## Production method

The passing pipeline is:

```text
WFS EPSG:3826
-> pyproj / WorldModel / ENU
-> GEOS source repair
-> deterministic 500 m owner tile
-> tile-local coordinates
-> float32 serialization-space footprint quantization
-> GEOS revalidation
-> GEOS constrained Delaunay triangulation
-> trimesh extrusion
-> GLB export + reload
-> strict numerical / topology / cap / hole QA
-> Blender 5.2.0 LTS headless import
-> Blender imported-buffer QA
-> overview renders
```

No building-ID-specific geometry policy exists in this path.

## Why triangulation changed

The earlier serialization-space method using mapbox-earcut passed the locked 80-part representative
gate and the full numerical/GLB gate.

However, the first full-Xinyi Blender cloud audit found:

- 5 failed mesh components;
- 5 zero-area triangles;
- 15 non-manifold edges;
- 15 inconsistent edges.

Each failure was a very thin cap sliver that remained nonzero under the numerical path but collapsed
under Blender's float32 mesh arithmetic.

The production cap triangulation was therefore changed globally to GEOS constrained Delaunay via
Shapely. The historical earcut regression remains in the test suite; earcut is not silently erased.

After the change:

- locked 80-part representative gate remained PASS;
- full-Xinyi run 1 remained PASS;
- full-Xinyi run 2 remained PASS;
- deterministic hashes remained identical across both full runs;
- Blender zero-area / non-manifold / inconsistent-edge counts all became zero.

No triangle deletion, tolerance relaxation, footprint substitution or per-building fix was used.

## Blender signed-volume stabilization

After constrained Delaunay removed all sliver failures, Blender reported one remaining tiny solid as
nonpositive volume.

The solid had:

- finite vertices;
- triangular faces;
- zero degenerate triangles;
- manifold topology;
- consistent winding;
- correct cap / wall orientation;
- positive volume under the numerical mesh path.

The issue was the Blender audit's float32 scalar-triple-product accumulation against a distant
origin. For a very small solid offset tens of metres from `(0,0,0)`, cancellation changed the
computed sign.

The audit now recenters the vertices around their own local reference point before accumulating
signed volume. Closed-mesh volume is translation invariant, so this changes only numerical
conditioning; it does not move the mesh or relax acceptance.

The final Blender audit then passed all 11,130 imported mesh components.

## Determinism and performance

Full Xinyi run 1:

- runtime: 107.061 s
- peak RSS: ~329.5 MB
- failures: 0

Full Xinyi run 2:

- runtime: 106.499 s
- peak RSS: ~325.8 MB
- failures: 0

The following matched exactly between both runs:

- projected source hash;
- source accounting;
- tile manifest;
- every tile GLB SHA-256;
- total triangle count;
- total GLB byte count.

Blender 5.2.0 LTS full imported-buffer gate:

- 25 tile GLBs;
- 11,130 mesh components;
- 485,936 triangles;
- runtime: 163.610 s;
- peak RSS: ~2,613.8 MB;
- failed meshes: 0.

Three screenshots were emitted by the GitHub Actions artifact:

1. full-Xinyi top view;
2. full-Xinyi oblique view;
3. central-tile oblique view.

Mesa/EGL emits non-fatal `EGL_BAD_MATCH` messages on the GitHub runner, but all three renders are
successfully saved and the Blender job exits successfully.

## What is now considered solved

For the currently locked Xinyi source and dependency stack:

- projected-source precision;
- source-part accounting;
- holes / courtyards;
- invalid-source repair policy;
- tile ownership;
- tile-local float32 serialization;
- cap triangulation;
- GLB round-trip stability;
- imported Blender topology;
- Blender signed-volume conditioning;
- deterministic full-Xinyi regeneration.

Do not reopen these topics without new evidence or a source/dependency/policy change.

## What is not yet solved

This PASS is a geometry and Blender validation milestone. It is **not** an Unreal performance or
production acceptance result.

Still pending:

- Unreal XinyiV2 import;
- asset/actor granularity;
- coordinate / transform validation in Unreal;
- World Partition / HLOD integration;
- import / load / cook time;
- memory and streaming behavior;
- draw calls and frame-time profiling;
- fresh-editor reload stability;
- wider Taipei source partitioning / incremental regeneration.

## Next gate

Create an isolated Unreal `XinyiV2` import spike.

Do not overwrite legacy Xinyi assets. Freeze the current source hash, generator commit and manifest,
then validate engine placement and performance before expanding the same method to wider Taipei.
