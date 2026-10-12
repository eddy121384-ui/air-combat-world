# AC7-class aerial forest — visual benchmark and rendering research v0.1 (Issue #19, Phase A)

Status: **Phase A research only — revision 1, pending second human review.** No Unreal scene, shader, tree mesh,
tree placement, Xinyi geometry/terrain or PR #18 content was changed. No integration code, no forest map.
**Phase B (Codex) remains stopped** until this revision is reviewed.

| Item | Value |
|---|---|
| Branch | `research/ac7-forest-visual-benchmark` (Draft PR #20) |
| Base | `feat/opus55-xinyi-visual-quality` @ `ede7960d8ec05b2aa521b1e4c65b5bbd667c456d` (fetched 2026-10-12) |
| PR #18 read at | `spike/north-taiwan-vegetation-pilot` @ `e05a959aa9b6a751e72def07c2781d4709dd2b67` (Draft, untouched) |
| PR #15 read at | `research/north-taiwan-environment-assets` @ `796e03892d85731582ddb6c9151d3a1fe49d102a` (Draft, untouched) |
| Repo code read | `tools/lookdev/build_ground.py` (`write_tree_mesh`, `write_forest_clump`, hill-forest placement), `tools/lookdev/shaders/xinyi_city.hlsl::xc_foliage`, `adapters/unreal/lookdev/xinyi_look_build_level.py` (HISM layers) |
| Images committed | only the project's **own** UE5.8 capture (annotated 50 % frame + one native-pixel crop). **No AC7, AC8 or other third-party pixels are committed**; public references are links + timestamps only. |

## Revision log

| Rev | Commit reviewed | Change |
|---|---|---|
| v0 | `3574eef` | first Phase A draft |
| **v0.1** | review 5489064245 on `3574eef` | (1) REF-U1 retagged **owner-reported AC8, cross-title context only, NOT AC7 evidence**; added provenance-grounded public AC7 gameplay references (Digital Foundry Switch vs Xbox One S footage, PC Mission 2 gameplay) with timestamps and initial morphological targets (§4). (2) ~68 % cover restated as a **geometric model estimate** pending an Unreal top-down stencil measurement (§2.1, §7). (3) Phase B split into **B1** 1 km near/mid microbenchmark with a shared lightweight 6 km context and **B2** separate ≥ 6–9 km high-speed flight/streaming corridor (§12). (4) Far canopy layer S made an **independent factor** in a near-representation × far-layer factorial with a fixed common handover distance (§12.2). (5) UHD 770 allowed for B1 functional/indicative timing only, labelled "UHD 770 only", no extrapolation to PS5, PC discrete GPUs or phones (§2.4, §12.6). (6) Four publicly licensed Northern Taiwan aerial references added as link-only calibration candidates (§9.1). |

## Evidence tags used in this document

| Tag | Meaning |
|---|---|
| **[V-Dev]** | statement by the developer/publisher (Bandai Namco, Project Aces) or a report of their own talk |
| **[V-Epic]** | Epic Games documentation (UE 5.8 doc pages, fetched 2026-10-12) |
| **[V-3P]** | credible third-party technical analysis, **read second-hand** (summary of the original) |
| **[V-Vid]** | frames of a publicly posted gameplay/analysis video, viewed by me at a stated timestamp from the YouTube 1080p stream (re-encoded; **not native pixels**; nothing saved or committed) |
| **[Comm]** | community/player report — anecdotal |
| **[Acad]** | peer-reviewed publication |
| **[Repo]** | read or measured from this repository |
| **[Calc]** | computed in this pass (script in repo; reproducible) — **a model, not an engine measurement** |
| **[Obs]** | my visual observation of an image or frame — subjective, provenance stated |
| **[I]** | inference / hypothesis — **not** evidence; each has a test in §11 or §12 |

Nothing tagged [I] may be cited later as "AC7 does X". [V-Vid]/[Obs] describe **what the shipped game shows on
screen**, never its internal implementation; a Switch port's behaviour does not establish PS4/PC internals.

---

## 1. Executive findings

1. **Verified AC7 technical facts remain thin**: UE4 [V-Dev/V-Epic]; trueSKY volumetric clouds with a reported
   ~100 km map, ~15 km height and ~300 km visibility [V-Dev]; Digital Foundry's 2024 Switch analysis (second-hand
   text) that at significant height forests are "only represented using flat texture art" on Switch [V-3P]. **No
   developer talk on AC7 terrain or vegetation was found.** SpeedTree use is unverified.
2. **Now grounded in public AC7 gameplay footage [V-Vid]** (§4.3): Digital Foundry's own Switch-vs-Xbox One S split
   at 01:24 shows the **same forest drawn with 3D crowns near the camera on Xbox One S and as flat texture on
   Switch, while the distant forest patches look the same on both** — on-screen behaviour consistent with
   "far forest = ground texture" on Xbox One S too (H-AC1 supported, not proven). PC Mission 2 footage at HUD
   ALT ≈ 512 shows a **closed canopy with crown stipple and no visible ground** in the mid band, irregular
   field-following edges, hedgerows and single trees, and forest reading as dark patches of a field mosaic at
   ALT ≈ 699 looking several km away.
3. **The owner-supplied REF-U1 is an AC8 screenshot by the owner's account** — cross-title context only, **not AC7
   evidence**, and no longer used for any AC7 target.
4. **Our current hill forest fails mostly at forest scale.** In the project's own UE5.8 capture: a straight coverage
   cut-off at the Xinyi build box, bare "felt" Landscape beyond, light ground showing between crowns, regular clump
   speckle, no canopy grain on far ridges. A **geometric model** of the clump rule gives **~68 % top-down cover
   [Calc]** — an idealised estimate (ellipse projections, 0.9 × circumradius heuristic, 400 m × 400 m sample of the
   placement rule), **not** a pixel measurement of the screenshot, not the whole Xinyi forest, not GIS-validated.
   It is to be replaced by an Unreal top-down stencil measurement in B1.
5. **Canopy coverage, not tree count, is the controlled variable.** Issue #19's 2k / 5k / 10k per km² give only
   ~10 / 22 / 40 % random cover with 8 m crowns [Calc]; the public AC7 mid-band frames show effectively closed
   canopy. B1 sweeps 40 / 70 / 90 % coverage and translates to counts per arm.
6. **Every altitude shows several bands at once** [Calc, flat ground]: at 1,000 m / −20° pitch ~47 % of rows are
   theater band, none near band. Acceptance is judged per band inside each altitude pass.
7. **Recommended architecture to test (not a decision):** one canopy field drives both instance placement and a far
   canopy layer S; dark understory U under instances; rule-based edges. **Phase B is split**: B1 (1 km core +
   shared lightweight 6 km context, factorial near representation × S on/off at a fixed handover distance) and B2
   (separate ≥ 6–9 km corridor for 20 s high-speed flight and streaming, gated on a working UE host and B1 results).

---

## 2. Inputs read and baseline facts

### 2.1 Existing Xinyi trees and hill forest [Repo]

