# Taipei Facade Grammar v0A — classification calibration + procedural residential generations

Status: **complete — procedural v0A accepted for review; no Image 2.5 assets generated.**

Branch `feat/opus55-xinyi-visual-quality`, on top of `a5b3bad` (facade generation metadata payload).
Inputs: `docs/xinyi-facade-metadata-payload-v0.md`, `docs/xinyi-facade-material-pilot-v0.md`,
`docs/taipei-urban-visual-language-research-v0.md` (§18.3 measured decades, §20 readability, §21 taxonomy).
Evidence (local, not committed): `unreal/Saved/XinyiLook/evidence/facade_grammar_v0a/`.

---

## 0. Gate 0 — payload runtime parity: **PASS**

Method: pre-payload state captured first (current UE content = accepted Roofscape v2 step 2), the payload tiles
rebuilt from HEAD (`build_look_tiles.py`, era cache on), UE asset + level stages from HEAD, captured again in fresh
processes. For DUSK / NIGHT the pre-payload tiles were restored, the UE stages re-run and the same views captured,
so both sides are same-machine, same-day, fresh-process captures.

* Offline: `verify_facade_payload.py` — 25 tiles, 991,557 vertices, positions / normals / TEXCOORD_0/1 / indices /
  TEXCOORD_2.y bit-identical, TEXCOORD_2.x identical once the payload is stripped (`PASS_NO_VISUAL_CHANGE`);
  `urban_identity/` outputs SHA-identical.
* DAY, 17 accepted cameras (skyline, overview, low pass, Wuxing rooftops, 101 close pass, SYS hall, roof_mid /
  ne1 / ne2, rp_low150 / steep_ne / top_wuxing, storefront `cb_songqin_arcade` / `sf_cvs_wuxing` / `st_wuxing`,
  frontage `fr_corner_b` / `fr_block_e420`): **16 / 17 bit-identical**. `a_skyline_nw` differs by uniform speckle
  (mean 0.795 / 255) — the same signature as two pre-payload sessions of that view (step-2 frame vs today: mean
  0.797). Renderer run-to-run noise, not payload.
* DUSK / NIGHT, 11 cameras each: **9 / 11 bit-identical** each; the other two differ in 2–4 pixels on one red
  rooftop aviation obstruction light (animated emissive, off by day).
* Facades, storefront v0E, schools (roof_ne1 / ne2), roofs, geometry: no change. No decode corruption.

## 1. Classification strategy (final)

Precedence per building group (unchanged order, one new layer):

```
not applicable (office / podium / civic / school / registry landmark)       -> unknown (archetype grammar)
observed era   (permit, exact | range)                                       -> family of the era band
inferred era   (profile_inference record, none ship today)                   -> family of the era band
profile draw   (acw.facade_profile/0, NEW)                                   -> family of the drawn band, or unknown
no profile     (--no-facade-profile: the v0 morphology prior, bit-identical) -> legacy / huaxia / unknown
```

**Generic code** (`tools/lookdev/facade_generation.py`, no regional numbers, no Taipei import):

* era buckets fold to three **bands**: `pre_1980`, `1980_1999`, `2000_plus`; a band maps to a visual family per
  archetype (`family()`): pre-1980 -> legacy; 1980-99 -> huaxia, except low / walk-up stock, which stays legacy
  (a 1985 5 F walk-up is still a walk-up); 2000+ -> modern, or premium by the premium draw;
* `FacadeProfile.posterior(arch, floor_h, core, era_consulted)` =
  band prior (zone x archetype) x floor-height likelihood ratio x (1 - evidence recall) for bands the consulted era
  source would have found, plus an explicit `unknown` mass;
* the group draws its band from that posterior with `unit_hash(group id, "band")` (SHA-256, order and platform
  independent); a 2000+ band (observed or drawn) becomes premium when `unit_hash(group id, "premium")` falls under the
  profile's premium share x floor-height x floors x bucket factors;
* no year is read, stored or invented. The payload still carries only the 3-bit class; provenance (`profile`,
  `observed_era`, ...) stays in the sidecar / report.

**Profile layer** (`tools/lookdev/profiles/facade_taipei_xinyi_v0.json`, chosen by the builder, `--facade-profile`
/ `--no-facade-profile`):

