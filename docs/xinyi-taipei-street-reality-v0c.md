# Xinyi — Taipei Street Reality v0C: curb-zone truth

Status: **engineering validated, visual iteration done, not committed** on `feat/opus55-xinyi-visual-quality`, built on
HEAD `fa656bf` (Taipei Street Reality Audit). Look-dev layer only: the 25 look tiles, frontage roles, ground data
texture, trees, forest, lamps, rooftops, campus paint and the v0B signs / boxes / awnings are byte-identical to HEAD.
Authoritative research: `docs/xinyi-taipei-street-reality-audit.md` (§2 W1–W4, §4, §8, v0C cut line).

What changed, in one line each:

1. the "scooter confetti" ground cells are gone (W1);
2. raised sidewalks now come from data, with a grey / beige-grey municipal paver palette (W3, W4);
3. white scooter stall rows are painted on plausible curbs, and real low-poly scooters stand in them (§8);
4. the Hangul-like pseudo-lettering on horizontal shop boards is gone (W2).

Not in v0C (unchanged, per the brief): green pedestrian lanes, 機車待轉區, convenience stores, storefront states,
horizontal TC atlas, YouBike, cabinets, street furniture.

## 1. Sidewalk logic (`tools/lookdev/curb_zone.py`, called by `build_ground.py`)

Each side of every drivable way is sampled every ~5 m and gets one of three classes:

| class | rule (first match wins) | ground treatment (`xc_ground`) |
|---|---|---|
| **sidewalk** | a mapped `footway=sidewalk` runs parallel (cos ≥ 0.9) within W/2 − 1.5 … W/2 + 9 m **and this road's kerb is the nearest kerb to it**; else `sidewalk=both/left/right/separate` (or `sidewalk:<side>`) and not `no`; else an unmapped trunk / primary / secondary / tertiary (not `*_link`, not tagged `sidewalk=no`) | kerb + municipal pavers (unchanged width, 3.5–5 m fade) |
| **arcade** | no sidewalk, and the side is fronted by old-stock commercial frontage (roles 5–7 on low / walk-up / huaxia: the walls the shader paints a 騎樓 arcade on) | no kerb; 0.45 m drain-cover strip at the carriageway edge, then owner-built concrete / tile, value-mottled |
| **none** | everything else: residential / unclassified / living_street without mapping, `*_link`, `sidewalk=no`, and **every service way** | no kerb, no slab: older, lighter, patched lane asphalt continues ~3 m toward the building line |

* Mapped geometry beats the tag: `sidewalk=no` beside a separately mapped sidewalk is still a sidewalk. The tag only
  blocks the arterial default.
* Evidence gaps ≤ 15 m are bridged and isolated evidence < 10 m is dropped (same for arcade frontage). There are
  no per-street exceptions.
* Raster: each half-carriageway carries its class, and every ground pixel takes the class of the **nearest**
  half-carriageway (EDT indices). A side's class therefore never leaks across its carriageway. It is stored in the
  campus texture's alpha, which was unused (`T_XinyiCampus`, RGBA8, box mips): 0 / 0.5 / 1. No new texture, no new
  channel; campus R / G / B are byte-identical to HEAD.

Sidewalk presence before (HEAD drew a raised sidewalk on every road side, all classes) → after:

| road class | side length | raised sidewalk v0C | share |
|---|---|---|---|
| primary | 12.8 km | 8.7 km | 68 % |
| secondary | 57.6 km | 41.4 km | 72 % |
| tertiary | 68.8 km | 63.0 km | 92 % |
| trunk | 5.4 km | 1.1 km | 20 % (mostly ramps / `sidewalk=no`) |
| residential | 131.6 km | 14.1 km | 11 % (mapped or tagged only) |
| unclassified | 11.1 km | 1.7 km | 15 % |
| service lanes (巷 / 弄) | 166.4 km | **0** | 0 % |
| other service | 42.8 km | **0** | 0 % |

Residential non-sidewalk sides: 22.1 km arcade apron, 95.4 km lane asphalt.

## 2. Sidewalk palette

Value variation only, no hue variation, no red:

