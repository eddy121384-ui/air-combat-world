# Xinyi — Taipei Street Reality Audit (read-only research / art direction)

Status: **accepted research / art-direction document; no implementation yet.** No code, asset, Unreal or tile change was
made. Written on branch `feat/opus55-xinyi-visual-quality` on top of HEAD `f360685` (Phase B street props). The v0C / v0D
cut line in the final section is unchanged.

Inputs read: `docs/xinyi-street-facade-identity-v0a.md`, `docs/xinyi-street-facade-identity-v0b.md`,
`docs/xinyi-urban-identity-engineering-plan.md`; evidence sheets `unreal/Saved/XinyiLook/evidence/street_v0b/sheets/fin_*`
and `frontage_v0a/sheets/fin_midhigh_day.png`; shader `tools/lookdev/shaders/xinyi_city.hlsl` (`xc_wall` sign band,
`xc_ground`); `tools/lookdev/build_ground.py` (road paint); the locked OSM cache `data/lookdev_cache/osm_xinyi_context.json.gz`
(tag inventory measured in this pass). External sources are listed in §15 and were used as **reference only**: no image,
logo or trade dress was downloaded or copied.

Evidence labels used throughout:

| label | meaning |
|---|---|
| **[O]** | observed from a cited reference (§15); the reference says so, including numbers quoted from it |
| **[O-gk]** | general knowledge of Taipei street imagery, **not pinned to any cited source — treat as UNCONFIRMED** until checked against Mapillary / Commons / site photos before any number or colour is tuned |
| **[R]** | derived from existing Xinyi data / repo: code, locked OSM cache measurements, renders and evidence sheets |
| **[I]** | inferred design rule or estimate (reasoning from the above; not a fact) |
| **[P]** | implementation recommendation / proposed game abstraction |
| **UNVERIFIED** | plausible but not confirmed by a source in this pass |

### Evidence classification (how to read this document)

| class | tags | where it applies |
|---|---|---|
| Observed from references | **[O]** | national / Taipei counts (scooters, stalls, stores, YouBike, transformers); painted-walkway colour, ≥ 1.5 m width and 「人行道」 text; stall width 1–1.5 m; 1999 policy and its 2.0 revision; two-stage left-turn rule; high-pressure paver specification; brick-red = bike lane |
| Derived from existing Xinyi data | **[R]** | the scooter-blob, pseudo-glyph, sidewalk-everywhere and red-kerb defects (code); OSM cache inventory (77.7 km alleys, 65.6 km residential, 58.8 km mapped sidewalks, 71 `sidewalk=no`, 676 crossings / 16 diagonal, 2.4 km busway); Phase A/B behaviour and costs |
| Implementation recommendations | **[P]** + **[I]** | every "Proposed", palette value, density, cull distance, instance / triangle / ms estimate, and the v0C–v0F sequence. Estimates are not measurements |
| Still unconfirmed | **[O-gk]**, **UNVERIFIED** | see the list below. Do not use as fact |

Known unconfirmed or weakly sourced items (not upgraded to facts anywhere in this document):

* that most Taipei lanes / alleys (巷 / 弄) have no raised sidewalk, and the share of streets using painted walkways;
* the typical convenience-store frontage (6–12 m), fascia and interior-lighting grammar, and "usually on corners";
* open-front breakfast / food shop grammar and night lighting; "Taipei's street level is the brightest layer at night";
* contextual red / yellow kerb practice and white stall-row layout; scooter colour mix;
* dimensions of 機車待轉區 boxes; where walkway edge lines are white;
* the Xinyi underground-wiring rate; litter-bin and parking-meter practice; post-box and signal-mast look;
* local counts of convenience stores, YouBike stations, stalls and temples inside the WFS area (all estimates);
* the citywide stall count: sources gave about 230 k and about 282 k; 282 k is used for scale only;
* specific school-route (通學步道) walkway locations: the density boost near campuses is a design rule, not a claim.

The Chang & Marshall (2025) Da-an interface-type paper was cited from its abstract only; its PDF could not be parsed.

Distance bands (as requested): **VERY LOW** 0–50 m · **LOW** 50–200 m · **MID** 200 m–1 km · **HIGH** > 1 km.
Pixel sizes below assume 1080p and a 60° vertical FOV ⇒ ≈ **935 / d px per metre** (d in m): 18.7 px/m at 50 m, 9.4 at
100 m, 4.7 at 200 m, 1.9 at 500 m, 0.94 at 1 km.

---

## 0. Answer to the core question — why it reads "generic East Asian", not Taipei

The Phase A/B layers added the things Taipei **shares** with Hong Kong, Guangzhou, old Seoul and Tokyo side streets:
vertical blade signs, AC condensers, iron window cages, awnings. Those are necessary but not distinguishing. Meanwhile
the scene is **missing every signal that is specific to Taiwan**, and two current elements actively point elsewhere:

1. **The most Taiwanese object on any street — the parked scooter — is absent as an object.** Taiwan has ~14.7 M
   registered scooters, 62.7 per 100 people [O]; Taipei alone 921 k [O] and ~282 k on-street scooter stalls [O]. Our
   streets are empty asphalt with a confetti strip (see 2.).
2. **The "colourful sidewalk" is a mistake, and it's literally the scooters.** `xc_ground` paints "parked scooters" as
   0.75 m hash cells in white / black / grey / red / blue / yellow on a 0.45–2.3 m sidewalk band [R]. At street angles
   that reads as a harlequin mosaic (see `fin_zoom_day.png`). It also puts the scooters on the **sidewalk**, which
   Taipei has policed away since 1999 ("機車退出騎樓、人行道", now "2.0": stalls go into road-edge bays) [O].
