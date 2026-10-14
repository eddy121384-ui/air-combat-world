# 紅楠 Machilus thunbergii — Blender golden reference, round 1 (visual review)

Branch `lookdev/forest-assets-v1` (stacked on `spike/ac7-forest-b0-preflight` @ `a1d7238`).
Scope of this round: **one mature 紅楠 in Blender, real Cycles renders, at least two real visual iterations.**
No Unreal import, no game LOD, no forest, no other species yet (those are phases 2 and 3 and wait for the visual review).
Fab / Megascans were dropped by the owner; nothing in this round needs an account or a download of third-party art.

## 1. Deliverable (final round = `v1`, native 1920x1080, Cycles 128 spp, denoised)

| view | file |
|---|---|
| front (eye level 5 m, 35 mm) | `docs/evidence/treegen/machilus/v1_front.jpg` |
| oblique (32 deg down, 50 mm) | `docs/evidence/treegen/machilus/v1_oblique.jpg` |
| top (orthographic) | `docs/evidence/treegen/machilus/v1_top.jpg` |
| close-up (shoot tips, 50 mm, ~2.8 m) | `docs/evidence/treegen/machilus/v1_close.jpg` |
| 6-azimuth turntable at 35 deg (silhouette check) | `docs/evidence/treegen/machilus/v1_turntable.jpg` |
| iteration history it1 ... it9 (front / oblique / top) | `docs/evidence/treegen/machilus/machilus_iterations_sheet.jpg` |

The grey cylinder is a 1.7 m scale figure. Same stage, sun, sky and exposure for every round (`tools/treegen/tg_scene.py`).

| measure (v1, seed 20261014) | value |
|---|---|
| height / crown spread | 14.1 m / 15.7 m (trunk base r 0.30 m before flare, fork at 2.7 m) |
| skeleton | 19,799 nodes, 4,578 tips, space colonisation 47 iterations, 52,000 attractors, 22 lobes + core |
| branch mesh (unique) | **298,384 triangles**, 1 material (procedural bark, young-twig blend by radius) |
| spray prototypes (unique) | 8 meshes, 398-1,832 tris each, **10,322 triangles total**; materials leaf / twig / bud |
| instances | 15,456 sprays -> **591,826 leaves**, **19.9 M instanced triangles** (20.2 M rendered in total) |
| unique geometry | ~309k triangles; `.blend` 7.0 MB (`docs/evidence/treegen/machilus/machilus_thunbergii_v1.blend`) |
| build / render | skeleton 17 s; Cycles CPU (i7-12700) 1920x1080 112 spp: 4-18 min per view on this host |

This is a **golden reference**, not a game asset: 20 M instanced triangles is offline-render scale. Game LODs / cards / impostors are phase 2.

## 2. What the tree is based on (species form, not a generic broadleaf)

Botanical facts used (sources at the end; photos are **linked, not committed** — licences not reviewed for redistribution):

- Large evergreen tree, Lauraceae; commonly 10-15 m, up to ~20 m. Open-grown trees have a short stout trunk that forks low into several
  ascending limbs and a broad, dense dome made of distinct billowy foliage masses (Hiroshima Castle tree photo).
- Bark grey-brown, relatively smooth, conspicuous lenticels; old trunks buttressed and mottled (Tabunoki trunk photo).
- Leaves simple, alternate but **crowded at the shoot tips** (pseudo-whorl around a large terminal bud with red imbricate scales),
  leathery, glossy dark green above, paler beneath; obovate to obovate-elliptic, ~4.5-13 cm; lateral veins 7-12 pairs.
- New flush and bud scales bright red — the origin of the name 紅楠 (and of 豬腳楠). Here: red buds on every rosette, red-bronze
  young flush on ~2 of 8 spray types (kept sparse so the aerial read stays dark green).

How each fact became geometry:

| fact | implementation |
|---|---|
| low fork, 3-5 ascending scaffold limbs | explicit trunk polyline to 2.7 m, 5 limbs staggered over the top 0.8 m, 36-60 deg elevation, S-curve + wander, plus a leader |
| billowy dome of foliage masses | crown envelope = 22 lobes on a dome + a core lobe, soft-clipped by an egg-shaped dome (wide low, tapering top) |
| branches fill the masses | space colonisation (Runions et al. 2007) toward 52k attractors concentrated in the outer ~0.5 m of the lobes |
| thick wood, thin twigs | pipe model (exp 2.35) remapped geometrically so trunk base r = 0.30 m and tips r = 6 mm; buttress flare on the trunk |
| leaves crowded at shoot tips | 8 instanced "spray" prototypes: short stout shoots, 10-15-leaf terminal rosettes, 8-12-leaf side rosettes, a few older leaves along the shoot, red bud |
| dense sun-leaf shell | tips within 1.1 m of a lobe surface get 2 terminal + up to 3 lateral sprays; interior tips are thinned (45 %) |
| glossy dark upper / pale under | UV-driven leaf shader: midrib, faint chevron veins, per-leaf and per-spray tint, backface = paler rougher underside, 34 % translucency |

