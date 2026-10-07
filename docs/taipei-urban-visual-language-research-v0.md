# Taipei urban visual language — research v0

Status: **research only; not approved**. No assets, runtime code, shaders, tiles or levels were changed, and nothing
was committed. Written on `feat/opus55-xinyi-visual-quality` at `5ef4b6c` (Taipei storefront identity, v0E).

Scope: what makes a **broad aerial view** of Taipei read as Taipei at roughly 100–800 m, and at multi-kilometre
range. Street-level identity (scooters, storefronts, walkways, kerbs) was covered in
`docs/xinyi-taipei-street-reality-audit.md` and is only referenced here.

> **Revision v0.1 — hardening / falsification pass (Part II, §16–§24).** Part I (§1–§15) was a
> hypothesis-generation pass. Part II tests its strongest claims against a 12-district orthophoto roof sample
> (348 valid points), the official building-age, permit and parcel layers, and the current build's own statistics.
> **Where Part I and Part II disagree, Part II wins.** Corrected Part I statements are marked *(revised v0.1 → §n)*;
> the original text is kept for traceability. The main changes:
> * roof colour shares changed: blue is far rarer, white/grey is as common as mint, and red/maroon is more common;
> * whole-roof sheet covers are common but district-dependent, not dominant everywhere;
> * the "1990s tower" family is really a 1980s–90s family;
> * building age **is** available from official data.

Evidence labels (used everywhere below):

| label | meaning |
|---|---|
| **[O]** | observed directly in a cited image or authoritative source (§2 source log) |
| **[R]** | repeated pattern: seen in ≥ 2 independent references, or measured over the project's own city-wide WFS data |
| **[I]** | interpretation / synthesis by this pass, not a fact |
| **[P]** | proposal for Skyfront, not approved |
| **UNVERIFIED** | plausible, but no adequate source in this pass |

Distance arithmetic follows the earlier audits: at 1080p with a 60° vertical FOV, one metre covers about **935 / d
pixels** at distance d m. That gives 9.4 px/m at 100 m, 2.3 at 400 m, 1.2 at 800 m and 0.31 at 3 km.

---

## 1. Executive visual thesis

**From the air, Taipei is a flat basin carpet of 4–12-storey concrete-and-tile blocks.** Three things make that
carpet recognisable:

1. a **mint / sage-green, white and faded-red sheet-metal roofscape** covering the walk-up layer *(revised v0.1 →
   §17: pale green-grey ≈ white / grey > maroon / oxidised red ≫ blue; covers on about two-thirds of low-rise roof
   area, from about one-third to about nine-tenths by district)*;
2. a **lighter, ordered rim of taller 1990s–2020s towers** along the arterials, with the Xinyi tower cluster and
   Taipei 101 as the single strong peak;
3. **steep, forested green mountains on every side**, under a usually **overcast, humid, slightly hazy** sky.

The carpet is not low-rise and not uniform. Six signals separate it from a generic East Asian city:

* **Mid-rise dominance.** About 61 % of the built footprint has a mean height of 12–30 m, and only ~24 % is under
  12 m [R, WFS §3.2]. Taipei is neither a low-rise sea with towers (old Tokyo / Kyoto) nor a tower forest
  (Hong Kong / Shenzhen) [I].
* **Superblock structure.** Arterial edges carry 10–20-storey slabs, and block interiors hold a fine-grained,
  alley-cut carpet of walk-ups whose roofs are almost entirely covered by 頂樓加蓋 sheet roofs [O, R]
  *(revised v0.1 → §17: "commonly", not "almost entirely")*.
* **Age.** 74 % of Taipei homes are more than 30 years old [O]. The dominant surface is a weathered, rain-streaked
  1970s–1990s tile-and-concrete stock. Clean glass is the exception, concentrated in a few districts [R].
* **Generation mixing.** A 2020s glass-balustrade tower sits next to a 1975 walk-up with a mint tin roof. Urban
  renewal (都更 / 危老) produces this mix one lot at a time [O, R].
* **Active construction.** Red tower cranes, green-netted frames and planted green site hoarding are a normal part
  of the view, because renewal runs at about 245 cases a year citywide [O].
* **A specific colour field.** Off-white / light grey / beige walls, brown and salmon tile accents, teal-tinted
  1990s glass, mint-green roofs and deep subtropical vegetation [R].

[I] **The current Skyfront Xinyi already gets the macro geography right**: real WFS massing, 101, the basin and the
mountain ring. **Its main errors are generational and roof-related:**

* it has no age dimension: every 6–12-storey building gets 1970s–80s grammar, and every 13–24-storey building gets
  the same stone tower;
* its sheet-roof palette and layout are wrong for the dominant walk-up roofscape: blue is over-weighted and green
  under-weighted, and roofs are covered by discrete room boxes rather than whole-roof gable covers;
* construction is completely absent.

*(revised v0.1 → §22. Verdicts:*
* *too blue: CONFIRMED;*
* *construction missing: CONFIRMED;*
* *age variation missing: CONFIRMED as a mechanism, but most 6–12 F buildings really are 1970s–80s;*
* *too uniform: LIKELY;*
* *"too many small rooms": REJECTED as stated. The issue is room form, not count, and coverage is lower than
  observed.)*

---

## 2. Research sources and evidence quality

### 2.1 Method

* **Images.** Public Wikimedia Commons photographs, all CC0 / CC BY / CC BY-SA, were **viewed in the in-app browser
  only**. Nothing was downloaded into the repo or copied into any asset. Each is used as evidence for a stated
  observation and listed below.
* **Authoritative text.** Taipei City regulations were read in full where a document could be parsed
  (construction-site rules). Government statistics come from news reports quoting them, marked as such.
* **Project data.** The city-wide Taipei WFS building-height layer that the project already uses
  (`data/lookdev_cache/far_city_generalized.npz`: 318,327 records generalised to 50 m cells) was measured for the
  height distribution by district (§3.2). This is the same source as the accepted Xinyi geometry.
* **Current Skyfront.** `tools/lookdev/build_look_tiles.py` (archetype rules), `build_rooftops.py` (sheet weights),
  `shaders/xinyi_city.hlsl` (palettes), the existing identity docs, and the evidence sheets under
  `unreal/Saved/XinyiLook/evidence/`.

### 2.2 Weaknesses (read before trusting any number)

* Photographs show **one moment, one camera and one exposure**. Colour claims are about recurring families and
  relative shares, never sampled RGB values.
* The roof-colour shares in §6 are **visual estimates from three photographs**, not pixel counts. A counted sample
  from an orthophoto is listed as further research (§15).
* Several government figures were taken from **search-result summaries of official PDFs that were not opened**.
  They are marked *(summary)* in the log. Treat them as order-of-magnitude only.
* WFS "towers" are **records ≥ 50 m**. The WFS splits one building into several height-zone records, so tower
  counts are record counts, not building counts.
* The pinned EPSG:4326 snapshot was **not used** for anything here.

### 2.3 Source log

Government, statistics and regulations

| # | source | type | used to establish |
|---|---|---|---|
| G1 | 自由時報 2026 (Q2 2026 housing-tax stock): https://ec.ltn.com.tw/article/paper/1770861 | news quoting official stats (opened) | ≈ 922 k homes; **74.47 % > 30 yr, 59.61 % > 40 yr, 23.39 % > 50 yr** |
| G2 | 臺北市主計處 weekly statistics (Q2 2019): https://www-ws.gov.taipei/001/Upload/367/relfile/46908/8099662/c1d4d4f3-de56-4da5-a0cb-b66e3ab6c555.pdf | official stats *(summary)* | 53.1 % of homes in buildings of 5 floors or fewer |
| G3 | 臺北市建築物施工中妨礙交通及公共安全改善方案: https://laws.gov.taipei/law/LawSearch/LawExport/FL004127?type=0 | regulation (full text read) | hoarding ≥ 2.4 m closed metal; ≥ ½ densely planted on roads ≥ 10 m; covered pedestrian corridor; scaffold net ≤ 15 mm mesh; canvas below the 4F slab; 2 m catch fans every 5 floors; warning lights every 2.25–6 m |
| G4 | UDN 2025, urban renewal + 危老 ≈ 245 cases/yr in Taipei: https://money.udn.com/money/amp/story/5621/9018030 | news *(summary)* | renewal throughput; recent 2-year filings 2.3× the previous 8 years |
| G5 | NLMA / NCCU material on 危老 approvals: https://irtest.lib.nccu.edu.tw/handle/140.119/150204 , https://www.nlma.gov.tw/uploads/files/b3aef29c636c1f4b7340bb92cee9eace.pdf | thesis / official *(summary)* | Taipei led Taiwan with 891 approved 危老 cases by Nov 2023 |
| G6 | 臺北市建管處: https://dbas.gov.taipei | official *(summary)* | Jan–Oct 2025: 5,361 illegal-structure reports, 3,874 demolitions; rooftop structures with ≥ 3 units prioritised |
| G7 | Taipei zoning rules (騎樓 on commercial lots facing roads ≥ 7 m; 3.64 m width): https://laws.gov.taipei/law/LawSearch/LawExport/FL003988?type=2 , https://laws.gov.taipei/law/Interpretation/Content/FE015926 | regulation *(summary)* | arcade / setback ground-floor grammar |
| G8 | CNA 2017-12-30 — 雨遮 / eaves not counted or priced from 2018: https://www.cna.com.tw/news/afe/201712300028.aspx | news *(summary)* | why post-2018 façades lost deep rain shelters |
| G9 | CWA climate monitor 2025: https://www.cwa.gov.tw/Data/climate/Watch/twn/twn-monitor_2025-0.pdf | official *(summary)* | Taipei 2025: 135 rain days, 1,662.9 h sunshine = +280 h over normal (normal ≈ 1,383 h ≈ 3.8 h/day) |
| G10 | Building-type definitions (公寓 / 華廈 / 大樓 as used in 實價登錄): https://www.housefeel.com.tw/article/華廈大樓搞不清楚，這些類型的房子該怎麼分！？/ | trade article *(summary)* | 公寓 = no elevator; 華廈 = elevator, ≤ 10 F; 大樓 = elevator, ≥ 11 F |

Architecture, history and urban-form literature

