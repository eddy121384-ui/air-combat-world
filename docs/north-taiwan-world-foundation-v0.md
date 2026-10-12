# Northern Taiwan World Foundation v0 — GIS coverage and whitebox expansion (Phase 1)

Date: 2026-10-12 · Branch: `feat/north-taiwan-whitebox-foundation` (from `feat/opus55-xinyi-visual-quality` @ `ede7960`)
Environment: Windows 11, venv `D:\Users\EDDY\.venvs\acw-ntw` (pins identical to `requirements-citygen-v2.txt` + `duckdb==1.4.1`), Blender 5.2.1 LTS headless.
No Unreal launched. No accepted Xinyi file modified.

**Convention:** *MEASURED* = produced by a script in `tools/ntw/` from pinned input, evidence committed in `data/ntw/`.
*ESTIMATE* = arithmetic on measured values with the assumption stated. *UNKNOWN* = could not be measured; no number invented.

---

## 0. Verdict

| Question | Answer |
|---|---|
| Can the accepted whitebox pipeline run on real data outside Xinyi? | **Yes.** 3 pilots, 31,311 components, 1.04 M triangles, **0 failures**, Blender 5.2 clean, reproducible hashes. |
| Is the geometry the bottleneck for the full theater? | **No. Height and footprint-completeness data are.** Outside Taipei, 92–99.9 % of buildings have no height anywhere (Overture) and would be a flat 9.6 m. |
| Is a 60 × 60 km box the theater? | **No.** Six core regions = **5,182 km²** of land inside a **113.8 × 96.7 km** box (+Yilan: 7,375 km², 113.8 × 109.6 km). |
| Can Xinyi's ENU frame be extended across the theater? | **No** (up to 186 m placement error, 0.5 % N–S scale error even at Xinyi). Use an EPSG:3826-based NTW frame; place Xinyi by a measured affine. |
| Go / no-go for a theater-wide build | **NO-GO now. GO for a bounded next step** (§12): per-L1-cell sharded pipeline, full-Taipei WFS build, and a height-source decision for the other regions. |

---

## 1. Git safety

- Active checkout (`main`, with untracked `unreal/Plugins/`, `data/generated/taipei/{era,terrain,…}`) was **not touched**.
- `git fetch origin`; remote `feat/opus55-xinyi-visual-quality` = `ede7960d8ec05b2aa521b1e4c65b5bbd667c456d` (matches the handoff).
- Work is in a separate worktree `..\air-combat-world-ntw` on new branch `feat/north-taiwan-whitebox-foundation`. No clean/reset/force operations. PR #9 / #14 untouched.
- `git diff origin/feat/opus55-xinyi-visual-quality -- tools/citygen_v2 tools/compiler` is empty; the branch only **adds** `tools/ntw/`, `data/ntw/`, `tests/test_ntw_foundation.py`, `docs/…`, a `.gitignore` line.

## 2. Buju reuse findings

**Buju was located**, not guessed: it is `eddy121384-ui/Taipei-Maps` (GitHub) = `C:\Users\EDDY\Documents\GitHub\Taipei-Maps` (HEAD `1c5d199`). The existing `docs/buju-technical-audit.md` (2026-09-11) was re-checked against the real repo.

