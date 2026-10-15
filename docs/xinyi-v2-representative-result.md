# Xinyi Robust Whitebox v2 — Representative Gate Result

> Superseded for release readiness by the [strict representative gate](xinyi-v2-strict-representative-result.md):
> float64 80/80, but actual float32 GLB roundtrip **76/80** with four reversed roof/base
> pairs and overlapping caps. Blender was not run after this failed numerical gate.
> The report below preserves the earlier, narrower checks as historical evidence.

Date: 2026-09-20  
Branch: `feat/xinyi-robust-whitebox-v2`  
Draft PR: #6  
Tracking issue: #5  
Baseline: `main@08afe383d1b89a745f78f17d1930a75f045cec7a`

## Status

**NUMERICAL / RAW-GLB GATE: PASS on projected WFS source.**  
**BLENDER VISUAL GATE: PENDING.**  
**FULL XINYI: NOT STARTED.**  
**UNREAL V2 IMPORT: NOT STARTED.**

The branch stops at the intended representative-sample boundary. It does not
authorize full-Xinyi generation until official Blender MCP inspection confirms
that low-rise and complex buildings visually read as coherent masses.

## 1. Source diagnosis changed the pipeline

The original v0 snapshot requested GeoJSON in `EPSG:4326`. Its coordinates
were quantized to at most four decimal places, approximately a 10–11 m grid at
Taipei latitude. That collapsed 5,297 source polygon exteriors.

CI then queried the exact same WFS bbox and feature set in projected
TWD97/TM2 `EPSG:3826`:

| Metric | EPSG:4326 | EPSG:3826 |
|---|---:|---:|
| Features | 11,132 | 11,132 |
| Polygon parts | 11,136 | 11,136 |
| Parts with holes | 715 | 715 |
| Collapsed exterior parts | **5,297** | **0** |

All 5,297 features that collapsed in the geographic response recovered
area-bearing footprints in the projected response.

Therefore the Taipei WFS itself remains viable. The destructive component was
the 4326 GeoJSON output precision, not the underlying city geometry.

v2 now uses:

```text
Taipei WFS
→ GeoServer EPSG:3826 response
→ pyproj / PROJ
→ high-precision lon/lat metadata + theater ENU
→ Shapely / GEOS validity + make_valid
→ mapbox-earcut via trimesh
→ trimesh extrusion
→ numerical mesh gate
→ GLB
```

The pinned v0 4326 sample stays untouched as baseline / forensic evidence.

## 2. First representative run on old 4326 source — expected FAIL

Before the source-route correction, the v2 mature-library stack was run against
the old quantized snapshot.

Result:

- 80 selected source polygon parts;
- 75 passed;
- 5 failed;
- two hole cases were not watertight;
- three repaired cases still contained 2–4 zero-area triangles.

No cleanup exceptions were added for those five cases. The run was used as
evidence that source quantization must be fixed before judging the geometry
stack.

## 3. Representative run on projected source — PASS

Projected-source SHA-256 for the passing CI run:

`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`

Whole-source accounting before sample selection:

- source features: 11,132;
- Taipei 101 hero-suppressed features: 8;
- unsuppressed polygon parts scanned: 11,128;
- GEOS-ready without repair: 10,977;
- GEOS-repaired: 151;
- rejected: **0**;
- polygonal parts after repair: 11,130.

The deterministic 80-part representative sample included overlapping
categories:

- 46 concave;
- 14 with holes;
- 31 complex;
- 39 low-rise / small-footprint;
- 4 true multipart features;
- 8 high-rise;
- 21 simple rectangles;
- 27 mid-rise.

Mesh result:

- selected: 80;
- pass: **80/80**;
- failures: **0**;
- vertices: 2,594;
- triangles: 4,984;
- zero-area triangles: 0 by per-mesh gate;
- every mesh finite, watertight, winding-consistent and positive-volume;
- roofs +Y;
- bases -Y;
- source height preserved.

Representative build performance on GitHub Actions / Python 3.11:

- runtime: ~1.24 s;
- max RSS: ~174 MB;
- GLB size: ~128 KB.

A second raw-GLB reload outside the CI generation process found 80 geometry
objects and again found zero watertight / winding / volume failures.

## 4. Backward compatibility

The same CI run regenerated the v0 WorldModel and v0 tile before running tests.

All 16 tests passed, including the existing compiler tests and new v2 tests.
The WorldModel change is additive: outer-ring fields remain intact for v0,
while v2 gains holes, source CRS, original source coordinates and polygon-part
provenance.

PR #3 remains independent and unmerged.

## 5. Current gate

The numerical evidence is strong enough to advance to the required human
geometry inspection, but not beyond it.

Next action on the home workstation:

1. download/import `xinyi_v2_representative_80.glb`;
2. inspect through official Blender MCP;
3. deliberately inspect dense low-rise, concave, hole/courtyard, complex and
   multipart cases — not just towers;
4. confirm flat coherent roofs and building-like massing from multiple angles;
5. record screenshots and any failing building IDs.

If Blender visual QA fails, stop and diagnose the representative set.

If Blender visual QA passes, the next code step is **full-Xinyi v2 generation
in deterministic spatial tiles**, followed by raw/Blender QA again. Unreal
import remains after that gate.

## 6. Scaling note

The representative path already uses a deterministic 500 m tile key for
coverage reporting. The sample GLB keeps per-building nodes for inspection
only. A full-Xinyi/Basin build must batch geometry by spatial tile rather than
create one district-wide mesh or one Unreal asset per building.

No Houdini / CityEngine / lightweight-path winner is selected by this spike.
The mature-library path has earned the right to proceed to full-Xinyi only if
the Blender visual gate passes; Taipei Basin scaling still requires its own
generation/RAM/import/HLOD/streaming/mobile measurements.
