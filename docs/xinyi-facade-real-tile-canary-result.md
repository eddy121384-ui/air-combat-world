# XinyiV2 façade metadata real-tile canary: PASS

Date: 2026-09-28 Asia/Taipei  
Issue: #12  
Draft PR: #13  
GitHub Actions run: `36410662228`  
Artifact: `xinyi-facade-real-tile-canary` (artifact ID `10963174563`)

## Result

**PASS_REAL_TILE_CANARY**

The offline façade metadata contract survived a real accepted Xinyi 500 m tile
without changing geometry.

The job refetched the projected WFS source and required the accepted SHA-256:

`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`

The fetched source matched exactly.

## Selection

The canary deterministically selected the densest ordinary 500 m owner tile by
source polygon-part count, with tile-key ordering as the tie breaker.

Selected tile:

`-002_-001`

Tile ENU origin:

`[-1000.0, -500.0]`

This tile contains:

- 1,422 ordinary source polygon parts
- 1,422 unique ordinary buildings
- 1,422 serialization components
- 30,260 vertices
- 55,300 triangles

Buildings are owned by centroid; they are not clipped to the tile boundary.
Therefore the combined local bounds extend slightly beyond the nominal 0..500 m
tile footprint. That is expected and consistent with the accepted ownership rule.

## Geometry equivalence

Baseline GLB:

- 1,027,480 bytes
- SHA-256 `66406b6299f81f037181cca69f691c3f98a790389cf797e56dea91947ca3770a`

Metadata GLB:

- 1,148,724 bytes
- SHA-256 `93d0d03c74cf27dd259d94afab4d47065eb1a965ff907a632899724fc4fde2f7`

Metadata overhead:

- 121,244 bytes
- approximately 11.8% over the baseline GLB for this dense tile

The gate required and passed:

- pre-export vertices exactly equal
- pre-export faces exactly equal
- pre-export bounds exactly equal
- post-GLB-round-trip vertices exactly equal
- post-GLB-round-trip faces exactly equal
- post-GLB-round-trip bounds exactly equal

This is strong evidence that the current COLOR_0 decoration path is downstream
visual metadata rather than a geometry mutation.

## Source-field coverage

For all 1,422 buildings in the selected tile:

- surveyed `floors` present: 1,422 / 1,422 = 100%
- surveyed `ground_elev_m` present: 1,422 / 1,422 = 100%

The visual floor-height derivation used:

- surveyed floors directly: 1,418 components
- estimated floor rhythm fallback: 4 components

Those four fallbacks occur because the surveyed height/floor combination produces
a visual floor height outside the canary's 2.4..6.0 m rendering range. Geometry
and surveyed floor data remain untouched; only the façade rhythm falls back.

## Metadata distribution

Diagnostic façade profiles:

- profile 1 / low-rise: 673 components
- profile 2 / mid-rise: 593 components
- profile 3 / high-rise: 156 components

Appearance seed:

- 255 distinct 8-bit seed values observed
- collisions are expected because the seed controls variation, not identity

Full RGBA tuples:

- 1,419 unique RGBA values before export
- 1,419 unique RGBA values after GLB reload

Only three components share a complete RGBA tuple with another component in this
1,422-building tile. That is acceptable for a compact visual-variation contract.

## What this proves

For one unusually dense real Xinyi tile, the current path can preserve
per-building façade intelligence while still producing one combined tile mesh.

The proven path is:

```text
accepted projected WFS
-> WorldModel source semantics
-> accepted GEOS / serialization-space geometry
-> surveyed ground-Z placement
-> per-building COLOR_0 metadata
-> concatenate to one tile mesh
-> GLB export / reload
```

## What this does not prove

This remains an offline transport canary.

It does not prove:

- UE5.8 Interchange preserves COLOR_0 under the intended explicit import policy
- wall normals are suitable for world-space horizontal façade coordinates
- Nanite preserves the visual behavior
- HLOD preserves or replaces the material contract correctly
- World Partition or packaged runtime streaming
- final Taipei façade art quality

Issue #8 remains the runtime architecture gate and is not bypassed by this result.

## Next step

After Issue #8 passes, run a one-tile UE5.8 façade canary with explicit source
vertex-color import, debug profile colors, floor-band material, angled-wall checks,
fresh reopen, and packaged-build verification.
