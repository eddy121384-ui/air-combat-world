# Xinyi — Taipei Street Reality v0D: pedestrian / ground reality

Status: **accepted**. Branch: `feat/opus55-xinyi-visual-quality`, built on `3c5d92d` (v0C). Includes the facade-shader
performance pass (section 9).

This is a look-dev layer only. Unchanged from HEAD, byte for byte:

* the 25 look tiles, frontage roles, and ground data texture;
* the campus texture, including A, the v0C curb class;
* the v0C curb table (side classes, 792 scooter rows, 6,204 bays);
* all street instances (signs, boxes, awnings, 4,513 scooters);
* forest, lamps, and rooftops.

The shader is unchanged by the walkway / tree work; section 9 optimises `xc_city` / `xc_wall` with no change to output.

What changed:

1. Green painted pedestrian walkways (標線型人行道) are added to the existing road-paint mesh. They appear **only where
   the Taipei Traffic Engineering Office maps one**, and they yield to every v0C curb priority.
2. Generated street trees standing on asphalt, arcade apron, walkway paint or at crossings are suppressed. This is a
   filter after generation: survivors keep position, order and attributes.

Not in v0D (per the brief):

* 「人行道」 road text;
* left-turn boxes;
* storefronts, convenience stores, the TC atlas;
* YouBike, cabinets, furniture;
* replacement trees.

## 1. Green walkway research (narrow; verified vs abstraction)

Grades: **[O]** observed in a cited source, **[I]** inferred, **[P]** implementation abstraction.

| question | finding | grade |
|---|---|---|
| what it is | 人行道標線 marks a pedestrian-only way on the road surface. Its surface **may be coloured green** (道路交通標誌標線號誌設置規則 Art. 174-3, as amended 2026-03-11) | [O] |
| painted directly on roadway | yes. It covers part of the asphalt **and the side drain** (側溝) where no physical sidewalk fits | [O] |
| separation from traffic | a **路面邊線** (road edge line): **white solid, 15 cm** (Art. 174-3 → Art. 183) | [O] |
| kerb-side no-stopping line | a red (no stopping) or yellow (no parking) line is required. Taipei's marking-restoration note: 「禁停標線應緊鄰路面邊線繪設（不得有間隔）」, i.e. drawn **tight against the edge line, no gap** | [O] |
| colour | national colour sample **No. 6 green** (Art. 9, named in the Taipei note), cold-plastic anti-slip coating. Drain grates are masked, not painted. Bike lanes use brick red, not green | [O] |
| width | ≥ 1.5 m recommended (0.9 m clear passage). In the Taipei dataset, recorded area / length = **1.50 m** (5–95 %: 1.49–1.52 m, 162 records) | [O] |
| segmentation / text | 「人行道」 text and pictogram at the start and at **every junction entry**. Joins a physical sidewalk at a junction where one exists | [O] |
| where used | service-level roads only (collector, 巷 / 弄). Main and secondary roads get physical sidewalks. Recommended for lanes ≤ 6.4 m, with one-way control | [O] |
| where actually painted | **open dataset 「臺北市標線型人行道」** (Taipei Traffic Engineering Office, data.gov.tw 145867, geometry dated 2024-06-06): 3,526 patches city-wide, **509 in the look extent** | [O] |
| where NOT | arterials; across junction mouths / zebra / stop line; on a raised sidewalk; on school / civic ground; under scooter bays | [O] arterial, junction / [I] rest |
| geometry | the city polygons are **schematic**: drawn about 1.26 m wide and often shorter than the recorded length, so they are used as *where* evidence, not as paint outlines | [O] |
| how it is drawn here | 1.5 m road-aligned green ribbon + 15 cm white edge line + 12 cm red line abutting it on the carriageway side | [P] |

Sources:

