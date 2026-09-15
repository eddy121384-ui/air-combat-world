# Buju Technical Audit — Taipei-Maps Pipeline (for air-combat-world reuse)

> Audit date: 2026-09-11. Source repo (READ-ONLY): `eddy121384-ui/Taipei-Maps`
> Local path inspected: `C:/Users/EDDY/Documents/GitHub/Taipei-Maps`
> Method: root listing + all 4 named `.bat` files + `docs/`, `docs/data/`,
> `docs/concepts/`, `public/`, `public/generated/`, `tools/data/`, `tools/dev/`,
> no-`package.json` check, generated-artifact sizes, dependency-chain tracing.
> Tags: `REUSE_DIRECTLY` | `REUSE_WITH_ADAPTATION` | `DO_NOT_REUSE` | `MISSING_FOR_AIR_COMBAT`
> Rule: document vs code conflicts resolved in favour of actual code + artifacts.

## 0. TL;DR

- Taipei-Maps is a **2.5D MapLibre GL JS web-map demo stack**, not a game engine.
  No Unity/Unreal/Godot scene, no physics, no collision meshes.
  Evidence: `public/*.html` pages + MapLibre `fill-extrusion` rendering.
  → `DO_NOT_REUSE` as combat renderer; `REUSE_WITH_ADAPTATION` as data-acquisition reference.
- The only production-grade 3D-geometry pipeline is **Issue #31 Taipei official
  building-height overlay**: City Dashboard WFS → slim GeoJSON (`height_m` only)
  → Planetiler custom-YAML → PMTiles → MapLibre `fill-extrusion`.
  Evidence: `build-taipei-building-height-pmtiles-citywide.bat`,
  `tools/data/download_taipei_building_height_citywide.mjs`,
  `tools/data/taipei_building_height_semantics.mjs`,
  `tools/data/taipei_building_height_citywide_pmtiles.yml`.
  → `REUSE_WITH_ADAPTATION` (core seed of air-combat city geometry).
- **Overture = global 3D baseline; OSM = POI hole-filler only; Taipei WFS =
  authoritative Taipei overlay.** Overture buildings render everywhere; local
  PMTiles overrides only inside Taipei.
  Evidence: `public/shared-map-core.js`, `public/maplibre-pmtiles-provider-spike.html`,
  `docs/issue-31-local-validation.md`, `docs/data/taipei_osm_poi_reconciliation_v01.md`.
  → `REUSE_DIRECTLY` (pattern); geometry sources need per-city replacement.
- **Terrain = MapLibre `raster-dem` + hillshade, OFF by default, no game-heightfield export.**
  → `MISSING_FOR_AIR_COMBAT` (collision-grade heightfield).
- **Roads/waterways: MISSING as geometry.** Only OSM raster tiles (pictures of roads),
  MRT/rail LineStrings, school-district polygons. No road centerlines, no water polygons.
  → `MISSING_FOR_AIR_COMBAT`.
- **No `package.json`, no npm deps.** Runtime is system Node (citywide BAT can
  self-bootstrap portable Node 22.14.0) + portable Temurin Java 21 + Planetiler jar
  + CDN `maplibre-gl` + `pmtiles` + Python only for school-district + DuckDB POI jobs.
  → `REUSE_DIRECTLY` (zero-install pattern is good for air-combat tooling).

## 1. True pipeline (acquire → clean → fuse → geometry/height → render)

