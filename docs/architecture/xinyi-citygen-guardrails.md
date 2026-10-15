# Xinyi Citygen v2 — Guardrails and Regression Traps

Read together with `xinyi-citygen-v2.md` and `../xinyi-v2-full-xinyi-cloud-result.md`.

This file records the mistakes and tempting shortcuts that future agents must not reintroduce.

## 1. Do not use the coarse EPSG:4326 snapshot as production input

The committed coarse snapshot is useful because it reproduces historical failures. It is not a
precision-preserving building source.

Observed forensic facts include thousands of collapsed exteriors and widespread loss of
building-scale detail. A triangulator cannot reconstruct information that the source no longer
contains.

Use the projected EPSG:3826 route for production-candidate generation.

## 2. Do not blame every failure on triangulation

The project has seen failures from:

- source-coordinate collapse;
- dropped interior rings;
- invalid / self-intersecting topology;
- point-contact / courtyard topology;
- float32 serialization after triangulation;
- triangulator-created sliver triangles that collapse in Blender float32 arithmetic;
- QA algorithms that are numerically unstable at large coordinate offsets.

Diagnose the failing stage before changing policy.

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

The failed 76/80 result remains a regression fixture.

## 4. Do not restore earcut as the production triangulator

Earcut remains installed only because the test suite reproduces historical failures.

The first full-Xinyi cloud run using serialization-space earcut passed the numerical/GLB gate but
Blender imported five mesh components with one degenerate sliver triangle each. Those five
degeneracies also produced 15 non-manifold / inconsistent-edge findings in Blender.

The validated production triangulator is now **GEOS constrained Delaunay via Shapely**.

Changing this policy is a validation event: rerun the locked representative gate, both deterministic
full-Xinyi runs, and the full Blender cloud gate.

## 5. Do not discard holes / courtyards

Interior rings are source topology. An exterior-only path can emit a plausible-looking solid while
filling courtyards.

The v2 path must preserve and validate holes end-to-end.

## 6. Do not make per-building exceptions

Forbidden examples:

- `if building_id == ...`
- custom coordinate nudges for one building;
- deleting a bad triangle;
- replacing one footprint by a rectangle / convex hull;
- manually editing a courtyard;
- skipping a building without accounting for it;
- building-specific repair recipes;
- special tolerance overrides for known failures.

If a general policy cannot handle a case, fail the gate and diagnose the failure class.

## 7. Do not weaken QA to obtain green CI

A failure is evidence, not an inconvenience.

Do not:

- increase tolerances after inspecting one failing ID merely to pass it;
- stop checking cap overlap because volume passes;
- stop checking geometric normals because stored normals look correct;
- ignore failures because they are visually small;
- remove a hard representative case from the locked sample;
- reinterpret zero-area triangles as harmless after Blender proves they collapse.

A tolerance or policy change must be global, independently justified, documented and
regression-tested.

## 8. Do not confuse numerical stabilization with tolerance relaxation

The Blender full-Xinyi gate found one tiny solid whose direct-origin float32 scalar-triple-product
sum reported a small negative signed volume despite valid topology and a positive Trimesh volume.

The approved QA fix recenters vertices around a local reference point before signed-volume
accumulation. Closed-mesh volume is translation invariant.

This is allowed because it improves numerical conditioning without moving geometry, changing the
acceptance threshold or adding an ID-specific rule.

Do not generalize this into arbitrary QA rewrites after failures.

## 9. Do not equate "watertight" with "correct"

A mesh can be watertight, consistently wound and positive-volume while still containing a locally
folded cap, overlapping cap or filled courtyard.

Keep the full strict gate:
cap coverage, overlap, normals, hole retention, wall direction, actual serialization and imported
buffer checks.

## 10. Do not bypass source accounting

For full-area work, every source polygon part must end in an explicit outcome.

Required categories include at least:

- ready / valid as supplied;
- repaired;
- rejected with reason;
- hero suppressed;
- emitted;
- failed QA with reason.

Unaccounted parts are a gate failure.

The validated full-Xinyi run accounts for 11,128 ordinary polygon parts and 8 hero-suppressed
polygon parts with zero failures.

## 11. Do not let Unreal repair upstream geometry

Unreal is downstream.

Do not advance because a defect is "probably invisible" or because engine import hides it. The
current geometry has already passed the numerical, GLB and Blender gates.

Use a separate `XinyiV2` asset / level path for engine experiments until the new pipeline is
accepted.

## 12. Do not overwrite historical evidence

Keep failed and passing runs separately so future agents can understand why the current method
exists.

Important history:

- old custom / PR #3 evidence;
- coarse-source forensic audit / PR #7;
- projected-source representative numerical pass;
- 76/80 post-serialization failure at `3b963a4`;
- representative serialization-space 80/80 PASS at `cc057996...`;
- full-Xinyi earcut numerical PASS but Blender 5-mesh sliver failure;
- full-Xinyi GEOS-CDT + stable Blender volume QA PASS at
  `4438d82fe2006710b0fda08e8a06989fba4c09a8`.

Do not rewrite failed reports to look successful.

## 13. Treat source or dependency drift as a new validation event

If any of these change:

- WFS dataset / response;
- source hash;
- CRS;
- height-field semantics;
- pyproj transform;
- GEOS / Shapely;
- trimesh;
- triangulation policy;
- tile size / ownership rule;
- GLB transform convention;
- strict QA policy;
- Blender import / buffer audit logic;

rerun the locked representative gate before trusting full-city output, then rerun the full-Xinyi
regression gate before scaling farther.

## 14. Keep hero and ordinary layers separate

Ordinary city generation must respect hero suppression. Do not emit duplicate ordinary masses under
Taipei 101 / designated hero replacements.

Do not silently alter the 508 m hero reference while changing ordinary-building generation.

## 15. Scale by repeating the validated method, not by inventing a new one

After Unreal Xinyi passes, Taipei should be an expansion of coverage and automation.

Do not use "Taipei is bigger" as a reason to remove validation, switch back to global coordinates,
create a monolithic mesh, restore a known-failing triangulator, or hand-fix districts.

The scalable unit is the deterministic tile plus machine-readable accounting, numerical QA and
headless Blender QA.
