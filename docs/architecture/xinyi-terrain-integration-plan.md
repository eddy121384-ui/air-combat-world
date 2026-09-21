# Xinyi Terrain Integration Plan

Status: planned next world-geometry layer. Not yet production-validated.

This document defines the contract for adding terrain beneath the already validated Xinyi building
whitebox without reopening solved building geometry.

## Goal

Add real elevation so the Xinyi whitebox reads as a district sitting inside actual terrain rather
than on a flat reference plane.

The terrain layer should make hillside transitions and the southeast urban edge legible while
preserving the already validated building geometry.

## Core rule

**Do not remesh buildings to make terrain work.**

The validated building meshes remain immutable.

Terrain integration should change only:

- terrain geometry / heightfield;
- terrain tile placement;
- building world-Z placement derived from a documented terrain anchoring policy.

Do not edit building XY geometry or triangulation as part of terrain integration.

## Terrain source requirements

Before implementation, lock an authoritative terrain dataset and record:

- provider;
- product / dataset name;
- bare-earth DTM vs surface DSM semantics;
- source CRS;
- horizontal resolution;
- vertical datum / units;
- license / usage terms;
- acquisition date;
- source file hashes.

Preferred semantics for this project are **bare-earth terrain elevation** rather than a surface model
that already includes buildings / trees.

Do not silently mix a DSM containing structures with our separately generated building meshes.

The exact source dataset is not considered production-locked until a terrain-source audit is
committed.

## Coordinate contract

Terrain must use the same world reference as buildings.

Target route:

```text
authoritative terrain source
-> source CRS validation
-> transform to EPSG:3826 if required
-> same WorldModel / ENU origin used by Xinyi buildings
-> deterministic 500 m ownership tiles
-> tile-local coordinates
-> terrain QA / serialization
```

Do not create a second arbitrary origin for terrain.

Terrain/building alignment is a hard gate.

## 500 m tile strategy

Reuse the existing 500 m city tile grid where practical.

Each terrain tile should have:

- deterministic tile index;
- exact ENU tile origin;
- source sample provenance;
- height range;
- output hash;
- seam checks against neighboring terrain tiles.

Terrain may use a regular grid internally even though buildings use polygon meshes.

The shared contract is tile ownership and world placement, not identical mesh topology.

## Building elevation anchoring

Current building geometry has validated local shape and height.

Terrain integration should place each building by a separate vertical transform.

A candidate general policy is:

```text
building footprint
-> sample terrain under footprint
-> derive one deterministic base elevation
-> apply that value as building world-Z offset
```

Candidate aggregation methods include median or another globally defined robust statistic.

Do not choose the final policy by visually tuning individual buildings.

Before locking the policy, test:

- flat urban blocks;
- buildings on moderate slopes;
- footprints spanning multiple terrain samples;
- buildings near sharp terrain transitions;
- courtyard buildings;
- high-rise / hero-neighborhood cases.

## Important slope problem

A single rigid building base plane cannot perfectly conform to sloped terrain.

Therefore the terrain milestone must explicitly decide how to handle:

- small terrain penetration on uphill edges;
- small floating gaps on downhill edges;
- retaining-wall / podium cases;
- very steep footprints that may require future hand-authored hero treatment.

For ordinary whitebox buildings, prefer a deterministic global placement policy over deforming the
building mesh.

Any exceptional hero treatment must be in the hero layer, not hidden inside ordinary citygen.

## Terrain QA

Terrain integration should add machine-readable checks for:

- finite heights;
- expected coordinate range;
- no NaN / nodata leakage into emitted mesh;
- deterministic sample counts;
- deterministic output hashes;
- no tile cracks / seam height mismatch;
- neighboring boundary samples agree;
- terrain bounds cover the intended building area;
- building base offsets are finite and reproducible;
- no unexplained large vertical jumps between adjacent urban tiles.

Visual review should include:

- full Xinyi aerial;
- southeast hillside transition;
- central urban core;
- hero / Taipei 101 neighborhood;
- at least one steep-slope sample.

## Preview milestone

The first terrain milestone does not need final Unreal Landscape authoring.

A good first gate is:

```text
terrain source
-> 500 m terrain tiles
-> building Z anchoring
-> Blender headless assembly
-> deterministic whitebox renders
```

PASS should mean:

- hills visibly appear where terrain source says they should;
- building XY placement remains unchanged;
- no tile seams;
- buildings sit at plausible elevations under one documented global policy;
- source / tile / transform accounting is complete.

Only then move the same elevation data into the Unreal import experiment.

## Unreal direction

For Blender QA / preview, terrain may be emitted as a regular mesh.

For Unreal production, evaluate a heightfield / Landscape representation rather than assuming the
Blender preview terrain mesh is the final runtime asset.

Unreal-specific questions belong in the Unreal gate:

- Landscape resolution / component layout;
- World Partition alignment;
- HLOD / streaming;
- collision;
- terrain material;
- runtime memory;
- cook size;
- tile / landscape seam behavior.

Do not couple these engine decisions back into source terrain processing unless measurements require
it.

## Scope boundary

Terrain v0 should include:

- terrain elevation;
- deterministic terrain tiling;
- building base-Z anchoring;
- terrain + building whitebox preview;
- QA / provenance.

Terrain v0 should **not** include:

- roads conforming to terrain;
- vegetation;
- facade dressing;
- final landscape materials;
- erosion detail;
- hero mountain sculpting;
- gameplay.

Those can come later after the coordinate / elevation contract is proven.

## Proposed order

1. audit and lock terrain source;
2. write terrain-source manifest and hash;
3. convert to the same EPSG:3826 / ENU frame;
4. generate deterministic 500 m terrain tiles;
5. validate seams and height statistics;
6. define and test one global building-base elevation policy;
7. render terrain + current Xinyi buildings in Blender;
8. record terrain gate result;
9. feed the same validated elevation contract into Unreal XinyiV2.

Do not expand to wider Taipei until this contract works cleanly on Xinyi.
