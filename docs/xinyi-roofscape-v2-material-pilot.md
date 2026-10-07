# Xinyi Roofscape v2 + Roof Material Pilot — planning / spec

Status: **plan only. No code, shader, asset or Unreal change.** Nothing here is approved or built.
Inputs: `docs/taipei-urban-visual-language-research-v0.md` (§3.4, §6, §9, §12–14, §17 orthophoto sample),
`docs/xinyi-rooftop-identity-v0-result.md`, `tools/lookdev/build_rooftops.py`,
`tools/lookdev/shaders/xinyi_city.hlsl` (`xc_sheet16`, `xc_sheet_paint_index`, `xc_roof`),
`docs/taipei-building-era-metadata-v0.md`.

Evidence tags: **[R]** observed in the research docs, **[M]** measured from current code in this pass,
**[I]** inference, **[U]** unverified, must be checked before building on it.

---

## 1. Current problem summary

Three separate problems, with different fixes. Only the third needs new art.

**1.1 Roofs are too blue — a data bug, not an art gap.** [M]
Family shares implied by the current builder weights and `xc_sheet16` slot colours:

| family (slots) | old fabric `SHEET_W_OLD` | planned core `SHEET_W_CORE` | painted whole roofs (`xc_sheet_paint_index`) | orthophoto target [R §17, n = 348] |
|---|---|---|---|---|
| blue (0 blue-grey, 1 faded blue, 2 light blue) | **26.6 %** | **22.7 %** | **≈ 25 %** | **1–4 %** |
| green-grey (6, 7, 8, 14) | 21 % | 14 % | 25 % | ≈ 37 % |
| white / grey / beige (9–13, 15) | 33 % | 59 % | ≈ 41 % | ≈ 39 % |
| red / maroon (3, 4, 5) | 19 % | 5 % | ≈ 9 % | ≈ 23 % |

Blue is 6–25× over target. Slot 1 ("the signature 鐵皮 blue", saturated) is the single heaviest weight (10).
Slots 7 and 14 (teal) also read blue-green from the air, while the evidence says Taipei's green is **pale,
low-saturation green-grey** [R §17.2]. `xc_sheet_paint_index` makes it worse: it moves half of the warm picks
*to blue / galvanised*, so painted far-city roofs are also blue-heavy.

**1.2 Form: separate boxes with gaps instead of lot-filling covers.** [R §6.1, §17.2; M]
Real walk-up roofs read as a **strip of per-lot sheet covers, 4–8 m wide, footprint-filling, ridge along the lot's
long axis, each often a different colour** [R]. Our v0 builder places **1–3 rooms in a row from one end of the
largest inscribed rectangle**, covering 55–95 % of the *long axis* only, skips rooms < 2.6 × 2.6 m, and gets no
rooms at all on walk-ups split into tiny parts [M, rooftop v0 report]. From 150–400 m that reads as little boxes
on a grey roof, not as a sheet-metal roofscape.

**1.3 Flat-roof surface language is thin.** [R §6.1, §17.2; M]
About a third of low-rise roof area is flat concrete with clutter, and it is only seen as a flat tint + procedural
ponding stains in `xc_roof`. Missing states: stained old concrete, PU-coated / patched resurfaced roofs, clean
modern membrane, large-roof solar, an unfinished slab. These are mid-frequency (2–8 m patch) features, the scale
that survives at 150–800 m and that a noise shader renders poorly.

**1.4 What is already fine.** Palette *mechanism* (16 slots, per-instance colour index, district weights), 頂樓加蓋
room geometry, tanks / AC / bulkhead props, parapet cap, weathering terms. Reuse them.

---

## 2. Roofscape v2 visual target

Seen from 100–800 m over old Xinyi fabric:

* a **continuous quilt of per-lot sheet covers** (each 4–8 m wide) with **step changes in height and colour
  between neighbours**; between them, flat concrete / PU roofs with tank clusters at stair ends;
