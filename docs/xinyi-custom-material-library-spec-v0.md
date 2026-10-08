# Xinyi / Taipei custom material library — spec v0

Status: **doc-only spec.** Nothing here is built, generated or approved. No shader, Unreal asset, image or runtime change.
Branch `feat/opus55-xinyi-visual-quality`, on top of `e17b35e` (blank side-wall v0B).

Builds on, and does not replace: `docs/xinyi-facade-material-pilot-v0.md` (the facade-ageing mask pilot and its
texel-density table), `docs/xinyi-facade-grammar-v0a.md`, `docs/xinyi-roofscape-v2-material-pilot.md`,
`docs/xinyi-wall-ads-v0-result.md`, `docs/xinyi-blank-side-wall-v0b-result.md`,
`docs/taipei-urban-visual-language-research-v0.md`. Where this document and the pilot disagree, this one is newer.

Evidence tags: **[M]** measured on this repo's current build · **[R]** from an earlier project document ·
**[I]** my judgement, not tested · **[P]** proposal.

---

## 0. Short answer

* **Yes, a small custom source library is worth having; no, not a big one.** Estimate: **MVP 8-10 source images
  packed into 3 runtime textures; "good Taipei" 24-32 source images packed into ~8 runtime textures.** Both fit a
  mobile budget of ~1-2 MB of texture memory in total. [I]
* **The library is mostly masks, not pictures.** The city already has the right *grammar* (frontage roles, generation
  classes, storefront and wall-ad atlases, roof covers). What reads "synthetic" is that surfaces are too uniform in
  *shape* at 150-400 m: stains, repairs, tile fields and roof coverings are noise or flat colour. Greyscale masks that
  carry irregular 1-8 m shapes fix that without photographic colour.
* **Biggest expected win: old-stock walls plus roofs, together, as shared masks** (old stock is ~4,800 legacy +
  ~3,900 huaxia of 11,124 ordinary records [M, v0A counts], and roofs are the largest visible area in an oblique
  aerial view). Facade *pictures* (bay modules, photo tiles) are the wrong investment. [I]
* **Biggest risk: expecting materials to fix grammar.** Generation, composition (bands, piers, crowns) and window
  rhythm are procedural by design; a texture cannot change them and would bake geometry that cages, AC, storefronts
  and night lights depend on. If the first mask pack gives only a small improvement, the remaining "juvenile" feel is
  a grammar / palette problem, not a missing-asset problem.
* **None of the benefit estimates below has been tested.** Batch 1 is chosen so that one texture can be A/B'd first.

---

## 1. Design constraints that shape the library

### 1.1 Viewing range decides the texel budget

From the pilot's table (1080p, 60° vFOV, `px/m = 935 / d`) [R]:

| distance | px per metre | 3.5 m bay | 2 m patch |
|---|---|---|---|
| 150 m | 6.2 | 22 px | 12 px |
| 300 m | 3.1 | 11 px | 6 px |
| 600 m | 1.6 | 5 px | 3 px |
| 800 m | 1.2 | 4 px | 2 px |

Rules that follow:

* Nothing finer than ~0.5 m matters past ~200 m; nothing finer than ~2 m matters at 800 m. Source art is designed
  at **1-8 m features** and must still average to a stable value when those features are sub-pixel.
* **Texel density: 12-16 texels per metre of wall or roof** is the ceiling (mobile 512² over 32 m = 16 texels/m).
  Wall-metric mapping, not UV unwrap: tiles use the existing `(u, h)` coordinates (`TEXCOORD_0`), roofs the existing
  tile-local roof coordinates.
* Hard budget: **one new texture sample per surface class** (wall or roof), not per mask. Masks are channel-packed.

### 1.2 What stays procedural (all families)

Window / bay rhythm, floor alignment, balconies, cages, AC placement, frontage-role logic, storefront layout, night
window light, glass tint, composition (two-tone bands, piers, frame grids, crowns), range tone, distance contact
ramp, roof cover placement and seams. These are already generation-aware and need exact alignment to geometry that
art cannot know. **Generated art never contains windows, doors, floor lines or lighting.**

### 1.3 Colour comes from palettes, not from art

