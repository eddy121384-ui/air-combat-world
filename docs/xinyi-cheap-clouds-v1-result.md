# Xinyi Cheap Cloud Renderer v1 — far field, cheap shadows, proxy scaling (EXPERIMENTAL)

Status: **experimental, opt-in only** (`-Clouds cheap`). Clouds stay OFF by default; HIGH / LOW profiles,
the cloud state and the saved look level are unchanged. Builds on `docs/xinyi-cheap-clouds-v0-result.md`.

Scope of this pass, and only this: (1) far-field cloud mass, (2) cheap cloud shadows, (3) proxy / object
scaling. Near-cloud shapes, cloud entry, night glow and the global translucency setting are untouched.

## Verdict

**Worth keeping.** The far field no longer reads as an army of small round / mushroom towers; it reads as
broad, merged, flat-based weather masses with occasional domes, and covers the far ring far better.
Broad soft cloud shadows now exist on terrain and city for ~1 ms. Motion stays pop-free, cloud entry is
unchanged. The cost rose by ~0.5–2.5 ms over v0 (same session), landing at **+3.6 … +7.6 ms** over OFF on
the UHD 770 — still about half of LOW (+10 … +18 ms) and ~1/60 of HIGH, but two difficult views exceed
the ~6 ms soft ceiling (as v0 already did in this session's runs, see below).

Overall (my judgement from the side-by-side sheets, not a metric): far field from ~60–65 % of HIGH to
~75 %; whole-image ~70 % of HIGH. HIGH's remaining advantages: thin cloudlet field at the cloud base,
haze / translucency of distant clouds, sky-light cloud AO, much richer near-field silhouettes.

## 1. Far field

### Root cause (measured)

Cells were ray-cast into the review cameras and compared with what each renderer draws
(`cellmask.py` / `cov.py` in the evidence harness):

* v0 drew its cells faithfully out to ~30 km (15–30 km: 58–81 % of the cell footprint vs HIGH 64–83 %),
  but beyond 30 km only **5–42 %** (HIGH 57–79 %): the v0 alpha fade 38 → 46 km and 49 km cull.
* every v0 cell is a separate round puff with a crown at the cell top: at 20–50 km they read as many
  separate vertical "mushroom / cauliflower" objects; HIGH's dome threshold + domain warp merges
  neighbours into wider, flatter masses with lower effective tops.
* about half of HIGH's cloud pixels lie **outside any cell** (high basin 54 %, Elephant 50 %, skyline
  32 %): HIGH's coverage noise grows thin flat cloudlets at the base of the layer everywhere. That is
  HIGH's interpretation of the weather map, not the cloud state.

### Strategy: a second, cluster-level representation of the same cells

`build_cloud_cheap.py` now derives, besides the per-cell impostors (unchanged shapes), **far cluster
impostors** from the same `clouds_v0.cells.json` — no new placement:

* single-linkage grouping of neighbouring cells (rims < 1.5 km apart, 64 km wrap), split along the
  principal axis to ≤ 8 cells / ≤ 7.5 km extent; broken patches grouped separately. 354 cells →
  68 clusters (mean 5.2 cells, 4 broken). Every cell is owned by exactly one cluster (fails closed).
* far grammar per cluster (≤ 8 lobes): one broad, flattened lobe per cell, wider than the cell
  (×1.15–1.35), top at 0.72–0.92 of the cell top, pulled toward its neighbours (merged mass); a separate
  broad turret only on tall, narrow cells (h > 1.5 r — 13 tower lobes in 68 clusters); remaining lobes
  are thick flat decks on the shortest neighbour links (shared ragged base), or offset satellites for a
  lone cell (never a single round dome).
* per-lobe vertical squash (packed into the radius fraction of the custom primitive data), an extra
  ~2.4 km erosion octave for far proxies (ragged, asymmetric outlines), lighting height normalised to
  the local lobe tops, a sun-direction-aware far lighting approximation, higher multiple-scattering
  floor and lighter bases for far decks (no grey slabs / dark seams).
* **hand-over by camera distance in optical depth**: near cells full to 12 km, far clusters full from
  22 km (near τ × (1 − w), far τ × w — the summed transmittance interpolates continuously); far
  clusters fade 50 → 60 km. The engine culls each proxy just outside its zero-weight edge
  (near `LDMaxDrawDistance` 22.6 km; far `MinDrawDistance` 11.4 km / max 60.6 km).

Rejected / not done: uniformly larger clouds; a noise-born cloudlet layer to imitate HIGH's off-cell
cloudlets (that would be a second placement system).

### Result (DAY, same frames as the timing session)

