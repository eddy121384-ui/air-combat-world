# Taipei facade material pilot v0 — planning / spec

Status: **plan only.** Nothing here is approved, generated or built. No shader, texture, Unreal asset or grammar
change. Accepted HEAD at writing: `a9c58d6` (Roofscape v2 complete).

Inputs: `docs/taipei-urban-visual-language-research-v0.md` (§4, §5, §9–14, §18–22),
`docs/taipei-building-era-metadata-v0.md`, `tools/lookdev/shaders/xinyi_city.hlsl` (`xc_wall`, `xc_tile_palette`,
`xc_city`), `tools/lookdev/build_look_tiles.py` (vertex data contract), current captures
(`evidence/roof_surface_step2/frames/s2_day`: `e_lowpass_xinyi_rd`, `f_rooftops_wuxing`, `a_skyline_nw`,
`rp_steep_ne`, `roof_mid`).

Evidence tags as in the roof plan: **[R]** research docs, **[M]** measured / read from code or captures in this pass,
**[I]** inference, **[U]** unverified, check before building on it.

---

## 0. Short answer

**Only one of the four families clearly deserves generated source art, and only as masks, not as facade pictures.**

| family | generated art? | form |
|---|---|---|
| 1. old walk-up / mixed use | **yes** (pilot) | 3–4 greyscale **macro-ageing masks** packed into one small RGBA texture, shared with family 2 |
| 2. huaxia 1980s–2000s | **shares family 1's masks** at lower weight; no art of its own | palette + grammar data |
| 3. modern residential | **no** | procedural era grammar (bands, piers, glazing ratio, neutral glass) |
| 4. luxury / premium | **no for v0**; one optional cladding sheet held back | procedural premium grammar; art only if it fails review |

The biggest facade error on screen today is **generational**: every 13–24 F tower and new mid-rise wears the same
cream punched-window grid. That is a **grammar and data** problem (rectangles aligned to floors and bays, glass tint,
palette, composition). Generated art cannot fix it and would bake window geometry that the procedural layers
(storefronts, frontage roles, cages, AC, night lights) depend on. Image 2.5 is useful for the **irregular 0.5–8 m
ageing shapes** of old stock, where procedural noise reads as noise.

---

## 1. Current facade visual weaknesses

From the captures above and `xc_wall` [M]:

| # | weakness | where it shows | range |
|---|---|---|---|
| W1 | **One tower grammar.** `res_tower` (and every `huaxia`) is a uniform grid of square dark windows on cream / light grey: no balcony bands, piers, frames or composition. Reads as a generic Asian new town. | `f_rooftops_wuxing` right half, `e_lowpass` right | 100–800 m |
| W2 | **No generation axis.** Palette = archetype + seed. A 2015 tower and a 1988 tower differ only by hash. ~25 % of `res_tower` and ~10 % of `huaxia` are 2000+ [R §18.3, §22]. | all residential | all |
| W3 | **Punched-card windows.** Each bay × floor is a dark rectangle. At 300–800 m that becomes a regular dot grid (`winMean` fade averages it, but 150–400 m shows the grid). | towers / huaxia | 150–400 m |
| W4 | **Ageing is noise.** Streaks (`xc_noise1`), wear (7 m `xc_fnoise`), run-off lines and the humid cast are correct in *value* but uniform in *shape*. No repaint / repair zones, no mould blotches, no tile-replacement patches. | old walk-up / huaxia | 100–400 m (shape), 400–800 m (value) |
| W5 | **Too clean / too cream mid-rise.** Little warm brown / red-brown tile patching on huaxia [R §10.5]. | overview, `roof_mid` | 300–3,000 m |
| W6 | **Windows on every wall.** No blank stepped party walls [R §10.3, M5]. | side walls above low neighbours | 100–1,000 m |
| W7 | **Glass tint is uniform.** Residential glass picks from one green / blue / bronze set; `isTower * 0.3` office mix. No 1990s-teal vs contemporary-neutral split [R §9]. | towers | 100–800 m |
| W8 | No crowns / roof frames on 1990s and 2010s towers [R M4]. | skyline | 300–3,000 m |

Already good, keep as is: old walk-up grammar at 100–300 m (enclosed balconies, cages, AC stacks, sill streaks,
parapet run-off), storefront v0E, frontage roles, school grammar, office curtain wall, range tone / neighbourhood
variation, distance contact ramp, night window logic.

