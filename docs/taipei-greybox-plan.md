# Taipei Battlefield Greybox v0 — Plan

> First milestone: prove the **City Compiler**, not the game.
> No aircraft, missiles, AI, HUD, missions, final textures, cinematics.

## 1. Acceptance criteria (all must pass)

1. Terrain correct: quantized DEM heightfield loads in Godot; spot heights match source DEM within tolerance.
2. River/coastline correct: Tamsui River + coastline visible and geographically right.
3. Buildings white massing: Layer A extrusions generate across the combat core; heights
   plausibly distributed (101 tallest; residential bands reasonable).
4. Building height roughly right: sampled extrusions match WFS surveyed heights; fallback
   provenance (`height_source`) present per tile.
5. Major roads recognizable: at least the primary expressway corridors read from the air.
6. ≥1 true 3D bridge: deck + piers + clearance over water, crossable airspace underneath.
7. ≥1 elevated road segment: ramp → plateau → ramp profile with terrain attachment.
8. Taipei 101 placeholder replacement: procedural massing suppressed at the 101 footprint,
   placeholder tower stands at the correct ENU position (no double-stack).
9. Consistent real-world scale: runway length / 101 height / river width measure correctly in meters.
10. Pipeline re-runnable: clean rebuild from pinned manifest reproduces the greybox.
11. Godot-loadable: greybox scene opens in Godot and runs on the mobile target profile.

## 2. Work breakdown (smallest-first)

| # | Task | Output |
|---|---|---|
| 0 | Scaffold repo: `cities/taipei/city.yaml`, `cities/taipei/heroes.yaml`, `docs/` (this round), `tools/` skeleton, `manifest.json` format | Repo skeleton + this doc set |
| 1 | **Smallest first task (J):** WFS sample ingest — bbox Daan/Xinyi rect → `height_m + height_source` GeoJSON via Buju derivation verbatim | `tools/taipei/fetch_buildings_sample.mjs` + sample GeoJSON |
| 2 | Sample WorldModel: footprints → ENU massing records (suppression hook stubbed) | `worldmodel_sample.json` |
| 3 | Sample tile export: 1 tile (2 km, Xinyi/101 area) → glTF white massing → Godot scene | 1 tile in Godot, 101 footprint flagged |
| 4 | 101 placeholder replacement: suppress + placeholder tower | Replacement architecture proven |
| 5 | DEM ingest: SRTM/COP-DEM tile → heightfield → Godot terrain + terrain-following bases | Terrain + conformance |
| 6 | Water mask: river/coast polygons → mask + visual water plane | River/coastline criterion |
| 7 | Transport v0: 1 bridge + 1 elevated segment via clean-room profile builder | Bridge/elevated criteria |
| 8 | Citywide scale-up: full WFS ingest + footprint audit (4-archive z16 sweep) + 10×10 core tiling | Full-core greybox |
| 9 | Runways + clearance + collision proxies + manifest determinism | `nav/`, `_col.json`, rebuild check |
| 10 | Mobile perf pass: LOD + budget check on target profile | Ship greybox v0 |

## 3. Out of scope (explicitly)

Aircraft, weapons, AI, HUD, missions, PBR facades, roof variation, regional style,
final hero art, night lighting, weather, sound.

## 4. QA harness

- Buju MapLibre/PMTiles pages (reused as 2D QA) + Godot greybox scene (3D truth).
- Footprint audit per city before accepting tiles (Buju 4-archive z16 sweep).
- Visual-compare harness (terranian-inspired top-down PNGs) for regression on rebuilds.

## 5. Definition of done

All §1 criteria pass + `git status` clean + branch pushed + review-ready by another
model/agent. No merge to `main` this round.
