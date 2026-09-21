# Xinyi Citygen v2 — Production Geometry Method

Status: production-candidate method validated on the locked representative sample.

Primary evidence:
- `docs/xinyi-v2-serialization-space-result.md`
- Draft PR #6 / Issue #5

This document records the method discovered and validated during the Xinyi robust-whitebox work
so future agents do not regress to older geometry assumptions.

## Why v2 exists

The old Xinyi path mixed two separate problems:

1. the pinned EPSG:4326 WFS snapshot exposed coordinates at roughly 0.0001 degree precision,
   collapsing thousands of small building footprints;
2. the old custom geometry stack dropped holes and relied on handwritten cleanup / ear clipping.

A mature-library replacement alone was not enough. The production path also had to preserve source
precision and survive the actual float32 coordinate representation used by GLB / engine workflows.

## Validated data route

Use a precision-preserving projected source:

```text
Taipei WFS
-> EPSG:3826 response
-> pyproj / PROJ
-> WorldModel / ENU meters
```

The old pinned EPSG:4326 file remains valuable as a forensic regression fixture. It is not valid
production input for ordinary-building reconstruction.

## Geometry libraries

Use:

- Shapely / GEOS: polygon validity, repair, topology and footprint QA
- mapbox-earcut: triangulation
- trimesh: extrusion, mesh assembly and GLB export
- pyproj: projected CRS conversion

Do not reintroduce a custom triangulator, custom hole bridge, custom validity fixer or manual
per-building reconstruction into the production path.

## Deterministic 500 m ownership tiles

For each source polygon part:

1. Determine its owner from the source-part centroid in ENU meters.
2. Tile index is `floor(coord / 500)` independently for east and north.
3. Negative coordinates use mathematical floor, not integer truncation.
4. All repaired components produced from the same source part keep the same owner.
5. Do not clip a building at tile boundaries.
6. Tile origins are integer multiples of 500 m.

This provides stable ownership while allowing output coordinates to remain small.

## Serialization-space meshing

This is the critical rule that fixed the 76/80 strict-gate failure.

Do **not** triangulate a high-precision global footprint and cast mesh vertices to float32 afterward.

Instead:

```text
GEOS-repaired ENU footprint
-> subtract deterministic tile origin
-> quantize exterior + interior ring XY through float64 -> float32 -> float64
-> validate the quantized polygon with GEOS
-> if necessary, apply the single global GEOS repair policy
-> triangulate the representable polygon with earcut
-> extrude with trimesh
-> write tile-local POSITION values to GLB
-> place the result with a node / tile transform
```

The reason is numerical, not cosmetic. In the earlier 76/80 run, four extremely thin cap triangles
were valid in float64 but changed signed area after final float32 serialization, producing reversed
roof/base triangles. Meshing directly in serialization space removed that failure without deleting
triangles, changing tolerances or introducing per-building exceptions.

## Quantized-footprint policy

After tile-local float32 quantization:

- Revalidate with GEOS.
- If invalid, the only allowed general repair policy is the documented GEOS
  `make_valid(method="structure", keep_collapsed=False)` path.
- Requantize any polygonal output once, then require valid, area-bearing, disjoint polygon parts.
- Reject unacceptable collapse or fidelity loss.
- Never search through building-specific repair recipes.
- Preserve hole / courtyard count and topology within the documented global error budget.

The representative sample required no quantized-footprint `make_valid`, but the policy is defined
for full-city work.

## Coordinate / export policy

- GLB mesh POSITION values are tile-local.
- World placement is carried by deterministic node / tile transforms.
- Preserve the established ENU -> glTF Y-up convention.
- Actual exported/reloaded GLB buffers are part of the acceptance gate.
- Do not treat a pre-export float64 mesh as proof of final correctness.

## Strict geometry QA

Every accepted component must satisfy the current strict gate, including:

- finite vertices / valid indices;
- zero degenerate triangles;
- watertight topology;
- consistent winding;
- positive signed volume;
- expected base and roof elevation;
- roof normals up and base normals down;
- outward wall normals, including courtyard walls;
- volume consistent with footprint area × surveyed height;
- roof/base union covers the footprint;
- no missing / excess / overlapping cap area beyond the global numerical budget;
- hole / courtyard count retained and hole cores remain empty;
- actual GLB export/reload still passes the same checks;
- reconstructed ENU placement matches its tile transform.

Watertight + positive volume alone are insufficient.

## Representative evidence

The locked sample is 80 source polygon parts from 79 unique building IDs.

Validated serialization-space result:

- strict serialization-space solids: 80/80 PASS
- actual GLB export/reload: 80/80 PASS
- Blender imported-mesh QA: 80/80 PASS
- zero-area triangles: 0
- wrong roof/base/wall triangles: 0
- nonfinite vertices: 0
- 29 holes retained in 14 selected parts
- six visual categories reviewed: PASS
- output deterministic across local / CI reruns

The four IDs that previously failed after post-triangulation float32 casting now pass without any
ID-specific policy:

- `tp_building_height.296019`
- `tp_building_height.269609`
- `tp_building_height.295251`
- `tp_building_height.269018`

These IDs may appear in tests/evidence; they must never appear in production geometry policy.

## Full-Xinyi production gate

For full-Xinyi generation:

- account for every source polygon part;
- distinguish ready, repaired, rejected, hero-suppressed, emitted and failed outcomes;
- no unaccounted parts;
- no silent skips;
- run strict QA on every emitted component;
- fail closed if any emitted component fails;
- record tile/building/part/component IDs and reasons;
- record deterministic output hashes, timing, memory, counts and sizes;
- only after numerical success, perform Blender imported-mesh and visual sampling across difficult
  and representative tiles.

Only after full-Xinyi geometry and Blender sampling pass should Unreal `XinyiV2` import begin.

## Scaling to Taipei

The intended scaling strategy is not "make one giant Taipei mesh."

Reuse the exact same validated method district by district / tile by tile:

```text
validated source
-> deterministic 500 m tiles
-> same serialization-space geometry rules
-> same fail-closed QA
-> Blender automation / sampling
-> Unreal streaming / HLOD validation
```

Xinyi is the production template. Taipei expansion should mainly expand source coverage, not invent
a new geometry algorithm.
