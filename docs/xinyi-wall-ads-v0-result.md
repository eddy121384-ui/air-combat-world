# Taipei large wall ads v0 — result

Status: **complete — restrained wall-ad layer accepted for review (27 boards); no Image 2.5 assets; no
construction wraps.** Density deliberately deviates from the brief's literal 8 % (§3).

Branch `feat/opus55-xinyi-visual-quality`, on top of `a00ac29` (wall-ad research + Street View verification).
Inputs: `docs/xinyi-wall-ads-identity-research-v0.md` (incl. §K survey), `docs/taipei-urban-visual-language-research-v0.md`,
`docs/xinyi-facade-grammar-v0a.md`, `docs/xinyi-facade-metadata-payload-v0.md`.
Evidence (local, not committed): `unreal/Saved/XinyiLook/evidence/wall_ads_v0/` (`gate0/`, `frames/`, `sheets/`,
`harness/`). Offline outputs: `unreal/Saved/XinyiLook/wall_ads/`.

---

## 0. Summary

| item | result |
|---|---|
| raw ring edges >= 5 m (all ordinary records) | 31,216 |
| research "exposed wall" prime pool, recomputed | 1,162 (the brief's ~1,090) |
| **genuinely blank, street-exposed walls (Gate 0 valid)** | **109** walls on 87 buildings |
| research prime pool walls that are genuinely blank | 33 / 1,162 (stepped party walls 27 / 181, road flanks 0 / 610, open flanks 6 / 371) |
| boards placed | **27** (25 % of the valid pool; see §3 for why not 8 %) |
| atlas | 1 x 2048² sRGB + A, 34 authored cells, sha `1fee3297...` |
| UE | 1 material (`M_XinyiWallAds`), 1 texture, 1 two-triangle mesh, 1 HISM, 54 triangles |
| DAY / DUSK / NIGHT | pass (§6) |
| motion / shimmer / cull | no shimmer or mip flashing; a 0.9 km hard cut visibly popped, so the cull sits beyond the district (§6.4) |
| perf (UHD 770, same-session interleaved) | within noise of zero at LOW / MID / HIGH, day and night (§7) |
| regression | ads hidden == HEAD: DAY 18 / 25, DUSK 14 / 15, NIGHT 14 / 15 bit-identical, rest at the known renderer-noise signature; off build == on build outside board pixels (§8) |

## 1. Gate 0 — wall eligibility

### 1.1 The blank-wall signal

The procedural facade paints windows on **every** wall, so "the facade currently has windows" carries no information.
Gate 0 therefore uses real geometry plus the Taiwan building code:

* **建築技術規則建築設計施工編 §45(2)** [O, quoted in a Taipei appeal decision]: an exterior wall immediately adjacent to the
  neighbouring lot may not open doors, windows or balconies toward it unless the wall is >= 1 m from the boundary.
* A wall sample is a **lot-line sample** when another building group's footprint lies within 1.0 m outward (probes at
  0.3 / 0.65 / 1.0 m). The boundary must lie in that gap, so this wall is < 1 m from it: by regulation, windowless toward
  the neighbour. The gap histogram is sharply bimodal (4,085 host walls at <= 0.3 m, 383 at 0.3-0.65, 356 at 0.65-1.0,
  229 at 1.0-1.25 ...), so the 1 m rule separates true party walls from setbacks rather than cutting through a mode.