| field | value | source |
|---|---|---|
| band prior, outside core | walk-up 81 / 15 / 3 %, huaxia 25 / 64 / 9 %, res_tower 14 / 62 / 25 %, low 62 / 22 / 15 % | research §18.3 (age layer, matched Xinyi groups) |
| band prior, planned core | huaxia 5 / 55 / 40 %, res_tower 2 / 50 / 48 %, low-rise 65 % unknown | assumption (district built from the 1980s), documented |
| floor-height likelihood (6+ F only) | 2000+ x0.20 (<= 3.05 m), x0.42 (<= 3.35), x2.0 (<= 3.6), x4.4 (> 3.6) | **measured this pass**: era-confirmed 2000+ vs no-era groups outside the core (n = 209 / 1,275). Walk-up / low show no signal -> 1.0 |
| evidence recall, 2000+ | 0.85 | permit-confirmed 2000+ share of outside-core 13-24 F groups (27 %) already equals the age layer's 25 %: the permits find almost all of them. 0.85 is deliberately below that |
| premium share of 2000+ | res_tower 22 % (core 45 %), huaxia 5 % (core 15 %); x0.3 ... x1.6 by floor height, x0.5 ... x1.4 by floors, x0.7 (2000-09) / x1.4 (2010+) | assumption, documented; capped at 0.85 |

The profile is global data: no building id, no per-building exception, no tolerance tuned on a frame.

### 1.1 Counts (11,124 ordinary records / 4,137 groups)

| generation | committed v0 (records / groups) | **v0A (records / groups)** |
|---|---|---|
| legacy | 3,607 / 1,687 | **4,835 / 2,027** |
| huaxia | 4,626 / 1,270 | **3,918 / 1,113** |
| modern | 1,146 / 499 | **1,256 / 556** |
| premium | 7 / 4 | **159 / 51** |
| unknown | 1,738 / 677 | **956 / 390** |

| basis | records | groups |
|---|---|---|
| observed era (permit) | 1,153 (1,021 modern + 132 premium) | 503 |
| profile-derived | 9,015 (4,835 legacy, 3,918 huaxia, 235 modern, 27 premium) | 3,244 |
| genuinely ambiguous (profile unknown mass / >40 F) | 104 | 87 |
| not applicable (office, podium, civic, school, landmark) | 852 | 303 |

By archetype (records): low 1,271 legacy / 221 modern / 97 unknown; walk-up 2,334 legacy / 66 modern;
huaxia 1,044 legacy / 3,077 huaxia / 665 modern / 54 premium; res_tower 186 legacy / 841 huaxia / 304 modern /
105 premium / 7 unknown; office / podium / civic / school all unknown (their own grammars).

By zone (records): **planned core** 77 legacy / 588 huaxia / 420 modern / 65 premium / 736 unknown (mostly
office / podium / civic, plus ambiguous low-rise); **outside** 4,758 legacy / 3,330 huaxia / 836 modern / 94 premium /
220 unknown.

Transitions from the committed v0 classification (records): 1,191 morphology-huaxia records (6-24 F) become legacy
(the measured pre-1980 share of elevator mid-rises and towers); 117 become modern / premium (high floor-to-floor
height); 782 previously undecidable records (planned core, > 24 F) become 600 huaxia / 77 legacy / 87 modern /
18 premium; 125 observed-modern records become premium; 40 morphology-legacy records become modern. No observed era
record changes band.

Finding worth keeping: **permit coverage is not the bottleneck in this bbox.** The permits already confirm about as
many 2000+ residential groups as the age layer predicts, so a profile cannot honestly add many modern buildings outside
the core. The visible problem was that the shader ignored the 1,146 observed-modern records; v0A fixes that. Premium
needed a profile share because no data source identifies luxury class.

An offline debug map (`evidence/facade_grammar_v0a/sheets/debug_generation_map.png`) and a harness-only false-colour
material (`harness/debug_shader.hlsl`, `MExpG_D_city`) were used for review; neither is shipped.

## 2. Procedural grammar (`tools/lookdev/shaders/xinyi_city.hlsl`, `xc_wall`)

`gen` is decoded once in the `M_XinyiCity` Custom node (`xc_unpack_tile`) and passed `xc_city` -> `xc_wall`
(`M_Taipei101` passes 0). It is constant per building and non-zero only on residential archetypes, so every new term
is either a constant lerp or sits in a coherent per-building `[branch]`. Unknown (0) and legacy (1) take exactly the
accepted grammar. No texture, no sample, no geometry, no new material, no new interpolator.

### 2.1 Huaxia / older mid-rise (gen 2; huaxia and res_tower archetypes)

* **Tile palette** (`xc_gen_palette`): warm beige, grey, muted salmon-pink, pale green, brown 二丁掛, cream —
  warmer and more coloured than the accepted cream / white mid-rise mix.
