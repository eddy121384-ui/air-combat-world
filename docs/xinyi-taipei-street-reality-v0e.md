# Xinyi — Taipei Street Reality v0E: storefront identity

Status: **engineering validated, visual iteration done, not committed**. Branch: `feat/opus55-xinyi-visual-quality`,
built on `2cf7f8c` (v0D).

Look-dev layer only. Unchanged, byte for byte, from the accepted v0D build: look tiles and frontage roles; ground,
campus and road paint; trees; walkways; the curb table (scooter rows / bays); every street instance (vertical signs,
boxes, awnings, 4,513 scooters); the v0B vertical-sign atlas.

What changed:

1. the plain horizontal shop boards (v0C) became a **Traditional-Chinese storefront atlas** (original names only);
2. commercial ground floors follow an **offline storefront plan**: convenience-store anchors, breakfast / soy-milk
   shops, noodle / bento / local food, beverage, pharmacy / clinic, neighbourhood retail and ordinary shops;
3. **night street level**: per-category shop glow and lit light-box boards, with many shops dark.

All of it is in the existing facade shader's street-band branch: no new geometry, actors, materials or translucency.

## 1. Reference check (narrow)

| grammar | finding | grade |
|---|---|---|
| convenience-store density | 13,706 stores in Taiwan (Dec 2023), one per ~1,700 residents; Taipei's densest street ~1 per 100 m | [O] |
| convenience-store placement | corner sites favoured; 24 h | [O] |
| convenience-store storefront | wide white fascia band, one or two brand stripes, full-height glazing with shelves and posters visible, bright cool-white interior, automatic door | [O-gk] (audit §6) |
| breakfast / soy-milk shop | grew around the flat-top griddle (鐵板); open 騎樓 frontage, griddle / counter at the front, menu boards above, closes by early afternoon | [O] / [O-gk] |
| noodle / bento / local food | narrow board, warm light, stainless counter, tiled wall with menu tags | [O-gk] |
| pharmacy / clinic | cleaner white / green / blue boards (「健保特約」), enclosed glazing, cool light | [O-gk] |
| neighbourhood retail | rolling shutters, mixed boards, subdued light | [O-gk] |

Abstraction [P]: no brand reproduction. Convenience stores are a white board with ONE stripe from a generic palette
(teal / deep blue / warm red / green), an invented two-character name + 超商, and 24H. No chain colour combination,
logo, or name. Sources:
* https://www.taiwannews.com.tw/en/news/6196604 (density)
* https://news.tvbs.com.tw/english/2628840 (store count)
* https://www.funtime.com.tw/blog/?p=180204 (breakfast-shop history)

## 2. Storefront atlas (`tools/lookdev/build_shop_atlas.py`)

`street/shop_atlas.png`: 2048², sRGB + emissive mask in A, BC7 with box mips; 48 cells, power-of-two aligned.

| bin | cells | use |
|---|---|---|
| h4 512×128 (4:1) | 4 convenience, 2 breakfast, 2 breakfast menu strips, 6 food, 3 beverage, 5 pharmacy / clinic, 10 retail | one-line fascia: name + trade |
| h2 512×256 (2:1) | 4 breakfast, 2 food, 2 pharmacy / clinic, 8 retail | big trade word (早餐 / 豆漿 / 便當 / 牙醫 / 五金 / 洗衣 ...) + a small line |

* Content: the v0B name pool and brand / chain blacklist, plus a chain / political word gate in the check.
* Every cell keeps a 10 % pure-background margin on each side, so a board wider than its cell continues in the cell's
  own colour.
* Fonts: Noto Sans TC / Noto Serif TC (OFL), with SHA-256 recorded.

## 3. Storefront plan (`tools/lookdev/build_storefronts.py`)

Eligible frontage: role 5–7 edges of old-stock (low / walk-up / huaxia), non-rooftop buildings. These are the walls the
shader paints a 騎樓 arcade on. Never schools, civic buildings, offices or towers, rear walls or residential streets.
That is 39.0 km on 4,988 edges.

Edges are split into ~4.5 m shop units. Each unit takes a category from the sha256 of its id, with role weights.
Convenience stores are placed first:
* corner sites on role 7, then role 6, then role 5, then long role-7 frontages;
* 8–11 m at the corner end;
* at least 160 m apart.

The plan is rasterised as `street/storefront_plan_2048.png`: L8 over the ground extent (1.22 m / px), value
`category * 32 + lit * 16 + seed`, painted 0.15–3.0 m outward from each unit. In the UE material it is uncompressed G8,
with no mips, never streamed, and read with `Texture.Load`.

