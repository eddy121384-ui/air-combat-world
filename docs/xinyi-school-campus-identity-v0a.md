# Xinyi School & Campus Identity v0A

Status: **engineering validated + final visual polish pass done** on `feat/opus55-xinyi-visual-quality`, built on HEAD
`09b90b4`. Look-dev layer only: no accepted geometry, terrain, Taipei 101 or hero change; the accepted
triangle soup of all 25 tiles stays bit-identical (fail-closed check in `build_look_tiles.py`).

Inputs: `docs/xinyi-urban-identity-engineering-plan.md` (§3, §8, §11), the locked education snapshot
`data/lookdev_cache/osm_education_context.json.gz` (ODbL) and the accepted WFS footprints.

## 1. ARCH_SCHOOL = 7 and archetype safety

| path | before | now |
|---|---|---|
| `xc_wall` `isCivic = step(5.5, arch)` / `isPodium` / tower / old-stock palette tests | open-ended: arch 7 would be read as civic (stone facade) or podium | **left text-identical to HEAD.** School pixels never use their results: `xc_city` routes `arch == 7` (`[branch]`) to `xc_school_wall` / `xc_school_roof`, which replace base colour, roughness, metal, specular and emission of both wall and roof |
| `xc_roof` `isCivic` → `imperial` / `domeRoof` (variant 15 / 14 → gold glazed / white dome) | would catch 7 | same: overridden by `xc_school_roof` |
| `xc_roof` sheet-metal roof, painted 3 m equipment grid | any arch | overridden for schools (real tank / bulkhead props instead) |
| `build_look_tiles.py` `ARCH_NAMES`, weathering table | 0..6 (KeyError on 7) | include 7 (`ARCH_SCHOOL: 120`) |
| `build_rooftops.py` final `else:` | unknown arch → podium chillers / cooling towers | explicit `ARCH_PODIUM`, explicit `ARCH_SCHOOL` branch; unknown archetype **fails closed**; school roofs may only emit tank / bulkhead / solar |
| `build_urban_identity.py` `ARCH_NAMES` | IndexError on 7 | includes `school`; schools are not commercial-frontage candidates |
| far city / landmarks | constants 2, 3, 4, 6 only | unchanged (no 7); a registry landmark keeps its art direction over a school (0 conflicts) |
| flags | bits 0-3 | bit4 = school wall facing the schoolyard (open-corridor side); max A = 31 < hero tag 248 |

Because the accepted functions are untouched and school pixels are replaced after them, every non-school pixel
compiles and computes exactly as before; the data gates in §6 verify that nothing non-school carries archetype 7.

## 2. Campus membership (`tools/lookdev/campus_identity.py`)

Grade-A campus = rule, not a list: OSM `amenity=school` multipolygon relation, level elementary /
junior high / senior high / vocational, polygon ≥ 97 % inside the WFS building-source bbox. Exactly 9
campuses on the locked cache (a different count fails closed): 信義國小, 信義國中, 三興國小, 吳興國小,
博愛國小, 興雅國中, 光復國小, 松山工農, 喬治商職.

Membership is decided per building **group** (so a wing and its height-zone records stay consistent):

* accept: ≥ 97 % of the group footprint inside the campus polygon, or ≥ 85 % inside and ≥ 60 % covered
  by OSM-tagged school buildings;
* reject: straddling groups below those thresholds (a group override would repaint fabric outside);
* reject: groups abutting (≤ 1 m) a building group that lies mostly outside the campus unless OSM tags
  them as school buildings (an edge terrace continuing out of the campus is shop-house fabric).

Result: 114 school groups (263 WFS records) accepted, 12 boundary-straddling groups rejected (all
`straddles_campus_boundary`; the `abuts_outside_fabric` rule never had to fire), 0 registry-landmark conflicts.
The rejected groups are 15-415 m² edge terraces / out-of-campus fronts (overlays in
`evidence/.../membership/`). Archetype group counts change only by reassignment into `school`: podium 52 → 46,
walkup 829 → 802, huaxia 1478 → 1448, low 1226 → 1177, res_tower 409 → 407; civic and office are untouched.

