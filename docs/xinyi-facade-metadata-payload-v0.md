# Facade generation metadata payload v0

> **Superseded in part by `docs/xinyi-facade-grammar-v0a.md`:** the payload encoding (§1-4) is unchanged; the
> classification (§5, §7, §8) now adds an `acw.facade_profile/0` profile layer and a profile-weighted premium draw,
> and `xc_wall` consumes the code. The rules below remain the `--no-facade-profile` behaviour.

Status: **data wire installed, not consumed.** No shader visual logic, geometry, texture, roof, storefront, frontage
or school behaviour changed. Branch `feat/opus55-xinyi-visual-quality`, on top of `d620369`.

Inputs: `docs/xinyi-facade-material-pilot-v0.md` §8.1 (proposed a fourth UV channel), `docs/taipei-building-era-metadata-v0.md`,
`tools/lookdev/build_look_tiles.py`, `tools/lookdev/gltf_writer.py`, `tools/lookdev/shaders/xinyi_city.hlsl`.

Result in one line: the facade pilot's `TEXCOORD_3` is **not necessary**. A 3-bit generation code fits in unused
headroom of `TEXCOORD_2.x` at **0 extra bytes per vertex**.

---

## 1. Existing payload audit

The 25 look tiles are single static meshes (one draw per 500 m tile, 991,557 vertices, 485,936 triangles).
`UseFullPrecisionUVs` is on (`xinyi_look_build_assets.py:564`), so every UV channel is 2 x float32.

| field | stream / bits | consumer | spare capacity |
|---|---|---|---|
| position | POSITION, 3 x f32 | geometry | n/a |
| normal | NORMAL (UE packs tangent basis) | lighting | n/a |
| wall (perimeter m, height m) / roof (east, north m) | TEXCOORD_0, 2 x f32 | `xc_wall` window grid, `xc_roof` | none: continuous metres |
| record height m, visual floor height m | TEXCOORD_1, 2 x f32 | `xc_wall` floor rhythm, hero | none: real values, `floors = height / fh` is **derivable** |
| archetype x 16 + variant | TEXCOORD_2.x high byte **R**, 7 of 8 bits (arch 0..7 = bits 4-6, variant = bits 0-3) | `xc_city` arch / variant | **R bit 7 free** (always 0) |
| appearance seed (per building group) | TEXCOORD_2.x low byte **G**, 8 bits | every hash | none |
| weathering | TEXCOORD_2.y high byte **B**, 8 bits | stain / wear | none *usable*; value is `f(arch, core, seed & 63)` so it is derivable, but moving that into the shader is a visual-logic change (see §2 E) |
| flags bit0 core, bit1 anchor, bit2 podium part, bit3 rooftop structure | TEXCOORD_2.y low byte **A** bits 0-3 | `xc_wall`, `xc_roof` | none |
| flags bits 4-6: school corridor (bit4) / frontage role `FRONT_*` | A bits 4-6 | `xc_school_wall`, storefront / frontage | none |
| flags bit 7 | A | **hero tag**: the shader tests `A >= 0.97`, so any value with bit 7 set can land in that range | **not usable** |
| COLOR_0 | not emitted (deliberate: "the Unreal material never depends on the importer's vertex-colour policy") | none | n/a |
| per-instance / custom primitive data | not applicable | none | tiles are merged static meshes, 1 instance per tile |
| look-tile sidecar `look_buildings.jsonl.gz` | offline only | tests, tools | unlimited |

Duplicated / derivable values: weathering (derivable from archetype + core + seed), floors (`height / floor_h`),
core flag (position-derivable, kept for speed), `variant` (hash of building id; not derivable at runtime).
The pre-existing float packing is exact: x <= 32,767 + 255 and y <= 65,535, both far below 2^24, so integers survive
float32 and the shader's `floor(x/256 + 1e-4)`.

School records (`ARCH_SCHOOL = 7`), frontage roles, storefront plan lookups and the hero tag are untouched: R, G, B, A
keep their exact values and bit positions.

## 2. Candidate encodings

Current Xinyi: V = 991,557 look vertices, 25 tiles. "Vertex bandwidth" is the share of the current 40 B/vertex stream.

| | bytes / vertex | memory delta (Xinyi) | vertex bandwidth | shader decode | implementation risk |
|---|---|---|---|---|---|
| **A. reuse spare bits only** (R bit 7) | 0 | 0 | 0 | 1 bit test | 1 bit holds 2 states; 5 classes need 3 bits. A bit 7 collides with the hero tag. **Insufficient alone** |
| **B. COLOR_0 vertex colour** | +4 | +3.97 MB | +10 % | extra `VertexColor` input | the project avoided vertex colour on purpose (importer colour policy: replace / ignore / override); needs a new color interpolator and material graph change |
| **C. UV3 / fourth UV channel** (pilot proposal) | +8 (full-precision UVs apply to the whole mesh, float2) | +7.93 MB (+20 % of the 40 MB look tiles) | +20 % | new `TexCoord[3]` input | material graph + importer UV count change; expected to fit the spare half of the 2nd UV interpolator (unverified), so likely no extra interpolator on mobile, but the stream grows for every pixel-shaded draw of every tile |
| **D. per-instance / custom primitive data** | n/a | n/a | n/a | n/a | **incompatible**: 25 tile instances, not per building. A lookup texture keyed by building would need a unique id, which no vertex channel carries |
| **E. headroom in TEXCOORD_2.x** (bits 15-17) | **0** | **0** | **0** | ~5 ALU (estimate: `floor`, mul, sub, round) per pixel in the Custom node, `gen` itself dead-code eliminated | decode must strip the payload, and float interpolation noise must not corrupt R/G (analysis below) |
| E'. derive weathering and reuse B | 0 | 0 | 0 | more ALU | changes shader visual logic and four other meshes' weather; rejected for a zero-visual-change pass |