| # | source | type | used to establish |
|---|---|---|---|
| L1 | Smile Taiwan / Pro360 guides on 外牆磁磚 history: https://smiletaiwan.cw.com.tw/index.php/article/7524 , https://www.pro360.com.tw/guide/brickwork_tile_external_wall | popular history *(summary)* | 1960s mosaic tile; post-1980 roller kilns → larger tiles and 二丁掛; later stone / slate-look tiles |
| L2 | CNA 2018 / Huayu World on 鐵窗: https://www.cna.com.tw/culture/article/20180316w004 , https://www.huayuworld.org/Overseas/PrintReport?PID=2660 | culture journalism *(summary)* | from the late 1980s stainless-steel grids replaced black iron; new towers drop grilles |
| L3 | NCU, "Analyzing 3D urban development in Taipei City": https://scholars.ncu.edu.tw/zh/publications/analyzing-3d-urban-development-in-taipei-city/ | academic *(summary)* | built-up area 21.7 % (1980) → 41.3 % (2010); vertical growth after the 1990s |
| L4 | NTU thesis on 信義計畫區 urban-design control: https://tdr.lib.ntu.edu.tw/handle/123456789/36174 ; UDN on setback bonuses: https://udn.com/news/story/7266/9589208 | academic / news *(summary)* | Xinyi planned 1980 (郭茂林); bonus-driven setbacks and plazas; skybridge network |
| L5 | Taipei Times 2002, "Taipei's architecture": https://www.taipeitimes.com/News/feat/archives/2002/01/28/0000121792 ; Ketagalan Media 2016: https://ketagalanmedia.com/2016/02/13/5066/ | opinion / feature | widely perceived "tile, concrete, rooftop sheds, sign clutter"; 1970s mass reproduction with cheap materials. **Opinion, not evidence** |
| L6 | Bureau Spectacular, "Rooftops urbanism": https://bureau-spectacular.net/project/rooftops-urbanism/ ; Taipei Times 2011 on illegal architecture: https://www.taipeitimes.com/News/feat/archives/2011/04/13/2003500604 | architecture practice / feature | 頂樓加蓋 as a city-defining informal layer |
| L7 | Pro360, metal-roof colours: https://www.pro360.com.tw/guide/metal_roof_color ; roof waterproofing: https://www.pro360.com.tw/guide/roof_waterproof_methods | trade guides | green is a common default sheet colour; PU / waterproof paint and light reflective coats on flat roofs |
| L8 | 天下 / Money Weekly on 內湖 / 南港: https://www.cw.com.tw/article/5131970 , https://www.moneyweekly.com.tw/_Article?AID=200946 | business press *(summary)* | Neihu tech park ≈ 150 ha mature office / tech; Nangang ≈ 86 ha, industrial → new HQ / station / expo |

Photographs (Wikimedia Commons, viewed only; file pages at `https://commons.wikimedia.org/wiki/<File>`)

| # | file | licence | used to establish |
|---|---|---|---|
| P1 | `File:Aerial_view_of_West_Taipei_20230620.jpg` | CC BY-SA 4.0 | macro grain, tower scatter, red-brown tile field, mountains / river, CKS Hall |
| P2 | `File:Aerial_panorama_of_Taipei_City's_west.jpg` (2022) | CC BY 4.0 | West Taipei roofs: mint / grey / faded-red sheets, stainless tank clusters, roof greenery, black-stained concrete, extreme height mixing |
| P3 | `File:Taipei-rooftop-additions.jpg` (2018, Xinyi / Wuxing from height) | CC0 | walk-up roofs **fully covered** by low gable sheets; mint / sage green dominant, then white / grey, red, rare blue |
| P4 | `File:Taipei-apartments-with-rooftop-additions.jpg` | CC0 | walk-up façade: stacked enclosed balconies, ACs, brown tile, rooftop room with sloped sheet |
| P5 | `File:Utsikt_från_Taipei_101_Observatory_8_August_2023_01.jpg` | CC BY-SA 4.0 | multi-km carpet, overcast haze, taller arterial rims vs mint-roof interiors |
| P6 | `File:Mountain_view_of_Taipei_from_Elephant_Mountain.jpg` (2018) | CC BY-SA 4.0 | tower generations: 1990s brown-tile tower, sandstone postmodern crowns, contemporary curved-balcony tower, dark glass; overcast light; red crane near 101 |
| P7 | `File:Cityscape_of_Nangang_District,_Taipei_from_New_Silicon_Valley_Business_Building_20141210a.jpg` | CC0 | Nangang: walk-ups with mint / pale sheet roofs, painted-ad blank side walls, factory sheds, cleared redevelopment land, new towers, close hills |
| P8 | `File:Neihu_Skyline_from_Songshan_Airport.jpg` | licence not checked | Neihu: boxy 10–20 F grey-blue glass offices in superblocks, low airport-edge sheds, hills behind |
| P9 | `File:Apartment_buildings_in_Shilin,_Taipei_20220705.jpg` | CC BY-SA 2.0 | 1990s 大樓: small white / cream tile, **teal reflective glass**, projecting bays, arched crown, shop podium |
| P10 | `File:08_Apartment_Building_in_Taipei.jpg` (2026) | CC BY 4.0 | 1990s postmodern tiled tower with curved balcony bays |
| P11 | `File:Minglun_Social_Housing_front_view_20230304.jpg` | CC BY-SA 4.0 | 2020s social housing: colour-gradient tile, recessed balconies, curved massing |
| P12 | `File:Taipei_Twin_Towers_construction_progress_20250818.jpg` | licence not checked | steel high-rise: red frame, **green netting**, yellow edge protection, 3 red luffing cranes per tower, glass from the bottom up |
| P13 | `File:信義區大樓_-_panoramio_-_Tianmu_peter_(23).jpg` | licence not checked | Xinyi steel frame with yellow joint marks; red hammerhead and luffing cranes |
| P14 | `File:View_of_Taipei_101,_a_skyscraper_under_construction,_apartment_buildings,_and_a_temple_at_Wufenpu.jpg` (2021) | CC BY-SA 4.0 | bare RC tower frame with twin luffing cranes; temple roof language (red, swallowtail ridges, cut-porcelain dragons); grey walk-ups |
| P15 | `File:China_Life_Taipei_College_development_construction_site_20190901a.jpg` | CC BY-SA 4.0 | curtain-wall install with external construction-hoist column |

Previously cited (street audit §15, not re-checked here): pedestrian-lane, scooter, convenience-store and YouBike
sources.

---

## 3. Taipei macro urban language (0.5–5+ km)

### 3.1 Basin and mountains

* [O P1, P5, P6, P8] The city fills a flat basin floor that ends abruptly at steep, densely forested hills: Elephant
  Mountain and the Four Beasts behind Xinyi, Neihu's hills, Yangmingshan to the north, Guanyin to the west across
  the Tamsui. In almost every elevated view the **city's edge is a mountain, not a horizon**.
* [O P1, P2] Rivers (Tamsui, Keelung) appear as broad grey-green bands with green floodplain parks and levees. They
  are the only large non-built breaks besides parks and the airport.
* [R P1, P5, G9] Light is frequently **overcast or hazy**. Normal sunshine is about 3.8 h/day, and at multi-km
  range the city desaturates toward blue-grey. Clear blue-sky days exist but are not the default.
* [I] Macro reading is therefore driven by **value and texture contrast** (dark window voids, roof-colour mottling,
  vegetation), more than by hard sun-and-shadow.

### 3.2 Height distribution (measured)

City-wide Taipei WFS (`far_city_generalized`, 50 m cells, coverage-weighted cell-mean height; "towers" = height
records ≥ 50 m) [R]:

| area (lon/lat box) | coverage | mean h | p90 h | < 12 m | 12–30 m | 30–50 m | ≥ 50 m records / built km² |
|---|---|---|---|---|---|---|---|
| **all Taipei** | 0.35 | 19.1 | 25.8 | 24 % | **61 %** | 12 % | 94 |
| West: Wanhua / Datong | **0.47** | 18.7 | 27.7 | 23 % | 65 % | 10 % | 106 |
| Daan | 0.40 | 23.7 | 32.0 | 8 % | 68 % | 19 % | 197 |
| **Xinyi planned core** | 0.36 | **38.1** | **49.4** | 5 % | 46 % | **29 %** | **371** |
| Xinyi / Wuxing old fabric | 0.42 | 17.5 | 23.8 | 16 % | **76 %** | 7 % | 69 |
| Neihu tech park | 0.36 | 22.7 | 28.9 | 10 % | 68 % | 17 % | 101 |
| Nangang (rail / expo) | 0.33 | 23.3 | 31.5 | **28 %** | 49 % | 13 % | 154 |
| Songshan / Minsheng | 0.39 | 18.8 | 23.5 | 11 % | **79 %** | 9 % | 97 |
| Shilin / Tianmu | 0.39 | 17.0 | 23.8 | 27 % | 65 % | 7 % | 79 |

The boxes are approximate, not administrative boundaries. Supporting: 53.1 % of homes are in buildings of ≤ 5
floors (G2, summary).

[I] Readings:

* Taipei is a **mid-rise city**. A 4–10-storey carpet is the normal state almost everywhere.
* **Xinyi's planned core is the outlier**, not the template.
* **West Taipei is the densest grain** (highest coverage) without being taller.
* **Nangang is bimodal**: low industrial / rail land next to new towers.

### 3.3 Block structure and towers vs background

* [R P1, P3, P5] **Superblocks.** Arterials (often with tree medians) are lined by taller, more continuous 8–20-storey
  slabs. Inside the block sits a fine carpet of 4–5-storey walk-ups and 6–10-storey 華廈, cut by narrow lanes. From
  1–3 km the city reads as **ordered rims around textured interiors**.
* [R P1, P5, P6] Towers (≥ 50 m) are **scattered pins** across almost every district, typically 1990s–2020s
  residential towers, not only offices. The **only real cluster** is Xinyi.
* [O P2, P7] **Abrupt height steps.** A 15-storey slab directly beside a 3–4-storey walk-up is common. It exposes
  tall **side walls that are mostly blank or sparsely windowed**, sometimes painted with large adverts (P7).

### 3.4 Roofscape, old / new juxtaposition, construction

* [R P2, P3, P5, P7] Seen from above, the interiors are dominated by **sheet-metal 頂樓加蓋 roofs** in pale mint /
  sage green, white / light grey and faded red, with stainless water-tank clusters on taller flat roofs. Roof
  identity is covered in §6.
* [O G1; R P2, P6, P14] **Old / new juxtaposition is the norm, lot by lot**, because renewal is parcel-scale
  (危老 average case ≈ 620 m² per G5, summary). There is no clear "new district" except planned areas like Xinyi
  and Nangang's redevelopment sections.
* [O G4, P6, P12–P14] Construction cranes appear in typical elevated views (§7).

### 3.5 Irregularity vs order

* [I from P1, P3, P5] Plan order is high: grid streets, superblocks, real WFS footprints. Elevation order is low:
  heights step lot by lot, every roof is altered, and façades of different decades alternate.
* **The identity lives in the elevation and roof irregularity over a regular plan.** Skyfront gets the plan from
  real data for free.

---

## 4. Mid-scale architectural language (100–800 m)

What survives at aircraft range: pixel size from the header arithmetic; observations from §2 images.