```text
ACQUIRE
  buildings : WFS GetFeature paged (EPSG:4326) .... download_taipei_building_height_{sample,citywide}.mjs
  POI       : Overture S3 (places) via DuckDB ..... build_taipei_daily_life_poi_v01.mjs + taipei_daily_life_poi_v01_config.json
              OSM Overpass snapshot (pinned date) . build_taipei_osm_poi_reconciliation_v01.mjs
  transit   : data.taipei MRT GIS (TWD97/EPSG:3826)  build_taipei_mrt_official.mjs (+stations variant)
              OSM API relation/full (rail) ........ build_north_taiwan_urban_rail.mjs / build_taiwan_intercity_rail.mjs
  basemap   : CDN tiles (no acquire step) ......... OSM raster / NLSC PHOTO2 WMTS / GSI xyz / Mapterhorn DEM / Overture PMTiles
CLEAN
  buildings : keep Polygon/MultiPolygon only; derive height_m via taipei_building_height_semantics.mjs;
              citywide keeps ONLY {height_m} (+id); sample keeps {height_m, height_source}
  POI       : buju-poi-canonical-v02.mjs (chain regex, branch tokens, dedup)
              → buju-poi-reconcile-v01.mjs (matched / safe_hole / unresolved)
  transit   : TWD97→WGS84 math in-builder; route→line-code map; LineString-only keep
FUSE
  buildings : NO geometric fusion. Visual stacking only: Overture global layer always on;
              local PMTiles drawn above inside Taipei. Outside Taipei local disappears by design.
  POI       : Overture canonical baseline (IDs frozen) + OSM safe_hole additions only.
              Never Overture+OSM counts summed.
GEOMETRY/HEIGHT (tile build)
  Planetiler generate-custom --schema tools/data/*.yml --output public/generated/*.pmtiles --force
  citywide: z13-16, preservation flags (--min_feature_size 0, --simplify_tolerance 0)
  sample  : z13-15 per yml (min_zoom 13 max_zoom 15)
  audit   : 4x z16-only archives (centroid control, 1x, 2x, 4x scaled)
RENDER
  node tools/dev/serve_single_engine_core.mjs <port> <page> (static server + Range support for .pmtiles)
  pages: maplibre-pmtiles-provider-spike.html (Issue #31 validation)
         / maplibre-single-engine-core.html / taipei-building-footprint-audit.html
         + ~15 POI/school/healthcare smoke pages
```

Evidence paths: `build-taipei-building-height-pmtiles-citywide.bat:53-138`,
`build-taipei-building-height-pmtiles-sample.bat:15-97`,
`audit-taipei-building-footprints.bat:17-80`,
`probe-taipei-building-height-semantics.bat:16`,
`tools/data/*.mjs`, `tools/data/*.yml`,
`tools/dev/serve_single_engine_core.mjs`, `public/generated/` listing
(130 MB citywide GeoJSON → 12 MB PMTiles; 373,532 source IDs).

## 2. Building footprints: how obtained

| Claim | Evidence | Tag |
|---|---|---|
| Sole footprint source = Taipei City Dashboard public WFS layer `taipei_vioc:tp_building_height`, endpoints `https://citydashboard.taipei/geo_server/{taipei_vioc/ows,ows}`, WFS 2.0.0 `GetFeature`, `srsName=EPSG:4326`, `count=5000` paging with `startIndex`, `resultType=hits` pre-count, dual-endpoint failover | `tools/data/download_taipei_building_height_citywide.mjs:7-74,95-200`, `tools/data/probe_taipei_building_height_wfs.mjs` | `REUSE_WITH_ADAPTATION` — endpoint + layer name are Taipei-only; paging/slim/failover pattern ports to any WFS city |
| Citywide streams pages straight to `public/generated/taipei_building_height_citywide.geojson` (dedupe by WFS `id`, drop non-Polygon/MultiPolygon); sample uses bbox `121.5200,25.0050,121.6350,25.0750` (Daan+Songshan+Xinyi rect, not admin boundary) | `download_taipei_building_height_citywide.mjs:95-164`, `download_taipei_building_height_sample.mjs` | `REUSE_WITH_ADAPTATION` |
| Citywide scale: 373,532 unique source IDs, 130 MB slim GeoJSON → 12 MB PMTiles; sample: ~159k features, ~60 MB → 1.5 MB; browser sample ~24.6k fragments @ ~2.1 s move→idle, judged smooth | `public/generated/` sizes + `taipei_building_height_footprint_expected.json`, `docs/issue-31-local-validation.md`, `docs/issue-31-sample-browser-metrics.md` | `REUSE_DIRECTLY` (perf anchor for air-combat budgets) |
| Footprint identity audit: `prepare_taipei_building_height_footprint_audit.mjs` rewrites props to `{source_id}` + emits x2/x4 scaled GeoJSONs + expected-ID index; audit BAT builds 4 separate z16 PMTiles (centroid control proves loss is size-sensitive snap, not data loss) | `audit-taipei-building-footprints.bat:51-72`, `tools/data/prepare_taipei_building_height_footprint_audit.mjs`, `tools/data/taipei_building_height_footprint_audit_*pmtiles.yml` | `REUSE_DIRECTLY` (rerun per city before trusting tile retention) |
| Taipei boundary used for POI gating only (12-district polygon), NOT for building clipping | `tools/data/taipei_daily_life_poi_v01_config.json`, `tools/data/build_taipei_osm_poi_reconciliation_v01.mjs` | `DO_NOT_REUSE` for geometry clipping |

