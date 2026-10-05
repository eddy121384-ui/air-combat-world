# Xinyi Street & Facade Identity v0A — Phase A: frontage-aware facade core

Status: **engineering validated, visual review done, not committed** on `feat/opus55-xinyi-visual-quality`, built on
HEAD `c8e086b`. Look-dev layer only: no accepted geometry, terrain, Taipei 101, cloud, school or rooftop change; the
accepted triangle soup of all 25 tiles stays bit-identical (fail-closed check in `build_look_tiles.py`).

Inputs: `docs/xinyi-urban-identity-engineering-plan.md` (§2, §4.1, §6, §11.2) and its frontage rules
(`build_urban_identity.build_frontage`, `acw.frontage/0`). No new GIS: the same rules, run on the in-memory records.

## 1. How frontage reaches the renderer

`build_look_tiles.py` runs `build_frontage` on the records it has just classified (so archetypes / school membership
are never stale — the stored `frontage.json.gz` depends on the previous `look_buildings.jsonl.gz`), derives one
**frontage role per ring edge**, matches every wall triangle to its ring edge geometrically and packs the role into
**flag bits 4-6** of `TEXCOORD_2.A`. No new vertex channel, no new material input, no new texture.

| role | value | meaning |
|---|---|---|
| none | 0 | no frontage contract: roofs / soffits, rooftop-structure records, schools (bit4 keeps its corridor meaning), and every mesh outside the 25 tiles (far city, landmarks). The shader reduces exactly to the accepted grammar |
| rear | 1 | wall with no street frontage (rear, side, party wall, courtyard) |
| alley | 2 | faces only a `service` way (alley / parking aisle) |
| street / street_major | 3 / 4 | faces a local / collector-or-arterial road, building is not a commercial frontage |
| commercial_side | 5 | commercial building, secondary frontage on a metadata **corner** (side street) |
| commercial / commercial_major | 6 / 7 | commercial building, primary frontage on a local / major road |

* Commercial = `commercial_candidate` of the metadata (low / walk-up / huaxia / podium, best class ≥ local,
  ≥ 6 m frontage). Primary = its highest-class street edge plus every street edge within 50° bearing of it; other
  street edges become `commercial_side` only on metadata corners, otherwise a plain street wall (controlled
  secondary frontage, no invented corners).
* Matching: wall-triangle normal within 15° of the edge normal, plane within 0.5 m of the edge line, extent midpoint
  on the edge (±0.25 m). **99.96 %** of 108.4 km non-school frontage lands on wall triangles, 0 edges mostly
  unmatched; the build **fails closed below 99.5 %**. (School frontage, 185 edges, is intentionally not baked.)
* Max flags value 117 < 248 (hero tag). Welded vertex count unchanged (991,557): roles are constant per wall plane.
* Audit: `unreal/Saved/XinyiLook/urban_identity/frontage_bake.json` (+ `frontage` block in `look_tiles.report.json`).
* Deterministic: two rebuilds give the same tile-set hash (`734d0b82…`).

Counts (non-school): 5,770 buildings with frontage, 2,181 commercial candidates, 1,744 corners; frontage edges
alley 8,512 · street 1,759 · street_major 975 · commercial_side 1,733 · commercial 3,672 · commercial_major 1,037.
Wall area by role is in the audit (e.g. walk-up: 132 k m² commercial, 27 k major, 55 k corner side, 848 k rear).

## 2. Facade behaviours that became frontage-aware (`xc_wall` only)

| behaviour | before (HEAD) | now |
|---|---|---|
| 騎樓 arcade / shopfront ground floor | every side of every old building | commercial frontage only (primary + corner side); a tiled pier at each bay line, faintly lit interior, fewer closed shutters on the primary front |
| sign band | every side, 65 % of cells | by role: major commercial 78 % (taller board, 0.70 floor), commercial 65 %, corner side 40 %, plain street 15 %, alley 8 %, rear 0 %; huaxia one step weaker |
| sign boards (near only) | random pixel blobs | one row of character blocks with word gaps, text contrasting with the board colour, dark board edge (Phase B replaces this with the atlas) |
| quiet ground floor (old stock, rear / alley / residential street) | shopfront | street / alley: scooter-garage roll-ups and steel doors; rear / side: small high barred windows, rare back door; darker tiled plinth; area-weighted mean at range |
| AC condensers | random per window | street / alley walls: fixed columns (same side, a few floors skipped); rear: unorganised scatter at 70 % |
| iron window cages | every side alike | rear / side walls ×0.8 |
| humid weathering | uniform | rear / side / alley walls +18 % grime, stronger green-grey cast |
| podium LED panels (night) | every side | street-facing walls only |
| residential tower ground floor | stone base / windows | street walls: glazed, warm-lit lobby; rear walls unchanged |

