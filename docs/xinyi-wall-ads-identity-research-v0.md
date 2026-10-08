# Taipei wall ads / facade billboard identity — research + asset spec v0

Status: **research and spec only.** No shader, builder, asset or Unreal change. Branch
`feat/opus55-xinyi-visual-quality`, on top of `5d3c49d` (Facade Grammar v0A).

Inputs: `docs/taipei-urban-visual-language-research-v0.md` (§3.3, §7, §11, §12, §20), `docs/xinyi-taipei-street-reality-v0e.md`
(storefront layer), `docs/xinyi-facade-grammar-v0a.md` (generation classes, register-pressure lessons),
`docs/xinyi-facade-metadata-payload-v0.md`, the baked frontage roles, and the two Taipei regulations read in full this pass.
Helper evidence (kept out of production paths): `unreal/Saved/XinyiLook/evidence/wall_ads_research_v0/exposed_walls.py`
and its `exposed_walls.json` (ignored by git).

Evidence tags: **[O]** observed in a source I read this pass · **[R]** repeated across sources · **[K]** background
knowledge, not verified this pass · **[M]** measured on the project's own data this pass · **[I]** interpretation ·
**[P]** proposal · **[U]** unverified, check before building on it.

---

## A. Executive conclusion

**Worth adding, as a small, controlled layer. Conditional go, behind a short verification survey (§J).**

* **Why.** Large wall ads are one of the few Taipei / Taiwan mid-distance cues that is *large*, *flat-coloured* and
  *aligned to geometry we already have*. They live on exactly the walls that currently read as repeated windows or as
  plain boxes: tall stepped side walls above 4-5 F neighbours and the flanks of buildings on wide roads. At 150-600 m a
  10 m x 20 m coloured field is 60 x 120 px at 150 m and still 16 x 32 px at 600 m; a storefront board is below 30 px
  beyond 150 m.
* **How much of it exists here [M].** 14,397 wall edges >= 8 m. 4,118 are >= 10 m long, rise >= 9 m above the neighbour or
  ground, and belong to residential stock. A strict aerial-visible filter (not inside a < 8 m lane, >= 200 m2) leaves
  2,257. Placement priority classes (§D) select **~1,090 walls on 783 buildings** as the prime pool. There is plenty of
  room; the risk is clutter, not scarcity.
* **Priority.** After the construction kit (cranes, netted frames, hoarding: research §11 M3, whose site wraps are part of
  this layer) and alongside *blank stepped side walls* (M5: the ad is the content of that wall). It should rank **above**
  further tiny facade detail and above the old-stock ageing masks (v0A §6): those add 0.5-8 m irregularity that
  disappears past 300 m, while this adds identity at 150-600 m.
* **Evidence honesty.** The regulatory and content-constraint evidence is strong (primary texts). The *visual
  prevalence* evidence is weak: this pass could retrieve only a handful of public photo references (two project photos P2 /
  P7 from the earlier research, one press caption), not a survey. Density and category mix below are therefore
  **proposals with caps**, and the §J survey should settle the prevalence before any build is approved.

---

## B. Evidence summary

### B.1 Regulation (primary text, read in full) — Taipei-specific

| tag | fact | source |
|---|---|---|
| [O] | A **招牌廣告** is fixed to a building wall: TV wall, display, advertising board, **canvas on a support frame**, in front, side-hung or under-arcade forms. **張貼廣告** is hung, pasted, **painted** or sprayed directly on a wall with no frame | 廣告物管理自治條例 art. 2 (2016, 46 articles) |
| [O] | Owner: signs by 建管處; direct-applied ads by 環保局 below 3 m, 建管處 from 3 m up | art. 3 |
| [O] | Large signs: a front-mounted sign taller than 2 m is *large*: needs a 雜項 permit, a 5-year licence (re-apply), liability insurance, non-combustible frame; direct-applied ads: licence 2 years, consent of the owners' meeting | art. 18-24 |
| [O] | Ads must not block escape openings, daylight / ventilation openings or fire-escape devices (art. 7); no flashing neon in residential zones (art. 8); none in parks, green space, heritage sites or where they harm 市容 (art. 9); lights project <= 1.5 m (art. 11) | art. 7-11 |
| [O] | Ads must be kept tidy and intact; decayed, torn or dirty ones must be repaired or removed (art. 14) | art. 14 |
| [O] | The city may designate **street districts** with a mandated ad style and may subsidise renewal (art. 38-39) | art. 38-39 |
| [O] | **Construction sites**: ads on scaffold, net or safety fence are **canvas only**, must relate to the project unless >= 2/3 of the fence is planted; sample-house ads <= 6 m tall and set back >= their height; building owners / 起造人 apply | 臺北市建築工程樣品屋及臨時廣告管理辦法 art. 10 (2014, 12 articles) |
| [R] | Existing hoarding rules (>= 2.4 m closed metal, >= 1/2 planted on roads >= 10 m): project research G3 | `docs/taipei-urban-visual-language-research-v0.md` §7 |