---

## 2. Material-art problems vs shader / geometry / data problems

| weakness | true owner | why |
|---|---|---|
| W1 one tower grammar | **shader grammar** | balcony bands, piers, frames, glazing ratio are rectangles aligned to the floor (`fh`) and bay (`bw`) grid that `xc_wall` already computes. Procedural keeps them exactly aligned, shimmer-free (`xc_detail`), night-correct |
| W2 no generation axis | **data** (era band, class, profile) | the era pipeline exists; it needs a per-building byte and weights (§8) |
| W3 punched-card windows | **shader grammar** | strip windows, paired windows, balcony bands and solid piers change the 150–400 m read; art cannot, because a bay is 4–11 px wide there |
| W4 ageing shapes | **material art (masks)** ✔ | irregular 0.5–8 m shapes: repaint zones, mould blotches, tile-replacement patches, long rain runs. The shader produces either noise or stamped rectangles |
| W5 cream mid-rise | **data** (palette weights) | colour field per building is zero-cost data |
| W6 blank side walls | **data bake + shader** | needs adjacency per wall; once known, the existing stain terms paint the blank wall (art masks help it look aged) |
| W7 glass tint | **data** | per-era glass palette |
| W8 crowns | **geometry** | silhouette; out of scope here |

Research §12 proposed "facade bay modules per generation" as an Image 2.5 atlas. After inspection that is
**rejected for v0**:

* at 100 m a 3.5 m bay is 33 px wide, at 300 m 11 px and at 600 m 5 px. A module picture adds almost nothing
  that a procedural rectangle with a frame line does not;
* baked windows would fight the procedural window, cage, AC, storefront, ground-floor, lobby and night-light layers,
  which all key off the same `(fu, fv)` cell;
* per-family bay pictures multiply cells (bays × floors × colourways), which is the "unique texture library" this
  pilot must avoid.

---

## 3. The four pilot families

Each family is a **parameter set** inside the residential grammar, not a new archetype. Era and class choose the
weights (§8).

### 3.1 Old walk-up / mixed use (F1 low, F2 walk-up)

* **Cues at range:** dirty beige / grey / salmon tile or washed pastel render; enclosed-balcony aluminium columns;
  cages and AC stacks (exist); **owner-by-owner patchiness** (each household repaints / re-tiles / replaces its
  window at a different time); mould at parapets and slab edges; long rain runs.
* **Procedural (keep / add):** palette, bays, cages, AC, streaks. Add **per-household cell variation**: each
  `(bay, floor)` cell gets a small hashed value / hue shift on its wall and frame. It is aligned to the grid, so it
  stays procedural.
* **Generated art:** **macro-ageing masks** (§4.1): irregular repaint / repair zones, mould and stain blotches,
  long rain-run structure. Used at full weight.

### 3.2 Huaxia / 1980s–2000s mid-rise (F3, F4 1990s tile towers)

* **Cues:** regular 45 mm / 二丁掛 tile field (a colour field at range), regular balcony rhythm, **brown / red-brown /
  cream / grey tile** with two-tone floor banding, stone base, teal / green or bronze glass on 1990s towers;
  cleaner than walk-ups, older than contemporary towers.
* **Procedural:** warmer tile palette weights (W5), two-tone band rule (every N floors / top and base), strip windows
  on some buildings, fewer cages above floor 4 (exists), **1990s glass palette** (teal / bronze) by era band.
* **Generated art:** **none of its own.** Reuses the family 1 masks at 0.5–0.7 weight (less repair, same staining).

### 3.3 Modern residential (2000–2019, F5 ordinary)

* **Cues:** painted panel / porcelain / stone, larger glazing, **continuous horizontal balcony bands** (glass
  balustrade over a dark recess, a light slab edge line), **vertical piers or fins** every 2–3 bays, neutral clear /
  grey glass, little clutter (no cages, AC hidden in ledges).
* **Procedural only:** glazing ratio 0.55–0.70, balcony band per floor (rail value band + recess), pier rule
  (`floor(bi / k)`), neutral glass palette, no cages, AC in a ledge strip, light ageing (masks at 0.1–0.2).
* **Generated art:** **none.** Everything here is a floor- / bay-aligned rectangle.

### 3.4 Luxury / premium residential (2010+, premium class)

Must not be "clean huaxia". Distinguished by **composition**, not texture:

