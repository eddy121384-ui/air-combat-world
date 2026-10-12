# Northern Taiwan environment asset inventory — v0

Status: **research and documentation only.** No image generation, 3D modelling, Unreal execution, shader change,
runtime change or asset purchase happened in this pass. Nothing here is approved, built or measured in-engine.

Branch `research/north-taiwan-environment-assets`, created directly from fetched remote
`origin/feat/opus55-xinyi-visual-quality` = `ede7960d8ec05b2aa521b1e4c65b5bbd667c456d` (verified equal to the
handoff SHA). Draft PR #14 (`spike/xinyi-material-imagegen-batch1`, head `6c2feb1`) was **read only**; it is not
modified, duplicated or merged here.

Evidence tags used throughout:

| tag | meaning |
|---|---|
| **[Repo]** | read directly from this repository at the baseline SHA |
| **[Gov]** | official Taiwan government or agency page / dataset page (as surfaced by search; see §10 limits) |
| **[Acad]** | thesis, journal or institutional repository |
| **[Sec]** | news, trade, blog or contractor-guide source: useful for vocabulary and orientation, not for numbers |
| **[I]** | my judgement or general engineering / botanical knowledge, **not verified against a source in this pass** |

Rule applied: no prevalence figure appears unless a source states it, and it is then quoted with its source tag.
Where a number would be useful and none was found, the document says "no figure found".

---

## 1. Executive findings

1. **The accepted Xinyi build is a city, not a world.** Everything it has — facade shader, roof props, street trees, hill
   forest, road SDF, backdrop mountains, far-city massing — is tuned for an urban basin. [Repo] It has **no** agriculture,
   port, airport, industrial, coastal, river-bank, bridge, pylon or retaining-wall content at all. Those are the gaps that
   decide whether Northern Taiwan reads as Northern Taiwan from 600–800 m and from several kilometres.
2. **At aircraft distance, ground-cover pattern beats object detail.** At 600–800 m a 3.5 m bay is 4–5 px and a 2 m patch
   is 2–3 px (the repo's own pilot table). [Repo] What survives is *field mosaics, pond scatter, canal lines, hill
   canopy texture, coast edges, warehouse/tank/crane silhouettes and road/rail linework*. Priority therefore goes to
   **land-use-driven ground materials (E) + a handful of silhouette modules (C/D)**, not to more building texture.
3. **Vegetation is the single most under-built family.** The current tree is one 28-triangle jittered-icosahedron blob
   (8 trunk + 20 crown triangles) with a 4-way colour variant, opaque, no leaf texture. [Repo] 16,082 street/park trees
   remain after the v0D filter. The hill forest is a 100-triangle five-blob clump. This is a good *cost* baseline and a
   weak *identity* baseline: every tree has the same silhouette. The fix is **4–6 crown archetypes, one shared leaf/canopy
   atlas and shader-driven variation**, not many species and not high polygon counts.
4. **Material work is already ahead of everything else.** Xinyi's facade/roof grammar is procedural and mask-driven, and
   PR #14 supplies six offline candidate surfaces. [Repo] The remaining material gap for the *north-Taiwan* world is the
   **non-Xinyi surface set**: corrugated/sheet roofs, industrial cladding, exposed concrete (bridges, retaining walls),
   pavement/apron wear, field top-down surfaces and shoreline materials.
5. **Taiwan identity cues that the sources do support** (confidence in §10): Taoyuan Plateau irrigation ponds (埤塘) as a
   scatter of water polygons in farmland [Gov/Sec]; red-brown 二丁掛 and washed/pebble (洗石子/抿石子) walls as
   mid-century public and residential finishes [Sec]; mangrove (水筆仔) at the Tamsui estuary and sand-coast belts of
   馬鞍藤 → 林投/草海桐/黃槿/白背芒 [Gov/Acad]; second-generation farmhouses and spreading 農舍 in Yilan's Lanyang Plain
   [Sec/Acad]; elevated freeway segments with very tall piers (五楊高架 林口段 pier ≈ 40 m, per one news source) [Sec].
6. **Do not default to blue roofs.** This repo's own roofscape study measured blue sheet at only 1–4 % of Xinyi
   orthophoto roofs against a code-implied ~25 %. [Repo, roofscape-v2 §1.1] The stereotype "Taiwan = blue 鐵皮 roofs"
   must be **verified per region (factory, farm, village)** before any industrial/rural roof palette is authored.
   No source in this pass gives rural or industrial roof colour shares.
7. **Sales-readiness is a separate risk track.** Taiwan's Open Government Data License v1.0 is permissive (commercial use,
   attribution required, sub-licensable, compatible with CC BY 4.0) [Gov/SPDX], but Overture/OSM-derived data may carry
   ODbL share-alike [Sec], Copernicus/MOI mirrors have their own terms, and AI-generated sources need provenance
   records. See §11.
8. **Recommended order:** E-class land-use backbone and the vegetation pilot first (P0), then rural roofs/farmhouse and
   ground-material batch 2, then port / airport / industry modules, then bridges/pylons. Sensitive military layouts are
   out of scope throughout.

---

## 2. Existing asset coverage vs gaps

### 2.1 What exists at the baseline (all [Repo])

| area | what exists | source |
|---|---|---|
| Building geometry | deterministic 500 m ENU tiles, 11,128 ordinary parts, GEOS-triangulated; accepted, **not to be rebuilt** | `AGENTS.md`, `docs/xinyi-v2-full-xinyi-cloud-result.md` |
| Facades | fully procedural ALU shader (`xc_wall`): era archetypes (legacy walk-up, huaxia, modern, premium, office), cages, AC, arcades, storefront atlases, wall-ad atlas; **no photographic textures** | `docs/xinyi-look-v1-visual-pass.md`, `tools/lookdev/shaders/xinyi_city.hlsl` |
| Ageing masks | **specified, not built**: `T_XinyiFacadeAge`, `T_XinyiRoofSurface`, podium fascia | `docs/xinyi-custom-material-library-spec-v0.md` |
| PR #14 (Draft) | 6 offline candidates: ceramic surface, washed-aggregate plaster, warm-grey stone, weathering field, sparse repairs, rain run; **zero runtime atlases, zero Unreal imports, pending artistic approval** | PR #14 body + `assets/materials/xinyi/imagegen/batch1/README.md` on the spike branch |
| Roofs | 29,030 instanced props on real roof polygons (9 HISMs: sheds, tanks, solar heaters, antennas, condensers, machine rooms, cooling towers, BMU cranes, aviation lights); Roofscape v2 sheet-metal covers (procedural) | `docs/xinyi-look-v1-visual-pass.md`, `docs/xinyi-roofscape-v2-material-pilot.md` |
| Street trees | `SM_XinyiTree`: 20-face jittered icosahedron crown + 4-sided trunk, one mesh, per-instance yaw, scale 0.8–1.25 (×1.15 for park trees), 4 colour variants in `xc_foliage`; cull 1.5–2.6 km; 20,401 → **16,082** trees after v0D filter (park 10,567 + mapped 290 never dropped) | `tools/lookdev/build_ground.py`, `docs/xinyi-taipei-street-reality-v0d.md` |
| Hill forest | `SM_XinyiForestClump`: five jittered blobs, 100 triangles, one per ~16 m on slopes (`z ≥ 28 m` and slope rule), 1,190 clumps over the Four Beasts | `build_ground.py` |
| Roads/ground | OSM road SDF in a 2048² data texture (kerbs crisp at any distance), paint mesh (95k tris), walkways, scooters, lamps with baked light-pool texture. **Bridge and tunnel ways are skipped** (`skip = tunnel or bridge`). Water is a class value (1.0 water / 0.8 running) in the ground data texture, not a river asset. | `build_ground.py` |
| Terrain | MOI 2025 20 m bare-earth DTM (mirror), accepted 2.5 km Xinyi Landscape (E −1500…1000, N −1000…1500), basin backdrop ~150 m sampling with urban-floor and forest weights, far-city massing (43 × 2.5 km chunks, 207,360 tris, WFS-based) | `tools/lookdev/build_backdrop.py`, `build_far_city.py`, `docs/xinyi-terrain-v0-dtm-result.md` |
| Landmarks | Taipei 101 hero (2.5k tris), 國父紀念館, 臺北大巨蛋, 臺北市政府 via `landmarks.json` | `tools/lookdev/landmarks.json` |
| City config | 40 × 40 km playable, 20 × 20 km detail core, 80–100 km visual outer, 0–12 km vertical; runway source planned as OSM `aeroway` but **no runway code found** | `cities/taipei/city.yaml`, `docs/architecture.md` |