Limits: these are the versions the Taipei legal database returned; later amendments were not checked [U]. Law explains
*what is plausible and permitted*, not how common anything is.

### B.2 Market and visual evidence

| tag | fact | source |
|---|---|---|
| [O] | First nine months of 2020: **96 new projects in Taipei, 83 pre-sale (86.5 %)**, a record. Pre-sale marketing is the dominant source of large temporary ads | CNA, 2020-10-08 |
| [O] | A 2010 AFP photo caption describes **large property-sale signs on the wall of a building near Taipei 101** | AFP / Getty via nbr.org (caption only; page blocked, not independently opened) [U] |
| [O] | A Taipei office listing advertises a dedicated **exterior ad wall facing a busy overpass** as a selling point | JLL listing, Dunnan |
| [R P7, P2] | Older mixed-use blocks show tall blank or sparsely windowed side walls, **some painted with large adverts** (CC0 Nangang view); height steps of a 15 F slab next to a 3-4 F walk-up are common | project research §3.3 |
| [O] | Wikimedia Commons holds outdoor insurance ads photographed on building sides (Jianguo N. Rd / Changchun Rd, Nanjing W. Rd) — titles only, not inspected | Commons "Taiwan Life" category |
| [R] | Hand-painted large boards have a long Taiwanese tradition (cinema boards painted in gridded sections by teams); the craft has largely moved to printed canvas | The News Lens features (via search results; the specific article was not verified) |
| [K] | In Taiwan generally, large printed canvas on side and front walls is a common, visually loud layer: pre-sale (預售 / 建案), clinic and dental, cram school, rentals, telecom and appliance, local services; faded or half-removed boards persist on old walls | not verified this pass |
| [K] | Election-season banners are among the largest building-wall banners in Taiwan | not verified this pass |

What I could **not** establish this pass: the share of exposed side walls that carry an ad, the category mix, the
painted : canvas ratio, and the Taipei-specific density difference. All are **[U]** and drive §J.

### B.3 Taipei-specific, Taiwan-generic or generic

| trait | class | note |
|---|---|---|
| frame-fixed canvas on a licensed support; formal permit, insurance, re-licensing | **Taipei** (regulation) | explains why ads are rectangular, framed and mostly intact |
| pre-sale real-estate banners and project wraps | **Taiwan-generic with strong Taipei weight** [I] | 86.5 % pre-sale share; highest land value |
| clinic / dental / cram-school / rental boards | **Taiwan-generic** [K] | |
| painted ghost ads on old walls | **Taiwan-generic** [R P7] | local fade level is [U] |
| telecom / appliance / 3C large boards | **generic urban** [K] | low identity value |
| LED video walls | **generic urban** | excluded from v0 |
| election banners | **Taiwan-generic** [K] | excluded (political) |

---

## C. Visual taxonomy

The distinction that matters: **A. storefront signs (v0E, done)** vs **B. large facade ads (this layer)**.

| | A. storefront signs (v0E) | B. large facade ads (this pass) |
|---|---|---|
| mounting | fascia board / vertical blade on the ground floor, 騎樓 | upper walls: framed canvas or painted wall, party walls, flanks |
| size | 3-6 m x 0.7-1.5 m (Taipei "small sign": front-mounted <= 2 m tall) | 6-14 m wide x 8-25 m tall, or 15-25 m x 4-8 m bands (large signs, > 2 m) |
| height band | bottom 1.7 floors (< ~6 m) | from ~6 m up to the parapet |
| regulator tier | small sign, 600 NTD, light | large sign: 雜項 permit, insurance, 5-year licence |
| data | storefront plan texture (units on commercial frontage) | per-wall plan from exposed-wall geometry (new) |
| readable range | <= 150 m (text), colour only beyond | 150-300 m headline; 300-800 m colour field |
| content | shop names, trades | projects, services, leasing |
| night | per-shop glow | few spotlit, most dark |