3. **The horizontal storefront sign band reads as Hangul.** The near-range pseudo-lettering is a 2 × 3 grid of random
   on/off stroke cells per character box [R `xc_wall` L537-549]; that grid produces ㄱ ㄴ ㅂ ㅁ-like shapes. Next
   to real Traditional-Chinese blade signs, the wide boards say "Korea" (clearest in `fr_corner_b`).
4. **Every street gets the same cross-section**: a 3.5–5 m raised paved sidewalk + kerb on all roads with class ≥ 0.2,
   which includes OSM `service` (alleys) [R `walk = step(0.2, cls)`]. In the cache that is 77.7 km of `service=alley` +
   65.6 km `residential` [R] — ~60 % of the street network by length — that in Taipei is mostly **asphalt running
   to the building line or arcade, with no raised sidewalk** [UNCONFIRMED: O-gk; painted lanes exist as an official measure for
   streets without sidewalks, O, but the share of such streets is not established].
5. **The night street level is dark.** Taipei's night street is lit mainly by its ground floors: white LED shop
   interiors, open-front food shops and a convenience store every few hundred metres [O-gk; density O]. Our shop
   interiors are 0.07–0.15 albedo, faintly lit [R]; v0B already records the lowest band as "slightly darker than HEAD".
6. Taiwan-specific **road grammar is thin**: we have zebras, double yellow centrelines, red kerb lines and 機車停等區
   waiting boxes (good, Taiwan-correct) [R], but no white scooter stall rows, no 機車待轉區 two-stage left-turn
   boxes, no green painted pedestrian lanes, no contextual red/yellow kerb use.

Fix 2 and 3 (wrong), then add 1 (scooters + their stalls), then 5 (convenience-store / lit-shop night). These four
changes are what turns "an East Asian city" into "Taipei", and all four are cheap at aircraft distances.

---

## 1. Top 10 missing Taipei street signals

Ranked by (identity strength × perceived at game distances) ÷ cost. "Value" columns: ●●● strong, ●● useful, ● marginal,
— invisible.

| # | signal | basis | VERY LOW | LOW | MID | HIGH | cost class |
|---|---|---|---|---|---|---|---|
| 1 | **Parked scooter rows** in white-painted road-edge stalls, in front of shops, lanes and arcades | [O] 62.7/100 people; 282 k Taipei stalls; stalls 1–1.5 m wide | ●●● | ●●● | ● (as a dark textured kerb band) | — | 1 HISM + paint |
| 2 | **Convenience-store glow** at corners: wide glazed bay, white fascia band, uniformly bright cool-white interior, 24 h | [O] ~13.7 k stores, 1 per ~1,700 people (2023); [O-gk] spatial grammar | ●●● | ●●● | ●● night (emissive 8 m bay ≈ 7 px at 1 km) | ● night | shader + placement |
| 3 | **Bright open ground floors at night** (food shops with roller shutter up, fluorescent / LED white), mixed with shutter-down closed bays | [O-gk] | ●●● | ●●● | ●● night | ● night | shader only |
| 4 | **Real Traditional-Chinese horizontal shop boards** (replacing the Hangul-like pseudo-glyphs) | [R] defect; [O-gk] horizontal L→R TC boards | ●●● | ●● | — (colour only) | — | atlas + shader |
| 5 | **Correct street cross-section**: lanes/alleys without raised sidewalks; grey municipal pavers only where sidewalks exist | [O] painted-lane policy; [R] OSM has 58.8 km mapped `footway=sidewalk`, 71 `sidewalk=no` | ●● | ●●● | ●● (street widths/rhythm) | ● | ground shader + class flag |
| 6 | **Green painted pedestrian lanes** (標線型人行道) on narrow streets | [O] green per regulation, ≥ 1.5 m, "人行道" text at entries; Taipei adds ~9 km/yr | ●● | ●●● | ●● (green threads in grey) | — | paint geometry |
| 7 | **機車待轉區 two-stage left-turn boxes** at signalised arterial junctions (+ the existing 停等區) | [O] legal mechanism and marking exist | ●● | ●●● | ● | — | paint geometry |
| 8 | **Contextual kerb paint**: red (no stopping) concentrated at junctions / bus stops, yellow stretches, white stall rows mid-block | [O-gk]; [R] currently red on 2/3 of roads end-to-end | ● | ●● | ● | — | paint rule change |
| 9 | **Real crossings incl. diagonal scramble crossings + median bus lanes** from data | [R] cache: 676 crossing ways (16 `crossing=diagonal`), 2.4 km `highway=busway` — currently unused | ●● | ●●● | ●● | ● | paint geometry |
| 10 | **YouBike dock rows** (white/yellow 2.0 bikes) | [O] Taipei ~1,633–1,708 stations, ~23.9 k bikes | ●● | ● | — | — | 1 HISM, data-driven |

Deliberately **not** in the top 10 (see §9): utility poles / wires, litter bins, hydrants, parking meters, bollards.

Outside street scope but worth a later note: neighbourhood temples (red/orange curved roofs) and night markets are
strong Taiwan reads from LOW/MID; check the OSM bbox for `amenity=place_of_worship` + `religion=taoist` and
`amenity=marketplace` before any future pass. UNVERIFIED which exist inside the WFS area.

---

## 2. Current elements that look actively wrong

