# Battlefield City Compiler v0 — Architecture

> Status: research-phase design (no implementation yet). Target engine: Godot (mobile-capable).
> Principle: **don't rebuild the city — build the air-combat stage that reads as the real city.**

## 1. Design principles

1. **City-agnostic input, contract-stable output.** Any city provider may feed the front;
   every city emits the same Battlefield schema (§4). No `build_taipei.py` with embedded
   city special-cases — city differences live in `cities/<city>/city.yaml` + provider adapters.
2. **Repeatable, batch, headless.** Every canonical geometry artifact regenerates from
   pinned inputs + a manifest. No "open Blender and hand-fix" in the critical path.
3. **Three independent geometry layers** (procedural city / transport infra / hero landmarks),
   composable and replaceable per layer.
4. **Mobile-first budgets.** White/grey massing first; PBR/facades later and optional.
   LOD + tiling from day one; tile size and draw-call budgets are architecture constraints,
   not polish tasks.
5. **Renderer-free interchange.** A `WorldModel` JSON (terranian-inspired, renderer-independent)
   sits between GIS ingestion and engine export, so Godot today does not lock out other
   engines tomorrow.

## 2. System overview

```text
City Data (per-city providers)
  └─► Ingest adapters ─► WorldModel (renderer-free JSON, EPSG:4326 + ENU meters)
        ├─► A. Procedural City Layer   (footprint + height + class → massing)
        ├─► B. Transport Infra Layer   (bridges / viaducts / ramps / interchanges / runways)
        └─► C. Hero Landmark Layer     (footprint suppress → custom GLB/Godot scene)
              └─► Tiling + LOD + collision proxies ─► Godot-loadable export (glTF + heightfield + manifest)
                    └─► QA harness (MapLibre/PMtiles viewer reused from Buju, Godot greybox scene)
```

## 3. The three geometry layers

### A. Procedural City Layer
- Input: footprint polygons + `height_m` + `height_source` + building class (from Overture /
  OSM / local datasets per `city.yaml`).
- Output: white/grey extruded massing (flat tops v0; roof variation + procedural facade
  + regional style are later, optional stages).
- Rules: plausibility clamp (reuse Buju 1.2–600 m bounds); fallback chain
  `surveyed → elevation-delta → floors×3.2 → 9.6 m` retained with `height_source` provenance.
- Suppression: any footprint claimed by Layer C is excluded here (never double-stacked).

### B. Transport Infrastructure Layer (the differentiator)
- First-class 3D geometry — never ground texture. Scope v0: bridges, elevated highways,
  viaducts, highway ramps, one major interchange, runway strips.
- Core algorithm (adapted from terranian, clean-room): geometric crossing detection
  (road∩water, road∩building, road∩road with layer tags) → elevation profile
  (ramp ≤5% grade → flat plateau at clearance → ramp down, one hump max) → deck + piers
  + guardrails → terrain attachment at anchors.
- Must handle: elevation, layer ordering, crossings, clearance, ramps, terrain attachment,
  tile-boundary continuity (shared anchor heights in WorldModel so adjacent tiles agree).
- Runways: flattened terrain patch + strip geometry; approach-corridor clearance check.

### C. Hero Landmark Layer
- Registry in `cities/<city>/heroes.yaml`: footprint matcher → suppress Layer A massing
  → replace with custom GLB / Godot scene at the same ENU origin.
- v0: Taipei 101 = placeholder tower (validates the replacement architecture, not the art).
  Later: Grand Hotel, Taipei Dome, terminals/airports, signature bridges.

## 4. Battlefield output contract (stable across cities)

```text
battlefield/
  manifest.json        # pinned input versions, sha256, city.yaml hash, tool versions, tile grid
  tiles/
    <tz>/<tx>_<tz>.glb      # merged layer geometry per tile (A+B, heroes referenced)
    <tz>/<tx>_<tz>_col.json # collision proxies (bbox forest / convex hulls)
  terrain/
    heightfield.tif / .bin  # quantized DEM mesh source + Godot-importable heightmap
    water_mask.tif          # splash/landing logic
  heroes/
    <hero_id>.glb + <hero_id>.godot.tscn  # custom landmark scenes
  nav/
    runways.json            # runway endpoints, headings, lengths
    clearance.json          # approach corridors + obstacle heights
```

