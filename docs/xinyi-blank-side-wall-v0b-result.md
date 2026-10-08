# Xinyi blank side-wall v0B — result

Status: **complete — 17 high-confidence exposed party-wall faces render windowless (12 wall-ad hosts + 5 others);
15 ad hosts deliberately left unchanged as ambiguous.**

Branch `feat/opus55-xinyi-visual-quality`, starting HEAD `c7340c0` (Taipei wall ads v0). Evidence (local, not
committed): `unreal/Saved/XinyiLook/evidence/blank_wall_v0b/` (`frames/`, `sheets/`, `harness/`). Offline outputs:
`unreal/Saved/XinyiLook/blank_walls/`.

## 1. Root cause

`xc_wall` (`tools/lookdev/shaders/xinyi_city.hlsl`, `M_XinyiCity`) synthesises the whole opening grammar — windows,
balconies, frames, iron cages, AC units, piers, sill streaks — and the night window light (per window, plus its
far-distance mean) on **every** wall face from the face's (perimeter, height) coordinates. No input says "this face
has no openings", so exposed party walls above a lower neighbour, including the wall-ad hosts, get a full window grid
by day and lit windows at night.

Per-face data already reaches the shader: wall faces carry their own vertices (the frontage role is baked per face),
and the facade-generation payload in `TEXCOORD_2.x` (bits 15-17, `docs/xinyi-facade-metadata-payload-v0.md`) had
**reserved codes 5-7**. The generation code is consumed only by `xc_wall`.

## 2. Strategy (chosen): targeted per-face code + one composition arm

* **Data:** `tools/lookdev/build_blank_walls.py` marks a selected face by adding 5 to the generation code **on that
  face's vertices only** (unknown 0 -> 5, legacy 1 -> 6, huaxia 2 -> 7; `facade_generation.BLANK_FACE_OFFSET`).
  No new UV channel, no packing change, no geometry change: the triangle soup of every patched tile is verified
  identical and no vertex had to be duplicated (34 triangles / 78 vertices marked). Patched copies go to
  `blank_walls/tiles_blank/` (14 tiles); the accepted `tiles/` are never written.
* **Shader:** `xc_wall` decodes `blankF = step(4.5, gen); gen -= 5 * blankF` (the building keeps its real
  generation everywhere else), and the blank treatment is the **first arm of the existing composition if / else
  chain** (blank -> modern -> premium -> accepted grammar). The arm zeroes every opening term and its far mean, so
  glass, material response and the whole night block see no window; the tower crown band is off via `isTower`.
* **Finish (restrained):** host tile / paint continued on ~55 % of faces, grey cement render ~25 %, corrugated sheet
  cladding (鐵皮) ~20 % (per building hash); value pulled to x0.86 (a windowless wall has no dark glass in its mean);
  12 m tone blotches, occasional lighter repair panels, parapet rain stains (3-14 m, ~1.6 m apart), a faint RC beam line
  per floor on rendered walls; everything converges to its mean at range. No texture, no new material.
* **Switch:** `ACW_XINYI_BLANK_WALLS=off` (asset stage) imports the accepted tiles; the shader then renders exactly as
  before (§8). Wall ads stay independent (`ACW_XINYI_WALL_ADS`, or hidden in memory for state C).

## 3. Alternatives rejected

| option | why not |
|---|---|
| overlay "blank wall" planes | a second material must re-derive the host's palette / weathering / cast; seams at face corners, a 2-3 cm offset surface (Z-fighting risk at 600-900 m), extra opaque layer, and night "covering" instead of removing emission |
| separate branch ahead of the composition (first implementation) | visually identical, but measured **+0.1...+0.3 ms** in every class (HIGH +0.23) in two sessions; the same code as a chain arm measured ~0 (attribution in §7) |
| per-face flag in `TEXCOORD_2.y` / a new UV | would touch the decode of every tile consumer or add 8 B / vertex; the reserved generation codes need neither |
| suppress windows only around the board on ambiguous hosts | would hide possibly real windows: the brief's "preserve when ambiguous" |

## 4. Selection (17 faces) and rejections

A face is marked only if it is a Gate 0 valid wall (`build_wall_ads.py`) **and**, along its *whole* ring edge
(0.5 m samples): another building group touches it (<= 0.3 m) on >= 80 %, lies within the 1 m lot-line distance on
>= 95 %, the building's own wing never faces it; the face is <= 25 m long (a lot depth) and no neighbour shares more
than ~1.25 x this edge with the host (a low block wrapping a tower is its podium / complex split into WFS records);
the matched tile triangles are rear / side walls (frontage role 1), cover >= 98 % of the edge, reach the roof line,
and carry generation 0-2 consistent with the look sidecar.

| scope | marked | rejected (ambiguous) |
|---|---|---|
| wall-ad hosts (27) | **12** | 15: neighbour wraps the host 8, lot line not along the whole face 3, gap not touching (0.65-1 m) 2, own wing 2 |
| secondary (best-exposed valid walls, >= 8 m wide, band >= 9 m, >= 80 m apart, >= 40 m from boards, max 12) | **5** | 14: neighbour wraps 4, lot line partial 5, gap 2, longer than a lot (incl. a 60.8 m face) 2, own wing 1; plus 63 skipped by spacing / size / board proximity |

Marked length 221 m of wall. No school, office, podium, civic, landmark, Taipei 101, modern or premium face can be
marked (class + role + generation checks, test-enforced). The first, looser selection (26 faces) was rejected after the
first captures: a 60 m face over a long low block turned into a featureless panel — the low block is almost certainly the
same complex; the lot-depth and wrap rules came from that review, applied globally.

## 5. Visual result (UE5.8, SceneCapture2D 1080p)