| category | units | length | lit at night |
|---|---|---|---|
| convenience store | **64** (one per ~610 m of commercial frontage; min spacing ≥ 160 m) | 0.58 km | 64 (24 h) |
| breakfast / soy milk | 927 | 4.1 km | 0 (closed after the morning) |
| food | 1,321 | 5.9 km | 954 |
| beverage | 317 | 1.4 km | 239 |
| pharmacy / clinic | 577 | 2.6 km | 339 |
| neighbourhood retail | 2,047 | 9.1 km | 1,026 |
| ordinary | 3,434 | 15.3 km | 1,392 |

Ordinary + retail shops are 63 % of units; special archetypes are 37 %.

## 4. Shader (`xc_wall` street band; `xc_city` frame)

* `xc_city` passes the wall frame used to locate a board in the world: d(u, h) / d(screen) and the horizontal
  direction of +u along the wall. Derivatives are taken outside every branch.
* Board grid: one board width per building (3.1–6.2 m), so atlas text never jumps at a bay line.
* Inside the existing `h < 1.72 floors` branch:
  * one `Texture.Load` of the plan at the board centre, 1.4 m out from the wall (old-stock commercial walls only);
  * one atlas `SampleGrad`, with explicit gradients, for the board, or for a breakfast shop's menu strip above the
    counter. Each board is fitted to its cell: letterboxed, continuing in the cell margin colour;
  * per-category storefront: an open-shop interior (goods on shelves, lit ceiling strip, dark floor, fading to its mean
    once sub-pixel) for ordinary / retail shops, and one branch per special category (only that category is evaluated):
    * convenience store: bright cool glazing, posters, mullions, kick plate, ~1 m fascia with wall above;
    * breakfast: warm interior, stainless counter with the griddle edge, atlas menu strip;
    * food: warm, stainless, tiled wall with red menu tags;
    * beverage: colourful menu band;
    * pharmacy / clinic: clean glazing with frosted film.
* Night (inside the v0D `Night > 0` branch):
  * convenience stores are the brightest ground-floor element;
  * food warm and moderate; clinics / pharmacies cool;
  * ordinary / retail lit per plan;
  * light-box boards lit where the atlas mask says so (~65 %);
  * breakfast shops shuttered and dark from dusk.
* By day, convenience-store and clinic interiors carry a small glow so they read as lit inside a shaded arcade.

## 5. Review cameras / visual result

New VERY LOW cameras (evidence `shots_extra.json`):
* `sf_cvs_corner_b`: convenience-store anchor on a role-7 frontage near `fr_corner_b`, eye ~7.5 m above ground across
  the road;
* `sf_cvs_wuxing`: pedestrian-height oblique view along a commercial street with a store between `st_zhuangjing` and
  `st_wuxing`.

Changed pixels (|Δ| > 8/255), DAY / DUSK / NIGHT, HEAD vs v0E:

| view | changed px | read |
|---|---|---|
| **sf_cvs_corner_b** | 18.8 / 19.7 / 18.5 % | **strongest before / after.** Before: big flat colour blocks over a brown arcade. After: a 仁昌超商 24H fascia over glazing with stocked shelves, then 洗衣 / 文具 boards and open shops; at night the store is the brightest ground-floor element, the 洗衣 light box glows, and others stay dark |
| sf_cvs_wuxing | 8.4 / 8.9 / 8.8 % | a convenience store glowing inside the shaded arcade, with Traditional-Chinese boards down both sides of the street |
| fr_corner_b | 6.2 / 6.4 / 5.6 % | LOW altitude: 洗衣 / 豆漿 / 文具 / 眼鏡 boards and shopfronts replace colour blocks; at night the breakfast shop is shuttered |
| cb_songqin_arcade | 3.3 / 3.3 / 3.2 % | 長光文具 board on the arcade corner |
| st_zhuangjing / st_wuxing / st_yanji / wk_keelung380 | 0.8–1.8 % | board text at street distance; shopfront rhythm |
| roof_ne1 / d_overview_sw (MID / HIGH) | 0.7–1.2 % | board / shopfront colour rhythm only, no readable text, no shimmer |
| a_skyline_nw, g_101, fr_rear_a, e_lowpass, f_rooftops | ≤ 0.18 % | unchanged in practice |

DAY / DUSK / NIGHT:
* **Day:** boards read as Taiwanese shop signage; convenience stores and clinics read as lit inside.
* **Dusk:** warm, with the store anchor and lit boards visible.
* **Night:** inhabited rather than neon. The convenience store is brightest, then light boxes and some warm shop
  interiors, and many shops are dark.