## 3. Tool evaluation (existing tools first)

| tool | licence / version | Blender 5.2.1 | verdict |
|---|---|---|---|
| **Modular Tree (MTree)** 5.5.2, extensions.blender.org | GPL-3.0-or-later | branch generation works (cp313 wheel). **Leaf step fails on 5.2**: it sets geometry-nodes modifier inputs with `modifier[id] = v`, which 5.2 rejects ("id properties not supported"); works with an in-memory patch to `modifier.properties.inputs.<id>.value` (`tools/treegen/mtree_eval.py`, addon files untouched) | excellent manifold branch mesher with welded joints; but crown envelope / foliage-mass control is generic (trunk+branch+split parameters) and leaves are scattered evenly along branches, not crowded at tips. Its OAK preset render (`docs/evidence/treegen/mtree_oak_eval_front.png`, leaves untextured) reads as a generic leaning oak. Not adopted for this species. |
| Sapling Tree Gen 0.3.7 | GPL | listed for 4.4+, users report failures on 5.0.1/5.1 | not rendered; parametric Weber-Penn branching + flat leaf quads, no tip rosettes; lower ceiling than MTree |
| Space colonisation / Easy Tree / others on the extension platform | various | not tested | same family as the method used here |

Decision: **a small custom Blender-Python generator** (`tools/treegen/`, ~900 lines, numpy + mathutils, no new framework) because the species identity lives in two
things the existing tools cannot express: the lobed foliage-mass crown and leaves crowded in tip rosettes. MTree remains the best candidate if we later want
welded branch joints (its mesher cannot take an external skeleton through the Python API today).

## 4. Visual iterations (all judged on the actual Cycles frames)

| round | what the render showed | change |
|---|---|---|
| it1 | winter sapling: 34k leaves, trunk r 0.11 m, SC stopped after 38 iterations (728 tips) | more attractors / finer SC; pipe radii remapped to a 0.30 m trunk; second lateral spray |
| it2 | full crown, but an umbrella-pine/acacia silhouette (bare trunk to ~5 m, flat-bottomed crown); uniform fuzz; white specular "dust"; grey-blue | lower and broader lobes; attractors concentrated in lobe shells; spreading limbs; less coat, more saturated |
| it3 | better dome, but see-through from the side | (analysis) sprays held every leaf facing the sky -> edge-on from the side |
| it4 | still ~50 % sky through the crown | rosette blades now face along the shoot axis (star whorl), outward shoots present faces to side viewers |
| it5 | first dense evergreen read; natural green | sun-leaf shell weighting (more sprays near lobe surfaces), finer skeleton, lower leaf specular, more yellow-green transmission |
| it6 | lobes protrude, close-up credible; but a hole at front-centre, candelabra fork, narrow leaves, bare twig sticks | — |
| it7 | real mature-tree read; tip rosettes and red buds visible | core lobe (gaps become crevices), staggered limbs, broader obovate leaves, short stout shoots, fuller rosettes, larger buds |
| it8 | best front so far; oblique/top looked boxy / exaggerated clover; leaf albedo too dark | more, smaller, less protruding lobes; twig colour by radius; brighter sun-leaf variation |
| it9 | dome envelope; 6-azimuth turntable mostly round, but the oblique azimuth still boxy | oblique camera moved to 50 mm / farther (lens was only part of it) |
| it10 | 50 mm oblique still boxy: the crown really was a cylinder (as wide at 4 m as at 10 m) | dome re-centred low with a tall tapering top (rz_up 9.2 / rz_dn 3.1) |
| it11 | turntable fine, but the 1080p oblique was still a hexagon outline = a vertical cylinder seen from above | low-frequency azimuthal asymmetry of the dome (+-10 % radius, +-10 % height) |
| it12 | paraboloid upper taper (q 1.35) did not remove the straight wall at the 40 deg azimuth -> not the envelope | (analysis) lobe centres came from a golden-angle spiral with ordered elevations; lobes 8 / 13 apart share an azimuth and stack into vertical columns |
| it13 | blue-noise lobe directions: oblique reads as round billowy masses, front shows two upper masses like the Hiroshima tree | final `v1` |

