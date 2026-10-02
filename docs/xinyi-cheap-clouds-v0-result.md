# Xinyi Cheap Cloud Renderer v0 — feasibility result (EXPERIMENTAL)

Status: **feasibility prototype, opt-in only** (`-Clouds cheap`). Clouds stay OFF by default; the
volumetric HIGH / LOW profiles, the cloud state and the saved look level are unchanged.

Question: can a non-volumetric renderer reach roughly 70–80 % of HIGH's perceived quality / scale at a
small fraction of the GPU cost on the Intel UHD 770?

Answer: **partly yes.** At aircraft distances of ~1–10 km it is convincing and cleaner than LOW
(no ray-march grain), cloud entry is a usable intentional transition, and it costs **+2.5 … +4.3 ms**
at 1080p over clouds OFF (LOW: +12.5 … +17.6 ms). It does **not** reach 70–80 % of HIGH at long range
(smaller, rounder, more uniform clouds, no cloud shadows, broken layer barely visible). Worth keeping
as the weak-GPU / mobile candidate; not a HIGH replacement.

## Technique: analytic lobe impostors (not cards)

Billboard cards / crossed planes were rejected up front because they rotate, pop and sort per sprite.
Instead each cloud cell is **one translucent proxy box** whose pixel shader intersects the view ray
analytically with up to 8 ellipsoid "lobes" (closed-form chord integral of a `(1 - r²)²` density):

- rotation-invariant and true-parallax: no billboard swing or crossed-card geometry by construction;
- optical depth is a sum → **order-independent inside a cell** (no intra-cloud sorting); cells are
  separate primitives so the engine's per-primitive translucency sort orders them;
- chords are clipped by the cell base plane (flat cumulus bases, noise-jittered) and by the opaque
  **scene depth** (soft intersection with terrain / buildings, depth test disabled on the material);
- the proxy box is **inward-facing**: only its far side rasterises, once per pixel, also with the camera
  inside the box — so the same primitive keeps working when flying into the cloud;
- world-anchored 3D texture noise (iq lattice trick, 256² RGBA) erodes the outer lobe shell only
  (`E·min(h², 1)`), 2–4 octaves by distance; nothing swims with the camera;
- rendered in the separate (after-DOF) translucency pass at **25 % resolution**
  (`r.SeparateTranslucencyScreenPercentage 25`, cheap capture process only; the impostors are the only
  translucency in the look scene).

Files: `tools/lookdev/shaders/xinyi_clouds_cheap.hlsl`, `tools/lookdev/clouds/build_cloud_cheap.py`,
`adapters/unreal/lookdev/xinyi_look_clouds_cheap.py`.

## Architecture / Cloud State reuse

```text
cloud_state_v0.json --build_clouds.py--> clouds_v0.cells.json + weather map   (unchanged)
                                  |            |
            HIGH / LOW volumetric <- weather map |
                                               +--build_cloud_cheap.py--> clouds_v0.cheap.json (CHEAP only)
```

`build_cloud_cheap.py` reads the existing 354 cells (336 cumulus, 18 broken) and derives only renderer
detail: per-cell lobe layout seeded from `[state seed, cell index]` (core lobe, flat-cut skirt lobes,
an overlapping leaning tower whose crown reaches the cell's `top_m`; flattened lobes for broken
patches), plus 64 km wrap copies within 52 km of Xinyi (670 instances). Placement, radius, base and top
are the state's; gameplay should keep querying the cells, never the lobes. Per instance the 36
custom-primitive-data floats carry 8 lobes + base z + squash + seed + bounding radius.

`apply_clouds(..., "cheap", tod)` sets the volumetric actor exactly as OFF, then spawns the impostors
transiently in the capture process; nothing is saved into `L_XinyiLook_Hero`.

## Distance / inside strategy (one representation, continuous LOD — no switches, no popping)

| range | treatment |
|---|---|
| near (< ~3.5 km) | density ×2.5 below 1.5 km easing to ×1 at 9.5 km (narrow edge band, crisp billows), 4 noise octaves, billow self-shadow (noise step toward sun) |
| mid (≤ 18 km) | 3 octaves, smooth-union lobe normal, analytic sun transmittance through the lobes |
| far (18–46 km) | normal fades to "up", sun pass fades to a height-based approximation (22–30 km), fine octaves off |
| fade | alpha fades 38 → 46 km; proxies culled at 49 km |
| inside | chord starts at the camera (dense lit mist) + **local fog**: lobe density *at the camera* blends in a uniform diffuse mist so lobe structure dissolves; multiple-scattering floor rises to 0.6 inside |

Consecutive-frame pop detector on the 30 Hz fly-bys: no spikes in any segment (skyline, low Xinyi,
inside layer, Elephant Mountain, high basin); the approach segment rises smoothly through entry.