* **Two-tone tile banding** on ~45 % of huaxia buildings: a contrasting course (brown on light walls, cream on dark)
  under the sills and over the window heads, i.e. horizontal stripes at the floor period that converge to their area
  mean once floors are unresolved. This is the strongest 300-800 m cue.
* **Orderly rhythm**: 2-3 bay groups with one stacked balcony column per group (no random balcony scatter), denser
  punched windows (sill 0.30, head 0.80 of the floor), 1990s towers get a 3.4 m bay instead of 3.9 m.
* **Glass**: one tint per building — 1990s teal or bronze reflective on ~40 %, else the accepted residential mix.
* **Services**: cages x0.65, AC x0.85, enclosed balconies rarer (35 % of balcony columns vs 55 %).
* Weathering, humid cast, ground floor, arcade and storefront logic unchanged.

### 2.2 Modern residential (gen 3)

* **Palette**: light warm grey, cool grey, warm stone, mid grey painted panel / porcelain (no tile grain).
* **Glazing**: bay-to-bay glass between slab lines (fv 0.10-0.96), thin dark mullions at the bay lines instead of
  wall piers between windows.
* **Horizontal banding**: a light slab-edge line every floor; glass balustrade bands (grey glass over the recess) on
  balcony bays.
* Per building one of two compositions: **pier** — a 1.3 m solid fin every 2-3 bays (strong verticals, resolve to
  ~1.5 km); **ribbon** — the balustrade band runs across every bay (strong horizontals).
* **Clean services**: no cages, no enclosed balconies, AC x0.25 (mostly hidden), grime x0.5, no humid cast.

### 2.3 Premium / luxury residential (gen 4)

* **Frame grid**: a member every 2 floors x 2 bays (~7-8 m cells) — honed stone (62 %), graphite or champagne
  metal (38 %); cells resolve to ~1.2 km.
* **Deep reveal ring** inside every cell (stone in shadow), then a **glass balustrade band on every floor** and
  full-height low-iron glass.
* **Base / tower composition**: a 2-3 floor warm granite podium (<= 11.5 m) with tall glazed openings between stone
  piers; residential-tower lobby / storefront rules still own the ground floor.
* **Crown**: the top floor is an open sky-garden void (dark) inside the frame, under the light parapet.
* No cages, no AC, grime x0.3. No vertical greenery (not cheap enough to justify at range).

### 2.4 Protected layers

Storefront v0E, frontage roles, quiet ground floors, tower lobbies, school grammar (separate path), office curtain
wall, podiums, civic / landmark grammar, Taipei 101 and the Roofscape v2 roof path are not touched; offices / podiums /
civic / schools / landmarks always carry gen 0. Ground-floor logic still runs after the facade composition; a
reclassified building only changes its wall tile colour at street level (the same palette as its upper floors).

## 3. A/B review (A = HEAD `a5b3bad` facade, B = v0A; same payload tiles, materials built fresh together)

Cameras: accepted views plus seven facade-facing review obliques (`harness/shots_extra.json`):
`fa_150_mix` (Keelung Rd west fabric), `fa_150_premium_w`, `fa_300_premium_w`, `fa_300_songren` (Songren tower
belt), `fa_300_core_e` (planned core, east), `fa_600_mixed` (old fabric with towers behind), `fa_800_overview`.
Sheets: `evidence/facade_grammar_v0a/sheets/ab4_*.png`, `ab3_*.png`; labelled false-colour check `dbg_*.png`.

| range | read |
|---|---|
| 150 m | all three families are unmistakable: huaxia = warm two-tone tile with dense punched windows and teal / bronze glass; modern = grey glass bays between white slab lines with fins or balustrade ribbons; premium = bold stone / metal 2 x 2 frame grid with dark double-height cells and a dark crown void. Old walk-ups unchanged |
| 300 m | still sortable at a glance: tile warmth vs clean grey glass vs framed cells. Premium reads "expensive contemporary tower" from the frame alone |
| 600 m | the cream-grid monotony is gone: warm mid-rises, grey contemporary towers and a few framed premium towers sit in the unchanged walk-up carpet. Modern vs huaxia separates by value / warmth; premium by its frame |
| 800 m | subtler; the family is carried by colour field and the slab-line / frame period (both still resolve). Range tone and neighbourhood variation keep owning the far read |

Questions from the brief:
1. *Huaxia / modern / premium at aircraft range?* Yes at 150-600 m; at 800 m modern and premium remain distinct,
   huaxia vs legacy becomes a warmth difference.
