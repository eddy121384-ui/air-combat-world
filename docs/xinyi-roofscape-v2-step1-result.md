# Xinyi Roofscape v2 — Step 1: lot-filling roof covers (result)

Status: **visual layer, DAY verified, DUSK inspected.** Plan: `docs/xinyi-roofscape-v2-material-pilot.md` §8 step 1.
Step 0 palette (b69c677) preserved. Building geometry, facades / storefronts, roads, trees, schools, sky, Taipei 101,
terrain and shaders are untouched. No new mesh, material, texture or HISM.

## Verdict

**Keep.** From 150–400 m the old low-rise fabric changes from "a few procedural rooms on grey roof slabs" to rows of
per-lot sheet covers, each a little different in colour and height, with flat concrete roofs (tanks, bulkheads, AC)
still clearly present as the second state. From 650–800 m it becomes a fine lot-scale quilt that separates the old
fabric from the towers; a little busier than before, not noisy or toy-like. Cost ≈ +0.4 … +0.9 ms (≈ +1 %) on the
dev iGPU, mostly cover shadows; instances, HISMs and materials unchanged (see Performance).

## Previous logic (v0 / Step 0)

Per low / walk-up / huaxia roof part (inset 0.8 m): with probability 0.42–0.80 (× 0.45 planned core, × 0.7–1.3
age), the part's largest inscribed rectangle took **1–3 rooms in a row** from one end, covering 30–95 % of the
long axis only; rooms < 2.6 m / 8 m² were skipped. Result: 1,622 old-fabric roof parts with rooms, 2,041 room
instances, i.e. small boxes with large gaps on mostly flat roofs.

## New deterministic cover logic (`tools/lookdev/build_rooftops.py`)

The audit showed the WFS height records are already near lot scale (median roof part 5.4 × 10.5 m) with a long tail
of row polygons (25 % ≥ 10 m deep, 20 % ≥ 20 m long), and surveyed rooftop records are cut out of their parent
parts (0 overlap). So the part itself is the unit, and only rows are subdivided — a geometric heuristic, no parcel
data:

1. **Usable roof:** the part inset 0.35 m (mitre joins; no parapet geometry exists), each piece ≥ 7 m².
2. **Lot cells** in the part's own roof frame (u = long axis of the minimum rotated rectangle):
   * deep parts (≥ 7.5 m) are a row of narrow lots cut **across** the long axis at the archetype frontage
     (walk-up 5.0–7.5 m, low 5.0–8.0 m, huaxia 6.5–10 m; jittered ± ~25 %);
   * parts deeper than 22 m hold back-to-back rows (~13 m each), each cut independently;
   * shallow parts are one long lot, split only every 8–12 m.
3. **State per lot:** SHEET COVER with p = rule (walk-up 0.80, low 0.62, huaxia 0.48) × 0.45 planned core ×
   (0.7 + 0.6 age) × a per-part factor 0.6–1.25; otherwise **FLAT CONCRETE** (existing bulkhead / tank / solar /
   antenna / AC rules run on whatever is left).
4. **Cover = the lot's largest inscribed rectangle** (0.5 m grid) + one lower annex rectangle when the first leaves
   > 28 % of an irregular lot; min side 3.0 m. Reused meshes (gable `addition` 50 %, flat `shed`, `barrel`, open
   `leanto` ≤ 80 m²), ridge along the lot's long axis (random on near-square lots), scaled so the eaves end at 98 %
   of the rectangle (thin seam between lots).
5. **Rhythm:** each covered lot steps 0.2–0.5 m up or down from the previous one (walls 2.3–3.4 m), so equal
   neighbours never merge into one slab; colour drawn per lot from the accepted Step 0 weights, re-drawn (p 0.7) if
   it repeats the previous lot; walls = roof colour 55 % else the Step 0 wall weights.
6. Tanks: 22–30 % of covers carry 1–2 tanks at a ridge end; walk-up covers keep the rare (6 %) second storey.
   Residential towers keep the v0 room path byte-for-byte.

## Affected roof parts and counts

| archetype | roof parts | lot cells | covered lots | roof area under covers |
|---|---|---|---|---|
| walk-up | 1,197 | 3,721 | 72 % | 61.5 % |
| low | 1,067 | 1,960 | 53 % | 46.1 % |
| huaxia | 2,083 | 4,418 | 37 % | 31.0 % |
| low, planned core | 202 | 641 | 22 % | 19.0 % |
| huaxia, planned core | 512 | 1,571 | 14 % | 12.4 % |