All masks are **neutral greyscale, linear, non-sRGB**. Hue and value come from the existing per-building palettes
(`xc_gen_palette`, `xc_tile_palette`, roof `xc_sheet16`), so a mask can be recoloured or reused across generations,
districts and later cities without a new image. This is the main lever that keeps the library small.

---

## 2. Families: what is procedural, what is generated

Legend — **Form:** `P` palette / shader only · `M` greyscale mask (channel-packed) · `T` full-colour tiling ·
`A` atlas of authored cells (text / graphics) · `D` decal (placed card).

### 2.1 Legacy walk-up / mixed-use old stock (≈ 4,800 records)

| | |
|---|---|
| Stays procedural | grid, enclosed balconies, cages, AC stacks, sill streaks, parapet run-off, ground-floor logic, tile grain (`tileGrain`), palette and finish family |
| Generated source | **macro-ageing mask pack (M):** stain / mould field, repaint-repair zones ×2, rain-run field |
| Optional | **old tile-field value sheet (M):** irregular 二丁掛 / 馬賽克 patches, patched-over tile, exposed render, repaired bands — only if the ageing mask pack leaves walls reading flat |
| Form | one RGBA packed mask (pilot's `T_XinyiFacadeAge`); no colour |
| Not needed | full-colour wall texture; per-floor bay pictures |

### 2.2 Huaxia / 1980s-90s mid-rise residential (≈ 3,900 records)

| | |
|---|---|
| Stays procedural | two-tone tile banding, orderly 2-3 bay rhythm, stacked balcony columns, teal / bronze glass choice |
| Generated source | **none of its own**: reuses the §2.1 masks at lower weight and a different palette weight |
| Optional (Batch 3) | **tile colour-field value sheet (M):** the broad tile-brown / cream / salmon patchiness of 1990s tile towers (variation at 3-10 m, not tile joints) |
| Form | shared mask; palette-only otherwise |

### 2.3 Modern residential tower (≈ 1,250 records)

| | |
|---|---|
| Stays procedural | bay-to-bay glazing, slab lines, pier / ribbon composition, balustrade bands, clean services |
| Generated source | **none.** Maintained buildings should look cleaner than old stock; the only honest need is subtle panel-joint / porcelain-sheet value variation, which is a 2-3 m checker of 3-4 values and is cheaper as a hash |
| Form | `P` only |

### 2.4 Premium / luxury residential tower (≈ 160 records)

| | |
|---|---|
| Stays procedural | frame grid with deep reveal, glass balustrade per floor, sky-garden crown void, stone podium |
| Generated source | **none in MVP.** One optional **stone / cladding value sheet (M, 512²)** with 1-3 m panel variation, only if a premium tower fails review at 150-300 m |
| Form | `P`; optional single `M` |
| Cap | ≤ 160 records: a bad return on any custom art |

### 2.5 Office / podium / commercial base

| | |
|---|---|
| Stays procedural | curtain-wall module, spandrel, coated / clear glass families, podium glass bands, LED panels |
| Generated source | **podium signage / banner atlas (A)** — *already partly covered* by wall ads (podium banners were deferred, ≤ 3 in Xinyi). **Commercial-base atlas (A):** department-store / bank / hotel podium graphic bands (lettering-free coloured fascia, canopy tones) |
| Form | `A` for fascia bands; `P` otherwise |
| Not needed | glass-tower art: reflections come from SkyLight / environment, and a baked picture would fight lighting |

### 2.6 Roofs (largest visible area)

Already procedural and generation-aware (Roofscape v2: palette, lot-filling sheet-metal covers with local-orientation
seams, flat-concrete variation, rooftop props) [R].

| | |
|---|---|
| Stays procedural | cover placement, lot-filling geometry, seam direction, props (tanks, AC, antennas, bulkheads), parapet |
| Generated source | **roof surface mask pack (M, RGBA):** flat-concrete / waterproof-membrane patchiness (R), patched-and-repainted zones (G), puddle / drainage stain and rust bleed (B), tar-and-gravel / paint-chip scatter at 0.5-1 m (A) |
| Optional | **roof cover wear sheet (M):** corrugated-sheet fading, rust blooms and re-sheeted bays for 頂樓加蓋 covers |
| Form | one RGBA mask; wall and roof masks may share one authoring pass but are sampled by different surface classes |
| Why it ranks high | at 300-800 m oblique, roofs dominate the screen; today's roof variation is value noise |

### 2.7 Construction / site layer (future, not built)

| | |
|---|---|
| Stays procedural | site footprint, hoarding line, crane / frame geometry, net colour (blue and green), scaffold lines |
| Generated source | **hoarding / wrap atlas (A):** non-text decorative graphic bands, project-teaser panels with *invented* project names, planted-wall green panel, safety-net tiles |
| Form | `A` (≤ 8 cells, shares the wall-ad atlas pipeline and fonts); net and scaffold are `P` |
| Rule | observed wraps were blue netting and decorative panels without readable text; text only in the project panel [R, wall-ads §K] |

### 2.8 Supporting decals and masks

| item | form | note |
|---|---|---|
| storefront atlas, sign atlas, storefront plan | `A` | **exist** (v0B / v0E) |
| wall-ad atlas | `A` | **exists** (34 cells) |
| blank-wall finish | `P` | **exists** in `xc_wall`; could later borrow §2.1 masks (free once they exist) |
| stain / grime decals | **not recommended** | decal passes add overdraw and draw calls; the masks do the same job at no extra pass |
| tile-pattern "closeup" textures | **not recommended** | below 0.5 m; invisible past 200 m |
| photographic PBR sets | **rejected** | breaks the world's stylisation; see §5 |

---

## 3. Material count estimates

"Source image" = one distinct authored image or channel plane; "runtime texture" = one packed texture asset.

| scope | source images | runtime textures | memory (mobile ASTC 6x6, with mips) | memory (PC BC7) |
|---|---|---|---|---|
| **existing, already shipped** | 4 atlases (sign, shop, plan, wall-ad) | 4 | ~3-5 MB (2048² each) | ~16 MB |
| **MVP (new)** | 8-10 | 3 | ~0.5 MB | ~2.8 MB |
| **fuller "good Taipei" (new)** | 24-32 | ~8 | ~2-3 MB | ~9-12 MB |
| **later cities / North Taiwan** | +6-10 per district style | +2-3 | palette swap first | |

How the MVP count arises: facade ageing mask pack 4 channels + roof surface mask pack 4 channels = 8 source planes in 2
runtime textures; +1 optional old tile-field value sheet; + 1 podium / commercial fascia band atlas (small). The
"fuller" count adds the huaxia tile field, premium cladding, roof cover wear, 3-4 colour-variant sets of the ageing
packs (independent *base* patterns, not recolours), construction atlas (6-8 cells) and a second wall-ad / banner atlas
page. Counts are estimates; they are sized by what is *distinct in shape at 150-800 m*, not by building count. [I]

Independent patterns vs variants: the library should contain **~12 independent base patterns at MVP-plus, ~24 at
"good Taipei"**; everything else (recolour, mirror, rotation by 90°, per-building offset, channel swap) is derived in
the shader from existing per-building hashes at zero asset cost. A library that grows by copying and tinting a few
patterns will show repetition at 300 m; derive variation, do not pre-bake it.

---

## 4. Prioritisation

### Batch 1 — highest value (MVP): 3 runtime textures, 8-10 source images

| # | asset | form | families | why first |
|---|---|---|---|---|
| 1.1 | **`T_XinyiFacadeAge`** (4 planes: stain / mould, repair A, rain-run, repair B), 1024² authoring, 512² mobile | RGBA `M` | legacy, huaxia, blank side walls | the pilot's one justified asset; fixes W4 (ageing is noise) |
| 1.2 | **`T_XinyiRoofSurface`** (4 planes: patchy membrane, repaint zones, drainage / rust, gravel scatter), 512² | RGBA `M` | all roofs | roofs dominate aerial frames; today value-noise only |
| 1.3 | **`T_XinyiPodiumFascia`** (6-8 cells: department-store band, bank / hotel band, canopy tones; lettering-free) | `A` | office / podium, commercial base | podiums currently share the glass-band grammar; small and cheap |

### Batch 2 — next layer

| # | asset | form | families |
|---|---|---|---|
| 2.1 | old tile-field value sheet (二丁掛 / mosaic patchiness) | `M` 512² | legacy, huaxia |
| 2.2 | roof cover wear sheet (re-sheeting, rust blooms) | `M` 512² | old-stock covers |
| 2.3 | construction hoarding / wrap atlas (6-8 cells) | `A` 1024² | construction layer (with the construction kit, not before) |
| 2.4 | second variant set of 1.1 and 1.2 (independent patterns, not recolours) | `M` | repetition control |

### Batch 3 — optional / nice-to-have

* huaxia tile colour-field sheet; premium stone / cladding sheet (only if a premium tower fails review);
* banner / podium-promotion page 2 of the wall-ad atlas;
* district-specific style packs for later cities (see §7);
* any decal system (not recommended).

---

## 5. Visual-language guardrails

The world around buildings (sky, mountains, trees, roads, clouds) is flat-shaded, value-driven and filtered toward
its mean; materials must sit inside that language.

| failure to avoid | guardrail |
|---|---|
| too photographic | no photographs, no scan-like grain; shapes are simplified, edges soft-to-crisp, 4-8 distinct value steps max per plane; no specular detail baked in |
| too noisy | **no feature under ~0.4 m**; dominant features 1-8 m; the plane's mean must be near mid-grey so it averages to the palette at range; no high-frequency speckle (it shimmers in motion — measured as crawling text/specks in earlier passes) |
| too micro-detailed | no cracks, individual tile joints, bricks, pipes; those are sub-pixel past 200 m |
| too Western | Taiwanese vocabulary: 二丁掛 / mosaic / washed-stone render, 鐵窗 and 鐵皮加蓋 rust, rain-run under parapets and AC; no brick, clapboard, brownstone or graffiti |
| too cyberpunk | no emissive in art, no neon colours, no gradients-as-glow; night lighting stays in the shader |
| too dirty / ruined | maintained legal-compliance look (Taipei requires intact ads and façades): staining max ~25 % darkening, repair patches ±12 % value; no peeling, no collapse, no vegetation overgrowth |
| too saturated | art is **greyscale**; colour only from palettes, which already cap saturation (≤ ~0.65 on large fields) |
| inconsistent family look | all planes drawn from one shared shape vocabulary (soft rectangles for repairs, vertical runs for rain, irregular blotches for mould); every plane tileable on both axes; one authoring style sheet |
| baked lighting | no shadows, highlights or ambient occlusion in the art |

Acceptance test for every plane (cheap, offline): box-downsample ×8 and ×16 — it must look like a near-uniform tone,
not a pattern; and place it on a flat wall at 150 / 300 / 600 / 800 m in the existing capture harness.

---

## 6. Image 2.5 usage plan (later; nothing generated now)

All outputs are **source material**: greyscale, seamless, square power-of-two, no text, no windows, no lighting.
Text (podium fascia, construction panels) stays font-rendered in the existing atlas builders. Every image is post-processed
offline (levels, tiling check, channel pack) and committed as a lossless review set with its prompt, seed and hash.

| order | asset | purpose | size / atlas strategy | why Image 2.5 (not procedural) |
|---|---|---|---|---|
| 1 | **A1 stain / mould field** | irregular 1-8 m blotch shapes with plausible edge behaviour | 1024², seamless; → R of `T_XinyiFacadeAge` | procedural noise gives uniform blob shape; this is the one thing noise does badly |
| 2 | **A2 / A4 repair-repaint zones** (two decorrelated vocabularies) | rectangular-ish patches, lighter and darker | 1024² each; → G, A | irregular, human-made patches (not random blobs) |
| 3 | **A3 rain-run field** | vertical runs 2-12 m, irregular start heights | 1024²; → B | broken, varied runs beat periodic noise |
| 4 | **R1 roof membrane patchiness** | roof-surface macro variation | 512² or 1024²; → R of `T_XinyiRoofSurface` | same shape-vocabulary argument as A1 |
| 5 | **R2 roof repaint / patch zones** | irregular rooftop repairs | 512²; → G | |
| 6 | **R3 drainage / rust bleed** | stain streaks from roof edges and equipment | 512²; → B | |
| 7 | **R4 gravel / paint-chip scatter** | 0.5-1 m scatter for near roofs | 512²; → A | lowest priority within Batch 1; may stay procedural |

Do **not** use Image 2.5 for: building elevations or bay pictures; any text, signage or Chinese lettering; windows or
doors; photographic textures; logos; anything containing a recognisable real building. Prompts must say *flat
greyscale mask, no perspective, no lighting, seamless tile*. Generate 4-8 candidates per plane, pick, then derive
variants in shader.

---

## 7. Extensibility to North Taiwan and other cities

* The mask library is style-neutral (shapes only); a new city re-uses it and swaps **palette data** (`FacadeProfile`,
  roof palettes, `CityProfile`). Expect to need new masks only for distinctive materials, not for a different city.
* Add per-district packs only when a district's building language differs materially (e.g. an old harbour district
  with weathered concrete, or a hillside village with corrugated roofs): 1 facade pack + 1 roof pack each.
