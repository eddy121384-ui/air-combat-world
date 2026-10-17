# 柳杉 Cryptomeria japonica — Golden Reference v1 (third species, first conifer)

Branch `lookdev/taiwan-cryptomeria-japonica-v1` from `lookdev/taiwan-acacia-confusa-v1` @ `5f30274` (PR #36). Scope of this round:
**one representative mature 柳杉 mother tree in Blender** (golden reference). No Unreal game version, no forest integration, no new
vegetation system (see §6). 紅楠 / 相思樹 goldens and all existing assets are untouched.

## 1. Why this tree (art direction, short)

* The project has two broadleaves (紅楠 dark glossy domes, 相思樹 light feathery clouds) and **no conifer silhouette**. 柳杉 adds the one
  thing neither can: a tall, straight, narrow, dark cone standing above the broadleaf canopy — readable from the air at any distance.
* It is real for the map: Yangmingshan's 頂山–石梯嶺 trail (陽明山東西大縱走, 風櫃嘴 → 頂山 → 石梯嶺 → 擎天崗) passes dense, dark
  柳杉 stands that hikers call the "童話黑森林" / "小溪頭"; they are **not native** — a Japanese-era afforestation legacy, described as
  Christmas-tree-like in outline. That makes 柳杉 a *local, patchy plantation* element (blocks of uniform conifers in a broadleaf / grass
  landscape), not a forest-wide species — exactly the kind of contrast a flight game can use as a landmark.
  Sources (media / hiking reports, linked only): https://smiletaiwan.cw.com.tw/article/3889 ,
  https://today.line.me/tw/v2/article/9mrqGqe , https://travel.yam.com/article/133347 . Botanical traits below are standard
  descriptions of the species (Cupressaceae; not re-cited here, deliberately no long literature review this round).

## 2. Species traits → geometry

| trait (flight-distance first) | implementation |
|---|---|
| tall, straight single trunk; plantation tree self-prunes its lower bole | 24 m leader (slight sway), clear bole to 9.5 m with 7 dead stubs; r 0.36 m at the base, mild fluted swell |
| **narrow conical crown**, tapering to an acute but slightly irregular top | primaries from 9.5 m to the top, reach 3.3 m × (1 − rel)^0.9 × U(0.75, 1.12): crown width 7.3 m = 0.30 × height |
| branches near-horizontal low, ascending high; tips turn up; loose spiral, **no regular whorls** | 55 primaries every 0.18–0.32 m at a 137.5° ± noise spiral; elevation −12…+2° (low) → 30…50° (top); 14° mid-branch sag (fading with height) + 30° tip upturn |
| foliage = clumped **rope-like cords**, not flat fir sprays, not long pine needles | `tg_needle.py`: awl needles 10–18 mm, spread 40–65° and curved forward, spiral all round each shoot → thick bristly cords; 8 "pad" prototypes = axis + 9–16 side cords + 2–3 upturned second-order tufts each |
| foliage clumps at the branch ends, crown dark and dense | 602 secondaries (alternate, 45–70°, tips up), sprays every 4.5 cm along them + tip tufts + outer half of every primary + a 1.4 m terminal leader column → 4,492 pads |
| dark blue-green, a little bronze / lighter on exposed upper tips | `tg_materials.phyllode()` with conifer parameters (no veins, matte 0.6, low translucency); per-spray tone lighter up high, darker low |
| reddish-brown, stringy bark in long vertical strips | `tg_materials.fissured_bark()` with a 柳杉 palette (longitudinal fissure bands) |

What keeps it from being a **Christmas tree / fir**: no regular whorled tiers, no flat horizontal needle plates, an irregular spiral
with drooping-then-upturned branches and tufted cords; from a **pine**: short awl needles in cords (no long needle bundles), a narrow
pointed crown (no flat / open mature crown); from **cartoon**: no clean cone envelope — the outline comes from the branches.

## 3. Golden v1 (native 1920 × 1080, Cycles 64 spp, same stage / sun / sky / exposure as the 紅楠 and 相思樹 goldens)

| view | file (`docs/evidence/treegen/cryptomeria/`) |
|---|---|
| front, oblique, top, close-up (cord foliage on a branch) | `v1_front.jpg`, `v1_oblique.jpg`, `v1_top.jpg`, `v1_close.jpg` |
| 6-azimuth turntable | `v1_turntable.jpg` |
| **3-species lineup** 紅楠 \| 柳杉 \| 相思樹: front / oblique / top / ~200 m flight view | `lineup_front.jpg`, `lineup_oblique.jpg`, `lineup_top.jpg`, `lineup_flight.jpg` |
| iterations it1–it5 | `cryptomeria_iterations_sheet.jpg` |
| editable project | `cryptomeria_japonica_v1.blend` (procedural materials + GN instancer live; regenerable from the seed) |

| measure (v1, seed 20261017) | 柳杉 v1 | 紅楠 v1 | 相思樹 v1 |
|---|---:|---:|---:|
| height / crown spread | **24.3 m / 7.3 m** | 14.1 / 15.7 m | 13.2 / 13.8 m |
| crown width / height | **0.30** | 1.11 | 1.05 |
| skeleton | 2,035 nodes (explicit: leader + 55 primaries + 602 secondaries + stubs) | 19,799 (space colonisation) | 10,403 |
| foliage | 4,492 pads → **7.39 M needles** | 591,826 leaves | 619,596 phyllodes |
| instanced / branch triangles | 8.95 M / 32,304 | 20.2 M / 298,384 | 8.8 M / 165,794 |

## 4. Iterations (960 × 540, 24 spp)

| round | what the render showed | change |
|---|---|---|
| it1 | right skeleton (straight leader, spiral horizontal limbs) but a bare spine: 1,192 tiny single-cord sprays vanish at tree scale | more primaries, sprays every 6 cm, larger |
| it2 | still a see-through sparse fir; cords are 0.3 m wires | sprays rebuilt as branchlet **pads** (axis + side cords + second-order tufts), ×8 needle area each |
| it3 | crown appears; close-up: thin wiry cords, dark twig tubes dominate | needles longer / wider / spread 40–65°, thinner green twig tubes |
| it4 | oblique reads as a dark narrow conifer; front still airy | denser secondary network, sprays every 4.5 cm |
| it5 | tall narrow dark blue-green cone, irregular outline, upturned tips, bristly cords → **v1** | — |

## 5. Known defects (honest list)

1. **Lower crown edge is still a little airy from eye level** (the crown is denser from above than from the side); a mature stand tree
   has a denser outer shell. More pads on the primaries' outer thirds would fix it.
2. **Close-up cords** are believable as bristly ropes but needles are single triangles (no 4-sided awl), no cone / pollen buds.
3. Branch joints are overlapping tubes (as for the other goldens); bark is procedural fissure bands, no peeling strips.
4. One seed, one form: a plantation 柳杉 (high crown base). An open-grown / ridge tree (crown to the ground, broader base) would be a
   second form.
5. Golden colour is dark blue-green at all heights; no winter bronzing variant.
6. The game exporter is not run yet: `build()` already returns the skeleton, crown lobes (spheres stacked along the cone) and
   `P["shell_depth"]` so `machilus_game.py` can be pointed at it with a species switch next round.

## 6. Not done this round (by design — weekly budget ~8 %)

* Unreal game version (cards / LODs / import / fresh-process gate): **recommended as the next round** — the generator is export-ready,
  and the 相思樹 lessons apply directly (tight cards; conifer cords are long thin tiles, so expect clump tiles for LOD2/3).
* Forest integration (頂山–石梯嶺 plantation blocks): after the game version; plantation = regular spacing, even age, sharp edges.

## 7. Reproduce

```powershell
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"; $o = "$PWD\out\treegen\cryptomeria"   # absolute output paths
& $b -b --factory-startup -noaudio --python tools/treegen/cryptomeria_japonica.py -- $o/it9 --res 960x540 --samples 24 --tag it9   # preview
& $b -b --factory-startup -noaudio --python tools/treegen/cryptomeria_japonica.py -- $o/v1 --no-render --tag v1
& $b -b $o/v1/v1_cryptomeria_japonica.blend -noaudio --python tools/treegen/tg_render_saved.py -- $o/v1 v1 64 1920x1080
& $b -b $o/v1/v1_cryptomeria_japonica.blend -noaudio --python tools/treegen/tg_turntable.py -- $o/v1/tt 6 30 16 960x540 12 58
& $b -b $o/v1/v1_cryptomeria_japonica.blend -noaudio --python tools/treegen/species_lineup.py -- $o/lineup 1920x1080 48 `
    "$PWD/docs/evidence/treegen/machilus/machilus_thunbergii_v1.blend:MachilusThunbergii:-16" "$PWD/docs/evidence/treegen/acacia/acacia_confusa_v1.blend:AcaciaConfusa:14"
D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe tools/treegen/make_sheets.py out/treegen/cryptomeria docs/evidence/treegen/cryptomeria cryptomeria
```
New code: `tools/treegen/cryptomeria_japonica.py`, `tg_needle.py`, `species_lineup.py`; `tg_turntable.py` gained optional
`target_z dist` arguments (defaults unchanged).
