# Xinyi Whitebox Preview Pipeline

Status: visualization pipeline built on top of the validated Full-Xinyi geometry artifact.

This document defines how to turn the validated Xinyi building tiles into human-readable whitebox
previews without changing production geometry.

## Purpose

The whitebox preview exists to answer visual questions such as:

- does the district read like a coherent city massing?
- are high-rise / low-rise distributions plausible at a glance?
- are there obvious missing swaths, duplicated clusters or tile seams?
- where are hero-suppressed gaps such as Taipei 101?
- where will terrain materially change the silhouette?

It is **not** the geometry acceptance gate and must not mutate the geometry that already passed the
numerical / GLB / Blender validation pipeline.

## Frozen upstream geometry

The current validated upstream baseline is:

- validated geometry commit:
  `4438d82fe2006710b0fda08e8a06989fba4c09a8`
- passing cloud workflow:
  `35557915078`
- projected WFS source SHA-256:
  `c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`
- full tile manifest SHA-256:
  `bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`
- 25 deterministic 500 m tiles
- 11,130 emitted mesh components
- 485,936 triangles
- full numerical / GLB / Blender imported-buffer gate: PASS

Whitebox preview work should consume this artifact rather than regenerating geometry with a separate
algorithm.

## Data flow

```text
validated Full-Xinyi GLB artifact
-> download the same 25 tile GLBs
-> Blender 5.2.0 LTS headless import
-> do not alter vertices / faces / node transforms
-> apply visualization-only whitebox shading
-> choose deterministic overview cameras
-> render PNG previews
-> upload screenshots as a separate preview artifact
```

The current automation is:

- workflow: `.github/workflows/xinyi-preview.yml`
- renderer: `tools/preview/xinyi_blender_preview.py`
- artifact name: `xinyi-v2-whitebox-preview`

The preview workflow is intentionally separate from
`.github/workflows/xinyi-v2.yml`.

## Current whitebox style

The current renderer uses Blender Workbench for a fast technical preview:

- single light grey building color;
- dark viewport background;
- studio lighting;
- shadows enabled;
- cavity enabled;
- no facade materials;
- no textures;
- no terrain;
- no atmosphere / sky / gameplay lighting.

The point is readable massing, not presentation art.

## Standard preview cameras

The current script produces three deterministic views:

1. **full district oblique** — primary human-readable city massing view;
2. **high aerial oblique** — broader silhouette / density review;
3. **top-down orthographic** — map-like coverage and gap review.

These views may be refined, but changing them must never change production geometry.

## Hero suppression

The ordinary building pipeline intentionally suppresses designated hero geometry.

Therefore, a visible gap in the whitebox does not automatically mean source loss.

Taipei 101 is the important current example:

- ordinary-source 101 geometry remains suppressed;
- the hero asset is not yet reinserted in the whitebox preview;
- do not fill this gap by disabling hero suppression.

Hero reintegration is a separate downstream task.

## Terrain limitation

The current whitebox is a **building-only massing preview**.

There is no terrain layer yet.

This means:

- all building world elevation is effectively evaluated against the current flat reference plane;
- mountain / hill silhouettes are absent;
- the southeast edge of Xinyi can appear to end abruptly even where real terrain rises;
- empty or sparse hillside zones must not automatically be interpreted as missing building data.

See `docs/architecture/xinyi-terrain-integration-plan.md` before changing building geometry to address
those visual gaps.

## Preview vs validation

Keep these concepts separate.

### Geometry validation

The production gate answers:

> Is the generated geometry numerically and topologically valid after serialization and Blender import?

It lives in the citygen / Blender QA pipeline and is fail-closed.

### Whitebox preview

The preview answers:

> Can a human quickly read the district massing and identify the next world-building gaps?

A preview render failure does **not** invalidate a previously passing geometry artifact.

Conversely, a visually attractive preview does **not** override a failing geometry gate.

## Reproduction

The preview workflow consumes the locked passing Full-Xinyi artifact and invokes Blender headlessly.

Conceptually:

```bash
blender \
  --background \
  --factory-startup \
  --python tools/preview/xinyi_blender_preview.py \
  -- \
  --tiles <validated-full-xinyi-run>/tiles \
  --out <preview-output>
```

Do not export a second production mesh from the preview scene.

## What this stage proves

The current whitebox stage proves that the validated building tiles can be assembled into a coherent
district-scale massing view.

It does **not** yet prove:

- terrain correctness;
- building-to-terrain anchoring;
- Taipei 101 / hero reintegration;
- roads;
- facades;
- materials;
- Unreal placement;
- World Partition / HLOD;
- runtime performance.

Those remain separate gates.