### 2.2 Gaps (all [Repo] absence, grep-checked for songshan/runway/aeroway, container, crane, paddy/rice, greenhouse)

| family | status at baseline |
|---|---|
| 1 Urban materials | **partial**: Xinyi procedural + 6 PR #14 candidates (unapproved); no rural/industrial/infrastructure surfaces |
| 2 Vegetation | **thin**: one broadleaf blob, one forest clump; no archetype diversity, no leaf/canopy texture, no coastal/wetland/scrub/bamboo/palm |
| 3 Agriculture / water / coast | **absent** (water exists only as a ground-texture class in Xinyi) |
| 4 Ports / harbours | **absent** |
| 5 Airports | **absent** (Songshan lies north of the Xinyi frame, but no runway/apron asset exists) |
| 6 Industry / energy | **absent** (rooftop cooling towers and tanks exist on buildings only) |
| 7 Suburban / rural | **absent** (the building generator is era/frontage-role driven for dense Taipei lots) |
| 8 Roads / bridges / utilities | **partial**: surface roads + paint; no elevated roads, bridges, overpasses, pylons, poles, retaining walls, drainage |

---

## 3. Ranked eight-family asset matrix

**Method classes:** A AI surface material · B AI leaf/foliage atlas source · C 3D mesh / modular Blender asset ·
D procedural geometry / placement rule · E GIS / terrain / land-use data · F unique hero landmark.
One asset may use several. **Image generation alone does not produce an engine-ready 3D asset**; every C/D entry still
needs geometry, UVs/LODs and an engine test.

Priority scale: **P0** core world visual identity · **P1** important secondary · **P2** later detail.
Aerial score (1–5) = visibility at 300–800 m and over kilometres. Cost: L/M/H development cost. Mobile: L/M/H runtime cost.

### 3.1 Top-ranked list (the ~15 items to start from)

| rank | asset | family | method | pri | aerial | reuse | cost | mobile | existing equivalent |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Land-use / ground-cover classification → regional ground material layers** (paddy, dry field, orchard, forest, scrub, built, water, sand, mud) | 3 | E (+A for the surfaces) | P0 | 5 | very high | M | L | none (Xinyi ground = OSM SDF only) |
| 2 | **Crown archetype set (4–6) + shared canopy/leaf atlas + shader variation** | 2 | B, C, D | P0 | 5 | very high | M | M | `SM_XinyiTree` (single blob) |
| 3 | **Hillside canopy cover** (broadleaf + bamboo + acacia mixes) for Yangmingshan / Linkou / Keelung / Wulai-direction slopes | 2 | B, D, E | P0 | 5 | high | M | M | `SM_XinyiForestClump` (Xinyi-only) |
| 4 | **Coastline + shore materials + sea edge/foam band** (sand, rock shelf, riprap/armour units, mudflat, estuary) | 3 | E, A, D | P0 | 5 | high | M | L | none |
| 5 | **Field mosaic + canal/ditch + farm-road pattern** | 3 | E, D | P0 | 5 | high | M | L | none |
| 6 | **Taoyuan irrigation-pond scatter** (埤塘 polygons, bank trees, canal links) | 3 | E, D | P0 | 5 | medium | L | L | none |
| 7 | **Rural / suburban low-rise house kit** (3–5 storey 透天厝 / 農舍 / 加蓋 roofs / sheds) | 7 | D, C, A | P0 | 4 | very high | M | M | procedural dense-lot buildings only |
| 8 | **Sheet-metal / flat-roof wear surfaces for non-Xinyi roofs** | 1 | A, D | P0 | 4 | very high | L | L | Roofscape v2 sheet covers (Xinyi); mask pack specified, unbuilt |
| 9 | **Container terminal + breakwater + STS crane + ship kit** (Keelung, Taipei Port) | 4 | C, D, E | P0 | 4 | high | H | M | none |
| 10 | **Airfield kit** (runway/taxiway/apron markings, terminal, tower, hangar rows, generic support) for Taoyuan / Songshan / Hsinchu-type fields | 5 | E, D, C, F | P0 | 5 | high | M | L | none |
| 11 | **Elevated road / bridge / overpass modular set** (deck, piers, parapet, ramps) | 8 | C, D, E | P0 | 4 | very high | M | M | skipped in `build_ground.py` |
| 12 | **Factory / warehouse / tank / stack industrial kit** | 6 | C, D, A | P1 | 4 | very high | M | M | rooftop tanks only |
| 13 | **River + riverbank + wetland / mangrove strip** (Tamsui, Keelung, Dahan, Xindian; Guandu) | 3 | E, D, B | P1 | 4 | medium | M | L | water class only |
| 14 | **Pylon lines + substations** (generic lattice, spacing along E data) | 6/8 | D, C | P1 | 3 | very high | L | L | none |
| 15 | **Retaining walls / slope protection / drainage channels** on hill roads and housing edges | 8 | D, A, E | P1 | 3 | high | L | L | none |

### 3.2 Full matrix by family (all recommended assets)

**Family 1 — Urban architectural materials**