## 3. School facade / roof grammar

School walls take `xc_school_wall` (replaces every wall output): pale tile / render with one palette per
campus (variant = hash of the campus id), restrained brick-red / ochre accent bands, strong floor beam bands and two
deliberately different sides:

* **classroom-window side** (enclosed): a 4.5 m structural bay with a solid pier, one pale sky-tinted window per
  bay (glazing ~0.25 linear, not dark), a centre mullion and transom, and a brick / ochre sill stripe under every
  window band;
* **corridor side** (walls facing the yard, flag bit4, 878 wall triangles = 35 % of school wall area): a continuous
  1.1 m parapet with an accent cap, a deep dark recess (~0.06-0.15 × wall, darker under the slab) with only a dim
  hint of the back wall, and one slender column per classroom (every 9 m, not every bay), so the recess reads
  as an unbroken horizontal band.

The far-field means are set from the same coverages, so beyond floor resolution the corridor side stays about
0.65-0.7 × the window side's brightness (mean campus luminance is unchanged versus the pre-polish candidate).
Roof parapets carry an accent coping (50 %).
Disabled for schools: sign bands, arcades, iron cages, AC rows, sheet-metal additions, shop-house window-grid
streaks. Every pattern converges to its mean when unresolved; night is mostly dark with a few lit classrooms and
corridor runs.

School roofs: `xc_school_roof` (bare concrete or green / grey PU waterproofing per wing, ponding stains; no sheet
metal, no painted equipment grid) plus real props from `build_rooftops.py`: 170 school roof parts get water-tank
clusters, an occasional stair bulkhead and an occasional solar heater. **Rooftop architecture:** school props go
into the ordinary `tank` / `bulkhead` / `solar` HISMs; there are no school-specific HISMs and no placeholder
instances. Versus HEAD the instance lists differ only on school roofs: removed ac 563, antenna 65, tank 270,
solar 46, bulkhead 38, addition 29, shed 23, cooling 18, machine 15, barrel 10, leanto 9; added tank 306,
bulkhead 25, solar 9 (total 31,150 → 30,404 instances). Every instance elsewhere is identical and in the same
order (`check_rooftops.py`).

## 4. Schoolyard

`T_XinyiCampus` (2048², same extent as the ground texture, box-filtered mips, ~21 MB with mips): R = Grade-A
campus signed distance (±16 m), G = court / playground signed distance (±8 m), B = surface id. `xc_ground` applies a
`[branch]` override after the accepted composite, so the accepted code path and texture are untouched: neutral grey
paved concrete inside the campus polygon, with sidewalks, greens, kerbs, roads and water keeping their mapped
surfaces on top, and the generic school / court / track classes suppressed inside campuses. The mask is inset
0.5 m + 0.6 × (pixel footprint − 1 m) so mip averaging cannot push it past the polygon edge.

## 5. Courts / pitches

12 tagged surfaces in the 9 campuses (11 pitches, 1 playground); 1 tennis pitch rejected (86 % under a building).
Surfaces are filled from the court signed distance with restrained matte greens / blues (one hue per campus for
basketball / volleyball / multi courts, green for tennis / badminton, muted grey-green for playgrounds) and an
analytic 12 cm outline 0.35 m inside the real edge; once the pixel footprint passes ~0.15 m the outline widens
inward with it (0.85 × footprint, max 0.8 m) and its coverage stays ~0.85, so the outer rectangle still reads at
mid range without leaving the court polygon. Standard basketball markings (scale 0.87-1.0) are drawn as
paint geometry (1,660 triangles, 6 cm above terrain, 15 cm lines, cull 900 m) only for tagged sports on clearly
elongated pitches that fit the standard court at ≥ 85 % scale (6 surfaces: 博愛 ×2, 興雅 ×2, 吳興 ×2; line weight
0.21 m / footprint, slightly brighter paint); the other
pitches (near-square or untagged) get surface + outline only because their long axis is ambiguous.