| trait | 100 m (9 px/m) | 400 m (2.3 px/m) | 800 m (1.2 px/m) | evidence | note |
|---|---|---|---|---|---|
| floor banding (≈ 3 m) | ●●● | ●●● (7 px) | ●● (3.5 px) | [R P1, P4, P9] | strongest mid-range façade cue |
| bay rhythm / window voids | ●●● | ●● | ● | [R] | voids read darker than walls under overcast light |
| tile colour field (white / beige / grey / brown / salmon) | ●●● | ●●● | ●●● | [R P1, P6, P9] | the façade "material" at range is a colour field |
| enclosed balconies (陽台外推) protruding ±0.5 m in aluminium frames | ●●● | ●● (stacked columns) | ● | [O P4] | vertical stripe of lighter frames per bay |
| iron / stainless grilles | ●● | ● (adds grey "busyness") | — | [O P4; O L2] | individual bars are sub-pixel beyond ~60 m |
| AC condensers | ●● | ● (texture) | — | [O P4] | read only as stacks; individual units sub-pixel at 400 m |
| teal / green reflective glass on 1990s towers | ●●● | ●●● | ●● | [O P9] | distinctive Taiwan 1990s residential cue |
| glass balustrades, metal fins, planted balconies (2010s+) | ●●● | ●● | ● | [O P6] | contrast: clean, light, vertical |
| postmodern crowns (arches, pyramids, domes, frames) | ●●● | ●●● | ●● (silhouette) | [R P6, P9, P10] | very readable skyline cue on 1990s–2000s towers |
| blank / sparse side walls above lower neighbours | ●●● | ●●● | ●● | [R P2, P7] | large plain stained surfaces; sometimes painted ads |
| rooftop sheet roofs (whole-roof gable covers) | ●●● | ●●● | ●●● (colour) | [R P2, P3, P7] | §6 |
| stainless water-tank clusters | ●●● | ●● (≈ 5 px each) | ● | [O P2] | silver dots on flat roofs |
| podium / arcade (騎樓) ground floor | ●● | ● | — | [O G7, P9] | mostly hidden at oblique aerial angles |
| rain streaks, black mould on parapets / roofs | ●●● | ●● | ● (value darkening) | [O P2, P4] | the "age" cue that survives distance |
| cranes, netting, hoarding | ●●● | ●●● | ●●● (cranes) | [R P6, P12–P14] | §7 |
| roof greenery / overgrown roofs | ●● | ●● | ● | [O P2] | old roofs and a few designed rooftop gardens |

[I] **Detail that does not matter at aircraft range:** tile grout, tile size (45 mm vs 二丁掛), grille patterns,
individual AC units, sign lettering beyond ~150 m, balcony furniture, and window-frame profiles. These should be
carried by **mid-frequency colour / value patterns**, not by texture resolution.

---

## 5. Discovered building-family taxonomy

Derived from the evidence above. The constraint is "no more families than are visually useful". **Eight primary
families**, **two point-feature families** and **one cross-cutting state (construction)** are proposed.

### F1 — Low-rise mixed fabric (1–3 F)
* Era / context: pre-war shophouses (West Taipei: Dihua, Wanhua) and post-war 1–3-storey houses, sheds and
  workshops, hill-edge settlements, rail / industrial margins [O P7; R §3.2: 23–28 % of built area in the West,
  Nangang and Shilin, 5–10 % in Daan and Xinyi core].
* Massing: small, deep, narrow lots; continuous street walls in the West.
* Façade: plaster / old tile, heavy weathering; heritage baroque fronts only in specific West Taipei streets.
* Roof: sheet roofs (mint / red / grey), old clay tile rare, lean-tos; often fully covered.
* Ground: shopfront / workshop directly on the street or arcade.
* Palette: grey, faded plaster, rust and mint sheets.
* Difference from neighbours: lower, darker, more patched; reads as a "hole" in the carpet.

### F2 — Walk-up apartment 公寓 (4–5 F, no elevator)
* Era: 1960s–1980s mass housing [O L5; G10 definition]. Dominates block interiors.
* Massing: rows of narrow deep slabs sharing party walls; flat roof, almost always with an addition.
* Façade: mosaic / small tile (beige, grey, brown, salmon, some pistachio) or painted render. Stacked
  enclosed-balcony columns with aluminium windows; grilles (black iron older, stainless later); AC stacks; strong
  rain streaking [O P4; L1; L2].
* Roof: **whole-roof low-pitch gable sheet cover** (頂加), mostly mint / sage, white / grey or faded red; occasional
  2-level additions; plants [R P2, P3, P7].
* Ground: shopfront or arcade on streets, garage doors / gates on lanes.
* Palette: dirty beige / grey / brown walls under a mint-green roof.
* Difference: the roof colour field is the identifier; façades are shorter and dirtier than F3.

### F3 — Elevator mid-rise 華廈 (6–10 F)
* Era: late 1970s–2000s [G10; I].
* Massing: slab or L-block, sometimes podium + slab, usually along local streets and arterials.
* Façade: 45 mm square tile or 二丁掛 brick-proportion tile (brown, red-brown, cream, grey) [L1, P1]. Strip windows,
  balconies, some bay windows; grilles on lower floors.
* Roof: flat; stair / elevator bulkhead; **stainless tank cluster**; partial sheet additions (less than F2).
* Ground: arcade / shops on commercial streets; lobby on residential streets.
* Difference: taller, more regular than F2; brown / red-brown tile more common [I].

### F4 — 1990s–2000s tiled residential tower 大樓 (11–25 F)

*(revised v0.1 → §17.2 / §21: official age data puts most 13–24 F residential buildings in the Xinyi area in
the 1980s–1990s. F4 and F5 become era parameters of one residential grammar, not separate archetypes.)*
* Era: 1990s–2000s boom; the pins scattered over every district [R P1, P6, P9, P10].
* Massing: point tower or slab, frequently with **projecting bays, curved balconies and a decorative crown**
  (arches, pyramidal caps, domes, frames).
* Façade: small tile in white, cream, salmon, brown, sometimes two-tone banding. **Teal / green or bronze
  reflective glass**. Recessed or curved balcony parapets.
* Roof: machine room plus crown feature; water tanks hidden or exposed; no sheet additions [I].
* Ground: shop podium or gated lobby.
* Difference: the most "Taiwan 1990s" silhouette. It is neither the plain stone tower nor the glass office.

### F5 — Contemporary residential tower (2010s–, incl. premium / luxury)
* Era: renewal and new-land projects, densest in Xinyi, Daan, Nangang and Neihu edges [O P6; L4; G8].
* Massing: slender or slab towers 15–40 F, often with a stone podium and large setbacks / plazas (bonus-driven, L4).
* Façade: stone or metal-panel frame, **glass balustrades**, vertical fins / louvres, deep balconies with planting,
  neutral palette (white, warm grey, charcoal, champagne metal). Post-2018 projects have no deep rain shelters
  (G8: eaves no longer priced) [I].
* Roof: **architectural crown frame / lattice / sky garden**, BMU crane, no informal additions.
* Ground: landscaped setback, lobby, sometimes retail.
* Variants: **luxury** (larger balconies, double-height sky gardens, twisting / stepped forms, e.g. 陶朱隱園) and
  **social housing** (colour-gradient tile, recessed balconies, curved massing; P11).
* Difference: clean, light, vertical; the "new Taipei" counterpoint to F2–F4.

### F6 — Office / commercial glass (incl. department-store podiums)
* Context: Xinyi core, Neihu tech park, Nangang, Dunhua / Nanjing E. corridors [O P8; L8; R §3.2].
* Massing: Xinyi: towers 100–300 m + large podium boxes. Neihu: **boxy 10–20 F grey-blue glass blocks** in
  superblocks. Nangang: new HQ towers + exhibition / station megastructures.
* Façade: curtain wall (blue-grey, green-grey, silver, dark), spandrel bands; department stores as large opaque
  boxes with signage.
* Roof: plant rooms, cooling towers, helipad marks on tall towers, BMU.
* Ground: plazas, skybridges (Xinyi, L4).
* Difference: the only family with continuous glass. It must look **clean and maintained**.

### F7 — Civic / educational / institutional
* Context: campuses (4–5 F classroom wings with open corridors), civic halls, hospitals, MRT depots.
* Façade: pale tile / render, regular long window strips; civic stone. Already modelled for schools (v0A).
* Roof: flat, PU waterproof (green / grey), solar, sports courts on roofs occasionally (UNVERIFIED frequency).
* Difference: long, low, regular, pale; set in open ground (yards, tracks, courts).

### F8 — Industrial / warehouse / infrastructure sheds
* Context: Nangang, Neihu margins, rail / airport edges, riverside depots [O P7, P8; R §3.2 Nangang 28 % < 12 m].
* Massing: large single-storey or low halls, long spans.
* Roof: large sheet roofs in blue, mint / green, grey, white, often rusted or patched.
* Difference: big flat colour slabs at range. **Irrelevant inside the Xinyi WFS area** [I]; relevant for wider Taipei.

### Point features (not families, but identity-critical)
* **T — Temples** [O P14]: red / orange curved roofs, swallowtail ridges, cut-porcelain (剪黏) dragons, often
  squeezed between walk-ups. A strong Taiwan cue at 100–400 m. Count and locations inside Xinyi: **UNVERIFIED**
  (needs an OSM `amenity=place_of_worship` + `religion=taoist|buddhist|chinese_folk` check).
* **L — Landmarks** (existing registry: 101, SYS Memorial Hall, Dome, City Hall).

### Cross-cutting state — **Construction / renewal** (§7)

### 5.1 Mapping to current Skyfront archetypes [I]

| current archetype (by floor count only) | real families it currently covers | problem |
|---|---|---|
| 0 low (≤ 3 F) | F1 (+ some F8) | fine for Xinyi; F8 needs its own roof treatment later |
| 1 walkup (4–5 F) | F2 | façade fine; **roof wrong** (§6, §10) |
| 2 huaxia (6–12 F) | F3 **and** new 2010s mid-rises and some F4 | new buildings get 1970s grammar (cages, mosaic, arcade) |
| 3 res_tower (13–24 F) | F4 **and** F5 | one plain stone / porcelain grid: neither 1990s-tile-and-teal-glass nor contemporary glass-and-fins |
| 4 office_glass | F6 | fine |
| 5 podium | F6 retail podium | fine |
| 6 civic, 7 school | F7 | fine (v0A) |
| — | F5 luxury / social-housing variants, T temples, construction | missing |

**The missing variable is building age / generation**, not height. Floor count alone cannot separate F3 from new
mid-rises, or F4 from F5.

---

## 6. Rooftop language

### 6.1 Observations

* [R P2, P3, P7] **Walk-up roofs (F2) are almost fully covered** by a single low-pitch gable or mono-pitch sheet
  roof spanning nearly the whole footprint, ridge along the building's long axis. From above, a row of walk-ups
  reads as a **row of coloured sheet rectangles**, not as concrete roofs with small rooms on them.
* [R P2, P3, P7; L7] Sheet colour shares (visual estimate across three photos, **UNVERIFIED by pixel count**) —
  **superseded by the 12-district orthophoto sample in §17** (blue ≈ 1–4 %, not 5–10 %; white/grey ≈ mint):

| colour family | estimated share of sheet roofs | notes |
|---|---|---|
| pale mint / sage / green-grey | **≈ 40–50 %** | the dominant walk-up roof colour in P3, also prominent in P2 and P7 |
| white / light grey / galvanised | ≈ 20–25 % | fresh or reflective-coated sheets; grey ageing |
| faded red / brick red / terracotta | ≈ 10–15 % | strong accents; reads orange-red in sun |
| light blue / blue-grey | ≈ 5–10 % | present but a minority |
| ochre / yellow / other | < 5 % | rare |

* [O P2] Older flat concrete roofs (F2 without additions, F3) are **dark-stained grey with black mould streaks**,
  often with **overgrown planters / weeds**, and with dense **stainless cylindrical tank clusters**.
* [O L7] Flat roofs that do get finished carry **PU / waterproof coats, commonly green or grey**, or light
  reflective (white) heat coats.
