# Data Sources — Battlefield City Compiler

> Interchange CRS: EPSG:4326 unless noted. Every source is pinned (release/snapshot
> date + sha256 where downloadable) in the per-build `manifest.json`.

## 1. Taipei v0 (greybox)

| Data | Source | Role | Pin strategy |
|---|---|---|---|
| Building footprints + heights | Taipei City Dashboard WFS `taipei_vioc:tp_building_height` (`https://citydashboard.taipei/geo_server/...`, WFS 2.0.0, `srsName=EPSG:4326`, paged 5000) | Authoritative Layer A input; semantics `1_bud_high` → `1_top_high−1_ent_heig` → `floors×3.2` → `9.6 m` (reuse Buju derivation verbatim) | Record `resultType=hits` count + fetch date + per-page sha; keep `height_source` per feature |
| Global building backfill | Overture Maps `buildings` theme (release-pinned, e.g. `2026-07-22.0` pattern) | Fills areas outside WFS coverage / future cities | Pin release string; dual-release preflight (primary + fallback) |
| Roads / rail / water | Overture `transportation` theme + OSM `highway/waterway/railway` + OSM `relation/full` rail trick (pinned relation IDs) | Layer B geometry inputs | Pin Overture release + OSM snapshot timestamp |
| Runways / airports | OSM `aeroway` (runway/taxiway/aerodrome) + cross-check with overture `transportation` | Runway strips + `nav/runways.json` | Pin snapshot; visual QA vs satellite |
| DEM / terrain | SRTM 30 m or Copernicus COP-DEM 30 m (global, offline GeoTIFF) for v0; evaluate NLSC DTM later for Taiwan quality | `terrain/heightfield` + terrain-following building bases + water mask | Pin DEM tile IDs + version; record vertical datum |
| Water mask | OSM `waterway` + `natural=coastline` (terranian-style grid + marching-squares reconstruction where needed) | Splash/landing logic + bridge crossing detection | Pin snapshot |
| Hero footprints | Same WFS/Overture footprint that Layer A would extrude (matcher by id/polygon) | Suppression targets for Layer C | Pin matcher rules in `heroes.yaml` |

## 2. Tokyo (future — PLATEAU special route)

| Data | Source | Role | Note |
|---|---|---|---|
| Buildings / infra / terrain / textures | Project-PLATEAU CityGML (LOD1–LOD2 for compiler; LOD3+ reference only) | Authoritative Japan input — **replaces** the Taipei-style WFS path | Preprocess with citygml-tools (Apache-2.0); tile/export via MIERUNE plateau-gis-converter pattern (MIT) |
| Backfill / POI | OSM + Overture as above | Same adapters, different `city.yaml` pins | Output contract identical to Taipei |
| Godot loading pattern | shiena/godot-plateau (MIT) | Reference only | |

**Decision (H): Tokyo SHOULD take the PLATEAU special route.** PLATEAU is surveyed,
attributed CityGML — strictly higher fidelity than reconstructing Tokyo from
Overture/OSM extrusion. The architecture absorbs this: Tokyo's `city.yaml` selects the
CityGML adapter, but emits the same WorldModel + Battlefield contract. Mobile weight
(LOD2+) is handled by decimation/impostors in the export stage, not by rejecting the data.

## 3. Other future cities (pattern)

| City | Likely providers |
|---|---|
| Seoul | Overture + OSM + Korean NGII open data (to evaluate) |
| New York | Overture + NYC Open Data (building footprints + heights) |
| Shanghai | Overture + OSM (local authoritative data TBD) |

All emit the same Battlefield contract (§4 of architecture.md).

## 4. Sources explicitly NOT used for geometry

- OSM raster tiles / NLSC WMTS / GSI xyz — pictures, not data (`DO_NOT_REUSE` for geometry).
- Buju POI chain regexes (7-ELEVEN/全家/…) — no combat value unless repurposed as target-class seeds.
- Google 3D cities (ToS risk) — never an input.

## 5. Determinism + licensing rules

1. Every input pinned: URL/release/snapshot + sha256 + fetch date in `manifest.json`
   (extends Buju's `*.audit.json` pattern to all combat inputs).
2. Rebuild with the same manifest → byte-comparable geometry; tool-version bumps recorded.
3. Compiler deps restricted to MIT / BSD / Apache-2.0. GPL (blosm, BlenderGIS) and
   no-license (terranian) sources are ideas-only; any reimplementation is clean-room.
4. LGPL transitives (libgeos/gdal paths) isolated behind process boundaries if adopted.