## 3. Overture vs OSM roles (do not swap)

| Claim | Evidence | Tag |
|---|---|---|
| Overture BUILDINGS = global 3D baseline, remote PMTiles, extruded with `height ? height : num_floors*3.2 : 9.6`, `min_height` base | `public/shared-map-core.js`, `public/maplibre-single-engine-core.html` | `REUSE_DIRECTLY` (pattern + expression); swap release pin per theater |
| Overture PLACES = POI baseline (DuckDB extract from S3 GeoParquet); known gaps (incomplete coverage + duplicates) → canonical engine required | `tools/data/taipei_daily_life_poi_v01_config.json`, `tools/data/build_taipei_daily_life_poi_v01.mjs`, `docs/data/overture_places_taipei_v01_audit.md`, `public/buju-poi-canonical-v02.mjs` | `DO_NOT_REUSE` for air-combat geometry; `REUSE_WITH_ADAPTATION` only if combat needs POI layer |
| OSM BUILDINGS = never used. OSM role is strictly (a) raster basemap pictures, (b) pinned POI hole-filler with `matched/safe_hole/cross_source_unresolved` reconciliation, (c) rail geometry via core API `relation/full` (NOT Overpass) | `public/shared-map-core.js`, `docs/data/taipei_osm_poi_reconciliation_v01.md`, `tools/data/build_north_taiwan_urban_rail.mjs` | `REUSE_DIRECTLY` (rail-via-relation/full trick); `MISSING_FOR_AIR_COMBAT` re buildings/roads/water from OSM |

## 4. Height source + missing-height handling

| Claim | Evidence | Tag |
|---|---|---|
| Live WFS keys (probe-verified 2026-08-20, Taipei 101 + Daan + Yangmingshan): roof `1_top_high`, entrance `1_ent_heig`, surveyed height `1_bud_high`, floors `1_floor`; identity `1_bud_high == 1_top_high − 1_ent_heig` row-by-row (101: 512.43 m; Daan 24F: 87.90 m; YMS 11F: 57.83 m) | `docs/issue-31-local-validation.md:28-43`, `tools/data/probe_taipei_building_height_semantics.mjs` | `REUSE_DIRECTLY` |
| Derivation order in `deriveBuildingHeight()`: ① plausible `1_bud_high` (1.2–600 m) → ② plausible `top−entrance` → ③ `floors×3.2` (1–150 fl) → ④ `9.6` default; stale-cache aliases kept defensively; citywide build logs per-source counts + consistency gate | `tools/data/taipei_building_height_semantics.mjs:1-116`, `tools/data/download_taipei_building_height_citywide.mjs` | `REUSE_DIRECTLY` — copy the function + plausibility bounds verbatim |
| Old spike queried nonexistent `1_entr_heig/1_bd_high` → forced fallback; fixed in citywide path. Sample GeoJSON keeps `height_source`, citywide strips to `height_m` only | `docs/issue-31-local-validation.md:35` | `REUSE_WITH_ADAPTATION` — keep `height_source` in air-combat tiles for QA provenance |
| Render fallback mirrors offline logic: local `['to-number',['get','height_m'],9.6]`; Overture `[height → num_floors*3.2 → 9.6]`, base `[min_height → 0]` | `public/maplibre-pmtiles-provider-spike.html`, `public/shared-map-core.js` | `REUSE_DIRECTLY` |
| `1_top_high` is ELEVATION (roof AMSL), never extrusion height — do not feed raw to extrusion height | `taipei_building_height_semantics.mjs:38-46` | `REUSE_DIRECTLY` (safety rule) |

## 5. Terrain / elevation status

| Claim | Evidence | Tag |
|---|---|---|
| Terrain = Mapterhorn `raster-dem` + `hillshade` layer; toggle default OFF; buildings sit at `fill-extrusion-base 0` ignoring terrain | `public/shared-map-core.js`, `public/maplibre-pmtiles-provider-spike.html` | `REUSE_WITH_ADAPTATION` for viz; `MISSING_FOR_AIR_COMBAT` for flight/collision (no heightfield export, no DEM caching, no offline tiles) |
| Hillside probe (Yangmingshan bbox) only confirmed `top−entrance == surveyed height` on slopes — not terrain-following geometry | `tools/data/probe_taipei_building_height_semantics.mjs` | `DO_NOT_REUSE` as terrain solution |
| No DEM/DTM acquisition script, no contour builder, no `terrain-*.geojson/pmtiles` in `public/generated/` | `tools/data/` listing (zero terrain builders), `public/generated/` listing (buildings, rail, MRT, healthcare only) | `MISSING_FOR_AIR_COMBAT` — air-combat needs SRTM/ALOS/CopDEM or NLSC DTM + offline heightfield pipeline |

