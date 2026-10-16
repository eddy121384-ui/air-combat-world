# 相思樹 Acacia confusa — research + Blender golden reference v1

Branch `lookdev/taiwan-acacia-confusa-v1` (from `lookdev/taiwan-hillside-forest-v1` @ `b1da16d`). Second Taiwan lowland species after 紅楠
(Machilus thunbergii, PR #30–#33). Same tools: `tools/treegen/tg_tree.py` (space colonisation + tube meshing), `tg_scene.py` (the shared
golden stage), the geometry-nodes spray instancer of `machilus_thunbergii.py`; new: `acacia_confusa.py` (species parameters + explicit
limb architecture), `tg_phyllode.py` (phyllode sprays), `tg_materials.phyllode()` / `fissured_bark()`. The 紅楠 generator and its outputs
are untouched (the golden `.blend` sha256 is re-checked in the PR report).

## 1. What a 相思樹 looks like (Phase A)

Sources (linked, **not committed** — photo licences not reviewed for redistribution; looked at, not copied):

| source | used for |
|---|---|
| PROSEA / Pl@ntUse, *Acacia confusa* — https://uses.plantnet-project.org/en/Acacia_confusa_(PROSEA) | phyllodes 6.5–10 cm × 5–9 mm, straight to slightly falcate, hooked apex, leathery, ≥ 5 parallel veins; tree to ~10 (–15) m |
| HKBU campus tree list — https://eo.hkbu.edu.hk/eo-services/services-facilities/Landscape-Maintenance/List-of-Trees-on-Campus/Acacia-confusa.html | 6–15 m evergreen; grey-brown trunk bark; phyllode = flattened petiole, true leaf only on seedlings |
| CUHK Shiu-Ying Hu Herbarium factsheet — https://syhuherbarium.sls.cuhk.edu.hk/collections/factsheet-pro/acacia-confusa/ | 6–20 m; golden globular flower heads (Apr–Jun) |
| HAST (Academia Sinica) specimens — https://hast.biodiv.tw/en/specimens/HAST:135678 | Taiwan records |
| Wikimedia Commons, Category:Acacia confusa — https://commons.wikimedia.org/wiki/Category:Acacia_confusa | form reference photos: `相思林.JPG` (stand: leaning, sinuous, multi-stemmed trunks, wispy clumped foliage, light passing through), `Taiwan acacia on Dadu Plateau 20100531.jpg` (open-grown: low fork into 2–3 pale grey limbs, broad irregular crown of separate fluffy clouds, yellow-olive), HK Kwun Tong "leaves crown 01" (narrow falcate phyllodes along slender arching twigs) and "tree trunk", Starr / Maui "habit" series (hillside stands from above) |
| 中興大學文山林場植群調查 (via MOA / 林業試驗所 notes, search summary) | 相思樹型 is one of the plant communities of northern low hills; without disturbance mid-slope → ridge forest succeeds to 紅楠 dominance and ravines to 水同木 / 江某 — i.e. acacia stands are a seral, plantation-derived stage |
| 林業試驗所 / 新聞 (相思樹 造林, 相思炭, 坑木) | planted island-wide in the Japanese era and after the war for charcoal, fuelwood and coal-mine props (the Taipei hills, incl. the Nangang–Xinyi coal belt next to 象山); common on slopes and degraded / dry sites |

Flight-distance identity, in order of how far it carries:

1. **Colour** — a lighter, yellower olive green than the glossy near-black-green 紅楠 dome; slightly greyish in the shade.
2. **Texture** — fine-grained, feathery, "wispy"; light passes through the crown; no big glossy leaf facets.
3. **Crown architecture** — a few separate, flattened foliage clouds at the ends of long limbs, with sky / dark branches between them;
   irregular, often lopsided outline; not a continuous dome.