| Capability | Status in Buju (verified in code) | Status in Skyfront |
|---|---|---|
| Taipei WFS paged ingestion (`hits`, count=5000, dual endpoint, dedupe by id) | `tools/data/download_taipei_building_height_citywide.mjs` | **Ported as pattern** in `tools/ntw/fetch_taipei_wfs.py` (projected EPSG:3826 output). Re-measured: 373,532 hits = 373,532 unique — identical to Buju's 373,532. |
| Height semantics (`1_bud_high` → top−entrance → floors×3.2 → 9.6) | `taipei_building_height_semantics.mjs` | **Already ported verbatim** (`tools/taipei/vendor/buju/`); now also a Python port `tools/ntw/heights.py`, **tested for parity against the vendored `.mjs`** via node. |
| Overture buildings | **Render-only** PMTiles overlay (`shared-map-core.js`, releases `2026-07-22.0`/`2026-06-17.0`). **No Overture building ingester, no height extraction.** Overture *Places* via DuckDB (`extract_overture_places_bbox.py`) only. | **New** here: `extract_overture_buildings.py`, `fetch_overture_footprints.py` (DuckDB over the public S3 GeoParquet). |
| OSM buildings | **Never used** (OSM = POI hole-filler + rail relations). | OSM is reached only as the OSM-sourced share of Overture; raw Overpass counts measured as an independent check (§5). |
| Spatial filtering / batching / caching / resume | WFS paging only; Planetiler tile build | New: band-partitioned extraction, ignored parquet/ndjson caches with manifests. **Resume is NOT implemented** (§11). |
| Coordinates | 4326 interchange; hand-rolled TWD97→WGS84 | Superseded by pyproj + NTW frame (§7). |
| 3D massing / whitebox export | **None** (MapLibre `fill-extrusion`) | Accepted Skyfront Xinyi pipeline (reused unchanged). |
| North Taiwan rail (OSM `relation/full`, pinned) | `build_north_taiwan_urban_rail.mjs`, `public/generated/north_taiwan_urban_rail_*.geojson` | **Reusable, not yet ingested** (next step). |
| Footprint-retention audit (Planetiler z16) | `audit-taipei-building-footprints.bat` | Not needed: Skyfront does not tile through Planetiler. |

Honest summary: Buju's "large-scale / international building data" is an Overture **rendering** overlay, not a data pipeline. Reusable substance = WFS pattern, height semantics, pinning/audit-manifest discipline. Everything about large-area Overture building ingestion had to be built.

## 3. Verified data providers

All facts below were measured in this session unless marked.