| # | element | where [R] | why it's wrong | severity |
|---|---|---|---|---|
| W1 | Harlequin "scooter" confetti on sidewalks | `xc_ground`: `scooterZone`, `xc_pick6` over 0.75 m cells, all roads except arterials | Saturated multicolour diamonds at oblique view; reads as decorative tile / toy. Also places scooters on the sidewalk (contrary to Taipei policy) [O] | **high** — dominant ground feature in every LOW street shot |
| W2 | Hangul-like pseudo-lettering on horizontal shop boards | `xc_wall` L537–549 (`stroke` 2 × 3 cells) | Makes the most legible text surface in the frame look Korean, right next to real TC blade signs | **high** — wrong-country signal |
| W3 | Raised 3.5–5 m paved sidewalk + kerb on every road incl. alleys | `walk = step(0.22, sd) … step(0.2, cls)`; `service` cls = 0.2 | Taipei 巷/弄 mostly have none; every street gets the same new-town section | **medium-high** |
| W4 | Brick-red paver variant (0.31, 0.25, 0.22) in 60 m cells | `paverR` | Muted, but brick-red ground in Taiwan is the regulation colour for **bicycle lanes** [O]; adds hue where Taipei sidewalks read grey | medium |
| W5 | Continuous red kerb line on 2/3 of non-arterial roads, regardless of context | `build_ground.py` `(w["id"] % 3) != 0` | Real use is contextual (junction approaches, bus stops, hydrants, no-stopping stretches) and mid-block curbs are often stall rows [O-gk] | low-medium |
| W6 | Dark ground floor at night | `shop` 0.07–0.15, faint glow | Taipei's street level is the brightest layer at night [O-gk] | medium (night only) |
| W7 | Heuristic zebras/stop lines at every OSM junction | `build_ground.py` crossings loop | Real crossing geometry (676 ways, incl. diagonal) is already in the cache and unused; some junctions get zebras that don't exist | low |

Not wrong, but generic (outside this audit's scope): flat large window panels on mid-rise walls; empty roads (traffic is
a gameplay / simulation decision, not an art fix — do not add static parked cars on carriageways to compensate).

---

## 3. What already works (keep)

* **Vertical TC blade signs** (v0B) — the strongest Taipei-ish read at LOW; overlapping boards along 莊敬路 are
  convincing. Night: ~half lit, no neon wash — correct restraint.
* **Frontage-aware ground floors** (v0A): rear walls quiet, corners keep both faces. This is the correct foundation for
  every proposal below (stores, scooters and stalls should all key off `frontage_roles.json`).
* **AC stacks, iron window cages, rooftop tin additions, water tanks** — Taiwan/HK-specific, survive to MID.
* **Awnings** (雨遮) — correct, restrained palette; read as a line from 50 m+ (fine).
* **Road paint**: double-yellow centrelines, zebras, stop lines, **機車停等區** boxes — Taiwan-correct vocabulary.
* **School/campus layer**, Taipei 101 hero and MID/HIGH roofscape — untouched by this audit; MID/HIGH already reads well.

---

## 4. Sidewalk / ground correction recommendation

### Observed
* Taipei municipal sidewalks are built from **high-pressure interlocking concrete pavers** (高壓混凝土地磚) under city
  specifications 02778/02779/02781 [O]; ~196 k m² were permeable paving by mid-2022 [O]. Tone in public imagery:
  mid/warm grey, beige-grey, some charcoal banding; **low saturation** [O-gk].
* **Yellow tactile strips** (導盲磚) at kerb ramps / crossings — the only saturated accent on most sidewalks [O-gk].
* Arcade (騎樓) floors are owner-built and mismatched (ceramic, granite-look, terrazzo/抿石子, quarry tile), with level
  steps; Taipei runs 騎樓整平 levelling programmes [O]. **But** in this project the arcade is painted on the wall —
  the arcade floor lies inside the building footprint and is **never visible** from the air [R/I]. So the ground needs
  no arcade-floor colour at all.
* Many streets have **no raised sidewalk**: pedestrians share the asphalt edge, or walk a painted green lane [O].
* Sidewalk height jumps (up to ~40 cm for flood reasons) and obstructions (utility boxes, recycling, lamp posts) are
  common complaints [O] — sub-pixel beyond VERY LOW; ignore.

### Inferred rules [I]
1. **Sidewalk presence is data-driven first**: a road side gets a raised sidewalk if a mapped `footway=sidewalk` runs
   parallel within ~8 m (58.8 km mapped in the cache) or the road is tagged `sidewalk=both/left/right`; **no**
   sidewalk if `sidewalk=no` (71 ways) or the road is `service` / `residential`/`unclassified` < 10 m wide;
   otherwise (unmapped tertiary+) default to a sidewalk. No per-street exceptions.
2. Where there is no sidewalk, asphalt runs to the building line (the arcade edge), with optional green lane (§5) or
   scooter stall row (§7) at the edge — mutually exclusive per curb segment.
3. **Palette = value variation, not hue variation.**

### Proposed [P] (linear albedo, sit beside existing values; tune in look-dev)

| surface | base | variation | notes |
|---|---|---|---|
| municipal paver | (0.29, 0.285, 0.275) | ±7 % value per ~40–60 m stretch; second variant beige-grey (0.31, 0.30, 0.28); **no red** | keep the existing 0.3 m joint lines (`xc_detail`-gated) |
| charcoal banding (optional) | (0.20, 0.20, 0.20) | 0.3 m bands every 6–10 m | only on arterials; adds municipal rhythm at LOW |
| older concrete sidewalk | (0.32, 0.32, 0.31) | stains −10 % low-freq | where no paver signal (unmapped) |
| tactile strip | (0.42, 0.34, 0.06) | — | 0.6 m strip at crossing ramps only, `xc_detail`-gated |
| kerb | keep (0.55, 0.55, 0.53) | — | red/yellow paint stays geometry |
| lane edge asphalt (no sidewalk) | existing asphalt, +5 % value, more patching | — | old lanes look patched / lighter than arterials |