**Why E is safe.** `x = gen * 32768 + (R*256 + G)` with `R <= 127` (guaranteed: arch <= 7, variant <= 15). Largest
value is 4 * 32768 + 32767 = 163,839 < 2^18, exact in float32 (24-bit mantissa), ulp = 1/64 at the top. The GPU
interpolates a constant across the triangle with perspective weights; worst error measured over 800k simulated float32
perspective-weighted interpolations per code (bases 0 / 255 / 256 / 32767) is **0.031** (gen 3 / 4), vs. a decode tolerance of **0.5** (round to nearest): 16x margin.
The old decoder only tolerated 0.0256, which is why `xc_unpack` itself must not be fed a payload and a new
`xc_unpack_tile` rounds. Codes 5..7 stay reserved (x < 2^18 still holds for all 8 values).

## 3. Chosen encoding

`TEXCOORD_2.x = generation * 32768 + R * 256 + G`.

* Writer: `gltf_writer.pack_rgba8(rgba, payload=...)`. `payload=None` or all-zero output is **bit-identical** to the
  historical bytes. It refuses `R > 127` and `payload > 7`.
* Decoder: `xc_unpack_tile(float2 d, out float gen)` in `xinyi_city.hlsl`:
  `gen = floor((d.x + 0.5)/32768); x = floor(d.x - gen*32768 + 0.5)`, then the unchanged R/G/B/A decode.
  With `gen == 0` it equals `xc_unpack`. **Only `M_XinyiCity` calls it** (`ue_custom_code.py`; the call site declares a
  `float fgen` that nothing reads). `M_Taipei101`, ground, paint, props, street, backdrop and foliage keep
  `xc_unpack` untouched. The preview viewer uses it only for `uKind == 0`.
* Python mirror and constants: `tools/lookdev/facade_generation.py` (`encode_x` / `decode_x`).
* The weld key already contains the per-building colour row; the payload is a function of the building so the vertex
  count is unchanged (991,557 before and after).

Deployment pairing: look tiles built **with** the payload must run with a material built from the new HLSL (the old
`xc_unpack` would read `R` as `gen*128 + R`). `build_all.py` rebuilds both; `--no-facade-payload` on
`build_look_tiles.py` reproduces the previous bytes exactly.

## 4. Memory / bandwidth cost of the choice

| item | delta |
|---|---|
| vertex stream | **0 B/vertex, 0 MB** (same 991,557 vertices, same attributes) |
| GLB size | 0 (same accessor sizes) |
| vertex bandwidth | 0 |
| pixel ALU | ~5 ops in the `M_XinyiCity` Custom node (the generation output is unused; the strip/round is not) |
| shader permutations | none added |

For reference, C (UV3) would add 7.93 MB and 20 % stream width, B 3.97 MB.

## 5. Classification semantics

Stored value (3 bits, `facade_generation.py`):

| code | name | meaning for the future grammar |
|---|---|---|
| 0 | `unknown` | no usable signal, or the facade family does not apply; the shader keeps its archetype prior |
| 1 | `legacy` | old walk-up / mixed-use stock |
| 2 | `huaxia` | 1980-1999 tile mid-rise / 1990s tile tower |
| 3 | `modern` | 2000+ residential |
| 4 | `premium` | 2010+ luxury-class residential |
| 5-7 | reserved | |

Rules (pure function of archetype, floors, height, floor height, core flag, optional era record):

1. **Not applicable** -> `unknown`: archetypes office, commercial podium, civic, school, and any registry landmark.
2. **Era evidence** (below) maps the bucket: `pre_1980 -> legacy`, `1980_1999 -> huaxia`, `2000_2009 -> modern`,
   `2010_2019` / `2020_plus -> modern`, upgraded to **premium** only if the morphology is a luxury-class candidate:
   residential tower, inside the core district, >= 18 floors, floor height >= 3.3 m.
3. **Morphology** (no era): outside the core district, <= 24 floors: `low`/`walkup -> legacy`, `huaxia`/`res_tower -> huaxia`.
   Inside the planned core district (developed after ~1990, era spread too wide) or taller than a residential tower:
   `unknown`. Morphology alone never yields `modern` or `premium`.
4. Everything else -> `unknown`.

The thresholds are v0, provisional, and global: change them only as a documented global change, never per building.
The code stores no year, no permit field and no confidence: provenance (`observed_era` / `inferred_era` / `morphology` /
`none` / `not_applicable`) and the era bucket go to the sidecar `look_buildings.jsonl.gz` and the report only.