* **pale green-grey ≈ white / grey, then faded red, blue only as a trace** (target mix in §3.3);
* the planned core and new towers stay **clean, light, neutral**; solar and clean membrane appear on large flat
  roofs;
* **macro contrast, not micro detail:** patch edges, seam rhythm, colour breakup at 2–8 m; nothing finer than
  ≈ 0.5 m is expected to survive.

Why 0.5 m: at 1080p / 60° vFOV the ground sample distance is ≈ 0.11 m/px at 100 m, **0.32 m/px at 300 m**,
**0.86 m/px at 800 m**. Corrugation ribs (0.25 m pitch), rust speckle and cracks alias or vanish beyond ≈ 150 m
and shimmer in motion. The design band for roof art is **seams ≥ 0.9 m apart, patches 2–8 m, mottling 8–30 m**.

Style fit: stylised-real like the rest of the game world (sky, trees, roads, mountains). Roof surfaces therefore
carry **clean value shapes and restrained wear**, not scanned grit. A photo-real roof next to stylised trees is
the specific mismatch to avoid.

---

## 3. Procedural vs material split

### 3.1 Layers

| layer | what | owner |
|---|---|---|
| **G — geometry / layout / rules** (build time, deterministic) | lot subdivision, cover placement and fill, roof-state assignment, solar fields, clutter placement, district / era weighting | `build_rooftops.py` (+ a small roof profile in the city profile JSON) |
| **M — surface material** (small shared atlas, optional) | mid-frequency surface pattern for a few roof states | Image 2.5 source → one atlas |
| **S — shader-only** | palette tint, weathering, fades, edge darkening, far-city painted roofs, LOD fade of seams | `xinyi_city.hlsl` |
| **X — not now** | see §3.4 | — |

### 3.2 Roof-state system

One state per roof part. States are surface/layout classes, not building types.

| # | state | G (geometry / rules) | M (material) | S (shader) |
|---|---|---|---|---|
| 1 | **lot-filling sheet cover** (頂樓加蓋 quilt) | **main change.** Cut a row-like roof into 4–8 m lots; one cover per lot (mono-pitch 50 %, low gable 35 %, flat tin deck 15 %) filling ≥ 85 % of the lot's inscribed rectangle; ±0.2–0.5 m height step vs neighbour; neighbour colour ≠ previous with p ≈ 0.7; keep a 2.5–3.5 m band at one end for bulkhead + tanks | `sheet_ribbed`, `sheet_panel` (tint by palette) | palette tint, UV-fade, rust bloom, rib lines fade out by distance |
| 2 | **flat stained concrete** (old, uncovered) | none beyond clutter density (dense tanks at stair end, AC along parapet) | `concrete_stained` | value only: ponding, soot, parapet run-off (existing terms, re-weighted) |
| 3 | **patched / PU-resurfaced flat roof** | none; optional 1–3 patch rectangles as *mask*, not geometry | `pu_patched` (green-grey / grey tint; ≈ 4 % of flat roofs are green PU [R]) | tint, edge darkening |
| 4 | **modern clean finish** (towers, new podiums) | sparse aligned clutter only (BMU, plant enclosure exist) | `membrane_clean` | neutral light grey / white variants |
| 5 | **large-roof solar** (overlay on 2–4) | 1–3 rectangular fields aligned to roof axis, 25–50 % of roof, ≥ 3 m inset, roofs ≥ 400 m² (public / civic / school / large podium); one low-tilt instanced mesh ≤ 12 tris | `solar_field` | none (dark, fixed) |
| 6 | **unfinished / construction roof** | **deferred** (own Construction pass: slab stack, crane, net, hoarding) | optional later cell `slab_formwork` | — |

Water tanks / clutter: **rules only, existing props.** Tanks cluster on the bulkhead or at the uncovered stair-end
band; density by state (stained old flat: dense; PU: medium; modern: sparse and axis-aligned; covered lots: only
on the end band). Keep the current tank budget (≈ 9 k); no new tank geometry.