Measured mean luminance at night is slightly *lower* than v0C at street views (e.g. st_zhuangjing 14.8 → 14.3,
fr_corner_b 20.4 → 18.3). v0C lit 75 % of shopfronts as flat glowing colour blocks; v0E lights fewer surfaces and gives
them structure. MID / HIGH luminance is unchanged within 0.3.

Iterations:
* **it1:** the plan lookup worked first time. The convenience-store fascia filled the whole 2 m band (tiny text), the
  storefront read as a white wall, and at night the store blew out to a white rectangle.
* **it2:** a ~1 m fascia with wall above; a shared open-shop interior (goods, ceiling strip, floor); a daytime interior
  glow for stores and clinics; more shops lit by the plan.
* **it3 / it4:** lit shops brighter with structure; light-box boards lit ~65 % at 2× (night was too dark).
* **it5:** a far-path variant (MID / HIGH) was tested and rejected: it gave no gain, because the cost is not
  text / goods at distance. The special categories now evaluate only their own branch (−0.1…−0.3 ms).

## 6. Validation (`evidence/street_v0e/harness/check_v0e.py`): CHECK_V0E_PASS

| gate | result |
|---|---|
| v0D layers byte-identical: road paint, trees, walkways, curb table, ground + campus textures, street instances (signs, boxes, awnings, 4,513 scooters) | PASS |
| v0B atlas, look tiles, street identity, ground and curb builders untouched | PASS |
| plan units only on role 5–7 frontage of old-stock, non-rooftop buildings | PASS (8,687 units) |
| convenience stores ≥ 160 m apart | PASS (64, min 160.2 m) |
| plan texture valid; plan deterministic (rebuild → identical texture + table); atlas deterministic | PASS |
| atlas: original names only (no brand / chain / political word), Traditional Chinese + digits | PASS |
| shader: only `xc_wall` / `xc_city` changed; added only `xc_eq` / `xc_shop_cell` / `xc_shop_sample` | PASS |
| DXC ps_6_0 `-WX`, all 8 materials (this SDK has no SPIR-V backend) | ok |
| UE5.8 assets / level / capture (fresh reopen) | PASS_LOOK_ASSETS / PASS_LOOK_LEVEL / PASS_LOOK_CAPTURE |

## 7. Performance (SceneCapture2D 1080p; same session, 6 interleaved rounds, both orders)

Method: the v0D shader and the v0E shader are built as fresh materials together after the asset stage, so neither
carries stale state (v0D lesson), and swapped in-session. The stage-built v0E material reads the same as the fresh
v0E material.

| view | DAY Δ ms | NIGHT Δ ms |
|---|---|---|
| cb_songqin_arcade | +0.62 | +0.52 |
| st_zhuangjing | +0.34 | +0.37 |
| st_wuxing | +0.67 | +0.36 |
| wk_keelung380 | +0.40 | +0.56 |
| fr_corner_b | +0.62 | +0.45 |
| sf_cvs_corner_b (store-filled VERY LOW view) | +0.85 | +1.04 |
| roof_ne1 (MID) | +0.66 | +0.35 |
| d_overview_sw (HIGH) | +0.72 | +0.50 |

Attribution experiments:
* far path (no text / goods past 0.25 m / px): **no gain**;
* no texture fetches at all: −0.2…−0.4 ms at MID (kept: removing them would pop board colours);
* one-category branch: −0.1…−0.3 ms (adopted).

The remaining ~0.3–0.5 ms at MID / HIGH is shader size / register pressure of the facade material, not per-pixel
storefront work. The v0D facade pass had saved ~5–7 ms in the same views, so v0E spends roughly a tenth of it.

Texture memory: storefront atlas 2048² BC7 with mips ≈ 5.3 MB; plan 2048² G8 ≈ 4 MB. No new mesh, actor or material.

## 8. Weakest remaining areas

* Boards that straddle a building corner split their text across the two faces; this reads like a wrap-around board,
  but the text is cut.
* 48 cells over ~8,700 units: a name can repeat within a block. The fascia of a long convenience store repeats its name.
* Shop interiors are a generic goods pattern. They read as stocked shops from a street view, but tile-like up close.
* Total night luminance is slightly below v0C (see §5).
* Non-old-stock commercial frontage (towers, podiums, offices) gets no storefront grammar (no arcade layer there).

## 9. Next pass recommendation

**A. near-only AC / iron-window refinement.** The upper floors are now the least Taipei-specific part of a LOW view:
the ground floor carries the shop identity, and the upper facade still repeats the v0A cage / AC grammar. It is also
where most of the facade shader cost sits (wall ALU ≈ 10 ms of flat-wall removal, v0D §9). A near-only refinement
gated by footprint could raise identity and remove cost in the same pass. YouBike / utility boxes (B) add little from
the air and new instance layers.