| Asset | Geometry | Placement / count | Rendering |
|---|---|---|---|
| `SM_XinyiTree` (`write_tree_mesh`) | 20-face jittered icosahedron crown (±12 %) + 4-sided trunk = **28 tris**, flat per-face normals | 20,401 street/park/OSM trees (v1 doc; later thinned by v0D curb filter); yaw, scale 0.8–1.25, 4 colour variants | HISM, LOD1/2, cull 1.5–2.6 km, casts shadow |
| `SM_XinyiForestClump` (`write_forest_clump`) | **5 icosahedra = 100 tris**, centre crown + 4 crowns at 4.0–6.5 m, radii 3.2–4.4 m, heights 5.5–8.5 m | 16 m grid, ±5 m jitter, on DTM where z ≥ 28 m or slope ≥ 0.08 (z < 45 m), outside buildings, **inside the Xinyi build box only**; 1,190 clumps; scale 0.9–1.35 | HISM "HillForest", cull 1.6–2.4 km, casts shadow |
| `xc_foliage` shader | no texture; 4 palette picks (camphor/banyan greens, golden-rain bloom), 3D value noise ×(0.75–1.25), height ramp 0.6→1.1 for underside darkening, roughness 0.85, night under-glow | — | one opaque material slot |

Derived from the placement rule [Calc]: **39 clumps/ha = 195 crowns/ha ≈ 3,900 LOD0 tris/ha**.

**Canopy cover — model estimate only [Calc]:** replicating the clump crowns (seed 11) on the 16 m jittered grid
(seed 3 for jitter/scale/yaw), rasterising each crown as an ellipse at **0.9 × icosahedron circumradius** on a
0.25 m grid over **400 m × 400 m** and averaging the interior gives **~67.7 % top-down cover**. Limits: idealised
silhouettes (the 0.9 factor is a heuristic between in- and circumradius); flat ground; the placement *rule*, not the
actual 1,190 placed clumps on the DTM; no occlusion by view angle; no GIS validation. **Required replacement:** a
top-down orthographic Unreal capture with trees writing CustomStencil (§6 F1), on the B1 core and, separately, on a
copy of the Xinyi hill-forest layout if the owner wants the production value.

### 2.2 PR #18 vegetation pilot [Repo, read-only]

Four opaque archetypes × 3 authored LODs: dense rounded 120/36/20, horizontal tiered 112/38/20, open vase 102/40/20,
tall columnar 108/38/20 tris. No textures or alpha. PR #18's own review notes: tiered tips plate-like, dense mass
joins visible, vase openness lost at LOD2, columnar far LOD reads as a spindle, repetition recognisable. Distance
sheet: 8.44 m reference tree projects to 52.6 / 26.3 / 13.2 / 9.9 px at 150 / 300 / 600 / 800 m (1080p, 60° vFOV).
No device or engine timing.

### 2.3 PR #15 inventory [Repo, read-only]

