# External Prior Art — GIS/OSM/Overture/CityGML/DEM → 3D City → Game Engine

> Purpose: Phase 2 survey for City Compiler (air-combat world). Each entry is
> classified **ADOPT** (use directly) / **ADAPT** (reuse design/code with changes) /
> **REFERENCE** (ideas only) / **REJECT** (don't use). Data pulled 2026-09-11.
> ⚠️ = GPL/copyleft caution — do not copy code into the game without legal review.

## Verdict matrix (TL;DR)

| Project | License | Activity | Verdict |
|---|---|---|---|
| tordanik/OSM2World | MIT | Active (push 2026-09-09, ★780) | **ADAPT** |
| vvoovv/blosm | ⚠️ GPL-3.0 | Active (push 2026-09-08, ★2110) | **REFERENCE** (license-blocked) |
| romanshuvalov/rsgeotools (rvtgen3d) | BSD-3-Clause | Stale (last push 2020-09-29, ★132) | **ADAPT** |
| willjoe/terranian | None / all-rights-reserved | New, inactive-ish (created 2026-08-18, ★0) | **REFERENCE** (ideas only, no code reuse) |
| Project-PLATEAU SDK for Unity / Unreal | MIT | Active (Unity 2026-06 / Unreal 2025-06) | **ADOPT** (Japan tiles) / **ADAPT** (pipeline pattern) |
| MIERUNE/plateau-gis-converter | MIT | Active (2026-09-07, ★103) | **ADAPT** |
| shiena/godot-plateau | MIT | 2026-07, ★8 | **REFERENCE** |
| domlysz/BlenderGIS | ⚠️ GPL-3.0 | Active (2025-12, ★9370) | **REFERENCE** (license-blocked) |
| citygml4j/citygml-tools | Apache-2.0 | Active (2026-05, ★165) | **ADAPT** |
| OvertureMaps/data + reearth/reearth-buildings | MIT + MIT | Active (2026-08 / 2026-09) | **ADAPT** |
| cesiumgs/cesium-unreal (+ 3D Tiles) | Apache-2.0 | Active (2026-09) | **REFERENCE** (streaming std); **REJECT** as runtime dep |

---

## 1. tordanik/OSM2World — ADAPT

- Repo: https://github.com/tordanik/OSM2World (Java, ★780, branch `master`)
- License: **MIT** (verified via API + LICENSE.txt). Safe to adapt.
- Activity: pushed 2026-09-09; presented at SotM 2026; OSM-3D-Terrain Prototype Fund project (2026-06).
- Input: OSM data (.osm extracts). Output: **glTF, glb, obj, pov**, OpenGL renders; JVM + Web libraries, CLI/desktop, self-hosted web service.
- Capabilities:
  - Terrain: flat/unknown — **no DEM integration** (terrain is the known gap; OSM-3D-Terrain prototype in progress).
  - Buildings: 250+ OSM tags (skyscrapers → benches, lane markings, power lines); height/floors; complex parts; many roof shapes.
  - Roads: lane markings, sidewalks inferred; ground-plane painting, no elevated-deck model.
  - Bridges / elevated roads: rendered as tagged (`bridge=yes`, layers) but **no procedural pier/deck/clearance generation**.
  - Water: polygons; coastline reconstruction not a focus.
  - Materials/facades: **PBR** (normal, ORM, displacement maps, texture snapping) — best-in-class facade approach here.
  - LOD: **yes, multi-LOD generation** for scale/perf.
  - Tiling/batch: single-area conversion; no tiled streaming story.
  - Blender/Godot/mobile: outputs import into both; no native plugins; mobile suitability depends on chosen LOD.
- Reuse: tag-to-3D mapping rules, PBR material strategy, LOD scheme; JVM lib could run in a build service.
- Limitations: Java toolchain; no terrain; no batch tiling; bridge modeling is literal, not procedural.

## 2. vvoovv/blosm — ⚠️ REFERENCE (GPL-blocked)

- Repo: https://github.com/vvoovv/blosm (Blender addon, ★2110)
- License: **GPL-3.0** (verified: `release/LICENSE` = GPL v3 preamble). ⚠️ Copyleft — **do not copy code**; free vs Pro split (Pro adds textures/trees/baking).
- Activity: pushed 2026-09-08; base version import path maintained.
- Input: OSM (.osm), SRTM .hgt terrain, GPX, Google 3D cities (Pro), satellite imagery. Output: Blender scene (export to glTF/FBX manually).
- Capabilities:
  - Terrain: 30 m global DEM import; buildings/roads **draped on terrain**; imagery projection.
  - Buildings: height/floors extrusion, complex parts, many roof shapes; Pro adds tileable UV textures + lit-window materials.
  - Roads: Blender curves with profile + width; projected on terrain. No bridge/elevated-deck generation.
  - Water/vegetation: rivers/lakes/forests as polygons; forests as 3D trees (Pro).
  - Materials/facades: base = untextured; Pro = tileable textures + texture baking for 3D Tiles.
  - LOD/tiling/batch: none (single Blender session, interactive).
  - Blender: **native**; Godot/mobile: only via manual export + decimation.
- Reuse: drape-on-terrain math, curve-profile road pattern, texture-baking-for-tiles idea.
- Limitations: interactive-only, no headless batch; GPL blocks code reuse; Google 3D-city path has ToS risk.

## 3. romanshuvalov/rsgeotools (rvtgen3d) — ADAPT

- Repo: https://github.com/romanshuvalov/rsgeotools (C, ★132, BSD-3-Clause verified)
- License: **BSD-3-Clause**. Safe to adapt/fork.
- Activity: **stale — last push 2020-09-29**; game (Generation Streets, Steam) is proprietary, generator is the OSS part.
- Input: OSM Planet PBF → o5m tiles (z7) + water polygons + heightmaps via gdal; custom RVT vector tiles. Output: 3D world meshes (game-ready).
- Capabilities:
  - Terrain: relief from external heightmaps (gdal pipeline); terrain surface map.
  - Buildings: 3D + roof decorations + entrances; roofs limited to **dome/onion/cone-pyramid**; random rural houses.
  - Roads: road markings, street lighting, rail, power towers/lines (limited), walls/fences, trees/bushes.
  - Bridges: destroyed-bridge set pieces only — **no procedural elevated-highway builder**.
  - Materials/facades: game-styled, low-fi; no PBR story.
  - LOD/tiling/batch: **mass-processing design** (planet → tiles → RVT), closest batch story to City Compiler; no runtime LOD documented.
  - Blender/Godot/mobile: none; Linux-only toolchain (libgeos LGPL ⚠️ dep, gdal, osmctools, boost).
- Reuse: **planet-scale batch pipeline shape** (subdivide → per-tile gen), RVT tile-spec idea, game-first asset pragmatism.
- Limitations: stale; custom tile format = lock-in; Linux-only; weak roofs; LGPL transitive dep (libgeos) needs linking care.

## 4. willjoe/terranian — REFERENCE (no license; bridge focus)

- Repo: https://github.com/willjoe/terranian (TypeScript+three.js/R3F, ★0, created 2026-08-18)
- License: **NONE** (`package.json: "private": true`, no LICENSE). ⚠️ Default = all rights reserved — **ideas only, no code copying**.
- Input: live Overpass API (buildings/roads/land-use) + Mapbox Terrain-RGB. Output: in-browser three.js scene (~1 km radius) + top-down visual-compare PNGs.
- Capabilities (bridge/elevated-road focus — the reason it's here):
  - **Bridges**: `src/world/bridges.ts` detects road∩water and road∩building crossings **geometrically** (not trusting OSM `bridge` tags); builds elevation profile: **single ramp ≤5% grade → flat plateau at clearance → ramp down, one hump max**; 3 m clearance over roofs; water clearance from anchor gradient. **Best procedural-elevated-road pattern found.**
  - Roads: 3 merged meshes (sidewalk outline below + surface + dashed centerline) to hide intersection seams; footways simplified.
  - Terrain: real DEM (Mapbox), but buildings sit on **single flat median-height base** — breaks on large/sloped footprints (documented).
  - Water: **coastline reconstruction** from `natural=coastline` lines via grid sampling + marching squares (96²), with building-enclosure sanity check — robust to marinas/islands; thin slips (<~10 m) missed.
  - Architecture: `geo/data/world` layers are **three.js-free**; `world/schema.ts` WorldModel JSON designed as portable interchange. **Adopt this layering.**
  - Materials/facades/LOD/tiling/batch: flat colors, no facades/PBR/LOD/tiling; no batch; Overpass 504s; in-memory tile cache only; relations/multipolygons skipped.
  - Blender/Godot/mobile: none (web demo + driving mode).
- Reuse: bridge clearance-profile algorithm, coastline grid+marching-squares, WorldModel interchange + renderer-independent layers, visual-compare harness idea.
- Limitations: demo-scale, no streaming, no license, browser-only deps (Mapbox token, Overpass reliability).

## 5. Project-PLATEAU (Japan CityGML) — ADOPT / ADAPT

- SDK Unity: https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unity (C#, MIT, ★207, push 2026-06-29)
- SDK Unreal: https://github.com/Project-PLATEAU/PLATEAU-SDK-for-Unreal (C++, MIT, ★113, push 2025-06-03)
- What they do: map-based range selection → CityGML import → feature filtering → C# API on attributes → export (FBX/OBJ/Datasmith); samples incl. GIS + game samples; mobile = partial (coordinate utils only on Android/iOS).
- Input: PLATEAU CityGML (LOD1–LOD4 incl. interiors). Output: Unity/Unreal scenes + exported 3D files.
- Capabilities: full buildings/infra with attributes; terrain/road/water as authored (no procedural gap-filling); materials as authored; LOD = source LODs; tiling via range selection; batch via editor scripts; Blender: via export; Godot: not directly (see godot-plateau §6).
- Reuse: **ADOPT for any Japan theater** (highest fidelity available); ADAPT the range-select → filter → attribute-API → export pipeline shape for other CityGML sources.
- Limitations: **Japan-only data**; LOD2+ models heavy for mobile air-combat (needs decimation/impostors); Unity/Unreal-only.

## 6. Self-searched topics

### 6a. CityGML → glTF / GIS interchange — ADAPT / REFERENCE
- **MIERUNE/plateau-gis-converter** (Rust, MIT, ★103, push 2026-09-07) — CityGML → 3D Tiles 1.1 / MVT / GeoPackage. **ADAPT** as the tiling/export reference; Rust = embeddable in a compiler service.
- **citygml4j/citygml-tools** (Java, Apache-2.0, ★165, push 2026-05-31) — validate/clean/subset CityGML. **ADAPT** for preprocessing.
- **shiena/godot-plateau** (C++ GDExtension, MIT, ★8, push 2026-07-27) — CityGML in Godot 4.x. **REFERENCE** for Godot loading pattern.
- PLATEAU Data-Conversion-Manual (FME workspaces) — proprietary FME dep → **REJECT** as tooling, useful only as format-mapping notes.

### 6b. Overture Maps → 3D city — ADAPT
- **OvertureMaps/data** (MIT, ★1163, push 2026-08-12) — global buildings/transportation/places releases; the **global-scope answer** where OSM is sparse.
- **reearth/reearth-buildings** (Rust, MIT, ★4, push 2026-09-06) — Overture → 3D Tiles 1.1 on Cloudflare Workers. **ADAPT**: proves Overture→tiles serverless batch path; mirrors City Compiler's fetch→build→serve shape.

### 6c. GIS → Blender / Godot — REFERENCE
- **domlysz/BlenderGIS** (Python, ⚠️ GPL-3.0, ★9370, push 2025-12-20) — GeoTIFF/DEM/Shapefile/WMS import to Blender. Ideas only (authoring-side terrain), GPL-blocked.
- blosm §2 covers the OSM→Blender path; godot-plateau §6a covers CityGML→Godot.

### 6d. DEM → game terrain — ADAPT (pattern)
- No single dominant OSS "DEM→Godot/UE" repo surfaced. Verified pattern across repos: **gdal-based heightmap pipeline** (rsgeotools), **Terrain-RGB sampling** (terranian/Mapbox), **SRTM .hgt import + drape** (blosm/BlenderGIS). Recommendation: standardize City Compiler on **DEM GeoTIFF → quantized mesh tiles + texture drape**, implemented once in the WorldModel layer, not per-engine.

### 6e. Procedural bridges / elevated highways — ADAPT terranian
- Code search for dedicated procedural bridge/highway generators returned no maintained project. terranian §4 remains the sole verified procedural pattern (geometric crossing detection + 5%-grade single-hump profile + clearance rules). rvtgen3d contributes only set-piece destroyed bridges. → **Specify our own elevated-road builder on terranian's algorithm**, extended with piers/guardrails/LOD and tile-boundary continuity.

## 7. Licensing caution summary

- ⚠️ **GPL-3.0: blosm, BlenderGIS** — copyleft; study, don't copy. Clean-room reimplementation only.
- ⚠️ **No license: terranian** — all rights reserved by default; ideas only.
- ⚠️ **LGPL transitives: libgeos** (via rsgeotools chain), libgeotiff paths — dynamic-link / process-boundary isolation if adopted.
- Safe: MIT (OSM2World, PLATEAU SDKs, MIERUNE, godot-plateau, Overture, reearth), BSD-3 (rsgeotools), Apache-2.0 (citygml-tools, cesium).

## 8. Recommendation for City Compiler

1. **Pipeline shape**: rsgeotools-style batch tiling + terranian-style renderer-free WorldModel interchange + MIERUNE-style 3D-Tiles/MVT export.
2. **Buildings/roads base**: OSM2World tag coverage + PBR/LOD + Overture backfill where OSM sparse; citygml-tools preprocessing where CityGML exists; PLATEAU SDKs for Japan theaters.
3. **Differentiator to build**: procedural elevated-road/bridge builder (terranian algorithm + piers/rails/LOD/tile continuity) and DEM-quantized terrain mesher — the two gaps no prior art covers together.
4. **Do not**: depend on Cesium runtime (heavy for mobile air-combat — use the 3D Tiles *standard* only); copy GPL/no-license code.
