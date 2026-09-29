# XinyiLook v1 — Taipei visual pass over the validated Xinyi world

Branch: `feat/opus55-xinyi-visual-quality`  
Status: **look-dev candidate**. Offline pipeline + preview renders PASS in the cloud
container; Unreal stages are written, DXC-compiled and syntax-checked, and **still need
their first run on the UE5.8 workstation** (see "Run it" and "Not yet verified").

This is a visual layer. It does not change the accepted geometry, terrain, tile policy,
runtime streaming work, or any Issue #8 evidence. Everything lives under
`tools/lookdev/`, `adapters/unreal/lookdev/`, `/Game/XinyiLook` and a separate level
`/Game/XinyiLook/L_XinyiLook_Hero`.

## What changed on screen

| Layer | Before | After |
|---|---|---|
| Taipei 101 | missing (hero-suppressed hole) | 2.5k-tri hero at the WFS anchor: 25-storey base, 8 flared modules, top tower, pinnacle to 508 m, 26F coins / ruyi, warm floodlit modules at night |
| Buildings | grey extrusions, smoothed eaves | archetype façades from real data: tiled walkups / 華廈 with iron window cages, AC units, balconies, 騎樓 + signage bands, 頂樓加蓋 sheet metal; tower stone/porcelain; Xinyi curtain walls with per-pane reflection jitter; night windows (cool fluorescent / warm), office floor bands, crown lights |
| Roofs | flat | 29k instanced props on the real roof polygons: sheds, stainless tanks, solar heaters, antennas, condensers, machine rooms, cooling towers, BMU cranes, red aviation lights on ≥ 60 m roofs |
| Ground | uniform Landscape | OSM road SDF (crisp kerbs at any distance), sidewalks, parked scooters, parks, tracks / courts / lots; opaque paint geometry: lanes, double yellow, red kerbs, zebra crossings, stop lines, 機車停等區; 20.8k street / park trees (台灣欒樹 in late-September bloom) |
| Surroundings | black / empty | MOI-DTM mountain ring enclosing the basin; basin floor shaded from real WFS density (no fake street grid); far-LOD massing from the same WFS layer over the Taipei basin (318,327 records → 14,086 mid-rise cells + 6,650 tower records, 43 chunks, 207360 tris) |
| Light | QA whitebox rig | day / dusk / night presets shared by preview and Unreal (sun, SkyAtmosphere, SkyLight, height fog, manual exposure, MPC `Night` / `LitFrac` / `EmissiveScale`) |

Preview frames (same shader source as Unreal, see below): `docs/evidence/xinyi-look/`
(象山 view day / dusk / night, 101 close pass, low pass along 信義路 day / night, 松智路
canyon, rooftops over 吳興街, basin overview, NW skyline at night).

## Geometry contract (unchanged truth)

`tools/lookdev/build_look_tiles.py` re-emits each of the 25 runtime tiles and **fails
closed unless the triangle soup is bit-identical** (same triangles, order and float32
corner positions) to the accepted runtime tile from `build_contract.py`. Only vertex
sharing and attributes change:

- the accepted tiles share roof / wall vertices and carry POSITION only, so engines invent
  smoothed normals across 90° eaves — a big part of the "GIS" read. Look tiles carry flat
  normals, welded only where every attribute matches;
- `TEXCOORD_0` walls = (perimeter m, height above surveyed ground), roofs = tile-local m;
- `TEXCOORD_1` = (WFS height m, visual floor height m = height / floors);
- `TEXCOORD_2` = packed RGBA8 (archetype·16+variant, seed, weathering, flags).

Per-vertex data travels in UVs, never vertex colours, so the material does not depend on
the importer's vertex-colour policy (the risk PR #13's canary flagged). Packing is used
only for triangle-constant data; smoothly varying data (terrain weights, tree height) is
written as plain floats.

`build_all.py` re-checks the accepted source SHA (`c7ca8da1…`), tile manifest
(`bfaf5ab0…`) and terrain manifest (`3f6b5f31…`) before building anything.

Building groups: the WFS models one building as several height-zone records; records are
grouped (small / nested parts join their host) so a tower and its podium share one
archetype, palette and floor rhythm. 11,130 records → 4,137 groups
(華廈 1,484 · low 1,227 · walkup 829 · residential tower 411 · office glass 133 ·
department-store podium 53).

## Single shader source