| Provider | Footprint | Height | Floors | Type | Stable ID | Coverage in theater | Licence / reuse |
|---|---|---|---|---|---|---|---|
| **Taipei WFS** `taipei_vioc:tp_building_height` | yes (per-unit records, EPSG:3826 available) | **yes — 99.98 %** (`1_bud_high` 373,467 of 373,532; floors×3.2 for 65) | yes | no | WFS feature id | **Taipei City only**: 373,532 records, 35.1 km² footprint | **UNVERIFIED** (no licence statement found; see §13) |
| **Overture buildings** `2026-09-23.1` | yes | **0.01–5.6 % per region** | 1–25 % | `class`/`subtype` partly | GERS UUID | whole theater, 542,874 rows | per-record: OSM rows **ODbL-1.0**; ML rows from Zenodo 8174931 **CC-BY-4.0** (record's own page; Overture license field is null) |
| ↳ OSM-sourced rows | yes | 7,760 of 228,935 in bbox | some | yes | OSM id (`src_record`) | 78,433 in Taipei | ODbL |
| ↳ Zenodo 8174931 rows (Shi et al., East-Asia ML footprints) | yes | **none (0 of 343,230)** | **none** | no | no | 60 % of all rows | CC-BY-4.0 |
| **OSM raw** (Overpass) | yes | rare | some | yes | yes | Taipei 78,591; New Taipei 49,493 (mirror base 2026-06-01); Taoyuan 57,930; Hsinchu C 6,774; Hsinchu Co 10,318; Yilan 15,611; **Keelung UNKNOWN (HTTP 500 on 2 attempts × 3 mirrors)** | ODbL |
| **MOI 2025 20 m DTM** (z13 Terrarium mirror `yhzkiki/…`) | — | terrain | — | — | — | all 442 land-touching tiles present (§6) | Gov. Open Data License v1 (source); mirror tagged `license:other` |
| **Overture transportation / base** | roads, water, airports | — | — | — | yes | 323,867 segments; 44,420 water features; 13 runway + 356 taxiway features | ODbL |
| MOI/NLSC national LOD1 3D building model | yes | **yes (LOD1 prisms)** | — | — | — | per official slides: national build 2019, 2022 refresh of ~2.15 M models incl. New Taipei, Taoyuan, Hsinchu | **Not acquired. Access, format, licence UNVERIFIED** (from a web search of an MOI presentation, not from the data) |
| Google 3D / photogrammetry | — | — | — | — | — | — | **Excluded by policy** |

OSM-vs-Overture cross-check: Overture's OSM-sourced rows ≈ raw OSM (Taipei 78,433 vs 78,591; Taoyuan 56,589 vs 57,930; Hsinchu City 6,717 vs 6,774) → OSM adds nothing beyond Overture for footprints.

### Source priority and fallback policy

1. **Authoritative surveyed layer where one exists** (Taipei WFS). Heights from Buju semantics.
2. **Overture, OSM-sourced rows** (carry OSM tags; sometimes explicit height/floors).
3. **Overture, Zenodo ML rows** (footprint only).
4. Height: explicit → floors×3.2 → **9.6 m, tagged `fallback_9.6m`** (never silently).
5. **No cross-source duplicates:** a lower-priority row is dropped if ≥ 50 % of its area is covered by a higher-priority footprint (measured in Taipei: 84.4 % of Overture rows, 90.5 % of the OSM-sourced ones, lie mostly inside a WFS footprint). Rows with < 5 % overlap (**10.6 %, 11,505 rows in Taipei**) are *candidate backfill* but **must not be auto-ingested inside the WFS area** until visually checked (could be stale/misregistered duplicates).
6. Per-building provenance is carried in the ledger: `provider`, `record_id`, `height_source`, `ground_elev_m`.
7. An Overture row flagged `is_underground` is excluded (ledgered as `excluded_underground`; 36 in the core theater).

## 4. Geographic theater (MEASURED, `tools/ntw/theater.py`)

Boundaries: Overture `divisions/division_area` (`subtype=region`, `class=land`), release `2026-09-23.1`, areas in EPSG:3826.

| Region | Land km² (mainland) | lon/lat bbox |
|---|---:|---|
| 臺北市 Taipei | 269.8 | 121.457–121.666, 24.961–25.210 |
| 新北市 New Taipei | 2,059.7 | 121.283–122.007, 24.673–25.300 |
| 基隆市 Keelung | 132.9 (+1.2 km² islets excluded) | 121.627–121.809, 25.052–25.196 |
| 桃園市 Taoyuan | 1,205.8 | 120.986–121.480, 24.586–25.123 |
| 新竹市 Hsinchu City | 107.1 | 120.879–121.034, 24.713–24.853 |
| 新竹縣 Hsinchu County | 1,407.0 | 120.930–121.412, 24.427–24.946 |
| **Core six** | **5,182.4** | **EPSG:3826 E 237,803–351,649, N 2,702,381–2,799,079 → 113.8 × 96.7 km (11,009 km² box)** |
| 宜蘭縣 Yilan (evaluate) | 2,192.8 | 121.318–121.966, 24.309–24.988 |
| **Core six + Yilan** | **7,375.2** | **113.8 × 109.6 km (12,483 km² box)** |

- A 60 × 60 km box (3,600 km²) is **smaller than the land area alone**.
- Terrain: all 442 z13 DTM tiles that touch the land boundaries exist in the mirror (mean valid fraction 0.886; invalid = sea). Pixel ≈ 17.3 m at 25°N (20 m source). **Offshore terrain/bathymetry: not covered by this DTM** (sea = NODATA); flight over water needs a separate sea-level/bathymetry decision (UNKNOWN; not needed for whitebox).
- Land buildings vs flight space are separable: offshore flight volume adds area but no building workload. Coastline from Overture `base/water` + `divisions` land polygons (the same polygons used here); not separately processed.

## 5. Coverage survey (EXACT over pinned Overture; `coverage_manifest.json`, `coverage_map.svg`)

Overture `2026-09-23.1`, 572,165 rows in the theater bbox; 542,874 inside the seven regions (centroid-in-boundary, 150 m-simplified boundaries; border rows may flip within ~150 m), 29,291 outside (neighbouring counties/sea).

| Region | Buildings | per km² | explicit height | floors only | **fallback 9.6 m** | height-or-floors |
|---|---:|---:|---:|---:|---:|---:|
| Taipei | 108,399 | 401.7 | 6,055 (5.6 %) | 20,607 | 81,737 | 24.6 % |
| New Taipei | 134,829 | 65.5 | 591 (0.4 %) | 11,499 | 122,739 | 9.0 % |
| Keelung | 13,910 | 104.7 | 3 | 106 | 13,801 | 0.8 % |
| Taoyuan | 141,046 | 117.0 | 855 (0.6 %) | 3,719 | 136,472 | 3.2 % |
| Hsinchu City | 27,629 | 257.9 | 45 | 887 | 26,697 | 3.4 % |
| Hsinchu County | 53,802 | 38.2 | 203 | 577 | 53,022 | 1.4 % |
| **Core six** | **479,615** | | 7,752 | 37,395 | **434,468 (90.6 %)** | |
| Yilan | 63,259 | 28.8 | 4 | 714 | 62,541 | 1.1 % |

**Footprint availability ≠ height availability.** Overture's footprints exist everywhere; heights essentially do not (outside Taipei, only **5.0 %** of the other five core regions' 371,216 rows have a height or a floor count).