### 3.3 Palette target (data, no asset)

Proposed slot weights per 100, replacing `SHEET_W_OLD` / `SHEET_W_CORE`; slots keep their indices, **only weights
and a few slot colours change**:

| family | slots | old fabric | planned core |
|---|---|---|---|
| green-grey (pale, low saturation) | 6, 7, 8, 14 → 13 / 3 / 16 / 5 | **37** | 28 |
| white / grey / beige | 9, 10, 11, 12, 13 → 12 / 6 / 13 / 4 / 3 | **38** | 60 |
| faded red / maroon | 3, 4, 5 → 7 / 7 / 6 | **20** | 10 |
| rust / oxidised galvanised | 15 | 2 | 0 |
| blue (trace) | 0, 1, 2 → 1 / 1 / 1 | **3** | 2 |

Companion edits (all shader / builder data): retune slots 6, 7, 8, 14 toward **paler, less saturated, less
blue-teal**; demote slot 1; change `xc_sheet_paint_index` so warm picks move to galvanised / off-white (not to
blue). District red-heavy profiles (Wanhua, Beitou ≈ 40 % red [R]) become a profile parameter, not code. Era
(§6) can bias the same table.

### 3.4 Not worth doing now

* corrugation as geometry or normal maps; sub-0.5 m rust / crack / moss detail;
* per-roof unique textures; any texture sampled by world-unique UV;
* cadastral-accurate lot splitting (the era / parcel data is optional, see §6); lots are a **geometric heuristic**;
* rooftop gardens, laundry, railings, antennas redesign (small, already props);
* crowns, cranes, hoarding, construction states (Construction pass);
* city-wide generalisation beyond the detailed Xinyi source;
* facades (separate pass).

---

## 4. First Image 2.5 pilot batch

**Seven source cells, one shared atlas, one material sample.** The atlas is *optional* until the §7 A/B shows it
earns its cost.

Design decisions:

1. **Neutral value + masks, tinted by data.** Sheet and flat-roof cells are authored near-neutral. Colour comes
   from `xc_sheet16` and the §3.3 weights, so *the generator can never reintroduce "too blue"* and district / era
   weighting stays a data concern. Only `solar_field` carries baked colour.
2. **Packed channels, one RGBA sample:** R = value (pattern, 0.35–0.85 band), G = wear / patch mask,
   B = seam / joint mask (drives darkening and roughness), A = reserved. Linear (non-sRGB) texture; ASTC on mobile.
3. **Cell = 8 m × 8 m at 256 px** (32 px/m, far more than the ≥ 3 px/m the 0.3 m/px design band needs; mips do the
   rest). Atlas 1024 × 512 (4 × 2 cells, 8th spare), ≈ 0.3 MB ASTC 6×6 with mips.
4. Each cell tiles seamlessly on both axes. Sheet cells have a stated **rib axis** (cell +Y); instances rotate it
   to the cover's ridge, replacing today's world-axis ribs.
5. Atlas bleed on mobile: 8 px gutters, per-cell mip clamp in the shader. A 2D-array would avoid it but mobile
   support is **[U]**.

### 4.1 Per-asset spec table