* Regulation: https://laws.gov.taipei/law/LawSearch/LawExport/FL012456?type=0
* Taipei marking notes §12: https://www.treca.org.tw/component/k2/download/24102_855c04d0659a29741aa14ca6ee9fa585.html
* Rules summary: https://c.8891.com.tw/news/18158
* Dataset: https://data.gov.tw/dataset/145867 (Open Government Data License v1.0; attribution 臺北市政府交通局交通管制工程處)

Locked snapshot: `tools/lookdev/fetch_ped_walkways.py` →

* `data/lookdev_cache/taipei_marked_walkways_xinyi.json.gz`: 27 KB, EPSG:3826 kept projected;
* `…meta.json`: zip sha256 `cccd6c90…92dd2`, licence, counts.

The SHP / DBF readers use the standard library only. The transform is the WFS-building route (EPSG:3826 → pyproj →
lon/lat → ENU).

## 2. Walkway placement rules (`curb_zone.py` §3)

1. **Evidence.** Each city polygon is assigned to the parallel road side (|cos| ≥ 0.8) whose kerb is nearest. Its
   arc-length interval is extended by half the recorded-minus-drawn length (≤ 3 m), then merged with gaps ≤ 3 m.
   Result: 450 of 509 polygons assigned; 59 have no parallel drivable side.
2. **Curb priority, highest first** (tested on 1 m pieces):
   1. junction / lane mouth / driveway / mapped crossing clearance:
      * the major cross road's half width + 7 m, which clears the painted zebra (+2.5…+6.5 m) and the stop line;
      * a lane mouth + 1 m;
      * a driveway on that side + 0.5 m;
      * a mapped crossing ± 2 m, both along the centreline and by distance;
   2. raised sidewalk, both the side's own v0C class and the class the ground shader draws there (nearest kerb);
   3. special ground: school / campus / court / parking / construction;
   4. **v0C scooter bay rows (locked; never moved)**;
   5. painted walkway;
   6. ordinary road edge.

   A piece is also dropped when it:
   * is on trunk / primary / secondary;
   * hits a building footprint;
   * hits another carriageway or a mapped sidewalk line;
   * hits a park / mapped tree;
   * leaves less than the v0C carriageway clearance (opposite bays counted).
3. **Offset.** The white line sits at the city polygons' median offset, clamped to W/2 − 0.5…+1.0 m. One inward
   shift per run (≤ 0.8 m) clears WFS footprints, which include the arcade floor, so the walkway hugs the wall line.
   49 runs are shifted.
4. **Runs.** Runs shorter than 8 m are dropped. Ends are square; no termination text in v0D.
5. **Colour.**
   * Base sRGB (80, 114, 90) for recent paint, (90, 111, 95) for 2018 and older, from the city install year.
   * Per run: ±3 jitter.
   * Along the run: ±6 % value and up to 35 % fade toward road grey, on 6 m knots, using per-quad vertex colours in
     the same opaque mesh.
   * The existing paint shader adds tyre wear. No shader change, no texture, no translucency.

### Result

| | value |
|---|---|
| runs / total length | **266 runs / 11.69 km** (median 36 m, 8–159 m) |
| by road | 巷弄 service lanes 8.21 km, residential 3.38 km, other service 0.10 km |
| by side class | none 10.69 km, arcade 0.99 km, raised sidewalk **0** |
| city evidence sampled | 19.4 km (none 14.2, arcade 1.9, sidewalk 3.3) → 60 % painted |
| not painted (m) | raised sidewalk 3,390 · junction / driveway / crossing 1,861 · building 754 · special ground 635 · **scooter rows 512** · short run 375 · clearance 111 · other 72 |
| install years | 2018: 144 runs, 2019–2021: 92, 2013: 7, unknown: 23 |

**Scooter interaction:** 0 scooter rows, bays or scooters removed or moved. The curb table and street instances
are byte-identical. In 512 m the city maps a walkway where a locked v0C bay row stands; the walkway breaks there.
The regulation allows parking lines beside a walkway (Art. 174-3), so this break is a v0C-locking abstraction.

