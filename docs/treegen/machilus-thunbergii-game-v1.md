# 紅楠 Machilus thunbergii — game version v1 in Unreal Engine 5.8 (phase 2, round 1 visual review)

Phase 1 (golden reference, PR #30, review 5512731289) is accepted and **unchanged**: `docs/evidence/treegen/machilus/*` and
`machilus_thunbergii_v1.blend` are byte-identical (sha256 of the .blend `510F8D10…EB98833` checked before / after every export).
This round: one game-version tree, real UE5.8 renders at the golden cameras, 50 m / 200 m AGL, cost figures. No forest, no other
species, no large perf sweep. Host: Intel UHD 770 iGPU (SM5, no Nanite / VSM / Lumen) — every timing below is "this host only".

## 1. Result in one paragraph

The golden tree converts into a classic card-based game tree that keeps the golden crown outline, lobes and massing **exactly**
(the cards sit at the 15,456 golden spray transforms) and the deep glossy-green read at flight distances. At 50 m and 200 m AGL the
UE tree (automatic LOD1 / LOD2) is close to the Cycles reference; up close (2-3 m) it is clearly a card tree (flatter, less gloss).
LOD0 is 129k tris, LOD1 37k, LOD2 4.3k; textures 11.7 MB; measured single-tree GPU cost on this iGPU: +10.6 ms (front, LOD0), +1.15 ms (50 m AGL, LOD1), +0.14 ms (200 m AGL, LOD2). The dominant cost
is **masked-card overdraw** (mean ~17 rasterised card layers per tree pixel), not triangles — that is the first optimisation target.

## 2. What could not be "just imported", and how it was converted

| golden (Blender) | why it cannot go to UE as-is | game version |
|---|---|---|
| 15,456 geometry-nodes instances of 8 spray prototypes, 592k leaf meshes (20 M tris) | GN instances realise on export; 20 M tris is offline scale | each instance -> 2 alpha-masked cards (LOD0) at the **identical instance transform**; LOD1/2 keep a shell-weighted subset with enlarged cards |
| Cycles procedural leaf shader (UV veins, backface colour, translucency, coat, per-instance tint) | Cycles node graph does not translate | per prototype, orthographic Cycles bakes "top" (sky side) and "end" (along the shoot): albedo (emission of the golden base-colour chain, incl. backface colour and veins) x in-spray AO, camera-space normals -> tangent-space (DirectX), alpha; 2048^2 atlas, colour dilated into transparent texels, mips scaled for alpha coverage |
| per-instance tint attribute (INSTANCER) | instancer attributes do not export | vertex colour R = golden tint value per card |
| path-traced crown self-shadowing / GI | real-time has CSM + SSAO only | vertex colour G = crown-depth occlusion (lobe depth); card normals blended 60/75/90 % (LOD0/1/2) toward the nearest crown-lobe surface normal |
| procedural UV bark (noise, voronoi lenticels, bump) + radius-based young-twig blend | Cycles nodes; non-periodic noise in UV space | tileable 512^2 bark albedo + normal (periodic FFT noise, torus lenticel grid, golden palette); vertex colour R = young-twig blend from branch radius |
| 298k-tri branch mesh | too dense | re-meshed from the **same deterministic skeleton** (19,799 nodes reproduced) with fewer sides; thin chain ends cut (cards carry their own shoots): 67k / 16k / 1.5k tris |

Engine material graphs (no custom HLSL): `M_TL_LeafCards` (Masked, two-sided, Two Sided Foliage, clip 0.4) and `M_TL_Bark`.

## 3. LODs, triangles, materials

| LOD | screen size from | ~distance (60 deg hfov) | tris total | branch tris | cards (sprays) | card scale | vertices | sections / materials |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| LOD0 | 1.0 | < 52 m | **129,278** | 67,454 | 30,912 (15,456 x top+end) | 1.0 | 165,639 | 2: bark + leaf cards |
| LOD1 | 0.5 | 52-175 m | **36,710** | 16,310 | 10,200 (5,100 x 2) | 1.74 | 50,943 | 2 |
| LOD2 | 0.15 | > 175 m | **4,256** | 1,474 | 1,391 (top only) | 3.33 | 6,495 | 2 |

UE screen size = projected bounding-sphere diameter / screen height (~3.08 R / D at 60 deg; R = 8.5 m here), see the B0.1 note.
The 50 m AGL camera (slant ~152 m) selects **LOD1**, the 200 m AGL camera (~391 m) selects **LOD2**; both are also captured with
forced LOD0/1/2. Draw calls per tree: 2 sections (+2 in each shadow cascade it reaches).

## 4. Memory

| item | format | size |
|---|---|---:|
| leaf atlas colour + alpha 2048^2 | BC3 (DXT5) + mips | 5.59 MB |
| leaf atlas normal 2048^2 | BC5 + mips | 5.59 MB |
| bark colour 512^2 | BC1 + mips | 0.17 MB |
| bark normal 512^2 | BC5 + mips | 0.35 MB |
| **textures total** | | **11.7 MB** |
| LOD0 mesh | 165,639 verts x ~32 B (pos, packed tangents, full-precision UV, colour) + 32-bit indices | 6.9 MB |
| LOD1 / LOD2 mesh | | 2.1 MB / 0.2 MB |
| **mesh total (3 LODs)** | | **~9.2 MB** |

Texture sizes are computed from format and resolution (the commandlet's `get_memory_size` only reports resident low mips).
Textures and meshes are shared by every instance of the tree in a forest; per-instance cost is a transform.

## 5. Overdraw (offline rasteriser over the exported cards, 1920x1080, `tools/treegen/card_overdraw.py`)

| view / LOD | card footprint px | raster layers mean / p95 / max | alpha-passing layers mean / p95 |
|---|---:|---|---|
| front, LOD0 | 454,619 | **16.7** / 33 / 61 | 4.6 / 10 |
| front, LOD1 | 472,374 | 16.0 / 32 / 57 | 4.4 / 10 |
| front, LOD2 | 487,339 | 7.9 / 16 / 29 | 2.6 / 6 |
| 50 m AGL, LOD0 / **LOD1 (auto)** / LOD2 | 16.9k / 17.5k / 18.2k | 17.0 / **16.3** / 8.6 | 4.6 / 4.5 / 2.7 |
| 200 m AGL, LOD0 / LOD1 / **LOD2 (auto)** | 2.7k / 2.8k / 2.9k | 17.7 / 16.9 / **9.4** | 4.8 / 4.6 / 2.9 |

"Raster layers" = every card fragment (masked pixel shader / depth pre-pass invocations, worst case without early-Z rejection);
"alpha-passing" = fragments that survive clip 0.4. Only ~27 % of rasterised card area is leaf: **LOD1 does not reduce overdraw**
(1/3 of the cards at 1.74x size = same area). LOD2 halves it.

## 6. GPU cost (measured, UHD 770 only, standalone `-game` 1920x1080, CSV profiler + `r.GPUCsvStatsEnabled`)

Method (ForestSpike B0 workflow): one saved level per camera with and without the tree (same stage), 600 frames, first 150
discarded, median per run; 2 rounds with the tree / empty order alternated. Delta = tree - empty.

| view (auto LOD) | tree on screen | GPU delta round 1 / round 2 | mean | Prepass | Basepass | ShadowDepths | Lights |
|---|---|---|---:|---:|---:|---:|---:|
| close (LOD0, foliage fills the frame) | ~100 % | +24.65 / +24.04 ms | **+24.4 ms** | +8.4 | +8.0 | +3.2 | +0.5 |
| front (LOD0, ~25 % of the frame) | ~455k px | +10.52 / +10.57 ms | **+10.6 ms** | +1.2 | +3.8 | +3.1 | +0.9 |
| 50 m AGL (LOD1, ~170 px wide) | ~17k px | +1.22 / +1.08 ms | **+1.15 ms** | +0.18 | +0.54 | +0.68 | 0.0 |
| 200 m AGL (LOD2, ~60 px wide) | ~2.9k px | +0.16 / +0.11 ms | **+0.14 ms** | +0.03 | +0.07 | +0.07 | 0.0 |

Empty-stage GPU time is 25.7 ms (front) to 32.8 ms (ground-filled AGL views); SSAO alone is ~7.4 ms of that on this iGPU.
Reading: the near cost is fill-rate (Prepass + Basepass scale with card pixels x layers, section 5), and the shadow cost is the
cards rendered into the cascades. At 200 m one tree is ~0.1 ms (at the B0 noise floor, but the same in both rounds); at 50 m
~1.1 ms. **A forest of these at 50-200 m would be dominated by LOD1/LOD2 overdraw and shadow depth, not by triangles.**
This is one iGPU host: no statement about iPhone or discrete-GPU PCs.

## 7. Visual comparison (same cameras, same sun direction; stage matched by calibration, section 8)

| sheet | content |
|---|---|
| `docs/evidence/treegen/machilus_game/cmp_front.jpg` | golden vs UE, front (UE auto = LOD0) |
| `cmp_oblique.jpg`, `cmp_top.jpg`, `cmp_close.jpg` | golden vs UE at the other golden cameras |
| `cmp_front_lods.jpg` | front: golden / LOD0 / forced LOD1 / forced LOD2 |
| `cmp_agl50.jpg` | 50 m AGL: full frames + x4 crops golden / UE auto (LOD1) / LOD0 / LOD1 / LOD2 |
| `cmp_agl200.jpg` | 200 m AGL: full frames + x8 crops golden / UE auto (LOD2) / LOD0 / LOD1 / LOD2 |
| `ue_*.jpg` | the native 1920x1080 UE captures (r2: auto LOD at every camera + forced LODs at 50 m / 200 m / front) |
| `golden_agl50.jpg`, `golden_agl200.jpg` | the golden .blend rendered (read-only, ground enlarged in memory) at the two new AGL cameras |
| `overdraw_front_lod0_lod1_lod2.jpg`, `textures_preview.jpg` | card raster-layer heat maps (black 0 -> white 40 layers); leaf atlas / normal / bark |

**Differences from the golden reference (honest list):**

1. **Crown outline, lobes, mass distribution: same** at every camera (cards occupy the golden spray transforms).
2. **Close-up (2-3 m): clearly a card tree.** Leaves are flat (baked), lose the per-leaf glossy highlights and the 3D depth of the
   golden rosettes; red terminal buds read as flat red smears; some card edges show as straight cuts between clusters.
3. **Leaf clustering reads coarser** at 10-50 m: each card is a whole spray, so the crown surface shows spray-sized clumps with
   brighter sun-facing patches instead of the golden's fine leaf texture.
4. **Interior light:** real-time has no GI; the crown interior is lit by sky + SSAO + vertex-colour occlusion. Front/oblique tone was
   matched by calibration, but gaps between masses are darker / harder-edged than the path-traced golden.
5. **Specular:** the golden waxy coat produces sky reflections on individual leaves; the UE cards were tuned rougher / lower specular
   (a strong sheen on whole cards turned the crown grey-blue, cal round 4), so the UE crown is less glossy.
6. **Branches/bark:** procedural bark replaced by a tileable texture; the trunk reads slightly more mottled and the thin limbs
   inside the crown slightly lighter than the golden.
7. **LOD0 at distance is worse than LOD1/LOD2:** at 200 m forced LOD0 dissolves into speckles (thin leaves vanish in low mips),
   so the LOD switch improves the image there; LOD2 seen at 50 m shows holes and blotchy oversized cards (it is only used beyond ~175 m).
8. **Stage, not tree:** the golden ground/sky are greyer and bluer (AgX + Nishita); UE ground is more olive. A shallow dark band
   appears at the UE horizon (sky-atmosphere ground below the 4 km plane edge) at 50 m AGL.
9. Pale outlines on some leaf margins in the close-up (not present in the atlas: in-engine shading at alpha edges) - open.

## 8. Stage calibration (applied to the whole image, documented, not per-building / per-pixel tuning)

The Cycles stage (AgX, Nishita multiple-scattering sky x0.22, sun 4.2) has no exact UE equivalent. Five short calibration captures
(`tl_capture.py` sets cal/cal2...cal5) chose: manual exposure +0.8 EV, SkyLight 4.0 (shadowed ground ~0.6x sunlit, as in Cycles),
lower-hemisphere ground bounce (0.5, 0.55, 0.3), global saturation 0.9; leaf material Brightness 0.42, SSS 0.4, Specular 0.2,
Roughness 0.72, OcclMin 0.2; bark brightness 0.5. Without the ground bounce the crown underside and trunk go black; without the
brightness compensation the foliage goes pale lime under the brighter sky.

## 9. Most promising optimisation directions (not done in this round)

1. **Cut-out card geometry** (fit each atlas tile with a 6-8 vertex hull of the alpha): ~73 % of every card is transparent;
   a tighter hull typically removes half of the rasterised area for ~3x the vertices per card. Biggest lever on the measured overdraw.
2. **A real LOD1 reduction of area**, not just card count: merge neighbouring sprays into fewer, denser cluster cards (bake clusters)
   instead of enlarging single-spray cards.
3. **LOD2 / far: octahedral impostor** (one quad, ~0 overdraw) for the far range; the current LOD2 still rasterises ~9 layers.
4. Branch LOD0: 67k tris is half of LOD0; most is hidden inside the crown — cull branches whose radius < 3 cm that are fully
   enclosed by the card shell, keep only the visible scaffold.
5. Atlas: 1024^2 is likely enough beyond 50 m (texture streaming will do part of this automatically).

## 10. Reproduce

```powershell
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"; $py = "D:\Users\EDDY\.venvs\acw-xinyi\Scripts\python.exe"
& $b -b --factory-startup -noaudio --python tools/treegen/machilus_game.py -- docs/evidence/treegen/machilus/machilus_thunbergii_v1.blend out/treegen/machilus_game
& $py tools/treegen/machilus_game_textures.py out/treegen/machilus_game
& ./tools/treegen/run_tl.ps1 -Script tl_build.py -Name build -Expect tl_build.report.json
& ./tools/treegen/run_tl.ps1 -Script tl_capture.py -Name cap_r2 -Expect tl_capture.r2.report.json -Env @{ACW_TL_SPEC="<abs>/r2.json"}
& $b -b docs/evidence/treegen/machilus/machilus_thunbergii_v1.blend -noaudio --python tools/treegen/golden_views.py -- out/treegen/machilus_game/views.json out/treegen/machilus/v1_agl agl50,agl200 112
& $py tools/treegen/machilus_compare.py docs/evidence/treegen/machilus out/treegen/machilus/v1_agl unreal/TreeLookdev/Saved/TreeLookdev/captures/r2 r2 <out>
& $py tools/treegen/card_overdraw.py out/treegen/machilus_game <out> front,agl50,agl200
& ./tools/treegen/run_tl.ps1 -Script tl_perf_levels.py -Name perf_levels -Expect tl_perf_levels.report.json
& ./tools/treegen/run_tl_perf_schedule.ps1 -Prefix p1 -Rounds 2
```

The r2 capture spec (`unreal/TreeLookdev/Saved/TreeLookdev/specs/r2.json`) is reproduced in `docs/evidence/treegen/machilus_game/r2_spec.json`.
Generated UE content, GLBs and atlases are regenerable and not committed except the evidence images / reports listed above.
