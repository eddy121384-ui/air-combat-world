# Xinyi Roofscape v2 — Step 2: procedural roof surfaces (result)

Status: **shader + one custom-data float; DAY verified, DUSK inspected.** Plan: `docs/xinyi-roofscape-v2-material-pilot.md`
§8. Step 0 palette and Step 1 lot-cover geometry untouched: `rooftop_instances.json` is byte-identical
(`525d8419…`, rebuilt twice), all 16 prop GLBs byte-identical, builder `build_rooftops.py` not changed.
No new texture, material, mesh, HISM or draw call.

## A. Sheet rhythm now follows each cover

**Cause.** `xc_prop` drew seams as `frac((wpos.x + wpos.y) / 0.19)` and `xc_sheet_weather` cut the re-roofed patch strips
on `floor((p.x + p.y) / 0.9), floor((p.x - p.y) / 2.4)` — a fixed 45° world diagonal, whatever the cover's yaw. (The 0.19 m
ribs were also effectively invisible past ~150 m.)

**Now.** Covers (`shed`, `addition`, `barrel`, `leanto`) carry their ridge yaw as per-instance custom data 1,
`(ENU yaw mod 180) / 180`, written by the level builder from the existing `yaw` field (no instance-JSON change; 4 B per
cover, ~35 KB total). `xc_prop` builds a ridge frame from it (`ru = (cos yaw, -sin yaw)` in UE world xy) and uses it for
(a) broad seams every 0.7 m across the ridge, so they run down the slope, fading by ~400 m, and (b) the patch strips.
`xc_sheet_weather` takes the strip coordinates as a parameter; painted whole-roof sheets and rooftop-record walls pass the
old diagonal frame, so they are unchanged. The material gets one extra `PerInstanceCustomData` node.

## B. Flat concrete

In `xc_roof` (tile roofs), flat concrete only (not sheet roofs or office membrane):
* a few large resurfacing / repair patches: 11 m cells in a per-building rotated frame, about 1 cell in 4 holds one
  rectangle of 40–70 % of the cell, lighter (+14 %) or darker (−16 %), faded with `xc_detail(fwp, 9)`;
* one broad 7 m stain (≤ 16 % darkening, weathering-scaled);
* the fake-equipment grid is now 4 m, rotated per building, 12 % occupancy (was 3 m, world-aligned, 38 %) with smaller
  boxes. Real tank / AC props are unchanged.

No cracks, moss, speckle or high-frequency detail.

## Visual A/B (Step 1 vs Step 2, DAY + DUSK)

Changed pixels 0.1–6 % (largest at 150 m), sky / mountains 0 %, mean luminance −0.1…−0.7.
* **150 m:** covers show seams running down their own slopes; flat roofs lose the white dot grid and show a few soft
  large patches. Clearly better than world-diagonal stripes.
* **300–330 m:** subtle — faint seam rhythm on covers, calmer flat roofs.
* **650–800 m:** essentially unchanged by design (details dissolve); no new noise or shimmer.
* **DUSK (`rp_low150`, `roof_ne1`, `rp_steep_ne`, `roof_mid`):** no regression.

## C. Cover shadows

Same-session interleaved A/B on the level's own HISMs; Step 1 and Step 2 materials built fresh together; cover
shadow variants set in memory. 6 and 12 alternating rounds, 40 timed frames each, UHD 770 1080p.

| variant | what it does | result |
|---|---|---|
| `noshadow` | no cover shadows | −0.1 … −0.7 ms vs Step 2 (noisy); visibly flatter lot rows (the dark roof-to-wall edge between height steps is lost) |
| `flatoff` | no shadow from `shed` + `leanto` | −0.3 … +0.1 ms; indistinguishable from noise; picture unchanged |
| `far0` | `cast_far_shadow` off | +0.5 … +1.3 ms (worse / noise) |
| `gableonly` | only `addition` casts | +0.4 … +2.2 ms (worse / noise) |

`cast_far_shadow` / per-type switches are the only per-component distance-style shadow controls on the CSM path in use
(`r.Shadow.Virtual.Enable = 0`); none produced a gain clearly outside the ±0.5 ms same-session noise except full
removal, which costs the lot-height read. **Decision: keep the Step 1 cover shadows.** No shadow change shipped.

## Frame time, Step 1 vs Step 2 surfaces

Same-session paired median delta (ms): `rp_steep_ne` +0.16/+0.21, `rp_low150` +0.39, `roof_ne1` +0.29/+0.69,
`roof_mid` +0.61 (min-based deltas −0.6 … +0.6). Net ≈ +0.2 … +0.6 ms, i.e. roughly cost-neutral to slightly above
(~0.5 %); the first-shot low-altitude result of the second pass (+9.8 ms for Step 1) was a not-yet-warm A state and is
discarded (first pass: +0.4 ms).

Counts: instances 30,441, instance triangles 812,180, 13 rooftop HISMs, materials / draw calls: unchanged. Memory
≈ +35 KB (second custom float on 6,273 covers).

## Regression

Step 0 palette weights, Step 1 geometry, prop meshes, tile meshes, facade / storefront, roads, trees, schools, far city:
no change in code or generated data (only `xc_roof`, `xc_prop`, `xc_sheet_weather` differ). Deterministic rebuild
confirmed. UE `PASS_LOOK_ASSETS` / `PASS_LOOK_LEVEL`.

## Image 2.5 roof materials

**No longer recommended.** After Step 2 the 150–800 m read is carried by form, palette and distribution, and the two
procedural issues are fixed. What remains (flat roofs are plain, patches subtle) is intentional restraint, not missing art.
Revisit only if a later pass shows flat concrete at 150–300 m still reads as an untextured plate in flight, not in stills.

## Files

`tools/lookdev/shaders/xinyi_city.hlsl`, `tools/lookdev/ue_custom_code.py`,
`adapters/unreal/lookdev/xinyi_look_build_assets.py`, `adapters/unreal/lookdev/xinyi_look_build_level.py`, this report.
Evidence (untracked): `unreal/Saved/XinyiLook/evidence/roof_surface_step2/`.