| # | asset (cell) | serves | why it earns a cell | form | channels needed |
|---|---|---|---|---|---|
| 1 | `sheet_ribbed` | state 1 (covers), the dominant roof read | replaces world-axis noise ribs with real seam rhythm along the ridge; carries re-roofed panel patches | tileable cell, ribs along +Y, seams every ~1 m | value + wear + seam |
| 2 | `sheet_panel` | state 1 variant: flat tin deck / coated white-grey sheets | second rhythm so neighbouring lots do not repeat: wide panels, 1.2 m, screw lines, no ribs | tileable cell | value + wear + seam |
| 3 | `concrete_stained` | state 2 (old flat roofs) | where the macro read comes from: large dark ponding blotches, rain-run direction, edge soiling at 2–10 m scale that noise shaders do badly | tileable cell | value + wear (shader adds a little world noise) |
| 4 | `pu_patched` | state 3 | rectangular recoat / repair patches with crisp edges (the "resurfaced" cue) | tileable cell; patch rectangles on the wear mask | value + wear |
| 5 | `membrane_clean` | state 4 (modern) | clean roofs need *some* structure: paver / membrane grid 1.2 m, expansion joints, a faint edge band; otherwise they read as unlit flat colour | tileable cell | value + seam |
| 6 | `solar_field` | state 5 overlay | baked colour; module grid (4 × 2 modules per 8 m) and frame lines; a dark navy-black is the only blue allowed at scale | decal-like quad texture, not tinted | base colour only (+ seam in A) |
| 7 | `roof_edge_dirt` (optional, may drop) | all flat states | soft darkened parapet-edge / drip band so roofs seat in their parapet | small 1D strip in the spare cell, sampled along the footprint edge distance | value only |

If cell 7 cannot be sampled cheaply (needs edge distance; shader already has parapet terms), **drop it**; edge
darkening stays shader-only. The first batch is then **six assets**.

### 4.2 Style rules shared by all assets

Generate as **material source, not as a picture of a roof.**

* top-down, orthographic, **no perspective, no horizon, no foreshortening**; the camera is looking straight at a
  flat surface;
* **flat neutral lighting, no baked sun, no hard or soft cast shadows, no ambient-occlusion pools, no reflections,
  no vignette**;
* **seamless on both axes**; features must not touch the border in a way that breaks the repeat;
* near-neutral grey (value 0.35–0.85) for tinted cells; **no hue** beyond ≤ 5 % warm/cool lean, because the
  palette supplies colour;
* **macro rhythm over micro:** seams ≥ 0.9 m apart, patches 2–8 m, soiling blotches 3–10 m; edges slightly soft;
* **restrained, low-contrast weathering:** value contrast between wear and clean ≤ 0.25 (0–1);
* **stylised-real:** clean value shapes like a good game material; no photographic noise, grain, lens artefacts;
* **no text, logos, arrows, objects** (tanks, vents, people, cars, plants).

### 4.3 What makes an asset wrong (reject on sight)

| defect | why it fails |
|---|---|
| any visible perspective, vanishing lines, scene context | not a material; cannot tile |
| baked shadows, light direction, highlights on ribs | double-lights under UE sun; breaks time-of-day |
| tileable only with a visible repeat (obvious blotch, single stain) | repeats read as a pattern at 150–300 m |
| **hue** present in a "neutral" cell (esp. blue or brown cast) | defeats the palette; recreates "too blue / too brown" |
| ≥ 0.15 m detail carrying contrast (rust speckle, fine corrugation, cracks, moss) | aliases / shimmers beyond 150 m, adds nothing |
| high contrast (wear vs clean > 0.35) | looks like camouflage from the air |
| scan-photographic grain or dirt | mismatched with the stylised world |
| seams that are 1 px wide at the cell's native scale | vanish at distance; seam lines need ≥ 0.1 m width |
| patches that are the *same size and shape* every time | reads as stamped |

---

## 5. What should remain procedural / not be generated

| thing | stays | because |
|---|---|---|
| roof colour, palette weights, district / era / profile bias | **data** (§3.3, `xc_sheet16`, profile JSON) | zero cost; generated colour would drift and override weights |
| lot cutting, cover fill, heights, colour sequence, solar placement | **rules / geometry** | silhouette and layout are the identity; textures cannot fix them |
| tanks, AC, antennas, bulkheads, BMU, plant rooms | **existing instanced props** | already geometry; no art |
| macro weathering: ponding, soot, parapet run-off, UV fade, rust bloom | **shader** (existing terms, re-weighted) | cheaper and consistent across all buildings and far city |
| far-city painted roofs (beyond the detailed 2 × 2 km) | **shader palette only** | cannot afford atlas sampling and has no geometry |
| seam LOD fade, anti-aliasing of rib lines | **shader** | distance-dependent |
| tank / clutter contact shadows | **shader / existing fake shadow** | tiny, cheap |
| construction states, cranes, hoarding, netting | **separate Construction pass** | geometry + material system of its own |
| normal maps, roughness maps, AO | **none** | mobile cost with no measurable aerial payoff; seam mask drives roughness |
| per-district or per-era texture variants | **data weighting of the same cells** | do not multiply assets by district |