* **Cues:** stone or metal frame grid enclosing **double-height** bays (frame every 2 floors), deep reveals
  (darkened 0.3–0.6 m border inside each frame), wide continuous glass balcony bands, restrained 2–3 tone palette
  (warm grey stone + charcoal or champagne metal + neutral glass), a stone base 2–3 floors tall, a lit crown band /
  sky-garden void near the top.
* **Procedural only for v0:** frame grid with a period of 2 floors and 2–3 bays, reveal darkening, champagne / charcoal
  accent palette, stone base, crown band (already partly exists as the night `crown` term).
* **Generated art: held back.** One optional **premium cladding value sheet** (large-format stone with soft
  per-panel value variation + one metal panel field, neutral, tintable) is specified (§6, image P1) but **not in the
  first batch**. Generate it only if review shows the procedural premium grammar reads plastic at 100–250 m. Per-panel
  hashing can likely match it.

---

## 4. Source-art format per family

### 4.1 The only pilot asset: `T_XinyiFacadeAge` (old stock, families 1–2)

**One RGBA texture, one sample, linear (non-sRGB), wall-metric mapping.**

| channel | content | source image |
|---|---|---|
| R | **stain / mould field**: broad soft blotches 1–8 m, slightly darker toward upper edges of blotches, faint downward elongation | A1 |
| G | **repaint / repair zones A**: irregular rectangular-ish patches 1–5 m with soft-to-crisp edges, both lighter and darker than base | A2 |
| B | **rain-run field**: vertical runs 0.2–0.6 m wide, 2–12 m long, starting at irregular heights, fading downward | A3 |
| A | **repaint / repair zones B** (second vocabulary, decorrelated from G, so neighbouring buildings differ) | A4 |

* **Mapping:** the tile covers **32 m × 32 m of wall**. `uv = (u + o_u, h + o_h) / 32` with per-building offsets
  `o_u, o_h` and a horizontal mirror bit from `seed`. Wall metric `(u, h)` already exists (`TEXCOORD_0`).
  Seamless on both axes.
* **No windows in the art.** The masks describe a *blank* wall. The shader applies them to wall pixels only and
  scales them down on glass, frames, cages, AC, storefront and arcade pixels.
* **Neutral greyscale only.** Colour comes from the palette (repaint tone = per-building hashed palette shift), so
  the art never imposes hue.
* **Anchoring stays procedural.** Parapet emphasis, slab-edge drips and sill streaks keep their existing
  floor-aligned terms; the masks give them *shape*:
  `stain_final = stain_mask * (base + topGrime + slabBand)`. Art supplies structure, the shader supplies placement.

### 4.2 Everything else

| family | format | notes |
|---|---|---|
| huaxia | none (reuses 4.1) | weights only |
| modern | none | shader grammar spec in 3.3 |
| luxury | none in v0; optional `P1` value sheet later (would go into a second 512² texture or a spare atlas region) | gated |

---

## 5. Atlas / memory proposal

**Texel density from viewing distance** (1080p, 60° vFOV: `px/m = 935 / d`):

| distance | screen px per metre | a 3.5 m bay | a 2 m repair patch |
|---|---|---|---|
| 100 m | 9.4 | 33 px | 19 px |
| 150 m | 6.2 | 22 px | 12 px |
| 300 m | 3.1 | 11 px | 6 px |
| 600 m | 1.6 | 5 px | 3 px |
| 800 m | 1.2 | 4 px | 2 px |

* Anything finer than ~0.5 m is sub-pixel past ~200 m; anything finer than ~2 m is gone at 800 m.
* A mask needs at most ~**16 texels/m** (1.7× the 100 m screen density, headroom for 60 m passes).
* `T_XinyiFacadeAge` at **1024² over 32 m = 32 texels/m** (PC / authoring); **512² = 16 texels/m** (mobile ship size).
  2048² or 4K are not justified at any game range.

| platform | size | format | memory incl. mips |
|---|---|---|---|
| mobile | 512² RGBA | ASTC 6×6 (≈ 3.56 bpp) | **≈ 0.16 MB** |
| mobile, if ASTC artefacts on masks | 512² RGBA | ASTC 4×4 (8 bpp) | ≈ 0.35 MB |
| PC | 1024² RGBA | BC7 (8 bpp) | ≈ 1.4 MB |
| optional later: premium `P1` | 512² RG | BC5 / ASTC 6×6 | ≈ 0.1–0.35 MB |