**Remove entirely**: the shader scooter blobs (`scooterZone` / `hasScooter` / `scooterCol`). Replace by real stall
paint + instanced scooters (§7). Far-field substitute: none needed — the stall rows' paint (white outlines over a
slightly darker oil-stained fill) already averages to a darker kerb band at MID.

---

## 5. Green pedestrian-lane recommendation (標線型人行道)

### Observed
* Colour: **green** for coloured painted pedestrian walkways under the national marking rules; brick-red is for bike
  lanes [O]. (Taichung has a documented green-walkway vs green-bike-space conflict [O]; irrelevant for Xinyi.)
* Width: **≥ 1.5 m**, aiming for ≥ 0.9 m clear passage (都市人本交通道路規劃設計手冊) [O].
* Marking: white **「人行道」** text at the walkway start and at junction entries [O]. A white solid edge line on the
  carriageway side is the common form in imagery [O-gk — verify per street before tuning].
* Extent: deliberately expanding but **not universal** — Taipei planned ~9 km new/improved in one year, and the
  existing stock is described as **fragmented, poorly connected to raised sidewalks**, often obstructed [O].

### Rules [I] → abstraction [P]
| item | proposal |
|---|---|
| eligible streets | road sides with **no** raised sidewalk (§4 rule 1): `residential` / `unclassified` / `service=alley` with computed width ≥ 6 m. Never `driveway`, `parking_aisle`, tertiary+ |
| coverage | deterministic by road id hash: ~30 % of eligible length, boosted to ~70 % within 300 m of a campus polygon (school routes, 通學步道 — UNVERIFIED for specific Xinyi streets; it's a rule, not a claim about a street) |
| geometry | 1.5 m band on the road edge adjacent to the kerb / building line, as **paint geometry in `XinyiRoadPaint`** (same opaque mesh, 6 cm drape, same wear noise as `xc_paint`) |
| colour | fresh ≈ sRGB (70, 135, 90); weathered toward (85, 115, 92) by the existing wear noise; matte. Must read as **dull municipal green**, not neon or court green |
| edge | white solid 0.12 m line on the carriageway side |
| segmentation | broken at junction kerb returns (reuse `jclip`), at `service=driveway` endpoints, and wherever a stall row claims the curb; min segment 12 m |
| text | 「人行道」 at each segment start: VERY LOW / LOW only — defer to the road-text pass (§10), not v0C |
| LOD | no cull (paint is cheap); at MID the 1.5 m band (≈ 7 px at 200 m, 1.4 px at 1 km) averages into a green-grey thread — correct. Watch for thin-polygon shimmer at MID; same risk as existing lane lines |

---

## 6. Taiwan convenience-store archetype proposal

### Observed
* Density: ~13.7 k stores in Taiwan (2023), ~1 per 1,700 people; among the highest densities in the world [O]. Two
  chains dominate (≈ 7.1 k + 4.3 k stores) [O].
* Spatial grammar [O-gk]: ground floor of a 4–12-storey mixed-use building, **very often on a corner**; frontage
  roughly 1–2 shophouse bays (≈ 6–12 m); **full-height glazing** with an automatic sliding door; a continuous
  **horizontal fascia band** above the glazing with a white or light base and coloured horizontal stripes; interior
  **uniformly bright, cool-white**, visible at all hours; window counter seating; posters taped to glass; scooters
  clustered outside; under arcade buildings the store sits behind the 騎樓 piers with the fascia at arcade top.
* The chains' stripe colour combinations and logos are **trade dress / trademarks** — do not reproduce [policy].

### Proposal [P] — a generic **便利商店 archetype**
| aspect | proposal |
|---|---|
| placement | prefer **real positions** of OSM `shop=convenience` nodes (new locked snapshot like `fetch_education_context.py`; use position only, discard brand; ODbL notice). Fallback rule: commercial corner units (role 7/6 + metadata corner), ≥ 180 m apart, target ~1 per 300–400 m of commercial frontage ⇒ ~50–90 in the WFS area (estimate from population × national ratio; UNVERIFIED locally) |
| facade (shader, `xc_wall` ground floor) | 1–2 bays forced to **glazed shopfront**; interior colour near-white (0.75–0.85) with shelf-row darkening stripes at VERY LOW; door bay |
| fascia | 0.9–1.1 m band at arcade top: white base + **one** stripe from a small generic palette (teal, deep blue, warm red, green) — single-stripe rule keeps it away from any chain's multi-stripe livery. Optional generic text cell 「便利商店」/ original name from the atlas blacklist pipeline |
| night | emissive interior **above** every other shop (≈ 2× v0A shop glow) + fascia lit; spill onto the kerb via the existing ground `spill` term. This is the single strongest MID-range night signal: an 8 × 3 m lit bay is ≈ 7 × 3 px at 1 km |
| associated | scooter cluster priority in front (§7); no props needed (ATM / posters are interior, sub-pixel) |
| cost | shader branch on known commercial walls (per-building coherent) + a placement table; 0–1 new HISM |

---

## 7. Food / breakfast / small-shop grammar

### Observed [O-gk]
* Unit width ≈ one shophouse bay, **~4–6 m**; arcade 騎樓 in front on older stock.
* 早餐店 / 小吃 / 麵店 / 便當: **open front** (rolling shutter fully up, no glazing), stainless prep counter / griddle at
  the arcade line, menu boards (long white/yellow/red text lists) above the opening, plastic stools, cool fluorescent/LED
  light; many breakfast shops close by early afternoon (shutter down), dinner shops open at night.
* 飲料 (drink stands): narrow (2–4 m), very bright, saturated light-box menus, often counter-only.
* Pharmacies / clinics: glazed, bright, big single-character signs (藥 / 醫) — already in the blade atlas [R].
* Hardware / repair / scooter repair: deep open bays, goods spilling into the arcade, darker interiors.
* Hair salons: glazed, rotating pole outside (sub-pixel beyond VERY LOW).
* Exhaust ducts: steel ducts up rear/side walls — VERY LOW only.

### What survives at game distances [I]
| trait | VERY LOW | LOW | MID |
|---|---|---|---|
| open-front lit bay vs shutter-down bay rhythm | ●●● | ●●● | ●● night |
| horizontal sign board colour + legible TC text | ●●● | ●● (colour) | — |
| menu boards | ●● | — | — |
| stools / counters / goods spill | ● | — | — |
| exhaust ducts | ● | — | — |

### Proposal [P]
* Per commercial bay **storefront state** in `xc_wall` (shader, no geometry): `glazed-bright` (convenience, pharmacy,
  phone, clinic) · `open-bright` (food, drinks — shutter up, warm-to-cool white interior, counter line) · `shutter-down`
  (corrugated grey) · `dim-deep` (hardware / repair). State chosen by hash + role; night factor flips some `open` bays to
  `shutter-down` and keeps food/drink open — a deterministic, believable night mix.
* **Horizontal atlas** for the sign band: the existing 2048² atlas is exactly full (32·128·512 + 8·256·512 + 16·256²
  = 2048²) [R]. Add a second **2048 × 1024 BC7** atlas (≈ 2.7 MB with mips) with 4:1 and 6:1 cells, left-to-right TC,
  same font/licence/blacklist pipeline. Sample it in the existing `signBand` path (one guarded sample, near only).
* Skip props (stools, menu stands) — sub-pixel beyond 50 m.

---

## 8. Scooter-cluster proposal

### Observed
* 14.7 M scooters nationally (62.7 per 100 people) [O]; Taipei 921 k registered (2025-03) [O]; ~282 k on-street scooter
  stalls citywide [O]; legal stall width 1–1.5 m (some as narrow as 0.7 m) [O].
* Policy since 1999 moves scooters out of arcades / sidewalks into **road-edge stalls / bays** [O]; in practice arcades
  and lanes still hold informal clusters [O].
* Rows are perpendicular to the kerb, packed, mixed colours (white, black, silver, muted colours), many with rear top
  boxes (delivery) [O-gk].

### Abstraction [P]
| item | proposal |
|---|---|
| silhouettes | **4 meshes, ≤ 40 tris each**: (a) step-through 125 cc scooter, (b) maxi scooter, (c) scooter + rear top box, (d) small e-scooter. Boxes / wedges / 6-sided wheel slabs; no mirrors, no transparency |
| material | reuse `M_XinyiStreet` or `M_XinyiProps` (opaque); custom data: body colour index (8: white 25 %, black 20 %, silver 20 %, dark blue, dark red, beige, matte green, grey-blue) + mesh-variant jitter. No emissive |
| placement | **from the stall paint**: stall rows (white outlines, 1.2 m pitch × 2.0 m depth, perpendicular to the kerb) placed mid-block on curbs of roles 5–7 (p ≈ 0.5 per curb segment) and 3/4 / lanes (p ≈ 0.25); never within ~12 m of a junction kerb return, never across `service=driveway` endpoints, never where a green lane claims the curb. Occupancy 60–95 % by role. Yaw ±8°, offset ±0.15 m, 10 % nose-out flips |
| arcade clusters | later (v0D): 3–8 scooters in front of convenience stores / food shops on the road edge |
| determinism | per-row RNG seeded by sha256 of the curb-segment id (same method as v0B) |
| shadows | **off** (paint a slightly darker oil-stained stall fill instead; reads as contact shadow) |
| cull | fade 160–220 m (scooter ≈ 5 × 9 px at 200 m; below that it's a dark kerb texture provided by the stall fill) |

### Estimates
| quantity | estimate | basis |
|---|---|---|
| stalls in the WFS area (~4 km²) | **4,000–6,000** | 282 k / 271.8 km² ≈ 1,040 /km² citywide, ×1.5–2 for dense Da'an/Xinyi [I] |
| scooter instances | **3,000–4,500** | 70–80 % occupancy |
| visible (LOW, in frustum, within cull) | **100–400** | v0B blade/box ratios scaled to a 220 m cull |
| triangles | 120–180 k total; **4–16 k drawn** | ≤ 40 tris |
| new components | 1 HISM (4 meshes ⇒ 4 HISMs if one mesh per component, as v0B does) | |

Visual value per cost: the best item in this audit. At VERY LOW / LOW a packed scooter row is unambiguous Taiwan.

---

## 9. YouBike recommendation

* Observed: Taipei ~1,633 stations / 23,860 bikes (2025; city target 2,000 stations) [O], 1,708 stations in a 2026
  report [O]; YouBike 2.0 bikes are **white with yellow**, docks are light, **unpowered single-bike pillars** with
  on-bike electronics, so stations fit sidewalks and lanes [O].
* Abstraction [P]: a **dock row** = N × (bike silhouette ≤ 24 tris + thin pillar) along a sidewalk edge, N = 8–20, plus
  occasional empty docks. No kiosk. Positions from official open data (station coordinates) or OSM
  `amenity=bicycle_rental` — data-driven only, never invented.
* Estimate: ~30–60 stations in the WFS area (UNVERIFIED), ~600–1,000 bike instances, cull 150 m, ~2–5 k tris drawn.
* Verdict: **secondary.** Readable only at VERY LOW / LOW (a yellow-white dash at 100 m ≈ 9 px tall bikes). Worth a
  cheap later pass (v0F) once scooters and storefronts land; **not in Xinyi v0C/v0D**.

---

## 10. Utility-prop priority (ranked by actual Taipei identity value, not existence)

| rank | prop | observed | identity | VERY LOW | LOW | MID | verdict |
|---|---|---|---|---|---|---|---|
| 1 | Pad-mounted transformer / switch cabinets (台電 亭置式, grey-green, ~1–1.5 m) on sidewalks & green strips | [O] ~182 k above-ground units in Taiwan, mostly on sidewalks / parks / setbacks | medium (Taiwan-typical) | ●● | ● | — | later, on raised sidewalks only, ~1 per 60–100 m, cull 150 m |
| 2 | Signal mast arms with horizontal heads + pedestrian countdown "walking green man" | [O-gk] | medium | ●● | ● | — | later junction pass |
| 3 | Bus shelters + median bus-lane platforms | [R] 2.4 km `busway` in cache | medium | ●● | ●● | ● | junction/transit pass |
| 4 | Overhead green direction-sign gantries on arterials | [O-gk] | low-medium | ● | ●● | ● | junction/transit pass |
| 5 | Red + green post boxes (中華郵政) | [O-gk] | high identity, tiny | ● | — | — | optional, VERY LOW only |
| 6 | Guardrails / median planters | [O-gk] | low | ● | ● | — | skip for now |
| 7 | Bollards / anti-scooter barriers at sidewalk ends | [O] common | low | ● | — | — | skip |
| 8 | Utility poles + wires | Xinyi largely undergrounded (UNVERIFIED rate); wires need alpha | negative risk | — | — | — | **do not add** in Xinyi |
| 9 | Street litter bins | Taipei street bins are sparse (household waste goes to scheduled trucks) [O-gk, UNVERIFIED count] | wrong if overused | — | — | — | **do not add** |
| 10 | Parking meters | Taipei roadside parking is billed by attendant slips / apps, not meters [O-gk, UNVERIFIED] | wrong | — | — | — | **do not add** |
| 11 | Fire hydrants | [O-gk] | negligible | ● | — | — | skip |

---

## 11. Taiwan road-marking priority

| rank | marking | basis | VERY LOW | LOW | MID | in repo | proposal |
|---|---|---|---|---|---|---|---|
| 1 | **White scooter stall rows** (+ darker stall fill) | [O] | ●●● | ●●● | ● | no | v0C, paint geometry; anchors §8 |
| 2 | **Green painted pedestrian lanes** | [O] | ●● | ●●● | ●● | no | v0C (cut-line item) |
| 3 | **機車待轉區** two-stage left-turn boxes: white box on the near-right corner area at signalised arterial junctions, scooter symbol inside | [O] mechanism; dimensions UNVERIFIED | ●● | ●●● | ● | no | v0C (cut-line item); place only where both roads are tertiary+ with `crossing=traffic_signals` nodes |
| 4 | **Contextual red / yellow kerbs** | [O-gk] | ● | ●● | ● | red everywhere (2/3) | v0C: red only on junction approaches (~15 m) / bus stops; yellow on a share of mid-block; white stall rows on the rest |
| 5 | **Real crossings incl. diagonal scrambles** | [R] 676 / 16 diagonal in cache | ●● | ●●● | ●● | heuristic | junction pass (v0E) |
| 6 | **Median bus lane** markings | [R] 2.4 km busway | ● | ●● | ●● | no | v0E; verify marking colours against imagery first |
| 7 | 機車停等區 waiting boxes | [O] | ●● | ●● | ● | **yes** | keep |
| 8 | Chinese road text (慢, 停, 讓 triangle, 人行道, 公車專用) | [O]/[O-gk] | ●●● (strong identity) | ● | — | no | later: small text atlas on paint quads, near only |
| 9 | Yellow cross-hatch keep-clear boxes (網狀線) | [O-gk] | ● | ● | — | no | optional |
| 10 | Lane arrows | generic | ● | — | — | no | skip |

---

## 12. LOD / culling strategy

Principle (unchanged from the engineering plan): one representation per feature, opaque, cull-faded, never alpha;
shader detail collapses to its mean via `xc_detail`; **far bands are carried by paint / shader means, not by props**.

| feature | VERY LOW (0–50 m) | LOW (50–200 m) | MID (0.2–1 km) | HIGH (> 1 km) |
|---|---|---|---|---|
| scooters | HISM meshes | HISM meshes, fade out 160–220 m | stall-fill paint = darker kerb band | nothing |
| stall / green lane / 待轉區 paint | geometry | geometry | geometry (sub-pixel lines average) | negligible |
| sidewalks | paver joints + tactile | value bands | mean grey | mean grey |
| convenience store | glazed bay, shelves, fascia text | lit bay + fascia colour | **night emissive bay** | night emissive speck |
| storefront states | full detail + atlas text | bay rhythm + board colour | night glow mix | night city glow (existing far glow) |
| YouBike (later) | bikes + pillars | fade out 120–150 m | nothing | nothing |
| utility cabinets (later) | mesh | fade out 120–150 m | nothing | nothing |

Rule of thumb for cull ends: stop drawing when the object's **smallest silhouette dimension < ~2 px** (≈ 935 · size / 2 m):
scooter 1.1 m ⇒ ~500 m theoretical, but in street canyons rows are mostly occluded and the stall fill carries the read, so
220 m is enough.

---

## 13. Performance estimate (Intel UHD 770, 1080p reference, same method as v0A/v0B)

Baseline measured in v0B: 4,926 street instances, 3 HISMs, **≤ ~0.3 ms at LOW, unmeasurable at MID/HIGH** [R].

| item | instances | tris total / drawn (LOW) | components | GPU est. LOW / MID / HIGH | memory |
|---|---|---|---|---|---|
| remove shader scooter blobs | — | — | — | ≈ 0 / −ε | — |
| sidewalk palette + presence rule | — | — | — (ground class flag) | ≈ 0 | 0 (channel already exists) |
| stall + green-lane + 待轉區 + kerb paint | — | +15–25 k static (long polyline segments) | 0 (in `XinyiRoadPaint`) | < 0.05 ms all bands | < 1 MB |
| scooters | 3,000–4,500 | 120–180 k / 4–16 k | 1–4 HISM | +0.1–0.4 / ≈ 0 / 0 ms | ~meshes only |
| sign-band glyph mitigation (v0C) | — | — | — | ≈ 0 (fewer ALU) | — |
| horizontal TC atlas (v0D) | — | — | — | 1 guarded sample, near only ≈ 0.05–0.2 ms | +2.7 MB BC7 |
| convenience stores + storefront states (v0D) | 50–90 stores | 0–100 fascia instances | 0–1 | +0.05–0.3 ms (per-building-coherent branch) | — |
| YouBike (v0F) | 600–1,000 | ~20 k / 2–5 k | 1–2 | +0.05–0.15 ms | — |
| **v0C total** | **≈ 3–4.5 k** | **≈ 20 k drawn worst case** | **+1–4** | **≲ +0.5 ms LOW, ≈ 0 MID/HIGH** | **< 1 MB** |

Measure with the interleaved same-session harness (layer on / hidden / shadows off), never sequential runs — perf
drifts between sessions (v0A −3.6 ms and v0B +4.1 ms were drift).

---

## 14. Recommended implementation sequence

| pass | theme | contents | why this order |
|---|---|---|---|
| **v0C** | **Curb-zone truth** | remove scooter confetti; grey paver palette + data-driven sidewalk presence; stall rows + contextual kerbs; **scooter HISM**; sign-band pseudo-glyph mitigation; (cut line) green lanes, 待轉區 | fixes both "actively wrong" items and adds the #1 Taiwan signal; all ground/paint/props, no facade rewrite |
| v0D | Storefront truth | horizontal TC atlas; storefront states (open / glazed / shutter / deep); **便利商店 archetype** (OSM snapshot positions); night shop glow; scooter clusters at stores | the night/MID signal; needs a new atlas, so keep it separate |
| v0E | Junctions & transit | real OSM crossings incl. diagonal; median busway + shelters; signal mast arms; overhead direction signs; road text atlas (慢 / 停 / 讓 / 人行道) | LOW/MID credibility over arterials, the flight corridors |
| v0F | Secondary street furniture | YouBike dock rows (open-data positions); transformer cabinets on raised sidewalks; optional post boxes | VERY LOW / LOW only — last |

Out of sequence / do not do: wires & poles in Xinyi, litter bins, parking meters, street-level clutter beyond the above,
any traffic simulation, any change to building tiles, terrain or Taipei 101.

---

## Proposed next pass — **Taipei Street Reality v0C: curb-zone truth**

Scope is one focused Opus pass; look-dev layer only; the 25 look tiles stay bit-identical; no facade grammar change
except the one glyph line set.

**In scope (mandatory)**

1. **Ground correction** (`xc_ground`, `build_ground.py`):
   * delete the shader scooter blobs (`scooterZone`, `hasScooter`, `scooterCol` and the `paver` lerp);
   * replace the paver palette with the grey/beige-grey value-only palette of §4 (drop the brick-red variant);
     tactile strip at crossing ramps (near-only);
   * sidewalk **presence** from data: encode a per-road-side "has sidewalk" flag into the ground class channel
     (existing texture; no new channel) from mapped `footway=sidewalk` proximity / `sidewalk=*` tags / class + width;
     no sidewalk ⇒ asphalt to the building line.
2. **Curb paint** (`build_ground.py`, same `XinyiRoadPaint` mesh): white scooter **stall rows** (1.2 m × 2.0 m,
   darker oil-stained fill) on eligible curbs keyed by `frontage_roles.json` roles; red kerb only on junction
   approaches and remaining no-stall stretches; a yellow share mid-block. Placement table written to
   `urban_identity/curb_segments.json.gz` (deterministic, sha256-seeded).
3. **Scooters** (`build_street_identity.py` or a sibling): 4 silhouettes ≤ 40 tris, opaque, no shadows, placed only in
   painted stalls at 60–95 % occupancy; cull 160–220 m.
4. **Sign-band mitigation** (`xc_wall` L537–549 only): remove the 2 × 3 stroke pseudo-glyphs; boards become plain colour
   panels with a faint lighter text band at near range, until v0D's TC horizontal atlas replaces them.

**Cut line (do if time allows, else first item of v0D)**: green pedestrian lanes (§5) and 機車待轉區 boxes (§11 #3).

**Not in v0C**: convenience stores, storefront states, the horizontal atlas, YouBike, utility cabinets, junction /
transit features, road text.

**Gates**
* tiles bit-identical; shader diff limited to `xc_ground` + the sign-band glyph lines (every other function
  text-identical to HEAD); DXC `-WX` for all materials;
* every scooter inside a painted stall; no stall within 12 m of a junction kerb return or across a driveway endpoint;
  no scooter or stall footprint intersecting any building footprint; no green lane where a stall row or mapped sidewalk
  exists;
* sidewalk-presence audit: km of sidewalk by road class before / after, and 0 sidewalks on `service=*`;
* ground pixel regression: changed pixels confined to kerb/road-edge bands (rear-wall, roof, MID/HIGH skyline views
  ≈ 0 %);
* determinism: two rebuilds ⇒ identical paint mesh, placement table and instance hashes;
* UE5.8 SceneCapture2D DAY / DUSK / NIGHT on the v0B cameras + one new alley camera (巷, ~15 m eye) + one junction
  camera (~80 m over an arterial junction); interleaved same-session perf: **target ≤ +0.5 ms at LOW, ≈ 0 at MID/HIGH**.

**Success looks like**: at 20–80 m, 莊敬路 / 吳興街 read as grey municipal sidewalks with packed scooter rows at the
kerb and calm plain boards on the sign band; alleys read as asphalt to the wall with scooters along the edge; nothing
on the ground is multicoloured.

---

## 15. Sources (reference only)

Painted pedestrian lanes / sidewalks
* TVBS 車鑑 — Taipei painted walkways: green, fragmented, ~9 km/yr, obstructions: https://cars.tvbs.com.tw/life/327095
* Newtalk 2026-07-31 — green for painted walkways, brick-red for bike lanes (Taichung conflict): https://newtalk.tw/news/view/2026-07-31/1050561
* TRECA document — painted walkway ≥ 1.5 m, ≥ 0.9 m clear, 「人行道」 text: https://www.treca.org.tw/component/k2/download/19893_63c9631fa616d25b47de03048aeeb7be.html
* UDN on Taipei pedestrian markings: https://udn.com/news/story/7323/9567862
* Taipei city paving specifications (high-pressure concrete pavers): https://www-ws.gov.taipei/001/Upload/837/relfile/62040/8974314/3e56c2a9-466b-427d-b700-c8c13cba5fea.pdf
* Construction Agency (NLMA) paving material references: https://www.nlma.gov.tw/uploads/files/06d8aad6a63a95b9eec5b6725c90e695.pdf
* Taipei Times 2023-12-13, pedestrian conditions in Taiwan: https://taipeitimes.com/News/feat/archives/2023/12/13/2003810541
* Chang & Marshall (2025), building–street interface types, Da-an District (abstract only; PDF could not be parsed here): https://discovery.ucl.ac.uk/id/eprint/10216030

Scooters
* Taiwan News — 14.665 M scooters, 62.7 per 100 people: https://www.taiwannews.com.tw/en/news/6098407
* Taipei DBAS statistics — Taipei registered scooters 921 k (2025-03): https://www-ws.gov.taipei/001/Upload/367/relfile/46908/9404878/dc6ba8d2-ef4c-4023-980d-fb3ae7fbadad.pdf
* TVBS / UDN — ~282 k scooter stalls, stall width 1–1.5 m: https://cars.tvbs.com.tw/life/254810 , https://udn.com/news/story/7323/9577150
* 8891 — 機車退出騎樓、人行道 (since 1999) and 2.0: https://c.8891.com.tw/news/17391
* Two-stage left turn (機慢車兩段左轉) rules: https://www.laws.taipei.gov.tw/Law/File/0000046225

Convenience stores
* Taiwan Today — store counts and density: https://taiwantoday.tw/AMP/Society/Top-News/20481/
* IHL Services — Taiwan retail / store density 2026: https://www.ihlservices.com/news/analyst-corner/2026/03/taiwan-pos-terminal-market-2026/
* Young Pioneers in Asia — why stores cluster: https://ypa.beehiiv.com/p/why-are-there-two-family-marts-across-the-road-in-taiwan

YouBike
* Taipei DOT report — 1,633 stations / 23,860 bikes, 2026 targets: https://www-ws.gov.taipei/001/Upload/367/relfile/46908/8974682/29644daa-32a3-4f1b-b100-33ba280aa47d.pdf
* ETtoday 2026-05-17 — 1,708 Taipei stations: https://www.ettoday.net/news/20260517/3167530.htm
* Taiwan News — YouBike 2.0 lite docks, white/yellow bikes: https://www.taiwannews.com.tw/en/news/4321183
* YouBike official: https://en.youbike.com.tw/region/main/about-youbike

Utility cabinets
* Techbang — ~6,000 platform transformer stations; pad-mounted units on sidewalks: https://www.techbang.com/posts/73965-6000-timeless-bombs-on-the-streets-of-taiwan-i-saw-it-when-i-opened-the-window
* Control Yuan — 446 k pad-mounted transformers, 182 k above ground on sidewalks / parks / setbacks: https://multimedia.cy.gov.tw/Message_Message/21974/1001207News-變壓器.pdf

Repo evidence: `unreal/Saved/XinyiLook/evidence/street_v0b/sheets/fin_street_{day,night}.png`, `fin_zoom_{day,night}.png`,
`frontage_v0a/sheets/fin_midhigh_day.png`; `tools/lookdev/shaders/xinyi_city.hlsl` (`xc_wall` sign band, `xc_ground`);
`tools/lookdev/build_ground.py` (paint, `CLASS`, `way_geometry`); `data/lookdev_cache/osm_xinyi_context.json.gz`
(tag/length inventory computed in this pass, read-only).