| family | what / where | class | priority |
|---|---|---|---|
| **W1 pre-sale / project banner** | large canvas on a tall wall near a site or on a visible flank; project name, a house or skyline silhouette, "預售 / 接待中心" | Taipei-weighted | **P1** |
| **W2 clinic / dental / aesthetic** | large board on the upper wall of mixed-use mid-rise above the shop band; trade word, tooth / cross | Taiwan-generic | **P1** |
| **W3 cram school / education** | tall board on mid-rise flanks; subject words, scores-style graphic | Taiwan-generic | **P1** |
| **W4 leasing / for sale** | 招租 / 出租 / 出售 in red-yellow-white on blank walls, a lower-grade board | Taiwan-generic | **P1** (cheap, high yield) |
| **W5 faded / ghost / blank board** | old painted rectangle, bare frame, half-peeled canvas | Taiwan-generic | **P1** (identity of age) |
| **W6 telecom / 3C / appliance** | broad generic category words, no logos | generic | P2 |
| **W7 local retail / services** | moving, cleaning, driving school style boards | Taiwan-generic | P2 |
| **W8 construction wraps** | canvas on scaffold / net / hoarding; project-related only | Taipei (regulation) | **P1 with the construction kit** |
| **W9 podium / department-store banner** | brand-free promotional banner on a commercial podium, core only | generic | P3 (optional, cap very low) |
| lifestyle / fashion | | generic | P3 |
| **excluded** | real brands / logos, political and election content, LED video walls, alcohol / tobacco / gambling, religious solicitation | | never |

---

## D. Placement rules

### D.1 Wall candidate geometry [M]

An edge qualifies if: ring edge >= 10 m; blank height above the neighbour (attached, taller than neighbour) or above ground
(open) >= 9 m; clear outward view >= 8 m (not inside a lane); residential archetype. Counts on the 25 look tiles:

| class | rule | walls | notes |
|---|---|---|---|
| A. stepped party wall | attached to a lower neighbour, old stock, >= 150 m2 | **231** | median 274 m2; huaxia 103, res_tower 83, walk-up 45 |
| B. road flank | frontage role street_major / commercial / commercial_major, exposed >= 12 m, old stock, outside the planned core | **623** | commercial 350, commercial_major 155, street_major 118 |
| C. open flank | open to >= 20 m, exposed >= 15 m, no road frontage | **249** | seen from far, no street |
| union | | **1,090 walls, 783 buildings** | prime pool |

Excluded by construction: 261 school, 254 office, 103 podium and 64 civic walls >= 9 m; 592 modern / premium residential walls.

### D.2 Eligibility (all must hold)

1. Archetype low / walk-up / huaxia / res_tower; **generation = legacy or huaxia** (v0A payload). Modern and premium: never.
   Unknown generation: only role >= commercial with a profile weight <= 0.25. Offices, podiums, civic, schools,
   landmarks, hero buildings, rooftop-structure records: never (W9 podium is a separate opt-in).
2. Wall: length >= 10 m; blank band from `y0 = max(6 m, 2 floors)` (above the storefront / arcade band) to
   `y1 = H - 1.0 m`; band height >= 9 m.
3. Exposure: attached-higher (A), road-facing (B) or open >= 20 m (C). Inside a < 8 m lane: no.
4. Not inward-facing to a park, plaza or school yard within 25 m (factor 0.2), not within 15 m of a campus polygon.
5. Never over a wall flagged as a school corridor side, a heritage or landmark building, or a hero tag.

### D.3 Scoring and selection (deterministic)

```
score = 1.0
      * exposure   (A: 1.0, B: 0.8, C: 0.6)
      * road_gain  (street_major / commercial_major: 1.0, commercial: 0.85, street: 0.5, none: 0.4)
      * corner_gain(1.25 if wall within 12 m of a frontage corner)
      * area_gain  (clamp(area / 300 m2, 0.5, 1.4))
      * age_gain   (legacy 1.0, huaxia 0.8)
      * district   (CityProfile: old fabric 1.0, mixed 0.6, planned core 0.15)
      * hash(wall id)   in [0.7, 1.3]
```