* [R P6, P9, P10] 1990s towers (F4) carry **decorative crowns**: pitched / pyramidal caps, arches, domes, often in
  the tile colour or with metal.
* [O P6] Contemporary towers (F5) have **clean flat roofs with architectural frames**, sky gardens and BMU cranes.
  No informal additions.
* [O P8] Offices (F6) carry **plant rooms / cooling towers**. Large podiums have flat equipment-dotted roofs.
* [O G6] Illegal rooftop structures are actively policed (5,361 reports in Jan–Oct 2025, summary). The informal layer
  is **under pressure but still dominant on F2**.

### 6.2 Roof language by family [I]

| family | coverage by additions | form | colour | equipment |
|---|---|---|---|---|
| F1 low | 60–100 % | lean-to, gable, patched | rust, mint, grey | few tanks |
| **F2 walk-up** | **80–100 % of footprint**, one cover | low gable / mono-pitch, sometimes 2-tier | **mint-dominant** (above) | tanks on bulkhead, solar heaters |
| F3 華廈 | 0–40 %, partial rooms | small gable rooms, sheds | mint / grey / white | **stainless tank clusters**, bulkhead |
| F4 1990s tower | ~0 | crown | tile colour / metal | machine room, tanks |
| F5 contemporary | 0 | frame / sky garden | neutral | BMU, plant |
| F6 office | 0 | plant enclosure | grey / dark | cooling towers, BMU, helipad |
| F7 civic / school | 0–10 % | flat | green / grey PU | solar |
| construction | — | open slab / climbing formwork | concrete grey, netting green | tower crane |

---

## 7. Construction language

### 7.1 Evidence

* **Volume.** Taipei leads Taiwan in renewal; urban renewal + 危老 ≈ 245 cases/yr average, with recent filings
  2.3× the earlier rate [O G4 summary]. 74 % of homes are > 30 years old [O G1], so the pipeline will persist [I].
* **Regulated site appearance** [O G3, full text read]:
  * closed **metal hoarding ≥ 2.4 m** (≥ 3 m beside the safety corridor); mesh hoarding within 10 m of corners;
  * hoarding must be decorated (paint / canvas / stickers / planting); on roads ≥ 10 m, parks or plazas
    **≥ ½ of the hoarding area densely planted** → **green planted hoarding walls**;
  * **covered pedestrian safety corridor** outside the hoarding where the site fronts a sidewalk;
  * scaffolding (buildings ≥ 5 F or close to the line) with **galvanised wire mesh or ≤ 15 mm nylon net**;
    **canvas** up to the 4th-floor slab; **sloped steel catch fans (斜籬) at the 2F slab and every 5 floors, ~2 m wide**;
  * warning lights every 2.25–6 m along the hoarding, at corners and gates (**a night cue**);
  * the 騎樓 must be opened within a month of the 2F slab pour.
* **Cranes and frames** [R P6, P12, P13, P14]: red hammerhead or luffing tower cranes (1–3 per high-rise); steel
  frames in red primer or grey with yellow joint marks; RC frames as grey slab stacks with dark open floors;
  **green safety netting** wrapping the working floors; glass installed **bottom-up**, so a finished lower band sits
  under a bare top; external hoist column on the façade (P15).

### 7.2 Construction states useful at aircraft range [I]

| state | duration share (UNVERIFIED) | visual cue at 100–800 m | at 1–3 km |
|---|---|---|---|
| S0 cleared / demolition lot | short | bare earth / gravel rectangle, hoarding line (green band), excavators | dirt-coloured hole in the carpet |
| S1 excavation / basement | months–1 yr | deep pit, struts, **1–2 tower cranes**, green hoarding | crane silhouettes |
| S2 rising RC frame | longest | grey floor stack, **dark open floors**, top floors **wrapped in green net**, catch fans every 5 F, crane(s) | crane + pale block |
| S2s rising steel frame (towers) | — | red / grey frame, green-netted working floors, yellow edges, 2–3 luffing cranes | strong red / green signal |
| S3 envelope / fit-out | months | scaffold + canvas / net over whole façade, or curtain wall rising from the bottom, hoist column, crane removed late | netted block |
| S4 completed, hoarding still up | short | finished building, ground hoarding remains | — |

[P] The aerial signature is **crane + netted slab stack + green hoarding rectangle**. All three are cheap and
readable from 3 km for the crane and from 1 km for the net colour.

---

## 8. District variation

Only differences supported by §3.2 data and §2 images are listed. Everything else is **UNVERIFIED**.

| profile | evidence | dominant families | distinctive cues | colour bias |
|---|---|---|---|---|
| **Xinyi core** | [R §3.2] tallest, 371 tower records / built km²; [L4] planned 1980, setback plazas, skybridges; [O P12, P13] steel construction | F6, F5 luxury, podiums | tower cluster, plazas, skybridges, cranes | glass blue-grey / silver, stone, clean |
| **Xinyi / Wuxing old fabric** | [R] 76 % in 12–30 m; [O P3] mint roof carpet | F2, F3, scattered F4 / F5 | full-roof sheet covers, alleys | mint roofs, beige / brown tile, weathered |
| **Daan** | [R] taller residential (19 % at 30–50 m, 197 tower records / km²), only 8 % < 12 m | F3, F4, F5 (premium) | boulevard rims (tree medians), more 1990s–2010s residential towers | brown tile + new neutral towers; leafy |
| **West (Wanhua / Datong)** | [R] densest grain (coverage 0.47); [O P2] very mixed heights, old stained roofs, roof greenery; temples (P14 is in Wanhua) | F1, F2, F3, T | heritage shophouses, temples, river edge | greyest, most weathered, red temple accents |
| **Neihu tech park** | [O P8; L8] ≈ 150 ha office / tech; [R] mid-rise 68 % | F6 (boxy mid-rise), F5 edges, F8 margins | superblock campus offices, wide roads, hills close | grey-blue glass, light grey |
| **Nangang** | [R] bimodal (28 % < 12 m + towers); [O P7] factories, cleared land, new towers | F8, F2, F5, F6, construction | redevelopment land, rail / expo megastructures | rusty sheds + new glass |
| **Songshan / Minsheng** | [R] most uniform mid-rise (79 % in 12–30 m) | F2, F3 | 1970s planned community grid (UNVERIFIED detail) | — |
| **Shilin / Tianmu** | [R] 27 % < 12 m; [O P9] 1990s tile towers | F1, F2, F4 | hill-edge low-rise, 1990s towers | — |

[I] **Conclusion: future City Profiles do need different archetype weights and palettes.** The strongest axes are:

1. tower share and generation mix (Xinyi / Daan vs the rest);
2. low-rise / industrial share (Nangang, West, Shilin);
3. weathering level (West highest, Xinyi core lowest);
4. glass type (Neihu boxy grey-blue vs Xinyi tower curtain walls).

A profile is a small data table (family weights, generation weights, roof-colour weights, weathering bias,
construction rate), not new art per district [P].

---

## 9. Colour / material language

Families and contrasts, not sampled pixels. Values in §12 are proposals.

| field | recurring colour families | role at range | evidence |
|---|---|---|---|
| **wall base** | off-white, light grey, beige / cream (concrete, white / grey tile, render) | majority tone of the carpet | [R P1, P2, P5, P9] |
| **wall accent** | brown, red-brown, salmon (二丁掛 / brick-tile), some two-tone banding; minor pistachio / old pastels | breaks the carpet into warm patches; 1980s–90s marker | [R P1, P4, P6, P9; L1] |
| **roof field** | **mint / sage green**, white / grey, faded red, minor blue | the identifier of the walk-up layer | [R §6] |
| **flat roofs** | dark-stained grey concrete, green / grey PU, silver tanks | darker mottling between sheets | [O P2; L7] |
| **glass** | 1990s residential: **teal / green, bronze**; offices: blue-grey / dark / silver; contemporary: neutral grey-clear | teal is a period cue | [O P8, P9, P6] |
| **construction** | red cranes, green net, yellow edges, grey frames, green hoarding | strong accents | [R P12–P14; G3] |
| **vegetation** | deep saturated subtropical greens; mountains near-black green at range | frames the city | [R P1, P6] |
| **point accents** | temple red / orange / gold; rare saturated façades (social housing gradients) | rare, small | [O P11, P14] |
| **atmosphere** | overcast, humid haze → blue-grey desaturation with distance | lowers contrast | [O G9; R P1, P5] |

Contrasts that make it Taipei [I]:

* **cool green roofs over warm-neutral walls**;
* **dirty old mid-rise vs clean light new towers**;
* **dense grey carpet vs dark green mountains**;
* **small red accents** (cranes, temples, faded red sheets) in an otherwise low-saturation field.

Weathering [R P2, P4]: dark vertical rain streaks below parapets and sills, black mould on parapets and roof edges,
and stained concrete roofs. Weathering is **value darkening with vertical structure**, not a brown "dirt" tint.

---

## 10. Comparison with current Skyfront Xinyi

Inputs: `evidence/rooftop_identity_v0/sheets/day_overview__before_after.png`, `day_roof_ne2__before_after.png`,
`day_elephant__before_after.png`, `street_v0e/sheets/final_v0e_day.png`; `build_look_tiles.py` L222–243
(archetype = floor count + core flag + area); `build_rooftops.py` `SHEET_W_OLD`; `xinyi_city.hlsl`
(`xc_tile_palette`, `xc_glass_palette`, `xc_sheet16`).

### 10.1 Already convincing
* **Macro geography** [R]: real WFS massing, basin floor, mountain ring, 101 + tower cluster, parks, the Dome and
  SYS Hall. The multi-km read is right in shape.
* **Superblock rims vs interiors** come out automatically from the real geometry [I].
* **Rooftop clutter vocabulary**: tanks, bulkheads, AC rows and solar heaters exist and are culled sensibly.
* **School campuses, street layer (v0A–v0E)**: storefronts, TC signage, scooter rows. Street identity is ahead of the
  roof and façade identity.
* **Weathering machinery** (sill streaks, parapet run-off, rear-wall grime) already exists in the shader.

### 10.2 Over-represented
* **Blue sheet roofs.** `SHEET_W_OLD` weights blues (indices 0–2) ≈ 27 %, reds ≈ 19 %, greens + teal ≈ 21 %.
  Evidence suggests mint / sage ≈ 40–50 % and blue ≈ 5–10 % (§6, estimate). The `roof_ne2` sheet reads red-and-blue
  where the real Wuxing fabric reads mint.
* **1970s–80s street grammar on 6–12-storey buildings**: iron cages, arcades, mosaic tile and AC scatter on all
  `huaxia`. This includes recent mid-rises that would have glass balustrades and no cages [I from §5.1].
* **Discrete rooftop rooms in a row** (55–95 % of the long axis) on walk-ups, where the real pattern is one
  near-full-footprint sheet cover. The result is a confetti of small colour squares instead of colour rectangles
  per building.

### 10.3 Missing
* **Building generation / age**: no F4 (1990s tile towers with teal glass and crowns) and no F5 (contemporary
  towers with glass balustrades, fins and planted balconies, luxury and social-housing variants).
* **Construction / renewal**: no cranes, frames, netting, hoarding or cleared lots.
* **Stepped blank side walls**: windows are painted on every wall; the shader has no adjacency-based window
  suppression (grep found none; rear / side walls only get lower clutter density).
