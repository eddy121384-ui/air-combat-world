# 柳杉 Cryptomeria japonica — Unreal 5.8 game asset v1

Branch `lookdev/taiwan-cryptomeria-unreal-v1` from `lookdev/taiwan-cryptomeria-japonica-v1` @ `c56b546` (PR #40, golden v2 accepted).
Source = **golden v2** (`docs/evidence/treegen/cryptomeria/cryptomeria_japonica_v2.blend`, now archived; v1 `.blend` unchanged,
sha256 `73C5C531…`). Isolated UE 5.8 project `unreal/TreeLookdev` only; no North Taiwan / Xinyi map, no PR #39 data touched; the golden
look was not changed. Revisions: `j1` species lineup, `j2` / `j3` 象山 forest with a 柳杉 plantation block.

> Draft for review. Host: **Intel UHD 770 iGPU, UE 5.8, standalone `-game` 1080p native MRQ**. GPU numbers exploratory (2 interleaved rounds).

## 0. Answer

**柳杉 v2 is a usable third game tree in UE 5.8**: it keeps the tall narrow dark cone, reads unmistakably next to 紅楠 / 相思樹 from
eye level to 500 m, passes the fresh-process persistence / material gates (no grey HISM), shows no LOD pops in the flyover.
GPU is reasonable: a 101-tree 柳杉 plantation block (replacing 20 broadleaf crowns) adds **−2.9 / +1.0 / +2.2 ms** at 50 / 200 / 500 m and **+13.6 ms flyover median** (flying straight over the block at 56–78 m; flyover p95 unchanged, −2.9 ms) on the UHD 770 — clump cards from LOD1 on make the distant 柳杉 cheaper than a broadleaf crown. Main residual risk: the LOD0 → LOD1 step (15k → 1.4k triangles) for trees right under a low camera; no pop was measured.

## 1. Exporter: what had to change (review 5557826475 was right — it did not run before)

All in the existing `tools/treegen/machilus_game.py` / `machilus_game_textures.py` / `adapters/unreal/treelookdev/ac_import.py`; no new
exporter. Every 紅楠 / 相思樹 default is unchanged.

| blocker | fix |
|---|---|
| no cryptomeria in the species switch | `ACW_TL_SPECIES=cryptomeria` → `cryptomeria_japonica` module, objects `CryptomeriaJaponica_*`, stem `cryptomeria`; the golden's params come from `ACW_TG_PARAMS=tools/treegen/params/cryptomeria_v2.json` so `mt.build()` reproduces v2 (exporter check: 2,035 nodes, 4,313 pads = golden) |
| golden stats hard-coded to `v1_stats.json` | `<tag>_stats.json` beside `<tag>_<species>.blend` when present, else v1 (old goldens unchanged) |
| clump code reads `mt.P["shell_c"]` | `shell_c=(0, 0, 16)` (crown axis point) added to the 柳杉 `P` — not used by the golden itself, v1 / v2 output unchanged |
| absolute clump counts are species-specific | profile key `clump_cover` = multiple of one full clump cover (n_pads / pads per clump); `n_clumps` still works |
| texture / material / GLB names were acacia-only | `machilus_game_textures.py <out> cryptomeria wide` (T_Cryptomeria_*, reddish-brown fissured bark palette); `ac_import.py` `ACW_AC_SPECIES` (T_ / M_TL_ / GLB names by species) |
| forest build knew forms A / B / C only | form **J** in `hf_build.py` / `hf_verify.py`: own mesh (`ACW_HF_J_MESH`), bark `M_TL_Cryptomeria_Bark`, leaf parent `M_TL_Cryptomeria_LeafCards` (`ACW_HF_J_LEAF`), tints 8 / 9; the gate fails a J HISM drawing any other species' material |

## 2. Game asset (one chain, built from the 相思樹 lessons; no LOD parameter search)

| LOD | triangles (branch + cards) | cards | card area (m², scale 1) | screen size |
|---|---|---|---:|---|
| LOD0 | **15,080** (4,728 + 10,352) | 2,588 cord pads × top + end, tight, ×1.29 | 5,967 | 1.0 |
| LOD1 | **1,380** (920 + 460) | 115 **clump** cards (2.4 × one full cover), top + side, tight | 2,683 | 0.5 |
| LOD2 | **898** (630 + 268) | 67 clump cards (1.4 ×) | 1,586 | 0.15 |
| LOD3 | **607** (455 + 152) | 38 clump cards (0.8 ×, ×1.12), top only | 1,102 | 0.06 |

(紅楠 A chain T: 34,272 / 8,578 / 1,400 / 534; 相思樹 tight: 38,156 / 16,752 / 1,477 / 452.)
Bounds at scale 1: sphere 12.78 m, centre 12.66 m up, half-width 5.3 × 5.0 m (branch tips).

* **Atlas** 4096 × 2048 (`T_Cryptomeria_LeafAtlas_BC/_N`): 16 cord-pad tiles (coverage 3–12 % — single cords) + 16 clump tiles, each an
  orthographic bake of a real 2.4 m chunk of the golden crown (75–96 pads per chunk; coverage 22–31 %). Preview `atlas_preview.jpg`.
* **LOD1 from clump tiles, decided before UE**: the first export used single-pad cards ×2.0 at LOD1 (5,232 triangles); with 3–12 % tile
  coverage that is exactly the 相思樹 a1 / a5 failure (blobs / speckle at 52–135 m). Clump cards from LOD1 on avoid it — and make LOD1–3
  cheap. Cost: a large LOD0 → LOD1 step (15k → 1.4k triangles) at ~52 m slant (watched in the flyover, §4).
* **Materials** (`ac_import.py`): `M_TL_Cryptomeria_LeafCards` — Masked, two-sided, Two Sided Foliage, clip 0.25 + alpha-coverage 0.25
  (adopted in PR #36), same graph as the other leaf materials; `M_TL_Cryptomeria_Bark` opaque. **ISM usage flag set + compiled + saved
  at creation.** Mesh: Nanite off, PR #31 LOD build settings, slots Bark / LeafCards.

## 3. Unreal native validation

| gate | result |
|---|---|
| import receipt (`cj_import.report.json`) | PASS: 4 LODs, screens 1 / 0.5 / 0.15 / 0.06, slots → 柳杉 materials, both materials `used_with_instanced_static_meshes = True`, leaf MASKED + two-sided. UE exit 3 = one *handled ensure* of the level-editor mode manager during `-Cmd` startup (not from the script) |
| **fresh-process persistence** (`hf_verify`, a new editor process reading only what is on disk = editor reopened) | lineup j1 **220 / 220**, forest j2 **424 / 424**, forest j3 **424 / 424**: 柳杉 materials saved with ISM usage, packages clean after load, MASKED / two-sided / foliage shading, every form-J HISM uses the 柳杉 mesh + bark + leaf parents, nothing dirtied by loading every map |
| native material guard (standalone `-game` MRQ: tree pixels saturated green, not grey) | forest j2 / j3: **PASS** at 50 / 200 / 500 m. Lineup j1: eye / 45° PASS; ≈200 m frame FAIL on the hue rule only (62 % of mask pixels in 50–170°; saturation 0.23 = not grey): the tree mask includes the long blue sky-lit **shadow** of the 24 m tree (mask hue p75 = 194°) — a mask artefact, not a material error |

Native frames (`docs/evidence/forest/hillside_v1/cryptomeria_v1/`):

* `lineup_j1_{eye,oblique,aerial}.jpg` — 紅楠 A · crown B · 相思樹 · **柳杉** at eye level (≈ 80 m, LOD1), 32° and ≈ 200 m;
  `lineup_j1_crop.png` native pixels of the 柳杉 crown: coherent clumpy dark blue-green mass, no speckle.
* `j3_still_agl{50,200,500}.jpg` — the 象山 forest (PR #36 two-species) with a **101-tree 柳杉 plantation block** (46 × 40 m, 4 m
  spacing, 18–23 m, replacing 20 broadleaf crowns) under the flight line; `j3_flight_patch.jpg` flyover frames 300 / 360 / 420.
* **`fly_j3.mp4`** — normal-speed flyover (40 m/s, 56–78 m AGL, 60 fps), plantation in view frames 40–371.
* First placement `j2` (block north of the flight line) is kept as `j2_*`: the block hid behind the ridge / foreground broadleaves in the
  flyover — moved, the asset unchanged.

## 4. Visual acceptance (single reviewer, native frames)

* **Tall narrow cone kept?** Yes — lineup and flyover show the 24 m spire with the v2 crown mass; from above (200 / 500 m) the block reads
  as rows of narrow dark crowns, the plantation look of 頂山–石梯嶺.
* **Mid / far canopy volume?** Yes — clump cards keep a continuous dark mass at 200–500 m (no speckle, no see-through block).
* **LOD pops?** j3 flyover: whole-frame pop spikes **0**, 8 × 6-tile pop hits **0**, 818 calculated LOD switches in view (mean in-view
  LOD0 / 1 / 2 / 3 = 4.2 / 162 / 317 / 61). The LOD0 → LOD1 step happens at ≈ 52 m slant, i.e. only for trees right under the flight
  path; no visible jump in the frames, not measured separately.
* **Flicker / material errors / over-transparency?** None seen; masked clump cards read solid, not ghostly.
* Weak points: at ≈ 80 m (LOD1) the crown is a little more *columnar* and blobby than the golden's tapered cone; trunks show between the
  rows in the plantation interior (realistic for a plantation, slightly busy).

## 5. GPU — exploratory (UHD 770; empty / a8 / j3 interleaved, order reversed in round 2)

Forest cost of the plantation = j3 (a8 + 101 柳杉 replacing 11 crown B + 8 相思樹 + 1 紅楠 A) − a8 (PR #36 two-species forest) of the same
round and view, mean [min..max] of 2 rounds, run `q1` (`perf_q1.json`):

| view | a8 forest over empty | **j3 − a8** | per-pass (j3 − a8) |
|---|---:|---:|---|
| 50 m AGL | +139.6 | **−2.9 [−3.2..−2.7]** | prepass −0.5, base −1.6, shadow −0.6 |
| 200 m AGL | +83.1 | **+1.0 [0.9..1.1]** | prepass +0.5, base −0.5, shadow +1.0 |
| 500 m AGL | +17.8 | **+2.2 [2.0..2.3]** | prepass +0.7, base +0.4, shadow +0.9 |
| flyover median / p95 | +101.3 / +133.4 | **+13.6 [13.3..13.8] / −2.9** | — |

Reading: in the stills the block is mostly at LOD1–LOD3 (clump cards, 607–1,380 triangles, 1,100–2,700 m² of card area) — cheaper than
or equal to the broadleaf crowns it replaced. The flyover passes straight over the block at 56–78 m AGL, so its trees spend frames at
LOD0 (15k triangles, 6,000 m² of masked card area) — +13.6 ms median for 101 trees, i.e. roughly the per-tree cost of a 相思樹 at the same
distance (PR #36: 248 相思樹, +21.6 ms). Absolute frame GPU at 50 m: empty 40.4, a8 180.1, j3 177.2 ms (UHD 770, 1080p).

## 6. Not done / next

* No second 柳杉 form, no winter bronzing, no LOD0 → LOD1 hybrid (the step is the main remaining LOD risk if cameras fly lower).
* No North-Taiwan / Yangmingshan integration (as instructed); the plantation block in 象山 is a recognisability test only.

## 7. Reproduce

```powershell
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"; $py = "D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe"
$env:ACW_TL_SPECIES = "cryptomeria"; $env:ACW_TL_PROFILE = "cryptomeria"; $env:ACW_TG_PARAMS = "$PWD\tools\treegen\params\cryptomeria_v2.json"
& $b -b --factory-startup -noaudio --python tools/treegen/cryptomeria_japonica.py -- $PWD/out/treegen/cryptomeria/v2 --no-render --tag v2   # = archived v2 .blend
& $b -b --factory-startup -noaudio --python tools/treegen/machilus_game.py -- $PWD/out/treegen/cryptomeria/v2/v2_cryptomeria_japonica.blend $PWD/out/treegen/cryptomeria_game
#   (the exporter reads v2_stats.json beside the .blend; the docs copy cryptomeria_japonica_v2.blend is the editable archive)
& $py tools/treegen/machilus_game_textures.py out/treegen/cryptomeria_game cryptomeria wide
./tools/treegen/run_tl.ps1 -Script ac_import.py -Name cj_import -Expect ac_import.report.json -Env @{ ACW_AC_GAME = "$PWD\out\treegen\cryptomeria_game"
  ACW_AC_SPECIES = "cryptomeria"; ACW_AC_PROFILE = "cryptomeria"; ACW_AC_ATLAS_STEM = "T_Cryptomeria_LeafAtlasW"; ACW_AC_CLIP = "0.25"; ACW_AC_DEST = "/Game/HillsideForest/Trees/Cryptomeria" }
& $py tools/forest/hillside_lineup.py out/forest/hillside j                     # 4-tree lineup files (*_lineup_j.json)
& $py tools/forest/hillside_cryptomeria_patch.py out/forest/hillside 5 -25      # plantation block in the PR #36 forest (instances_acacia.json)
$cm = "/Game/HillsideForest/Trees/AcaciaTight/acacia_acacia_tight_lod0/StaticMeshes/acacia_acacia_tight_lod0"
./tools/forest/run_hf_all.ps1 -Rev j1 -Instances instances_lineup_j.json -ViewsFile views_lineup_j.json -AChain T -CMesh $cm -CLeaf M_TL_AcaciaW_LeafCards -Renders stills_forest,stills_empty
./tools/forest/run_hf_all.ps1 -Rev j3 -Instances instances_cryptomeria.json -AChain T -CMesh $cm -CLeaf M_TL_AcaciaW_LeafCards
& $py tools/forest/hillside_frames.py out/forest/hillside unreal/TreeLookdev/Saved/TreeLookdev/hillside/movies j3 out/forest/hillside/evidence_j3 views.json instances_cryptomeria.json
./tools/forest/run_hf_perf.ps1 -Rev a8 -Prefix q1 -Rounds 2 -Views agl50,agl200,agl500,flight -ExtraRevs j3
& $py tools/forest/hillside_perf.py unreal/TreeLookdev/Saved/TreeLookdev/hillside/perf q1 docs/evidence/forest/hillside_v1/cryptomeria_v1/perf_q1.json
```
The UE project content (PR #33 / #36 assets incl. `a8` maps) is untracked; it was copied from the PR #36 worktree (see memory note).
