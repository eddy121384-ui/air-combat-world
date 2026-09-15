# Taipei Greybox Core v0 — Result

> Branch: `feat/taipei-greybox-core` (from `research/city-pipeline-audit`, `main` untouched).
> Question answered: can the City Compiler turn real Taipei building data into
> game-engine-usable white massing automatically? **Yes — with documented limits.**

## 1. Actual pipeline (all rerunnable, stdlib-only, no Blender)

```text
node tools/taipei/fetch_sample.mjs            # WFS sample bbox -> sample_buildings.geojson + manifest
python tools/compiler/worldmodel.py           # GeoJSON -> WorldModel v0 (ENU + hero suppression)
python tools/compiler/build_tile.py           # WorldModel -> xinyi_tile_2km.glb (Layer A + hero)
node tools/smoke_greybox.mjs [--skip-fetch]   # full chain + godot install + scene check + unittest
python -m unittest discover -s tests          # 11 automated tests
```

No npm packages, no pip packages, no Blender, no manual mesh edits anywhere.

## 2. Source data

- Layer: `taipei_vioc:tp_building_height` (Taipei City Dashboard WFS 2.0.0, EPSG:4326, paged 5000).
- Endpoint used: `https://citydashboard.taipei/geo_server/taipei_vioc/ows` (first of two; no failover needed).
- Sample bbox: `121.5546,25.0247,121.5744,25.0427` (~2×2 km, Xinyi / Taipei 101).
- Fetched: 2026-09-11T21:33:08Z. Expected hits 11132 = received 11132, 0 non-polygon dropped.
- Heights: **100% `1_bud_high` surveyed** (no fallbacks triggered in this tile).
- Semantics: vendored verbatim from Taipei-Maps (`tools/taipei/vendor/buju/`), probe-verified 2026-08-20.
- Sample sha256: `cc70f0b890c66f298ce504840151abc05b457a5346e854f1accf19432268a848`

## 3. Outputs (this run)

| Artifact | Value |
|---|---|
| WorldModel buildings | 11132 (zero silent drops vs manifest) |
| Layer A extruded | **5819** white/grey flat-roof prisms, one merged mesh |
| Suppressed (hero complex) | **8** records (tower stack incl. true 512.43 m tower) |
| Fully skipped | 5305 buildings (every polygon zero-area or self-intersecting; part-level: 5296 zero-area + 10 complex self-intersecting) |
| Hero placeholder | `hero_taipei101_placeholder` at ENU (-90.78, 77.92) = known 101 coords, 508 m tall |
| GLB | `xinyi_tile_2km.glb` 7.1 MB, 2 meshes / 2 prims, 253,518 verts — sha `c2a00cd55dfda0e4` |
| WorldModel sha (this run) | `f96ce87b0526cb2f` (normalized JSON) |
| Godot | `godot/greybox/` project + scene + free-fly camera; tile auto-installed to `assets/` by smoke |
| Tests | **11/11 OK** (`python -m unittest discover -s tests`) |

Committed to git: scripts, tests, Godot project, docs, sample input (5 MB geojson + manifest).
Gitignored (regenerable): worldmodel JSON (13 MB), GLB binaries, tile reports, installed godot asset copy.

## 4. Coordinate convention

- GIS I/O: EPSG:4326. Game frame: theater-local ENU meters around `cities/taipei/city.yaml`
  origin (121.5654, 25.0330): `x = R·dlon·cos(lat0)`, `y = R·dlat`, Y-up GLB with north = −Z.
- Validated: ENU distance of 101→SYS Memorial Hall pair agrees with independent haversine <1%.

## 5. 101 replacement method + key data finding

- **Finding: WFS models 101 as a stack of 8 records** (512.43 / 467.28 / 450.89×2 / 408.84 /
  405.74 / 395.02 / 391.04 m) sharing near-identical centroids; three have degenerate
  point footprints. First matcher version (nearest single centroid) caught only a 129 m
  artifact and left three 400 m+ procedural boxes double-stacked with the placeholder —
  caught by inspection, fixed before commit.
- **Rule (deterministic, tested): suppress ALL features with min centroid distance ≤ 60 m
  AND height ≥ 300 m** (`HERO_SUPPRESS_RADIUS_M`, `HERO_SUPPRESS_MIN_HEIGHT_M` in
  `tools/compiler/worldmodel.py`). Neighbors (<300 m) stand. Test recomputes the set
  independently + asserts no remaining ≥300 m massing near the site (anti-double-stack).
- Placeholder anchored at the **known hero coordinates** (not an artifact centroid),
  base scaled from largest suppressed footprint, 508 m total (real 101 height).
- **Second finding: ~54% of WFS rings in this tile are zero-area point artifacts**
  (verified on raw GeoJSON independently of the compiler). They are filtered with logged
  reasons; Buju never noticed because MapLibre renders nothing for them. This likely
  applies citywide — future citywide runs should expect ~half of raw features to be
  non-extrudable points, not buildings.

## 6. Validation results (Phase 6)

All 9 required checks implemented in `tests/test_compiler.py`, 11/11 passing:
count>0; heights>0; 1.2–600 m plausibility; NaN-free ENU; meter-scale vs haversine;
hero set == rule recomputation (8 records incl. 512 m tower); anti-double-stack;
GLB parses (magic/version/2 meshes/placeholder 508 m); manifest hash == artifact;
WorldModel count == manifest count (no silent drops).
GLB determinism note: byte-for-byte GLB stability across runs is NOT asserted
(tooling may vary padding/order); logical determinism (ids/bounds/dimensions/hashes
of normalized intermediates) IS asserted. Recorded limitation.

## 7. Completion gates

- GATE A (re-fetch sample): PASS — `node tools/taipei/fetch_sample.mjs`.
- GATE B (WorldModel): PASS — 11132 buildings, zero drops.
- GATE C (2 km massing): PASS — 5819 extrusions, GLB parses.
- GATE D (101 suppressed): PASS — 8-record stack incl. true tower, anti-double-stack test.
- GATE E (placeholder at site): PASS — hero-point anchor, 508 m, exactly once.
- GATE F (Godot loads + shows): **STRUCTURAL PASS ONLY** — scene references resolve,
  GLB parses as the referenced PackedScene, camera script present. No Godot engine
  binary exists on the build machine (and installing one is out of scope), so the
  in-engine visual confirmation is pending. NOT claimed as complete.

## 8. Known blockers / next smallest tasks

1. **GATE F visual**: install Godot 4.2+ on a dev machine, open `godot/greybox`, confirm
   white massing + placeholder visible, fly camera. Smallest next task.
2. 10 self-intersecting complex rings skipped (0.2%) — needs lobe-splitting beyond quads
   or source-side fix; negligible for v0.
3. Zero-area rate citywide TBD — confirm ~50% holds outside Xinyi before budgeting tiles.
4. Next pipeline slices (in order): DEM heightfield → water mask → 1 bridge + 1 elevated
   segment → citywide scale-up. None started (per round scope).