* **Tower crowns**: 1990s skyline caps and contemporary roof frames.
* **Roof greenery** and dark-stained, mouldy flat roofs on old stock (partially present as ponding stains).
* **Temples** (UNVERIFIED presence in the WFS area) and **F8 industrial** (needed outside Xinyi).
* **Overcast / haze validation**: all accepted captures are clear-sky. The palette has not been judged under the
  city's typical diffuse light (lighting is out of scope; palette evaluation is not).

### 10.4 Generic East Asian rather than Taipei
* Facade clutter (cages, ACs, blade signs) is shared with Hong Kong and older Guangzhou (street audit §0). Taipei
  becomes specific through the **mint roof carpet**, **1990s teal-glass tile towers** and **green planted
  construction hoarding**, all currently absent or wrong.
* The **stone / porcelain `res_tower` grid** reads as a generic Asian new-town tower.

### 10.5 Too clean
* Mid-rise façades in the overview read as **uniform cream / light grey boxes**, with little warm brown-tile
  patching and little vertical streak darkening at range.
* Old flat roofs: not dark or mouldy enough.

### 10.6 Too old-fashioned
* Every 6–12 F building gets cages and mosaic, and every walk-up and 華廈 gets the same "1975" read. Real Taipei has
  a visible share of post-2000 buildings even in old fabric (renewal lot by lot).

### 10.7 Too uniform
* Façade colour is driven by archetype only, with no generation, district or profile axis.
* `bTone` / `hood` value variation is ±17 % with no hue families. The far city is one pale tone.

### 10.8 Wasted at aircraft distance
* Fine shop interiors, shelf stripes, mosaic grain and cage bars are correctly `xc_detail`-gated, so they cost
  little. But **authoring effort** went into street-level detail while the **400–3,000 m roof and generation
  read**, the dominant gameplay range, stayed generic.

---

## 11. Missing visual systems

| # | system | why (evidence) | aerial value | type |
|---|---|---|---|---|
| M1 | **Generation axis** in archetype assignment (F3 / F4 / F5 split; F5 variants) | §5.1, G1, P6, P9 | ●●● all ranges | data + material variation |
| M2 | **Walk-up roof covers** (whole-footprint gable / mono-pitch) + roof palette rebalance | §6 | ●●● 0.2–3 km | simple geometry + data |
| M3 | **Construction sites** (states S0–S3) | §7 | ●●● 0.1–3 km | instanced props + simple geometry + materials |
| M4 | **Tower crowns** (F4 caps, F5 frames) | P6, P9, P10 | ●● skyline | simple reusable geometry |
| M5 | **Blank stepped side walls** (window suppression where a wall faces a nearby lower or attached neighbour) | P2, P7 | ●● 0.1–1 km | data bake + shader |
| M6 | **Teal 1990s glass / F5 glass-balustrade bands** | P6, P9 | ●● | material variation |
| M7 | **Old-roof staining / greenery** | P2 | ● | shader + few instanced planters |
| M8 | **City Profile tables** (district weights) | §8 | enables scale-out | data |
| M9 | **Temples** | P14 | ●● locally | small geometry kit, data-driven |
| M10 | **F8 industrial sheds** | P7, P8 | outside Xinyi | data + roof material |

---

## 12. Candidate asset requirements

Per recommendation, the cheapest representation that keeps the aerial read [P]. Mobile is the baseline (§14).

| need | best form | why not something heavier |
|---|---|---|
| **Façade bay modules** per generation: F2 walk-up (enclosed-balcony / aluminium / grille bays in 3–4 tile colourways), F3 華廈 (二丁掛 + strip windows), F4 1990s (small tile, teal glass, projecting bays), F5 contemporary (glass balustrade, fins, planted balcony), F5 social-housing gradient | **Image 2.5 source art → one shared façade atlas** (bays as cells, neutral-lit, tintable), sampled by archetype / generation / variant in the existing `M_XinyiCity` | today's façades are pure ALU rectangles; mid-frequency module art is where "real building" vs "procedural box" shows at 100–400 m. One atlas keeps one material |
| **Blank side wall** surfaces (stained concrete, old tile, ghost-ad paint) | **procedural shader** (streak / mould masks already exist) + a few atlas cells for painted ads | low frequency; procedural is enough |
| **Rooftop sheet covers** (whole-footprint gable / mono-pitch, 2-tier variant) | **simple reusable geometry** (parametric box + gable cap, ≤ 20 tris, scaled per roof) + **data** palette | geometry gives the silhouette that defines the walk-up roof read |
| **Roof surface materials** (corrugated sheet, PU coat, stained concrete) | **procedural shader** (corrugation and patches exist) + optional small **Image 2.5 roof atlas** (neutral grey, tint by data) | only if procedural sheets look synthetic at 100–300 m |
| **Roof palette** (mint-dominant) | **data / material variation** (`SHEET_W_*`, `xc_sheet16`) | zero cost |
| **Glass** (teal / bronze 1990s, neutral contemporary, office blue-grey) | **data / material variation** in `xc_glass_palette` per generation | zero cost |
| **Tower crowns** (arch, pyramid, dome-cap, frame / lattice crown) | **simple reusable geometry**, 6–10 parametric meshes, instanced on F4 / F5 roofs | silhouettes need geometry; few instances |
| **Tower crane** (hammerhead, luffing) | **instanced prop** (≤ 60 tris, opaque, red / yellow / white), long cull | the single strongest construction cue |
| **Construction frame** (RC slab stack, steel frame, netted floors, catch fans) | **simple geometry generated per site** (floor slabs + columns as boxes) + **tileable net / canvas material** (Image 2.5 or procedural) | opaque net surface; no alpha cut-outs |
| **Site hoarding** (green planted wall, painted panel, warning lights) | **simple geometry strip** + atlas cells (planted wall, painted panel) + emissive dots at night | 2.4 m strip; reads as a coloured line |
| **Cleared lot / excavation** | **ground data** (ground texture class) + pit box | existing ground pipeline |
| **Rooftop greenery / planters** | **instanced prop** reuse (existing tree / clutter HISM) | small counts |
| **Temples** | **small geometry kit** (curved roof, ridge, porch) + one atlas row (red / gold / porcelain colourways), OSM-placed | only where data proves a temple |
| **Storefronts / signage** | existing atlases (v0B / v0E); TC text stays **real fonts, deterministic baking** | — |
| **Macro weathering** (rain streaks, parapet mould, roof stains) | **procedural shader** (existing terms, re-weighted by generation and profile) | — |
| **District variation** | **data**: City Profile JSON | — |

---

## 13. Image 2.5 opportunities

Image generation produces **source art**, not photogrammetry. It is worth using only where mid-frequency
"designed" detail is the gap: façade bays, construction textiles, hoarding panels and possibly roof surfaces.
It is **not** the answer for:

* roof palette, glass tint, district variation (data);
* silhouettes: crowns, cranes, roof covers (geometry);
* weathering (procedural);
* lettering (real fonts).

Generation rules (all sheets):

* orthographic elevation / plan, **no perspective**, flat neutral lighting, **no baked sun, shadow, reflection, DOF
  or noise**;
* game-art rendering consistent with Skyfront: clean mid-frequency shapes, restrained micro-detail;
* **neutral or tint-mask colour**: base in light neutral with separate masks, or generated per colourway, so data
  can tint;
* modules **tile horizontally per bay and vertically per floor** at a stated metric size (e.g. 1 cell = 1 bay ×
  1 floor ≈ 3.5 × 3.0 m);
* no text, logos or signs (signage stays in the deterministic TC atlas);
* every accepted sheet is reviewed at 100 / 400 / 800 m in-engine before more are made;
* generated output is checked against the §2 evidence; nothing is traced from a photograph.

---

## 14. Mobile-performance implications

Reference: the current building material is one opaque `M_XinyiCity` with **no textures** (ALU only), 25 tile draws
and HISM props (v1 doc). Any atlas is new cost and must earn it.

| proposal | mobile cost | mitigation |
|---|---|---|
| façade atlas | +1–2 texture samples per wall pixel, ~2–5 MB | **one** shared 2048² atlas (ASTC 6×6 ≈ 1.9 MB + mips; PC may use BC7 or 4096²); sample only where `xc_detail` says the bay resolves; aggressive mips; keep procedural fallback at range |
| generation axis, palettes, profiles | ≈ 0 (constants / branches per building) | coherent per-building branches (rooftop-pass lesson) |
| roof covers | +1.5–2 k instances in Xinyi, ≤ 20 tris each | one HISM, no shadows on small ones, cull ~3–4 km (they are the far roof read) |
| crowns | few hundred instances | one HISM, shadows on (silhouette), long cull |
| cranes | tens of instances | one HISM, ≤ 60 tris, long cull, no shadows or cheap ones |
| construction frames / net / hoarding | tens of sites | opaque only; no alpha nets; reuse the prop material with an atlas row |
| blank-wall bake | needs per-wall data | uses the free flag bits or the frontage-style sidecar; **UNVERIFIED** whether bits 4–6 can be shared with frontage (they are used) |
| temples | few | — |

Rules:

* no unique textures per building;
* no normal maps without measured aerial payoff;
* no translucency;
* PC gets resolution and optional normals, not different content.

Measure every step with the interleaved same-session harness.

---

## 15. Unknowns / weak evidence / further research

1. **Building age data (blocking for M1).** Does Taipei open data expose use-permit dates (使用執照) or completion
   years per building / address that can be joined to WFS footprints? Candidates: 臺北市使用執照 open data,
   實價登錄 建築完成年月 (by address), NLSC 3D building attributes. **UNVERIFIED** feasibility. Until then, a
   generation proxy must be a deterministic weighted assignment per City Profile, labelled as a proxy.
2. **Roof-colour shares**: pixel-count a NLSC orthophoto sample (licence check) over Wuxing, West Taipei and Songshan
   instead of three photographs.
3. **Construction density** in the Xinyi WFS area today: count active 建造執照 within the bbox (Taipei 建管 open
   data), or count cranes on a recent orthophoto. Rate per km² is **UNVERIFIED**.
4. **Netting colour mix**: green observed (P12); blue / black / white nets and the share of canvas vs mesh are
   **UNVERIFIED**.
5. **Share of post-2000 buildings** in the Wuxing old fabric and in the core: unknown without age data.
6. **Temples inside the WFS bbox**: run the OSM check.
7. **Blank side walls**: share of exposed side walls that are windowless vs windowed is **UNVERIFIED** (two images).
8. **Government statistics marked *(summary)*** (G2, G4–G9, L1–L4, L8) were not opened in full; re-verify before
   quoting outside this document.
9. **Night language** beyond the street (window-light colour share per generation, crown lighting) was not
   researched here.
10. **Mobile ASTC budget** for a façade atlas has not been measured on a device.

---

## Proposal (not approved)

*(Part I proposal, kept for traceability. **Superseded by §24.**)*

### Top visual gaps
1. **No building-generation axis.** 1990s tile / teal-glass towers and contemporary glass-balustrade towers are
   missing. 6–24 F buildings get one old or one generic look.
