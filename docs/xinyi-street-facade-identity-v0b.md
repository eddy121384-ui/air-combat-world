# Xinyi Street & Facade Identity v0B — Phase B: awnings + vertical Traditional-Chinese signs

Status: **engineering validated, visual iteration done, not committed** on `feat/opus55-xinyi-visual-quality`, built on
HEAD `f2096c0` (Phase A). Look-dev layer only: the 25 look tiles are bit-identical to Phase A (no wall, roof, school,
rooftop or Taipei 101 change); the new layer is three instanced components on one opaque material.

## 1. Contract: placement reads the baked frontage roles

`build_look_tiles.py` now also writes the role table it bakes into the tiles,
`urban_identity/frontage_roles.json.gz` (`acw.frontage_roles/0`: per ring edge `p0, p1, normal, role, road_id,
road_hw, road_width, curb_m`; schools excluded). The tiles themselves are unchanged (tile-set hash `734d0b82…`).
`build_street_identity.py` places props from that table only — frontage is never re-derived.

| role | vertical blades | small boxes | awnings |
|---|---|---|---|
| 7 commercial, major road | 1 per ~6.5 m (× archetype) | 1 per ~22 m | 52 % of shop units |
| 6 commercial, local road | 1 per ~10 m | 1 per ~26 m | 46 % of shop units |
| 5 corner side street | 1 per ~22 m | 1 per ~40 m | 25 % of shop units |
| 3 / 4 residential street | none | rare (old stock 10 %, towers 12 % ground level, offices 3 %, per edge) | none |
| 2 service way | none | sparse, **lanes only** (see §4) | none |
| 1 rear / side, 0 | none | none | none |