## 6. Unknown behaviour

`unknown` is a first-class, valid result. It occurs when the family does not apply, when morphology cannot discriminate
(core district, very tall), and for ambiguous or unknown era records. A building with `unknown` renders exactly as
today. The future shader should treat `0` as "use the archetype prior", never as "oldest" or "newest".

## 7. Era / profile input precedence

```
not applicable (archetype / landmark)   -> unknown
observed era   (exact | range, open_use_permit / open_construction_permit)   -> class from bucket
inferred era   (profile_inference, confidence "inferred")                   -> class from bucket
morphology prior (archetype, floors, height, core)                            -> legacy / huaxia
otherwise                                                                    -> unknown
```

* Group level: per-footprint era records are folded with `era_schema.aggregate_group` (observed members vote, largest
  exact wins; conflicting buckets -> ambiguous -> ignored here). Observed always outranks inferred.
* The classifier imports no regional adapter. The builder reads an **optional** generic `acw.building_era/0` cache
  (`--era-cache`, default `data/lookdev_cache/xinyi_building_era_v0.json.gz` if present, `--no-era` to ignore it). A
  missing file, an empty file or no era at all still builds and classifies. The unresolved Taipei cadastral enrichment is
  not required. No exact year is read, stored or invented: only the bucket. Tests assert the module graph contains no
  `taipei` / `adapters` module and that the guard `TestNoVisualWiring` keeps era out of shaders, Unreal code and the viewer.
* Caveat on current data: the permit cache holds **new-build use permits only** (buckets 2000_2009, 2010_2019, 2020_plus).
  "unknown" therefore does **not** mean old; the morphology prior covers the old stock and nothing contradicts it.

## 8. Current Xinyi counts

With the committed era cache (`xinyi_building_era_v0.json.gz`), 11,124 ordinary records, 4,137 building groups:

| generation | records | groups |
|---|---|---|
| legacy | 3,607 | 1,687 |
| huaxia | 4,626 | 1,270 |
| modern | 1,146 | 499 |
| premium | 7 | 4 |
| unknown | 1,738 | 677 |

| basis | records | groups |
|---|---|---|
| observed era | 1,153 | 503 |
| inferred era | 0 | 0 (no `EraInferer` priors ship) |
| morphology | 8,233 | 2,957 |
| none (morphology cannot decide) | 886 | 374 |
| not applicable | 852 | 303 |

Known (code != 0): 9,386 records / 3,460 groups. Unknown (code 0): 1,738 / 677. Era-confirmed: 1,153 records.
Morphology-only run (`--no-era`, same 991,557 vertices): legacy 3,747 / huaxia 5,259 / unknown 2,118 records (0 modern, 0 premium), i.e. 9,006 morphology + 1,266 undecidable + 852 not applicable. Premium is 7 records because it needs both a 2010+ era record and a core
luxury tower profile; this is deliberately rare until more era evidence exists.

## 9. Future shader integration point

`xc_city` already receives the stripped value from `xc_unpack_tile` as `fgen` in the Custom node call. A future facade
pass should (a) add `float gen` to `xc_city`'s parameters and thread it to `xc_wall`, (b) treat `gen == 0` as "archetype
prior", (c) select the grammar parameter set (palette, glass tint, balcony / pier rule, ageing mask weight) from `gen`
and `arch`, (d) keep one branch-free weight table. Nothing in this pass reads `gen`.

## 10. Verification

* `tests/test_facade_generation.py` (17 tests): determinism and order independence, unknown handling, ambiguous era,
  bucket mapping, premium rule, observed > inferred > morphology, era does not override inapplicable families, no Taipei
  dependency (AST + `python -I` subprocess), exhaustive round trip of every legal base for every code in float32,
  rejected boundaries (R = 128, code 5, payload 8), interpolation-noise decode, historical `pack_rgba8` equality, all
  flag values 0..127 preserved, shader contract (new function present, `xc_unpack` untouched, only one call site).
* `tests/test_building_era.py`: the existing "no visual wiring" guard now allows only the two offline producers.
* `tools/lookdev/verify_facade_payload.py` on the real 25 tiles: positions, normals, TEXCOORD_0/1, indices and
  TEXCOORD_2.y bit-identical to payload-off tiles; TEXCOORD_2.x with the payload stripped bit-identical.
  Payload-off rebuild vs the local pre-change tiles in `unreal/Saved/XinyiLook/tiles`: all 25 GLB SHA-256 identical.
  Two payload-on builds: all 25 GLB SHA-256 identical (deterministic).
* DXC `ps_6_0` (`check_hlsl.py`): all 8 materials compile (`ok ... dxil`); the SPIR-V pass fails identically at HEAD because
  this SDK's `dxc` has no SPIR-V backend.
* Not run: an in-engine UE5.8 capture. The Unreal editor was not available in this session (`unreal-mcp` refused the
  connection) and the pass changes no material input that renders; the capture comparison should be repeated with the
  next look-dev stage run (rebuild tiles + materials together).
