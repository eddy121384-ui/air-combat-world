# XinyiV2 Façade Metadata Offline Canary

Status: experimental downstream canary. This is **not** part of Issue #8 runtime acceptance.

## Purpose

Prove that per-building visual metadata can survive the existing XinyiV2 strategy of
combining many validated building components into a small number of tile meshes.

The accepted geometry remains authoritative:

- WFS footprint / height / surveyed ground semantics are unchanged;
- 500 m source-tile ownership is unchanged;
- GEOS constrained Delaunay triangulation is unchanged;
- ENU -> game -> Unreal coordinate mapping is unchanged;
- Issue #8 still decides whether the 25-tile runtime architecture is acceptable.

This canary adds visual metadata only.

## Why building identity is split from GPU appearance data

The runtime material does not need a semantic building ID. IDs remain in a sidecar
record for QA, PCG, hero replacement, gameplay lookup and later tooling.

The mesh carries only compact values the shader needs to render a façade.

A future sidecar should retain at least:

```text
building_id
canonical_component_key
tile
footprint / centroid reference
height_m
ground_elev_m
top_elev_m
floors
facade_profile_id
appearance_seed
```

## COLOR_0 v1 contract

Every vertex belonging to one building receives the same RGBA value before tile
concatenation:

| Channel | Meaning | v1 encoding |
|---|---|---|
| R | façade profile | integer profile ID 0..255 |
| G | appearance seed | first byte of SHA-256(building_id) |
| B | visual floor height | 2.4..6.0 m mapped to 0..255 |
| A | surveyed-ground floor phase | frac(ground_elev / floor_height) mapped to 0..255 |

Profile IDs in this canary are deliberately coarse and diagnostic:

- 0 generic / invalid
- 1 low rise
- 2 mid rise
- 3 high rise

These are not production Taipei art classifications.

## Floor rhythm

When a sane surveyed floor count exists:

```text
floor_height = building_height / floors
```

If that value is outside the visual contract range, the canary estimates a floor
count from a 3.2 m default and clamps only the **visual rhythm** to 2.4..6.0 m.
Building geometry is never resized.

For a material using world-space height:

```text
floor_position = frac(world_z_m / floor_height - floor_phase)
```

The phase makes the periodic façade pattern start at each building's surveyed
ground instead of at world Z=0.

## Horizontal façade coordinate

v1 does not reserve a UV channel for metadata. A future Unreal material can derive
a wall-local horizontal coordinate from world position and a horizontal wall
normal:

```text
T = perpendicular(horizontal_wall_normal)
wall_u = dot(world_xy, T)
bay_position = frac(wall_u / bay_width + seed_phase)
```

This avoids a UV unwrap requirement for arbitrary GIS footprints.

A later Unreal canary must explicitly verify hard wall normals at angled corners
before relying on this method.

## Import policy

The Unreal Interchange canary must explicitly import source vertex colors using a
Replace/source-data policy. It must not depend on an editor default.

UV channels remain reserved for real texture/lightmap use until a separate
round-trip contract proves a need for generic numeric payloads there.

## Offline acceptance

The test gate must prove:

1. WorldModel preserves floors and surveyed ground/top elevation fields.
2. RGBA encoding is deterministic.
3. Applying COLOR_0 does not change vertices, faces or bounds.
4. Two differently encoded buildings can be concatenated into one mesh.
5. GLB export/reload preserves triangle count, bounds and both distinct RGBA values.

Passing this document's gate is evidence only for metadata transport through the
Python/Trimesh/GLB path. It is not evidence for Unreal Interchange, Nanite, HLOD,
World Partition, packaged runtime streaming or material correctness.

## Next engine canary

Only after Issue #8 runtime architecture passes, take one 500 m tile and verify in
UE5.8:

1. explicit Interchange vertex-color import;
2. debug material displaying profile IDs;
3. debug floor bands aligned to each building ground;
4. angled-wall coordinate behavior;
5. save, exit, fresh reopen and re-check;
6. packaged build check before any visual-polish milestone.

No commercial façade art work is required for this canary.
