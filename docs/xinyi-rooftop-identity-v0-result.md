# Xinyi Rooftop Identity Pass v0 — tin roofs & rooftop chaos

Status: **visual layer, DAY verified, DUSK / NIGHT sanity-checked**. Building geometry, the cloud system
(OFF / HIGH / LOW / CHEAP), sky / atmosphere, Taipei 101, terrain and roads are untouched.

## Verdict

**Worth keeping.** From oblique / medium-altitude views the old residential fabric now reads as Taipei's
patchwork roofscape — 頂樓加蓋 sheet-metal rooms with gable, barrel and mono-pitch roofs in blue-grey,
oxidised red, faded / teal green, galvanised and off-white, stair bulkheads with water tanks on top,
AC rows along the parapets — while modern towers and the planned Xinyi core stay clean. The new room
geometry is effectively free; the whole rooftop layer costs about what it did before.

## Typology

`tools/lookdev/build_rooftops.py` (deterministic per building, constrained to the accepted footprint,
inset 0.8 m for the parapet; buildings are not edited). Four new instanced types next to the existing
props:

| type | mesh | role |
|---|---|---|
| `addition` | unit room + low-pitch gable sheet roof with eaves (18 tris) | the classic 頂樓加蓋 room |
| `barrel` | unit room + 6-segment curved sheet roof (36 tris) | curved-roof variant |
| `leanto` | open mono-pitch awning on 4 posts (50 tris) | drying / roof-garden covers |
| `bulkhead` | painted concrete stair room, slab cap, door (26 tris) | 樓梯間, tanks often on top |

Existing `shed` is reused as a flat-roof room and as the rare second storey on a walk-up room.

Layout: for each roof part the **largest inscribed rectangle** in the roof frame (0.5 m grid,
maximal-rectangle scan) holds 1–3 rooms in a row along its long axis, starting at one end, with mixed
heights (2.2–3.4 m). Earlier attempts (anchoring rooms on the footprint's minimum rotated rectangle,
then sliding toward the centre) failed on ~70 % of walk-up roofs; the inscribed rectangle places rooms
on ~91 % of attempts. Rooms smaller than 2.6 m × 2.6 m / 8 m² are skipped (they read as thin prisms).
Tanks come in clusters of 1–3 on the roof or on the bulkhead roof; AC condensers line the parapet.

## District-sensitive rules

Driven by the existing look record (archetype, planned-core flag, weathering as an age proxy) and roof
size:

| archetype | 頂樓加蓋 probability | roof coverage (long axis) | other |
|---|---|---|---|
| walk-up (4–5 fl.) | 0.80 | 55–95 % | bulkhead + tanks, solar, antennas, AC rows; 9 % second storey |
| huaxia (6–12 fl.) | 0.42 | 30–65 % | larger bulkhead / machine room, tanks |
| low (1–3 fl.) | 0.42 | 40–85 % | more lean-tos and flat sheds |
| residential tower | 0.12 | 15–35 % | taller machine / stair bulkhead, small sheds |
| office / glass | none | — | machine room, cooling, window-cleaning crane (unchanged) |
| podium / civic | none | — | chillers / cooling towers; civic & landmark roofs untouched |

Multipliers: planned Xinyi core ×0.45 and a neutral palette; age (weathering) ×0.7…1.3. Result: 1,706
roof parts carry rooms (walk-up 767, huaxia 575, low 336, towers 28; 83 in the core).

## Colour / material

One 16-entry sun-faded Taipei sheet palette (`xc_sheet16` in `tools/lookdev/shaders/xinyi_city.hlsl`,
names in the builder) shared by the instanced rooms **and** the painted sheet roofs / walls of the
surveyed rooftop records, old roofs and the far city, so near geometry and far paint agree.

* weights in the builder: blue-greys / faded blue, galvanised and off-white dominate, then oxidised
  red, faded / teal green; core roofs skew neutral. Per building one dominant colour; 32 % of rooms
  are re-roofed in another colour (patchwork); walls usually light / neutral or the roof colour.