Old-fabric roof parts with covers / rooms: 1,622 → 2,812 (walk-up 924, low 741, huaxia 1,147; 5,061 eligible
after the area filters). The shader still paints ~28 % of old flat roofs
as whole sheet roofs, so the visible sheet share of walk-up roofs is ≈ 70 %, close to the Xinyi–Wuxing orthophoto
window (75 %), with flat concrete ≈ 1/3 as the research asks.

| instances | HEAD (Step 0) | Step 1 | Δ |
|---|---|---|---|
| addition | 795 | 2,980 | +2,185 |
| barrel | 415 | 950 | +535 |
| shed | 568 | 1,617 | +1,049 |
| leanto | 263 | 726 | +463 |
| bulkhead | 1,443 | 1,108 | −335 |
| tank | 9,200 | 8,907 | −293 |
| ac | 11,302 | 8,696 | −2,606 |
| antenna | 3,167 | 2,631 | −536 |
| solar | 1,342 | 917 | −425 |
| cooling / machine / bmu / avlight | 507 / 896 / 35 / 471 | unchanged | 0 |
| **total** | **30,404** | **30,441** | **+37** |

Covers displace clutter that used to sit on the now-covered roof area, so the instance count is flat.

## Geometry / draw-call / memory impact

* Instance triangles 800,594 → 812,180 (+11.6 k, +1.4 %). By cull band (covers live to 3.5–4.5 km, clutter to
  0.6–2 km): ≤ 0.9 km −56 k, 0.9–2 km −22 k, **> 2 km +90 k (89 k → 179 k)**. Far covers are 1–3 px; their cost is
  covered by the perf A/B below.
* Draw calls / components: unchanged — same 13 rooftop HISMs, same meshes and props material; no new mesh, texture
  or material.
* Memory: +37 instances (≈ +6 KB instance data); mesh / texture memory unchanged.

## Performance

UHD 770, 1080p, capture harness. Sequential sessions drift by several ms, so cost is measured **in one session**:
both rooftop sets (HEAD Step 0 and Step 1) are built fresh as in-memory HISMs exactly like the level builder and
swapped per state, 6 interleaved rounds in alternating order, 40 timed frames per state. ms per frame:

| view | HEAD roofs (min / median) | Step 1 (min / median) | Δ paired median | Δ paired min | Step 1, cover shadows off | Step 1, covers culled at 2 km |
|---|---|---|---|---|---|---|
| `rp_steep_ne` 330 m | 61.94 / 63.19 | 62.59 / 63.59 | +0.39 | +0.63 | +0.28 / +0.25 | +0.42 / +0.67 |
| `rp_low150` 150 m | 59.90 / 61.48 | 60.82 / 62.00 | +0.60 | +0.56 | −0.03 / +0.21 | +0.41 / +0.53 |
| `roof_ne1` 240 m | 70.86 / 73.15 | 71.22 / 73.06 | +0.88 | +0.41 | +0.68 / +0.51 | +0.58 / +0.30 |
| `roof_mid` 650 m | 71.01 / 72.23 | 71.86 / 73.09 | +0.95 | +0.88 | +0.75 / +0.85 | +0.84 / +0.91 |
| `d_overview_sw` | 68.59 / 71.92 | 69.27 / 71.39 | −0.31 | +0.93 | −0.45 / +0.70 | −0.08 / +0.77 |

(attribution columns: paired median / paired min delta vs HEAD.)

* Step 1 costs **≈ +0.4 … +0.9 ms (≈ +1 %)**, within measurement noise in the overview. That is at or slightly
  above the plan's ≤ +0.5 ms target in 3 of 5 views.
* Most of the near-view cost is **cover shadow casting** (shadows off recovers 0.3–0.6 ms at 150–330 m). Shadows
  are kept: the height steps between neighbouring covers read through them. Lever if mobile profiling needs it:
  cover HISMs `cast_shadow` off in `xinyi_look_build_level.py` (one line, no rebuild of rooftops).
* Shorter cover cull (2 km) buys nothing measurable, so the existing 3.5–4.5 km cull is kept.
* A first in-session run that compared the saved level HISMs to a fresh HEAD set read +0.3 … +1.2 ms median
  (+0.5 … +2.9 ms min); saved-vs-fresh HISMs are not a fair pair, so the table above (both fresh) is the result.