4. **Trunk** — short, leaning, forking low (≈ 1.5–2.5 m) into 2–4 long, SINUOUS (zig-zag) limbs; grey-brown bark with shallow
   longitudinal fissures (pale grey on old open-grown trees, darker in stands).
5. **Leaf** — no broad leaves: alternate narrow falcate phyllodes (≈ 8 × 0.7 cm), parallel-veined, both faces alike.

Pitfalls named in the brief and how they were avoided: **pine** (no needle tufts, no conical leader — broad clouds on a low fork);
**savanna umbrella acacia** (no flat plate on a long bare stem: iteration it3/it4 drifted toward that and were corrected with deeper,
lower side clouds); **another green ball** (it2 was exactly that and was rejected — see §3).

Distribution in the scene (used in Phase D): ridges, upper and sunny S–SW slopes (leeward of the NE winter monsoon), old plantation patches,
disturbed ground; not in ravines.

## 2. Golden reference v1 (Phase B)

Native 1920×1080, Cycles 128 spp, same stage / sun / sky / exposure as the 紅楠 golden (`tg_scene.py`). Grey cylinder = 1.7 m.

| view | file |
|---|---|
| front (eye level) | `docs/evidence/treegen/acacia/v1_front.jpg` |
| oblique (32° down, 50 mm) | `docs/evidence/treegen/acacia/v1_oblique.jpg` |
| top (orthographic) | `docs/evidence/treegen/acacia/v1_top.jpg` |
| close-up (phyllodes / limbs) | `docs/evidence/treegen/acacia/v1_close.jpg` |
| 6-azimuth turntable | `docs/evidence/treegen/acacia/v1_turntable.jpg` |
| **side by side with 紅楠 v1** (front / oblique / top / ~180 m flight view) | `docs/evidence/treegen/acacia/pair_*.jpg` |
| iteration history it1 … it8 | `docs/evidence/treegen/acacia/acacia_iterations_sheet.jpg` |

| measure (v1, seed 20261016) | 相思樹 v1 | 紅楠 v1 (for contrast) |
|---|---:|---:|
| height / crown spread | 13.2 m / 13.8 m | 14.1 m / 15.7 m |
| trunk | r 0.27 m, fork 1.8 m, leaning, 3 sinuous limbs + 1 sub-fork each | r 0.30 m, buttressed, fork 2.7 m, 5 limbs |
| crown envelope | 15 flattened clouds (zf 0.55) + 1 cap cloud, **no core lobe**, flat-shouldered dome (q 3.0) | 22 lobes + core, egg dome |
| skeleton | 10,403 nodes, 2,506 tips | 19,799 nodes, 4,578 tips |
| foliage | 8,461 sprays → **619,596 phyllodes** | 15,456 sprays → 591,826 leaves |
| spray prototypes | 8, 388–1,780 tris (27–131 phyllodes each) | 8, 398–1,832 tris |
| instanced triangles | 8.8 M | 20.2 M |

### What the geometry encodes

| fact | implementation |
|---|---|
| low fork, sinuous limbs | explicit trunk polyline to 1.8 m with lean; 3 limbs fanned around the lean, each a zig-zag polyline (`_sinuous`, periodic wobble + noise) with one secondary fork; space-colonisation jitter 0.16 (紅楠 0.08) |
| separate foliage clouds | 15 small flattened lobes on a broad shell, no core lobe, attractors concentrated in the lobe skins (surface bias 0.4), interior sprays kept at 20 % (紅楠 45 %); one cap cloud (dart-thrown lobes left a ring-shaped hole at the apex, it6) |
| feathery, light-transmitting texture | sprays = arching, sagging twigs 0.26–0.60 m with 0–3 side twigs, alternate (2/5 spiral) phyllodes every 0.8–1.2 cm, spread 30–60° from the twig, blades leaning toward vertical with a wide random tilt |
| narrow falcate phyllode | 6.5–10 cm × 5.5–8.5 mm blade, widest below the middle, midline bowed sideways 6–14 % of its length, hooked apex (`tg_phyllode.add_phyllode`, ~10 tris) |
| colour | `tg_materials.phyllode()`: isobilateral (back only slightly paler), satin roughness 0.52, lighter / yellower base than 紅楠, 3 faint parallel veins, pale-lime young tips, 38 % translucency |
| bark | `tg_materials.fissured_bark()`: grey-brown with pale patches, distorted saw-wave longitudinal fissures + bump; thin shoots red-brown |