## 6. Roads / waterways status

| Claim | Evidence | Tag |
|---|---|---|
| No road/water vector dataset, builder, or layer exists. Only linear vectors: official MRT lines+stations (`data.taipei` GIS, TWD97→WGS84 in-builder), TRA/THSR/NTR rail (OSM `relation/full` with pinned IDs) | `tools/data/build_taipei_mrt_official.mjs`, `tools/data/build_taipei_mrt_stations_official.mjs`, `tools/data/build_taiwan_intercity_rail.mjs`, `tools/data/build_north_taiwan_urban_rail.mjs` | `REUSE_WITH_ADAPTATION` (rail pattern only); roads/water `MISSING_FOR_AIR_COMBAT` |
| Transit overlay is decorative context, not routable graph | `public/shared-map-core.js:bootstrapTransit`, `public/transit-layer.js` | `DO_NOT_REUSE` for mission routing |
| Air-combat blockers: no runway/airbase data, no obstacle layer, no road-graph, no water mask | whole-repo grep: zero `highway|waterway|aeroway|runway` builders | `MISSING_FOR_AIR_COMBAT` — source from Overture `transportation` theme or OSM `aeroway/highway/waterway` |

## 7. Projection / coordinate conventions

| Claim | Evidence | Tag |
|---|---|---|
| Canonical runtime CRS = `EPSG:4326` (lon/lat). WFS requested with `srsName=EPSG:4326`; Planetiler sources declare `projection: EPSG:4326`; all generated GeoJSON outputs in 4326 | `download_*.mjs`, `taipei_building_height_*pmtiles.yml`, rail builders | `REUSE_DIRECTLY` — keep 4326 as interchange CRS for air-combat |
| Sole exception: Taipei MRT official GIS arrives in TWD97/TM2 (`EPSG:3826`) and is converted by hand-rolled `twd97ToWgs84()` with bounds-guard | `tools/data/build_taipei_mrt_official.mjs:35-64,86-87` | `REUSE_DIRECTLY` if ingesting any `data.taipei`/NLSC TWD97 source; otherwise ignore |
| Audit math uses equirectangular approx for bbox size only — never for placement | `tools/data/prepare_taipei_building_height_footprint_audit.mjs:50-64` | `DO_NOT_REUSE` beyond diagnostics |

## 8. GIS → display transformation (the part air-combat must replace)

| Claim | Evidence | Tag |
|---|---|---|
| No world-engine transform exists. Pipeline ends at MapLibre style: `fill-extrusion-base` + `fill-extrusion-height`, `vertical-gradient:true`, `minzoom 13/14` | `public/maplibre-pmtiles-provider-spike.html`, `public/shared-map-core.js` | `REUSE_WITH_ADAPTATION` — extrusion expressions + zoom windows port; game needs meters-based scene graph, ENU conversion, LOD, batching (all missing) |
| Local server exists only to serve Range-capable `.pmtiles` + static files + doorplate lookup; no build orchestration, no headless export | `tools/dev/serve_single_engine_core.mjs`, all `start-*-smoke.bat` | `REUSE_WITH_ADAPTATION` as dev-harness; game needs glTF/3D-Tiles/heightfield exporter (missing) |

## 9. Reuse ledger

### REUSE_DIRECTLY
- `tools/data/taipei_building_height_semantics.mjs` (derivation + 1.2/600 m plausibility + 9.6/3.2 constants) + citywide downloader paging/streaming/dedupe/diagnostics skeleton.
- Planetiler preservation flags (`--min_feature_size 0 --simplify_tolerance 0`, z16) + citywide yml shape.
- Footprint audit loop (4-archive z16 sweep + expected-ID index) — mandatory per new city.
- Overture-global + authoritative-local overlay pattern + `height/num_floors/9.6` + `min_height/0` expressions.
- Portable-runtime BAT pattern (Node 22 + Temurin 21 + Planetiler jar under `.cache/`) + Range-capable static server.
- Rail-via-OSM-`relation/full` with pinned IDs + TWD97→WGS84 function + audit JSONs with `source_url/source_crs/sha256/fetched_at`.