| 30–60 km cell footprint drawn | skyline | Elephant | high basin | low Xinyi |
|---|---|---|---|---|
| CHEAP v0 | 23 % | 5 % | 27 % | 42 % |
| **CHEAP v1** | **65 %** | **28 %** | **39 %** | **93 %** |
| HIGH | 70 % | 57 % | 68 % | 79 % |

Share of HIGH's cloud pixels also covered: v0 27–54 % → v1 32–62 %. Visually (sheets): Elephant shows
broad flat-based cumulus close to HIGH instead of cauliflower stacks; high basin / transit show merged
horizon masses instead of mushroom rows; at grazing angles from low altitude far decks stack into thin
horizontal layers (HIGH shows similar striation).

## 2. Cheap cloud shadows

* offline: the near lobes' optical depth integrated over three height bands (1250–1750, 1750–2400,
  2400–3400 m), Gaussian-softened (90 m), tileable 1024² RGBA8 over the 64 km tile (62.5 m texels).
* runtime: `M_XinyiCloudShadow_Cheap`, a **sun light function**: each band is sampled where the sun ray
  from the shaded point crosses the band's middle (3 bilinear fetches), so low suns stretch shadows
  along the azimuth. World-anchored and static with the cloud state: no swimming, no popping.
  Set on the sun only in the cheap process (fade distance 100 km, disabled brightness 1). Strength
  DAY 0.8 / DUSK 0.6 / NIGHT 0.4. Works with the project's light-function atlas setting unchanged.
* quality: broad, soft shadows beside their clouds on the eastern hills and on Yangmingshan under the
  northern deck; the city stays readable. Most review cameras look down-sun, where shadows hide behind
  their clouds, so two shadow-review cameras (looking across the sun azimuth) were added to the harness.
  Shadows follow the cells (round-ish footprints), not HIGH's extra cloudlets, so the basin floor gets far
  fewer shadow patches than in HIGH; no sky-light cloud AO (HIGH darkens the whole terrain).
* cost: **~1 ms** (same-session pairs +0.1 … +2.0 ms; at the noise floor).

## 3. Proxy / object scaling — measured

Fixed-cost probes (same session, ms over OFF, move phase):

| | skyline | low Xinyi | inside | Elephant | high basin | approach |
|---|---|---|---|---|---|---|
| translucency 25 % setting only | +0.1…0.5 | +0.3 | +0.4…0.8 | +0.2…0.8 | +0.2 | +0.1…0.4 |
| v1, proxies hidden (setting + shadow) | +1.9 | +2.0 | +1.1 | +2.0 | +1.7 | +1.3 |
| v1, proxies drawn at ~0 px | +2.9 | +3.4 | +3.3 | +3.1 | +4.0 | +2.8 |
| v1 full (timing session) | +6.3 | +4.8 | +6.6 | +3.8 | +3.6 | +7.6 |

Findings:

* at 25 % resolution **most of the CHEAP cost is fixed**, not cloud pixel shading: drawing the proxies
  at all (translucent draws + the separate-translucency pass doing work) costs ~+1.5 … +2 ms on top of
  the setting / shadow, and v0's "empty proxy" run cost +3.6 … +5 ms of its +2 … +7 ms total.
* hidden / culled proxies cost ≈ nothing: actor count is not the problem; **drawn** primitives are.
* v1 draws fewer proxies despite a longer range (frustum + distance, per view): v0 29–217 → v1 31–95
  (near 10–52 + far 21–51). Actors: v0 670 → v1 751 (447 near within 42 km, 304 far within 76 km).

Next scaling step (not built): camera-centred streaming — spawn / pool near-cell proxies only within
~25 km of the camera and cluster proxies to ~62 km. For a 100 × 100 km AOI at this cloud density that
is ~170 near + ~200 far actors regardless of AOI size. ISM / HISM batching is **not** a drop-in: the
translucency sort is per primitive, so instances inside one component would composite in index order
(wrong over-blending where clusters overlap); the cluster impostor already is the order-independent
batch. A further step would be a far ring of "region" impostors (several clusters per proxy).

## Performance — UHD 770, 1080p, continuous 30 Hz flight test

Interleaved fresh processes, 3 rounds, median of per-run move medians, Δ vs OFF in the same session
(this session ran 1–3 ms slower overall than the v0 session, so v0 is re-measured here):

| ms over OFF (move) | skyline | low Xinyi | inside layer | Elephant | high basin | approach |
|---|---|---|---|---|---|---|
| CHEAP v0 (this session) | +3.8 | +2.8 | +5.1 | +3.3 | +2.1 | +6.9 |
| **CHEAP v1** | **+6.3** | **+4.8** | **+6.6** | **+3.8** | **+3.6** | **+7.6** |
| CHEAP v0 (v0 session) | +2.6 | +4.3 | +2.5 | +2.8 | +4.2 | +4.3 |
| LOW (v0 session) | +12.5 | +13.9 | +16.3 | +13.6 | +16.1 | +17.6 |
| HIGH (v0 session, 1 run) | +252 | +326 | +378 | +283 | +357 | +433 |