**Footprint *completeness* — the exact Taipei comparison** (`taipei_wfs_vs_overture.json`, whole city, planar EPSG:3826):

- WFS 373,532 records / 35.15 km² vs Overture 108,399 rows / 30.12 km² (Overture has **29 % of the records but 85.7 % of the footprint area** — it merges complexes into big polygons; WFS is per-unit).
- 67.8 % of WFS footprint area is covered by Overture; **29.4 % of WFS features are not touched by any Overture polygon**.
- Consequence: Overture is a *massing-grade* footprint source, not a count-equivalent of the authoritative layer. **True building counts outside Taipei are UNKNOWN**; 479,615 is a lower bound for "Overture parts", not an estimate of reality.

Known gaps: height outside Taipei; no authoritative reference to measure completeness outside Taipei; Keelung OSM raw count; roads/water/airports not processed to geometry; offshore.

Transport/water/airfield availability (Overture, bbox counts, MEASURED): roads incl. 1,536 motorway and 8,372 primary segments; water: 2,100 river, 19,172 stream, 634 basin features; **aeroway: 13 runway, 356 taxiway, 62 helipad, 31 apron** — usable as an airbase/runway seed but unverified visually.

Expected whitebox workload → §11.

## 6. Terrain

Mirror tile index (`dtm_coverage.json`, MEASURED): 4,166 z13 tiles in the index, 2,066 with data (Taiwan + islands); theater regions need 442 unique tiles (Taipei 28, New Taipei 158, Keelung 15, Taoyuan 92, Hsinchu City 16, Hsinchu County 99 (2 all-NODATA), Yilan 154 (4 all-NODATA)). Same transport and decode as the accepted Xinyi terrain. Not yet tiled to 500 m terrain tiles outside the pilots.

**Vertical-datum finding (MEASURED, pilot A, n = 24,353 buildings with surveyed WFS ground):** DTM − surveyed ground: median **−0.025 m**, median |Δ| 0.201 m, P95 0.697 m, 3 buildings > 3 m. Xinyi's accepted global correction was **+0.342 m** (its median was −0.342 m). Applying Xinyi's offset in this Taipei sector would *create* a **+0.317 m** median error. → The Xinyi offset is **area-specific**, not a theater constant; outside Taipei no surveyed ground exists to calibrate, so DTM absolute error there is **UNKNOWN** (building bases must be DTM-based and carry that caveat).

## 7. Coordinate architecture (MEASURED, `coordinate_study.json`, `tools/ntw/frame.py`)

**Accepted Xinyi frame** = equirectangular tangent plane at (121.5654, 25.0330), `x = R·Δλ·cosφ0, y = R·Δφ` with R = 6,378,137 (the equatorial radius used for both axes).

Findings:

