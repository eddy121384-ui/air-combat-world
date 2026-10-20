# Commercial NPR clouds: research gate

2026-10-20 · Scope: Ace to Ace Cloud Lab only. Base: B2 `75db0dc3189cc9501210b4580521815d57b7a9cb`.

**Decision: GO for one bounded, prelit density cloud; NO GO for a new cloudscape or game integration.** Keep the accepted distant painting. A volume supplies spatial consistency and continuous extinction; an authored macro silhouette and designed light masses must supply the art. Neither “3D” nor a palette ramp proves hand-painted quality. Stop expansion if the motion evidence still reads as foam, rock or soft noise.

Evidence labels: **V** = directly verified in the linked original material; **E** = our engineering inference; **H** = unproven hypothesis. A published research demo is not proof of a shipped implementation or Safari performance.

## 1. Cygames: what the original material actually establishes

Sources: [official GCC follow-up](https://tech.cygames.co.jp/archives/2987/) and [Cygames GCC deck](https://speakerdeck.com/cygames/kuranhuruhuantasi-project-re-link-niokeruriarutaimuyun-biao-xian-falseyan-jiu-toji-shu-shao-jie). Page locators below use the Speaker Deck **transcript's numbered slide entries**, e.g. `?slide=108`; CDN `slide_N.jpg` filenames differ and must not be used as page numbers. The official follow-up explicitly says these techniques might not be adopted unchanged in Re:LINK.

| Question / locator | V: original result | E: portable consequence |
|---|---|---|
| Why noise is insufficient · [108](https://speakerdeck.com/cygames/kuranhuruhuantasi-project-re-link-niokeruriarutaimuyun-biao-xian-falseyan-jiu-toji-shu-shao-jie?slide=108) | Procedural volumetric noise did not deliver individually designed towering cumulus shapes. | Author the large shape; reserve noise for erosion. More octaves cannot supply composition. |
| Shape control · 109–113 | Combine spheres; editable volumetric shapes, including camera entry. | Spheres are authoring/support primitives, not visible opaque ball meshes. Ellipsoids are our extension. |
| Early implementation · 114–115 | A stored shape volume differed from the layer clouds and scaled poorly; the later version improved consistency. | Do not claim any arbitrary baked RGBA volume reproduces their later method. Our fixed-scale bake deliberately sacrifices relighting/scaling flexibility. |
| Effective interval · [116](https://speakerdeck.com/cygames/kuranhuruhuantasi-project-re-link-niokeruriarutaimuyun-biao-xian-falseyan-jiu-toji-shu-shao-jie?slide=116) | Define spheres in an otherwise invisible density space; collect density only inside them. | Bound the work before sampling. A single AABB is a simpler, looser POC bound; exact merged sphere intervals remain future work. |
| Shared lighting · 117–118 | Independent clouds use the same lighting as the cloud layer. | Share sun, palette, extinction and atmospheric tint across representations; matching only average RGB is insufficient. |
| Multiple clouds · 119–121 | Enumerate relevant cloud spheres along the view; stop when accumulated opacity is sufficient. | Front-to-back transmittance, depth clipping and early termination; overlapping support must not double-count density. |
| Mutual shadows · 122–123 | Consider multiple clouds along the light direction too. | A local prelight can include self-shadow only; one cloud does not validate inter-cloud shadows. |

The preceding raymarch section, entries 89–98, explicitly lists skipping misses, early termination and fewer steps; it also warns that larger steps reduce accuracy. Camera entry is stated at 111; a complete inside-camera implementation, interval union algorithm, buffer layout and per-platform timings are **Unknown**. Clamping the ray start to zero, sharing outside/inside density, and clipping to opaque depth are **E**, not quotations from Cygames.

### CEDEC 2017: verified scope, missing algorithm

[Official session](https://cedec.cesa.or.jp/2017/session/ENG/s5922ab3980408.html), 2017-08-30: **V** it covers arbitrary shape, hand-drawn NPR, noise, raymarch and optimization; the speakers explicitly describe reconciling illustration style with transparency and volume. The page says materials were planned for CEDiL, and no time-shift video. Searches of the official blog, Cygames Speaker Deck and CEDiL did **not** yield an accessible complete deck in this run. No CEDEC slide page numbers or shader details can responsibly be supplied.

Follow-up verification: the official Speaker Deck player visually confirms the single-cloud support diagram at 116 and light-direction multi-cloud diagram at 122. CEDiL's own `雲` search returned the Xenoblade 2018 and Ace Combat 2019 sessions, not this Cygames session; this is an access/search gap, not proof that the CEDEC materials never existed.

Consequently **Unknown**: their exact NPR transfer function, silhouette breakup, normal manipulation, light cache, sample count, and optimization timings. Do not substitute GCC slides or a press recap and label them CEDEC evidence. Hand-authored asymmetric masses + subtractive edge erosion + a broad warm/cool lighting ramp + precomputed light transmittance is **E/H**, a testable WebGL2 variant, not an authenticated Cygames recipe. Smooth balls plus a cel ramp alone are not sufficient.

## 2. Other commercial references: borrow only what is established

| Work / primary source | Verified, useful technique | Portability / Unknown |
|---|---|---|
| Sky · [Tanabe, GDC Summer 2020](https://www.gdcvault.com/play/1026903/Art-of-Sky-Children-of), [public 70-page deck](https://www.gdcvault.com/play/mediaProxy.php?sid=1026903) | V: original art presentation and mobile target exist; the accessible deck chiefly shows art/environment progression. | Cloud shader, mesh/particle recipe, inside transition and cloud-only cost **Unknown** from inspected material. Internet lookalikes are not evidence of Sky's implementation. Borrow no unverified algorithm or mobile FPS claim. |
| Xenoblade Chronicles 2 · [Inaba, CEDEC 2018 / CEDiL 1919](https://cedil.cesa.or.jp/cedil_sessions/view/1919) | V: developer states particle control was costly, polygon modeling unsuitable, and a raymarch cloud-sea method was developed. | Useful evidence against assuming mesh/particles are inherently cheaper or adequate. Slides require login; density encoding, lighting shortcuts, step counts and free-flight camera support **Unknown**. Switch success does not establish WebGL2 cost. |
| Ace Combat 7 · [Kono developer interview, Epic, 2019](https://www.unrealengine.com/en-US/developer-interviews/ace-combat-7-soars-high-with-ue4-to-become-franchise-s-best-installment) | V: trueSKY and 3D volumetric clouds; cloud entry reduces visibility and participates in the flight experience. | E: test continuous occlusion against real scene depth on high-speed routes. Exact shipped trueSKY cache/reprojection/LOD and Safari portability **Unknown**; do not import the middleware or infer its shader from screenshots. |
| Horizon Zero Dawn · [Guerrilla original publication](https://www.guerrilla-games.com/read/the-real-time-volumetric-cloudscapes-of-horizon-zero-dawn), [Schneider/Vos 99-page PDF](https://d3d3g8mu99pzk9.cloudfront.net/AndrewSchneider/The-Real-time-Volumetric-Cloudscapes-of-Horizon-Zero-Dawn.pdf) | V: low-frequency shape plus edge erosion/detail; cheap sampling until occupied, opacity exits, reduced-resolution temporal updates. PDF pages 31–39, 80–85, 91–95 (1-based PDF pages; printed slide labels are offset). | Borrow shape/detail separation and doing expensive work only in occupied regions. The 1-of-16 temporal strategy needs disocclusion handling; it is risky during fast 6DoF motion. Do not port their 64–128 view steps plus light samples or their console timing target. |

Three strongest borrowings: **art-directed support separate from detail** (GCC/Horizon); **bounded front-to-back extinction with empty-space rejection/opacity exit** (GCC/Horizon); **reduce runtime light/pixel work instead of endlessly adding steps** (Horizon). Our prelight bake is a different E adaptation of the last principle. These are verified research techniques, not a claim that all four shipped games use our hybrid.

Additional original AC7 source: [Kanno, CEDEC 2019 / CEDiL 2023](https://cedil.cesa.or.jp/cedil_sessions/view/2023) confirms UE4 + trueSKY and art/gameplay cloud definition; its listed PPTX requires login. WebGL2 has core 3D texture and depth texture facilities ([Khronos specification](https://registry.khronos.org/webgl/specs/2.0.0/)); API availability is not a Safari performance guarantee.

## 3. Local audit and failure causes

Read B0/B1/B2 research and performance documents, `cloud-field`, `cloud-layout`, `cloud-anime-renderer`, `cloud-volume`, `cloud-stable-renderer`, `cloud-hull`, `cloud-hybrid-renderer`, Lab and deterministic animation tools at the B2 base. Existing render evidence is retained, not reclassified as a new experiment.

| Representation | Root cause visible in code | Consequence |
|---|---|---|
| B0 | Three smooth ellipsoids per cluster; small noise multiplies density rather than designing the silhouette. | A useful diagnostic field is not an art-authored cloud asset. |
| B1 / #42 | Eye-to-center billboard basis, elevation-dependent unrelated top/side/base paintings, center-distance fade. | Fixed anchors do not mean fixed surfaces. Orbit changes the object; approach dissolves whole cards. Alpha-to-coverage is **not** conventional sorted transparency, so blaming sorting alone is wrong. |
| Animfix / #44 | Same smooth support with 32 density/normal texture probes; each occupied probe also reads three paint projections. | Stable world, rounded support and averaged low-contrast paint look like cotton. Up to 128 volume/paint fetches per covered pixel before exits; narrow density details are undersampled. |
| B2 / #45 | Density iso-surface, triplanar painted values, coverage mostly opaque outside a 90 m camera neighborhood; separate 3×3 directional fog. | Designed light in a painting becomes a texture on a solid surface. Rock/snow reading and hull/fog disagreement survive spatial stability. Separate opaque-depth prepass fixes one depth handoff bug, not the representation mismatch. |

Important existing evidence: [B2 research](../cloud-engine-b2/research.md), [B2 performance](../cloud-engine-b2/performance.md). Its 640×360 approach medians B1 85.98 / Animfix 553.47 / B2 205.28 ms are **historical SwiftShader** samples, not new runs or device FPS. Numerical continuity at one sampled region does not prove the entire image has no hard crossings.

Afterglow source was read at `45d75d362d2d3dde2b7abeb5aadc5447aefead1e`, `prototypes/afterglow-skies/game.js` on #51: merged 3D puff meshes, world noise modulating cel light thresholds, rim, peripheral point fluff and ellipsoid-driven screen whitening. Borrow its separation of light masses and micro-detail; opaque puffs plus a separate whitening proxy still need entry/orbit evidence. No changes to #51.

Also inspected Opus art-direction source documentation at `09aa191fb58c3ce7ab9985ff0d7972c1046da192`: analytic world ellipsoid intersection on proxy quads, parent-mass normal transfer, sun-depth shadow and inside mist. Analytic intersection is not the B1 rotating-image problem, but opaque first surfaces remain a different compromise. This is **local experimental evidence**, not a commercial reference.

**Cloud Cinema 2.5D latest original HTML: missing.** No matching tracked/local file or Cinema PR found in the checked worktrees/remote branch inventories. Its shader, source version, correspondence between views and entry behavior are Unknown; no invented reconstruction or conclusion about its implementation.

## 4. Compare by distance and transition

| Need | Preferred division of responsibility | Remaining risk |
|---|---|---|
| A: distant painted wall | Accepted R2 painting / 2.5D on distant sky. Do not fly into an infinitely distant painted landmark. | No translational parallax; distant placement must remain credible under camera roll and sky mapping. |
| B: world-fixed middle cloud | Authored macro masses, world-fixed 3D density and color/light. | “3D stable” still fails art if smooth shapes, uniformly soft edges or noisy shading dominate. |
| C: traversable nearby cloud | Same local medium integrated from outside and inside, no opaque shell or whole-cloud distance fade. | At low sample budgets, tangents, fast movement and silhouette voxels can band/pop. |
| D: inside occlusion/transition | Beer–Lambert extinction over that same density; foreground aircraft/sea clipped by opaque depth. | Baked light cannot respond to a changing sun. No independent screen-white inside toggle. |

## 5. Two bounded candidates and expected cost (E, not measured)

| | A — prelit local density brick (recommended) | B — painted first surface + volumetric fringe |
|---|---|---|
| Representation | One authored eroded ellipsoid union; bake density + premultiplied RGB into 64³ RGBA8; fixed sunlight/palette. | Fixed sculpted surface or analytic ellipsoid surface, broad transferred normals, depth/light cache, thin soft fringe and inside mist. |
| Runtime | One scene color+depth pass, one composite; AABB interval, at most 24 single 3D texture probes, stop at low T. Half linear resolution default, no temporal history. | Surface pass, soft fringe pass, opaque scene depth, mist composite; added overdraw/coverage or sorting complexity. |
| Resources | 1 MiB volume; 640×360 RGBA8+32-bit depth ~1.76 MiB RT; no new artwork, mesh builder, MSAA or dependency. CPU density/prelight bake only on asset apply. | Existing B2 5.33 MiB atlas + geometry, ~10.55 MiB MSAA/depth RT at 640×360 before fringe; optimizations could lower this, unmeasured. |
| Why / why not | Continuous medium removes the shell/mist handoff; prelight replaces per-step triplanar paint and nested light marching. Simpler falsifiable experiment than new engine work. | Likely stronger crisp painted surface at middle distance, but repeats B2's unresolved “solid object becomes fog” design problem and adds a fringe seam to solve. Not recommended for this POC. |

**H:** prelit broad color masses + asymmetric erosion can retain a convincing hand-painted character during 180° orbit. **H:** 24 samples and half resolution are acceptable in fast flight on iPhone Safari. Neither is established by the references. Fixed light, fixed scale, one brick and no mutual shadows are explicit POC limits.

## 6. Research Gate and experiment contract

GO because volume integration, authored support and bounded work are established, and the existing Lab already provides WebGL2, scene depth, R2 background and comparison renderers. This is a small adaptation, not an attempt to reproduce Cygames or a new cloud engine. Research is committed **before** implementation.

Only add a Lab one-cloud mode plus a small field/cache/renderer and reproducible capture harness. Keep B1/B2 algorithms unchanged. All comparisons share seed 73, the same single-cloud input, opaque scene, sun, resolution and camera poses; identify adaptation of their input separately from their historical nine-cloud results. One approach+skim route, one 180° orbit with a 90° checkpoint, one entry route, one exit route. Fixed seed and exact simulation times; continuous clips contain every captured runtime frame, no generated/interpolated frames. Their encoded playback rate is not measured FPS.

First inspect sparse stills, then short continuous clips. Reject on billboard rotation, rock/foam reading, banding, hard entry/exit, foreground occlusion error or loss of broad warm/cool masses. No expansion, new cloud sea or game connection after an art failure. Numerical tests cover determinism, inside/outside density/extinction, cache and no camera-dependent rebuilds; they do not certify art.

Measure warmed draws using external disjoint timer queries where available and synchronized wall time separately; show distribution/sample count, actual buffer and renderer string, with cloud-disabled control. SwiftShader is software and supports only within-run relative diagnosis. Actual iPhone Safari startup, WebGL2/depth/3D filtering, landscape orientation, GPU/memory limits and ten-minute thermal behavior remain **Unknown until tested on hardware**. No 30/60 FPS claim.