No lettering, no logos, no scene-like roof pictures, no per-building art.

---

## 6. Regional portability and the era signal

Roofscape v2 must not depend on Taipei-only data.

* Roof states are chosen from **archetype, roof size, weathering (age proxy), planted-core flag** — all existing
  look-dev fields — through a small **RoofProfile** block (state weights per archetype, family weights, cover fill,
  solar probability) in the city profile JSON. Another region ships its own profile; defaults must be safe.
* The **building era metadata** (`pipeline.load_records` → per group) is an *optional multiplier*:
  `pre_1980` raises stained concrete / sheet cover; `2010_2019`, `2020_plus` raise modern clean + solar and zero
  the informal cover; `unknown` (84 % of Xinyi groups today, all of a region with no age data) uses the profile
  prior unchanged. Nothing in the roof builder may *require* an era record.
* The parcel / permit join is **not** used for lot cutting. Lots come from footprint geometry (§3.2 state 1).
  Real parcel lines would be better but are a Taipei-only optional enrichment.

---

## 7. Acceptance criteria (UE review)

Review uses the existing capture harness and the roof suite (`roof_ne1`, `roof_ne2`, `roof_mid`, `overview`,
Wuxing, Elephant) plus **four fixed top-down-ish altitudes: 150 / 300 / 600 / 800 m**, DAY plus one DUSK sanity.
Compare **before / palette-only / palette + covers / palette + covers + atlas**.

| criterion | pass |
|---|---|
| **Colour mix** — pixel-class the sheet-roof pixels from nadir captures | blue ≤ 4 %; green-grey 30–45 %; white-grey 30–45 %; red 15–28 % (old fabric) |
| **Form** — on covered walk-up roofs | cover occupies ≥ 85 % of visible roof area; **no gap pattern** readable at 300 m; ≥ 60 % of adjacent cover pairs differ in colour or height |
| **Silhouette from 300 m** | rows read as strips of sheet rectangles with stair-end tank clusters, not boxes on a plate |
| **Core / towers unchanged** | planted-core and tower roofs stay clean and neutral; Taipei 101, landmarks, schools, sky, ground untouched (pixel diff confined to roofs) |
| **Aliasing / shimmer** — 2-frame diff while flying 60 m/s at 150 m | no new shimmer vs baseline; seam fade clean |
| **Style fit** | roofs not noticeably more photographic than trees and roads in the same frame (human review, 3 reviewers) |
| **Mobile budget** | one extra texture sample only on roof / cover pixels; atlas ≤ 1 MB; draw calls unchanged; **≤ +0.5 ms vs same-session baseline** (v0 rooftop layer cost +0.2…2.7 ms, so geometry changes must not increase it); instances ≤ today's + ~2 k, triangles ≤ today's + ~60 k [I] |
| **Determinism** | rebuilding the rooftop layer twice gives identical `rooftop_instances.json` (hash) |
| **Atlas earns its place (A/B)** | atlas ON beats OFF in at least 2 of 3 blind reviews at 300 / 600 m; if not, **do not ship the atlas** — ship palette + geometry only |

---

## 8. Recommended implementation order

Each step is reviewable alone; stop at any gate.

0. **Palette fix (data + 2 shader constants, no asset, no geometry).** Re-weight `SHEET_W_*`, retune slots 1 / 6 /
   7 / 8 / 14, fix `xc_sheet_paint_index`. Capture. *Gate: the colour mix passes.* This alone may fix the loudest
   complaint.