Archetype weights: walk-up / low 1.0, huaxia 0.7, podium 0.3 (signs only, no awnings), planned core × 0.45;
office only the rare box; civic, school (not in the table) and rooftop-structure records: nothing. Props stay ≥ 0.9 m
from wall ends, every footprint is tested against all building footprints (nothing pierces a neighbour or the
building's own wing: 394 blades, 259 boxes and 592 awnings were rejected that way), signs keep ≥ 1.4 m from each
other at overlapping heights, and each building avoids reusing an atlas cell. Deterministic: per-edge RNG seeded by
the sha256 of the edge id; two rebuilds give identical files.

## 2. Signage atlas (`tools/lookdev/build_sign_atlas.py`)

`T_XinyiSignAtlas`: 2048² RGBA, RGB = sRGB sign face, A = emissive mask; BC7 with box-filtered mips. The three bins
are power-of-two aligned, so a mip never mixes neighbouring cells (the shader also insets by half a texel of the
sampled mip):

| bin | cells | cell px | use |
|---|---|---|---|
| v4 | 32 | 128 × 512 (1:4) | narrow vertical blade, 3–4 stacked characters, optional colour band |
| v2 | 8 | 256 × 512 (1:2) | wide vertical light box: big name column + small side column |
| sq | 16 | 256 × 256 (1:1) | small projecting box: one big character (藥 / 醫 / 麵 / 髮 / 機 / P …) + small name |

Content: **original** generic names (two auspicious characters + trade word: 診所, 牙醫, 中醫, 內科, 藥局, 美語,
補習班, 房屋, 地產, 小吃, 麵館, 水餃, 熱炒, 美髮, 髮廊, 理髮, 電器, 通訊, 手機, 五金, 眼鏡, 文具, 布莊, 商行, 旅社,
事務所, 停車場); a blacklist rejects names that collide with known Taiwanese chains, banks and brands; no logos, no
political content. 12 restrained colour families (red / white / blue / green / yellow / navy / maroon / orange / teal
with contrasting text). Light mode per cell: 25 light boxes (whole panel lit), 20 lit-letter signs, 11 never lit.
Fonts: Noto Sans TC / Noto Serif TC variable (SIL OFL 1.1; file SHA-256 recorded in `sign_atlas.json`), 2×
supersampled, deterministic (atlas sha `4f982cef…`). Ageing and lit-or-not are per-instance shader parameters, not cells.

## 3. Geometry, material, LOD

| HISM | mesh | tris | instances | cull (start–end) | shadow |
|---|---|---|---|---|---|
| `Street_sign` | blade light box: panel + rim + 2 steel brackets, origin at the wall, panel 0.25–1.25 × width | 36 | 1,702 | 500–700 m | yes |
| `Street_box` | same mesh, square cells, 0.6–0.95 m | 36 | 817 | 220–320 m | no |
| `Street_awning` | 雨遮 canopy: thin sheet falling 0.36 / unit, 0.1 m drip lip, side cheeks, 2 diagonal struts | 14 | 2,407 | 280–400 m | yes |

Total 4,926 instances, 124 k triangles if everything were drawn; 3 new HISM components, 1 material
(`M_XinyiStreet`, opaque, two-sided, instanced), 1 texture (~5.3 MB BC7 with mips), 2 meshes. Per-instance custom
data 0 packs everything: signs `cell + 64 · lit + 128 · fade`, awnings `colour + 8 · fade + 32 · style`.

Blades are 0.5–1.4 m wide and 2–5.2 m tall (1:4 / 1:2 panels), start at 1.12–1.45 floor heights and stay ≥ 0.6 m
below the roof; text reads correctly from both faces. Awnings sit at the arcade top (≈ one floor, under the painted
sign band, ≥ 2.7 m), project 0.5–0.9 m, 2–5 m wide per shop unit with small gaps and ±0.15 m steps; colours faded
green / muted blue / off-white / grey / grey-blue, occasional restrained red, ochre, teal; corrugated sheet (70 %) or
polycarbonate / canvas (30 %); sun-bleaching and streaks by age.

Shading (`xc_street_uv`, `xc_street`, new functions in `xinyi_city.hlsl`): atlas face with per-instance age
(desaturation toward yellowed acrylic, value loss, rain streaks from the top), darker rim, painted-steel brackets /
struts; at night only lit instances glow, through the atlas mask (≈ 54 % of blades and 41 % of boxes are lit), plus a
faint warm drip-lip glow on ~60 % of awnings (shop light). Unlit boards stay dark.

## 4. Service-road handling

The role table marks OSM `service` frontage as role 2. Using only the tags already in the locked road cache:
**lane** = `service=alley`, or an untagged service way whose name contains 巷 / 弄 (Taipei shop lanes); everything
else (`driveway`, `parking_aisle`, `emergency_access`, unnamed untagged) is **access** and gets nothing. Lanes get
no blades and no awnings — only a sparse small box sign (1 per ~34 m at 50 %, old stock only). Result: 6,072 lane
edges → 242 small boxes; 599 access edges → 0 props. No new GIS, no tile change.

## 5. Validation

| gate (`evidence/street_v0b/harness/check_street.py`) | result |
|---|---|
| every prop on a role-table edge; blades / awnings only on roles 5-7; boxes also on 3/4 and lanes | PASS (0 violations) |
| no prop on rear walls, schools, civic, rooftop records, driveway / parking access | PASS |
| no prop footprint intersects any building footprint | PASS |
| look tiles bit-identical to Phase A | PASS |
| shader: every pre-existing function text-identical to HEAD; only `xc_street_uv`, `xc_street` added | PASS |
| rooftop instances, look sidecar content, campus membership; cloud / hero / rooftop / campus / ground / frontage sources | identical / unchanged |
| DXC ps_6_0 `-WX`: all 8 materials incl. `M_XinyiStreet` | ok |
| UE5.8 assets / level / capture stages | PASS |
| determinism (atlas, instances, meshes) | identical hashes across rebuilds |

### Visual result (real UE5.8 SceneCapture2D, DAY / DUSK / NIGHT, HEAD vs candidate)

Evidence: `unreal/Saved/XinyiLook/evidence/street_v0b/` (`frames/base_*`, `cand_*`; `sheets/fin_street_{day,dusk,night}`,
`fin_zoom_{day,night}`, `fin_regress_*`; iteration sheets `it1`-`it4`). New along-street LOW cameras:
`st_zhuangjing` (莊敬路), `st_wuxing` (吳興街), `st_yanji` (延吉街), eye ~20 m above the street.

| view | changed px (>8/255) DAY / DUSK / NIGHT | read |
|---|---|---|
| st_zhuangjing | 2.7 / 2.5 / 2.0 % | strongest: projecting boards overlap in depth along the street (祥美通訊, 光盛美語, 合安地產, 仁成通訊 …) |
| st_wuxing, fr_corner_b | 1.2-1.8 % | boards on primary and corner-side faces; canopies over shop units |
| st_yanji, fr_canyon_wuxing, fr_block_e420 | 0.2-0.7 % | sparser streets / higher eye: uneven, a few boards |
| fr_rear_a, fr_rear_b (rear walls) | **0.00 %** | rear walls stay quiet |
| roof_ne1 (MID) | 0.08 % | only blade colour specks |
| roof_mid, d_overview_sw, a_skyline_nw (HIGH), g_101_closepass, e_lowpass_xinyi_rd, f_rooftops_wuxing (school) | 0.00-0.01 % | unchanged |

Mean luminance over 15 shots: DAY 77.5 → 77.4, DUSK 38.3 → 38.2, NIGHT 15.4 → 15.3; no clipping (max 0.023 % > 250 at
DUSK). NIGHT: about half the boards glow through their lit panel / letters, the rest stay dark; no neon wash.

Iterations (critique → change): it1 blades read immediately, awnings looked like thick floating slabs (22 cm lip, no
support) and NIGHT was dark → it2 thin canopy, drip lip, steel struts, denser blades → it3 canopies moved to the
arcade top (they were hiding the lit painted shopfronts from above), runs with small gaps / height steps, less
grey bleaching, more lit boards → it4 shallower canopies, brighter lit faces, warm drip-lip glow at night.

### Instances and cost

| | total | visible in view frustum within cull (LOW / MID / HIGH) |
|---|---|---|
| blades | 1,702 | 166-355 / 148 / 0 |
| boxes | 817 | 33-50 / 2 / 0 |
| awnings | 2,407 | 185-256 / 9 / 0 |
| triangles | 124 k (all) | 10-18 k / 5.5 k / 0 (before occlusion) |

New: 3 HISM components, 1 material, 1 texture (~5.3 MB), 2 meshes; no new vertex data on the city.

Performance (SceneCapture2D 1080p, 40 captures per view): HEAD vs candidate, median of 3 sequential runs each:
mean 71.2 → 71.7 ms (+0.6 ms, +0.8 %); `fr_block_e420` +4.1 ms in that sequential comparison. Attribution in one
session, interleaved (layer on / shadows off / layer hidden, 2 runs each): the whole street layer costs
st_zhuangjing +0.02, fr_canyon_wuxing +0.32, fr_block_e420 +0.32, roof_ne1 +0.06 ms; shadow casting ≈ +0.1-0.6 ms;
`roof_mid` (0 street instances drawn) moved +0.58 ms = run-to-run noise. So the earlier +4.1 ms was session drift: the
layer costs ≤ ~0.3 ms at LOW and nothing measurable at MID / HIGH.

## 6. Known limits

* NIGHT street level: from a 20 m eye, canopies and unlit boards hide part of the painted shopfront glow; lit boards
  compensate but the lowest band is slightly darker than HEAD in places.
* Canopies read as canopies up close; from 50 m+ and looking along a street they mostly read as a horizontal line.
* Board text is crisp up to ~40 m and becomes colour panels beyond ~150 m by design (box mips).
* Density follows the baked roles; streets whose frontage is mostly huaxia / planned core stay sparse.
* No near-only 3D AC, utility clutter, banners or storefront atlas on the sign band yet (later passes).