2. **Wrong walk-up roofscape.** Blue / red room confetti instead of mint-dominant whole-roof sheet covers.
3. **No construction / renewal.** No cranes, netted frames, green hoarding or cleared lots.
4. **No skyline crowns** on 1990s towers and no roof frames on new towers.
5. **Façades are too uniform and too clean at range.** Brown-tile patches and stepped blank side walls are missing.

### Proposed asset families
* A — **Generation façade atlas** (F2 / F3 / F4 / F5 bay modules, F5 luxury + social-housing variants), one shared
  atlas.
* B — **Roof covers + roof palette** (walk-up gable covers, 2-tier; mint-dominant data palette; stained flat
  roofs).
* C — **Construction kit** (2 tower cranes, frame generator, net / canvas material, planted / painted hoarding,
  cleared-lot ground class).
* D — **Crown kit** (6–10 parametric crowns / frames).
* E — **Profile data** (City Profile JSON: family / generation / roof / weathering / construction weights).
* F (later) — temples kit, industrial-shed roof class, side-wall bake.

### Tentative priority
| P | item | form |
|---|---|---|
| **P0** | B roof covers + mint palette rebalance | geometry + data |
| **P0** | generation axis (proxy weights until age data) + glass / tile palette per generation | data / material |
| **P0** | C construction kit: cranes + netted frame + green hoarding (data-placed, few sites) | instanced / simple geometry + 1 atlas row |
| **P1** | A façade atlas, starting with one family (F4 1990s tower) as a measured pilot | Image 2.5 → atlas |
| **P1** | D crowns | simple geometry |
| **P1** | blank stepped side walls (bake + shader) | data + shader |
| **P1** | E City Profiles (Xinyi core / old fabric first) | data |
| **P2** | rest of A (F2 / F3 / F5 modules), old-roof greenery and staining, temples, F8 sheds, roof material atlas | mixed |

### Tentative first Image 2.5 batch (for review, not to be generated yet)
1. **F4 1990s residential tower bay sheet**: 3 colourways (white-cream small tile, salmon / brown 二丁掛, two-tone),
   teal and bronze glass variants, projecting bay + balcony parapet modules. Orthographic, flat-lit, 1 bay × 1 floor
   cells.
2. **F5 contemporary tower bay sheet**: glass balustrade + slab edge, vertical fin / louvre, stone-frame bay,
   planted balcony; neutral palette.
3. **F2 walk-up bay sheet**: enclosed-balcony aluminium window bays (with / without stainless grille, with AC),
   beige / grey / brown tile fields, heavy-weathered variant.
4. **Construction textiles + hoarding sheet**: green safety net (tileable, opaque), site canvas, planted green
   hoarding panel, painted hoarding panel. No text.
5. (optional) **Roof surface sheet**: neutral corrugated sheet with patch strips, PU-coated slab, stained concrete
   with mould. Only if procedural roofs fail review at 100–300 m.

These recommendations are **not approved**. No asset was generated, no runtime file was edited, and nothing was
committed.

---
---

# Part II — Hardening / falsification pass (v0.1)

Same rules as Part I: research only, no assets, no runtime change, no commit. All downloads went to the session
scratchpad, not the repo.

## 16. Method of this pass

| test | data | size / coverage |
|---|---|---|
| roof cover + colour | NLSC national orthophoto WMTS `PHOTO2` (2024 mosaic, ~0.3 m/px at z19), masked by Taipei WFS `tp_building_height` footprints | **12 sample windows of 350 × 350 m in 11 districts**; 36 area-weighted random points per window on 1–5 F footprints; **432 points, 348 classifiable**; each point classified by eye on contact sheets |
| building age | Taipei City Dashboard WFS `building_age` (same server as the accepted footprints), joined to the 11,132 accepted Xinyi records / 4,137 look groups | 10,623 age points in the Xinyi bbox |
| permits | data.taipei use-permit summary XML (8,762 permits) and construction-permit summary XML (9,043 permits), both 2001–2025; WFS `building_cadastralmap` parcels; WFS `building_permit`, `building_license`, `building_renewunit_*` | Xinyi bbox: 12,493 parcels |
| current build | `unreal/Saved/XinyiLook/rooftops/rooftops.report.json`, `build_rooftops.py`, `build_look_tiles.py`, rooftop evidence sheets | — |

Orthophoto sample windows (centre lon / lat):

| window | centre |
|---|---|
| Xinyi–Wuxing | 121.565 / 25.028 |
| Daan | 121.540 / 25.030 |
| Wanhua | 121.500 / 25.036 |
| Datong | 121.512 / 25.058 |
| Songshan–Minsheng | 121.560 / 25.060 |
| Zhongshan | 121.528 / 25.052 |
| Shilin | 121.525 / 25.090 |
| Beitou–Shipai | 121.515 / 25.118 |
| old Neihu | 121.583 / 25.080 |
| old Nangang | 121.607 / 25.054 |
| Wenshan–Jingmei | 121.542 / 24.993 |
| Zhongzheng–Guting | 121.522 / 25.024 |

Sampling and classification:

* Points are **area-weighted over 1–5 F footprints**, so they estimate the share of low-rise roof *area*, not of
  buildings.
* Each point is classified as **C** sheet / pitched cover, **N** flat roof without cover (concrete with clutter,
  coated slab, solar, garden) or **O** unclassifiable (shadow, tree, relief displacement, missing tile).
* C points are further coloured as **G** pale green / green-grey, **W** white / light-grey / grey / galvanised,
  **R** maroon / oxidised red / orange / brick, **B** blue.

Known biases of this method (do not ignore):

* **One observer, by eye.** Pale green-grey vs neutral grey is the hardest boundary.
* **Mixed flight conditions.** The 2024 mosaic is warm and dark in Wanhua, Daan, Datong and Nangang, and pale and
  hazy in Wuxing and Songshan. An automatic pixel classifier failed exactly here: it labelled pale green sheets
  "white" because their saturation is below 0.13, so classification was done by eye.
* **Top-down view.** The orthophoto sees roof colour, not the walls of additions. Oblique photos (Part I P3) make
  the same roofs look greener and more saturated.
* **Relief displacement** shifts tall roofs. Only 1–5 F footprints were sampled, and points in shadow were
  rejected.
* **Sampling error.** About 30 valid points per window ⇒ ±15–18 % per window (95 %). City totals ⇒ about ±5–6 %.
* **Coverage gaps.** Not a random city-wide sample: the windows were chosen to contrast districts. The planned
  Xinyi core (towers) is deliberately excluded.

---

## 17. Roof claims — hardened or weakened

### 17.1 Results

| window | valid | **sheet / pitched cover** | G green-grey | W white / grey | R maroon / red / orange | B blue | note |
|---|---|---|---|---|---|---|---|
| Xinyi–Wuxing | 32 | **75 %** | 42 % | 46 % | 13 % | 0 | continuous per-lot covers along rows |
| Daan | 25 | **52 %** | 23 % | 46 % | 31 % | 0 | many flat cluttered roofs, coated slabs |
| Wanhua | 28 | **79 %** | 23 % | 36 % | **41 %** | 0 | 6 of 9 red are old pitched orange-red roofs |
| Datong | 24 | 67 % | 38 % | 19 % | 38 % | 6 % | dark imagery |
| Songshan–Minsheng | 34 | **44 %** | 40 % | 40 % | 20 % | 0 | 1970s planned community; mostly flat roofs |
| Zhongshan | 28 | 75 % | 24 % | 48 % | 24 % | 0 | + 1 ochre; one large solar array |
| Shilin | 32 | **91 %** | **52 %** | 41 % | 7 % | 0 | densest cover of all windows |
| Beitou–Shipai | 35 | 69 % | 42 % | 17 % | **42 %** | 0 | large red market / civic roofs with solar |
| old Neihu | 30 | **33 %** | 40 % | 30 % | 10 % | **20 %** | larger, newer buildings; flat roofs |
| old Nangang | 18 | 56 % | 30 % | 70 % | 0 | 0 | **low quality** (dark imagery, industrial) |
| Wenshan–Jingmei | 33 | 79 % | 46 % | 31 % | 23 % | 0 | |
| Zhongzheng–Guting | 29 | 62 % | 28 % | **56 %** | 17 % | 0 | |
| **all windows** | **348** | **66 %** (228) | **37 %** (84) | **39 %** (88) | **23 %** (52) | **1.3 %** (3) | + 1 ochre |

Colour percentages are shares of covered points. If the 5 ambiguous slate / grey-blue points are counted as blue,
blue rises to ≈ 3.5 %.

### 17.2 What survives, what changes

* **Sheet covers are common but district-dependent, not dominant everywhere** [R, n = 348]:
  * about 2/3 of low-rise roof area citywide;
  * from 33 % (old Neihu) and 44 % (Minsheng) to 91 % (Shilin);
  * the Xinyi–Wuxing fabric (75 %) is above the city average.

  **Two low-rise roof states are both major:** (1) sheet / pitched covers and (2) flat concrete roofs carrying
  bulkheads, stainless tanks, clutter and, more rarely, coatings, gardens or solar. The second state is close to a
  third of low-rise roof area. Part I under-weighted it.
* **Cover form** [O orthophoto mosaics, e.g. Wuxing; consistent with P3]: covers are typically
  **footprint-filling and per land lot**. A walk-up row that WFS models as one polygon shows a strip of separate
  covers, often in different colours, each 4–8 m wide. They are low-pitch with ribs running along the lot's long
  axis. Discrete rooms with visible gaps exist but are the minority form in the covered windows [I, by eye].
* **Colour.**
  * **Green-grey ≈ white / grey** (37 % vs 39 %), then **maroon / oxidised red** at 23 %, and **blue is rare**
    (≈ 1–4 %).
  * Part I's "40–50 % mint / sage" was too high, "10–15 % red" too low and "5–10 % blue" too high.
  * The honest statement: **pale green-grey is a recurring and visually important roof family, about as common as
    white / grey.** Neither dominates; red / maroon is a strong third, and blue is a trace except in a few areas
    (old Neihu 2 of 10 covered points; Datong 1).
  * The green is **pale, low-saturation green-grey** in top-down imagery, not a saturated "mint".
* **Strong district contrasts in red** [R, within the sampling error caveat]: Wanhua and Beitou ≈ 40 % red
  (old pitched orange-red roofs; large maroon roofs), against Shilin 7 %. This difference is a profile parameter,
  not noise (95 % intervals do not overlap: Shilin 0–16 %, Beitou 22–62 %).
* **Green waterproof (PU) coatings on flat roofs exist but are a minority** (≈ 4 of ~120 N points) [O]. Downgrade
  from Part I.
* **Rooftop solar arrays** appear on large flat roofs in 3 of 12 windows (Beitou, Zhongshan, Nangang) [O]. This is
  a new roof state Part I missed (mostly large / public roofs; frequency UNVERIFIED).

---

## 18. Building-age data — availability and join test

### 18.1 What exists

