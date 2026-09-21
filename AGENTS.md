# AGENTS.md

## Read this before touching Taipei / Xinyi city generation

The current production-candidate geometry method is documented in:

1. `docs/architecture/xinyi-citygen-v2.md`
2. `docs/architecture/xinyi-citygen-guardrails.md`
3. `docs/xinyi-v2-serialization-space-result.md`

These documents override older experimental assumptions for city geometry work.

## Non-negotiable rules

- Do **not** use the pinned EPSG:4326 snapshot as production geometry input. It is forensic / regression evidence only.
- Production input must preserve projected-coordinate precision. The validated route is EPSG:3826 -> pyproj -> WorldModel / ENU.
- Ordinary buildings are owned by deterministic 500 m ENU tiles.
- Convert repaired footprints to tile-local coordinates and quantize their horizontal coordinates through float32 **before triangulation**.
- Revalidate the quantized footprint with GEOS before meshing.
- Use mature geometry libraries: Shapely/GEOS for validity/repair, mapbox-earcut for triangulation, trimesh for extrusion/export.
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
-> earcut / trimesh meshing
-> actual GLB export + reload
-> strict QA
-> Blender imported-mesh QA / visual review
-> only then Unreal
```

The representative gate at `cc0579962fb5c1af527bad895c6b5a340e6f5753`
passed 80/80 locked source parts through numerical, actual GLB and Blender imported checks.
The earlier 76/80 result at `3b963a4` is intentionally preserved as a regression proving why
post-triangulation float32 casting is unsafe.

## Historical branches / PRs

- PR #3: older custom-geometry experiment. Do not treat it as the production path.
- PR #6: Xinyi robust whitebox v2 production-candidate work.
- PR #7: forensic audit of the coarse pinned EPSG:4326 source. Useful QA evidence, not a production replacement.

When old reports disagree with the serialization-space result, treat the newer validated
serialization-space method as authoritative unless a newer documented gate supersedes it.

## Source drift

If the WFS response, source hash, CRS, height semantics, dependency versions, tile policy,
coordinate transform, or triangulation policy changes, do not silently continue full-city
generation. Re-run the locked representative gate first and record the new evidence.

## Hero buildings

Keep hero suppression separate from ordinary-building geometry. Do not duplicate the Taipei 101
ordinary-source records underneath the hero asset. The existing known hero anchor and 508 m
reference must not be silently changed by ordinary city generation.

## Scope discipline

For city-generation tasks, solve one gate at a time:

1. representative geometry
2. full Xinyi geometry
3. Blender full-area sample QA
4. Unreal XinyiV2 import / performance spike
5. only after that, scale toward Taipei

Do not mix facade polish, materials, gameplay, Taipei Basin expansion, or production-tool winner
decisions into a geometry gate unless the task explicitly asks for them.