Sheets: `sheets/ab_day_v0b.png`, `ab_night_v0b.png`, `ab_far_and_C.png`; motion `motion_bw_seq300_B2_day_day.png`.

* **150 m** (`wa_150_legacy`, `bw_150_host2`): the 數理 and 森悅 boards now sit on a plain wall in the host's own
  colour with faint rain stains; no window grid around or below the board; face boundaries are the building's own
  corners and parapet, so there is no patch outline.
* **300 m** (`bw_300_hosts`, `bw_300_core`): the 預售 host and a tall planned-core flank read as ordinary blank flanks
  next to windowed fronts — the clearest reduction of the "window-grid toy" look in this pass.
* **600 / 800 m** (`wa_600_west`, `bw_800_west`): a few calmer flanks among the windowed fabric (0.03-0.13 % of
  pixels); at this range the effect is a slight de-griding, not a feature.
* **NIGHT:** false lit windows are removed from every marked face (the core flank goes dark beside its lit front;
  the windows around 數理 / 預售 no longer glow); the wall-ad floodlights and all other window light are unchanged.
* **DUSK:** the faces take the warm low light like the rest of the building.
* **State C** (ads hidden, blank walls on): hosts read as plausible blank walls on their own.
* Rejected-face cameras (`bw_150_long`, `bw_150_tower`) are bit-identical to HEAD, as intended.

Limits: the 15 ambiguous ad hosts still show windows around their boards; the finish is procedural (no authored
material), deliberately quiet.

## 6. Motion / Z-fighting

300 m lateral pass over two corrected hosts, 1.5 m / frame (8 frames, masked by |on - off|): in-face luminance
102.3 -> 102.9 / 255 with steps of -0.13...+0.41 (no flicker); in-face high-frequency energy ~9 vs ~18.6 for the frame
(the faces are calmer than their surroundings). No shimmer, no crawling stains, no seams. No geometry was added, so
there is nothing to Z-fight; wall-ad boards keep their measured offsets.

## 7. Performance (UHD 770, same-session interleaved; city material A = HEAD shader, B = v0B, same tiles)

| session | LOW | MID | HIGH |
|---|---|---|---|
| final arm, DAY (`perf_final_day`, 9 views, B first) | +0.15 | -0.02 | +0.03 |
| final arm, NIGHT (`perf_final_night`, 4 views) | +0.16 | +0.08 | +0.05 |
| attribution (`perf_attr1`, 6 views): decode only (V0) | -0.02 | -0.14 | -0.21 |
| attribution: chain arm (V1 = final) | +0.13 | -0.11 | -0.04 |
| attribution: separate branch (first version) | +0.28 | +0.08 | +0.07 |
| first session: separate branch (`perf_day1`) | +0.06 | +0.16 | +0.23 |

Class medians of per-view paired medians (ms); per-round spread typically +-0.2...0.5 ms. Final: within LOW <= 0.3,
MID <= 0.2, HIGH <= 0.1-0.2, i.e. at or near the noise floor; the small positive LOW values are reported as a possible
~0.1 ms cost, not dismissed. DXIL: +327 instructions (7,059 -> 7,386), all inside the arm; decode-only adds 3.

| cost item | delta |
|---|---|
| geometry / vertices / triangles | 0 (same soup; 0 duplicated vertices; patched GLBs byte-size identical) |
| materials / textures / draw calls | 0 |
| vertex stream | 0 B (reserved payload codes) |
| disk (offline only) | 14 patched tile copies, 41.4 MB beside the originals; one set is imported |

## 8. Determinism, regression, tests

| check | result |
|---|---|
| `build_blank_walls.py` twice, once from an empty folder | report, face list and all 14 tiles byte-identical |
| patched tiles vs accepted tiles | triangle soup identical; only TEXCOORD_2.x of marked vertices differs, by exactly +5 x 32768 (test) |
| writer round trip of an untouched tile | byte-identical GLB (test) |
| `ACW_XINYI_BLANK_WALLS=off` build vs HEAD | DAY 21 / 29 bit-identical, rest = known `a_skyline_nw` speckle / a few aviation-light pixels; NIGHT 10 / 12, DUSK 9 / 12 identical — the new shader is neutral on unmarked faces |
| v0B vs HEAD, DAY | 10 views bit-identical; differences only where marked faces are visible |
| final arm vs first branch version | 39 / 39 DAY frames bit-identical |
| full UE rebuild (ON) vs previous ON frames | 5 / 7 identical, 2 with frame-wide stage-rebuild speckle (as documented in the wall-ads pass) |
| wall ads | plan / atlas hashes unchanged (`7e1f08c4...`, `1fee3297...`); 27 instances placed |
| DXC ps_6_0, HLSL 2018 + 2021 | 10 / 10 units compile |
| tests | `python -m unittest discover -s tests`: 130 OK, 9 skipped (118 + 12 new in `tests/test_blank_walls.py`) |
| UE stages | `PASS_LOOK_ASSETS`, `PASS_LOOK_LEVEL`, `PASS_LOOK_CAPTURE` |

## 9. Files

* `tools/lookdev/build_blank_walls.py` (new) — face confidence, mesh face matching, payload patch, fail-closed checks.
* `tools/lookdev/shaders/xinyi_city.hlsl` — flag decode in `xc_wall`; blank arm at the head of the composition chain.
* `tools/lookdev/facade_generation.py` — `BLANK_FACE_OFFSET` (codes 5-7).
* `adapters/unreal/lookdev/xinyi_look_build_assets.py` — imports `tiles_blank/` copies; `ACW_XINYI_BLANK_WALLS`.
* `tools/lookdev/build_all.py` — runs the builder after the wall ads.
* `tests/test_blank_walls.py` (new) — 12 tests.
* `docs/xinyi-facade-metadata-payload-v0.md` — codes 5-7 documented; this file.