## Lighting (no volumetric lighting)

Sun direction and atmosphere-filtered sun illuminance from `SkyAtmosphereLightDirection /
LightIlluminance`, ambient from `SkyLightEnvMapSample` (up / down) — so DAY / DUSK / NIGHT follow the
accepted rig. Analytic sun transmittance through the cell's lobes (self-shadow) with a
multiple-scattering floor; dual-lobe HG phase on thin parts (silver lining); smooth-union lobe normal
(wrap term); vertical gradient (darker bases); one-step noise derivative toward the sun for billow
self-shadowing; per-cell ±5 % albedo. Per-ToD: dusk uses a low MS floor + doubled sky fill (same
"orange cotton ball" fix as the volumetric renderer); night adds a weak warm city glow on bases.

## Measured cost — UHD 770, 1080p, continuous 30 Hz flight test

Same method as the LOW pass (SceneCapture2D with persistent history, every frame GPU-synchronised by a
1-px readback; move-phase median of 150 frames, 240 for approach), runs **interleaved** in fresh
processes (3 rounds, median of per-run medians), Δ vs OFF in the same session:

| ms over OFF (move) | skyline | low Xinyi | inside layer | Elephant | high basin | approach |
|---|---|---|---|---|---|---|
| **CHEAP (25 % res)** | **+2.6** | **+4.3** | **+2.5** | **+2.8** | **+4.2** | **+4.3** |
| CHEAP (50 % res) | +7.0 | +5.3 | +8.5 | +5.0 | +5.9 | +13.1 |
| LOW | +12.5 | +13.9 | +16.3 | +13.6 | +16.1 | +17.6 |
| HIGH (1 run) | +252 | +326 | +378 | +283 | +357 | +433 |

Resolution probe (one run each): 100 % +4 … +39 ms, 50 % +4 … +13, 25 % +1.3 … +5.9 → mostly pixel-
shading bound plus ~2–3 ms fixed (≈670 proxy primitives / translucency pass).

Image stability (static s59→s60 flicker inside the HIGH cloud mask, ×1000): CHEAP 4.5–4.8, LOW 11–19,
HIGH 19–47. CHEAP does not darken the city (no cloud shadows).

## Assessment

| | CHEAP vs HIGH |
|---|---|
| silhouette | good at 1–10 km (cauliflower tops, flat bases); far clouds smaller / rounder / more uniform |
| depth | true parallax, correct terrain / building intersection; good |
| lighting | sunlit tops, cool shaded bodies, silver lining; dusk good; a bit uniformly cream at day |
| repetition | no stamps (every cell's lobes unique), but the far field reads as many similar puffs |
| billboard artifacts | none by construction |
| transitions | no popping; cloud entry → mist is continuous and reads intentional |
| motion stability | best of the three (no ray-march noise) |
| performance | ~1/4 of LOW, ~1/100 of HIGH |

Overall: roughly HIGH-class at mid range, clearly below HIGH at long range → ~60–70 % overall.

## Biggest weaknesses

1. Far field: clouds smaller and rounder than HIGH's (cheap coverage ≈ 40–60 % of HIGH's on screen) —
   HIGH's domain-warped weather map spreads clouds wider than the cell radii.
2. No cloud shadows on the city / basin (the largest realism gap in high views).
3. Broken stratocumulus layer barely reads (flattened lobes).
4. Last ~300 m before entry a near lobe can still read as a round shape; faint lobe arcs mid-entry.
5. 25 % translucency resolution is a global setting; any future translucency shares it.
6. Night: city-glow under-lighting weak, slightly moon-blue.
7. ~670 primitives (one per cell) — fine here, needs merging / instancing for wider Taipei.

## Regression (existing paths)

Asset stage (now also building `M_XinyiClouds_Cheap`, 1324 PS instructions incl. translucency
overhead; `T_XinyiCloudNoise`; proxy box) `PASS_LOOK_ASSETS`, level stage `PASS_LOOK_LEVEL` (nothing
cheap is saved in the level). Accepted 8-shot suite, clouds OFF, DAY / DUSK / NIGHT vs the pre-pass
frames: 19 / 24 pixel-identical, 5 within sub-visible AA speckle (skyline: 0.2 % of pixels > 8 levels,
isolated) — the same result the cloud-v0 pass recorded. LOW: alt-basin / low-Xinyi identical; skyline
differs only in its not-yet-converged dither grain. HIGH / LOW code paths and parameters untouched.

## Evidence (generated, untracked)

`unreal/Saved/XinyiLook/evidence/cheap_clouds_v0/`: comparison sheets, DAY/DUSK/NIGHT captures, MP4
fly-bys, timing JSON per run, metrics, flight-test harness copy.