* Keep packs identified by `acw.material_pack/0` metadata (source images, prompts, seeds, hashes, intended channels)
  so the audit trail survives regeneration.

---

## 8. Minimum viable library

The smallest believable set that can make Xinyi read coherently:

1. `T_XinyiFacadeAge` (4 planes)
2. `T_XinyiRoofSurface` (4 planes)
3. everything else unchanged (storefront, sign, wall-ad atlases; procedural grammar; blank side walls)

**≈ 8 source images, 2 runtime textures, ~0.35-0.5 MB mobile.** Podium fascia can wait. This pair covers old stock
walls, huaxia, blank walls and roofs — the areas with the largest screen share and the weakest shape variation.

---

## 9. Risks and open questions

| risk | mitigation |
|---|---|
| **Materials cannot fix grammar.** The remaining synthetic read may be window-grid / composition / palette, not surface shape. | A/B the one-texture pilot (`T_XinyiFacadeAge`) before commissioning anything else; the pilot's expected cost (+1 sample on old-stock pixels within ~1 km) is small enough to test cleanly |
| Global shader tax. Facade v0A showed always-on terms cost +1.5 ms; blank-wall v0B showed an extra pre-composition branch cost +0.1-0.3 ms while a chain arm cost ~0. | any new sample goes inside existing coherent per-building branches; measure with same-session interleaved A/B on LOW / MID / HIGH |
| Repetition at 300 m from a 32 m tile. | per-building offset + mirror + two decorrelated plane sets (2.4); derive, don't copy |
| Mobile compression artefacts on soft masks (ASTC block edges). | fallback ASTC 4×4 (0.35 MB) before enlarging the source |
| Style drift between generated planes. | single style sheet and a shared review contact sheet per pack |
| Evidence limit: visual benefit is unmeasured; counts and benefit ranking are my estimates. | state this in the result doc of any later pass; judge by captures, not by this spec |
| IP / provenance of generated art. | no real buildings or brands in prompts; record prompt + seed + hash per image |

---

## 10. Final recommendation

* **Do we need custom-generated materials?** Yes, but as a small set of greyscale shape masks that the existing
  palettes colour. We do **not** need a facade-picture library, photo-PBR sets, decal systems or per-generation tile
  textures; the procedural grammar already owns those jobs.
* **How many?** MVP ≈ **8-10 source images in 3 runtime textures** (2 are the essential ones); "good Taipei" ≈ **24-32
  source images in ~8 textures**. Beyond that, derive variants in the shader.
* **What first?** The pilot's **facade ageing mask pack**, immediately followed by the **roof surface mask pack**, as one
  Batch 1. If forced to pick one: roofs have more screen area and today's roof variation is only value noise, but old-stock
  walls cover more building records and are where the pilot's design is already written and costed. I would generate
  both in one session and A/B them independently (one environment switch per texture, as for wall ads and blank walls), so the data decides.
* **Do not** start Batch 2 (construction atlas, tile fields, variants) until Batch 1 has passed same-session A/B
  captures at 150 / 300 / 600 / 800 m and a motion check.