Pick walls in descending score; accept while the density caps hold. All draws are `sha256(wall id, salt)`; no building ids or
manual exceptions.

### D.4 Density caps and spacing

| scope | cap [P] |
|---|---|
| fraction of the prime pool | **8-12 %** (~90-130 walls over Xinyi), a profile parameter `ad_rate` |
| per building | 1 ad; at most 1 per face |
| spacing | >= 25 m along a street frontage between two ads; >= 40 m between two ads of the same category |
| per 500 m tile | <= 14 ads, <= 5 in the planned core |
| per camera view (150-600 m oblique, ~1 km2) | target 8-15 visible; reject a build if > 20 |
| category mix on the pool | W1 30 %, W2 15 %, W3 12 %, W4 15 %, W5 20 %, W6 + W7 8 % |
| faded / ghost share | >= 20 % of all ads (§E) |

At ~110 ads over 5.5 km2 (~20 per km2) an aerial frame shows an ad every ~2-4 visible blocks: visible, not cluttered.

### D.5 Where it should be rare or absent

Quiet residential back lanes (role rear / alley: excluded by exposure rule 3); school and civic buildings; parkside inward
faces; luxury towers and every modern / premium facade; the planned core (weight 0.15: at most a few podium or hoarding
wraps); any wall already carrying a v0E commercial arcade band beneath it only counts the band above 6 m.

### D.6 Data dependencies

Wall edges and heights: the existing footprints and look sidecar; frontage roles: the baked table; generation: v0A payload;
campus / park masks: urban-identity and ground data. **No new vertex channel and no change to the facade material.**

---

## E. Style direction

* **Not photo-real pasted JPEGs.** They would be the most photographic thing in a stylised world, break the
  colour discipline (trees, roads, roofs) and carry brand and legal risk. They also cost texture memory.
* **Match the existing flat, value-driven game look**: 2-3 flat colours per board, one dominant colour field, one
  headline of 2-4 large Traditional Chinese characters, one simple vector graphic (house silhouette, tooth, book stack,
  key). No gradients except a subtle top-to-bottom sun fade. No fine print (invisible beyond 150 m).
* **Colour.** Boards should be a little louder than walls, quieter than v0E signs: saturation capped at ~0.65, a
  limited palette per category (real estate: warm cream / deep green / navy / gold; clinic: white-teal-blue; cram school:
  yellow-red-white; leasing: red-yellow-white; ghosts: cream and faded one-colour remnants). Value contrast against the
  host wall >= 0.25 so the board survives the range-tone pass.
* **Weathering.** 20-30 % of boards aged: sun-faded value, a streaked bottom edge, one corner sag, a missing strip; ghost
  boards are cream rectangles with a faded one-colour remnant. Most others are clean (law art. 14: permitted boards are
  maintained).
* **Pop.** A board is a 6-14 m colour block with a 0.25 m frame line. At 600 m it must read as "a coloured rectangle on
  that wall", not as text.
* **Anti-clutter.** Opaque only; no LED screens, no animation, no neon, no glow beyond ~25 % faintly spot-lit boards at
  night; no more than one dominant board per building face; the caps in §D.4; and no boards on modern / premium facades.

### E.1 What is readable, by range (1080p, 60° vFOV, 935 px per m at 1 m / d)

| distance | px / m | a 10 m wide board | a 3 m headline character | verdict |
|---|---|---|---|---|
| 150 m | 6.2 | 62 px | 19 px | headline readable; frame and graphic legible |
| 300 m | 3.1 | 31 px | 9 px | headline marginal; graphic and colour read |
| 600 m | 1.6 | 16 px | 5 px | colour field + one shape only |
| 800 m | 1.2 | 12 px | 3.6 px | a coloured patch; mip average must still look right |

Consequence: design for hierarchy, drop everything under ~0.8 m, and let atlas mips carry the far read.

---

## F. Asset strategy (recommendation)

**Recommendation: a mixed system — thin opaque ad *planes* (instanced) from an offline plan, sampling one small baked
atlas, in its own material. Not a shader branch in `M_XinyiCity`, and not per-building textures.**