* per instance: roof colour × 16 + wall colour in the existing custom-data float (256 variants).
* weathering: UV fade on up-facing sheets, rust bloom, soot streaks on walls, ~10 % mismatched patch
  strips; matte (roughness 0.62), low metalness (galvanised a bit higher).
* painted whole-roof sheets move half of the warm picks to blue / galvanised (whole red roofs are rarer
  than red rooms; avoids a red carpet in the far city).
* iteration: the first palette was too muted / too weathered (roofs went grey-brown, weaker than
  before); the second too warm (oxidised red read orange in sun); the final one sits between.

## Before / after (DAY)

* oblique passes over old fabric (`roof_ne1`, `roof_ne2`): strongest gain — dense, believable 3D
  rooftop patchwork, long rusty rooms over row-house strips, tanks on bulkheads, towers clean.
* medium altitude (`roof_mid`) / overview: finer, more varied rooftop colour across old districts; core
  and towers unchanged; far city gets a generalized mixed roof palette.
* low urban pass / Wuxing rooftops: more rooftop massing; the effect is modest at street level.
* Elephant Mountain (looks across the core): little change, by design (clean towers).

Accepted 8-shot suite: changes are confined to roofs, rooftop props and the painted walls of surveyed
rooftop records (0–9 % of pixels; sky, mountains, Taipei 101, landmark roofs and ordinary facades
unchanged). DUSK / NIGHT sanity: rooms take the dusk light; a few rooms show faint lit windows at night.

## Cost (UHD 770, 1080p, flight harness, ms per frame)

| | roof_sw | roof_ne1 | roof_ne2 | roof_mid | overview | Elephant | Wuxing |
|---|---|---|---|---|---|---|---|
| before (pre-pass build) | 66.1 | 75.9 | 66.3 | 78.4 | 76.9 | 58.2 | 66.3 |
| after (v5) | 66.4 | 77.0 | 66.4 | 79.2 | 76.3 | 58.0 | 66.2 |
| after, all rooftop props hidden | 65.1 | 74.3 | 64.7 | 76.7 | 76.1 | 56.5 | 65.0 |

"Before" is a different session (indicative): −0.6 … +1.1 ms. Same-session probes: hiding only the new
room types changes ≤ 0.4 ms; the whole rooftop layer is +0.2 … +2.7 ms, mostly small clutter (tanks,
AC, antennas). An early version that ran the sheet palette / weathering for every wall and roof pixel
cost +2 … +3.5 ms; it is now behind coherent per-building branches. Instances 29,030 → 31,150,
instance triangles 0.76 M → 0.81 M (HISM per type; rooms / bulkheads visible to 4.5 / 4 km, small
clutter culled at 0.6–2 km). Tank clusters were trimmed back to ~9 k (from 12.9 k in an earlier version).

Side effect: residential towers now get a stair / machine bulkhead instead of the generic machine room
and cooling only on large roofs (cooling 1,157 → 525, machine 1,286 → 911).

## Remaining weaknesses

* at street level / Elephant Mountain the gain is small; rooftops are mostly seen from oblique views.
* the detailed source covers ~2.2 × 2 km; the far city only gets painted, generalized roof colour.
* rooms are rectilinear boxes; no railings, laundry, rooftop gardens or irregular lean-to clusters yet.
* walk-up records split into many tiny footprint parts get no rooms (below the 2.6 m minimum).
* corrugation / patch strips follow world axes, not each roof's orientation.

## Files

Tracked: `tools/lookdev/build_rooftops.py`, `tools/lookdev/shaders/xinyi_city.hlsl`,
`adapters/unreal/lookdev/xinyi_look_build_level.py` (variant range, per-type cull distances), this
report. Generated (untracked): `unreal/Saved/XinyiLook/rooftops/*` (13 prop meshes, instances, report),
`/Game/XinyiLook/Meshes/Roof/{addition,barrel,leanto,bulkhead}` + rebuilt materials / level.
Evidence: `unreal/Saved/XinyiLook/evidence/rooftop_identity_v0/` (sheets, frames, suite before/after,
timing, harness).
