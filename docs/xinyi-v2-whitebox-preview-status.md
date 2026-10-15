# Xinyi Whitebox Preview — Current Status

Date: 2026-09-21 Asia/Taipei

## Current state

The Xinyi building whitebox exists as a district-scale visualization built from the same validated
25 GLB tiles that passed the Full-Xinyi cloud geometry gate.

This is no longer the old sparse 80-part representative sample.

The underlying building set is:

- 25 deterministic 500 m tiles;
- 11,130 mesh components;
- 485,936 triangles;
- Full-Xinyi numerical / serialization gate: PASS;
- Blender 5.2 imported-buffer gate: PASS.

Reference geometry result:

`docs/xinyi-v2-full-xinyi-cloud-result.md`

## What can currently be seen

The whitebox makes the following visible at district scale:

- dense low-rise blocks;
- high-rise clusters;
- complex source footprints;
- courtyards / holes retained by the validated geometry;
- broad urban-density changes across Xinyi;
- deliberate hero-suppressed gaps.

The preview should be read as **building massing only**.

## What is intentionally absent

### Terrain

No DTM / DEM terrain has been integrated yet.

The current visual ground is therefore not a representation of real elevation.

Any abrupt edge toward hillside areas, especially on the southeast side of the current Xinyi
coverage, should be treated as a terrain-layer gap until terrain is added and verified.

### Taipei 101 hero geometry

Taipei 101 ordinary-source geometry is intentionally suppressed.

The current whitebox does not yet reinsert the final hero model.

A gap around the hero location is therefore expected and must not be "fixed" by turning off hero
suppression.

### Roads / facades / materials / vegetation

These are outside the current milestone.

The current asset is a geometry / massing whitebox, not a finished city.

## Current preview implementation

Human-readable preview rendering is isolated from the geometry gate:

- `.github/workflows/xinyi-preview.yml`
- `tools/preview/xinyi_blender_preview.py`

The renderer is visualization-only and must not alter the validated mesh buffers.

Current intended preview style:

- Blender Workbench;
- single-color light grey buildings;
- dark background;
- shadows / cavity;
- full oblique;
- aerial oblique;
- top-down orthographic.

The preview workflow may evolve independently from the production geometry pipeline.

## Milestone boundary

This whitebox milestone means:

> Full Xinyi building massing can be generated deterministically, passes strict numerical and
> Blender import QA, and can be assembled into a district-scale visual preview.

It does **not** mean:

> Xinyi's final world geometry is complete.

The next world-building gap is terrain.

After terrain is integrated and building elevation anchoring is validated, the next engine gate is
the isolated Unreal `XinyiV2` import / performance spike tracked separately.

## Do not regress

Future agents must not respond to the absence of terrain by:

- changing validated building footprints;
- expanding buildings into hillside gaps;
- disabling hero suppression;
- adding per-building Z hacks;
- replacing the validated tile system;
- using visual preview output as a substitute for geometry QA.

Terrain is a separate layer and should be integrated as such.