**No running track is produced.** OSM has 0 `leisure=track` / `sport=athletics|running` features here;
the `track_candidate` audit hint is never a render input; the campus layer suppresses the generic
ground "track" class inside campuses.

## 6. Validation

### Containment gates (zero tolerance, all PASS; `evidence/school_campus_v0a/harness/`)

| gate | result |
|---|---|
| non-school building vertices (position, normal, UV0-2, archetype, flags), 1,457,808 corners | 33,240 changed, **0 on non-school records** (`check_tiles.py`) |
| accepted triangle soup | bit-identical, fail-closed in `build_look_tiles.py` |
| Grade-A campus rule | exactly 9, otherwise the build stops |
| shop-house capture / straddling groups | 0 / 12 rejected |
| campus texture samples outside campus polygons | 0 of 4,000,000 random samples at mip 0, 0 / 52,248 boundary probes 5 cm outside, 0 at simulated box-filter mips 1-5 with the shader inset (`check_campus_mask.py`) |
| court mask outside court polygons (+0.35 m) | 0 |
| accepted ground texture, road paint, trees, forest, lamps, lamp light texture, tree / lamp / forest meshes | byte-identical to HEAD |
| rooftop instances outside school roofs | identical and in the same order |
| school grammar on non-school buildings | none: the shader branch keys on archetype 7, which only the 114 groups carry |
| accepted shader functions (`xc_wall`, `xc_roof`, `xc_taipei101`, `xc_backdrop`, `xc_foliage`, `xc_prop`) | text-identical to HEAD; accepted `xc_ground` composite unchanged, campus layer is an override after it |
| running tracks | 0 (OSM has none; the generic track class is suppressed inside campuses) |

### Framebuffer comparison (informational; replaces the earlier "outside-campus pixels = 0" rule)

A zero-pixel framebuffer rule is not achievable in real UE5.8: campus-local changes legitimately propagate through
virtual-shadow-map allocation, occlusion, reflections, bloom, GI / AO and HISM cluster ordering. An early attempt
kept 1 mm invisible "ghost" copies of the removed legacy roof props to preserve HISM trees; it did not reach zero
either and was removed as architecture debt. Containment is proven by the data gates above.

Controlled capture (VSM, occlusion, bloom, reflections, Lumen GI, SSAO off; HEAD vs candidate, 11 shots): changed
pixels outside the campus mask are 0-2,693 per frame in DAY (0.00-0.13 %), 0-3,019 in DUSK, 0-1,674 in NIGHT;
median |Δ| 7-18 /255; 14-92 blobs per frame, largest 285 px, located on roofs of distant towers (median 34-95 px
from the mask). Diff maps show sparse rooftop-prop blobs on tower tops and skyline edges, no coherent ground,
material or geometry change.

Attribution probe: the candidate level built with HEAD's rooftop instance file shows 12 / 0 / 2 / 11 / 0 / 0 / 0 /
0 / 10 / 0 / 18 px (a_skyline ... roof_mid; 53 px total, max 20 /255) in the same DAY controlled mode. So about
98 % of the outside difference comes from the HISM instance-list change (cluster tree / LOD-cull transition of
rooftop props), and the rest is renderer-global shadow / visibility allocation. They are secondary effects, not
campus-content leakage, and are documented rather than engineered around. Full-lighting comparisons also show
±1 /255 specks across the frame from bloom / reflections of the new school facades.

### Performance (SceneCapture2D 1080p, 6 views x 40 captures per run, 3 runs each, same session settings)