| option | verdict | reason |
|---|---|---|
| shader branch in the facade material with a wall plan texture | **reject** | the facade material's cost is register pressure and global size (v0E +0.3-0.5 ms, v0A needed a restructure); wall ads would be a new always-compiled term in the busiest shader |
| fully procedural boards | reject as the main path | name / trade text and graphics need designed hierarchy; procedural gives noise |
| atlas cells on instanced planes | **adopt** | one material, one texture, few hundred instances, zero cost on the facade shader, correct framed silhouette |
| flush decals for painted ghost ads | adopt as the same planes at 3 cm offset | one code path; no decal system |
| construction wraps | **special case**, built with the construction kit | canvas panels on scaffold / net / hoarding follow site geometry, not building walls |
| Image 2.5 for the ad cells | **not needed for v0** | text must be real Traditional Chinese (Image 2.5 garbles characters and may reproduce logos); the boards are flat vector layouts: bake them with real fonts like the v0E shop atlas |

* **Plane placement:** per wall plan record `(edge, u0, u1, y0, y1, cell, variant, aged, lit)` offline; plane
  offset 0.10-0.25 m (canvas on frame) or 0.03 m (painted); width <= 0.85 x wall length, <= 14 m; aspect chosen from the
  blank band (tall when the band >= 2.2 x width; band 4:1 near the parapet).
* **One material** `M_XinyiWallAds`: atlas sample (cell rect from per-instance custom data), sun-fade and age ALU, a
  night emissive mask for the lit subset. Opaque, no shadows cast, no translucency.
* **Atlas:** one 2048x2048 sRGB + emissive-mask-in-alpha, power-of-two cells, 10 % margin (v0E convention); BC7 ~5.3 MB
  on PC, ASTC 6x6 ~2 MB on mobile (or a 1024² LOW variant).

---

## G. First asset / spec batch

About **40 cells in one 2048² atlas**, all baked with real fonts from an invented name pool:

| group | cells | bins | role | priority | style | Image 2.5? |
|---|---|---|---|---|---|---|
| W1 pre-sale / project banners | 8 | 4 tall 1:2, 2 giant 1:3, 2 wide 2:1 | the dominant category | P1 | flat colour field + big name + house / skyline silhouette | no |
| W2 clinic / dental / aesthetic | 4 | 2 tall, 1 square, 1 band | trade identity | P1 | white-teal-blue, tooth / cross glyph | no |
| W3 cram school / education | 4 | 2 tall, 1 square, 1 wide | | P1 | yellow-red-white, book / pencil glyph | no |
| W4 leasing / for sale | 3 | 1 tall, 1 wide, 1 band | cheap, high yield | P1 | red-yellow-white | no |
| W6 / W7 telecom, services | 3 | 3 mixed | variety | P2 | generic words, no logos | no |
| W5 ghost / faded / blank | 6 | 2 tall, 2 square, 2 wide | age and irregularity | P1 | cream rectangle, faded one-colour remnant, bare frame, peeled bottom, torn corner | **optional**: 2-3 mask-like blotch shapes (greyscale) if procedural ghosts look flat |
| W8 construction wraps | 8 | 2 scaffold canvas 1:4, 2 hoarding band 6:1, 2 project teaser, 1 planted-wall panel, 1 safety-net tile | construction kit | P1 (with kit) | project name, tower silhouette; planted panel and net are non-text | **optional** for the planted-wall panel (neutral green, no text) |
| W9 podium banner | 2 | 2 wide | core only | P3 | brand-free promotion | no |

Cells count ~38-40. Text rules: Traditional Chinese + digits only; a brand, chain, institution and political-word blacklist
check in the build (as v0B / v0E); invented project names verified against the blacklist; **no real phone numbers** (use
non-dialable strings); fonts Noto Sans TC / Noto Serif TC (OFL), SHA recorded.

**Production constraints (restated):** no real brands or logos; no political or campaign content; no copyrighted ad art or
photographs copied; all copy invented but plausibly Taiwanese; the style evokes Taiwan, it does not depend on a brand.

---

## H. Performance strategy

* **Views that need it:** 150-600 m oblique over old fabric and main-road corridors; not the first-person street and not
  the far city (> ~1 km).
* **Instances:** ~110 wall planes + ~35 sites x ~6 panels = **< 400 instances**, 2 triangles each. HISM per atlas bin
  or one HISM with custom data; opaque.