- Interchange CRS: EPSG:4326 for GIS I/O; theater ENU meters (origin per `city.yaml`) for engine.
- Tile grid: combat-sector-aligned (not slippy-map zooms); v0 tile = 2 km, combat core 20×20 km = 10×10 tiles.
- Every artifact regenerable: `manifest.json` records input pins; rebuilding with the same
  manifest yields byte-comparable geometry (modulo tool-version bumps, which are recorded).

## 5. City configuration

```text
cities/
  taipei/
    city.yaml      # bbox, ENU origin, providers, pins, budgets
    heroes.yaml    # hero registry (101 placeholder v0)
  tokyo/
    city.yaml      # future; PLATEAU provider flag
```

`city.yaml` selects provider adapters (e.g. Taipei: Overture + OSM + Taiwan WFS;
Tokyo: PLATEAU + OSM) but all adapters emit the same WorldModel — input varies, output contract doesn't.

## 6. Blender's role (decision)

**Blender is an optional cleanup/automation target, NOT the canonical build stage.**
- Canonical path: GIS → WorldModel → tiled glTF/heightfield → Godot. Headless, scripted, re-runnable.
- Blender enters only as: (a) headless script pass for mesh ops with no game-code equivalent
  yet, or (b) manual hero-asset authoring (art source, not pipeline stage).
- Rule: nothing in Layers A/B may *require* a human opening Blender. If a Blender step
  proves essential, it must be wrapped as a headless script with pinned version + manifest entry.

## 7. Toolchain choices (v0)

| Stage | Choice | Why |
|---|---|---|
| Building ingest (Taipei) | Buju WFS downloader skeleton + `deriveBuildingHeight` verbatim | Probe-verified semantics, 373k-ID scale proven |
| Global backfill | Overture buildings/transportation releases (pinned) | Global scope where local data sparse |
| Roads/water/runways | Overture `transportation` + OSM `aeroway/highway/waterway` | Fills Buju's biggest gap |
| Tag→3D rules, PBR/LOD design | OSM2World (MIT) as reference implementation | 250+ tags, PBR, multi-LOD — best documented |
| Batch tiling shape | rsgeotools planet→tiles pattern (BSD) | Only proven planet-scale batch story |
| Bridge algorithm | terranian profile (clean-room reimplementation) | Sole verified procedural pattern; no-license code is ideas-only |
| Japan theaters | PLATEAU SDKs + MIERUNE converter + citygml-tools | Highest-fidelity Japan data, MIT/Apache-safe |
| Tile export standard | glTF + 3D Tiles 1.1 concepts (no Cesium runtime dep) | Mobile-safe; runtime stays Godot-native |
| QA harness | Buju MapLibre/PMTiles pages + Godot greybox scene | Reuse viz; combat truth lives in engine |

## 8. Non-goals (v0)

Aircraft, missiles, enemy AI, HUD, missions, final textures, cinematic effects, Manhattan-grade
street-level reconstruction, global simulation. v0 validates the **City Compiler**, nothing else.

## 9. Risks + mitigations

| Risk | Mitigation |
|---|---|
| DEM gaps / datum mismatch → floating/sunk buildings | Terrain-following bases from day one; runway flattening; per-tile height audit |
| Tile-boundary cracks (bridges/terrain) | Shared anchor heights in WorldModel; boundary-continuity QA check |
| OSM tag sparsity outside Taipei core | Overture backfill; `height_source` provenance exposes weak tiles |
| PLATEAU weight on mobile | LOD2+ decimation + impostors; heroes budgeted separately |
| License contamination (GPL/no-license code) | Clean-room reimplementation; MIT/BSD/Apache-only deps in compiler |