| view | HEAD median of 3 (ms) | candidate median of 3 (ms) | delta |
|---|---|---|---|
| d_overview_sw | 83.5 | 82.2 | -1.3 |
| e_lowpass_xinyi_rd | 67.3 | 68.2 | +0.9 |
| f_rooftops_wuxing | 71.8 | 71.2 | -0.5 |
| h_sys_memorial | 78.9 | 79.8 | +0.9 |
| roof_ne1 | 85.2 | 86.3 | +1.1 |
| roof_mid | 85.5 | 90.4 | +4.9 |
| **mean** | **78.7** | **79.7** | **+1.0 ms (+1.2 %)** |

The candidate's first run after a rebuild is a cold-start outlier (84-104 ms); excluding it the mean delta is
+0.4 ms (+0.5 %), inside HEAD's own run-to-run spread (up to 6 ms on roof_mid / roof_ne1). The earlier +5-14 ms of
the non-mipped campus texture is gone. Added GPU memory about 21 MB (campus texture with mips); one added draw
(court paint actor); no new HISMs; 746 fewer rooftop instances. HEAD and candidate were built and measured
sequentially, not interleaved, so differences under ~2 ms are not significant.

### DAY / DUSK / NIGHT sanity

`sheets/fin_dday_dusk_night.png`: DAY reads as pale banded classroom wings around a grey yard with muted courts;
DUSK keeps warm side-lit corridors and cream render without clipping (mean luminance 34, 0.01 % pixels > 250);
NIGHT keeps schools mostly dark with a few lit classrooms / corridor runs and no emissive hot spots (mean 17).

## 7. Known limits / follow-ups

* Artistic: interior court lines still resolve only within a few hundred metres (by design at MID the court reads
  by its fill and outer rectangle); the yard is flat grey by design (no lanes or tracks).
* Data: untagged and near-square courts get outlines only; 13 of the 25 OSM campuses lie outside the WFS area
  and are not Grade A.
* The OSM education snapshot is ODbL; credit it wherever the derived layers ship.
* Deferred by design: campus edges, gates, flagpoles, hoops, 司令台, covered walkways, school signage, any running
  track (only a curated, cited per-track override may add one).

## 8. Final visual polish (shader-only, `xc_school_wall` + campus / court-paint branches)

Only `xc_school_wall`, the campus `[branch]` of `xc_ground` and the court-paint `[branch]` of `xc_paint` changed;
`xc_wall`, `xc_roof`, `xc_taipei101`, `xc_backdrop`, `xc_foliage`, `xc_prop` remain text-identical to HEAD. No
textures, geometry, HISMs or offline data changed. Evidence: `sheets/polish_*` (before = `fin_c_full_*`, after =
`pol2_full_*`).

| gate (after polish) | result |
|---|---|
| `check_tiles.py` | 0 non-school corner changes, PASS |
| `check_rooftops.py` | school roofs only, others identical + ordered, PASS |
| `check_campus_mask.py` | 0 leaks at mip 0-5, PASS |
| campus-mask mean luminance DAY / DUSK / NIGHT | 103.0 / 46.3 / 15.5 (pre-polish 103.0 / 46.3 / 15.6), 0 % > 250 |
| controlled outside-mask diff vs HEAD | identical (±7 px) to the pre-polish candidate in 32 of 33 shot × ToD frames |

The exception is DUSK `a_skyline_nw`: a sign-symmetric ±1 /255 shift over the frame (mean 0) plus ~6k isolated
specks (largest 9 px, median 104 px from the nearest campus mask) on distant fabric. It reproduces exactly on
re-capture, sits nowhere near the campuses and forms no coherent region; it is consistent with renderer-level
floating-point / dither differences after the shared city material recompiles, not campus-content leakage
(containment is proven by the data gates). The exact cause was not isolated.

Performance (same protocol, 3 runs): HEAD 78.7, pre-polish candidate 79.7, polish **79.0 ms** mean of medians;
roof_mid 85.8 ms (runs 86 / 86 / 85; HEAD 85.5).