* **Same-group footprints never count** (a tower's own podium / wing is the same building, its step faces have windows).
* The usable surface is the longest contiguous lot-line run, from 0.6 m above the highest obstacle in front (lower
  neighbour, rooftop props on its roof, anything that hides the wall from a 30° oblique aerial view) to 1 m below the
  parapet.

Walls not on a lot line (road flanks, open flanks, setbacks) are treated as **windowed** and never get a board. This is
why the research's road-flank class B (610 walls) contributes nothing: road-facing flanks are not party walls.

### 1.2 Funnel (31,216 ring edges >= 5 m)

| reason | edges |
|---|---|
| host class: modern / premium residential | 3,872 |
| host class: office / podium | 2,014 |
| host class: rooftop-structure record (< 40 m² roof parts) | 2,086 |
| host class: school | 805 |
| host class: civic / landmark (incl. Taipei 101 surround, SYS hall) | 250 |
| host class: unknown generation | 343 |
| **not on a lot line -> windowed** | **10,685** |
| faces only the building's own wing -> windowed | 5,968 |
| on a lot line, but neighbour as tall (no exposed band >= 6 m) | 3,862 |
| lot-line run < 5 m | 503 |
| occluded from a 30° aerial view | 215 |
| neighbour's rooftop props (頂加 / sheet covers / tanks) leave < 6 m | 137 |
| "neighbour" is an institutional / commercial complex (one structure split into WFS records, not a lot line) | 191 |
| only a lane / alley in front (service way or < 6 m) | 79 |
| no street exposure at all (block interior) | 68 |
| view opens onto a park / garden / school ground within 25 m | 28 |
| an existing projecting street sign in the air space | 1 |
| **valid** | **109** |

Taipei 101 and the other hero records are suppressed from the source and never become hosts; schools, civic, landmark,
office, podium, modern and premium buildings are excluded by class before any geometry is evaluated.

### 1.3 Valid pool (109 walls, 87 buildings, 82 groups)

| | |
|---|---|
| generation | huaxia 70, legacy 39 |
| archetype | res_tower 46, huaxia 43, walk-up 20 |
| frontage condition | road seen over the lower neighbour 66, own street frontage ends at the wall 32, corner (both) 11 |
| major-road exposure | 45 |
| planned core | 29 |
| lot-line run (m) | 5-8: 55, 8-12: 25, 12-16: 19, 16-24: 7, 24-40: 2, >= 40: 1 |
| blank band (m) | 6-9: 30, 9-12: 25, 12-18: 15, 18-30: 21, 30-60: 15, >= 60: 3 |
| blank area (m²) | 30-60: 26, 60-120: 33, 120-250: 25, 250-500: 17, 500-1000: 5, >= 1000: 3 |
| placement capacity | every valid wall fits a >= 4 m board (109) |

Offline plots: `gate0/gate0_valid_by_condition.png`, `gate0_valid_and_placed.png`, `gate0_size_distribution.png`,
`research_pool_vs_gate0.json`. Two rule corrections were made **globally** after inspecting the first map (not per
building): complexes split into several WFS records (the Dome wing, the central mixed complex, courtyard compounds)
produced false "party walls" -> neighbour must be ordinary building stock; and block-interior walls that no street sees
-> street exposure required. Default OSM residential widths (7.6 m) had made every 巷 a "lane"; the lane rule was aligned
with the frontage-role convention (service ways or < 6 m).

### 1.4 What Gate 0 cannot know

* Walls facing a vacant lot or surface car park on the lot line (a classic ad wall) are not detected: without a neighbour
  footprint there is no reliable lot-line signal, and the brief rules out inferring party walls from incomplete
  cadastral data. These walls are simply not used.
* A lower neighbour recorded as a separate WFS record of the same real building (not grouped) would look like a party
  wall; the complex / class rules remove the large cases, small ones may remain.
* In-game, the facade shader still paints windows on the blank walls the boards sit on (research §J.6 / M5). Boards
  therefore hide procedural windows; by the §45 signal those walls are windowless in reality. The mismatch is the
  shader's, and is most visible at night (a board is a dark rectangle among lit windows).

## 2. Placement

Deterministic, sha256-keyed, no building ids:

```
score = road (major 1.0, other 0.6) x corner 1.5 x area clamp(A / 120 m², 0.5, 1.4)
      x age (legacy 1.0, huaxia 0.8) x district (planned core 0.15) x jitter [0.7, 1.3]
```

Accepted in descending score while: one board per building group; >= 25 m between boards; **at most 2 boards within
120 m** (the survey never saw more than two large ads in one street window; this removed a 4-board cluster on one
Keelung Rd block); <= 14 per 500 m tile (<= 5 in the core); a family not repeated within 40 m; **the same artwork not
repeated within 400 m** (a family is skipped if all its cells are already used nearby). Family mix by quota (largest
deficit against the target mix, host-aware: legacy -> more aged, older towers -> more pre-sale), not by luck. >= 20 %
aged / ghost enforced by converting the lowest-scored legacy-host boards. Board = the largest atlas aspect (1:2, 1:1,
2:1) that fits 85 % of the run and 92 % of the band, 4-14 m wide, <= 24 m tall, top 10-50 % of the slack below the
parapet. Offset 0.15 m (framed canvas) or 0.04 m (painted), **measured from the tile mesh's actual wall plane**.

Fail-closed QA (`qa_attachment`): 9 points of every board must land inside a coplanar wall triangle of the accepted
tile mesh (corners within 6 cm of the plane, normal within 3°): no board in mid-air, past a wall end or above the
roof. All 27 pass; the mesh wall sits up to 5.3 cm off the footprint line and the offset is corrected per board.

## 3. Density decision: 27 boards, not 70-100

The brief's 6-10 % (default 8 %) and 70-100 boards were derived against the research pool of ~1,090 exposed walls
(research §D.4 / §K.7: "% of the prime pool"). Gate 0 shows only 33 of those are genuinely blank; the whole valid pool
is 109. Two literal readings conflict:

* 8 % of the 109 blank walls = 9 boards (~2 per km²): below the brief's own 20-40 pilot and visually negligible;
* 8 % of the exposed pool = ~90 boards, which would need ~80 % of all blank walls: denser than the survey, which saw
  bare blank flanks next to advertised ones (§K.2 W9, W12) and never more than two ads per window.

Chosen: **OCCUPANCY = 25 % of the genuinely blank, street-exposed walls = 27 boards** (a single profile constant in
`build_wall_ads.py`). It sits inside the pilot range, stays far below the 70-100 cap, and is consistent with the survey
interpretation that most survey ads sat on blank flanks while many blank flanks were bare [I]. Stage D expansion was
**not** done: the pool cannot support 70-100 without forcing ads onto unsuitable walls. Setting OCCUPANCY = 0.08 gives
the literal 9-board variant.

Placed (27): by family pre-sale 8, clinic 6, aged / ghost 6 (+2 painted clinics = 8 aged, 30 %), education 3,
services 3, leasing 1; by bin tall 14, square 12, wide 1; by condition road-facing 13, street-end 9, corner 5; major
road 19; generation huaxia 15 / legacy 12; archetype res_tower 15 / huaxia 10 / walk-up 2; core 0; painted 5; spot-lit
at night 4; 21 distinct cells (repeats >= 487 m apart); board 4.6-14.0 m wide (median 8.5), 5.3-24.0 m tall (median
11.1); 3,248 m² of boards. Area: 14 of 25 tiles, concentrated on the Keelung Rd and western arterial corridors and the
older fabric; none in the planned core (core weight 0.15 lets better walls win).

## 4. Atlas (`tools/lookdev/build_wall_ad_atlas.py`)

One 2048² RGBA atlas: RGB = sRGB board face, A = night spot-light mask (printed canvas only). Power-of-two bins so box
mips never mix cells: tall 1:2 (16 x 256x512, y 0-1024), square (16 x 256², y 1024-1536), wide 2:1 (8 x 512x256,
y 1536-2048). 34 of 40 cells used (~90 % of the area); sha256 `1fee329764950a8fd500a1658e1048c63e2707c3fd12f65a0a976cc7894ee2af`
(identical over repeated builds). Fonts: Noto Sans TC / Noto Serif TC VF (OFL), SHA recorded in `wall_ad_atlas.json`.

**Authored, not random**: a fixed list of 34 fictional boards, each a 2-3 colour layout with one headline (vertical on
tall boards, with a smaller side column; horizontal on wide / square), one simple vector graphic and, for pre-sale, a
tag bar (預售 / 接待中心). Nothing smaller than ~1.4 m on a 10 m board.

| family | cells | examples (all invented) |
|---|---|---|
| pre-sale / housing | 7 | 青嵐苑 公園第一排 · 澄心居 捷運生活圈 · 森悅 精裝三房 · 沐光居 · 和光邸 · 晴川苑 新案公開 · 預售 安和新邸 |
| clinics | 7 (2 painted / faded) | 康和牙醫 · 仁濟中醫 針灸 推拿 · 耳鼻喉科 · 復健科 · 明德皮膚科 · painted 中醫 專治跌打損傷 · painted 齒科 |
| education | 5 | 啟明美語 · 數理 國中 高中 · 升學數理 · 文昇補習班 會考 學測 · 才藝安親 |
| local services | 6 | 眼鏡 · 養生館 足體按摩 · 平安搬家 · 冷氣 家電 維修 · 汽車美容 · 五金 建材 水電 |
| leasing | 3 | 招租 · 出租 整層辦公 · 店面出租 樓上可分租 |
| aged / ghost | 6 | ghost-painted 旅社, ghost 冷氣, sun-faded 新成屋, half-removed (torn) 新成屋, stripped board, blank weathered canvas |

Ageing is baked with low-frequency, vertically elongated streak / blotch fields (cells >= 16 x 160 supersampled px):
the first version used ~3 px speckle, which would have crawled in motion. The first stripped-frame cell drew a 3 x 4 steel
lattice that read as a window grid at range; it became a pale backing panel with a ghost of the old print.

Content policy QA (build-time, fails closed, plus `tests/test_wall_ads.py`): every character Big5-encodable (no
Simplified-only leakage) and rendered by a real glyph of both fonts (compared against the font's missing-glyph raster);
sign-atlas brand blacklist + developer / agency / chain / hospital / cram-school chain names; political words; no digit
runs, phone or web patterns; 90th-percentile HSV saturation <= 0.70 per cell (the first build failed this on five reds /
blues / orange / teal, which were muted). Logos: none. Residual risk: generic poetic project names (e.g. 澄心居) may
coincide with some real project somewhere; none is a developer or brand name and none carries contact data.

Image-ready structure: every cell records its `art` region separately from `title` / `sub` / `tag` regions in
`wall_ad_atlas.json`, so a later pass can swap the vector graphic for an illustration while text stays font-rendered.

## 5. Rendering architecture

* `M_XinyiWallAds`: its own material and **its own HLSL file** (`tools/lookdev/shaders/xinyi_wall_ads.hlsl`): a UV node
  (`wa_uv`: per-instance cell -> atlas rect, half-texel inset of the sampled mip) -> one texture sample -> `wa_shade`.
  Opaque, one-sided, default lit, used with instanced static meshes. Nothing was added to `xinyi_city.hlsl`,
  `M_XinyiCity`, `M_XinyiStreet` or any other material (test-enforced).
* Print response: base = atlas x 0.70 (x 0.95-1.04 per-board tone). The first UE pass used the raw atlas: white boards
  reached ~0.87 linear albedo against facade walls around 0.2-0.45 and read as glowing stickers (167 vs 85 / 255 sunlit,
  85 vs 20 in shade). One global factor, not per board.
* Night: unlit boards get no emission; the 4 spot-lit canvas boards (`lit`, <= 25 %, never painted / aged / leasing) get
  `base x mask x 0.55 x (1.0 at the top -> 0.35 at the bottom) x Night` (fixtures along the top edge). No light box, no neon.
* Geometry: one 2-triangle unit plane (x = 0 facing +x, UV0 = cell UV), 27 HISM instances, per-instance custom data 0 =
  (cell + 64 lit + 128 tone + 0.5) / 512. No shadow casting, no collision. Cull 3.3-3.5 km (§6.4).
* Switch: `ACW_XINYI_WALL_ADS=off` makes the asset and level stages skip the layer entirely; an absent
  `wall_ads.report.json` does the same.

| item | delta |
|---|---|
| materials | +1 (`M_XinyiWallAds`) |
| textures | +1, 2048² BC7 + mips ≈ 5.6 MB on PC (ASTC 6x6 ≈ 2.5 MB mobile); 1024² ≈ 1.4 MB BC7 / ≈ 0.6 MB ASTC 6x6 |
| static meshes | +1 (2 triangles) |
| HISM components | +1, 27 instances, 54 triangles |
| draw calls | +1 instanced draw per depth / base pass when any board is in view; 0 in shadow passes |
| vertex payload / facade shader | unchanged |

At the review ranges a board samples mip 1-3 (a 10 m board is ~62 px at 150 m against a 256 px cell), so a 1024² atlas
(max texture size 1024 on mobile) renders identically beyond ~80 m; recommended for the mobile build, not applied here.

## 6. Visual review (UE5.8, SceneCapture2D 1080p, fresh process per time of day)

Cameras (`harness/shots_extra.json`): `wa_150_keelung`, `wa_150_corner`, `wa_150_legacy` (~150 m oblique),
`wa_300_cluster`, `wa_300_tower` (~300 m), `wa_600_cluster`, `wa_600_west` (~600 m), `wa_1200_overview`, plus the 17
accepted look-dev cameras. Sheets: `sheets/ab_day_150_300.png`, `ab_day_600_1200.png` (HEAD vs candidate),
`c_day_board_zooms.png`, `c_dusk_board_zooms.png`, `c_night_board_zooms.png` (ads hidden vs on, native-pixel crops).

### 6.1 DAY (primary)

| range | read |
|---|---|
| 150 m | headline, side column and tag bar legible (沐光居 / 兩房景觀宅 / 預售, 數理 / 國中 高中); boards sit flat on the wall, frame crisp, no bleeding, no floating; a board on a walk-up above a 1 F neighbour (數理) reads like the surveyed Wanhua / Roosevelt Rd cases |
| 300 m | headlines still readable on tall boards (康和牙醫, 復健科 on adjacent older towers along the arterial); square / wide boards read as colour + one glyph |
| 600 m | "a coloured rectangle on that wall": 1-5 boards per view among the tile / window texture; nothing cluttered |
| 1.2 km | single small colour patches; the layer dissolves into the city texture as intended |

Boards per view (blobs > 40 px): 1-3 at 150-300 m, 3-5 at 600 m, 1 at 1.2 km; screen coverage 0.03-0.8 % (2.8 % in
the deliberately close Keelung view). Not saturated, not neon, not cyberpunk. Strongest before / after views:
`wa_150_legacy`, `wa_300_tower`, `wa_150_keelung`.

### 6.2 DUSK

Boards take the warm low sun like the walls (康和牙醫 turns warm cream); the 數理 board receives the cast shadow of the
rooftop shed above it (shadow reception confirmed). Shaded white boards stay muted.

### 6.3 NIGHT

Unlit boards are dark, moonlit rectangles; the 4 spot-lit canvas boards show a soft top-down wash (澄心居 gold on navy
reads at 300 m without glowing). No light box, no neon; storefront and window lighting untouched. Visible side effect:
a board hides procedurally lit windows on a wall that is windowless in reality (§1.4).

### 6.4 Motion, shimmer, mips, culling

Controlled camera-step sequences; each frame is masked by |ads on - ads hidden| from the same build
(`harness/motion.py`, `sheets/motion_*.png / .json`):

* **300 m lateral pass**, 1.5 m / frame (~5-6 px image motion): in-board luminance drifts +0.1...+0.35 / 255 per frame,
  monotonic (no flicker); in-board high-frequency energy rises monotonically 17.0 -> 18.3; text and frame stable.
* **150 m lateral pass**, 0.4 m / frame (sub-texel phase steps on the text): +0.25...+0.32 per frame, monotonic; dense
  strokes (觀) do not crawl; no moiré, no mip flashing, no atlas bleeding.
* **Cull**: a hard cut at 0.9 km removed a ~20 x 47 px board in one step on a 55° lens (3,400 px on a 30° lens); a cut
  at 1.6 km still popped a white board off a dark tower (~12 x 26 px). Any hard cut inside the district's view range
  pops, and a dithered fade needs a masked material. With 27 two-triangle instances the cull buys nothing measurable, so
  it is **3.3-3.5 km** (beyond the district) and the atlas mips carry the far read. Consequence: boards now also appear
  as a few pixels in the skyline / overview views (`a_skyline_nw`, `d_overview_sw`, `roof_ne1`: 0.03-0.08 % of pixels).
* Z-fighting: none at 150-1200 m (painted boards 4 cm, canvas 15 cm off the measured mesh wall).

## 7. Performance (Intel UHD 770 / i7-12700, same-session interleaved A/B)

As v0D / v0E / v0A: one UE session per run, states `base` (ads visible) and `noads` (HISM hidden in memory), every
state pre-warmed, 6 rounds alternating the order, 40 GPU-synchronised SceneCapture samples per state per round.
Cost = per-round (on median - off median); "range" = spread of the 6 paired deltas. Machine quiet (3 % load, no other
UE session; a foreign single-core job seen earlier had ended).

| class | view | off ms | **paired median** | mean | range | min-of-all delta |
|---|---|---|---|---|---|---|
| LOW | `fa_150_mix` | 73.5 | -0.07 | -0.10 | -0.33...+0.02 | -0.16 |
| LOW | `wa_150_legacy` | 59.6 | -0.21 | -0.14 | -0.45...+0.61 | -0.26 |
| LOW | `wa_150_keelung` | 56.1 | -0.34 | -0.37 | -0.60...-0.14 | -0.58 |
| MID | `wa_300_cluster` | 60.2 | +0.02 | +0.07 | -0.26...+0.66 | +0.02 |
| MID | `wa_300_tower` | 70.6 | -0.33 | -0.25 | -0.46...+0.06 | -0.07 |
| MID | `roof_ne1` | 74.4 | -0.17 | -0.16 | -0.70...+0.41 | -0.15 |
| HIGH | `wa_600_cluster` | 67.1 | +0.02 | -0.04 | -0.39...+0.17 | +0.09 |
| HIGH | `d_overview_sw` | 72.8 | +0.10 | -0.30 | -2.39...+0.25 | -0.23 |
| HIGH | `wa_1200_overview` | 74.6 | +0.12 | +0.21 | +0.04...+0.59 | -0.08 |

Class medians, `perf_day1` (0.9 km cull): **LOW -0.21, MID -0.17, HIGH +0.10 ms**. Confirmation `perf_day2` (reversed
state order, 3.5 km cull): LOW -0.25, MID -0.08, HIGH -0.09 ms. NIGHT `perf_night1`: LOW -0.06, MID +0.01, HIGH -0.05 ms.
All within the targets (LOW <= +0.5, MID <= +0.3, HIGH <= +0.2) and within measurement noise of zero (paired spread
typically +-0.3...0.6 ms; single-round outliers to 2-4 ms). Negative values are plausible: a board pixel runs a tiny
material instead of the facade shader it covers. Visible instances 1-5 per view; +1 instanced draw per depth / base
pass; no shadow-pass draws. A weak-GPU canary, not an iPhone measurement.

## 8. Determinism and regression

| check | result |
|---|---|
| atlas / audit / plan / plane GLB / report rebuilt twice, and once from an empty output folder | all six byte-identical (atlas `1fee3297...`, plan `7e1f08c4...`, audit `fae26a94...`) |
| placement order independence (shuffled input walls) | identical placements and cells (test) |
| ads hidden in memory vs HEAD (first candidate build) | DAY 18 / 25, DUSK 14 / 15, NIGHT 14 / 15 bit-identical; `a_skyline_nw` day = the known speckle signature (mean 0.797, as in v0A); the rest differ in <= 0.001 % of pixels or by an animated aviation light |
| `ACW_XINYI_WALL_ADS=off` stage build | `PASS_LOOK_ASSETS`, `PASS_LOOK_LEVEL`, 0 wall-ad instances |
| off build vs rebuilt on build (same generation) | identical outside board pixels (5 / 14 views bit-identical; the rest differ only where boards are) |
| off build vs HEAD frames | 7 / 14 bit-identical; 7 show a frame-wide speckle (mean <= 0.84 / 255 over ~95 % of the frame, not localized). The same speckle appears between the rebuilt on build and the earlier on build, so it is stage-rebuild variance of the existing look content, not the ad layer |
| building geometry, tiles, facade v0A shader, roof / storefront / street / ground builders | no tracked change; their offline outputs were not rebuilt |
| storefront v0E / schools / civic / Taipei 101 / roads / trees / scooters | unchanged in the captures (bit-identical with ads hidden: `cb_songqin_arcade`, `sf_cvs_wuxing`, `st_wuxing`, `g_101_closepass`, `h_sys_memorial`, `rp_low150`, `fr_corner_b`, `roof_ne2`) |
| DXC ps_6_0 | 10 / 10 Custom-node units compile (8 existing + 2 wall-ad); SPIR-V fails identically for every unit (this SDK's dxc has no SPIR-V backend, as at HEAD; CI uses a dxc with SPIR-V) |
| tests | `python -m unittest discover -s tests`: 118 OK, 9 skipped (104 existing + 14 new in `tests/test_wall_ads.py`) |
| UE stages | `PASS_LOOK_ASSETS`, `PASS_LOOK_LEVEL` (27 instances), fresh-reopen `PASS_LOOK_CAPTURE` |

## 9. Image 2.5 — worth a later pilot?

**A small one, yes; a large one, no.** Text must stay font-rendered (it reads at 150-300 m and Image 2.5 garbles
characters). The vector graphic occupies ~20-30 % of a board: 25-60 px at 150 m, < 15 px at 600 m. Where it would help:

* **pre-sale boards** (3-4 cells): a stylised rendering of a fictitious tower / courtyard instead of the flat skyline /
  house silhouette — the most recognisable feature of real Taiwanese 建案 banners, still readable at 150-300 m;
* **one or two ageing masks** for the ghost / painted cells (irregular flaking that the procedural blotch field makes
  too uniform).

Clinic portraits and decorative backgrounds would add little at aircraft range. The per-cell `art` regions make this a
drop-in swap. Expected value: modest, limited to the 150-300 m band.

## 10. Files

* `tools/lookdev/build_wall_ads.py` — Gate 0 audit (lot-line blank-wall rule, exclusions, exposure, occlusion, rooftop
  props, park / school, street exposure), deterministic placement, attachment QA against the tile mesh, plane mesh,
  `acw.wall_ads/0` plan and report.
* `tools/lookdev/build_wall_ad_atlas.py` — authored 34-cell atlas, ageing, content-policy and glyph checks.
* `tools/lookdev/shaders/xinyi_wall_ads.hlsl` — `wa_uv`, `wa_shade` (isolated from `xinyi_city.hlsl`).
* `tools/lookdev/ue_custom_code.py` — wall-ad Custom-node bodies (separate from `MATERIALS`).
* `tools/lookdev/check_hlsl.py` — also compiles the two wall-ad nodes.
* `tools/lookdev/build_all.py` — runs the two new builders after the storefronts.
* `adapters/unreal/lookdev/xinyi_look_build_assets.py` — atlas import, `M_XinyiWallAds`, plane import; `ACW_XINYI_WALL_ADS`.
* `adapters/unreal/lookdev/xinyi_look_build_level.py` — one `WallAds` HISM (no shadow, no collision, 3.3-3.5 km cull).
* `tests/test_wall_ads.py` — 14 tests.
* `docs/xinyi-wall-ads-v0-result.md` — this file.

Not in scope and not started: construction wraps / hoarding (separate grammar, with the construction kit), podium
banners, modern-building exceptions, window suppression on blank walls (M5), Image 2.5 assets.