## 3. Iterations (all judged on the Cycles frames, 960×540 / 24 spp)

| round | what the render showed | change |
|---|---|---|
| it1 | a sparse "winter" tree; flat umbrella crown on a bare fork — the savanna look | more attractors / finer SC, 3× sprays, lower fork, thicker trunk, deeper crown |
| it2 | right texture and limbs, but the crown closed into a smooth green **ball**; too dark / blue | fewer, smaller clouds, larger lobe spread, looser asymmetric envelope, interior sprays 22 → 12 %, yellower phyllode colour |
| it3 | clumpy, irregular — the species read; but one tall single trunk, a stray low spray, plate-flat | lower limb elevation, no foliage below the crown base, deeper shell |
| it4 | low fork into sinuous limbs, separate clouds — first convincing 相思樹 | a little more density (Dadu reference is fuller) |
| it5 | close-up: narrow falcate phyllodes on arching twigs (matches the HK photo); top: lobed see-through outline | front still slightly umbrella-like |
| it6 | lower side clouds → deeper, irregular crown; oblique showed a ring with a hole at the apex | + one cap cloud |
| it7 | final form | — |
| it8 | first game export showed the top-view atlas tiles at 3–5 % coverage (vertical phyllodes edge-on from above → bare sticks after LOD enlargement) | phyllode tilt widened (N(0, 0.45) → U(±1.05) rad), spray twigs thinner; golden look unchanged, a little fuller from above → **v1** |

## 4. Known defects / open art issues

1. Branch joints are overlapping tubes (same as 紅楠) — hidden by foliage beyond ~10 m.
2. Bark is procedural (fissure bands); no photographed bark, no lichen plates.
3. No flowers or pods: v1 is the non-flowering aspect (Jul–Mar). The Apr–Jun golden-yellow flowering canopy — the most striking aerial
   signature of 相思樹 on Taipei hills — would be a seasonal leaf-tint variant (not done).
4. One seed / one tree art-directed; the forest varies it only by scale, anisotropy, yaw, lean and tint.
5. Phyllodes are geometry with procedural veins; at 2–3 m they read slightly clean / uniform (no damage, no colour noise beyond the tint).
6. The crown is open-grown. Stand-grown 相思樹 have higher crown bases and longer bare stems (photo `相思林.JPG`); in the forest the
   instance height factor (×1.05–1.30) stands in for that.

## 5. Reproduce

```powershell
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
& $b -b --factory-startup -noaudio --python tools/treegen/acacia_confusa.py -- out/treegen/acacia/v1 --no-render --tag v1
& $b -b out/treegen/acacia/v1/v1_acacia_confusa.blend -noaudio --python tools/treegen/tg_render_saved.py -- out/treegen/acacia/v1 v1 128 1920x1080
& $b -b out/treegen/acacia/v1/v1_acacia_confusa.blend -noaudio --python tools/treegen/tg_turntable.py -- out/treegen/acacia/v1/tt 6 35 24 960x540
& $b -b out/treegen/acacia/v1/v1_acacia_confusa.blend -noaudio --python tools/treegen/acacia_compare.py -- docs/evidence/treegen/machilus/machilus_thunbergii_v1.blend out/treegen/acacia/cmp_v1 --res 1920x1080 --samples 64
./tools/treegen/run_acacia_iter.ps1 -Tag it9          # preview iteration (960x540, 24 spp)
```
(Use absolute output paths: Blender resolves relative render paths against the saved `.blend`.)