1. **It is anisotropic against true ground even inside Xinyi.** Exact affine to EPSG:3826 (2.5 km extent, residual **0.12 m**): east scale **1.00054**, north scale **0.99503**, axes rotated **0.2393°** (grid convergence). A 500 m ENU tile is **500.3 m E–W × 497.5 m N–S** on the ground. It is self-consistent (terrain, buildings use the same contract), so Xinyi is *not wrong internally* — but it is not metric-true, and ignoring the rotation misplaces the far edge of Xinyi by 10.4 m vs. the real grid.
2. **Stretching it across the theater fails.** Distance error from the Xinyi origin: Hsinchu City −38 m, Yilan +112 m, Su-ao +174 m, Wufeng +186 m (0.06–0.46 %); flat-plane curvature drop 331 m at 65 km, 528 m at 82 km. A single best-fit similarity over ±50 km leaves 376 m max residual.
3. **EPSG:3826 (TM2) is metric-true to ≤ 0.009 %** over the whole theater (worst −7.2 m at 82 km; point scale 0.9999–0.99998) and is the CRS of the authoritative source and the DTM.
4. float32: precision at 114 km from an origin is 7.8 mm (1 cm in UE centimetre units) — acceptable for *placement*, **not** for vertices; at tile-local ≤ 500 m it is 0.03 mm.

**Decision (proposal, implemented in `frame.py` and used by all pilots):**

- **NTW frame** = EPSG:3826 minus a fixed origin `(224,000, 2,688,000)` (multiples of the 32 km top level, so all levels nest). x east, y grid-north, z TWVD2001 orthometric. All theater coordinates are positive, ≤ 120 km.
- **Geometry stays tile-local** (≤ 500 m from the tile origin, float32-quantised before triangulation, exactly as accepted); world position is a double-precision tile transform. Unreal 5 Large World Coordinates make double placement natural; **runtime behaviour on iPhone-class hardware is unverified**.
- **Xinyi is not re-expressed.** Its 25 GLBs and Landscape remain in their ENU frame and are placed into NTW as a **Level-3 sector instance** with the measured affine (translation (83,056.82, 81,551.86) m, linear part `[[1.000531, −0.004155],[0.004178, 0.995026]]`). The GLBs stay byte-identical. *Open decision for the integration gate:* either apply that affine (non-uniform instance scale, true-ground fit) or keep Xinyi as an isolated metric-approximate sector with a visible ≤ ~12 m seam at its boundary. The Xinyi **Landscape** cannot simply take a non-uniform scale — that is untested and listed as a risk.
- Tests (`tests/test_ntw_foundation.py`): frame round-trip < 1 mm; TM2 distance vs geodesic < 0.02 % at 5 far points; level nesting; the Xinyi ENU formula pinned to the accepted value; the Xinyi→NTW affine residual < 0.2 m and its axis scales.

## 8. Tile and LOD architecture (proposal + measured prototype)

| Level | Cell | Content | Source | Notes |
|---|---|---|---|---|
| **L0** | 32 km (13 non-empty cells) | far terrain + settlement silhouettes | DTM + merged L1 | no building identity |
| **L1** | 8 km (136 non-empty) | block massing (HLOD proxy of L2) | derived from L2 | identity map child→L1 id |
| **L2** | 500 m owner tile (13,701 non-empty, Overture-only) | individual building whitebox (the accepted pipeline) | WFS/Overture | owner = floor(vertex-mean centroid / 500 m) — **the Xinyi rule** |
| **L3** | existing accepted sectors (Xinyi, 25 tiles) | detailed urban/combat sector | accepted GLBs + affine | untouched |

Rules proven in the pilots: ownership by centroid with **no clipping and no duplication** (4–8 % of components overhang their tile by up to 164 m — legal by design); cell indices nest exactly (L2⊂L1⊂L0; test-covered); deterministic regeneration (identical hashes on repeat runs); building identity = source id + part index, carried in the ledger.

**LOD prototype** (`lod_prototype.py`, `lod_prototype.json`; sizing study, not an accepted asset): L1 = 50 m-cell union (+1/−1 m, simplify 2 m), L0 = per-500 m silhouette at area-weighted P75 height.