| source | access / licence | content | coverage | join |
|---|---|---|---|---|
| **WFS `taipei_vioc:building_age`** (citydashboard.taipei, same server as the accepted footprints) | public WFS, no key; licence terms **UNVERIFIED** (same status as `tp_building_height`) | **258,569 address points**: `constr_yr`, `numfloors`, `strtype`, `mbt` (structural class codes such as `C1M`, `C1H`, `RML`, `URML`, `W1`, `S1H`), `codeperiod`, floor / housing / business area, `addr_key`, `age_2021` | city-wide **existing stock as of ≈ 2021** (`age_2021`; created 2021-11); housing-oriented; derivation **UNVERIFIED** (the fields resemble a seismic-risk inventory built from the property-tax register) | point-in-polygon → WFS footprint |
| **臺北市歷年使用執照摘要** (data.taipei / data.gov.tw 128203) | Government Open Data License v1; XML 65 MB, annual | 8,762 use permits: issue / **start / completion dates**, addresses, **地段號 parcel list**, floors, height, structure, zoning, per-floor uses | **2001–2025 only** (ROC 90–114); 378 new builds in 信義區 | parcel key → `building_cadastralmap` → footprint |
| **臺北市歷年建造執照摘要** (data.gov.tw 128204) | Open Data License v1; XML 91 MB, annual | 9,043 construction permits (same structure) | 2001–2025 | parcel key; "permit without use permit" = active / stalled site |
| WFS `building_cadastralmap` | public WFS | **418,904 parcel polygons**, key = 段小段 + 8-digit 地號 | city-wide | permits ↔ parcels |
| WFS `building_permit` / `building_license` | public WFS | current-year construction permits (691 parcels) / use permits (158 points) | rolling, current year | parcel / point |
| WFS `building_renewunit_{12,20,30,…}` | public WFS | renewal-unit polygons with case numbers | city-wide; suffix meaning **UNVERIFIED** | polygon overlay |
| 執照存根影像 (data.gov.tw 132334 / img2.gov.taipei) | query system, scanned images | pre-2001 permit stubs | historical | **not structured; impractical** |

### 18.2 Join test (Xinyi WFS bbox)

* **Precision trap.** `building_age` returned in EPSG:4326 is rounded to 4 decimals (≈ 10 m). The request must
  use `srsName=EPSG:3826`, the same lesson as the footprint source.
* **Age points → footprints.** 10,623 points in the bbox:
  * 8,960 fall inside a footprint and 426 within 5 m, so **88 % attach**;
  * groups with an age: **2,545 / 4,137 = 61.5 % of look groups, 66.8 % of footprint area**.
* **By current archetype** (groups with an age / total):

  | archetype | matched | share |
  |---|---|---|
  | walk-up | 694 / 802 | 87 % |
  | huaxia | 1,077 / 1,448 | 74 % |
  | res_tower | 246 / 407 | 60 % |
  | low | 473 / 1,177 | 40 % |
  | podium | 7 / 46 | 15 % |
  | office | 44 / 132 | 33 % |
  | school | 2 / 114 | 2 % |

  Excellent for housing, poor for non-residential, as expected from a housing-based register.
* **Permits → parcels → footprints.** Of the new-build use permits in 信義 / 大安 whose parcels fall in the bbox,
  **231 / 257 (90 %) overlap WFS footprints**, tagging 1,868 footprint records. Permits whose parcels were not found
  are either outside the bbox or were renumbered by lot mergers; the split is **UNVERIFIED**.
* **Active construction.** 33 new-build construction permits from 2019–2025 with no matching use permit lie in the
  bbox: **≈ 7.6 ha of sites, mostly 9–37 F** (14 of them from 2022) [O data]. Some may be completed in 2026 or
  stalled; cross-check with the current-year `building_license` layer and the orthophoto. Part I's "construction is
  visible from the air" now has a **data-placeable source** inside the game area.

### 18.3 Measured construction decade of current archetypes (matched Xinyi groups)

| archetype (by floor count) | pre-1960 | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s |
|---|---|---|---|---|---|---|---|
| walk-up 4–5 F (n = 694) | 2 % | 16 % | **63 %** | 10 % | 5 % | 3 % | 0 |
| huaxia 6–12 F (n = 1,077) | 0 | 2 % | 23 % | **46 %** | 18 % | 8 % | 1 % |
| res_tower 13–24 F (n = 246) | 0 | 1 % | 13 % | **36 %** | **26 %** | 19 % | 6 % |
| low ≤ 3 F (n = 473) | 16 % | **31 %** | 15 % | 7 % | 15 % | 13 % | 2 % |
| office (n = 44) | — | — | — | 5 % | 16 % | **48 %** | 32 % |

The age layer ends ≈ 2021; post-2021 buildings come only from permits.

### 18.4 Verdict — **usable**

* **High-confidence age for ≈ 62 % of groups** (≈ 75–87 % of residential groups) comes from `building_age`.
* **Exact completion dates for 2001–2025 builds** come from permits via parcels.
* **Inference for the remainder** uses district × archetype × height priors computed from the matched groups
  (the table above).

That is sufficient: the visual need is an **era band** (≤ 1979 / 1980–1999 / 2000+), not a year. The pipeline
would be a locked, hashed snapshot in `data/lookdev_cache/` like the existing caches [P]. The open licence of the
`building_age` / cadastral WFS layers should be confirmed before shipping derived data.

---

## 19. Diagnosticity

Scale: **A** strongly Taipei-diagnostic · **B** common in Taiwan, useful for Taipei · **C** generic East-Asian /
global · **D** uncertain.

| trait | class | reasoning |
|---|---|---|
| basin floor ringed by steep forested mountains; Xinyi cluster + Taipei 101 | **A** | geography + landmark; the only truly Taipei-unique macro signals |
| Taipei 101 silhouette | **A** | landmark |
| sheet-metal rooftop covers (頂樓加蓋) over walk-up rows, green-grey / white / maroon patchwork | **B** (strongest B) | Taiwan-wide practice, but among East Asian cities a Taiwan marker. Taipei's 4–5 F carpet makes it the main roof cue |
| mid-rise (12–30 m) dominance with scattered towers | **B / C** | measured for Taipei; other Taiwanese cities and parts of Seoul / Tokyo share it |
| tiled residential façades (mosaic, 二丁掛, small square tile) | **B** | very Taiwan; Japan also tiles apartments. At range it reads as a colour field |
| 1980s–90s tiled towers with decorative crowns | **B / D** | Taiwan-typical in Part I photos; crown frequency **UNVERIFIED** (3 photos) |
| teal / bronze reflective glass on 1990s residential | **D** | single-photo evidence (P9); also common in 1990s mainland China / SE Asia |
| glass balconies, glass-balustrade towers | **C** | global contemporary |
| planted balconies / sky gardens | **C** | global trend; a few Taipei showpieces |
| maroon / oxidised-red sheet roofs; old orange-red pitched roofs (Wanhua) | **B** | Taiwan-typical; district-specific |
| green PU waterproof roofs | **B**, but rare | Taiwan trade practice; < 5 % of flat roofs sampled |
| stainless water-tank clusters on flat roofs | **B** | Taiwan / HK-typical |
| AC clutter, iron / stainless window grilles | **C / B** | shared with HK and South China; grilles slightly more Taiwan / HK |
| arcades (騎樓) | **B** | Taiwan / South China / SE Asia; invisible from the air |
| temples (red curved roofs, swallowtail ridges) | **B** | Taiwan (Min-style); locally strong |
| construction netting | **C** | generic |
| tower cranes | **C** | generic; still a strong "living city" cue |
| planted construction hoarding (≥ ½ planted on roads ≥ 10 m) | **B / D** | Taipei regulation; similar rules elsewhere **UNVERIFIED**; a thin line from the air |
| blank stepped side / party walls | **C** | any dense city with mixed heights |
| rooftop solar on large roofs | **C** | global |

**Conclusion [I].** At aircraft range "Taipei" is
**A-geography + A-landmarks + a B-grade Taiwanese residential / roof grammar at Taipei's measured density, height
mix and age**. Almost nothing below the landmark scale is uniquely Taipei. Identity comes from the right *mix and
proportions*, which argues for data-driven City Profiles rather than more unique props.

---

## 20. Aircraft readability (mobile-first, 1080p, 60° vFOV)

Pixel scale: 3.7 px/m at 250 m, 1.2 at 800 m, 0.31 at 3 km.

| trait | 100–250 m | 250–800 m | 0.8–3 km | 3 km+ | verdict |
|---|---|---|---|---|---|
| roof cover colour patchwork (per-lot 4–8 m strips) | ●●● | ●●● | ●● (mottling) | ● (district tint) | **keep, top value** |
| cover vs flat-cluttered roof state | ●●● | ●●● | ●● | ● | keep |
| tile colour field per building | ●●● | ●●● | ●●● | ●● | keep (palette by era) |
| era contrast: old streaked vs clean new towers | ●●● | ●●● | ●●● | ●● | keep |
| tower crowns / roof frames (10–25 m) | ●●● | ●●● | ●● | ● (silhouette) | keep, P1 |
| tower cranes (jib 50–60 m, members ≈ 1.5 m) | ●●● | ●●● | ●● (thin lines, alias risk) | ● | keep; geometry needs a min-pixel width policy |
| netted / scaffolded frames (whole-face colour) | ●●● | ●●● | ●●● | ●● | keep |
| cleared lots / excavation pits | ●●● | ●●● | ●● | ● | keep (ground class) |
| planted hoarding (2.4 m strip) | ●● | ● | — | — | **downgrade**: ground-line detail only |
| teal / bronze glass (large faces) | ●●● | ●●● | ●● | ● | readable, but evidence **D** → P2 |
| glass balconies / balustrades | ●● | ● | — | — | **downgrade**: atlas detail only |
| planted balconies | ●● | ● (green dots) | — | — | downgrade |
| AC stacks | ●● | ● | — | — | keep only as existing shader texture |
| arcades | ● (oblique only) | — | — | — | **reject for aerial work** |
| iron / stainless grilles | ● | — | — | — | already sub-pixel; no new work |
| stainless tank clusters | ●●● | ●● | ● | — | keep (existing) |
| blank side walls (10–30 m) | ●●● | ●●● | ●● | ● | candidate, evidence weak → P2 |
| temples | ●●● | ●● | ● | — | data-gated, P2 |
| rooftop solar arrays | ●●● | ●●● | ●● | ● | cheap roof state, P2 |

---

## 21. Taxonomy — attempt to break it

Each axis tested for **visual difference at 250–3,000 m per runtime / authoring cost**:

| axis | visual payoff | cost | decision |
|---|---|---|---|
| **age / era** | **high**: palette, weathering, balcony type, crown / roof state, glass | low (data + parameters) | **primary parameter** (≤ 1979 / 1980–99 / 2000+) |
| **use** (residential vs commercial glass vs civic / school vs industrial shed) | high: tile vs curtain wall vs long pale wings vs large spans | archetype codes already exist | **keep as the runtime grammar split** |
| **height** | high, but **already in the geometry** | 0 | parameter (podium / crown rules), not a family |
| **construction method** (`mbt`: masonry `URML` / `RML`, RC `C1*`, steel `S*`) | low directly; useful to *classify* old low-rise (masonry) and steel offices | 0 (data) | **classifier input only** |
| **socio-economic class** (ordinary / premium / social) | medium for 2000+ towers (finish, setbacks, sky gardens); low at range | data: `building_social_house` WFS layer; premium proxy = permit cost per floor area **UNVERIFIED** | **minor parameter** on 2000+ residential |
| **façade language** | the output, not an input | — | derived from era × use × class |