Total pilot budget: **≤ 0.35 MB mobile, ≤ 1.4 MB PC.** One texture, one sampler. The existing storefront atlas
(2048², ground-floor band only) is untouched. No normal map: the features are value and roughness changes on a flat
wall seen from 100+ m, and a normal map would add a second sample and a mobile mip / aliasing risk for no visible
gain.

---

## 6. Image 2.5 generation specification

All images are **source material**, not pictures of buildings.

* **Presentation:** strict orthographic elevation of a flat wall surface, camera perpendicular, **no perspective, no
  vanishing lines, no depth**; the wall fills the frame edge to edge.
* **Light:** flat, neutral, shadowless; **no sun direction, no cast or contact shadow, no AO pools, no reflections,
  no specular highlights, no vignette, no DOF, no grain**.
* **Content:** **blank wall, no windows, doors, balconies, pipes, AC units, cages, signs, plants, people, objects**.
  **No text, characters, numbers, logos or brands.**
* **Value:** greyscale, mid-grey base (≈ 0.5), features within ±0.25. **No hue.**
* **Frequency:** mid-frequency only. Shapes 0.5–8 m at the stated scale; nothing finer than ~0.3 m; **no tile grout,
  cracks, chips, moss speckle, fine dirt noise, scratches**.
* **Tiling:** seamless on both axes (or seamless horizontally for strip variants); no feature touches a border in a
  way that breaks the repeat; no single dominant blotch that would read as a stamp.
* **Style:** stylised-grounded game material, clean value shapes like the rest of Skyfront (sky, mountains, trees,
  roads). Not photographic, not scanned.
* **Scale statement in every prompt:** "the image spans 32 m × 32 m of wall".
* **Output:** square, ≥ 1536 px (downsampled offline to 1024 / 512; generated detail above 32 texels/m is discarded
  by design).

Post-processing (offline, deterministic script, later pass): desaturate, normalise to the stated value band, enforce
tiling with an offset-blend check, channel-pack, record source hash and prompt in a sidecar `.json`.

---

## 7. Reject criteria

Reject any generated image on sight if it has:

| defect | why |
|---|---|
| perspective, depth, vanishing lines, visible building edges | not a material; cannot be wall-mapped |
| any window, opening, balcony, pipe, AC unit, sign or object | collides with procedural layers |
| text, characters, digits, logos, brands | forbidden |
| baked light direction, shadows, AO, highlights | double-lights under UE sun; breaks ToD |
| hue / colour cast in a mask | masks must be neutral; colour is data |
| fine detail carrying contrast (< 0.3 m: grout, cracks, speckle, moss) | aliases / shimmers in motion, invisible at range |
| value contrast > 0.35 (0–1) between features and base | camouflage pattern at range |
| visible repeat or one dominant stamp-like shape | reads as a pattern at 300 m |
| photographic grain or scan texture | breaks the stylised world |
| horizontal banding at a fixed period (implied floors) | would misalign with real floor heights; floor structure belongs to the shader |

In-engine reject: masks that make old buildings read **dirtier than evidence** (research: value darkening with
vertical structure, not brown dirt), or any **shimmer** in the 60 m/s flight test at 150 m.

---

## 8. How the current shader would consume the assets

### 8.1 Data

The facade needs **one byte per building** of generation data. The look tiles' existing channels are full
(`TEXCOORD_2` RGBA = arch / variant, seed, weather, flags with bits 0–6 used and bit 7 reserved by the hero tag).
Proposal: add **`TEXCOORD_3`** (packed RGBA8 per vertex; vertex data only, no geometry change) =
`(era_band 0–5, class 0–2, profile_id, spare)` [U: confirm the mobile vertex-UV budget, now 3 of 8].

Facade weights, never a hard dependency on a year:

```
family weights w[old, huaxia, modern, premium] =
    archetype prior (walk-up / low -> old; huaxia -> huaxia; res_tower -> huaxia (1990s tile tower))
  x era multiplier          (pre_1980, 1980_1999 -> old / huaxia;  2000_2009 -> modern;  2010+ -> modern / premium)
  x era confidence blend    (exact / range: full;  inferred: half toward the prior;  unknown: prior only)
  x district profile        (CityProfile JSON: premium share, red-tile share, ageing strength)
  x class                   (premium only when class = premium or profile assigns it to 2010+ towers)
```