* The swapped-in HEAD set reproduces the HEAD capture to 0–0.33 % changed pixels (capture noise).

## Visual A/B (DAY)

Shots: `rp_low150` (new, 150 m oblique over the Wuxing walk-up rows), `rp_steep_ne` (330 m steep), `rp_top_wuxing`
/ `rp_top_sw` (430 m nadir), `roof_ne1` (240 m oblique), `roof_mid` (650 m), `d_overview_sw`, `f_rooftops_wuxing`,
`e_lowpass_xinyi_rd`, `a_skyline_nw`. Changed pixels 3–29 % (roof shots), sky / mountains 0 %, mean luminance ± 1.

* **150 m / 330 m:** the target read. Walk-up rows are strips of per-lot covers with ridges across the row, neighbours
  differing in colour or height; flat concrete roofs with tanks remain between them. The "three boxes in a row"
  pattern is gone.
* **430 m nadir:** lot rectangles read clearly along rows; large huaxia roofs stay mostly flat with a few covers.
* **650–800 m:** old fabric gets a fine lot-scale quilt; towers / core unchanged. Slightly busier, still calm in
  value (no high-contrast speckle).
* Not too uniform (lots vary 5–10 m, ~1/3 flat, per-part cover density varies); not too dense (instances flat);
  not toy-like (colours are the accepted muted palette, covers are low and matte).
* Remaining: covers are full-storey rooms with walls, which is right for 頂樓加蓋 but means at 150 m a covered row
  reads as "rooms + roofs", not only "roof sheets"; open canopies are the 13–25 % lean-to share.

## DUSK

`roof_ne1`, `rp_low150`, `rp_steep_ne`, `roof_mid`: covers take the low warm light on sun-facing walls and read as
sheet roofs; no black, glowing or flickering surfaces; nothing new at night was needed.

## Determinism and regression

* HEAD builder rebuilt at the start of this pass: identical `rooftop_instances.json`
  (`2d9135ba…`) and identical prop GLBs.
* Step 1 builder run three times (incl. the build loaded into UE): identical `rooftop_instances.json` (`525d8419…`)
  and report; all prop GLBs byte-identical to HEAD (no mesh change).
* Per-building tagged regression (scratch copies of both builders tagging each instance with its building id): all
  5,785 instances on residential towers, offices, podiums and schools are identical HEAD vs Step 1.
* Palette family share of sheet-metal instances, HEAD → Step 1: blue 3.0 → 3.1 %, red 18.2 → 19.9 %, green-grey
  36.4 → 36.4 %, neutral 40.4 → 38.7 %, rust 2.1 → 1.9 % (Step 0 weights unchanged; the small shift comes from the
  no-repeat neighbour rule).
* UE stages: `PASS_LOOK_ASSETS`, `PASS_LOOK_LEVEL` (instance counts match the JSON).

## Image 2.5 roof materials — still worth it?

Mostly **no, not as the planned 6–7 cell pilot.** After Step 1 the main roof read comes from form + palette +
distribution, and the remaining weaknesses are largely shader rules, not missing art:

* **large-scale sheet weathering variation** — not needed now; per-lot colour + height steps already give the
  variation at 150–800 m. The one real sheet issue (ribs / patch strips follow world axes, not the ridge) is a
  shader UV fix, not a texture.
* **aged flat concrete** — the most plausible cell. Flat roofs are now the visible "second state" and read as
  uniform beige with a regular 3 m dot grid of fake equipment; 3–10 m ponding / soot shapes would help at
  150–400 m. Try the procedural route (plan step 2) first; generate `concrete_stained` only if that fails.
* **patched waterproof roof** — low value (≈ 4 % of flat roofs).
* **clean modern membrane** — low value; core / tower roofs are mostly seen from far and already read clean.

Recommendation: plan step 2 (roof-state flag + procedural flat-roof surfaces, fix the dot grid) before any
generation; then, at most, a 1–2 cell pilot (`concrete_stained`, possibly `sheet_ribbed` in ridge space).

## Files

Tracked: `tools/lookdev/build_rooftops.py`, this report. Generated (untracked): `unreal/Saved/XinyiLook/rooftops/*`,
rebuilt `/Game/XinyiLook` assets + level. Evidence: `unreal/Saved/XinyiLook/evidence/roof_lotcover_step1/`
(frames, sheets, crops, perf, regression, harness incl. the in-session HEAD-roof swap).
