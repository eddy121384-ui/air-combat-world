# AGENTS.md

## Read this before touching Taipei / Xinyi city generation

The current production-candidate geometry method is documented in:

1. `docs/architecture/xinyi-citygen-v2.md`
2. `docs/architecture/xinyi-citygen-guardrails.md`
3. `docs/xinyi-v2-full-xinyi-cloud-result.md`
4. `docs/architecture/xinyi-whitebox-preview-pipeline.md`
5. `docs/xinyi-v2-whitebox-preview-status.md`
6. `docs/architecture/xinyi-terrain-integration-plan.md`
7. `docs/xinyi-v2-serialization-space-result.md` — historical representative evidence

These documents override older experimental assumptions for city geometry work.

## Current validated status

As of commit `4438d82fe2006710b0fda08e8a06989fba4c09a8`, workflow run
`35557915078` passed the complete cloud gate:

- locked representative geometry: PASS;
- full Xinyi numerical/GLB gate: PASS twice with identical deterministic hashes;
- 11,128 ordinary source polygon parts accounted for and emitted;
- 8 hero-suppressed source parts;
- 25 deterministic 500 m tiles;
- 485,936 triangles;
- Blender 5.2.0 LTS imported all 25 tiles / 11,130 mesh components: PASS;
- zero-area, non-manifold, winding, cap-normal, wall, nonfinite, volume and tile-transform errors: all 0.

The next gate is **Unreal XinyiV2 import / performance validation**. Do not restart the geometry
research unless a source/dependency/policy change invalidates the evidence above.

## Non-negotiable rules

- Do **not** use the pinned EPSG:4326 snapshot as production geometry input. It is forensic / regression evidence only.
- Production input must preserve projected-coordinate precision. The validated route is EPSG:3826 -> pyproj -> WorldModel / ENU.
- Ordinary buildings are owned by deterministic 500 m ENU tiles.
- Convert repaired footprints to tile-local coordinates and quantize their horizontal coordinates through float32 **before triangulation**.
- Revalidate the quantized footprint with GEOS before meshing.
- Production cap triangulation uses **GEOS constrained Delaunay triangulation** via Shapely.
- Trimesh owns extrusion / mesh assembly / GLB export. Mapbox-earcut remains only as a historical regression dependency and must not be silently restored as the production triangulator.
- Preserve holes / courtyards and multipart provenance.
- Never add per-building fixes, hidden skips, hand-edited footprints, deleted triangles, or building-ID-specific exceptions to make a gate pass.
- Never relax a QA tolerance after seeing a failing building unless the tolerance change is independently justified and applied globally.
- A generated mesh is not accepted merely because it is watertight or has positive volume. Run the strict geometry gates.
- Full-Xinyi generation must fail closed on any unaccounted or failed source part.
- Unreal import is downstream of geometry validation. Do not use Unreal to hide or repair source/mesh defects.
- Preserve historical evidence and the legacy compiler/assets unless a separate migration task explicitly removes them.

## Mandatory validation order

For representative or full-city work:

```text
projected source
-> GEOS repair
-> deterministic 500 m tile ownership
-> tile-local coordinates
-> float32 serialization-space quantization
-> GEOS revalidation
-> GEOS constrained Delaunay triangulation
-> trimesh extrusion
-> actual GLB export + reload
-> strict QA
-> Blender 5.2 headless imported-mesh QA + overview renders
-> only then Unreal
```

Historical evidence that must remain understandable:

- `3b963a4`: 76/80 after post-triangulation float32 cast — proves serialization-space meshing is required.
- `cc057996...`: 80/80 representative serialization-space PASS using earcut.
- Full-Xinyi earcut cloud run: numerical PASS but Blender exposed 5 degenerate sliver triangles.
- `4438d82...`: production switched to GEOS constrained Delaunay; full numerical + Blender gate PASS.
- Blender signed volume is accumulated after recentering vertices around a local reference origin. This is a numerically stable, translation-invariant calculation, not a tolerance relaxation.

## Whitebox preview and terrain are separate layers

The current district whitebox preview consumes the already validated 25 Full-Xinyi GLB tiles.

It is a visualization layer, not a second production geometry path.

- Preview workflow: `.github/workflows/xinyi-preview.yml`
- Preview renderer: `tools/preview/xinyi_blender_preview.py`
- Preview contract: `docs/architecture/xinyi-whitebox-preview-pipeline.md`
- Terrain candidate result: `docs/xinyi-terrain-v0-dtm-result.md`
- Current visible milestone: `docs/xinyi-v2-whitebox-preview-status.md`

The original building-only whitebox did not contain terrain. Terrain v0 now has a passing
candidate using a cloud-readable derivative mirror of the official MOI 2025 bare-earth 20 m DTM.

The earlier Copernicus GLO-30 DSM prototype is rejected as urban ground because its surface sat
roughly +17 m above surveyed building ground at the median. Do not restore it as production terrain.

The accepted candidate terrain uses the same Xinyi ENU / 500 m tile contract and a single documented
vertical-datum alignment. Blender-imported building bases are measured in world Z and snapped to
surveyed WFS `ground_elev_m`, with a fail-closed base-Z regression guard.

See `docs/xinyi-terrain-v0-dtm-result.md` and
`docs/architecture/xinyi-terrain-integration-plan.md`.

The building meshes remain immutable. Terrain integration may add terrain geometry and a documented
building world-Z offset policy, but it must not remesh ordinary buildings or introduce
building-specific Z hacks.

There are now two downstream tracks:

- **world-completeness track:** MOI 2025 bare-earth DTM derivative source audit -> 25 terrain tiles -> surveyed building base-Z anchoring -> terrain + building preview — PASS candidate;
- **engine track:** isolated Unreal `XinyiV2` import / placement / performance validation.

Do not confuse a preview render failure with a geometry-gate failure, and do not treat an attractive
preview as evidence that geometry or Unreal runtime validation has passed.

## Historical branches / PRs

- PR #3: older custom-geometry experiment. Do not treat it as the production path.
- PR #6: Xinyi robust whitebox v2 production-candidate work.
- PR #7: forensic audit of the coarse pinned EPSG:4326 source. Useful QA evidence, not a production replacement.

When old reports disagree with `docs/xinyi-v2-full-xinyi-cloud-result.md`, use the newer full-Xinyi
validated method unless an even newer documented gate explicitly supersedes it.

## Source / policy drift

If the WFS response, source hash, CRS, height semantics, dependency versions, tile policy,
coordinate transform, triangulation policy, or strict QA logic changes, do not silently continue
city expansion. Re-run the locked representative gate and full-Xinyi regression gate before
trusting the change.

## Hero buildings

Keep hero suppression separate from ordinary-building geometry. Do not duplicate the Taipei 101
ordinary-source records underneath the hero asset. The existing known hero anchor and 508 m
reference must not be silently changed by ordinary city generation.

## Scope discipline

Current sequence:

1. representative geometry — PASS
2. full Xinyi numerical / serialization gate — PASS
3. Blender full-area cloud QA — PASS
4. building-only Xinyi whitebox preview — AVAILABLE
5. terrain source / tile / building-elevation integration — NEXT WORLD-COMPLETENESS LAYER
6. Unreal XinyiV2 import / placement / performance spike — NEXT ENGINE GATE
7. only after these contracts are stable, scale the same tile pipeline toward wider Taipei

Do not mix facade polish, materials, gameplay, Taipei-wide expansion, or production-tool winner
decisions into the Unreal import gate unless the task explicitly asks for them.