2. *Less like one repeated cream-grid building?* Yes; the largest change is in the 6-24 F stock, exactly where the
   repetition was.
3. *Plausible old / new mixture?* Yes: the core mixes huaxia / modern / premium; the old fabric keeps legacy walk-ups
   with scattered warm mid-rises and occasional new infill.
4. *Same Skyfront style?* Yes: same flat-shaded, value-driven, fwidth-filtered language; no new texture.
5. *Better without becoming noisier?* Mostly. The two-tone banding is the busiest element at 150 m (by design, it is
   the 300-800 m cue); it converges to a flat colour by ~1 km. No shimmer was seen in the captures; a motion test was
   not run.

DAY / DUSK / NIGHT (`ab4_dusk.png`, `ab4_night.png`): dusk keeps the warm low-sun read with intact window lights;
at night modern bays light as wider panes, premium cells light inside the frames, crown / lobby / storefront /
sign glow is unchanged. No night redesign was needed.

Storefront / frontage / school regression (`diff_cb_songqin_arcade.png`, `diff_sf_cvs_wuxing.png`): boards,
arcades, convenience-store fronts and quiet ground floors keep their layout; a reclassified building only changes its
wall tile colour at street level. Schools, offices, podiums, civic, Taipei 101 and roofs are unchanged.

## 4. Performance (SceneCapture2D 1080p, UHD 770 harness; A / B swapped in one session, 6 rounds in both orders)

Method as v0D / v0E: A (HEAD shader) and B (v0A) built fresh together after the asset stage, swapped in memory, every
state pre-warmed, 40 GPU-synchronised samples per round. Paired delta = mean over rounds of (B median - A median) in
the same round; min = difference of the min-of-all-samples. Class = camera altitude class as in v0E.

**Primary (clean session `perf_day2`, after the restructure):**

| class | view | A ms | B - A paired median | B - A (median of rounds) | B - A min |
|---|---|---|---|---|---|
| LOW | `fa_150_mix` | 69.2 | +1.20 | +0.48 | +0.69 |
| LOW | `st_wuxing` | 58.3 | +0.38 | +0.34 | +0.24 |
| MID | `roof_ne1` | 74.3 | +0.82 | +0.62 | +0.40 |
| MID | `fa_300_songren` | 66.8 | +0.64 | +0.56 | +0.32 |
| MID | `fa_600_mixed` | 73.5 | +0.03 | +0.19 | +0.70 |
| HIGH | `d_overview_sw` | 73.9 | +0.45 | +0.35 | +0.39 |
| HIGH | `fa_800_overview` | 69.2 | +0.06 | +0.09 | +0.39 |

**NIGHT (`perf_night2`)**: min-based B - A = +0.09 (`fa_150_mix`), +0.37 (`roof_ne1`), +0.13 (`d_overview_sw`); the
night medians carry single-round spikes (one 90.8 ms round) and are not used.

Summary: **LOW ≈ +0.3…+0.5 ms, MID ≈ +0.2…+0.6 ms, HIGH ≈ +0.1…+0.4 ms** (day), night ≈ +0.1…+0.4 ms. LOW and HIGH meet
the target; MID sits at or slightly above the preferred +0.2–0.3 ms on two of three views.

A confirmation session (`perf_day3`) ran while unrelated processes loaded the CPU (the iGPU shares the package power
budget; A was 8 ms slower than in `perf_day2`): it is noisy (±1–3 ms) but consistent — B - A min-based +0.26…+0.78 ms at
MID / HIGH, ≤ 0 at LOW.

### 4.1 Shader complexity — what the first version cost and why

The first B (generation palettes, glass tints and the band mask evaluated as constant-weight lerps on every wall
pixel, modern / premium composition after the storefront block) cost **+1.2…+2.0 ms in every class**, HIGH included.
Attribution in one clean session (`perf_attr2`, 4 states):

| state | LOW | MID | HIGH |
|---|---|---|---|
| no modern / premium branches (parameters only) | +1.5 | +1.6 | +1.6 |
| full first B | +1.5 | +2.0 | +2.3 |
| full B, composition moved ahead of the storefront block | +0.5 | +0.9 | +0.9 |

So the tax was the **always-on per-pixel parameter work**, not the new branches, plus live storefront temporaries
across the composition. Fixes (visually identical, `B5` vs `B4` frames 3 / 6 bit-identical, rest at the renderer noise
signature):