## 5. Known defects / open art issues (honest list for the review)

1. **Branch joints are overlapping tubes**, not welded. Invisible at aerial range and mostly hidden by foliage, but a close look at the
   fork shows interpenetration. (MTree's manifold mesher is the fix if a hero close-up is ever needed.)
2. **Bark is procedural** (UV noise mottling, lenticel dots, bump). It reads as smooth grey-brown at mid range but has none of the
   buttress plating / lichen detail of a photographed trunk; a scanned or hand-painted bark texture would be the next step.
3. **Crown colour is fairly uniform under front light.** The sunlit shell lacks the strong yellow-green / dark-gap contrast of the
   reference photos at some angles (oblique / top look a little flat). Partly the neutral stage (single sun, AgX, flat ground).
4. **Inner crown is sparse and dark** by design (45 % of interior tips keep foliage); through-gaps toward the trunk are fewer than in
   the Hiroshima photo, i.e. the crown may be slightly too opaque / "full" for an old open-grown tree.
5. **Leaves are geometry with procedural veins**, no photo albedo. Close-up leaves are believable in shape (obovate, glossy, crowded
   whorls) but lack real colour noise, leaf-edge yellowing and damage.
6. **Red terminal buds on every rosette** make the close-up dotted with red; botanically plausible (large red-scaled buds) but may read
   too regular. Young red flush is only on 2 of 8 spray types — invisible at aerial range.
7. **8 spray prototypes** repeated 15k times; random roll/scale/tint hides it at every distance tested, but it is the main repetition risk.
8. **Lower crown skirt** comes low (~2.5 m) on most sides; from 32 deg above it hides the trunk. Correct for an open-grown tree,
   wrong for a forest-interior tree (phase 3 will need a forest-grown variant with a higher crown base).
9. Only one seed / one tree was art-directed. A second seed may expose new failure modes (the lobe-column bug was seed-independent
   and is fixed, but crown asymmetry parameters are hand-set).
10. **Close-up: some sky-facing leaves flash almost white** (broad sky reflection on the glossy coat + pale underside seen through
    translucency) and read slightly plastic/paper-like at 2-3 m. Needs a view-dependent gloss falloff or a real albedo map.
11. Turntable az300 (back-lit side) still shows a squarish outline with a flat underside; the other five azimuths read as billowy masses.
12. Not validated in Unreal yet; Cycles translucency / gloss will not transfer one-to-one to a game shader.

## 6. Reproduce

```powershell
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
& $b -b --factory-startup -noaudio --python tools/treegen/machilus_thunbergii.py -- out/treegen/machilus/v1 --res 1920x1080 --samples 128 --tag v1
& $b -b out/treegen/machilus/v1/v1_machilus_thunbergii.blend -noaudio --python tools/treegen/tg_turntable.py -- out/treegen/machilus/v1/tt 6 35 24 960x540
D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe tools/treegen/make_sheets.py out/treegen/machilus docs/evidence/treegen/machilus
```

The editable Blender project is the generated `.blend`, committed as `docs/evidence/treegen/machilus/machilus_thunbergii_v1.blend`
(7 MB: procedural materials and the geometry-nodes spray instancer stay live; branch mesh and spray prototypes are plain meshes;
no external textures). It is also regenerable from the fixed seed with the command above.

## Sources

- HAST herbarium (Academia Sinica), Machilus thunbergii specimen records: https://hast.biodiv.tw/en/specimens/HAST:112884
- TAI herbarium (NTU) species page: https://tai2.ntu.edu.tw/species/333%20010%2005%200
- CUHK Shiu-Ying Hu Herbarium factsheet (leaf dimensions): https://syhuherbarium.sls.cuhk.edu.hk/collections/factsheet-pro/machilus-thunbergii/
- Wikimedia Commons category (whole-tree, bark, leaf photos; viewed, not copied): https://commons.wikimedia.org/wiki/Category:Machilus_thunbergii
  - whole tree: "Machilus thunbergii in Hiroshima Castle.jpg"; shoot tip / red bud: "Persea thunbergii in Christchurch Botanic Gardens 01.jpg";
    trunk: "Tabunoki (Machilus thunbergii).jpg"; Taiwan foliage: "紅楠.jpg"
- Modular Tree extension: https://extensions.blender.org/add-ons/modular-tree/ (source https://github.com/GoodPie/modular_tree)
- Sapling Tree Gen reviews / versions: https://extensions.blender.org/add-ons/sapling-tree-gen/versions/
- Runions, Lane, Prusinkiewicz, "Modeling Trees with a Space Colonization Algorithm", Eurographics NPH 2007.