* municipal paver: (0.29, 0.285, 0.275) grey ↔ (0.31, 0.30, 0.28) beige-grey, blended by a smooth ~80 m noise
  (not axis-aligned cells, so diagonal streets don't staircase);
* ±7 % value over ~50 m stretches; darker, slightly cooler repair patches (−20 %, near only);
* the 0.3 m joint lines are kept;
* the brick-red variant is removed (brick red is the bicycle-lane colour in Taiwan).

The arcade apron is (0.275, 0.266, 0.25), ±10 % mottling at ~4 m (mismatched shop frontages), with a darker drain
strip. Lane-edge asphalt is (0.135, 0.135, 0.14) with stronger patching than the carriageway.

## 3. Scooter stall rules

Bays are 1.2 m wide (legal 1–1.5 m) × 2.0 m deep, perpendicular to the kerb, white 0.12 m outlines over a slightly
darker oil-stained fill (one paint mesh: the existing `XinyiRoadPaint`, fill draped 1 cm under the lines). Stalls
come **only from frontage**: a curb segment is a set of frontage edges with roles 2–7 (role 2 only on real lanes)
projected onto their road side and merged with ≤ 4 m gaps; civic, school and rooftop records give nothing.

* Segment chance by role: 7 → 0.45, 6 → 0.45, 5 → 0.35, 3/4 → 0.22, lanes → 0.12. Rows are 4–16 bays with
  2.5–9 m gaps; a blocked bay ends the row; rows shorter than 3 bays are dropped.
* Bay position by side class: on a sidewalk side the bay ends 0.25 m short of the kerb (gutter); on an arcade side
  it sits up to 0.4 m outward (stays off the apron); on a no-sidewalk side it shifts outward into the asphalt band
  (≥ 0.7 m from the wall, ≤ 1.6 m past the carriageway edge).
* A bay is dropped when it is:
  * within cross-road half width + 10 m of a real junction (arc length **and** straight line, for curved roads);
  * within + 4 m of a lane mouth, or within + 2 m of a driveway / aisle / access way meeting the road on that side;
  * within 4 m of a mapped `footway=crossing`;
  * touching a building footprint (repaired, holes kept), another road's carriageway, school / campus / court /
    parking / construction ground, a street-tree trunk or a lamp pole;
  * within 0.3 m of a mapped sidewalk line, or overlapping another bay;
  * leaving less than 3.5 m (two-way) / 3.0 m (one-way) / 2.6 m (lane) of clear carriageway (commercial curbs
    claim the carriageway first).
* Red kerb lines are clipped where a stall row claims the curb. Elsewhere they are unchanged.
* Deterministic: the per-segment RNG is seeded by the sha256 of the segment id. The placement table is
  `urban_identity/curb_segments.json.gz` (`acw.curb_segments/0`: side runs, segments, rows, bays).

Result: 2,289 curb segments, 659 hosting rows, **792 rows, 6,204 bays** (by class: sidewalk 1,865, arcade 2,413,
none 1,926; by role: 7: 1,202, 6: 2,305, 5: 473, 3/4: 508, lanes 1,716). Rejections: junction / driveway /
crossing 3,296, carriageway clearance 2,132, building 1,117, mapped sidewalk 272, tree / lamp 114, overlap 39,
special ground 17.

## 4. Scooter mesh / material

* Four silhouettes in `build_street_identity.py`, at true size, origin on the ground:
  * step-through 125 cc — 40 tris;
  * maxi — 42 tris;
  * step-through with delivery top box — 50 tris;
  * compact e-scooter — 40 tris.
* Each is built from tapered body / seat, floorboard, leg shield + steering column, handlebar, and two hexagonal
  tyre cards. No mirrors, lights, logos or brands.
* One HISM per silhouette (4 components), on the **existing** `M_XinyiStreet` (opaque, two-sided, instanced).
  `xc_street` gets a `[branch]` for type 17: 8 muted fleet colours (white 25 %, black 20 %, silver 20 %, dark grey
  10 %, dark blue / dark red / beige / green-grey ~6 % each), 4 grime levels, white / black top box, dark seat /
  tyres / trim.
* No shadows: the darker bay fill acts as the contact shadow. At night there is a flat 0.12 street-level spill, so
  scooters read as dark-grey silhouettes rather than black holes.
* Placement: one scooter per occupied bay, never anywhere else.
  * row fill is 55–98 % (per row, so some rows are packed and some sparse);
  * nose toward the carriageway 70 %, yaw ±8°, ±0.15 m along the kerb, scale 0.97–1.0;
  * a scooter whose footprint would touch a building is dropped;
  * so is one whose footprint lands on raised-sidewalk ground as the ground shader sees it (one 0.1 m nudge
    toward the road is tried first).

## 5. Counts and culling

| | value |
|---|---|
| total scooters | **4,513** (a 2,062 · b 676 · c 1,104 · d 671); 1,691 bays left empty |
| triangles if all drawn | 193 k; ~8–10 k drawn at the densest LOW view |
| HISM components | +4 (scooters), 1 shared material, 0 new textures |
| cull | 160 m start → 220 m end (`STREET_HISM`); no shadows |
| bay paint | +52 k static triangles on the existing road-paint mesh (95 k → 147 k) |

Scooters in frustum inside the 220 m cull (before occlusion):

| view | scooters |
|---|---|
| st_zhuangjing | 208 |
| st_wuxing | 176 |
| fr_corner_b | 78 |
| fr_canyon_wuxing | 51 |
| st_yanji | 43 |
| fr_block_e420 | 40 |
| cb_songqin_arcade, cb_lane_zj239 | 19 each |
| e_lowpass_xinyi_rd | 2 |
| roof_ne1, roof_mid, d_overview_sw, a_skyline_nw (MID / HIGH) | **0** |

VERY LOW shows individual silhouettes, LOW shows rows of parked scooters, MID shows only the painted bay rows (a
darker kerb band), and HIGH shows nothing.

## 6. Sign band

In `xc_wall`, the 2 × 3 stroke-cell pseudo-glyphs (Phase A) and the older blocky glyph cells are deleted. Boards are
now plain colour panels with the dark board edge and a little grime toward the bottom; lit boards glow as flat
panels. Only sign-band lines changed in `xc_wall` (14 removed, 5 added; gate-checked). The vertical TC blade signs,
boxes and awnings (v0B) are untouched.

## 7. Validation

| gate (`evidence/street_v0c/harness/check_curb.py`) | result |
|---|---|
| no bay overlap; no bay inside junction clearance (exact straight-line check), on a crossing, across a driveway / access way, on a building or on a mapped sidewalk | PASS |
| rows only from frontage roles 2–7, role 2 only on lanes | PASS |
| every scooter within 0.3 m of a bay centre and inside the bay (+0.25 m); none on a building; none on raised-sidewalk ground | PASS (4,513) |
| sidewalk presence data-driven; 0 km sidewalk on service ways | PASS |
| frontage roles, ground data texture, trees, forest, lamps, lamp light, campus paint, rooftops: identical to HEAD | PASS |
| campus texture R / G / B identical (only A changed) | PASS |
| v0B signs / boxes / awnings identical | PASS |
| shader: only `xc_ground`, `xc_wall` (sign band), `xc_street` changed; nothing added | PASS |
| determinism: two full rebuilds → identical road paint, campus texture, curb table, street instances, scooter meshes | PASS |
| DXC ps_6_0 `-WX`, all 8 materials | ok (this SDK has no SPIR-V backend) |
| UE5.8 assets / level / capture stages, fresh reopen | PASS_LOOK_ASSETS / PASS_LOOK_LEVEL / PASS_LOOK_CAPTURE |

### Visual result (UE5.8 SceneCapture2D, HEAD vs v0C, `evidence/street_v0c/`)

New cameras (in `shots_extra.json`):

* `cb_songqin_arcade` — 松勤街, an arcade-side row, ~11 m eye;
* `cb_lane_zj239` — 莊敬路239巷1弄, a lane, ~16 m eye.

Changed pixels (|Δ| > 8/255), DAY / DUSK / NIGHT:

| view | changed px | read |
|---|---|---|
| cb_songqin_arcade | 11.0 / 9.7 / 9.9 % | strongest before / after: confetti mosaic on both sides → plain apron + lane asphalt, one white bay row packed with scooters |
| fr_corner_b | 4.5 / 4.9 / 5.0 % | Hangul-like boards → plain panels; corner pavers grey; residential arm without slab |
| st_zhuangjing | 2.5 / 3.0 / 3.0 % | grey sidewalks both sides, bay rows packed along both kerbs, red line yields to the rows |
| st_wuxing, st_yanji | 1.2–2.0 % | arcade aprons, rows along 吳興街 |
| cb_lane_zj239 | 7.7 / 2.5 / 7.6 % | lane: no slab, one bay row along the wall (deep shade) |
| fr_rear_a, fr_rear_b | ≤ 0.4 % | unchanged (distant ground only) |
| roof_ne1, roof_mid, d_overview_sw (MID / HIGH) | 0.7–1.8 % | ground tone only (sidewalk band → lane asphalt on residential streets); 0 scooters |
| g_101_closepass, a_skyline_nw | ≤ 0.25 % | unchanged |

Mean luminance over the 15 standard shots: DAY 77.4 → 77.3, DUSK 38.2 → 38.1, NIGHT 15.3 → 15.1. No clipping
change.

Iterations:

* **it1:** confetti gone, rows read immediately. Scooters were near-black at night, and the apron was a little
  pale.
* **it2:** night spill on scooters, apron darker / more mottled.

Earlier offline iterations fixed:

* parallel-arterial sidewalks being attributed to alleys (nearest-kerb test);
* invalid WFS footprints skipped by the tree-rejection list (the curb layer now uses repaired footprints);
* bays collapsing on the inside of tight bends;
* curved-road junction clearance.

## 8. Performance (SceneCapture2D 1080p, 40 captures per view; this workstation's iGPU-class proxy)

Same-session attribution, scooters on vs hidden in memory, 4 rounds in both orders:

| view | median Δ | min-of-40 Δ |
|---|---|---|
| st_zhuangjing (208 in frustum) | +0.91 ms | **+0.68 ms** |
| st_wuxing | +0.17 ms | +0.29 ms |
| cb_songqin_arcade | +0.43 ms | +0.17 ms |
| cb_lane_zj239 | −0.25 ms | +0.12 ms |
| fr_canyon_wuxing, fr_block_e420 | noise | ±0.1 ms |
| roof_ne1, roof_mid, d_overview_sw (MID / HIGH) | noise | **−0.25 … −0.01 ms** (0 drawn) |

* A shorter cull (120 → 170 m) saved only ~0.2 ms at st_zhuangjing, inside the noise, so 160 → 220 m is kept.
* HEAD vs v0C, separate sessions, median of 3: −2.0 … +2.6 ms per view, both signs, including views with no
  visible change. That spread is session drift, as in v0A / v0B.
* The ground / sign-band shader changes cannot be toggled in-session. They are ALU-neutral by construction (a few
  smoothsteps replace the scooter hash / pick6 / glyph strokes).

Verdict: ≈ +0.2–0.7 ms at LOW street views (slightly above the 0.5 ms target only at the single densest view),
≈ 0 at MID / HIGH.

## 9. Known limits / weakest remaining area

* **Street trees** are still generated by road class (`build_ground.py`, unchanged in v0C). About 4,150 of them
  (20 % of all trees) now stand on no-sidewalk / apron sides, e.g. 松勤街, where they read as trees in the
  road-edge asphalt. This is the weakest street-reality area left.
* Lanes are narrow and mostly in shade: the lane camera reads "no slab + a bay row", but it is not a strong image.
* Scooter silhouettes are boxy at VERY LOW (< 25 m). From 30 m they read as scooters; from 60 m as rows.
* Sidewalk width is still the HEAD 3.5–5 m band. Mapped widths are not used, because the single-channel encoding
  carries only the class.
* Unmapped residential streets inside the planned 信義計畫區 grid that do have sidewalks in reality stay
  "no sidewalk". OSM is the only evidence used.
* The WebGL preview passes no campus texture, so it shows no sidewalks (UE is the reference).

## 10. Recommendation for v0D

As planned:

* green painted pedestrian lanes on the **none / arcade** sides from this pass's class table (`curb_segments`
  already marks which curbs are free of stall rows);
* the real horizontal Traditional-Chinese storefront atlas on the now-plain sign band;
* the generic 便利商店 archetype with night glow;
* small-food / breakfast storefront states.

Add one cheap correctness item: restrict generated street trees to sidewalk-class sides (a filter after
generation, so the remaining trees keep their positions), and consider the planned-core / named-arterial
sidewalk default once imagery confirms it.