| Pilot (6.25 km²) | L2 tris | L1 tris (×) | L0 tris (×) |
|---|---:|---:|---:|
| A dense Taipei | 928,660 (148.6 k/km²) | 137,676 (**6.7×**) | 4,200 (**221×**) |
| B Taoyuan suburban | 32,152 (5.1 k/km²) | 27,776 (**1.2×**) | 4,140 (7.8×) |
| C Banqiao dense (Overture) | 82,608 (13.2 k/km²) | 65,060 (**1.3×**) | 5,904 (14×) |

Implication: block-union L1 works in the dense core but **does nothing in sparse areas**; there L1 needs culling/instancing rather than merging (untested idea). Visible-budget arithmetic, *not a device result*: 1 M L2 triangles covers a radius of 1.5 km over A-like density but 7.9 km over B-like density, so budgets must be **per-cell triangle budgets, not radii**.

Not done: Unreal World Partition/HLOD import of any of this (`do not replace the current runtime architecture prematurely`).

## 9. Pilots (MEASURED; `pilot_results.json`, plan views in `docs/evidence/ntw/`)

Each pilot = 5 × 5 block of 500 m NTW tiles (2.5 km, same extent as Xinyi), built with the **unchanged accepted geometry stack** (repair → tile-local float32 → GEOS CDT → trimesh → GLB reload → strict QA). Inputs pinned (hashes in the pilot reports and ignored-cache manifests).

| | A · Taipei Main Station | B · Taoyuan Bade (suburban) | C · Banqiao (dense) |
|---|---|---|---|
| Provider | Taipei WFS (authoritative) | Overture only | Overture only |
| Source parts → emitted | 24,353 → 24,353 (47 GEOS-repaired) | 2,047 → 2,047 | 4,909 → 4,909 |
| GLB components / triangles | 24,355 / **928,656** | 2,047 / 32,152 | 4,909 / 82,608 |
| Tiles / GLB bytes | 25 / 30.3 MB | 25 / 1.54 MB | 25 / 3.84 MB |
| Height source | 99.99 % surveyed | **96.5 % fallback 9.6 m**, 3.0 % floors, 0.4 % explicit | **91.9 % fallback**, 7.5 % floors, 0.7 % explicit |
| Failures / rejected / underground | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Duplicate ownership / wrong-tile (rule recompute) | 0 / 0 | 0 / 0 | 0 / 0 |
| Placement: GLB → lon/lat vs source ring | < 0.05 mm | < 0.05 mm | < 0.05 mm |
| Blender 5.2.1 imported-buffer audit | PASS (24,355 meshes, triangle count equal) | PASS (2,047) | PASS (4,909) |
| Repeat-run tile + manifest hashes | **identical** (`5704f91b…`) | **identical** (`cd0a7c91…`) | **identical** (`aa95b83c…`) |
| Peak RSS (builder) / wall (3 runs in parallel) | 562 MB / 728 s | 122 MB / 38 s | 169 MB / 76 s |

Blender zero-counts across all pilots: non-finite vertices, non-tri faces, zero-area triangles, wrong roof/base/wall triangles, non-manifold and inconsistent edges, non-positive volume, wrong tile transform.

Checks and their honesty:
- The **placement check has a negative control**: shifting the source by 1 m makes it report 1.0001 m (so "0.0" is real, not a vacuous test). Initial version missed courtyard holes and falsely reported 18.5 m for A; fixed, documented here.
- A is **1.9 × Xinyi** (928,656 vs 485,936 triangles; 24,355 vs 11,130 components), so the stack scales to a denser sector without change.
- Vertical/DTM per pilot: B median DTM 142 m, C 7.4 m, A 3.4 m — plausible terraces/plain, not independently verified.
- The existing Blender audit's *renders* were blank (its camera is framed for Xinyi coordinates); only its numerical gate is claimed. The plan-view PNGs are drawn from the exported GLB roofs by `render_pilot_plan.py`.
- Declared difference from the Xinyi gate: parts GEOS can't turn into area and underground rows are *ledgered with a reason* instead of failing the run. All were 0 in the pilots, so it did not matter here; Overture ML data elsewhere may exercise it.

## 10. Regression and determinism evidence

