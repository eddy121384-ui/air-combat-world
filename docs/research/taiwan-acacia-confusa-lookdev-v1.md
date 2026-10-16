# Taiwan hillside forest — 相思樹 Acacia confusa lookdev v1 (second species), UE 5.8

Branch `lookdev/taiwan-acacia-confusa-v1` from `lookdev/taiwan-hillside-forest-v1` @ `b1da16d` (PR #33 head; review 5545794683 accepted
紅楠 A chain T = 34,272 / 8,578 / 1,400 / 534). Same 象山 250 m × 250 m block, same 989-tree canopy footprint, cameras, sun, flight, MRQ and
perf harness as PR #33. Nothing of PR #30 / #31 / #33 is overwritten: the 紅楠 golden (sha256 `510F8D10…`, re-checked), Mix D / C / T maps
and assets, the 紅楠 materials are only referenced; every new asset / map is new content (`/Game/HillsideForest/Trees/Acacia*`,
`/Game/TreeLookdev/{Textures,Materials}/*Acacia*`, revisions `a1`–`a8`).

> Draft for review. Host: **Intel UHD 770 iGPU, UE 5.8, standalone `-game` 1080p native MRQ**. GPU numbers exploratory (2 interleaved rounds).
> Species research and the Blender golden reference: [`docs/treegen/acacia-confusa.md`](../treegen/acacia-confusa.md).

## 0. Answer

**B (Mix T + 25 % 相思樹 stands) is the more natural, more northern-Taiwan forest; adopt the `acacia_tight` chain as the 相思樹 candidate.**

1. **Does a second species improve naturalness? Yes, clearly.** A was one evergreen-broadleaf texture everywhere (two 紅楠 crown forms
   differ in shape and tint, not in kind). B adds a second canopy *texture* — light, fine-grained, feathery yellow-olive clouds over sinuous
   grey limbs — in coherent stands on the two sunny spurs and the ridge, with 紅楠 holding the ravine and the north faces. The forest now
   has a readable ecological structure instead of a uniform pile of domes.
2. **Species blocks / canopy texture at 200–500 m? Yes, with the clump chain.** At 200 m the stands read as lighter, fluffier cloud
   masses next to the dark 紅楠 domes; at 500 m as yellow-olive, finer-grained patches inside a continuous canopy. The first two 相思樹
   chains failed exactly here (speckle over bare ground at 500 m, §3) — the fix is the clump atlas, not more triangles.
3. **Closer to the real northern-Taiwan lowland forest? Yes.** Old 相思樹 plantations (fuelwood, charcoal, mine props) on ridges and
   sunny upper slopes, being replaced by native broadleaves (紅楠) from the moist hollows, is the textbook picture of the Taipei hills; B
   places 66 % of its acacias on ridges (others 23 %), 73 % on sunny S–SW faces (others 33 %) and none in valleys (others 25 %).
4. **Repetition / colour breaks / LOD pops?** No pop spikes (frame and 8 × 6-tile proxies: 0); the stand edges are ragged; three tints
   per species. Two honest caveats: (a) at the LOD1 → LOD2 switch (≈ 135 m for an average acacia) the crown gets *denser* (single-spray
   cards → clump cards) — no pop was measured, but in the 200 m still the nearer acacias are visibly airier than the far ones;
   (b) one golden tree for all 248 acacias — at 50 m the sinuous-limb silhouette repeats if you look for it.
5. **Cost:** B costs more than A: **+22.6 ms at 50 m (+19 %), +12.2 ms at 200 m (+17 %), +1.0 ms at 500 m (+6 %), +21.6 ms flyover median (+27 %)** of forest GPU over Mix T with the adopted `acacia_tight` chain (the untightened clump chain cost +35.9 / +24.0 / +1.6 / +32.0 ms). Shadow depths and masked base-pass fill of the 25 % acacias are the cost; a cheaper LOD1 is the next lever (§7).

## 1. Pipeline (what was reused, what is new)