**Finding for later:** 3.3 km of city walkways lie on sides v0C classifies as raised sidewalk, mostly the unmapped
tertiary default and OSM sidewalk tags. Some of these sides probably have a painted walkway rather than a kerb.
Not changed here: it would move ground classes and scooter bays.

## 3. Street-tree reality filter (`build_ground.py`)

Generated street trees (kind 0, kerb + 1.8 m on every road ≥ local) are kept only when all of these hold:

* the ground shader's curb class under them is raised sidewalk (≥ 0.9);
* they are clear of scooter bays (+0.3 m), walkway bands (+0.5 m) and mapped crossings (2 m).

Park (10,567) and OSM-mapped (290) trees are never dropped; the build fails closed if the filter would drop one. The
RNG stream is consumed for every candidate, so forest, lamps and survivors are unchanged.

| | count |
|---|---|
| street-tree candidates | 9,544 |
| suppressed: lane-edge asphalt | 3,288 |
| suppressed: arcade apron | 712 |
| suppressed: mapped crossing | 145 |
| suppressed: walkway | 132 |
| suppressed: class boundary | 42 |
| **total trees: before / suppressed / after** | **20,401 / 4,319 / 16,082** |

In-frustum trees, before occlusion (HISM cull 2.6 km):

| view | street trees | all trees | within 150 m |
|---|---|---|---|
| st_zhuangjing | 598 → 221 | 961 → 584 | 26 → 24 |
| st_wuxing | 3,313 → 1,671 | 4,882 → 3,240 | 16 → 12 |
| st_yanji | 3,002 → 1,569 | 4,888 → 3,455 | 13 → 7 |
| cb_songqin_arcade | 1,043 → 569 | 3,308 → 2,834 | **25 → 0** |
| wk_keelung380 | 2,632 → 1,535 | 7,577 → 6,480 | 51 → 33 |
| wk_xinyi5_150 | 65 → 1 | 79 → 15 | 14 → 0 |
| roof_ne1 (MID) | 4,653 → 2,816 | 13,778 → 11,941 | 0 |
| roof_mid / d_overview_sw (HIGH) | 3,663 → 1,985 / 1,166 → 672 | 9,481 → 7,803 / 2,062 → 1,568 | 0 |

## 4. Review cameras and visual result

New LOW cameras, in `shots_extra.json` of the evidence harness:

* `wk_keelung380`: 基隆路一段380巷, eye ~17 m over the centreline. City walkway on the north side (arcade + none),
  and a row of trees on the apron in HEAD.
* `wk_xinyi5_150`: 信義路五段150巷, eye ~17 m. City walkway on the east side (2021), and trees in the road edge.

Changed pixels (|Δ| > 8/255), DAY / DUSK / NIGHT, HEAD vs v0D:

| view | changed px | read |
|---|---|---|
| **wk_keelung380** | 10.0 / 8.3 / 7.1 % | **strongest before / after.** Before: a row of trees grows from the apron and road edge. After: no trees; asphalt \| red \| white \| green walkway along the arcade side. It stops at the zebra, resumes past the junction, and yields to the scooter row at the near end |
| wk_xinyi5_150 | 6.4 / 4.7 / 4.9 % | trees gone from the road edge. The walkway starts past the zebra and stop line; in shade it reads mostly as the white edge line |
| cb_songqin_arcade | 62.6 / 43.6 / 39.9 % | trees growing out of the apron / lane asphalt are gone. The street now shows v0C's wide pale apron and setback ground (see §7). No walkway is mapped here |
| st_yanji | 2.5 / 2.7 / 2.0 % | mid-distance roadside trees gone; 0.6 km of walkway in frustum, mostly occluded |
| fr_canyon_wuxing, fr_block_e420, roof_ne1, roof_mid, d_overview_sw, f_rooftops | 0.3–1.7 % | thinner street-tree rows on residential streets. No visible green thread or shimmer at MID / HIGH |
| st_zhuangjing, st_wuxing, fr_corner_b, cb_lane_zj239, fr_rear_a / b, e_lowpass, g_101, a_skyline | 0–0.6 % | unchanged in practice |