- Re-running the accepted `build_full_xinyi.py` on the pinned source (SHA `c7ca8da1…` verified): 11,128 parts, 8 hero parts, 25 tiles, **485,936 triangles, 14,853,448 bytes, 0 failures** — **byte-identical** to the local accepted tiles Unreal imported (manifest `14c2890b…`).
- **Pre-existing, not caused by this branch:** the *CI-artifact* manifest the docs/tools pin (`bfaf5ab0…`) is **not** reproduced on Windows: 22/25 tiles identical; 5 of 11,130 nodes (3 tiles) differ with identical triangle/byte counts and |Δarea|,|Δvolume| ≤ 1.1e-4. Same-platform runs are byte-deterministic; cross-platform GEOS/trimesh differences exist. → NTW manifests must be compared **within one canonical build platform**.
- 14 NTW tests + the existing `test_compiler`/`test_citygen_v2` suites pass (17 passed, 9 skipped, unchanged).

## 11. Scale estimate (`scale_estimate.json`)

Unit costs **MEASURED** on pilots: WFS-like parts 38.1 tri / 1,243 B each; Overture-like 16.5 tri / 774 B; builder 24 KB RSS per component (whole block in memory); 0.017–0.030 s per component (pessimistic, pilots shared one CPU). Xinyi reference: 43.7 tri/component.

| Scenario (**ESTIMATE**) | Components | Triangles | GLB | Single-core time (upper bound) |
|---|---:|---:|---:|---:|
| S1 Overture only, core six (exact count = lower bound) | 479,579 | 7.9 M | 0.37 GB | 2.2 h |
| **S2 Taipei WFS + Overture elsewhere (planning case)** | 744,712 | 20.4 M | 0.75 GB | 4.8 h |
| S3 = S2 + Yilan | 807,971 | 21.4 M | 0.80 GB | 5.1 h |
| S4 stress: other regions as under-recorded as Overture is in Taipei (assumption only, overstated) | 1,652,704 | 35.3 M | 1.45 GB | 9.0 h |

- The real total is **UNKNOWN**: S1–S4 bracket it; footprint truth outside Taipei is unmeasured. Not extrapolated from one dense block: A and B/C unit costs are kept separate.
- **Bottlenecks:** (1) *memory* — one process cannot hold the theater; must shard per L1 8 km cell (136 non-empty; Overture max 48,422 buildings per L1 cell, Taipei WFS L1 cells are larger); (2) *height data* (§0); (3) acquisition: Overture DuckDB scans take ~1.5 min per bbox regardless of size (Taipei 166k rows ≈ 2–3 min; full theater by 4 bands ≈ ≤ 15 min, ESTIMATE); Taipei WFS full city ≈ 1.5 min (MEASURED); (4) Blender audit time (A: 17 min under load); (5) no resume/checkpointing yet.
- **Local feasibility:** yes with sharding (disk < 1.5 GB output, minutes–hours of compute; the S2 build is parallel per tile). **CI/cloud:** feasible as a sharded matrix job; hosted-runner limits (CPU/RAM/6 h) were *not* verified in this session.
- **Mobile runtime:** complete offline data ≠ visible geometry. S2's 20 M L2 triangles can never be resident; the L1/L0 levels (§8) and per-cell budgets are required. **No device performance claim is made. Mobile PASS: NOT TESTED.**

## 12. Risks and next steps