§6: 5–6 crown archetypes (V1 dense dome … V7 hillside broadleaf canopy, V8 grass/scrub); "the broader world needs a
canopy surface rather than instances beyond ~1.5 km"; overdraw (not triangles) is the mobile hazard; near-crown
removal in Xinyi v0D raised one view by ~7.5 ms because hidden facade/ground pixels became visible. Northern lowland
forest types from the 文山 survey: 紅楠, 相思樹, 水同木, 江某, 香楠, 山紅柿-大明橘 [Acad, via PR #15 S8].

### 2.4 Measurement host (owner decision, review 5489064245)

The known local host GPU is an **Intel UHD 770 iGPU** sharing package power with the CPU; earlier XinyiLook perf
drifted several ms between sessions and needed interleaved A/B [Repo, project notes]. Decision: **UHD 770 may run
B1 functional checks and indicative A/B timings**; every number is labelled **"UHD 770 only"** and is **not** a
PS5, PC discrete-GPU or iPhone budget. Arm *ranking* must be rerun on a named discrete-GPU host before any
platform-scale recommendation. If UE or the GPU is unavailable: **NOT MEASURED**, no inferred timings.

---

## 3. What was searched and not found

| Looked for | Result |
|---|---|
| CEDEC / UNREAL FEST / GDC talk on AC7 terrain, ground or tree rendering | **not found** (EN + JA). Only the UNREAL FEST WEST 2019 cloud talk [V-Dev] |
| Bandai Namco Studios "Making of AC7" Part 1 / Part 2 | fetched; no terrain/forest/LOD content; pages carry "© DigitalGlobe, Inc." (satellite imagery provider) — usage not stated |
| Epic developer interview on AC7 | title located; body returned HTTP 403 — **not read** |
| DF 2019 multi-platform written article | not reachable; the 2019 videos exist (§15) but were **not reviewed** in this pass |
| Eurogamer 2024 Switch article text | blocked to fetch; read via GoNintendo / Nintendo Everything summaries; **DF's own video was reviewed** (§4.3) |
| Official Steam store screenshots (10) | viewed: cockpit, air-to-air, city, snow mountains, character — **no forest frame usable** |
| Steep top-down AC7 dive over forest (R04-type) | **not found** in the sampled footage |
| AC7 middleware list incl. SpeedTree | **unverified** |
| Microsoft Flight Simulator official forest technique | no Asobo technical source found — not used |

---

## 4. AC7 visual reference evidence

### 4.1 Verified / attributed facts

| # | Fact | Tag | Source |
|---|---|---|---|
| A1 | AC7 is built on Unreal Engine 4 (first in the series) | V-Dev / V-Epic | Epic developer interview (title); Wikipedia |
| A2 | Volumetric clouds via Simul trueSKY plug-in for UE | V-Dev | BNS Making-of Part 1; UNREAL FEST WEST 2019 talk (玉置絢, 菅野昌人) reported by AUTOMATON |
| A3 | Map ≈ 100 km per side, ~15 km height, views across ~300 km | V-Dev (reported) | AUTOMATON |
| A4 | trueSKY initially ~60 % of GPU; reduced to ~30–40 % with a fast mode, distance LOD and VR mode | V-Dev (reported) | AUTOMATON |
| A5 | Switch: 720p docked / 540p handheld, 30 fps target | V-3P | DF 2024 via Nintendo Everything |
| A6 | Switch vs Xbox One: at significant height forests "only represented using flat texture art"; foliage draw distance pulled in; fewer trees, patchier grass | V-3P | DF/Eurogamer 2024-07-19 via GoNintendo |
| A7 | Switch removes foliage shadows vs Xbox One; structures pop in at about the same distance on both | V-3P | DF via Nintendo Life / GoNintendo |
| A8 | PC has no view-distance option; community `Engine.ini` edits (`r.ViewDistanceScale`, `r.StaticMeshLODDistanceScale`) reported to push trees/buildings further | Comm | DSOGaming; Steam discussions |

### 4.2 Hypotheses about AC7's forest look (on-screen behaviour; never internals)

| ID | Hypothesis | Status after v0.1 footage review | Further confirmation |
|---|---|---|---|
| H-AC1 | Beyond some distance, forest is ground texture on non-Switch platforms too | **Supported** by DF 01:24 (far patches identical on Switch and One S) and PC M2 15:00 [V-Vid]; YouTube compression could hide fine relief | PC climb 100 → 1,500 m over one forest (R07) |
| H-AC2 | Near trees are instanced meshes with a view-distance-scaled cull | consistent with A8 and with near crowns present on One S / absent on Switch (DF 01:24) | PC stock vs edited `Engine.ini` (owner's copy) |
| H-AC3 | Instance colour/value is tuned to the ground texture so the handover is soft | PC M2 11:00 shows a smooth dark forest band above the stipple zone without an obvious hard ring in a still [V-Vid] | motion review across the handover |
| H-AC4 | Tree shadows only in a near range | not assessed from footage | PC max settings, shadow vs distance |
| H-AC5 | Motion blur/TAA hide pop-in at combat speed | not assessed | per-frame review |

### 4.3 Reference matrix

**Cross-title context (not AC7 evidence):**

| Ref | Provenance | Use |
|---|---|---|
| **REF-U1** | supplied by the owner in the Phase A chat and **reported by the owner as an AC8 screenshot**; WebP 1024 × 429; mission, platform, capture mode, author and rights unknown; **not independently verified** | **owner-reported AC8; cross-title visual context only; NOT AC7 evidence.** Not committed. Not used for any AC7 target or threshold. Context note only: snow biome, high crown/ground contrast, irregular edges with outliers. |

**Public AC7 references (links + timestamps; viewed from the YouTube 1080p stream; nothing saved or committed):**

| Ref | Source | Platform / settings (as stated) | Timestamp | HUD (as displayed) | Observations [V-Vid / Obs] |
|---|---|---|---|---|---|
| P-01 | Digital Foundry, *Ace Combat 7 – Nintendo Switch DF Tech Review*, 2024-07-19, presenter Oliver Mackenzie — https://www.youtube.com/watch?v=WznKKwSBeHc | top: Nintendo Switch; bottom: Xbox One S (DF labels) | **01:24** (84.5 s) | off-frame | Same view, chase camera, mid–high oblique over forest and fields. **One S: near forest has visible 3D crowns; Switch: same area flat texture.** Distant forest patches look the same on both: dark green ground-texture areas in a field mosaic. |
| P-02 | same video | Xbox One S full frame | **01:30** (90.0 s) | off-frame | Low–mid pass (altitude not shown; est. ~100–300 m [I]). Closed conifer canopy near with legible crowns; crowns legible into the mid band; village and fields with tree groups and hedgerows; distant hills carry forest as dark patches without crown relief; haze lifts far values toward blue-grey. |
| P-03 | Shuvon Gaming, *Ace Combat 7: Skies Unknown – Charge the Enemy (Mission 2) \| 4K 60FPS Ultra Settings Gameplay*, 2024-05-19 — https://www.youtube.com/watch?v=2_7h8wQzc18 | "4K 60FPS Ultra Settings" stated; platform not stated (PC implied by Ultra settings — **unverified**) | **11:00** (660 s) | SPEED 689, ALT 512 (units as configured; not verified) | Mid band crop (right half): **dense closed canopy, crown stipple, no ground visible**, forest edge against pasture crisp but irregular; a power-line corridor cut through the forest; upper part of the crop shows a **smooth dark forest band without stipple** (possible instance→texture handover; distance not measurable). |
| P-04 | same | same | **12:10** (730 s) | partly occluded | Low pass: near conifers with alpha-card foliage and ragged crowns; groups and single trees in pastures, hedgerows; far hills as dark texture masses. |
| P-05 | same | same | **15:00** (900 s) | SPEED 787, ALT 699 | Banked look-down over several km: forests are **dark patches of the field/land-use mosaic** with no visible crown relief (YouTube compression caveat). |
| P-06 | same | same | **19:00** (1140 s) | ALT unreadable (very low, est. < 100 m [I]) | Ragged canopy skyline silhouette, strong edge breakup against sky; grass visible between trunks at grazing angle. |
| P-07 | Lord Lucus, *Mission 9: Faceless Soldier … [PC ULTRA 1080p]*, 2019-08-23, "recorded with NVIDIA ShadowPlay on PC" — https://www.youtube.com/watch?v=B9ptoZus-4Y | PC Ultra 1080p (stated) | 1:30–12:20 sampled | — | Snow/rock mountains; **no forest** — negative biome sample only. |

Limits: re-encoded streams (P-03 is a 4K capture viewed at 1080p); exposure, FOV and HUD units are not matched; no
steep top-down dive frame was found. These references support **morphological targets**, not pixel thresholds.

**Owner captures (optional later, ideal for calibration):** R01–R12 (v0 list, unchanged in intent), especially R04
(steep dive, top-down canopy cover), R07 (climb across the handover) and R11 (low sun). Store outside the repo with a
sidecar index (`id, mission, platform, version, settings, capture_mode, alt (HUD + units), speed, pitch_est, time,
weather, sha256, file`). Not required to start B1.

### 4.4 Initial AC7 morphological targets (from P-01…P-06)

| ID | Target | Evidence | Rubric link |
|---|---|---|---|
| M-1 | Closed canopy: inside "forest" areas no ground is visible in the mid band at oblique views | P-03, P-02 | F1 |
| M-2 | Individual crowns legible as stipple into the mid band; farther the forest becomes a smooth dark mass | P-01, P-02, P-03 | F2, F3 |
| M-3 | Far forest reads as dark patches consistent with the land-use mosaic (forest follows terrain/fields), not as bare terrain | P-01, P-05 | F3, F8, F10 |
| M-4 | Forest clearly darker than open land in every band; far forest shifts blue-grey under haze | P-01…P-05 | F5, F6 |
| M-5 | Edges irregular and field-following; hedgerows, tree lines, groups and single trees outside the mass; villages interleaved with trees | P-02, P-03, P-04 | F4, F8 |
| M-6 | Near: ragged crown silhouettes against sky | P-04, P-06 | F2 |
| M-7 | Platform scaling removes near 3D forest before it removes far texture | P-01, A6 | F12 / profiles |

Not established by the references: top-down cover at steep views, handover distance, shadow range, temporal
behaviour. Those stay calibration-pending.

---

## 5. Visual benchmark design

### 5.1 Distance bands (test viewpoints, **not** LOD switch distances)

Band by **slant range** camera→surface: **near < 150 m**, **mid 150–600 m**, **far 600 m–2 km**, **theater > 2 km**.

Projected size at 1080p / 60° vertical FOV (focal 935.3 px) [Calc]:

| Slant range | m per px | 8 m crown | 12 m crown |
|---:|---:|---:|---:|
| 150 m | 0.16 | 50 px | 75 px |
| 600 m | 0.64 | 12.5 px | 19 px |
| 1,000 m | 1.07 | 7.5 px | 11 px |
| 2,000 m | 2.14 | 3.7 px | 5.6 px |
| 4,000 m | 4.28 | 1.9 px | 2.8 px |
| 8,000 m | 8.55 | 0.9 px | 1.4 px |

Beyond ~3–4 km a crown is < 2–3 px; this is the regime Bruneton & Neyret 2012 handle with a terrain shader-map
[Acad] and matches M-3. The handover distance is a B1 measurement, not a decision here.

### 5.2 Altitude passes — screen share per band [Calc / flat ground]

| AGL | Pitch | Centre slant | Sky | Near | Mid | Far | Theater | Grazing angles |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 50 m | −5° | 574 m | 42 % | 28 % | 23 % | 5 % | 2 % | 0–35° |
| 50 m | −15° | 193 m | 27 % | 43 % | 22 % | 5 % | 2 % | 0–45° |
| 200 m | −10° | 1,152 m | 35 % | 0 | 36 % | 21 % | 9 % | 0–40° |
| 200 m | −25° | 473 m | 10 % | 0 | 58 % | 22 % | 10 % | 0–55° |
| 500 m | −15° | 1,932 m | 27 % | 0 | 0 | 51 % | 22 % | 0–45° |
| 500 m | −35° | 872 m | 0 | 0 | 16 % | 66 % | 18 % | 5–65° |
| 1,000 m | −20° | 2,924 m | 19 % | 0 | 0 | 35 % | 47 % | 0–50° |
| 1,000 m | −45° | 1,414 m | 0 | 0 | 0 | 73 % | 27 % | 15–75° |

**Flat-ground model only.** Hills occlude and re-order bands (facing slopes raise far/theater share at low altitude);
B1 reports measured band shares from depth for each viewpoint instead of relying on this table.

### 5.3 Gap visibility depends on grazing angle [Calc / Poisson-cylinder model]

| Canopy | 90° (top-down) | 45° | 30° | 15° | 8° |
|---|---:|---:|---:|---:|---:|
| 8 m crowns, 10k/km², D 6 m | 60 % | 37 % | 26 % | 10 % | 2 % |
| 8 m crowns, 20k/km², D 6 m | 37 % | 14 % | 7 % | 1 % | 0 % |
| 10 m crowns, 10k/km², D 7 m | 46 % | 23 % | 14 % | 3 % | 0 % |

Low passes hide sparse forests; canopy cover must be judged at steep views. Model only — B1 measures it.

### 5.4 Image-plane motion at combat speed [Calc]

Translation (60 fps): at 250 m/s a ground point at 150 m slant, 20° off the velocity vector moves **8.9 px/frame**;
600 m/10° → 1.1; 1,500 m → 0.5. At 400 m/s: 14.2 / 5.4 / 1.8 / 0.7.
Rotation moves the **whole frame** independent of distance: a level 9 g turn at 250 m/s has r ≈ 712 m and yaw
≈ 20°/s → **5.5 px/frame**; 6 g → 3.6 px/frame. Far-band content is nearly static under translation but not under
rotation, so B1 must test both.

### 5.5 Native-pixel comparison protocol

1. Fixed 1920 × 1080 output, 60° vertical FOV, screen percentage 100 % for comparison captures (an upscaled
   profile may be measured separately and labelled).
2. Fixed camera pose/path files (ENU metres + yaw/pitch/roll per frame), fixed sun, sky, fog, **manual exposure**,
   same post settings, seed and time.
3. Compare **unchanged native crops** at rectangles chosen before rendering; enlargements only nearest-neighbour,
   labelled. Never auto-fit, histogram-match or sharpen one arm.
4. Static frames after ≥ 64 warm-up frames with the camera locked; motion frames at fixed indices for every arm.
5. AC7 references are compared for **structure and statistics** (M-1…M-7), never by pixel difference.
6. Every sheet records arm, factor levels, commit, seed, pose id, frame index, AA mode, screen %, exposure,
   host label, capture SHA-256.

---

## 6. Forest-scale success / failure rubric

Scored 0–3 per band per altitude pass. *(cal.)* = calibration-pending: to be set against M-1…M-7, the Northern
Taiwan references in §9.1 and, later, owner captures. No *(cal.)* value is a pass/fail gate until the reviewer
accepts the calibration.

| ID | Criterion | Measure | Fail (0) | Pass target (≥ 2) |
|---|---|---|---|---|
| F1 | **Canopy closure / density** | visible-ground fraction (VGF) in the forest mask — see measurement note below | VGF at 45° > 35 % for "closed forest" | VGF at 45° ≤ 15 % *(cal.)*; top-down within ±10 % of the target cover; AC7 M-1: ~0 at oblique mid-band views |
| F2 | **Crown legibility (near/mid)** | can a reviewer separate crowns and ≥ 3 crown types at 150–600 m | blob carpet or identical repeats | distinct crowns, mixed sizes, no recognisable clone in a 9 × 9 crown window |
| F3 | **Canopy grain (far/theater)** | luminance σ of 32 × 32 px tiles in forest vs adjacent bare slope; FFT peak at instance grid | far forest flatter than bare terrain | σ_forest ≥ 1.5 × σ_bare *(cal.)*; no periodic peak |
| F4 | **Edge breakup** | perimeter of forest mask / perimeter of its 50 m-smoothed outline; outliers | straight cut or build-box edge | ratio ≥ 1.3 *(cal.)*; outliers within 30 m; straight edges only along mapped features |
| F5 | **Value stratification** | forest vs grass L*; lit crown vs shadow vs gap | forest ≥ grass L*; gaps read as lawn | forest mean L* below grass by ≥ 10 *(cal.)*; gaps darker than lit crowns |
| F6 | **Colour palette** | hue/chroma spread; ridge vs valley shift | single flat yellow-green | dark blue-green base, olive/yellow-green patches, accents ≤ 10 % area *(cal.)* |
| F7 | **Shadow & ground response** | slope-to-sun shading; cast-shadow character per band | far "felt"; near polka dots on bright ground | ridge/valley split at far; near shadows on dark understory |
| F8 | **Clearings, roads, interfaces** | cuts follow roads/power corridors/lots | trees on roads, data-box edges | aligned cuts; scattered trees at town interface |
| F9 | **Representation pop** | per-frame mean \|ΔL*\| in 64 × 64 px tiles crossing a transition ring (slow dolly) | step > 3× median frame change | ≤ 1.5× median *(cal.)*; no ring visible at 1× speed |
| F10 | **Far fusion seam** | tile-mean L*/C* across instance→S boundary | visible ring | \|ΔL*\| ≤ 3, \|ΔC*\| ≤ 3 *(cal.)* |
| F11 | **Temporal stability** | locked camera 64 frames: per-pixel temporal σ of L*, p95 in forest mask; rotation path review | p95 σ > 4 L* | p95 σ ≤ 1.5 L* *(cal.)*; no far-band crawl under rotation |
| F12 | **Cost** | §12.6 | — | judged at the decision gate at matched F1, not by this rubric |

**F1 measurement note (review fix).** Instances write **CustomStencil** (value per arm component, e.g. 1 = tree
instances, 2 = impostors). A material-only far layer S **cannot** be attributed through tree stencil. S therefore gets
an instrumented **measurement view**: a static switch in the S material that outputs its own coverage term
(0 = gap, 1 = canopy) as unlit emissive, captured in a separate pass with the same camera. The forest mask is the
canopy field projected to screen (another debug pass). Report separately: geometric canopy pixels (stencil), S
material canopy fraction (debug output), and combined VGF. Never claim S pixels as stencil-measured.

A representation that wins cost by failing F1 is **not** a win (Issue #19 matched-coverage rule).

---

## 7. Baseline analysis — what is wrong at forest scale

Project's own UE5.8 editor capture, `unreal/Saved/XinyiLook/evidence/final_D_hillside_farcity_day.png`
(captured 2026-09-30, editor viewport — axis gizmo visible; source SHA-256 `46501b1a…94608`; camera pose not
recorded). Since then hill-forest placement, `write_forest_clump`, `write_tree_mesh` and `xc_foliage` are unchanged in
git history; only the street-tree set was thinned by the v0D curb filter (`2cf7f8c`), which does not affect this view.
The reviewer should approve from the decoded images, not from these descriptions.

![Baseline annotated](assets/ac7-forest-benchmark-v0/baseline_ue58_hillside_annotated_50pct.jpg)

*Full frame reduced to 50 %. Cyan box = native crop below.*

![Baseline native crop](assets/ac7-forest-benchmark-v0/baseline_ue58_hillside_native_crop.png)

*Unchanged native pixels (640 × 360 from 0,720).*

| Mark | Observation [Obs] | Rubric | Root cause [Repo] | vs AC7 target |
|---|---|---|---|---|
| 1 | forest ends on a straight line | F4, F8 | placement limited to the Xinyi build box | M-5 |
| 2 | hills outside are bare smooth Landscape — "felt" | F3, F7 | no canopy layer outside instances | M-3 |
| 3 | faceted crown lumps; light olive ground between them; hard dark cast shadows → regular speckle | F1, F2, F5, F7 | 5-icosahedron clump on a 16 m grid; model cover ~68 % [Calc, estimate]; ground = open-grass Landscape colour; flat normals | M-1, M-4 |
| 4 | far ridges uniform green, no canopy grain or ridge/valley split | F3, F6, F7 | Landscape colour only beyond HISM cull (≤ 2.4 km) | M-3, M-4 |
| 5 | bare hill runs into the city fringe | F8 | same as 2 | M-5 |

The ~68 % figure supports mark 3 only as a **model expectation** that ground will show between crowns from steep
views; the visible gaps in the crop are an observation, not a measurement of cover.

PR #18 archetypes against the same rubric (from its own sheets, not re-rendered):

| Criterion | 28-tri reference | PR #18 archetypes | Comment |
|---|---|---|---|
| F2 crown legibility | one silhouette | 4 silhouettes, distinct at 150–300 m in its distance sheet [Obs] | real improvement, **near/mid only** |
| F2 at 600–800 m | ~10–13 px blob | identities reduce to width/height/gap cues (PR #18) | consistent with §5.1 |
| F1 / F3 / F4 / F7 / F8 / F10 | not addressed | not addressed | forest-scale problems independent of the crown mesh |
| Cost | 28 tris | 102–120 LOD0, 36–40 LOD1, 20 LOD2 | ×3.6–4.3 at LOD0; real cost unmeasured |

**Conclusion [I]:** at 200/500/1,000 m, which are dominated by mid/far/theater bands, the largest gains should come
from canopy closure, understory, edges and a far canopy layer, not from more crown triangles (H-02, tested by the
S factor in B1).

---

## 8. Commercial / documented technique comparison

| Technique | What it solves | Main cost axes | Flight-game risks | Mobile | Maturity in UE 5.8 | Evidence |
|---|---|---|---|---|---|---|
| **Static-mesh foliage / ISM / HISM** | one draw per batch; cluster culling | CPU culling/LOD per cluster, vertex work, shadow depth | whole cluster switches LOD at once; End Cull Distance makes groups vanish unless faded with `PerInstanceFadeAmount` | yes | production; 5.8 adds optional hierarchical CPU instance culling for non-Nanite ISM (`r.SceneCulling.HierarchicalCPUCulling`, off by default) | [V-Epic] Foliage Mode; 5.8 notes via Looman |
| **Authored mesh LODs** (PR #18) | triangle reduction | pop on switch | silhouette loss | yes | production | [V-Epic], [Repo] |
| **Impostor Baker — Upper Hemisphere** | far trees as 8-tri card, view-blended atlas (3 nearest frames) | atlas memory (Epic uses 2048²; 12×12 = 144 frames for distant foliage), pixel shader, optional parallax | atlas resolution vs 4–12 px crowns; view-blend smear under rotation (measure); masked overdraw | single-frame fallback; costlier pixel shader than billboards | documented; Fortnite BR uses hemisphere impostors "for all of our trees when Nanite is disabled" | [V-Epic] |
| **Traditional billboards** (9 views, 8 cards) | cheapest stand-in | 72 tris; worse masked overdraw | card flip/dither in banking | yes | same plugin | [V-Epic] |
| **World Partition HLOD — Instancing** | replaces unloaded cells with lowest-LOD ISMs; "ideal for imposter meshes, such as trees and foliage" | HLOD build, streaming | must match loaded content; Loading Range sets the swap ring | yes | production | [V-Epic] |
| **HLOD Merged / Simplified** | merged proxy per cell | memory per cell | loses canopy grain | yes | production | [V-Epic] |
| **Terrain canopy layer** (material / RVT / data texture) | far forest with zero instances | texture memory + one material's ALU | must match instance statistics at the seam (F10); RVT has no ISM instance culling/LOD | RVT fallback; data-texture route already used in Xinyi | building blocks production; the canopy model is ours | [V-Epic] RVT; [Acad] Bruneton & Neyret; on-screen analogue in AC7 (M-3, [V-Vid]) |
| **Nanite (opaque meshes)** | cluster LOD without authored LODs | Nanite raster, VSM | foliage overdraw/raster cost unknown on target | not all mobile | production for opaque | not measured |
| **Nanite Foliage** (Voxels, Assemblies, Skinning) | distant trees as near-pixel voxels | experimental raster path; VSM needs distant animation off | "use caution when shipping"; non-Nanite fallback merges parts | fallback only | **Experimental** in 5.8 docs | [V-Epic] |
| **PCG distribution** (Electric Dreams PCG forest) | rule-based biome placement | generation cost | sample is "graphically intensive" (RTX 2080 minimum): **distribution reference, not FPS evidence** | — | production framework | [V-Epic] |
| **Z-fields + shader-maps** | consistent forest lighting near→horizon, no popping | precompute; custom shader | research method | — | academic | [Acad] Bruneton & Neyret 2012 |
| **Volumetric textures (texcells)** | canopy as layered volume | fill rate | 2004-era | — | academic | [Acad] Decaudin & Neyret 2004 |
| **Ecology-driven placement** | coherent biome/edge rules | tooling | — | — | Far Cry 5 Houdini pipeline | GDC 2018 |

Nothing here establishes that Nanite helps, impostors win, masked always costs more, or three layers always win.

---

## 9. Northern Taiwan forest morphology

| Aspect | Northern Taiwan target | Source class |
|---|---|---|
| Canopy | closed evergreen broadleaf; from above a **billowy, cauliflower-like surface** of rounded crowns with deep inter-crown shadow | T-02, T-03 [Obs]; confirm with more references |
| Dominants | 紅楠 (mid-slope/ridge), 相思樹 (fine olive, lower hills), 水同木/江某 (valleys), 樟/楠 | [Acad] 文山 survey via PR #15 |
| Value / colour | darker, bluer than temperate pasture landscapes; mix of dark green and bright yellow-green crowns (T-03); far hills blue-grey in humid haze (T-01, T-02) | [Obs] |
| Non-forest vegetation | 芒草 ridge grassland (陽明山), bamboo, tea/terraces, landslide scars, hillside cemeteries | V8 Gov via PR #15; bamboo/cemeteries **[I]** |
| Cuts | roads hugging slopes with canopy closing to the road edge (T-03), power-line towers on ridges (T-04), quarries, golf courses | [Obs], OSM-derivable |
| Interfaces | basin floor ends abruptly at forested hills [Repo]; valley towns with street trees and forested ridges behind (T-02, T-04) | [Repo], [Obs] |

AC7's Mission 2 biome is temperate conifer/pasture; we copy its **morphological rules** (M-1…M-7), not its species,
palette or field pattern.

### 9.1 Northern Taiwan public references (link-only calibration candidates; nothing committed)

| Ref | File (Wikimedia Commons) | Author / date / licence | View | Observations [Obs] |
|---|---|---|---|---|
| T-01 | [Aerial view of Mount Guanyin in New Taipei from the airplane window](https://commons.wikimedia.org/wiki/File:Aerial_view_of_Mount_Guanyin_in_New_Taipei_from_the_airplane_window.jpg) | Ken Marshall, 2014-05-12, CC BY 2.0 | airliner window, altitude unknown (theater band) | whole mountain a dark blue-green mass under haze; settlement band at its foot; no crown detail |
| T-02 | [2018 Aerial View of Xindian District b](https://commons.wikimedia.org/wiki/File:2018_Aerial_View_of_Xindian_District_b.jpg) | Taiwankengo, 2018-05-12, CC BY-SA 4.0 | elevated hillside viewpoint (四十份), near→theater | near broadleaf crowns billowy; mid hills closed canopy with rounded crown texture; valley town; strong haze |
| T-03 | [Beitou Hell Valley 20220623 02](https://commons.wikimedia.org/wiki/File:Beitou_Hell_Valley_20220623_02.jpg) | 臺北旅遊網, 2022-06-23, "Attribution" (check exact terms before any reuse) | drone, near top-down | closed broadleaf canopy, dark green + yellow-green crowns, roads and buildings cut cleanly into it, no ground under canopy |
| T-04 | [Taipei Xiaocheng Station of the Ankeng Line aerial photographs](https://commons.wikimedia.org/wiki/File:Taipei_Xiaocheng_Station_of_the_Ankeng_Line_aerial_photographs.jpg) | 新北市政府捷運工程局, 2023-04-27, "Attribution" (check exact terms) | drone, low oblique | suburban valley, street trees, forested ridges behind, power-line tower on ridge |

Altitude/FOV are unknown for all four, so they inform F1/F5/F6 calibration qualitatively; quantitative thresholds
stay *(cal.)*.

**GIS inputs (data) vs synthetic art choices — keep separate:**

| Input | Role | Status |
|---|---|---|
| MOI 20 m DTM derivative | terrain, slope, aspect → self-shadow, ridge/valley class | [Repo] accepted |
| NLSC land-use survey (OGDL v1.0) | forest / agriculture / built classes | [Repo/PR #15] not ingested |
| ESA WorldCover 10 m (CC BY 4.0), class 10 = tree cover | canopy presence mask | not ingested |
| Meta/WRI 1 m canopy height | height/closure prior | **licence not verified** |
| OSM `landuse=forest`, roads, power lines | cuts and edges | in use for Xinyi ground [Repo] |
| Crown archetype mix, palette, clumping, edge rules, understory colour | art direction | **synthetic** — tuned to references, never presented as data |

---

## 10. Recommended architecture to test (hypothesis, not decision)

```text
            GIS + art rules
                  |
      canopy field (per 500 m tile, e.g. 2-4 m texel):
      cover %, mean crown size, height, archetype weights, edge distance
           |                                   |
   instances (near/mid, up to d_S)       far canopy layer S (beyond d_S)
   + optional mid stand-in               crown-scale noise at the SAME size/cover,
   + understory U under instances        slope/sun self-shadow, ridge/valley value
           \______ dithered crossfade ring at d_S, hysteresis, matched statistics ______/
                                  |
                 atmosphere / fog (existing presets)
```

1. **Single source of truth** — one canopy field drives instances and S (F10).
2. **Understory, not lawn (U)** — dark ground inside the forest mask (F1, F5).
3. **Edges by rule** — outliers and shrub belt near mapped edges; no data-box edges (M-5).
4. **Shadows split by band** — cast shadows where they resolve; far shading in S.
5. **Budgeted transitions** — overlap ring, per-instance fade, F9.
6. **Profiles** — PC/console reference first; mobile separate.

| Band | Candidates |
|---|---|
| near < 150 m | PR #18 opaque LOD0/1 · alpha-masked near-only foliage (C) · Nanite opaque if available |
| mid 150–600 m | PR #18 LOD1/2 · upper-hemisphere impostor · Nanite Foliage (experimental, PC only) |
| far 0.6–2 km | lowest LOD/impostor instances · S · HLOD instancing |
| theater > 2 km | S + atmosphere |

---

## 11. Cost / hypothesis register

| ID | Hypothesis | Phase B test | Kill criterion |
|---|---|---|---|
| H-01 | Canopy coverage, not instance count, drives the "forest" read at ≥ 200 m | B1 coverage factor | F1/F3 unchanged with coverage |
| H-02 | S improves 500/1,000 m passes more than A→B crowns | B1 factorial: S main effect vs N main effect | N effect > S effect on F1–F7 at 500/1,000 m |
| H-03 | Understory U removes the "lawn" read for < 0.1 ms (UHD 770 only) | U toggle in B1 | ΔGPU > 0.3 ms or F5 unchanged |
| H-04 | Hemisphere impostors hold crown identity at 150–600 m better than 20-tri LOD2 at similar cost | N = D vs B, mid band | D loses F2 or costs > B + 20 % |
| H-05 | Masked foliage (C) overdraw is acceptable near-only | overdraw view + GPU by band | — |
| H-06 | Hard cluster culls are the dominant visible pop; per-instance fade fixes it | F9 with/without fade | F9 fails with fade |
| H-07 | Far-band shimmer under rotation is worse than near ghosting at ≥ 500 m | F11 rotation paths | — |
| H-08 | Instance shadows beyond ~600 m cost ms without improving F7 | shadow distance sweep | F7 drops when off |
| H-09 | Statistics-matched S passes F10 at d_S | F10 | ΔL* > 3 persistently |
| H-10 | Streaming/HLOD cost only shows in B2, not B1 | B2 | — |
| H-11 | Nanite Foliage is not shippable for this project in 5.8 | optional PC-only probe | — |
| H-12 | 16 m clump grid periodicity visible from 500–1,000 m | F3 FFT on A | no peak |
| H-13 | Triangles alone don't predict GPU ms here | report tris and ms per arm | — |
| H-14 | UHD 770 ranking differs from a discrete-GPU target | rerun ranking on named dGPU | — |
| H-15 | ~68 % model cover over-/under-states the real Xinyi hill forest | top-down stencil on Xinyi layout copy | — |
| H-AC1…5 | AC7 on-screen hypotheses (§4.2) | owner captures R04/R07/R11 | — |

---

## 12. Phase B specification for Codex (stopped until approval)

Hard boundaries: new standalone maps and content folder only (suggest `/Game/ForestSpike/`); no edits to
`/Game/XinyiLook`, XinyiV2 maps, accepted geometry/terrain, production shaders, tree placement or PR #18 files (B
**copies** PR #18 GLBs, recording SHA-256). Draft PR, no merge. Without a working UE 5.8 + GPU: build the harness,
mark every number **NOT MEASURED**, report the blocker.

**Two separate experiments. Results of one are never reported as the other.**

| | **B1 — near/mid visual + GPU microbenchmark** | **B2 — real flight / streaming stress** |
|---|---|---|
| Question | which near/mid representation and which far layer give the best matched-coverage look per ms | does the chosen combination survive 20 s at 250–400 m/s, cold/warm streaming, boundary transients |
| World | 1 km × 1 km variable core + **shared lightweight ~6 km × 6 km terrain context** (cheap terrain, no instances, identical in every run) | deterministic contiguous **corridor ≥ 6.2 km (250 m/s × 20 s) to ≥ 9.2 km (400 m/s × 20 s) long, ≥ 1.3 km wide plus bank margin (suggest 2 km)**, populated per arm with the same terrain, coverage field, lighting and seeds |
| Camera | stills and short in-core paths with documented active dwell | 20 s straight, banked and dive runs (P1/P2/P8) |
| Gate | starts first, once approved; UHD 770 allowed (labelled) | starts only after B1 results are reviewed **and** a functional UE host is confirmed; only B1-surviving arms enter |
| Output | rubric + indicative GPU/CPU ms | cold vs warm, hitch/stall, streaming bandwidth, transients — not arm visual ranking |

### 12.1 B1 world

- **Core:** 1 km × 1 km; only the factors below vary here.
- **Context:** ~6 km × 6 km terrain around the core, cheap (Landscape or a single low-res mesh, no instances), with
  the **same** material state in every run of a given S level (see §12.2). It exists so far/theater bands are not
  blank; it is **not** proof of horizon coverage. Slant ranges beyond the context extent are labelled **untested**;
  if 1,000 m views need it, add one fixed far-background proxy (same in every run).
- Terrain: deterministic — preferred a hilly window copied from the audited MOI 20 m DTM derivative; fallback seeded
  fBm with documented seed/parameters.
- One fixed canopy field (cover, crown size, archetype weights) from a seed, shared by all arms and by S.
- Lighting: fixed sun (e.g. azimuth 135°, elevation 40°), SkyAtmosphere, SkyLight, height fog, **manual exposure**;
  Lumen state stated and fixed; same AA (TSR or TAA, stated); motion blur off for measurement.

### 12.2 B1 factorial design (review fix: S is an independent factor)

| Factor | Levels | Notes |
|---|---|---|
| **N — near/mid representation** | A: 28-tri Xinyi reference · B: PR #18 archetypes, 3 LODs · C: alpha-masked foliage (self-made or licensed, provenance + texture budget) · D: B near → upper-hemisphere impostor mid (Impostor Baker, 12×12 unless justified) | D's impostor stage belongs to **N**, not to S |
| **S — far canopy layer** | off · on | **identical material, parameters and extent for every N**; covers the forest class in the core beyond `d_S` and in the whole context |
| **Coverage** | 40 / 70 / 90 % top-down target | counts per N computed from measured footprints (§12.4) |
| **U — understory** (optional third factor) | off · on | run on N ∈ {A, B} first to limit runs |

Controls that make the comparison fair:

- **Fixed handover distance `d_S`** (e.g. a value chosen once from §5.1, such as 1.2 km) and a fixed crossfade width
  for **all** N: every N's instances end at `d_S` (with per-instance fade), whether S is on or off. With S off, the
  forest beyond `d_S` is bare context terrain for every N alike.
- Same seeds, positions, canopy field, lighting, exposure, AA, resolution, cameras in every cell.
- Effects reported separately: **N main effect** (S off), **S main effect** (per N), **N × S interaction**, coverage
  effect. Never present the eight N × S cells as one parity-controlled ranking.

Core run set: 4 N × 2 S × 3 coverage = **24 configurations** (+ U on A/B). Tune each N honestly (LOD screen sizes,
fade) within the fixed `d_S`; document where parity is not reached.

### 12.3 B1 camera set (everything stays in the core)

Sizing [Calc]: the core diagonal is 1,414 m; with 300 m margins a straight segment lasts ≤ 6.8 s at 120 m/s,
≤ 3.3 s at 250 m/s, ≤ 2.0 s at 400 m/s. A 9 g level turn at 250 m/s needs r ≈ 712 m (does not fit); 150 m/s at
7 g gives r ≈ 331 m and a **higher** yaw rate (≈ 26°/s vs 20°/s), so B1 reproduces combat **rotation** rates at lower
linear speed.

| ID | Description | Purpose |
|---|---|---|
| V1 | locked stills at 50 / 200 / 500 / 1,000 m AGL, pitches per §5.2, 64 frames each | F1–F8, F10, F11 static; measured band shares from depth |
| V2 | top-down orthographic + 45° stencil/debug passes of the core | F1 VGF (instances via stencil, S via measurement view) |
| V3 | slow dolly 30 m/s at 200 m through `d_S` and each LOD ring | F9, F10 |
| V4 | straight segment 250 m/s, 3 s, along the diagonal at 50 m and at 200 m | near-band translation ghosting, F11 |
| V5 | in-core orbit 150 m/s, r ≈ 330 m (7 g), 360° at 200 m and 500 m | rotation-driven shimmer/pop, F9, F11 |
| V6 | edge pass along a forest/clearing boundary at 150 m, 120 m/s | F4, F8 |

Each path records **active dwell**: the fraction of frames whose camera position and centre-ray ground hit are both
inside the core. GPU/CPU statistics are aggregated over in-core frames only.

### 12.4 Coverage sweep

Target top-down cover **40 / 70 / 90 %** of the forest class. For each N, compute the instance count that reaches
the target from a top-down orthographic stencil render of the core (not from a formula) and report **both** cover
and counts. Reference [Calc, random placement]: 8 m crowns ~10k / 24k / 46k per km²; 12 m crowns ~5k / 11k / 20k.
Issue #19's 2k / 5k / 10k per km² may be run as a secondary sweep, labelled with its measured cover.

### 12.5 B2 corridor and paths (separate, gated)

- Corridor length L ≥ v·T + 2 × 600 m: 6.2 km at 250 m/s × 20 s; 9.2 km at 400 m/s × 20 s (or 7.2 km for 15 s).
  Width ≥ 2 × 600 m × tan(45.7°) ≈ 1.23 km to keep the mid band in content when level; use ~2 km for bank margin.
- P1: 50 m AGL straight, 250 m/s, −5°, 20 s · P2: 200 m, 60° bank turn at 250 m/s (r ≈ 3.7 km for a 2 g
  coordinated 60° bank — lay the corridor along the arc or limit the turn angle) · P8: 400 m/s at 200 m, −10°.
- World Partition streaming with the same grid settings in every arm; cold (first pass after load) and warm runs
  separately; worst stall and its cause.
- Only arms that passed B1 review are built at corridor scale. B2 does not rank visual quality.

### 12.6 Measurements (both experiments; actual engine output only)

- Host: CPU, GPU, VRAM, driver, OS, UE version/changelist, RHI, power plan; confirm no other load (`Get-Process`,
  CPU) and only one UE session (project capture-harness lessons: interleave arms in both orders, min-of-N for small
  deltas). **Label: "UHD 770 only"** unless run on a named discrete GPU. No extrapolation to PS5 / PC dGPU / iPhone.
- Frame: CPU game/render/RHI ms, GPU ms (median, p95, worst), resolution, screen %, AA, shadow method/distance —
  `stat unit`, `stat gpu`, `profilegpu`, an Unreal Insights trace per run.
- Scene: draw calls, visible instances, triangles (`stat rhi`, `stat foliage`, `stat initviews` or 5.8 equivalents),
  GPU memory (`memreport -full` once per configuration), impostor/C texture memory.
- Missing tools → **NOT MEASURED**. No FPS inferred from triangles.

### 12.7 Decision gate output

Per altitude viewpoint: rubric scores (F1–F11) and N, S, coverage effects vs GPU/CPU ms and memory at matched
coverage (B1), plus B2 streaming results for the surviving combination. Native side-by-side sheets. A recommendation
names techniques per band only where both visual and performance evidence support it, with the host label;
otherwise "no winner".

---

## 13. Reproducing this document's numbers

[`scripts/forest_numbers.py`](assets/ac7-forest-benchmark-v0/scripts/forest_numbers.py) — NumPy only; analysis, not
integration code. Run with the project venv:
`python -I docs/research/assets/ac7-forest-benchmark-v0/scripts/forest_numbers.py`.

- Focal `f = 540 / tan(30°) = 935.3 px`; horizontal FOV at 16:9 = 91.5°; size in px = `f · size / range`.
- Band shares (flat ground): per image row, angle below horizon = pitch + `atan(row_offset / f)`; slant `h / sin`.
- Clump cover **model**: see §2.1 (ellipse 0.9 × circumradius, 0.25 m raster, 400 m × 400 m, seeds 11/3).
- Random cover `1 − exp(−N·A)`; gap visibility `exp(−N·(A + 2rD / tan g))`.
- Image speed: translation `f·v·sin(a) / (r·60)`; rotation `f·ω / 60` with `ω = v / r`, `r = v² / (g·√(n²−1))`.
- B1 segment length `(diag − 2·300 m) / v`; B2 corridor `L ≥ v·T + 1,200 m`, `W ≥ 2·600·tan(hFOV/2)`.

Baseline images: [`scripts/annotate_baseline.py`](assets/ac7-forest-benchmark-v0/scripts/annotate_baseline.py)
`<capture.png> <out_dir>` (Pillow). Source capture is under git-ignored `unreal/Saved/`. Output SHA-256: annotated
JPG `7fb2184d…3798`, native crop PNG `2210fc3e…ab41` (re-generated byte-identically).

---

## 14. Open items for the reviewer

1. Accept or adjust the AC7 morphological targets M-1…M-7 drawn from P-01…P-06 as the **initial** AC7 basis
   (thresholds stay *(cal.)*).
2. Accept T-01…T-04 as link-only Northern Taiwan calibration references, or supply better ones (altitude-known).
3. Approve the B1/B2 split, the factorial N × S × coverage design and the fixed `d_S` control.
4. Confirm whether B1 may start on the UHD 770 once approved (labelled), and name a discrete-GPU host for ranking.
5. Optional later: owner captures R04 / R07 / R11.

---

## 15. Sources

AC7 / Bandai Namco / platform analysis

- Bandai Namco Studios, *The Making of 'ACE COMBAT7 SKIES UNKNOWN'* Part 1 — https://www.bandainamcostudios.com/en/behind-the-game/205 ; Part 2 — https://www.bandainamcostudios.com/en/behind-the-game/252
- AUTOMATON, report of UNREAL FEST WEST 2019 talk 「『エースコンバット7』UE4×TrueSkyでの「雲」の表現について」 (2019-09-10) — https://automaton-media.com/devlog/report/20190910-101532/
- UNREAL FEST WEST 2019 — https://unrealengine.jp/unrealfest/west2019/
- Epic, *ACE COMBAT 7 soars high with UE4…* (title only; body 403) — https://www.unrealengine.com/en-US/developer-interviews/ace-combat-7-soars-high-with-ue4-to-become-franchise-s-best-installment
- Wikipedia, *Ace Combat 7: Skies Unknown* — https://en.wikipedia.org/wiki/Ace_Combat_7:_Skies_Unknown
- **Digital Foundry, *Ace Combat 7 – Nintendo Switch DF Tech Review – A Superb, Well-Handled Port* (2024-07-19), video reviewed at 01:24, 01:30** — https://www.youtube.com/watch?v=WznKKwSBeHc
- GoNintendo summary of DF (2024-07-19) — https://gonintendo.com/contents/38100-digital-foundry-offers-a-tech-analysis-of-ace-combat-7-skies-unknown-deluxe-edition ; original (not fetched): https://www.eurogamer.net/digitalfoundry-2024-ace-combat-7-is-one-of-the-most-impressive-switch-ports-weve-ever-tested
- Nintendo Everything (2024-07-19) — https://nintendoeverything.com/ace-combat-7-switch-technical-analysis-frame-rate-and-resolution/
- Nintendo Life (2024-07) — https://www.nintendolife.com/news/2024/07/video-digital-foundry-gives-its-tech-verdict-on-ace-combat-7-for-switch
- **Shuvon Gaming, Mission 2 4K60 Ultra gameplay (2024-05-19), reviewed at 11:00, 12:10, 15:00, 19:00** — https://www.youtube.com/watch?v=2_7h8wQzc18
- **Lord Lucus, Mission 9 PC Ultra 1080p (2019-08-23), sampled 1:30–12:20 (no forest)** — https://www.youtube.com/watch?v=B9ptoZus-4Y
- Digital Foundry 2019 multi-platform videos (located, **not reviewed**) — https://www.youtube.com/watch?v=1iDQEf5CHrU ; https://www.youtube.com/watch?v=Ds5DBeWlm-8
- Steam store page (10 official screenshots checked, no forest frame) — https://store.steampowered.com/app/502500/
- DSOGaming PC view-distance tweak — https://www.dsogaming.com/?p=122369 ; Steam discussion — https://steamcommunity.com/app/502500/discussions/0/1777135944140331772/
- Ace Combat Wiki mission list — https://acecombat.wiki.gg/wiki/Ace_Combat_7:_Skies_Unknown/Missions

Epic Games documentation (UE 5.8 pages, fetched 2026-10-12)

- Impostor Baker — https://dev.epicgames.com/documentation/en-us/unreal-engine/impostor-baker-plugin-in-unreal-engine
- Foliage Mode — https://dev.epicgames.com/documentation/en-us/unreal-engine/foliage-mode-in-unreal-engine
- World Partition HLOD — https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition---hierarchical-level-of-detail-in-unreal-engine
- Electric Dreams — https://dev.epicgames.com/documentation/en-us/unreal-engine/electric-dreams-environment-in-unreal-engine
- Nanite Foliage — https://dev.epicgames.com/documentation/unreal-engine/nanite-foliage?lang=en-US
- Runtime Virtual Texturing — https://dev.epicgames.com/documentation/en-us/unreal-engine/runtime-virtual-texturing-in-unreal-engine
- UE 5.8 release notes — https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes?lang=en-US ; Tom Looman, *UE 5.8 Performance Highlights* — https://tomlooman.com/unreal-engine-5-8-performance-highlights/

Academic / other studios

- E. Bruneton, F. Neyret, *Real-time Realistic Rendering and Lighting of Forests*, CGF 31(2), 2012, doi:10.1111/j.1467-8659.2012.03016.x — https://diglib.eg.org/handle/10.1111/v31i2pp373-382
- P. Decaudin, F. Neyret, *Rendering Forest Scenes in Real-Time*, EGSR 2004 — https://diglib.eg.org/items/3c60ca3a-63b0-4a34-8e07-3bd2908aff7b
- É. Carrier, *Procedural World Generation of Far Cry 5*, GDC 2018 — https://gdcvault.com/play/1025557/Procedural-World-Generation-of-Far

Northern Taiwan references and land cover

- Wikimedia Commons T-01…T-04 (links in §9.1)
- ESA WorldCover 10 m v200 (CC BY 4.0) — https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200
- Meta/WRI canopy height (licence to verify) — https://gee-community-catalog.org/projects/meta_trees/
