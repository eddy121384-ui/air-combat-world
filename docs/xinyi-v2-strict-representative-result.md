# Xinyi v2 strict representative gate: FAIL (76/80)

Date: 2026-09-20 Asia/Taipei. Issue [#5](https://github.com/eddy121384-ui/air-combat-world/issues/5).
Draft PR [#6](https://github.com/eddy121384-ui/air-combat-world/pull/6), branch
`feat/xinyi-robust-whitebox-v2`; starting head
`b06f0d1e2091188f4b9ae0dfa6bb01b1581eb106`.

**Not ready for full Xinyi tiled generation.** Float64 strict QA passes 80/80,
but actual GLB float32 serialization/reload passes only **76/80**. Four parts
each acquire one reversed roof triangle, one reversed base triangle, and
overlapping cap area. The representative numerical gate therefore fails.
Blender import/visual QA was not run, following the explicit stop condition.
No full Xinyi generation, Unreal import, materials/facades, gameplay, manual
per-building fixes, or merges of PR #3/#6/#7 were performed.

## Same source and same sample

The existing EPSG:3826 fetch, pyproj -> WorldModel -> ENU, GEOS structure repair,
mapbox-earcut, trimesh extrusion and deterministic selection algorithm are
unchanged. Only QA/reporting and fail-closed export handling were added.
PR #7's generator was not transplanted and neither branch history was rewritten.

Re-fetched projected source SHA-256 exactly matches the original passing run:
`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`.

Original CI evidence was downloaded from workflow run **35472593980**, artifact
**10593245819**, and its ZIP SHA-256 verified:
`7a74f8ede496fc961ef0c9c2f341cedfd38493191c635d2164810eb32a020e11`.
The original report hash is
`93188ca4e77882aa93d77b50f62d8ee8e7e43462f808d81c53f40c59d9a75d56`.

[representative_selection.json](../tools/citygen_v2/representative_selection.json)
locks all 80 `(building_id, polygon_index, height)` records in their original
order and the exact input hash. The builder refuses a changed source or changed
selection instead of silently replacing hard cases. For clarity, the historic
"80 buildings" sample is **80 source polygon parts from 79 unique building IDs**.
The categories remain 46 concave, 14 with holes, 31 complex, 39 low-rise/small
footprint, 4 multipart-feature parts, 8 high-rise, 21 simple rectangles and
27 mid-rise (categories overlap).

Dependencies remain PR #6's pinned versions: NumPy 2.3.5, Shapely 2.1.2
(GEOS 3.13.1 here), trimesh 5.1.0, mapbox-earcut 2.1.0, pyproj 3.7.2. Local run:
Windows, Python 3.12.10. No production dependency was added.

## Strict QA added

`strict_qa.py` adapts the useful independent predicates from PR #7's
`check_solid`, using PR #6's Y-up glTF frame. It does not generate or repair
geometry. Every selected repaired component is tested in float64 and again
after **actual in-memory GLB export and GLB reload**, including node transforms.
The GLB is written for Blender only when all selected parts pass both stages.
No failed strict output GLB was published by this run.

Checks now include:

- Finite vertices, valid indices, no triangles with area <= 1e-8 m².
- Exact-position welding for topology analysis only; watertightness, consistent
  winding and positive volume. No vertex movement or output-mesh modification.
- Expected base elevation 0 and roof elevation equal to surveyed height.
- Geometric roof/base normals from position cross products, independently of
  stored normals; roof +Y and base -Y.
- Volume equal to GEOS footprint area times surveyed height within a documented
  serialization error budget.
- GEOS union of roof and base triangles compared with the expected footprint:
  symmetric difference, missing area, excess area and triangle area sum.
- Cap overlap tested separately as `sum(triangle areas) - union area`, so matching
  total area or volume cannot hide overlapping faces.
- Courtyard/hole count must match, and each hole's interior core must remain
  empty. A small hole cannot silently disappear under a whole-building tolerance.
- Every wall normal must point outside the solid, including into courtyard
  voids; GEOS tests inward/outward offset points on both sides of each wall.
- Machine-readable failures identify building ID, source polygon index,
  repaired component index and failing precision stage.

Global numerical tolerances were chosen before the 80-part strict run; there
were **no per-building overrides or post-failure tolerance increases**. For
float64, coordinate/elevation error is 1e-7 m. For float32, it is the larger
of 1e-6 m and two float32 ULPs at the coordinate magnitude. Cap coverage budget
is `perimeter * xy_error + pi * xy_error²`, floored at 1e-8 m². Volume budget
propagates that area error and height error. Overlap tolerance remains 1e-8 m²;
cap direction must still be correct even for small triangles. Wall probes use
`max(0.001 m, 8 * xy_error)`. These tolerances account for serialization without
excusing topological changes, flipped caps or filled holes.

## Measured failures

All four failures occur after serialization, not in the float64 mesh. Every
failure has source polygon index 0 and repaired component index 0.

| Building ID | Category examples | Float64 signed roof area m² | Raw float32 signed roof area m² | Roof cap overlap m² |
|---|---|---:|---:|---:|
| `tp_building_height.296019` | complex, concave, 3 holes | +1.592263e-5 | -4.263781e-5 | 4.263781e-5 |
| `tp_building_height.269609` | complex, concave, 6 holes | +3.658346e-6 | -5.983748e-7 | 5.983748e-7 |
| `tp_building_height.295251` | complex, concave | +1.348044e-5 | -5.997717e-7 | 5.997717e-7 |
| `tp_building_height.269018` | low-rise/small footprint | +2.882351e-5 | -1.683482e-5 | 1.683482e-5 |

Each reports `roof_normal_not_up:1`, `base_normal_not_down:1`,
`roof_overlapping_triangles`, and `base_overlapping_triangles`.

The same defects were independently confirmed by decoding the **original PR #6
CI GLB's binary accessors** using struct/NumPy, without trimesh's GLB loader or
mesh repair. Its SHA-256 is
`dae3eff4608c5842e7fc5cf180d6e0a2e33975711301b4d7d27cb172e449cc84`.
All failing raw face-index arrays match regenerated float64 arrays exactly.
Only position quantization changes their geometric orientation. Maximum
coordinate rounding is approximately 1.45e-5–3.03e-5 m across these four meshes.
Near-collinear cap triangles are thin enough for that tiny coordinate rounding
to reverse signed area.

This explains why the earlier gate passed: topological winding, watertightness
and positive volume still pass after serialization. Those tests alone do not
detect a locally folded cap. The previous 80/80 result was valid for its earlier
checks, but it is superseded for release-readiness by the strict result here.

| Strict numerical / original raw GLB metric | Result |
|---|---:|
| Float64 strict pass | 80/80 |
| Float32 roundtrip strict pass | **76/80** |
| Failing source parts | **4** |
| Zero-area triangles | 0 |
| Wrong roof triangles | **4** |
| Wrong base triangles | **4** |
| Nonfinite vertices | 0 |
| Wrong wall triangles | 0 |
| Footprint coverage / volume / hole retention predicates | Pass within stated error budgets |
| Candidate geometry | 2,594 vertices / 4,984 triangles |
| Strict run time, excluding Python/module startup | 6.262 s |

The failure is a numerical correctness blocker. Without running Blender, this
report does **not** assert how visible these tiny inversions are from an aerial
camera, and does not claim projected-source buildings show the widespread source
collapse of the old EPSG:4326 experiment.

## Blender, screenshots and final verdict

**Blender geometry checks: NOT RUN. Visual inspection: NOT RUN. Screenshots:
none for this gate.** Official Blender connectivity was checked read-only before
the numerical run, but no strict sample was imported after the failure. Old
PR #7 screenshots were not reused as evidence for this projected-source sample.

Required conjunction:

```text
80/80 strict numerical PASS: FAIL (76/80)
Blender zero_area = 0:       NOT RUN
Blender wrong caps = 0:      NOT RUN
visual inspection PASS:     NOT RUN
Final: FAIL — cannot advance to full Xinyi tiled generation
```

Only read-only failure diagnosis and verification/reporting continued after the
failed gate. Possible future investigations include a consistent local-coordinate
serialization strategy or a general mature-library precision policy, followed
by the same locked sample gate. Neither was implemented here; no individual
triangle or building was patched.

## Reproduce / evidence

From the repository root with the pinned dependencies installed:

```powershell
node tools/citygen_v2/fetch_projected_sample.mjs
python -m unittest discover -s tests -v
python tools/citygen_v2/build_representative.py --count 80 --glb unreal/Saved/StrictRepresentative/recheck.glb --report unreal/Saved/StrictRepresentative/recheck.json
# Expected nonzero status; report is written and GLB is not published.
python tools/citygen_v2/diagnose_strict.py --report unreal/Saved/StrictRepresentative/recheck.json --baseline-glb unreal/Saved/StrictRepresentative/baseline/xinyi_v2_representative_80.glb --out unreal/Saved/StrictRepresentative/recheck-diagnosis.json
```

Download the original artifact identified above for the last command. Existing
GLBs are never overwritten; use a fresh output filename. The source hash lock
intentionally fails if a future WFS response changes. That is source drift, not
permission to select different buildings.

**23 tests pass, no skips**, including seven added strict tests. A real low-rise
regression proves float64 passes and float32 fails even though watertightness,
winding and positive volume still pass. Tests also reject filled holes, overlap,
missing caps, bad walls, shifted footprints, nonfinite and degenerate geometry.
The old compiler's existing ResourceWarning remains unrelated and unchanged.

Machine-readable evidence:

- [All 80 per-part strict results and expected footprints](evidence/xinyi-v2-strict/numerical.json).
- [Independent raw-buffer diagnosis, failure IDs and exact triangle coordinates](evidence/xinyi-v2-strict/diagnosis.json).
- [Final gate receipt](evidence/xinyi-v2-strict/gate.json).

The CI representative build now runs the strict gate and is expected to fail
until this blocker is addressed; it still uploads the numerical report for
diagnosis. It does not bypass the gate to obtain a green workflow.