### REUSE_WITH_ADAPTATION
- WFS endpoint/layer/bbox per theater (Taipei values not portable); keep `height_source` attr in tiles (citywide dropped it — re-add for QA).
- POI canonical+reconcile engines only if combat needs urban semantics; retune radii per theater density.
- Mapterhorn DEM + hillshade for visualization; must add offline DEM → heightfield/mesh exporter + terrain-following building bases.
- MRT/rail color/line maps per city; extend to `aeroway` (runways), Overture `transportation` (roads), OSM `waterway` (water mask).

### DO_NOT_REUSE (game-irrelevant)
- All `daily-life-poi-*` smoke pages, school-district shards, healthcare/location-summary/place-metrics/inventory/doorplate/BigFun modules, aerial-photo WMTS toggling, sky/fog cosmetics. POI chain regexes (7-ELEVEN/全家/…) have zero combat value unless repurposed as target-class seeds.

### MISSING_FOR_AIR_COMBAT (must build)
1. Game-mesh exporter: PMTiles/GeoJSON → chunked glTF / 3D Tiles / engine-native static meshes with LOD + batching.
2. Terrain heightfield: offline DEM acquisition + tiling + building-base conformance + runway flattening.
3. Roads/water/runways/obstacles: Overture `transportation` + OSM `aeroway/highway/waterway/power` ingestion; water mask; approach-corridor clearance.
4. Collision/physics proxies: convex hulls or bbox forests per tile; spatial index for line-of-sight + crash detection.
5. Coordinate frame: 4326 → theater ENU/ECEF meters transform + tiling grid aligned to combat map sectors.
6. Determinism manifest: extend `*.audit.json` (sha256 + snapshot date) pattern to every combat input; version combat tiles explicitly.

## 10. Dependency chains (follow-the-import map)

```text
citywide 3D : build-*-citywide.bat → download_taipei_building_height_citywide.mjs → taipei_building_height_semantics.mjs
            → public/generated/taipei_building_height_citywide.geojson → taipei_building_height_citywide_pmtiles.yml
            → (java21 + planetiler.jar) → taipei_building_height_citywide.pmtiles (+.layerstats.tsv.gz)
            → serve_single_engine_core.mjs → maplibre-pmtiles-provider-spike.html (+ shared-map-core.js)
sample 3D   : build-*-sample.bat → download_taipei_building_height_sample.mjs → (same semantics)
            → taipei_building_height_sample.geojson → taipei_building_height_pmtiles.yml → sample.pmtiles → spike page
audit       : audit-*.bat → prepare_taipei_building_height_footprint_audit.mjs → {audit,x2,x4}.geojson + footprint_expected.json
            → 2 yml → 4 z16 pmtiles → taipei-building-footprint-audit.html
probe       : probe-*.bat → probe_taipei_building_height_semantics.mjs (targets 101/Daan/YMS bboxes)
                          → probe_taipei_building_height_wfs.mjs (hits/count/paging/extent preflight)
POI         : config json → build_taipei_daily_life_poi_v01.mjs (duckdb + extract_overture_places_bbox.py)
            → buju-poi-canonical-v02.mjs → build_taipei_osm_poi_reconciliation_v01.mjs (+buju-poi-reconcile-v01.mjs)
            → public/data/daily-life-poi/*.geojson+manifest → daily-life-poi-*.html
transit     : build_taipei_mrt_official.mjs ─┐
              build_taipei_mrt_stations_official.mjs ─┼→ public/generated/*.geojson → transit-layer.js
              build_north_taiwan_urban_rail.mjs ──────┘
```

## 11. Suggested reuse order for air-combat-world

1. Copy `taipei_building_height_semantics.mjs` + citywide downloader skeleton → new per-city building ingester with `height_source` retained. (`REUSE_WITH_ADAPTATION`)
2. Replicate Planetiler yml + preservation flags → per-theater tiles; run footprint audit before accepting any city. (`REUSE_DIRECTLY`)
3. Add DEM → heightfield + ENU exporter (new; biggest gap). (`MISSING_FOR_AIR_COMBAT`)
4. Add roads/water/runway ingestion (Overture transportation + OSM aeroway). (`MISSING_FOR_AIR_COMBAT`)
5. Build glTF/tiles + collision-proxy exporter; leave MapLibre pages as QA harness only. (`MISSING_FOR_AIR_COMBAT`)