* **Cull / fade:** hard cull ~900 m; between 500 and 900 m the plane is just a flat cell-mean colour (atlas mips already do
  this, so no code); no per-instance LOD logic.
* **No per-building textures; one atlas; one material; no translucency; no shadow casting; no overdraw-heavy layering.**
  A plane covers < 1 % of a frame.
* **Facade shader untouched** — the v0A lesson (always-on terms in `M_XinyiCity` cost +1.5 ms) is the reason for the
  separate material.
* **Budget [P, to measure]:** <= +0.3 ms at MID, <= +0.2 ms at HIGH, <= +0.5 ms at LOW; reject above +0.5 ms. Use the
  interleaved same-session A/B harness, both orders, clean machine (CPU contention invalidated earlier runs).
* **Where to stop detail:** frame line, headline, one glyph, fade. No fine print, no mullions, no light fixtures, no animation.

---

## I. Recommended implementation order

1. Research / spec (this document).
2. **Verification survey (new, before approval)**: 12 windows, ~25 candidate walls each, by street-level and aerial
   imagery of old Taipei fabric; record "ad / painted ghost / blank / windowed", category, size. Settles ad rate, mix
   and painted share (§J).
3. Content plan: name pool, blacklist, palette per category, cell list (no generation yet).
4. **Offline placement prototype**: a script that turns the §D rules into a wall-ad plan, a debug map and counts; no UE.
5. Atlas bake with real fonts; offline checks (text, blacklist, determinism).
6. First visual test: instanced planes + `M_XinyiWallAds`, DAY and DUSK review at 150 / 300 / 600 / 800 m.
7. Construction wraps together with the construction kit (M3), not before.
8. Performance gate: A/B per class, then determinism and regression (storefront v0E, v0A, roofs, schools unchanged).

Better order than the brief's: **survey before atlas planning**, and **wraps after the plane system exists but inside the
construction kit**, because their geometry belongs to the site.

---

## J. Open questions

1. **Prevalence [U]:** what share of exposed walls actually carry an ad in Xinyi / old Taipei? The 8-12 % is a cap, not a measurement.
2. **Category mix [U]:** is pre-sale really the largest wall-ad category on existing walls (as opposed to site hoarding)?
3. **Painted vs canvas [U]:** share of direct-painted boards vs framed canvas, and how faded they usually are.
4. **Street districts [U]:** whether Xinyi's special district or art. 38 street-renewal areas restrict large wall ads on
   arterials; this would lower the road-flank (B) weight in the core.
5. **Amendments [U]:** whether the 2016 ordinance and 2014 temporary-ad rules have been amended.
6. **Existing windows:** today's shader paints windows on every wall; a plane hides them, which is fine at range, but
   M5 (window suppression on blank stepped walls) should ship alongside so unadvertised blank walls also read.
7. **Depth offset:** whether a 3 cm painted-ad offset is stable at 600-900 m with the current depth settings (test).
8. **Footprint gaps:** many footprints are separated by narrow gaps; "attached" counts are a conservative proxy for party walls
   (only 407 of 4,118 candidates attach), so open-flank and road-flank rules carry most of the load.
9. **Night:** the proportion of lit boards is a proposal (<= 25 %); verify against night imagery.
10. **Content safety:** a human check of every invented name against real project and company names before bake.

---

## Sources

* 臺北市廣告物管理自治條例 (2016): https://laws.gov.taipei/law/LawSearch/LawExport/FL079873?type=0
* 臺北市建築工程樣品屋及臨時廣告管理辦法 (2014): https://laws.gov.taipei/law/LawSearch/LawExport/FL073637?type=0
* CNA, Taipei new-project and pre-sale counts, 2020-10-08: https://www.cna.com.tw/news/afe/202010080099.aspx
* AFP 2010 photo caption (not opened): https://nbr.org/?p=111283
* JLL, Dunnan Taipei Office Tower listing: https://invest.jll.com/be/en/listings/office/dunnan-taipei-office-tower
* Commons "Taiwan Life" category (titles only): https://download.osmand.net/wiki/Category:Taiwan_Life
* The News Lens, hand-painted cinema boards (search result, article not verified): https://www.thenewslens.com/article/56166
* Project docs listed at the top; photo references P2 / P7 are those of `docs/taipei-urban-visual-language-research-v0.md`.

No image was downloaded or committed.