1. palettes (`xc_gen_palette`), glass (`xc_gen_glass`), the huaxia band mask and the premium podium run only inside
   coherent `[branch] if (gen > 1.5)` / per-family branches; unknown / legacy pixels skip them entirely;
2. the facade composition (accepted / modern / premium as one if / else chain) runs before the street-level block, so
   the storefront temporaries are not live across it;
3. the premium palette is recomputed inside its branch instead of being carried live.

A further variant without the modern / premium branches (`perf_attr3` / `perf_day3`, NB2) shows no consistent
saving, so the remaining ~0.3–0.6 ms is not those branches. No new texture sample, interpolator, material or draw call.

## 5. Determinism / regression

| check | result |
|---|---|
| tile rebuild twice (`build_look_tiles.py`) | 25 GLB + frontage roles + report SHA-identical; sidecar content identical (its `.gz` header carries a timestamp, pre-existing at HEAD) |
| geometry / attributes vs pre-payload tiles (`verify_facade_payload.py`) | `PASS_NO_VISUAL_CHANGE`: positions, normals, TEXCOORD_0 / 1, indices, TEXCOORD_2.y bit-identical; 485,936 triangles, 991,557 vertices |
| payload decode | decoded codes: unknown 98,912 / legacy 393,743 / huaxia 365,506 / modern 118,407 / premium 14,989 vertices; storefront / frontage / school / hero bits unchanged |
| no-profile mode | `--no-facade-profile` reproduces the committed v0 counts exactly |
| UE5.8 stages | `PASS_LOOK_ASSETS`, `PASS_LOOK_LEVEL`, fresh-reopen `PASS_LOOK_CAPTURE`; the stage-built `M_XinyiCity` matches the fresh B material (6 / 8 views bit-identical, 2 at noise) |
| office tower / Taipei 101 pixels (e_lowpass) | max 6 / 0.07 % of pixels changed (reflections of reclassified neighbours) |
| schools, roofs (rp_low150, roof_ne1 / ne2) | unchanged in the diff maps |
| storefront v0E / frontage | layout, boards, CVS fronts, quiet ground floors unchanged; only reclassified walls change tile colour |
| DXC ps_6_0 | 8 / 8 materials compile (SPIR-V backend absent in this SDK, same as HEAD) |
| tests | `tests/test_facade_generation.py` (+9 profile tests), `tests/test_building_era.py`: 104 tests OK, 9 skipped |

## 6. Image 2.5 ageing masks — still justified?

**Partly, and with lower priority than the pilot assumed.** v0A shows that the dominant facade error was grammar,
palette and classification: once the 6-24 F stock separates into huaxia / modern / premium, the "one repeated
cream-grid building" read disappears at 300-800 m without any texture. What remains on old stock (legacy walk-ups,
older huaxia) is genuinely **irregular material ageing** — repaint / repair patches and mould blotches whose shape the
shader can only render as noise — but it reads mainly at 100-300 m; at 600-800 m it is a value difference the
existing grime and range tone already carry. Recommendation: keep the pilot to **two** masks (stain field + repair
zones A) for close passes, gate them behind the old-stock branch, and only proceed if a 150 m flight review asks for
it. No assets were generated.

## 7. Files

* `tools/lookdev/facade_generation.py` — generic profile layer (`FacadeProfile`, `family`, `unit_hash`, profile draw,
  profile-weighted premium); no-profile behaviour unchanged.
* `tools/lookdev/profiles/facade_taipei_xinyi_v0.json` — new regional profile (data only).
* `tools/lookdev/build_look_tiles.py` — `--facade-profile` / `--no-facade-profile`, group key, report counts by
  archetype / zone / basis.
* `tools/lookdev/shaders/xinyi_city.hlsl` — `gen` threaded `xc_city` -> `xc_wall`; `xc_gen_palette`,
  `xc_gen_glass`; huaxia / modern / premium grammar; composition reordered ahead of the street-level block.
* `tools/lookdev/ue_custom_code.py` — `M_XinyiCity` passes `fgen`; `M_Taipei101` passes 0.
* `tools/lookdev/preview/viewer.js` — call-site signature only.
* `tests/test_facade_generation.py` — profile tests and shader call-site contract.
* `docs/xinyi-facade-grammar-v0a.md` (this file), `docs/xinyi-facade-metadata-payload-v0.md` (superseded note).

Evidence (not committed): `unreal/Saved/XinyiLook/evidence/facade_grammar_v0a/` (`frames/`, `sheets/`, `harness/`
incl. `perf*.json` summaries via `perfsum.py`, `base_offline/` pre-payload tiles, `payload_tiles/`).