v1 − v0 (same session): +2.5 / +2.0 / +1.5 / +0.5 / +1.5 / +0.7 ms, of which ~1 ms is the shadow.
DUSK single runs (not interleaved): v1 +3.0 … +7.1 ms, v0 +0.6 … +4.3 ms over OFF. The NIGHT OFF run was
disturbed (skyline 79 ms), so no night delta is reported.

## Motion

* 30 Hz fly-bys (all six review segments): consecutive-frame pop detector — no spikes; v1 per-frame
  change equal to or slightly below v0 (e.g. high basin median 0.66 vs 0.76).
* new transit segments (900 + 600 frames at 300–340 m/s, crossing the 12–22 km hand-over band and the
  50–60 km fade for every cluster ahead): no spikes (median 0.35 / 0.48, v0 0.40 / 0.52).
* grain / flicker unchanged from v0 (grain 3.6–5.3, static flicker ~4.7 ×1000; LOW 11–19, HIGH 19–47).
* cloud entry / inside-cloud mist: identical to v0 (near cells unchanged).
* shadows are world-anchored: no swimming or popping.

## Comparison summary (DAY)

| | OFF | CHEAP v0 | CHEAP v1 | LOW | HIGH |
|---|---|---|---|---|---|
| far silhouette | – | round puffs / mushrooms | broad merged flat-based masses | HIGH shapes, softened | reference |
| far coverage | – | weak beyond 30 km | good to 60 km | high | reference |
| shadows | – | none | broad soft, ~1 ms | softened | strong + sky AO |
| motion stability | – | best | best | good | grainy |
| cost (ms) | 0 | +2 … +7 | +3.6 … +7.6 | +10 … +18 | +250 … +430 |

## Remaining weaknesses

1. HIGH's thin cloudlet field at the cloud base (≈ half of HIGH's cloud pixels in high views) has no
   CHEAP equivalent; far clouds are also less hazy / more opaque than HIGH's.
2. Near cells (< 12 km) keep the v0 grammar: from above they still read as grape bunches / snowmen, and
   the dark "eye" self-shadow spots remain (pre-existing v0 artifact).
3. Far decks seen edge-on from low altitude stack into thin horizontal layers.
4. Two difficult views exceed the ~6 ms soft ceiling (approach +7.6, inside +6.6); fixed overhead
   (drawn translucent proxies + translucency pass) dominates.
5. Shadows follow the round-ish cell footprints; no sky-light cloud occlusion.
6. Unchanged from v0: last ~300 m before entry, weak night city glow, global 25 % translucency setting.

## Regression

Asset stage `PASS_LOOK_ASSETS` (`M_XinyiClouds_Cheap` now 1526 PS instructions, v0 1324; plus
`M_XinyiCloudShadow_Cheap`, `T_XinyiCloudShadow`), level stage `PASS_LOOK_LEVEL` (nothing cheap is
saved in the level; the light function is set only in the cheap capture process). Accepted 8-shot
suite, clouds OFF, DAY / DUSK / NIGHT vs the baseline frames: same result as the v0 regression — all
shots identical or within sub-visible AA speckle (skyline ≤ 0.26 % of pixels > 8 levels, two DUSK shots
≤ 0.31 %, the rest 0). LOW DAY: elephant / low-pass / overview / rooftops identical, skyline differs only
in its unconverged dither grain (as before); alt-basin differed on the first capture after the full
asset rebuild (temporal reconstruction not converged) and was pixel-identical to the baseline on
re-capture. HIGH / LOW code paths, parameters and the clouds-OFF default are untouched
(`xinyi_look_clouds.py` unchanged). Details: evidence `timing/regression.txt`.

## Files

Tracked: `tools/lookdev/clouds/build_cloud_cheap.py`, `tools/lookdev/shaders/xinyi_clouds_cheap.hlsl`,
`tools/lookdev/ue_custom_code.py`, `adapters/unreal/lookdev/xinyi_look_clouds_cheap.py`, this report.
Generated (untracked): `/Game/XinyiLook/Materials/M_XinyiClouds_Cheap` (rebuilt),
`M_XinyiCloudShadow_Cheap`, `/Game/XinyiLook/Textures/T_XinyiCloudShadow`,
`unreal/Saved/XinyiLook/clouds/cheap/*` (incl. `cloud_cheap_shadow_1024.png`).
Evidence: `unreal/Saved/XinyiLook/evidence/cheap_clouds_v1/` (sheets, MP4s, frames, timing, metrics,
harness copy).
