# Xinyi Citygen v2 — Guardrails and Regression Traps

Read together with `xinyi-citygen-v2.md`.

This file records the mistakes and tempting shortcuts that future agents must not reintroduce.

## 1. Do not use the coarse EPSG:4326 snapshot as production input

The committed coarse snapshot is useful because it reproduces historical failures. It is not a
precision-preserving building source.

Observed forensic facts include thousands of collapsed exteriors and widespread loss of
building-scale detail. A mature triangulator cannot reconstruct information that the source no
longer contains.

Use the projected EPSG:3826 route for production-candidate generation.

## 2. Do not blame every failure on triangulation

The project has seen failures from:

- source-coordinate collapse;
- dropped interior rings;
- invalid / self-intersecting topology;
- point-contact / courtyard topology;
- float32 serialization after triangulation;
- mesh winding / cap coverage issues.

Diagnose the stage that fails. Do not swap triangulators until the source and serialization path
have been ruled out.

## 3. Do not triangulate first and cast to float32 later

This caused the strict representative gate to fall from 80/80 in float64 to 76/80 after actual GLB
serialization.

Correct policy:

```text
tile-localize -> float32-quantize footprint -> GEOS validate -> triangulate -> extrude -> export
```

Incorrect policy:

```text
triangulate high-precision/global footprint -> cast finished mesh to float32
```

The failed 76/80 result is intentionally preserved as a regression fixture.

## 4. Do not discard holes / courtyards

Interior rings are real source topology. An exterior-only WorldModel path can emit solids that look
plausible while filling courtyards.

The v2 path must preserve and validate holes end-to-end.

## 5. Do not make per-building exceptions

Forbidden examples:

- `if building_id == ...`
- custom coordinate nudges for one building;
- deleting a bad triangle;
- replacing one footprint by a rectangle / convex hull;
- manually editing a courtyard;
- skipping a building without accounting for it;
- special tolerance overrides for known failures.

If a general policy cannot handle a building, fail the gate and diagnose the class of failure.

## 6. Do not weaken QA to obtain green CI

A new failure is evidence, not an inconvenience.

Do not:

- increase tolerances after inspecting a failing ID merely to pass it;
- stop checking cap overlap because volume passes;
- stop checking geometric normals because stored normals look correct;
- ignore failures because they are visually small;
- remove a hard representative case from the locked sample.

A tolerance or policy change must be global, justified, documented and regression-tested.

## 7. Do not equate "watertight" with "correct"

A mesh can be watertight, consistently wound and positive-volume while still containing a locally
folded cap or a filled courtyard.

Keep the full strict gate:
cap coverage, overlap, normals, hole retention, wall direction, actual serialization and imported
buffer checks.

## 8. Do not bypass source accounting

For full-area work, every source polygon part must end in an explicit outcome.

Required categories include at least:

- ready / valid as supplied;
- repaired;
- rejected with reason;
- hero suppressed;
- emitted;
- failed QA with reason.

Unaccounted parts are a gate failure.

## 9. Do not let Unreal repair upstream geometry

Unreal is downstream.

Do not advance to Unreal because a defect is "probably invisible" or because engine import happens
to hide it. Geometry must already pass before Unreal import.

Use a separate `XinyiV2` asset / level path for engine experiments until the new pipeline is
accepted.

## 10. Do not overwrite historical evidence

Keep failed and passing runs separately so future agents can understand why the current method
exists.

Important history:

- old custom / PR #3 evidence;
- coarse-source forensic audit / PR #7;
- projected-source representative numerical pass;
- stricter 76/80 post-serialization failure at `3b963a4`;
- serialization-space 80/80 PASS at `cc0579962fb5c1af527bad895c6b5a340e6f5753`.

Do not rewrite failed reports to look successful.

## 11. Treat source or dependency drift as a new validation event

If any of these change:

- WFS dataset / response;
- source hash;
- CRS;
- height-field semantics;
- pyproj transform;
- GEOS / Shapely;
- trimesh;
- mapbox-earcut;
- tile size / ownership rule;
- GLB transform convention;
- strict QA policy;

rerun the locked representative gate before trusting a full-city result.

## 12. Keep hero and ordinary layers separate

Ordinary city generation must respect hero suppression. Do not emit duplicate ordinary masses under
Taipei 101 / designated hero replacements.

Do not silently alter the 508 m hero reference while changing ordinary-building generation.

## 13. Scale by repeating the validated method, not by inventing a new one

After Xinyi passes, Taipei should be an expansion of coverage and automation.

Do not use "Taipei is bigger" as a reason to remove validation, switch back to global coordinates,
create a monolithic mesh, or hand-fix districts.

The scalable unit is the deterministic tile plus machine-readable accounting and QA.