| asset | method | pri | note |
|---|---|---|---|
| Ceramic surface, washed aggregate plaster, stone, weathering, sparse repairs, rain run | A | — | **already produced offline in PR #14**; awaiting art approval. Do not regenerate. |
| 二丁掛 / 小口磚 colour-field (no joints) | A + D (joints) | P0 | joints are procedural (hash-driven, pixel-footprint filtered); matches PR #14's own "A1 = continuous surface, grout later" plan |
| Square tile / mosaic colour-field | A + D | P1 | merge with 二丁掛 pack if the pack reads well |
| Painted plaster/concrete with mildew & run | A (PR #14 B1/B3) | — | exists as candidates |
| Exposed concrete (piers, retaining walls, industrial bases) | A | P0 | not in PR #14 |
| Commercial glass + metal facade | D (+ sky reflection) | exists | stays procedural; no art |
| Flat-roof waterproofing membrane | A | P0 | spec'd in custom-material-library §2.6 |
| Sheet-metal roofing wear | A + D (ribs) | P0 | ribs/seams procedural |
| Industrial profiled cladding | A + D (panels) | P1 | |
| Architectural stone | A (PR #14 A3) | — | exists |

**Family 2 — Vegetation**

| asset | method | pri |
|---|---|---|
| 4–6 crown archetypes (dome / tiered / vase-spread / columnar / palm / bamboo-plume) | C + B + D | P0 |
| Shared leaf/canopy atlas (broadleaf leaf-cluster sheet; bamboo/grass sheet) | B | P0 |
| Hillside canopy surface (far-LOD terrain-draped canopy material) | B + E | P0 |
| Scrub / 芒草 grassland patches (Yangmingshan-type slopes) | B + D | P1 |
| Coastal belt (林投/草海桐/黃槿/木麻黃-type windbreak lines) | B + D + E | P1 |
| Mangrove / riverside reed strips | B + D + E | P1 |
| Residential greenery (potted/rooftop/garden clusters) | D | P2 |

**Family 3 — Agriculture, water, coast**: see ranks 1, 4, 5, 6, 13; plus greenhouse strips (C + D, P1), dry-field row
pattern (A + E, P1), farm-road & ditch linework (D + E, P1).

**Family 4 — Ports / harbours**

| asset | method | pri |
|---|---|---|
| Quay + breakwater + mole geometry from coast data | E + D | P0 |
| Container stack yard (colour-block packing rule) | D (+ palette) | P0 |
| STS (ship-to-shore) container crane, 2 variants | C | P0 |
| Container ship + bulk/general cargo ship (2–3 hulls) | C | P0 |
| Warehouse/shed rows, storage-yard ground wear | D + A | P1 |
| Fishing harbour kit (basin, boat clusters, ice plant/auction shed) | D + C | P1 |
| Fishing boat hulls (2–3 types) | C | P1 |
| Wave-armour units (tetrapod-type) on breakwater heads | D (instanced) | P1 |

**Family 5 — Airports**

| asset | method | pri |
|---|---|---|
| Runway/taxiway/apron surface + markings (generated from E data + marking rules) | E + D + A (wear) | P0 |
| Terminal block (hero silhouette per major airport) | F / C | P1 |
| Control tower (2–3 generic types) | C | P1 |
| Hangar / apron-edge building rows | D + C | P1 |
| Approach-light rows, taxi signage | D | P2 |

**Family 6 — Industry / energy**: factory shed (long-span) · cylindrical/spherical tank farm · smokestack · cooling tower ·
coastal power-plant block as *generic form* · substation yard · pylon/lattice. All C + D; no named-facility replicas.

**Family 7 — Suburban / rural**: row/terrace low-rise (D + C), 農舍 with yard (D + C), agricultural sheds / pump houses
(C), mountain-village stepped cluster (D + E), fishing-village cluster with harbour link (D + E), urban-rural transition
rule (D + E: lot size grows, roof-cover mix shifts).

**Family 8 — Roads, bridges, utilities**: elevated freeway deck+pier (C + D), river bridge (C + D), overpass/ramp (D),
retaining wall (D), drainage channel / river canal (E + D), road barrier + guard rails + major markings (D), utility
pole line (D; low aerial value, P2), pylon (above).

---

## 4. Taiwan-specific visual references

Only references located in this pass are listed. "Not found" is stated rather than filled in. No copyrighted reference
image is committed; the links point to pages only.

| topic | what the source supports | tag |
|---|---|---|
| Taoyuan Plateau ponds | Taoyuan City describes **>2,800** 埤塘, "the most in Taiwan"; a historical account claims **>8,800** once existed and ~2,800 remain; Bade district alone is cited as ~80+. Ponds were built because the plateau lacked river water; **Taoyuan Canal (1928) and Shimen Reservoir (1956)** later became the main supply and were linked to the old ponds. Ponds are now partly converted to eco-parks, detention basins or solar sites; in 2017 low-reservoir drought the ponds were drawn on for ~30 million tonnes. **No official agency total was found**, and the figures disagree, so a single count must not be hard-coded. | Gov (Taoyuan Bade page)/Sec/Acad |
| Washed-stone (洗石子) & 抿石子 | introduced under Japanese rule from terrazzo-type techniques; a heritage-housing article says peak **1950–1980s** on public buildings, temples, schools and houses. No source for housing share. | Sec (not primary-verified) |
| 二丁掛 / 小口磚 | name of Japanese origin from brick-face proportions (~60 mm face = "二丁"); early examples dark red/brown on historic buildings; modern ones come in many colours and textures. | Sec |
| Roof sheet metal | common materials: galvanised steel, aluminium-zinc, aluminium and stainless sheet; galvanised rusts. No colour-share data found. | Sec (contractor guides) |
| Rooftop add-ons (頂樓加蓋) | one thesis found: 37 % of surveyed households had installed bars/rooftop add-ons/shutters (facade study) — not a roof-colour or prevalence source for the whole island. | Acad |
| North-Taiwan broadleaf forest | 文山林場 survey: six forest types (紅楠, 相思樹, 水同木, 江某, 香楠, 山紅柿-大明橘) with 紅楠 dominating mid-slope/ridge and 水同木/江某 in valleys; 惠蓀 secondary-forest study lists 樟, 香桂, 白匏子, 山黃麻-澀葉榕 types. **The second site is central Taiwan** and is a pattern reference only. 構樹 not covered by any source found. | Acad |
| Estuary and coast vegetation | mangrove in the north is dominated by **水筆仔**; a hobby-site figure of ~76 ha pure stand at Zhuwei–Gan-zhen (unverified, treat as unverified); Forestry Bureau sand-coast zonation: front herb belt (馬鞍藤, 濱刀豆), then shrub/coastal forest with 林投, 草海桐, 黃槿, 白背芒. | Gov/Acad/Sec |
| Taipei street trees | 臺灣欒樹 and 樟樹 appear as common street/park trees (park office statement as reported); a teaching document states **>90,000** street trees and **3,800+** protected old trees (**educational material, not an official statistic**); an NTU thesis (3 districts, 517 reports) finds 榕樹, 茄苳, 白千層, 盾柱木 have disproportionate failure incidents. **No species-share table for Taipei was found.** (Tainan's count — 38,344 trees, 187 species, 小葉欖仁 most common at 2,989 — is not Taipei.) | Gov/Acad/Sec |
| Yilan Lanyang Plain | farmhouse (農舍) spread since the 2000 amendment of the Agricultural Development Act (0.25 ha minimum); paddy, scallion fields and duck farms alternate on the plain; Yuanshan retains farm ponds (travel-blog source). No quantitative layout study found. | Sec/Acad |
| Elevated freeway | 五楊高架: 40 km; Linkou-section pier height ≈ 40 m; height varies strongly along the route, whereas 汐五高架 sits only slightly above the mainline. | Sec (CNA / NCU thesis) |
| Keelung Port | East side historically mixed military + container; planning moves containers/military to the west side and east toward cruise/commercial; some east-side quays are reserved for defence use. Crane counts or types **not found**. | Gov (Executive Yuan news) |
| Taipei Port | planned 1,038 ha land, 471 ha filled (time of the cited news); South Terminal Phase II ~567 ha planned. Its breakwater geometry was **not found** (the "北外廓防波堤" hits were Shen'ao fishing harbour). | Gov/Sec |
| Taoyuan Airport | north runway 3,660 × 60 m (rehab completed 2015); south runway reported 3,800 × 60 m (**single secondary source**, verify); two terminals today, Terminal 3 under construction, Terminal 1 slated for rebuild after T3. | Gov/Sec |
| Songshan Airport | runway ≈ 8,500 ft (≈ 2,590 m) per a CAA statement as reported; positioned as a business airport. | Gov/Sec |
| Hsinchu air base | home of a fighter wing; has hardened shelters at the north runway end per press coverage. **Layout detail is intentionally not recorded here.** | Sec |
| Power plants | 林口: three coal units of 800 MW each (Taipower monthly report). Visual form of 協和 / 大潭 **not found**. | Gov |
| Fishing harbours | 南方澳 is a Class 1 harbour (outside the north); 八斗子 has a recreation harbour zone; 龜吼 is a rated harbour. Class of 正濱, 梗枋, 野柳 not found. | Gov |

---

## 5. Essential building material families

Principles inherited from the accepted Xinyi pipeline [Repo]: art is **neutral greyscale, linear**, colour comes from
per-building palettes; windows, doors, floor lines and lights are never baked; one texture sample per surface class;
12–16 texels/m ceiling; features 1–8 m, averaging to a stable value when sub-pixel.

| material family | surface identity (A) | procedural part (D) | status |
|---|---|---|---|
| 二丁掛 / 小口磚 | broad colour-field patchiness, fade, replacement tiles (3–10 m variation) | tile joint grid at the 60 × 227 mm module-class spacing [I], grout colour, pixel-footprint fade to mean | **gap** — Queue A |
| Square tile / mosaic | colour field, chipped zones | small-tile joint lattice | P1 gap |
| 洗石子 / 抿石子 | aggregate mix, dirt, algae at base | expansion-joint lines on the building grid | **exists** (PR #14 A2) |
| Painted concrete / plaster | weathering, mildew, repaint patches, run-off | parapet drip, band logic | **exists** (PR #14 B1–B3) |
| Exposed concrete | stain, formwork tonal variation, leaching | form-tie holes only below ~100 m (not needed in air) | **gap** — Queue A |
| Architectural stone | panel-tone variation | panel layout | **exists** (PR #14 A3) |
| Commercial glass / metal | none (reflection comes from sky/environment) | module/spandrel/mullion | exists, procedural |
| Roof waterproofing | patch/stain/puddle/gravel mask | none | **gap** — spec'd, unbuilt |
| Sheet-metal roof | fade, rust bloom, re-sheeted bays | rib/seam direction, overhang, gutters | **gap** — Queue A |
| Industrial cladding | dirt gradient, panel-tone, rust at base | panel width, rib profile, roller doors | **gap** — Queue A |

**Colour caveat [Repo]:** blue sheet-metal roofs were measured at 1–4 % in a Xinyi orthophoto sample (n = 348) against
~25 % in code. [Roofscape v2 §1.1] For factories, farmhouses and villages **no colour-share source was found**; the
palettes for those must start neutral (white/grey/beige/green-grey as in the Xinyi measurement) and be changed only
after sampling lawful orthophotos or open imagery for each land-use class.

---

## 6. Urban and mountain vegetation families

### 6.1 Species vs crown archetype

Species identification does not need to equal species count. For aerial play, what the eye separates is **crown
archetype** (silhouette + texture grain + colour value), not taxonomy. The proposal is **5–6 archetypes** that cover
the species the sources actually name, with colour/size/density variation driven by instance data.

**Botanical names below are from general knowledge [I] and must be checked against TaiBIF / Flora of Taiwan before
they are written into any shipped metadata.**

| archetype | silhouette | species it stands in for | Northern Taiwan contexts | evidence |
|---|---|---|---|---|
| **V1 Dense dome** | wide, rounded, heavy foliage | 樟樹 *Cinnamomum camphora*, 榕樹 *Ficus microcarpa*, 茄苳 *Bischofia javanica*, 楠/樟科 mix | Taipei streets, schools, parks, temples, low-elevation forest | Sec/Gov (樟, 欒 named; 榕/茄苳 appear in the NTU risk study); 樟科/殼斗科 dominance in northern secondary forest [Acad] |
| **V2 Tiered umbrella** | horizontal layers, flat crown | 小葉欖仁 (*Terminalia*, name to verify), 黑板樹 [I] | street/avenue trees | Sec (小葉欖仁 "umbrella" form; dominant in Tainan count — not Taipei) |
| **V3 Spreading vase / open crown** | open branches, seasonal colour | 臺灣欒樹 *Koelreuteria henryi* (syn. *K. elegans* subsp. *formosana*), 楓香, 阿勃勒, 台灣欒 | Taipei streets and parks; autumn bloom | Gov/Sec (欒 stated); the current shader already encodes late-September bloom [Repo] |
| **V4 Columnar / conical** | narrow, tall | 水杉, 落羽松, 木麻黃-type windbreak lines [I] | parks, ponds, coastal windbreaks | [I] — no source in this pass |
| **V5 Palm / fan** | few leaves, point-shaped head | 大王椰子, 檳榔, 蒲葵 [I] | boulevards, farms, villages | [I] |
| **V6 Bamboo plume / clump** | feathered, arching | 桂竹, 麻竹 [I] | northern hill slopes, village edges | [I] — **not supported by a source in this pass but strongly expected** |
| (canopy-only) **V7 Hillside broadleaf canopy** | no individual crowns; textured carpet | 紅楠, 相思樹, 水同木/江某, 山黃麻-類 pioneers | Wenshan-type northern lowland forest | Acad |
| (ground) **V8 Grass/scrub** | no crowns | 五節芒/白背芒, 林投 on coast | Yangmingshan grasslands, coastal | Gov (白背芒, 林投) |
| (water) **V9 Mangrove/reed** | low dense | 水筆仔 *Kandelia obovata*; reeds | Tamsui estuary | Gov/Acad |

### 6.2 What makes natural-looking trees cheap

- **Silhouette variety beats leaf realism at ≥ 150 m.** A dome vs umbrella vs vase is legible; individual leaves are not.
- **Value structure beats colour.** Lit-top / self-shadowed-underside gradient (already in `xc_foliage`) carries most of the read. [Repo]
- **Break the outline, not the surface.** A jittered low-poly crown with a few clipped leaf-cluster cards on the rim reads
  as foliage at the cost of 40–120 triangles; a full-alpha card crown costs overdraw instead of triangles. [I]
- **Shader-driven variation:** per-instance hue/value, non-uniform scale and yaw give 4–5× apparent diversity at no asset
  cost. The Xinyi trees already use yaw, scale and a 4-way colour variant. [Repo] The missing lever is *shape*, not colour.
- **Far LOD:** collapse to an opaque lobed blob or a terrain-draped canopy material; for distances beyond ~1 km, individual
  trees should disappear into a canopy surface. External sources describe impostors / billboard clouds and alpha-to-coverage
  transitions, but **none was a mobile-specific or Unreal-specific source**; engine behaviour must be measured. [Sec]
- **Overdraw is the mobile hazard, not triangles.** The only cost data in this repo is Xinyi's own: trees are HISMs with
  LOD1/2 and cull 1.5–2.6 km; near-crown removal in v0D exposed ~+7.5 ms facade cost at one view. [Repo]
  Alpha-masked leaf cards must therefore be an *opt-in* for near trees, with distance fade to opaque.

### 6.3 Evaluation of the existing Xinyi tree system [Repo]

| aspect | finding | verdict |
|---|---|---|
| Mesh | 1 mesh, 28 tris, lumps of one icosahedron with ±12 % vertex jitter, fixed ellipsoid scale (3.2 × 2.4 × 3.2) | cheap, but one silhouette repeated 16k times |
| Variation | yaw, scale 0.8–1.25, 4 colour slots (camphor/banyan dark greens, golden-rain bloom slot) | colour is covered, **shape is not** |
| Texture | none; `leafN` is a 3D value-noise term | no leaf grain; fine at 800 m, flat at 150 m |
| Placement | street (kerb + 1.8 m, 9/11 m spacing by road class) + park scatter (1 per 55 m²) + OSM-mapped; v0D reality filter | placement logic is reusable for other cities and **must be retained** |
| Forest | 5-blob clump, 100 tris, 16 m grid on slope/elevation rule | good enough as a density template; identity weak; **no species mix, no bamboo, no gap/ridge structure** |
| LOD / cull | HISM LOD1/2, cull 1.5–2.6 km | fine for Xinyi; the broader world needs a canopy surface rather than instances beyond ~1.5 km |
| Species identity | all trees "broadleaf" | at most 3–4 archetypes needed — **not** dozens of species |

**Conclusion:** keep the placement/filter code and HISM approach; replace the single blob by 4–5 archetype meshes
(shared material and atlas) and add a canopy-surface layer for forest.

---

## 7. Agriculture, water and coast requirements

### 7.1 Recognisable aerial patterns (what to build)

| pattern | what the eye reads | production | data |
|---|---|---|---|
| **Taoyuan pond field** | irregular/rounded water bodies of 20–200 m scatter between fields and housing, often with tree-lined banks and canal links | E (water polygons) + D (bank trees, edge shaping) | no agency total (§4); use OSM `natural=water`/`landuse=reservoir` and the NLSC land-use water class; **verify counts per dataset, do not assume 2,800** |
| **Irrigated paddy mosaic** | rectilinear plots, varied by planting stage (flooded sky-mirror → bright green → gold → stubble), separated by bunds and ditches | E + A (4 top-down states) + D (plot hash colouring) | NLSC land-use "rice paddy" class (Government Open Data licence on the dataset pages) |
| **Dry field / vegetable rows** | striped rows, dark soil, small plots | A + D (row direction per plot) | NLSC land-use dry-field class |
| **Greenhouse / net-house strips** | long white-silver rectangles, tunnel arches | D (instanced low-poly tunnel) + C | NLSC class / OSM `building=greenhouse` where present; *no Taoyuan/Dayuan area figure found* |
| **Field boundaries & farm roads** | thin grid lines; farm roads as pale narrow strips | D + E | OSM `highway=track`, parcel edges from land-use polygons |
| **Irrigation canals** | thin straight/curved blue-grey lines with concrete lining | D + E | OSM `waterway=canal/ditch/drain` |
| **Wetlands / mangrove** | dark green belt on river mouths | E + B + D | NLSC wetland class |
| **Rivers & banks** | wide braided channel, gravel bars, levees, flood-plain fields | E + D + A | OSM/DTM water mask; embankment line from DTM |
| **Coast** | sand beach vs rock shelf vs breakwater vs mudflat | E + A + D | OSM coastline; DTM; NLSC |

Tainan-style fish-pond mosaics, mentioned in no source here, are out of scope for the north.

### 7.2 Source availability (see §10 and §11)

NLSC land-use survey and many MOI datasets are on data.gov.tw and are marked **Open Government Data License v1.0 /
free** on the dataset pages seen; classification versions differ (2015 edition at level 2 vs 2019 edition with
level-3, 93 classes in recent results). The newest dataset exposes an XML coordinate query API. [Gov via search]
**The raw tile/ZIP downloads were not reachable from this environment** (WebFetch DNS failure for data.gov.tw), and an
earlier repository note says the TGOS DTM ZIP is blocked from GitHub-hosted runners. [Repo] Production use therefore
needs a documented offline acquisition path.

---

## 8. Port, airport and industrial assets

Public-form assets only. No operational layouts, security perimeters or military-sensitive arrangements are recorded or
recommended.

### 8.1 Ports and harbours

| module | purpose | method | notes |
|---|---|---|---|
| Quay/wharf strips along coast data | the outline that makes a port a port from altitude | E + D | derive from OSM `man_made=pier/breakwater` and land-use, not hand-drawn |
| Breakwater ring | strongest coastal silhouette; includes wave-armour texture on heads | D + A | geometry procedural, surface by A |
| Container yard | colour-block mosaic of stacked containers; row direction follows quay | D | colour packing rule + palette (no photos) |
| STS crane (2 variants) | tall repeated silhouette along the quay; only meaningful from ≥ 3 km | C | 150–400 triangles each [I]; sensible LOD to a flat card at distance |
| Gantry/rail-mounted yard crane | secondary | C | P1 |
| Ship hulls (container, bulk, general, 1–2 fishing boat types) | moving/static scale cues | C | AI image alone cannot produce these |
| Warehouse rows, tank farms | repeated rectangular roofs | D + A | shares industrial kit |
| Fishing-harbour kit | small basin, boat cluster, sheds | D + C | representative harbours: **八斗子, 龜吼** (named in Gov/Sec sources); others unconfirmed |

Source gaps: Keelung and Taipei Port **crane counts, container-terminal footprints and breakwater dimensions were not
found** in this pass. The baseline should use OSM/land-use footprints, not asserted dimensions.

### 8.2 Airports (public exterior only)

| module | purpose | method | notes |
|---|---|---|---|
| Runway/taxiway/apron strips | the most legible long-distance "airport" cue | E (OSM `aeroway`) + D (markings: centreline, thresholds, numbers, aiming points) + A (rubber/patch wear) | project already plans OSM `aeroway` as a source [Repo] |
| Terminal silhouette | identity; one per major field | C or F | Taoyuan T1/T2 exist today; T3 under construction, so choose the date to model explicitly |
| Control tower, 2–3 generic forms | tall vertical cue | C | |
| Hangar / apron-edge shed rows | repeated arched/gabled roofs | D + C | |
| Support buildings | low rectangles | D | reuse industrial kit |

Reported public runway dimensions (Taoyuan ≈ 3,660 / 3,800 m × 60 m; Songshan ≈ 2,590 m) are "[Gov/Sec], verify with
AIP/OSM before use". **Hsinchu air base: no layout detail recorded; if used, restrict to what OSM aeroway data and
unclassified, publicly visible form already show.**

### 8.3 Industry / energy

| module | method | priority |
|---|---|---|
| Long-span factory shed (low-slope gable, ridge ventilators) | C + D + A | P1 |
| Warehouse box (flat roof, loading bays on one side) | D | P1 |
| Storage tank (floating-roof cylinder, sphere) clusters | C + D | P1 |
| Smokestack (1–3 variants) with aviation-light option | C | P1 |
| Coastal power-plant block (generic: hall + stack + tank + switchyard) | D + C | P1; **form of 協和 / 大潭 not sourced** |
| Substation yard + pylon lines | D + C | P1 |

---

## 9. Mobile performance implications

All estimates below are **[I] unless marked [Repo]**; nothing was measured in this pass.

1. **Budget anchor [Repo]:** the accepted Xinyi build holds ~1 draw per tile for buildings, 9 HISMs for roof props,
   instanced trees with cull 1.5–2.6 km, a 2048² RGBA8 ground data texture and a 1024² lamp texture, and **no textures
   in the building material**. The new world must add by *layers with tight budgets* rather than new per-object textures.
2. **Region-scale ground: one data texture per land-use tile** (R: class, G: variant, B: boundary distance, A: wetness)
   plus a small texture array of top-down surfaces. This extends the existing Xinyi ground-SDF design.
3. **Instances only where silhouettes matter:** pylons, cranes, tanks, stacks, ships, tall trees. Fields, ponds, canals, road
   lines, runway markings and canopy are **textures or flat geometry**.
4. **Triangle and overdraw guidance [I]:** tree crown 30–120 tris near, 12–30 tris mid, no instance beyond the cull; cross-card
   leaf rims only on the nearest ring; no per-leaf alpha beyond 300 m.
5. **Texture memory [I]:** at ASTC 6×6 the repo already estimates ~0.5 MB for the MVP mask pack and ~2–3 MB for a fuller pack.
   World-scale additions: ~6 top-down surfaces at 512² (~1.5 MB), 1 leaf/canopy atlas at 1024² (~0.5 MB with ASTC), and
   one shoreline atlas at 512² (~0.25 MB).
6. **Streaming:** Northern Taiwan at the stated airspace (40 × 40 km playable, 80–100 km visual) needs the existing
   500 m tile ownership extended to a coarser LOD (e.g. 2.5–5 km chunks for land-use ground and far massing). The far-city
   mesh (207k tris for the Taipei basin) already shows what that costs. [Repo]
7. **Moire & shimmer:** thin canal lines, pond edges, runway markings and fence/field lines alias at 800 m on a phone.
   Use the same strategy as the Xinyi facade shader: filter every procedural pattern to its mean by pixel footprint. [Repo]
8. **Night:** the Xinyi night is emissive-only with baked light pools. Ports, airports and industrial zones need
   *palette-driven emissive lines* (apron lights, quay lamps, aviation reds) with no dynamic lights.
9. **Do not buy performance with accuracy:** nothing in this document asks to change accepted geometry, shaders or
   runtime.

---

## 10. Source links and evidence confidence

### 10.1 Source list

All were reached through a **search tool that returns summarised results**; page contents were **not individually
read** (see §10.3). Listed as "where found".

| # | topic | link | tag | confidence |
|---|---|---|---|---|
| S1 | Taoyuan ponds, count claims | https://www.bade.tycg.gov.tw/cp.aspx?n=6455 | Gov | medium (figure disagreement) |
| S2 | Ponds, history, uses | https://ir.lib.ncu.edu.tw/handle/987654321/1127 ; https://gis.rchss.sinica.edu.tw/canal/archives/841 | Acad | medium |
| S3 | Ponds, drought use (2017) | https://www.cna.com.tw/news/afe/201702100188.aspx | Sec | low–medium |
| S4 | Washed-stone / 二丁掛 vocabulary and history | https://www.pro360.com.tw/guide/brickwork_tile_external_wall ; https://www.housefeel.com.tw/article/石材-洗石子-磁磚-玻璃帷幕-外牆/ | Sec | low |
| S5 | Washed-stone craft loss | https://www.tsce.org.tw/upload/files/201601210947123565.pdf | Acad | medium |
| S6 | Sheet-metal roof materials | https://www.pro360.com.tw/guide/photoai_steel_rooftop | Sec | low |
| S7 | Rooftop add-on facade study | https://nutcir-lib.nutc.edu.tw/entities/publication/a99ff422-32b3-4a24-bce9-a04c1c0992fc | Acad | medium |
| S8 | Wenshan forest types / northern secondary forest | https://www.airitilibrary.com/Publication/Index/05781345-200706-40-2-147-164-a ; https://www.airitilibrary.com/Publication/Index/05781345-200903-42-1-1-22-a | Acad | medium |
| S9 | Sand coast vegetation zonation | https://www.forest.gov.tw/file/192322 ; https://www.forest.gov.tw/MagazineFile/5245 | Gov | medium |
| S10 | Mangrove & 水筆仔 | https://tdr.lib.ntu.edu.tw/handle/123456789/99032 ; https://tdr.lib.ntu.edu.tw/handle/123456789/75471 | Acad | medium |
| S11 | Taipei street trees | https://tdr.lib.ntu.edu.tw/handle/123456789/98216 ; https://www.bles.tp.edu.tw/uploads/1788253183433xKX1Qx5j.pdf | Acad/Sec | low–medium |
| S12 | Taipei tree list context | https://www-ws.gov.taipei/001/Upload/356/relfile/16485/117660/649c11f4-338a-46ba-8fdf-c0c270e75d9a.pdf | Gov | medium (recommendation list, not a census) |
| S13 | Tainan street-tree count (comparison only) | https://news.pts.org.tw/article/693851 | Sec | low |
| S14 | Lanyang Plain farmhouse sprawl | https://www.ettoday.net/news/20150428/499076.htm ; https://nccur.lib.nccu.edu.tw/handle/140.119/122682 | Sec/Acad | low |
| S15 | Taoyuan rice area | https://www.ctee.com.tw/news/20260723701002-431401 (and related) | Sec | low |
| S16 | NLSC land-use datasets (OGDL v1.0, free) | https://data.gov.tw/dataset/98133 ; https://data.gov.tw/dataset/98134 ; https://data.gov.tw/dataset/98135 | Gov | high for licence, medium for content |
| S17 | OGDL-Taiwan-1.0 | https://spdx.org/licenses/OGDL-Taiwan-1.0.html | Gov/SPDX | high |
| S18 | Keelung Port east/west plan | https://www.ey.gov.tw/Page/9277F759E41CCD91/3006c2be-0494-4ebc-bb5b-15b85826223f ; https://news.pts.org.tw/article/509219 | Gov/Sec | medium (dates vary) |
| S19 | Taipei Port land area | https://www.ey.gov.tw/Page/9277F759E41CCD91/bf484f12-0ae6-4a75-9926-576b8077c273 | Gov | medium |
| S20 | Taoyuan airport runways/terminals | https://www.ey.gov.tw/Page/9277F759E41CCD91/ecaa25de-b7ae-4659-b51c-9e1b46e5f9e7 ; https://www.taiwannews.com.tw/zh/news/3993159 | Gov/Sec | medium |
| S21 | Songshan runway statement | https://www.ey.gov.tw/Page/9277F759E41CCD91/13557a19-a6d4-4c51-830d-a6cf30b3b0ba ; https://data.gov.tw/dataset/30468 | Gov | low–medium |
| S22 | Taipower plants (林口 units) | https://www.taipower.com.tw/media/djnb3bbf/11405簡明月報.pdf | Gov | medium |
| S23 | 五楊高架 / 汐五高架 | https://www.cna.com.tw/Proj_GoodBook/1286.aspx ; https://ir.lib.ncu.edu.tw/retrieve/89427/index.asp | Sec/Acad | medium |
| S24 | Fishing-harbour classes / examples | https://www.moa.gov.tw/ws.php?id=2447080 ; https://www.moa.gov.tw/redirect_files.php?id=60148 | Gov | low (north harbours not enumerated) |
| S25 | Overture / OSM licensing summaries | https://overturemaps.org/?p=349 ; https://www.openstreetmap.org/user/jacobwhall/diary/406979 | Sec | low–medium (conflicting) |
| S26 | Foliage LOD / impostors | https://www.simplygon.com/features/vegetationoptimization ; https://docs.unity3d.com/speedtree-runtime-sdk/manual/level-of-detail.html | Sec | low for mobile claims |
| S27 | Repo documents | `docs/xinyi-custom-material-library-spec-v0.md`, `docs/xinyi-roofscape-v2-material-pilot.md`, `docs/xinyi-look-v1-visual-pass.md`, `docs/xinyi-taipei-street-reality-v0d.md`, `tools/lookdev/build_ground.py`, `tools/lookdev/shaders/xinyi_city.hlsl`, PR #14 | Repo | high |

### 10.2 Confidence by claim class

| claim class | confidence |
|---|---|
| What exists in the repo | **high** (read at baseline SHA) |
| OGDL v1.0 terms | **high** (SPDX + multiple reporting) |
| Pond count, history | **medium**; figures disagree, no official agency total |
| Material vocabulary / history | **low–medium**; trade and heritage-article sources |
| Species names & archetype assignment | **low–medium**; Taipei species shares **not found** |
| Port / airport dimensions | **low–medium**; each number single-sourced or press-reported |
| Mobile cost numbers | **low**; the only measured numbers are Xinyi's own; everything else [I] |

### 10.3 Source limitations (important)

- **The web tooling was constrained.** `WebFetch` could not resolve `data.gov.tw` or `www.bade.tycg.gov.tw` (DNS), so dataset
  pages and several government pages were **not read first-hand**; their content is as summarised by the search tool.
- Several sources are **contractor guides, news items and travel blogs**; they are used for vocabulary and orientation only.
- **No Taiwan-wide or Taipei-wide species share, roof-colour share, greenhouse area, port crane count or airport-apron
  layout figure was found.** None is invented here.
- Botanical names in §6 were not verified against TaiBIF / Flora of Taiwan.
- Port, airport and power-plant "visual form" sections rely on general knowledge of such facilities and **require
  lawful image or open-data review before modelling**.

---

## 11. Asset reuse and licensing concerns

The immediate game is Skyfront Homeland. The engine-independent source library should preserve optional reuse in an
RTS, a city simulator or a commercial asset pack. **That reuse is not worked on here.**

| issue | finding | action |
|---|---|---|
| **Taiwan Open Government Data License v1.0** | worldwide, non-exclusive, irrevocable, royalty-free, any purpose, derivatives allowed, **sub-licensing allowed**, **attribution notice required** (failure = deemed unlicensed), compatible with CC BY 4.0; the agency may stop providing data; warranty disclaimer. [SPDX/Gov] | Record per-dataset licence and the exact "顯名聲明" attribution string in the build manifest. **Check that each dataset page actually specifies OGDL v1.0 — some agencies specify other terms.** |
| **Not everything on data.gov.tw is OGDL v1.0** | dataset pages list licence individually | per-dataset licence field, never assumed |
| **Overture / OSM** | OSM is ODbL; Overture's themes derived from OSM may be ODbL, others CDLA-Permissive; reporting conflicts [Sec] | read the Overture release's own licence file; ODbL **share-alike on derived databases** can constrain redistributing a *processed vector dataset*, even if rendered images are fine. Confirm with counsel before any pack that ships geometry derived from OSM |
| **Copernicus / DTM mirror** | project already uses a derivative mirror of MOI DTM and Copernicus prototypes [Repo] | pin source licence and whether the mirror is a permitted redistribution; **do not ship raw DTM tiles inside a sold pack** |
| **TGOS/NLSC base maps** | WMTS rasters are *pictures, not data* and already marked DO_NOT_REUSE for geometry [Repo] | never rasterise-and-trace |
| **AI-generated sources** | PR #14 records that the model ID/seed were not exposed, that training provenance is not certified and licence uniqueness is not independently certified [PR #14] | for each AI source keep: prompt, tool, date, generation count, rejects, SHA-256, human edits. Treat as "usable but provenance-limited"; do not sell them as exclusive |
| **Original model/source preservation** | Image generation produces PNG only | preserve `.blend` sources, texture masters (16-bit where possible), generation logs, and engine-agnostic exports (glTF + KTX2) alongside engine copies |
| **Real-world landmarks (hero)** | 101, 國父紀念館, airport terminals are protected by architecture/trade-dress claims in some jurisdictions [I] | label as "inspired by", avoid logos and signage; get a legal read before commercial packs |
| **Brands & signage** | storefront/convenience-store logos | the wall-ad pipeline already uses invented names [Repo]; keep that rule |
| **Reference imagery** | none committed here | keep reference captures out of git; store only URL + date + sampled statistics |
| **Redistribution of the pack** | the data and the art have different licences | separate "art" (own copyright) from "derived data" (licence-bound) in the pack structure |

---

## 12. Recommended production order

1. **E-1 Land-use + terrain backbone** (rank 1, 4, 5, 6): decide the data stack, pin versions, produce the class texture for
   one northern-Taiwan test window (Taoyuan Plateau scale, ~10 km). Gate: a flight-camera fly-over at 300/600/800 m reads as
   farmland with ponds.
2. **Vegetation pilot (Queue B)** in parallel; it is the cheapest and most visible global win.
3. **Materials batch 2 (Queue A)** after PR #14's art review resolves — A-class surfaces for non-Xinyi worlds.
4. **Rural/suburban kit** (rank 7–8) so the farmland is not empty.
5. **Port, airport, industry modules (Queue C)** — silhouettes that identify regions from kilometres.
6. **Bridges, elevated roads, pylons** (rank 11, 14) — linework and big vertical cues.
7. **P1 detail**: rivers/wetland, fishing harbours, retaining walls, power-plant forms.
8. **P2 detail**: utility poles, drainage details, secondary markings.

Cross-cutting rules:
- Each stage ends with a **3-distance review (150 / 300 / 600 / 800 m)** and one long-range (3–8 km) silhouette check.
- Nothing replaces accepted Xinyi geometry; new content enters as new layers.
- Every A/B-class asset gets a provenance record (§11).

---

# Queues

Every item lists: **name · purpose · visual requirement · production method · expected aerial importance · existing
equivalent · acceptance criteria**. These are *specifications*; **no generation has been requested**.

Common acceptance for all A/B images: native resolution recorded; neutral greyscale (A) unless stated; seamless-tile
check at 3 × 3; no baked windows/doors/floor lines/lighting; no text, logos or people; SHA-256 + prompt logged; stated
mean-value stability at 1/8 scale; no claim of engine readiness.

## QUEUE A — Codex ImageGen Batch 2 (8 original material sources)

| # | name | purpose | visual requirement | method | aerial importance | existing equivalent | acceptance |
|---|---|---|---|---|---|---|---|
| A-01 | `roof_membrane_wear` | non-Xinyi flat roofs: waterproof membrane/concrete deck, patches, puddle stains, gravel scatter | greyscale RGBA-packable planes: patchy membrane (R), repaint zones (G), drainage/rust stain (B), 0.5–1 m scatter (A); features 1–8 m, no seams, no parapet | A | high (roofs dominate oblique views) | `T_XinyiRoofSurface` spec (unbuilt); none in PR #14 | 3×3 tile has no obvious repeat at 100 %; coverage of dark patches ≤ 25 %; mean stable at 1/8 scale |
| A-02 | `sheet_roof_wear` | corrugated/standing-seam metal roofs on farm, factory, village, 頂樓加蓋 | fading, rust bloom, re-sheeted bays, dirt gradient; **no ribs, seams or colour** (ribs procedural); wear aligned to one axis so rotation by seam direction works | A + D | high | Roofscape v2 sheet covers (Xinyi, procedural, no wear art) | no embedded rib pattern; wear runs along single axis; usable at 90° rotation |
| A-03 | `tile_colour_field_erding` | 二丁掛 / 小口磚 / mosaic colour-field patchiness | broad 3–10 m variation in value (tile-lot differences, replaced courses, fading); **no grout lines**, no grid | A + D (joints) | high | PR #14 A1 `ceramic surface` (continuous, no joints) | distinct from A1: wider tonal range and larger patch size; no joint-like linework when autocorrelated |
| A-04 | `exposed_concrete_stain` | bridge piers, retaining walls, industrial plinths, port quays | greyscale leaching streaks, form-board tonal bands (optional), repair patches, damp base; vertical orientation fixed | A | medium–high | none (PR #14 B1/B3 are plaster-oriented) | vertical streak direction preserved; no rebar, text or form-tie holes; repeat-safe at 512² |
| A-05 | `cladding_wear_industrial` | profiled-metal factory/warehouse walls | rust at base, dirt-fade gradient, panel-tone variation, oxidised patches; **no rib profile** | A + D | medium–high | none | no baked panel seams; gradient axis vertical; usable on 6–12 m panel widths |
| A-06 | `pavement_apron_wear` | runway/apron/container yard/highway surfaces | tyre-rubber streaks, oil spots, patched cracks, fine aggregate; **no painted markings** (procedural) | A + D | high (airfield, port, freeway) | road SDF has no surface texture [Repo] | no linear features that can be mistaken for markings; mean stable at 1/16 scale |
| A-07 | `field_paddy_states_topdown` | irrigated rice plots: 4 states (flooded, early green, mature gold, stubble) | stylised, top-down, 4 colour-ready value+hue variants; no bunds, roads, buildings, shadows | A | very high | none | four states distinct in value **and** hue; plot-hash can blend any two without visible seam |
| A-08 | `shore_materials_set` | sand, rock shelf, riprap/armour rubble, tidal mud | four top-down surfaces; non-photographic; no foam, no water | A | high (coast silhouette) | none | each tile independently seamless; rubble scale 0.5–2 m; mud shows silt ripple at 5–20 m only |

Notes: items A-02, A-03, A-05 and A-06 deliberately exclude geometric elements (ribs, joints, panels, markings) per
the handoff's surface-vs-geometry rule. Prompt wording must forbid brand marks and text. **Blue-sheet palette is not part
of this queue** (see §5).

## QUEUE B — Vegetation pilot (minimal, measured)

Goal: prove that **5 crown archetypes + 1 leaf atlas + shader variation** read as Northern Taiwan from 150–800 m, at a
triangle/overdraw cost no higher than today's tree on the target mobile baseline.

| # | item | purpose | visual requirement | method | aerial importance | existing equivalent | acceptance |
|---|---|---|---|---|---|---|---|
| B-01 | `crown_dome` (V1) | street/school/park/temple dominant tree | wide rounded crown, dense interior, 40–120 tris, 3 LODs (hero 120, mid 40, far 12–20) | C + D | very high | `SM_XinyiTree` | silhouette differs from existing blob at 150 m; ≤ 120 tris at LOD0; stable at LOD handoff |
| B-02 | `crown_tiered` (V2) | avenue tree | layered horizontal tiers, flat top | C + D | high | none | tier structure readable at 300 m |
| B-03 | `crown_vase` (V3) | 台灣欒樹-type seasonal tree | open crown, visible branch fan, seasonal tint via variant | C + B + D | high | `xc_foliage` bloom slot | bloom variant readable at 600 m; open crown not mistaken for B-01 |
| B-04 | `crown_column` (V4) | windbreak, pond-bank, park conifer | narrow tall | C + D | medium | none | row of 10 reads as windbreak line at 800 m |
| B-05 | `crown_palm` (V5) | boulevard/farm accent | 6–10 fronds, head sphere only at far LOD | C | low–medium | none | optional for first pilot |
| B-06 | `leaf_atlas_broadleaf` | shared leaf-cluster atlas for the nearest ring + canopy surfaces | 8 cells: leaf clusters (broad / compound / elongated), 1 trunk/bark strip, 1 fine-twig card; alpha-cutout friendly; no stems longer than 20 % of cell | B | high | none (shader noise only) | alpha-coverage consistent across mips; no halo at edge; ≤ 1024²; ≤ 8 cells |
| B-07 | `canopy_surface_hill` | terrain-draped forest canopy for hills, replaces instances beyond ~1 km | greyscale+green canopy-grain, lobed 15–40 m structure, shaded gaps, mix of dome and bamboo plume | B + E | very high | `SM_XinyiForestClump` (Xinyi only) | seamless; no straight lines; mean stable at 1/16 scale |
| B-08 | `bamboo_clump` (V6) | northern hill village-edge accent | arching feather crown | C + B | medium | none | readable at 300 m; uses B-06 or a 2-cell variant |
| B-09 | `placement_rules_v1` | **retain** street/park/OSM-tree logic from `build_ground.py`; add archetype selection by land-use class and road type; add forest density by slope/elevation/aspect | D + E | very high | existing `build_ground.py` rules | tree counts per class reproducible from pinned inputs; v0D filter preserved |

**Pilot plan (all [I], to be measured):**
1. Build B-01, B-02, B-03, B-04, B-06, B-07 only (5–6 assets).
2. Render a locked 150/300/600/800 m camera set in the existing preview (`tools/lookdev/preview`) vs the baseline tree. Compare:
   silhouette diversity (human review), apparent repetition, draw-call delta, triangle delta, and overdraw (GPU capture
   on a real iPhone-class device if available).
3. LOD rule: LOD0 ≤ 120 tris, LOD1 ≤ 40, LOD2 ≤ 12–20, then **disappear into canopy surface** (B-07) or land-use
   ground; alpha-masked rim cards only on LOD0.
4. Reject criteria: any alpha card cluster that raises frame time more than the baseline by a threshold the team sets
   before testing; any silhouette indistinguishable from the old blob at 300 m.
5. Output: a 2-page result doc and a go/no-go for scaling to all of Northern Taiwan.

## QUEUE C — World asset modules (first reusable 3D / procedural modules)

| # | module | purpose | visual requirement | method | aerial importance | existing equivalent | acceptance |
|---|---|---|---|---|---|---|---|
| C-01 | `landuse_ground_v0` | classify land into paddy / dry / forest / scrub / built / water / sand / mud for a ~10 km Taoyuan Plateau test window | class texture + variant channel + boundary distance; filtered; per-class surface lookup from Queue A | E + D | very high | Xinyi ground data texture (OSM SDF) | fly-over shows farmland, ponds, towns and hills as distinct regions; data inputs pinned with licence and attribution |
| C-02 | `pond_scatter_v0` | Taoyuan irrigation-pond look | water polygons with irregular banks, tree-lined edges via B-01/B-04, canal links | E + D | high | none | density visibly differs from other regions; no assumption of 2,800 total |
| C-03 | `field_canal_road_v0` | field mosaics, bunds, farm roads, canals | plot hash colour, row direction, thin-line filtering | D + E | high | none | no shimmer at 800 m; plot edges stable under motion |
| C-04 | `rural_house_kit_v0` | 3–5 storey 透天厝/農舍, shed, pump house, yard, 2–3 roof types | 6–10 modules, ≤ 200 tris each, roof palettes **sampled** not assumed | C + D + A | high | none (Xinyi buildings are dense-lot only) | village reads as non-Xinyi at 300 m; palette review against sampled orthophotos |
| C-05 | `greenhouse_strip_v0` | long greenhouse rows | tunnel-arch repeat, white/silver translucency baked as opaque colour | D + C | medium | none | row direction follows field; ≤ 24 tris per bay |
| C-06 | `port_kit_v0` | quay, breakwater, container yard, STS cranes (2), ships (2–3) for **Keelung** and **Taipei Port** | footprint from OSM/land-use; crane 150–400 tris; container stacks as colour-block rule | E + D + C | high | none | port identifiable at 3–8 km; crane silhouettes visible at ≥ 3 km; no unlabeled real-facility dimensions asserted |
| C-07 | `fishing_harbour_kit_v0` | basin, boat cluster, sheds | 2 boat hulls, 6–12 instances per harbour | D + C | medium | none | harbour reads from 800 m; shape comes from data, not hand edits |
| C-08 | `airfield_kit_v0` | runway/taxiway/apron/terminal/tower/hangar rows for Taoyuan, Songshan and a generic field | OSM `aeroway` → strips; marking generator; terminal as F/C hero | E + D + C + F | high | planned in `docs/architecture.md`, not built | markings legible at 300 m and fade cleanly at 800 m; **no security/operational layout** |
| C-09 | `industrial_kit_v0` | factory shed, warehouse, tank, stack | 6–8 modules; palette neutral-first | C + D + A | high | rooftop tanks only | industrial zone reads from land-use + kit |
| C-10 | `elevated_road_kit_v0` | deck + pier modular set, river bridge, overpass | 3 deck widths, 2 pier types, parapet; ≥ 40 m pier option | C + D + E | high | skipped in `build_ground.py` | elevation read from 3 km; avoids breaking the existing road SDF |
| C-11 | `pylon_line_v0` | lattice pylons spaced along data | 1 lattice type, 2 heights; line linework | D + C | medium | none | line visible at 3 km; ≤ 120 tris per pylon |
| C-12 | `retaining_wall_slope_v0` | hill-road and housing-edge walls | procedural wall bands using A-04 | D + A | medium | none | follows DTM slope; no per-building exceptions |

Common rule for all of Queue C: **no changes to accepted Xinyi geometry, shaders or runtime**; every module is a new
layer with its own manifest and licence record, and ends with a four-distance review.

---

*Document status: v0 research only. Awaiting review. No generation, modelling, Unreal execution or runtime change has been
performed.*