DAY / DUSK / NIGHT:

* **Day:** the green reads as faded municipal paint, greener than asphalt with no game-UI saturation.
* **Dusk:** dark green-grey.
* **Night:** dark green under the lamp pools. No glow, no clipping.

Mean luminance moves only where trees left the frame.

Iterations:

* **it1:** placement right, but the green was a flat, fairly saturated stripe. At xinyi5 the walkway ran into the
  generated junction zebra; the junction clearance only covered OSM crossings.
* **it2:** major-junction clearance raised to the cross road's half width + 7 m. Restrained base colours with patchy
  fade / value variation along the run.
* **final:** ribbon quads 4 m instead of 2 m on straight stretches (walkway triangles halved, no visible change).

Offline fixes caught by the gate before UE:

* 117 m of band sat on the shader's raised-sidewalk ground at junctions. Fixed: test the class the shader draws.
* 7 runs passed within 1.5 m of a mapped crossing that does not cut their centreline. Fixed: distance test.

## 5. Validation (`evidence/street_v0d/harness/check_v0d.py`): CHECK_V0D_PASS

| gate | result |
|---|---|
| curb table (side classes, segments, rows, bays) byte-identical to HEAD | PASS |
| street instances (signs, boxes, awnings, 4,513 scooters) identical | PASS |
| ground + campus textures, campus paint, forest, lamps, lamp light, meshes identical | PASS |
| shader: only `xc_wall` / `xc_city` changed (section 9) | PASS |
| road paint: every HEAD triangle kept except 90 red kerb-line tris (replaced by the walkways' abutting red line); additions only walkway green / white / red | PASS |
| trees: survivors are an order-preserving subsequence of HEAD with identical attributes; all park / mapped trees kept; every kept street tree on raised sidewalk, clear of bays / walkways / crossings | PASS |
| walkways: ≥ 8 m; within 8 m of a city polygon; never on arterials or the shader's raised sidewalk; clear of bays (≥ 0.3 m), buildings, special ground, other carriageways, mapped crossings, junctions | PASS (266 runs) |
| determinism: two full rebuilds → identical paint, trees, walkway table, curb table, textures, street instances | PASS |
| UE5.8 assets / level / capture (fresh reopen) | PASS_LOOK_ASSETS / PASS_LOOK_LEVEL / PASS_LOOK_CAPTURE |

## 6. Performance (SceneCapture2D 1080p, 40 samples per view; iGPU-class proxy)

| item | value |
|---|---|
| road-paint triangles | 147,038 → **165,398 (+18,360, +12.5 %)**, same single opaque mesh, no new actor / texture / material |
| tree instances | 20,401 → 16,082 (−21 %) |

Tree filter, measured in a HEAD session with the suppressed instances removed in memory. 5 interleaved pairs, both
orders, median Δ (min-of-40 Δ):

| view | Δ |
|---|---|
| st_zhuangjing | −0.16 ms (−0.38) |
| st_wuxing | −0.75 ms (−0.71) |
| st_yanji | −0.09 ms (−0.18) |
| fr_canyon_wuxing | −0.09 ms (−0.06) |
| roof_ne1 | −0.32 ms (−0.35) |
| roof_mid | −0.04 ms (−0.29) |
| d_overview_sw | +0.12 ms (−0.03) |
| wk_keelung380 | **+0.88 ms (+0.85)** |
| wk_xinyi5_150 | **+0.74 ms (+0.63)** |
| cb_songqin_arcade | **+7.53 ms (+7.49)** |

The three increases are real, not an HISM artefact: the rebuilt v0D session reads the same (cb_songqin_arcade 61.2
vs 60.9 ms). Near crowns were cheap occluders; the facade / ground pixels behind them now get shaded. The trees
themselves cost less everywhere.

Walkway paint: below cross-session noise. v0D vs filtered-HEAD sessions differ by −0.2…+0.8 ms, uniformly,
including views with no walkway near. The whole paint mesh on / off costs 1.1–1.9 ms in every view, MID / HIGH
included, because it is never culled. The walkways' triangle share (11 %) bounds them at ≈ 0.15–0.2 ms, about the
same in every view.

Verdict: LOW street views −0.75…+0.9 ms, except **cb_songqin_arcade +7.5 ms** (revealed facades). MID / HIGH ≈ 0.

## 7. Weakest remaining pedestrian-ground issue

* **The v0C arcade apron / setback ground is now exposed.** With the trees gone, 松勤街 and similar streets read as
  wide, flat, pale concrete between the kerb and the buildings, plus a large frame-time rise at cb_songqin_arcade.
  This is the next ground-reality item (apron width / tone, and where real setbacks are). Adding trees back is not
  the fix.
* Painted walkways have no 「人行道」 text yet, so a walkway in deep shade reads as only a white edge line.
* 3.3 km of city-mapped walkways sit on sides classified as raised sidewalk (§2).
* The whole road-paint mesh costs 1.1–1.9 ms even at HIGH. A distance cull / split would help all bands (pre-existing,
  outside v0D).

## 8. Recommendation: v0E — Storefront Identity

* **Horizontal Traditional-Chinese storefront atlas** on the v0C plain sign band: original generic shop names from the
  existing atlas pipeline / blacklist, 2–4 characters, 2–3 board styles. Night: lit-board subset only.
* **Generic Taiwan convenience-store archetype** (audit §6):
  * placement by commercial corners (role 6/7 corners, ≥ 180 m apart; ~50–90);
  * full-height glazing, a white fascia with one generic stripe, no chain livery;
  * a bright interior night glow as the signature;
  * it can reuse the facade grammar on the ground-floor band.
* **Breakfast / small-food storefront grammar:** open frontage, awning / steel-shutter states by time of day, warm
  interior at dusk, on role 5–7 old-stock frontage.
* Since v0E touches `xc_wall`: profile its cost at a low eye height first. cb_songqin_arcade shows that close facade
  pixels are already the dominant LOW-view cost.

## 9. LOW-view performance pass: facade shader (follow-up, same uncommitted v0D)

Problem: removing the invalid near street trees exposed facade pixels they had occluded, and `cb_songqin_arcade` read
about +7.5 ms against HEAD. The tree removal is kept; the facade cost is fixed in the shader.

### Measured attribution (same-session, interleaved, both orders; 1080p SceneCapture2D; experiment harness only)

| experiment at cb_songqin_arcade | Δ |
|---|---|
| street trees re-added (HEAD-equivalent), old shader | −7.9 ms (so +7.5…+7.9 is real, and it is the exposed pixels) |
| whole `xc_city` material replaced by a flat colour (compiled and verified) | −7…−8 ms at this view (−17 ms at wk_keelung380) |
| wall shading only → flat | −10…−12 ms |
| roof finish evaluated on wall pixels → flat | **−3…−5 ms** |
| shadows off (all) | −10.5 ms (shadow cost is per visible pixel, unchanged by this pass) |
| scooters / signs / awnings / lamps hidden | −0.8 ms / small |
| road paint hidden | −2.4 ms |
| screen percentage 50 % | no change (probably ignored by SceneCapture; not used as evidence) |
| cages + AC removed / grime removed (inside the wall) | −1.4 / −1.6 ms each, noisy, no single dominant block |

Conclusion: the cost is **building pixel shading**, and about half of what could be removed is waste. The material
is branchless: every wall pixel also evaluated the full roof finish (`xc_roof`), every school building evaluated
both the generic and the school grammar, every upper-floor pixel evaluated the shopfront / arcade / sign-board
block, and every day pixel evaluated the whole night-emission block that is multiplied by `Night = 0`.

### Implemented (tools/lookdev/shaders/xinyi_city.hlsl: `xc_city` and `xc_wall` only)

1. **Wall XOR roof.** `xc_wall` runs only where `isRoof < 1`, `xc_roof` only where `isRoof > 0` (`isRoof` is exactly 0
   or 1 on building meshes; both run in the blend). School buildings run only their own wall / roof (they replaced every
   output of the generic path).
2. **Street band.** Arcade, shopfront, shutter and sign-board work only for `h < 1.72 floors`. Above that every mask
   was already exactly 0.
3. **Day emission.** The night block is skipped when `Night == 0` (a global material-parameter value). Dusk and night
   run it unchanged.

No LOD threshold, no per-street / per-camera special case, no visible simplification: outputs are mathematically
identical to the old shader (blend aside).

### Result (fresh materials built together after the last asset stage; 4 sessions agree, e.g. 6 rounds each)

old v0D shader → optimised, same session:

| view | Δ ms |
|---|---|
| cb_songqin_arcade | **−6.6** (75.2 → 69.1) |
| st_zhuangjing | −4.7 |
| st_wuxing | −6.3 |
| st_yanji | −5.2 |
| wk_keelung380 | −6.8 |
| wk_xinyi5_150 | −4.4 |
| MID roof_ne1 | −6.9 |
| HIGH d_overview_sw | −6.8 |

**Measured directly:** old v0D shader → optimised v0D shader, as in the table above (cb_songqin_arcade −6.6 ms).

**Inferred, not measured:** the relation to HEAD. Before this pass, v0D was +7.5…+7.9 ms vs HEAD at cb_songqin_arcade
(tree-filter experiments) and within ±0.8 ms of HEAD at the other LOW views. Combining the two measurements suggests
about +1 ms at cb_songqin_arcade and 4–7 ms faster than HEAD elsewhere. A direct final-v0D vs HEAD comparison was not
obtained (the in-memory tree re-add was unreliable in the later sessions). MID / HIGH gain about 6–7 ms vs the old v0D
shader, measured (the roof / wall waste was paid on every building pixel).

### Visual regression (opt vs the accepted v0D frames, 19 cameras × DAY / DUSK / NIGHT)

Changed pixels (|Δ| > 8/255): ≤ 0.11 % in every view, 0.00 % in most. The same build against itself differs by up to
0.107 % (st_wuxing) and 0.073 % (zhuangjing), so the difference is render noise: Lumen / VSM speckle at edges, not a
shader change. Phase A frontage, v0B signs and awnings, the scooter rows, the walkways, the school grammar, rooftops,
Taipei 101, far city: unchanged. DXC ps_6_0 `-WX` passes for all 8 materials (this SDK has no SPIR-V backend).
`check_v0d.py`: PASS, with the shader gate now "only `xc_wall` / `xc_city` changed".

### Measurement caveats (found while doing this)

* A first A/B was invalid: swapped-in materials were still compiling and rendered with a fallback. Fixed by waiting for
  shaders (`finish_loading_before_screenshot`) after each swap.
* Materials built before an asset-stage run carry stale state; comparisons must use materials built together.
* The in-memory tree re-add state is flaky when created after a material swap; the −7.9 ms HEAD-equivalent figure is from
  a session where it was created first. One later session gave only −2.9 ms for the optimisation vs −6.6 ms in the
  four others; it is listed, not averaged away.

### Remaining

cb_songqin_arcade is probably still about +1 ms over HEAD (inferred, see above). The rest of the wall cost (≈ 10 ms of flat-wall removal, mostly
window / cage / weathering ALU) is spread over many small blocks; the next lever would be a derivative-gated cheap path
at MID / HIGH, which needs visual sign-off. v0E should budget against this: the shader is now about 6 ms cheaper per
exposed frame, and the shopfront block it adds belongs inside the street-band branch.