1. **Lot-cover geometry (rules only).** In `build_rooftops.py`, replace the 1–3 room row for walk-up / low /
   huaxia with lot subdivision and lot covers, reusing `addition` / `leanto` (add one 10-tri mono-pitch mesh if
   needed). Keep tank / bulkhead end band. Capture. *Gate: form criteria pass without any new texture.*
2. **Roof-state flag + 2–3 surfaces.** Encode state in **flag bits 4–6 of roof triangles** (unused on roofs; 0 =
   today's behaviour, so old data stays valid) **[U: confirm no shader or builder path reads those bits on roofs]**.
   `xc_roof` selects stained / PU-patched / modern-clean. Procedural first (shader), so the atlas has a baseline.
3. **Pilot atlas (only now).** Generate cells 1–5 (six if solar is wanted) via Image 2.5 per §4, build the atlas,
   add one sample in `xc_roof` and the sheet-cover path. Run the A/B in §7.
4. **Solar fields** (state 5), only if step 3 is accepted and Xinyi has enough qualifying roofs (large public /
   school / podium roofs).
5. **Decide:** expand the family (variants per cell, a construction slab cell) **or stop**.

Estimated cost: steps 0–1 are the core of the value and need no generation. Steps 2–3 are the pilot proper.

### Open questions / [U] to verify before step 2–3

* free flag bits 4–6 on roof triangles (§8 step 2);
* whether the props material can take one extra atlas sample on cover pixels within the mobile budget;
* atlas gutter / mip-clamp behaviour on target mobile GPUs vs a 2D texture array;
* actual blue-share after palette fix, from pixel classes (the §1.1 numbers are weight arithmetic, not pixels).

---

## 9. Draft Image 2.5 prompts (not generated)

Common suffix for every prompt: *"seamless tileable material source, strict top-down orthographic view, flat
neutral lighting, no shadows, no highlights, no perspective, no objects, no text, stylised game-ready surface,
clean value shapes, low contrast, near-neutral grey with no colour cast, no photographic noise."*

1. **`sheet_ribbed`** — "Painted sheet-metal roof panels seen from directly above, long low ribs running
   vertically, one panel seam about every metre, a few rectangular re-roofed replacement panels in slightly lighter
   or darker value, soft sun-fade gradient across panels. Light-to-mid grey value only. Ribs are broad and soft,
   not fine corrugation." + suffix. Request value, wear mask and seam mask as separate layers.
2. **`sheet_panel`** — "Wide flat metal roof panels from above, 1.2 m panel width, thin screw lines, a few
   panel-to-panel value shifts, very faint soiling along the seams, no ribs." + suffix.
3. **`concrete_stained`** — "Old flat concrete roof from above: broad soft dark ponding blotches 3–10 m across,
   faint parallel rain-run streaks in one direction, slightly darker band along one edge, no cracks, no plants,
   no objects." Large shapes, low contrast. + suffix.
4. **`pu_patched`** — "Flat waterproof-coated roof from above with several crisp rectangular recoat patches of
   slightly different value, straight patch edges, a faint overlap seam line, otherwise smooth." + suffix.
5. **`membrane_clean`** — "Clean modern flat roof surface from above: 1.2 m square pavers or membrane panels,
   thin expansion joints, very light value, a faint darker band along one edge, no stains." + suffix.
6. **`solar_field`** (colour allowed) — "Rooftop solar panel array from directly above: two rows of dark
   navy-black modules with thin silver frames, 4 modules wide, tilted-array spacing as plain light-grey strips
   between rows, no reflections, no shadows, no text." Flat light. (Do not use the neutral-grey suffix line.)
7. **`roof_edge_dirt`** (optional) — "A 1 m wide strip of roof edge soiling from above, soft darker gradient
   fading from the parapet line into clean surface, tileable along its length." + suffix.

Acceptance of any generated cell is a **review in the engine at 150 / 300 / 600 / 800 m**, not on the source image.

---

## Files

New: `docs/xinyi-roofscape-v2-material-pilot.md` only.