`tools/lookdev/shaders/xinyi_city.hlsl` is written in the HLSL/GLSL common subset.

- Unreal: `tools/lookdev/ue_custom_code.py` wraps it in a struct inside one Custom node
  per material (no engine plugin, no shader directory mapping).
- Preview: `tools/lookdev/preview/viewer.js` prepends a GLSL macro prelude.
- Gate: `python tools/lookdev/check_hlsl.py --dxc <dxc>` compiles every material body in a
  UE-shaped wrapper for DXIL and SPIR-V, HLSL 2018 and 2021, warnings as errors.

## Performance discipline (iPhone 11 Pro-class lower bound)

| Item | Cost |
|---|---|
| Building materials | 1 opaque material, 1 draw per tile (25 + far chunks); ALU only, no textures; every pattern fwidth-filtered to its mean at distance (no shimmer, no mips needed) |
| Look tile vertices | 263k → 992k (flat shading minimum); 40 B/vertex with full-precision UVs ≈ 40 MB for all 25 tiles, streamed per 500 m cell. Dropping the invisible bottom caps would save ~25 % (not done: keeps the bit-identical claim simple) |
| Taipei 101 | 2,524 tris, 3 sections |
| Road paint | 95k tris, opaque, no decals, no transparency, draw distance 1.8 km |
| Trees | 20,780 × 28 tris, one HISM, LOD1/2, cull 1.5–2.6 km |
| Rooftop props | 29,461 instances, 9 HISMs (14–72 tris each), LOD1/2, cull 0.6–2.0 km, small props cast no shadows |
| Ground texture | one 2048² RGBA8 linear data texture (road SDF / green / class / surface) |
| Backdrop | 178k tris, no shadows; far-city data texture 1024² |
| Far city | 207360 tris in 43 × 2.5 km chunks, same material as Xinyi tiles, no shadows / collision; Xinyi source bbox skipped |
| Lights | 1 movable directional + sky light; night lighting is emissive only (no dynamic lights) |

## Run it (workstation)

```powershell
# 1. offline (restores locked inputs from data/lookdev_cache, no WFS/HF access needed)
python tools/lookdev/build_all.py
# 2-4. Unreal: assets -> level -> fresh-reopen check + SceneCapture2D hero shots
powershell -ExecutionPolicy Bypass -File tools/lookdev/run_xinyi_look.ps1 -SkipOffline
```

Receipts: `unreal/Saved/XinyiLook/unreal/look_{assets,level,capture}.report.json`  
Captures: `unreal/Saved/XinyiLook/unreal/captures/<shot>__<day|dusk|night>.png` — the
same camera poses as `tools/lookdev/preview/shots.json`, so every Unreal frame has a
like-for-like preview frame.

Preview in any Linux / Windows box with Node + Chromium:
`node tools/lookdev/preview/render.mjs --light day,dusk,night`.

## Not yet verified (be honest about the gap)

- The three Unreal stages have not run on UE5.8 yet. Likely first-run friction: Python
  property-name drift on `MeshBuildSettings`, `EditorScriptingMeshReductionOptions`,
  `SubobjectDataSubsystem`; landscape material re-assignment; Custom-node pin rebuild.
  Each stage fails closed with a receipt so the failing call is named.
- Unreal fog density / exposure mapping from the shared presets is first-order
  (`FOG_SCALE`, `log2(exposure)`); expect one calibration pass after the first capture.
  `MPC_XinyiLook.EmissiveScale` is the single emission trim.
- The preview approximates Unreal lighting (no GI, analytic sky); it is a look-dev tool,
  not evidence of Unreal output or performance.
- No device profiling yet. Numbers above are asset budgets, not frame times.

## Known limitations / next

- Landmarks other than 101 use generic archetypes (e.g. Sun Yat-sen Memorial Hall reads
  as a podium). A small landmark registry (look-only, like the 101 hero) is the next
  identity win.
- Far city covers Taipei City WFS only (bbox 121.455–121.645 E, 24.975–25.125 N);
  New Taipei falls back to a density mottle. Low-rise fabric (< 20 m p90) is shaded, not
  modelled, beyond the hero tiles.
- Sky has no clouds yet (Unreal SkyAtmosphere only); a cheap cloud layer would help the
  Ace Combat read at altitude.
- Street-level props (signs as geometry, lamps, scooters as meshes) intentionally not
  added: at aircraft speed the shader signage band + scooter speckle carry the read.