* **Unknown era** (84 % of Xinyi groups today; all of a region without age data) uses the archetype prior. That
  keeps today's look for old stock, which is correct for ~90 % of walk-ups and ~72 % of huaxia [R §22].
* **Observed 2000+** (permits) is exactly the share where the current error concentrates, so the partial coverage
  still targets the right buildings.
* The pick is deterministic per building: highest weight, ties broken by `seed`.

### 8.2 Shader (`xc_wall`, later pass)

* New texture-object input `AgeTX` on `M_XinyiCity`'s Custom node, wired like `ShopTX` / `PlanTX`. Same material,
  no new draw call.
* Per-building coherent branch: `ageW = familyAgeing * weather * (1 - isOffice) * (1 - isCivic)`
  (schools keep their own grammar). Inside `[branch] if (ageW * dMacro > 0)`:
  * one `SampleGrad` at `(u + o_u, h + o_h) / 32`, gradients from `fwu` / `fwh` (explicit, since we are inside a
    branch);
  * `stain = m.r * (0.6 + topGrime + slabBand)` → `c *= 1 - stain * 0.30 * ageW`;
  * `repair = lerp(m.g, m.a, seedBit)` → `c = lerp(c, c * repaintTone, repair * 0.5 * ageW)`, with `repaintTone`
    a hashed ±8 % value shift with a slight palette lean;
  * `runs = m.b * (streakN gate)` adds to the existing streak term, replacing part of the `xc_noise1` streak;
  * all three are masked to wall pixels: `* (1 - win) * (1 - cageCover) * (1 - ac) * (1 - arcade)`.
* Distance: `lerp(maskMean, mask, xc_detail(max(fwu, fwh), 6.0))`. Beyond ~1 km the result equals the mean
  darkening, so the range tone / neighbourhood terms keep owning the far read and nothing shimmers.
* Night: base colour only; emission untouched.
* Modern / premium grammar: pure ALU additions in the same function, behind the same per-building family branch
  (the rooftop-pass lesson: coherent per-building branches, not per-pixel blending of all families).

---

## 9. Expected mobile cost

| item | cost | note |
|---|---|---|
| texture memory | 0.16–0.35 MB (mobile), 1.4 MB (PC) | one texture |
| texture samples | +1 on old-stock wall pixels within ~1 km; 0 on glass towers, offices, roofs, schools, far city | coherent branch |
| ALU | small: 3 lerps + mask gating; modern / premium grammar ≈ the cost of today's old-stock cage / AC terms | |
| vertex data | +4 bytes per vertex (`TEXCOORD_3`) on 25 tile meshes | small |
| draw calls / materials | **0 / 0** | existing `M_XinyiCity` |
| expected frame cost | **≈ +0.1 … +0.4 ms** on the UHD 770 1080p harness [I] | to be measured |

Risk [R memory of v0E]: facade cost at mid / high quality can be **register pressure**, not per-pixel work. Measure
with the interleaved same-session harness (fresh old / new materials built together, alternating rounds, both
orders). Reject anything above **+0.5 ms** in any review view.

---

## 10. Planned A/B review

**States** (all in one UE session, materials built fresh together):

* **A** — HEAD (`a9c58d6`).
* **B** — procedural only: era / class weights + modern / premium grammar + huaxia palette + per-household cell
  variation. No texture.
* **C** — B + `T_XinyiFacadeAge`.

The art must beat **B**, not A. If C does not clearly beat B on old stock, the texture is not shipped.

**Cameras:** existing `rp_low150`, `rp_steep_ne`, `roof_ne1`, `roof_mid`, `f_rooftops_wuxing`, `e_lowpass_xinyi_rd`,
plus four new fixed facade-facing obliques (horizon-ish 10–25° pitch, so walls fill the frame):

| shot | distance to subject | subject |
|---|---|---|
| `fa_150_wuxing` | 150 m | Wuxing walk-up / huaxia street wall |
| `fa_300_towers` | 300 m | mixed 1980s–2010s residential towers (`f_rooftops_wuxing` cluster) |
| `fa_600_mixed` | 600 m | old fabric with towers behind |
| `fa_800_overview` | 800 m | district overview including core |

DAY mandatory; one DUSK frame per state; NIGHT only if base colour changes affect lit windows.

