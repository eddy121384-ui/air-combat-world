# Xinyi Terrain v0 Prototype Result — Pipeline Works, DSM Ground Rejected

Date: 2026-09-21 Asia/Taipei  
Branch: `feat/xinyi-terrain-v0`

## Decision

The terrain processing / tiling / Blender assembly pipeline works, but the current
Copernicus GLO-30 **DSM must not be accepted as the urban ground surface**.

The production target remains an authoritative bare-earth DTM, currently the
MOI/TGOS 2025 Taipei 20 m terrain dataset.

## What worked

The prototype proved the following contracts:

- the existing Xinyi ENU / 500 m tile grid can be reused for terrain;
- 25 deterministic terrain tiles can be generated;
- terrain tile seams are deterministic and machine-checkable;
- all 11,130 validated building mesh components can be assembled with terrain in Blender;
- WFS `ground_elev_m` is available for all source building features used by the prototype;
- building geometry itself does not need to be remeshed for terrain integration.

## Blender axis note

The production GLB/game frame is:

```text
X = East
Y = Up
Z = -North
```

However, Blender's glTF importer converts imported world-space geometry to Blender's
native Z-up convention.

Therefore, when applying a building elevation **after Blender import** through
`obj.matrix_world`, the elevation translation belongs on Blender world **Z**.

A temporary experiment that applied the offset on Blender Y was incorrect and is not
valid evidence.

The preview script now includes a regression guard that checks every building's
Blender world-space base Z against its surveyed ground elevation.

## Why the first terrain preview looked sunken

The cloud-readable prototype source is Copernicus GLO-30 DSM.

A DSM contains surface objects such as roofs and vegetation. It is not equivalent to a
bare-earth DTM.

The prototype also performs a global vertical alignment using surveyed WFS roof
elevations. This was sufficient to exercise the coordinate pipeline, but it leaves the
urban DSM surface far above surveyed building ground elevation.

A dedicated diagnostic measured the aligned DSM surface around every source building
against WFS `ground_elev_m`.

Run #20 source-audit result:

| Metric | Terrain surface minus surveyed building ground |
|---|---:|
| samples | 11,132 |
| minimum | +4.39 m |
| P05 | +11.38 m |
| median | **+17.36 m** |
| P95 | +23.42 m |
| maximum | +46.61 m |
| > 1 m | 11,132 |
| > 3 m | 11,132 |
| > 5 m | 11,128 |
| > 10 m | 10,893 |

This quantitatively explains the visual "ground subsidence / swallowed building" effect:
the terrain surface is frequently at or near roof/vegetation height while building bases
are correctly anchored to surveyed ground elevation.

## Rejected fixes

Do **not** solve this by:

- lifting buildings to the DSM surface;
- using roof elevation as building base elevation;
- per-building Z hacks;
- deleting terrain under buildings;
- flattening individual terrain cells by hand;
- deforming validated building meshes.

Those approaches would hide the source-semantics problem instead of solving it.

## Correct next step

Use a bare-earth DTM with documented horizontal and vertical reference.

Target flow:

```text
official bare-earth DTM
-> source hash / CRS / vertical datum audit
-> same Xinyi ENU frame
-> deterministic 500 m terrain tiles
-> seam QA
-> compare DTM elevation with WFS ground_elev_m
-> building base-Z anchoring
-> Blender terrain + building preview
-> Unreal Landscape / runtime validation
```

Before accepting a DTM source, measure the same
`terrain_surface - surveyed_ground_elev_m` distribution. In ordinary urban areas the
residual should be small enough to justify one documented datum/alignment policy.

## Current production status

- building geometry pipeline: PASS
- full Xinyi Blender building QA: PASS
- terrain tiling pipeline mechanics: PROTOTYPE PASS
- Copernicus GLO-30 DSM as urban ground: **REJECTED**
- official MOI/TGOS 2025 Taipei 20 m DTM: production target, cloud download currently blocked on GitHub-hosted runner
- terrain + building production acceptance: NOT YET PASSED