Archetype rules: walk-up / low = full response; huaxia = moderate (sparser signs); res_tower = lobby only on street
walls, no signs / arcades; office / premium = unchanged (clean); podium = LED on street walls only; civic / landmark =
unchanged (civic override still wins); school = untouched (`xc_school_wall` routing, bit4 corridor).

## 3. Validation

| gate | result |
|---|---|
| `check_tiles.py` (1,457,808 corners): position / normal / UV0 / UV1 / RGB bit-identical; flags bits 0-3, 7 identical; bits 4-6 changed only on walls of ordinary records; every ordinary wall carries a role, no roof does; school + rooftop-structure corners fully identical | **PASS** |
| accepted triangle soup | bit-identical (fail-closed) |
| shader functions vs HEAD: only `xc_wall` changed (`xc_school_*`, `xc_roof`, `xc_taipei101`, `xc_ground`, `xc_backdrop`, `xc_foliage`, `xc_prop`, `xc_city` text-identical) | **PASS** |
| cloud / hero / rooftop / campus / ground sources; rooftop instances; look sidecar content; campus membership | unchanged / identical |
| DXC ps_6_0 `-WX`, all 7 materials | ok (this SDK `dxc` has no SPIR-V backend) |
| UE5.8 assets / level stages; fresh-reopen capture | PASS_LOOK_ASSETS / PASS_LOOK_LEVEL / PASS_LOOK_CAPTURE ×6 |

Changed pixels (|Δ| > 8, DAY / DUSK / NIGHT): rear-wall views 7-9 %, corner 4-5 %, street / block 2-3 %, MID / HIGH
(`roof_ne1`, `roof_mid`, `d_overview_sw`, `a_skyline_nw`) 0.5-2.5 %, school view 1.2-1.6 %, Taipei 101 close pass
0.01-0.04 % (renderer noise). Mean luminance over 13 shots: DAY 80.4 → 80.2, DUSK 39.3 → 37.6, NIGHT 15.6 → 14.0
(the drop is the removed shop / sign glow on back walls); 0 % clipped in DAY / NIGHT, 0.004 % DUSK (both).

**Performance** (SceneCapture2D 1080p, 7 views × 40 captures, 3 runs each, median of 3): HEAD 80.9 ms, candidate
77.3 ms mean. The −3.6 ms is session drift, not a speedup (the HIGH overview where nothing visible changed moved
−5.9 ms; suites ran sequentially, not interleaved): **no measurable regression**. No new draw, texture, HISM or vertex;
the new ground-floor work is behind a per-building-coherent `[branch]`; MID / HIGH pay only a few ALU per wall pixel.

Evidence: `unreal/Saved/XinyiLook/evidence/frontage_v0a/` — `frames/base_*` / `cand_*`, `sheets/fin_low_{day,dusk,night}`,
`sheets/fin_midhigh_*`, zoom crops `c1_corner_zoom`, `c1_rearb_zoom`; harness `harness/` (cameras in `shots_extra.json`).
Strongest camera: `fr_rear_a` (walk-up rear wall facing a pond: HEAD paints a full shopfront arcade + sign band,
lit at night; now a quiet back wall). Also `fr_rear_b` (open lot) and `fr_corner_b` (corner keeps both street faces).

## 4. Known limits

* Streets mapped only as `service` (and unmapped lanes) read as rear / alley: some real shop lanes become quiet.
* Low-altitude ground floors are mostly hidden by neighbours; the effect shows on streets, corners and open lots.
* The commercial street front is now *correct* but not yet *richer*; awnings and vertical signs are Phase B.
* Lit shop interiors are subtle in shade; NIGHT street level is somewhat darker overall than HEAD.
