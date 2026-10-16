# Xinyi Terrain v0 — MOI 2025 DTM Candidate Result

Date: 2026-09-21 Asia/Taipei  
Branch: `feat/xinyi-terrain-v0`

## Decision

The Xinyi terrain pipeline now uses a cloud-readable derivative mirror of the
official MOI 2025 Taiwan 20 m bare-earth DTM.

The previous Copernicus GLO-30 DSM urban-ground prototype is rejected and remains
historical evidence only.

The MOI DTM candidate passes:

- source/provenance capture;
- deterministic 500 m terrain tiling;
- zero terrain seam failures;
- WFS surveyed-ground agreement;
- building-base anchoring;
- Blender 5.2 headless terrain + building preview.

## Source

Official dataset:

- title: `2025年版全臺灣20公尺網格數值地形模型DTM資料`
- Government Open Data dataset: `176927`
- semantics: bare-earth 20 m DTM
- mainland CRS: TWD97 / TM2 zone 121, EPSG:3826

The TGOS raw ZIP remains blocked from GitHub-hosted runners.

For cloud CI, the pipeline uses the derivative mirror:

- repository: `yhzkiki/taiwan-dtm-2025-terrarium-z13`
- format: z13 Terrarium XYZ PNG
- decoding: `R*256 + G + B/256 - 32768`
- mirror source manifests / hashes are captured by
  `tools/terrain/fetch_moi_2025_dtm_mirror.py`.

This is treated as a derivative transport of the official DTM, not as a different
terrain product.

## DTM vs surveyed WFS ground

All 11,132 WFS source features with surveyed `ground_elev_m` were compared against
the DTM at their representative points.

Before vertical datum alignment:

| Metric | DTM - WFS ground |
|---|---:|
| count | 11,132 |
| median | -0.342 m |
| median absolute | 0.401 m |
| P95 absolute | 1.279 m |
| > 1 m absolute | 720 |
| > 3 m absolute | 188 |
| > 5 m absolute | 32 |

A single global vertical offset of **+0.341955 m** is applied to the DTM.

After alignment:

| Metric | aligned DTM - WFS ground |
|---|---:|
| median | 0.000 m |
| median absolute | **0.173 m** |
| P95 absolute | **1.403 m** |
| minimum | -4.813 m |
| maximum | +12.045 m |
| > 1 m absolute | 857 |
| > 3 m absolute | 219 |
| > 5 m absolute | 41 |

This is dramatically different from the rejected DSM prototype, whose median
terrain surface sat roughly +17.36 m above surveyed building ground.

## Terrain output

- deterministic terrain tiles: 25
- tile size: 500 m
- terrain grid step: 20 m
- building XY geometry: unchanged validated Xinyi GLBs
- building components assembled in Blender: 11,130
- missing building elevation anchors: 0

Terrain tiles use the same Xinyi ENU / tile ownership contract as the validated
building pipeline.

## Building placement policy

After Blender imports the GLBs, it is operating in Blender Z-up world space.

The preview does not assume imported object origins or local bases are zero.
For each building:

```text
imported_world_base_z = measured minimum world-space base Z
surveyed_ground_z     = WFS ground_elev_m
delta_z               = surveyed_ground_z - imported_world_base_z
apply delta_z
re-measure world base
assert base == surveyed_ground_z
```

This is importer conditioning, not a per-building visual hack: every object follows
the same measured-base-to-surveyed-ground policy.

Run #29 confirms the post-placement errors are at floating-point noise scale
(example values around 1e-7 m).

## Blender result

Workflow run:

`35575152984`

Head commit:

`bc307341be8defbd622f2a5b45326aa29e7eda17`

Result:

- source-audit: PASS
- terrain build: PASS
- Blender axis probe: PASS
- building base-Z regression guard: PASS
- terrain + building render: PASS
- preview artifact upload: PASS

Preview artifact:

- name: `xinyi-terrain-v0-preview`
- artifact ID: `10627842026`
- SHA-256 digest:
  `1c4c3027c509eba16613a9cf8d34fb2ea68eb67f2665dac87007fcfe8a5ac3e8`

Rendered views:

- `01-xinyi-terrain-nw-to-se.png`
- `02-xinyi-terrain-sw-to-ne.png`
- `03-xinyi-terrain-aerial.png`
- `04-xinyi-terrain-top.png`

Visual review shows the southeast hillside / mountain mass rising as terrain rather
than appearing as an unexplained empty building-data gap. Buildings no longer show
the district-wide burial caused by the DSM prototype.

## Remaining caveats

This milestone does not claim centimeter terrain truth.

The DTM-vs-WFS comparison still has a small tail of outliers. Those should be
investigated statistically before expanding the terrain contract to all Taipei, but
they do not resemble the systematic +17 m DSM failure.

The next engine gate is still Unreal XinyiV2:

- import the same validated building tiles;
- derive Unreal Landscape/heightfield data from the same accepted DTM source;
- preserve the same world/tile transforms;
- validate fresh reload, streaming, HLOD and cook/runtime performance.

Do not regenerate or deform building geometry merely to fit terrain.