**Proposed structure** (replaces Part I's 8 families plus 2 point features):

* **Runtime grammars (archetype codes): 6.**

  | # | grammar | covers |
  |---|---|---|
  | 1 | residential | walk-up, 華廈, towers, low houses in residential zones |
  | 2 | commercial glass | offices, podiums |
  | 3 | civic / school | civic buildings, campuses |
  | 4 | low-rise informal / shophouse | old low-rise; masonry `mbt` |
  | 5 | industrial / large-span shed | sheds, depots |
  | 6 | landmark registry | 101, SYS Hall, Dome, City Hall |

* **Parameters per building group:**
  * era band;
  * height band (from geometry);
  * class (ordinary / premium / social);
  * roof state (cover / flat-cluttered / crown-frame / clean / solar);
  * district profile weights.
* **Point features:** temples (data-gated); **cross-cutting state:** construction (data-placed).

**Do 1980s–90s tiled towers and post-2010 towers deserve separate runtime archetypes? No.** They share the
residential structure: bays, balconies, floor banding, podium / lobby, roof equipment. They differ in parameters:

* tile vs stone / metal palette;
* glass tint;
* balcony type (parapet vs glass rail);
* crown type (cap vs frame);
* weathering.

Two archetype codes would double shader branches and authoring for little gain. As era ranges inside the
residential grammar, the difference is carried by **a palette / weathering table plus atlas cells and crown
props keyed by era**. The data (§18.3) also shows the old split was mis-dated: **most 13–24 F residential in the
Xinyi area is 1980s–90s, ≈ 25 % is 2000+**. The cut is by era, not by "tower type".

---

## 22. Current Xinyi biases — verdicts

| claim | verdict | evidence |
|---|---|---|
| **too blue on roofs** | **CONFIRMED** | Current instanced sheet colours (`sheet_colour_use`, 1,982 rooms): **blue 24 %**, green incl. teal 22 %, red 19 %, neutral 35 %. Sample: blue **1–4 %**, green-grey 37 %, neutral 39 %, red 23 %. Blue is ~6–18× over-weighted; green and neutral are moderately under. The shader's painted-roof index also moves warm picks *to* blue. Blue specks are visible in `day_roof_ne1` / `ne2` |
| **too uniform by building type** | **LIKELY** | Façade palette = archetype + seed, with no era or district axis, while measured decades within each archetype span 50+ years (§18.3). On-screen magnitude not measured |
| **missing age variation** | **CONFIRMED (mechanism), magnitude moderate** | No age input exists. But ≈ 72 % of huaxia and ≈ 91 % of walk-ups predate 1990, so the old grammar is *right* for most of them. The visible error concentrates in res_tower (≈ 25 % 2000+, 26 % 1990s) and in ≈ 10 % new huaxia |
| **missing construction** | **CONFIRMED** | 0 construction elements in the build; permits imply ≈ 33 active / stalled new-build sites (≈ 7.6 ha) in the bbox (§18.2); orthophoto windows show cleared lots / excavation (Daan, Neihu) |
| **too many small rooftop rooms** | **REJECTED as stated → re-scoped** | 1,650 of 5,061 old roof parts (33 %) carry rooms, plus painted sheet roofs on ~28 % of old buildings and surveyed rooftop records. Observed covered share of low-rise roof area is 66 % (Wuxing 75 %), so coverage is, if anything, **too low**. The real mismatch is **form**: discrete room boxes with gaps vs footprint-filling, per-lot covers (LIKELY, by eye) |

---

## 23. Confidence matrix

| finding | evidence strength | geographic coverage | aircraft relevance | implementation consequence |
|---|---|---|---|---|
| Taipei is mid-rise dominated (≈ 61 % of built area 12–30 m) | **strong** (city-wide WFS) | city-wide | all ranges | CityProfile height mix is free from geometry; no action |
| sheet covers ≈ 2/3 of low-rise roof area, 33–91 % by district | **moderate–strong** (348 points, 12 windows, one observer) | 11 districts | 0.1–3 km | per-profile cover rate; raise Xinyi–Wuxing coverage |
| covers are footprint-filling, per-lot strips | moderate (visual, several windows + P3) | several districts | 0.1–1 km | roof-cover generator by lot width, not room boxes |
| roof colours: green-grey ≈ neutral > maroon ≫ blue | **moderate** (±6 % overall; colour boundary subjective; mixed imagery) | 11 districts | 0.25–3 km | rebalance palette; blue → trace; per-profile red share |
| flat cluttered roofs are the second major low-rise state | moderate | 11 districts | 0.1–1 km | keep / strengthen the tank / bulkhead / clutter roof state |
| building age available for ≈ 62 % of groups (≈ 75–87 % residential) | **strong** (measured join) | Xinyi bbox; layer city-wide | indirect (drives era) | build an era band per group; infer the rest by priors |
| 2001+ completion dates via permits + parcels (≈ 90 % of located permits hit footprints) | strong | Xinyi / Daan tested | indirect | exact era for new buildings |
| active construction is data-placeable (≈ 33 sites / 7.6 ha in bbox) | moderate (permit logic; stall / complete status unverified) | Xinyi bbox | 0.1–3 km | construction layer from permits |
| 13–24 F residential is mostly 1980s–90s, ≈ 25 % 2000+ | strong (data, n = 246) | Xinyi bbox | 0.25–3 km | era parameter, not a new archetype |
| decorative crowns on 1980s–90s towers | **weak** (3 photos) | unknown | 0.25–3 km | needs a crown count before authoring a kit |
| teal / bronze glass on 1990s residential | **weak** (1 photo) | unknown | 0.25–3 km | parameter only; verify before art |
| blank stepped side walls | weak–moderate (2 photos) | West Taipei, Nangang | 0.25–3 km | P2; verify frequency |
| green PU roofs common | **weakened** (≈ 4 / 120 flat points) | 11 districts | 0.25–3 km | minor palette entry only |
| planted construction hoarding | strong as regulation, weak as aerial cue | Taipei | < 250 m | ground-line detail; low priority |
| diagnosticity: almost all sub-landmark traits are B / C | moderate (comparative judgement) | — | — | identity via mix / proportions → CityProfiles |
| overcast / haze default | moderate (climate normal ≈ 3.8 h sun/day) | city-wide | all | validate palettes under overcast, not only clear sky |

---

## 24. Summary of this pass

### 1. Findings that survived falsification
* Mid-rise carpet + scattered towers + one Xinyi cluster, ringed by mountains (city-wide WFS data).
* Sheet-metal rooftop covers are a **major, Taiwan-diagnostic** roof state and the strongest sub-landmark aerial
  cue, though not universal.
* Pale green-grey is a recurring, important roof colour family.
* Current Xinyi is **too blue on roofs** and **has no construction**.
* Age variation is genuinely missing, and age data exists to supply it.
* Construction is real and visible in the game area, and now data-placeable.
* Identity is carried by proportions and mix more than by any single unique prop.

### 2. Findings that weakened or changed
* Roof colour: **green-grey ≈ white / grey (≈ 37 / 39 %), maroon / red ≈ 23 %, blue ≈ 1–4 %**, not "40–50 % mint".
  The green is pale and desaturated.
* Covers are **common, not dominant**: 33–91 % by district. Flat cluttered roofs are the second major state.
* "Too many rooftop rooms" is **rejected**. The issue is **form** (rooms with gaps vs per-lot footprint covers), and
  coverage is if anything low.
* The "1990s tower" family is mostly **1980s–90s**. 1980s–90s vs 2000+ towers become **era parameters of one
  residential grammar**, not separate archetypes.
* Old-grammar misuse is **moderate, not pervasive**: most 6–12 F buildings really are 1970s–80s.
* Downgraded to short-range or unverified: teal / bronze glass, decorative-crown frequency, glass and planted
  balconies, green PU roofs, planted hoarding, arcades (rejected for aerial use), blank side walls (P2).

### 3. Unresolved questions
* Licence terms of the City Dashboard WFS layers (`building_age`, `building_cadastralmap`, `building_permit`), and
  the provenance and update cycle of `building_age`.
* Meaning of `building_renewunit_*` suffixes; how many of the 33 permit-only sites are active vs stalled vs
  just-completed.
* Crown and teal-glass frequency (needs a tower count from oblique imagery).
* A second observer or a calibrated colour classifier for the green-grey / grey boundary, preferably on a single
  flight date.
* Roof states of 6–12 F buildings (excluded from the orthophoto sample because of relief displacement).
* Night-time language by era (not studied).

### 4. Is building-age data usable? **Yes.**
* `building_age` attaches to ≈ 62 % of Xinyi look groups (≈ 75–87 % of residential).
* Permits + parcels give exact 2001–2025 completion dates (≈ 90 % of located permits overlap footprints).
* District × archetype priors fill the rest.
* Era *bands* are all the visuals need. Confirm the licence before shipping derived data.

### 5. Visual systems now most justified for further development (not approved)
1. **Era data layer.** `building_age` + permits + parcels → era band per group, plus priors for unmatched groups.
   *Data.*
2. **Residential grammar with era parameters.** Palette, weathering, balcony type, roof state and crown type keyed
   by era × height × class, replacing floor-count-only façade choice. *Data / material variation; atlas cells
   later.*
3. **Roofscape v2.**
   * footprint-filling, per-lot sheet covers;
   * colour rebalance (green-grey ≈ neutral > maroon, blue → trace, pale and desaturated);
   * district-dependent cover rate;
   * a stronger flat-cluttered roof state;
   * solar on large flat roofs.

   *Simple geometry + data.*
4. **Construction from permits.** Data-placed sites with states (cleared / excavation / frame / netted /
   envelope) and cranes. *Instanced props + simple geometry.*
5. **City Profiles from measured statistics.** Height mix, cover rate, roof colour shares and era mix per district
   (e.g. Wanhua and Beitou red-heavy, Shilin cover-heavy, Neihu and Minsheng flat-roof-heavy). *Data.*
6. **Era-driven macro weathering.** Rain-streak / mould darkening on pre-1990 stock, clean 2000+ towers. Readable
   to 3 km as value contrast. *Procedural shader (existing terms).*
7. **Tower crowns / roof frames keyed by era.** P1, gated on a crown-frequency count. *Simple geometry.*
8. (P2, evidence-gated) stepped blank side walls, temples from OSM, teal / bronze glass variants.

### Sources added in this pass
* NLSC WMTS orthophoto (`PHOTO2`, 2024 mosaic): https://wmts.nlsc.gov.tw/wmts — viewed / sampled only; tiles kept
  in the session scratchpad, not the repo.
* Taipei City Dashboard WFS (layers `building_age`, `building_cadastralmap`, `building_permit`,
  `building_license`, `building_renewunit_*`, `tp_building_height`):
  https://citydashboard.taipei/geo_server/taipei_vioc/ows
* 臺北市歷年使用執照摘要: https://data.gov.tw/dataset/128203 ·
  https://data.taipei/dataset/detail?id=c876ff02-af2e-4eb8-bd33-d444f5052733
* 臺北市歷年建造執照摘要: https://data.gov.tw/dataset/128204
* 臺北市執照存根影像: https://data.gov.tw/dataset/132334

**STOP.** No asset generation, no Image 2.5 call, no runtime change, no commit.