**Pass criteria:**

| criterion | pass |
|---|---|
| generation read (B vs A) | at 150 / 300 m, 3 reviewers can sort 6 marked buildings into old / 1990s / modern / premium better than chance in ≥ 2 of 3 blind trials |
| premium ≠ clean huaxia | premium towers identified as premium in ≥ 2 of 3 trials at 300 m |
| ageing shape (C vs B) | old stock reads "aged, repaired" rather than "noisy" in ≥ 2 of 3 blind trials at 150 / 300 m |
| no new noise | 2-frame diff in a 60 m/s pass at 150 m shows no new shimmer |
| style fit | facades not more photographic than trees / roads in the same frame |
| far read | 600 / 800 m: no regression of range tone; no visible repeat of the 32 m mask |
| cost | ≤ +0.5 ms per view (interleaved, same session); memory ≤ 0.35 MB mobile |
| regression | storefront v0E, schools, roofscape v2, offices, Taipei 101, night lighting pixel-identical outside changed walls |

---

## 11. Image 2.5 generation queue — first batch (4 images)

All four are **greyscale masks for old stock**. Common suffix for every prompt:

> *"Seamless tileable game material source, strict orthographic front elevation of a flat blank wall, camera exactly
> perpendicular, no perspective, no depth, flat neutral shadowless lighting, no sun, no cast shadows, no highlights,
> no reflections, no ambient occlusion, greyscale only, no colour cast, mid-grey base, low contrast, mid-frequency
> shapes only, no fine detail, no tile grout, no cracks, no speckles, no noise, no windows, no doors, no objects, no
> text, no letters, no numbers, no logos, stylised-grounded 3D game art, clean soft value shapes, not photographic.
> The image spans 32 m × 32 m of wall."*

**A1 — `age_stain_field` (→ R)**
> "Value map of humid-climate weathering on an old concrete and tile apartment wall in Taipei: broad soft-edged
> darker blotches 1 to 8 metres across where damp and mould collect, some slightly elongated downward, irregular
> spacing, about a third of the surface affected, the rest an even mid-grey. Blotches are soft and low contrast,
> darkest no more than 25 percent below the base. No horizontal bands, no regular grid, no single large stain." +
> suffix.

**A2 — `age_repair_zones_a` (→ G)**
> "Value map of owner-by-owner repairs on an old Taipei walk-up wall: irregular, roughly rectangular patches 1 to 5
> metres wide where sections were repainted or re-tiled at different times, some slightly lighter, some slightly
> darker than the mid-grey base, edges partly crisp and partly feathered as if painted by roller, a few patches
> overlapping, patches cover about a quarter of the surface, scattered without alignment to any grid." + suffix.

**A3 — `age_rain_runs` (→ B)**
> "Value map of rain run-off streaks on a tall old apartment wall: soft vertical darker streaks 20 to 60 centimetres
> wide and 2 to 12 metres long, each starting at a different height and fading out downward, irregular spacing of
> 1 to 4 metres, some grouped, some isolated, very soft edges, low contrast against an even mid-grey base, strictly
> vertical, no horizontal lines." + suffix.

**A4 — `age_repair_zones_b` (→ A)**
> "Value map of patched maintenance on an ageing Taipei mid-rise wall, different from a typical repaint pattern:
> fewer, larger patches 2 to 6 metres, mostly slightly lighter fresh-paint or fresh-tile zones with clean straight
> edges on one or two sides and soft edges elsewhere, plus a few narrow vertical repair strips 0.5 to 1 metre wide,
> patches cover about a fifth of the surface, irregular placement, mid-grey base." + suffix.

**Held back (not in the first batch):**

**P1 — `premium_cladding_values`** (generate only if the procedural premium grammar fails review)
> "Value map of a premium residential facade cladding field: large-format stone panels about 1.2 by 0.6 metres in a
> running bond with soft per-panel value variation within plus or minus 8 percent, joints only implied by the
> value change between panels (no drawn grout lines), plus a band of brushed metal panels 1 metre wide with very faint
> vertical value variation, no veining, no texture grain, mid-light grey base, seamless, the image spans 8 m × 8 m."
> + suffix (replace the last sentence of the suffix with the 8 m scale).

---

## Files

New: `docs/xinyi-facade-material-pilot-v0.md` only. No runtime, shader, asset or data change.