Risks (ranked):
1. **Height data outside Taipei** — 91–100 % fallback; the skyline would be a flat 9.6 m carpet. Evaluate the MOI/NLSC national LOD1 3D building model (UNVERIFIED access/licence) and per-city open data before any theater build.
2. **Footprint completeness outside Taipei is unmeasurable** with current sources (Overture holds 29 % of Taipei's authoritative record count / 86 % of its area).
3. **Xinyi frame anisotropy** (0.5 % N–S): the Xinyi sector will not seam perfectly into a metric-true theater without the affine; Landscape handling untested.
4. **Cross-platform byte determinism** is not guaranteed (5/11,130 Xinyi nodes).
5. **Licensing:** WFS licence unverified; Overture rows are ODbL (OSM) / CC-BY-4.0 (Zenodo) — attribution + share-alike obligations for derived data need a decision before shipping.
6. **Vertical datum** varies by area (−0.34 vs −0.03 m in Taipei) and cannot be calibrated elsewhere.
7. **L1 clustering ineffective in sparse areas** (1.2–1.3×).
8. Overpass/S3 availability for reproducibility (Keelung OSM count failed); the Overture release is pinned, Overpass is not (base timestamps differ per mirror).

Recommended next steps (each its own gate):
1. **Go/no-go:** *no-go* on a theater-wide generation now. *Go* on: (a) shard `build_pilot.py` per L1 cell with per-shard checkpoints; (b) full-Taipei WFS build (373,532 parts ≈ 14 M triangles, ≈ 0.46 GB) as the first large run and canonical-platform decision; (c) acquire and audit the NLSC LOD1 model for height/completeness in New Taipei/Taoyuan/Hsinchu.
2. Terrain tiling in the NTW frame for the pilot sectors; decide the Xinyi integration option and run the locked representative + full-Xinyi regression gates before changing any Xinyi placement (per `AGENTS.md` coordinate-transform drift rule).
3. Ingest Buju's north-Taiwan rail layer and Overture airports/runways; add the sparse-area L1 strategy; only then consider an Unreal World Partition / HLOD import experiment.

## 13. Licensing and provenance notes

- **Overture `2026-09-23.1`** (pinned; also present: `2026-08-19.0`, `2026-09-23.0`). Per-record licences read from the data: OSM rows `ODbL-1.0`; Zenodo rows have a null licence field — the Zenodo record 8174931 ("A first high-quality vector data of buildings in East Asian countries…", 2023-07-22) states **CC-BY-4.0**. Attribution required; ODbL share-alike applies to derived databases.
- **Taipei WFS**: no licence statement captured; treat as **UNVERIFIED** (consistent with the earlier finding in `docs/taipei-urban-visual-language-research-v0.md` §18). Government-data openness is likely but must be confirmed before redistribution of derived tiles.
- **MOI 2025 DTM**: official dataset 176927, Government Open Data License v1; HF mirror is a derivative transport (mirror files hashed per tile in pilot reports).
- **No Google 3D imagery or photogrammetry** used.
- Provenance fields persisted per building in each pilot ledger. Ignored caches carry manifests (hits, sha256, fetch time, release pin).

## 14. Reproduction

```text
venv: D:\Users\EDDY\.venvs\acw-ntw   (python -X utf8)
tools/ntw/theater.py                  -> data/ntw/theater_regions.json
tools/ntw/extract_overture_buildings.py --release 2026-09-23.1 --xmin A --xmax B --out ...   (4 bands: 120.85/121.15/121.40/121.65/122.05)
tools/ntw/coverage_survey.py          -> coverage_manifest.json, coverage_map.svg
tools/ntw/fetch_taipei_wfs.py --out data/generated/ntw/wfs_taipei_citywide.ndjson
tools/ntw/fetch_overture_footprints.py --bbox ... --out data/generated/ntw/ovt_<pilot>.parquet   (bboxes in pilots.json)
tools/ntw/compare_taipei.py, probe_sources.py, dtm_coverage.py, coords_study.py
tools/ntw/build_pilot.py --pilot <id> --out <new dir>     (refuses to overwrite)
blender -b --python tools/ntw/run_blender_audit.py -- --tiles .. --numerical .. --out .. --screenshots ..   (ABSOLUTE paths)
tools/ntw/validate_pilots.py, lod_prototype.py, scale_estimate.py
python -m pytest tests/test_ntw_foundation.py
```

Large outputs (`data/generated/ntw/**`: Overture parquet caches, 175 MB WFS ndjson, pilot GLBs, Blender JSON) are git-ignored and **not committed**; committed data is 0.37 MB + three PNG plan views.

Sources consulted for candidates only (not for data): [MOI/NLSC 111-year 3D building model update presentation](https://landoffice.chcg.gov.tw/files/內政部國土測繪中心%20111%20年度三維建物模型更新及精進%20作業內容及執行成果重點說明_127_1120531.pdf); [Zenodo 8174931](https://zenodo.org/records/8174931).