| step | reused | new for 相思樹 |
|---|---|---|
| golden | `tg_tree` space colonisation + tube mesher, `tg_scene` stage, GN spray instancer | `acacia_confusa.py`, `tg_phyllode.py`, `tg_materials.phyllode()` / `fissured_bark()` |
| game export | `machilus_game.py` cards / branch LODs / crown-blended normals / vertex tint + occlusion | opt-in `ACW_TL_SPECIES=acacia`; profiles `acacia`, `acacia_dense`, `acacia_clump`, `acacia_tight`; **clump tiles** (`bake_clumps`, `build_clump_cards`), **tight cards** (`card_quad`); 2:1 atlas (`machilus_game_textures.py … acacia wide`) |
| UE import | Interchange 4-LOD import, Nanite off, LOD build settings, screens 1 / 0.5 / 0.15 / 0.06 (PR #31 recipe) | `ac_import.py` (own textures + `M_TL_Acacia_Bark`, `M_TL_AcaciaW_LeafCards`, ISM usage flag set + saved at creation), `ac_tune.py` (leaf clip / dither / alpha-coverage experiments) |
| forest | `hf_build.py` / `hf_verify.py` / `hf_mrq_configs.py`, MRQ, frames analysis, perf | opt-in form **C** (own bark + leaf parents, tints 5 / 6 / 7), `ACW_HF_VIEWS`, `ACW_HF_C_MESH`, `ACW_HF_C_LEAF`; `hillside_acacia_mix.py`, `hillside_lineup.py`, `hillside_acacia_ab.py` |

Every 紅楠 default is unchanged (all new behaviour is behind a species / profile / env switch; Mix T `m7` is the PR #33 build).

## 2. Unreal game version — LOD chains tried (all 4 LODs, screens 1 / 0.5 / 0.15 / 0.06)

| chain | LOD0 / 1 / 2 / 3 triangles | cards | card area LOD0 / 1 / 2 / 3 (m², scale 1) | native result |
|---|---|---|---|---|
| `acacia` (first) | 29,696 / 9,984 / 2,949 / 476 | single sprays, ×1.35 / 2.24 / 4.08 / 7.45 enlarged | — | lineup a1: **"confetti"** blobs at 60 m, thin speckle at 200 m — rejected |
| `acacia_dense` | 38,156 / 16,752 / 5,657 / 1,696 | more sprays, ×1.12 / 1.58 / 2.67 / 4.71 | — | lineup a2 finer; forest a5: 50 m good, **500 m = speckle over bare ground** — rejected |
| `acacia_clump` | 38,156 / 16,752 / **1,477 / 452** | LOD0/1 = dense sprays; **LOD2/3 = 140 / 70 clump cards** | 6,066 / 6,115 / 2,447 / 1,427 | lineup a6 / forest a7: continuous canopy at 200–500 m |
| **`acacia_tight`** (candidate) | 38,156 / 16,752 / 1,477 / 452 | as clump, quads cropped to the foliage | **3,731 / 3,763 / 2,061 / 1,202** | forest a8 = a7 pixels (mean diff 0.3–1.3 / 255), cheaper (§6) |

(紅楠 A, chain T, for scale: 34,272 / 8,578 / 1,400 / 534 triangles; LOD1 card area 5,145 m².)

Why each step (native evidence, not taste):

* **Thin phyllodes break card LODs.** A 紅楠 tile is a dense rosette of broad leaves; a 相思樹 tile is a spray of 6–9 mm blades covering
  4–15 % of the tile. Masked + mip-mapped, those blades collapse into a few hard blobs per card at 60 m (a1), and with the area-preserving
  enlargement of distant LODs the crown becomes a speckle (a2 aerial, a5 500 m). More sprays (dense) helped near, not far.
* **Material knobs (lineups a3 / a4):** dithered opacity mask + TAA → soft but **ghostly** crowns (rejected); clip 0.25 + alpha-coverage
  threshold 0.25 → slightly fuller (kept in `M_TL_AcaciaW_LeafCards`). Neither fixes distance.
* **Clump tiles fix distance.** 8 extra tiles, each an orthographic bake of a *real* 2.3–3.7 m chunk of the golden crown (70–119 sprays),
  seen from above and from outside; coverage 14–25 %. LOD2 / LOD3 place 140 / 70 clump cards (≈ 1.7× / 0.85× one full cover of ≈ 83
  clumps), yawed so the baked outward side faces out. Result: continuous, lobed, yellow-olive cloud crowns at 200–500 m, and LOD2 / LOD3
  are *cheaper* than the first chain's.
* **Tight cards.** Square tiles framed on the longest side leave long thin sprays in mostly empty quads; cropping each quad and UV rect
  to the foliage extent removes 38 % of LOD0 / LOD1 card area at identical pixels — and masked card area (prepass, base pass, shadow
  depths) is what costs on this host (PR #33).

Atlas: 4096 × 2048 (`T_AcaciaW_LeafAtlas_BC/_N`, columns 0–3 spray tiles, 4–7 clump tiles), bark 512² tileable with longitudinal fissures.
Preview: `docs/evidence/forest/hillside_v1/acacia_v1/atlas_preview.jpg`.

### Materials — no grey HISM

* `M_TL_Acacia_Bark`, `M_TL_Acacia_LeafCards`, `M_TL_AcaciaW_LeafCards`: **"Used with Instanced Static Meshes" set, compiled and saved
  at creation** (`ac_import.py`), re-asserted in `hf_build.py`.
* `hf_verify.py` (fresh process, reads only what is on disk): flag saved, package clean after load, MASKED + two-sided + foliage shading,
  every HISM's slot 0 / 1 base = **its own species'** bark / leaf parent (a form-C HISM drawing any 紅楠 material — or the engine default —
  fails), no package dirtied by loading every map. Forest a7 **352 / 352**, a8 PASS, lineups 179 / 179.
* Native guard on the standalone `-game` MRQ frames (tree pixels saturated green, not grey): PASS on every forest still. The only FAIL
  is the 3-tree lineup's 200 m frame on the *area* rule (trees 1.93 % of the frame < 2 %); its colour passes (median saturation 0.21).

### UE visual test (species lineup, flat basin floor, same stage)

`lineup_*.jpg`: 紅楠 A (T) | crown B | 相思樹 at eye level (≈ 60 m, LOD1), 32° oblique and ≈ 200 m aerial (LOD2), revisions a1 → a6.
`lineup_lod_chains_aerial.png`: the 200 m 相思樹 crown with the first / dense / clump chains side by side.

## 3. Two-species forest (Phase D)

`tools/forest/hillside_acacia_mix.py` turns Mix T (`instances_mix.json`, PR #33) into `instances_acacia.json`; Mix T is read only, the
tree count stays **989**, every tree keeps its crown centre and radius (a fair A/B: same canopy footprint).

| | 紅楠 A (T) | 紅楠 crown B | **相思樹** |
|---|---:|---:|---:|
| trees | 482 | 259 | **248 (25.1 %)** |
| crown-area share | 50.6 % | 25.4 % | 24.0 % |
| est. height median / p90 | 10.4 / 15.2 m | 7.8 / 12.3 m | 10.3 / 15.3 m |

Site rule (ecology, not a target ratio): score = 0.55 × 30 m old-plantation patch field + 0.35 × ridge (TPI) + 0.20 × sunny S–SW aspect
(× slope) + 0.10 × upper slope + 0.15 × gap edge − 1 in valleys, smoothed over 11 m neighbours; the top 25 % become 相思樹 (111 were 紅楠 A,
137 crown B). The share was not tuned to a number: 25 % is what fills the two sunny spurs and the ridge-top patches the score selects
before it would push into the hollows; the brief's 20–30 % range agrees.

| where the 相思樹 stand | 相思樹 | other trees |
|---|---:|---:|
| ridge / convex (TPI > 2 m) | **66 %** | 23 % |
| sunny S–SW face (> 0.35) | **73 %** | 33 % |
| valley (TPI < −2 m) | **0 %** | 25 % |
| ≥ 2 of the 3 nearest trees also 相思樹 (stands, not singles) | **91 %** | — |

Instance rules: scale = crown radius / 6.95 m, height × U(1.05, 1.30), mild anisotropy, the leaning trunk's crown offset turned downslope
(±30°), lean 0.15 × slope (≤ 8°) + noise; tints 5 / 6 (sunny yellow-olive) / 7 (greyer) from a 20 m tone field biased to 6 on sunny faces.
Map: `acacia_map.png`.

## 4. Native A / B (same cameras, sun, flight; A = Mix T `m7` frames of PR #33, B = `a8`)

Native-pixel numbers (`acacia_ab_report.json`, tree mask = forest vs empty frame of the same pose; 32 × 32 px canopy blocks):

| view | | canopy share of frame | median brightness | median saturation | median hue | block hue std (stand-scale colour variety) | canopy blocks ≥ 6° yellower than A's median | pixels B ≠ A |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 50 m | A / B | 0.906 / 0.864 | 0.290 / 0.322 | 0.300 / 0.303 | 114.8° / 104.4° | 15.5° / 16.7° | 20 % / **43 %** | 44 % |
| 200 m | A / B | 0.690 / 0.680 | 0.333 / 0.353 | 0.246 / 0.262 | 122.7° / 114.6° | 15.7° / **18.7°** | 27 % / **40 %** | 34 % |
| 500 m | A / B | 0.249 / 0.253 | 0.377 / 0.384 | 0.200 / 0.216 | 135.8° / 132.0° | 14.1° / 15.7° | 22 % / **28 %** | 8 % |

Canopy cover inside the block (screen, `frames_report_*.json`): A 89.8 / 89.3 / 85.2 %, B 84.7 / 87.7 / 87.0 % at 50 / 200 / 500 m — the
相思樹 crowns are airier close up (ground and limbs show through, as in the stand photos) and, with the clump LODs, as continuous as 紅楠
from 500 m. B's canopy is a little brighter, yellower and more varied at every height; the variety grows most at 200 m, where the stands
read as separate colour / texture blocks.

* Stills: `ab_still_agl50.jpg`, `ab_still_agl200.jpg`, `ab_still_agl500.jpg` (A left / B right), native 1:1 crops `ab_crop_*.png`.
* **Flyover, normal speed** (7.5 s canopy pass, 40 m/s, 56–78 m AGL): **`fly_AB_m7_a8.mp4`** (A | B, 60 fps) and `fly_a8.mp4` (B,
  1080p), frames 90 / 180 / 270 / 360 in `ab_flight.jpg`. The rejected dense chain a5 (500 m speckle) is kept as `a5_ab_still_agl500.jpg`.

Single reviewer's reading of native frames; please judge the videos yourself.

## 5. Flicker / pop / repetition

| flyover (451 frames, 60 fps) | A Mix T | B a8 |
|---|---:|---:|
| whole-frame pop spikes (ratio > 1.5) | 0 | **0** |
| 8 × 6-tile pop hits | 0 | **0** |
| calculated LOD switches in view (total) | 747 | 740 |
| mean in-view LOD0 / 1 / 2 / 3 | 0.5 / 100.7 / 326.6 / 65.4 | 0.9 / 111.7 / 320.6 / 61.3 |

No pop events, no grey / colour jumps (native guard PASS on every still). Repetition: the acacia stands use one tree with yaw, scale,
anisotropy, lean and three tints; at 200–500 m nothing repeats visibly; at 50 m the same low-fork silhouette can be spotted twice in one
frame (`ab_still_agl50.jpg`, left) — the case for a second crown form. LOD1 → LOD2 density step: see §0 caveat (a).

## 6. GPU — exploratory (UHD 770; empty / A / a7 / a8 interleaved, order reversed in round 2)

Forest cost = forest − empty of the same round and view, mean [min..max] of 2 rounds (ms) — run `p9` (`perf_p9.json`); `p8` (`perf_p8.json`,
empty / A / a7 only, an hour earlier) reproduces A and a7 within 0.2 ms.

| view | A Mix T (m7) | B clump (a7) | **B tight (a8)** | a8 − A | a8 − A (%) |
|---|---:|---:|---:|---:|---:|
| 50 m AGL | +116.2 [115.5..116.9] | +152.2 [151.5..152.9] | **+138.8 [138.2..139.5]** | +22.6 | +19 % |
| 200 m AGL | +70.8 [70.7..70.9] | +94.8 [94.7..94.9] | **+83.0 [82.9..83.1]** | +12.2 | +17 % |
| 500 m AGL | +17.2 [17.2..17.2] | +18.8 [18.8..18.8] | **+18.2 [17.8..18.7]** | +1.0 | +6 % |
| flyover median | +79.5 | +111.5 | **+101.1** | +21.6 | +27 % |
| flyover p95 | +107.7 | +150.7 | **+133.5** | +25.8 | +17 % |

Where B's extra cost goes (a8 − A, 50 m): prepass +2.5, base pass +9.1, **shadow depths +10.9 ms**; 200 m: +2.9 / +5.0 / +4.2. Tight cards
removed 37 % (50 m) to 49 % (200 m) of the clump chain's extra cost at identical pixels — card area, not triangles, is what costs.
Absolute frame GPU at 50 m: empty 41.1, A 157.3, a7 193.3, a8 180.0 ms (UHD 770, 1080p).

Why an acacia costs more than a 紅楠 of the same footprint: its LOD0 / LOD1 keep 80 % / 40 % of the sprays with both card views (紅楠 T:
40 % / 12 %) to stay feathery instead of blobby, and see-through crowns cast and receive more layered shadow. Next levers, in order: a
hybrid LOD1 (≈ 15 % sprays + clump cards), clump cards from LOD1 on for trees beyond ~100 m, then shadow-casting from LOD2.

## 7. Known issues / not done

1. LOD1 → LOD2 density step (single-spray cards → clump cards) at ≈ 135 m; a hybrid LOD1 (fewer sprays + clumps) is the next step.
2. One golden tree / seed; a second acacia crown form (like 紅楠 crown B) would cut repetition at 50 m.
3. No flowering variant (Apr–Jun golden canopy — the most visible seasonal signature of 相思樹 in the Taipei hills).
4. Some UE processes in the a4 lineup exited with 0xC0000005 *after* `QUIT_EDITOR` (receipts written, next fresh-process verify PASS); not
   seen in later runs, cause not investigated.
5. The receipt of the first `acacia` import was overwritten by the next import (same receipt name); its numbers are in this report /
   `game_report_acacia.json`; later imports are saved as `ac_import_{dense,clump,tight}.report.json`.
6. A (Mix T) frames are PR #33's `m7` renders (same project content, same harness, read in place); perf A was re-measured in this session.

## 8. Reproduce

```powershell
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"; $py = "D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe"
# golden (docs/treegen/acacia-confusa.md) -> out/treegen/acacia/v1/v1_acacia_confusa.blend
& $b -b --factory-startup -noaudio --python tools/treegen/acacia_confusa.py -- $PWD/out/treegen/acacia/v1 --no-render --tag v1
# game chains: first export bakes the spray atlas; later profiles reuse it (the clump profiles bake bake/c*_*.png + bake/clumps.json)
$env:ACW_TL_SPECIES = "acacia"
$env:ACW_TL_PROFILE = "acacia"; & $b -b --factory-startup -noaudio --python tools/treegen/machilus_game.py -- $PWD/out/treegen/acacia/v1/v1_acacia_confusa.blend $PWD/out/treegen/acacia_game
& $py tools/treegen/machilus_game_textures.py out/treegen/acacia_game acacia
$env:ACW_TL_REUSE_BAKE = "1"
foreach ($p in "acacia_dense", "acacia_clump", "acacia_tight") { $env:ACW_TL_PROFILE = $p
  & $b -b --factory-startup -noaudio --python tools/treegen/machilus_game.py -- $PWD/out/treegen/acacia/v1/v1_acacia_confusa.blend $PWD/out/treegen/acacia_game }
& $py tools/treegen/machilus_game_textures.py out/treegen/acacia_game acacia wide
# UE: first import (textures + materials + chain "acacia"), then the clump material + chain, then the tight chain (mesh only)
$g = "$PWD\out\treegen\acacia_game"
./tools/treegen/run_tl.ps1 -Script ac_import.py -Name ac_import -Expect ac_import.report.json -Env @{ ACW_AC_GAME = $g }
./tools/treegen/run_tl.ps1 -Script ac_import.py -Name ac_import_clump -Expect ac_import.report.json -Env @{ ACW_AC_GAME = $g; ACW_AC_PROFILE = "acacia_clump"
  ACW_AC_LEAF_TAG = "AcaciaW"; ACW_AC_ATLAS_STEM = "T_Acacia_LeafAtlasW"; ACW_AC_CLIP = "0.25"; ACW_AC_DEST = "/Game/HillsideForest/Trees/AcaciaClump" }
./tools/treegen/run_tl.ps1 -Script ac_import.py -Name ac_import_tight -Expect ac_import.report.json -Env @{ ACW_AC_GAME = $g; ACW_AC_PROFILE = "acacia_tight"
  ACW_AC_MESH_ONLY = "1"; ACW_AC_LEAF_MAT = "M_TL_AcaciaW_LeafCards"; ACW_AC_DEST = "/Game/HillsideForest/Trees/AcaciaTight" }
# forest B (PR #33 inputs in out/forest/hillside: terrain, instances_mix.json, views.json)
& $py tools/forest/hillside_acacia_mix.py out/forest/hillside
./tools/forest/run_hf_all.ps1 -Rev a8 -Instances instances_acacia.json -AChain T -CLeaf M_TL_AcaciaW_LeafCards `
  -CMesh /Game/HillsideForest/Trees/AcaciaTight/acacia_acacia_tight_lod0/StaticMeshes/acacia_acacia_tight_lod0
$mv = "unreal/TreeLookdev/Saved/TreeLookdev/hillside/movies"; $mvA = "<PR #33 worktree>/$mv"   # A = Mix T m7 frames
& $py tools/forest/hillside_frames.py out/forest/hillside $mv a8 out/forest/hillside/evidence_a8 views.json instances_acacia.json
& $py tools/forest/hillside_frames.py out/forest/hillside $mvA m7 out/forest/hillside/evidence_m7 views.json instances_mix.json
& $py tools/forest/hillside_acacia_ab.py out/forest/hillside/evidence_m7 out/forest/hillside/evidence_a8 $mvA $mv m7 a8 docs/evidence/forest/hillside_v1/acacia_v1
$env:ACW_AB_MOV_A = $mvA; & $py tools/forest/hillside_ab_sheets.py out/forest/hillside/evidence_m7 out/forest/hillside/evidence_a8 $mv m7 a8 docs/evidence/forest/hillside_v1/acacia_v1 "A ..." "B ..."
./tools/forest/run_hf_perf.ps1 -Rev m7 -Prefix p9 -Rounds 2 -Views agl50,agl200,agl500,flight -ExtraRevs a7,a8
& $py tools/forest/hillside_perf.py unreal/TreeLookdev/Saved/TreeLookdev/hillside/perf p9 docs/evidence/forest/hillside_v1/acacia_v1/perf_p9.json
# lineup (UE visual test): hillside_lineup.py out/forest/hillside; run_hf_all.ps1 -Rev a6 -Instances instances_lineup.json -ViewsFile views_lineup.json ...
```
Revisions: a1 / a2 / a3 / a4 / a6 lineups (first / dense / dither / clip 0.25 / clump), a5 / a7 / a8 forests (dense / clump / tight).
Material experiments: `ac_tune.py` (`ac_tune_a3.report.json`, `ac_tune_a4.report.json`); a4 left `M_TL_Acacia_LeafCards` at clip 0.25,
alpha-coverage 0.25, no dither — the adopted chain uses `M_TL_AcaciaW_LeafCards` (created at clip / coverage 0.25).
Native MRQ frame folders of this round were pruned after analysis (`prune_hf_movies.ps1`); the committed stills / sheets / videos / JSON
are the evidence.
