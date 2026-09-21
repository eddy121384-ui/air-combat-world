# Xinyi v2 serialization-space representative gate: PASS

> **Historical representative evidence.** This document records the 80-part serialization-space gate that used mapbox-earcut and was correct for that representative sample. The current full-Xinyi production triangulator is GEOS constrained Delaunay; see `docs/xinyi-v2-full-xinyi-cloud-result.md`. Do not restore earcut as production policy from this older report.

Date: 2026-09-20 Asia/Taipei. Draft PR [#6](https://github.com/eddy121384-ui/air-combat-world/pull/6),
Issue [#5](https://github.com/eddy121384-ui/air-combat-world/issues/5).

**The representative gate passes. Full Xinyi tiled generation may begin as a
separate task. It was not performed here; neither was Unreal import.**

| Gate | Result |
|---|---:|
| Locked source parts / unique building IDs | 80 / 79 |
| Quantized footprint fidelity | 80/80 PASS |
| Serialization-space float64 strict solids | 80/80 PASS |
| Actual in-memory GLB export/reload strict solids | 80/80 PASS |
| Independent Blender imported-mesh audit | 80/80 PASS |
| GEOS strict QA on Blender's imported buffers | 80/80 PASS |
| Zero-area / wrong roof / wrong base / wrong walls / nonfinite | 0 / 0 / 0 / 0 / 0 |
| Holes retained | 29 in 14 selected parts |
| Visual inspection of six categories | PASS |
| Failure IDs | None |

## Historical baseline remains intact

The [76/80 strict result](xinyi-v2-strict-representative-result.md) at
`3b963a4076b81ff413fcb7152688b2eb6e37f4bb` and all files under
`evidence/xinyi-v2-strict/` are unchanged. This run adds a separate
`evidence/xinyi-v2-serialization/` directory; no historical evidence was replaced.
The earlier real-footprint regression still proves why post-triangulation
float32 casting fails.

The exact projected WFS source hash remains
`c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`.
The ordered `(building_id, polygon_index, height)` lock is unchanged. Selection,
original GEOS repair, EPSG:3826 -> pyproj -> WorldModel/ENU and surveyed heights
are retained. There is no reselection to avoid difficult parts.

## General serialization-space policy

1. Keep the existing source-part centroid ownership: tile index is
   `floor(centroid_enu / 500)`, independently for east and north. Negative
   coordinates use floor, not truncation. All repaired components of a source
   part share its owner. A footprint crossing a tile edge is not clipped.
2. Translate each GEOS-repaired footprint by the tile origin, exactly an integer
   multiple of 500 m. Quantize all exterior/interior ring coordinates through
   `float64 -> float32 -> float64` **before triangulation**.
3. Validate the quantized footprint using GEOS. If invalid, the sole repair
   policy is `make_valid(method='structure', keep_collapsed=False)`. Requantize
   any resulting polygonal coordinates once, then require valid, disjoint,
   area-bearing parts. No iterative repair search or handwritten footprint fix.
   Fidelity/holes checks reject unacceptable repairs. **No quantized footprint
   needed make_valid in this sample.**
4. Run the unchanged mapbox-earcut/trimesh extrusion on these representable
   coordinates. Require every output horizontal coordinate to be exactly
   float32-representable. No triangles are removed or patched.
5. GLB POSITION stores tile-local coordinates. Each building node carries the
   tile translation `[origin_east, 0, -origin_north]` in glTF Y-up. After Blender
   converts to Z-up, the translation is `[origin_east, origin_north, 0]`.
6. Actual in-memory GLB export/reload must preserve horizontal POSITION values,
   face indices and node transforms exactly. Run strict QA in local space and
   again on the reconstructed ENU mesh. Only then publish the representative GLB.

The 80 parts span 19 ownership tiles. Geometry remains 2,594 vertices and 4,984
triangles, exactly the baseline counts. The four former failing IDs now pass:
`tp_building_height.296019`, `.269609`, `.295251`, `.269018`.
IDs occur in evidence/tests/visual selection, never in geometry policy.

## Precision and fidelity

`strict_qa.py` is byte-for-byte unchanged from `3b963a4`; no QA tolerance was
relaxed. Footprint comparison uses the same global error formula:
`xy_error = max(1e-6 m, 2 * float32 ULP at local coordinate magnitude)` and
`area_error = max(1e-8 m², perimeter * xy_error + pi * xy_error²)`.
These are uniform formulas, not building-specific overrides. Reported bounds
displacements must be within `xy_error`; area delta and symmetric difference
must be within `area_error`. Hole counts must agree and eroded courtyard cores
must stay empty to the unchanged 1e-8 m² noise threshold.

Observed maxima over all 80 original-vs-quantized repaired footprints:

| Metric | Maximum |
|---|---:|
| Absolute area delta | 0.000465490223 m² |
| Symmetric difference | 0.002228702308 m² |
| Bounds displacement | 0.000022286832 m (0.0223 mm) |
| Hole-count changes | 0 |

Every component has its original and quantized geometry, displacement metrics,
precision budget, tile transform and both mesh QA stages in the numerical JSON.
The comparison is to PR #6's original repaired footprint, not to a substituted
or manually edited shape.

## Official Blender MCP independent validation

Blender 5.2.0 LTS imported this exact GLB, SHA-256:
`3fc0cdd5c66e515b9a97833f553221762c379acb1ed162a354d2a7cf1e298a33`.
Import used `merge_vertices=False`, `import_shading='NORMALS'`. The prior
unsaved scene was backed up to `unreal/Saved/SerializationSpace/before-serialization-gate.blend`
and preserved; the representative sample lives in a new scene
`Xinyi_Serialization_Strict_80`. A review copy is saved as
`unreal/Saved/SerializationSpace/representative-inspected.blend`.

The bpy audit reads imported vertices and faces without modifying geometry.
Independent scalar predicates verify finite vertices, triangle areas, geometric
cap normals, Blender's own polygon cap normals, exact-position edge manifoldness,
edge winding, positive signed volume and every ENU tile transform. All counts
of defects are zero. No trimesh loader is involved in that audit.

Blender's actual buffers are then checked externally with the unchanged GEOS
strict QA for cap union/overlap/symmetric difference, footprint area × height,
courtyard cores and outward wall normals. All 80 pass, with wrong walls = 0.
This second stage consumes bpy-exported buffers, not the pre-import GLB.

## Visual inspection and screenshots

The assistant visually inspected the actual Blender screenshots below. This is
a geometry/serialization review, not a claim of independent human sign-off or
real-world cadastral/height accuracy. No visible folded caps, unintended spikes,
or triangulation-created false buildings were found in the reviewed cases.
The 3-hole and 6-hole footprints retain their open courtyards. The high-rise
examples are slender, flat-topped prisms consistent with their source footprint
and surveyed height; their narrow proportions were not manually altered.

| View | Inspected IDs / observation |
|---|---|
| [Low-rise](evidence/xinyi-v2-serialization/screenshots/01-low-rise.png) | 269018: coherent flat roof and walls; former failure |
| [Courtyard top](evidence/xinyi-v2-serialization/screenshots/02-courtyard-top.png) | 296019: all three openings visible; former failure |
| [Courtyard oblique](evidence/xinyi-v2-serialization/screenshots/03-courtyard-oblique.png) | 296019: inner walls and roof continuity |
| [Complex six holes](evidence/xinyi-v2-serialization/screenshots/04-complex-six-holes.png) | 269609: complex outline and six open voids; former failure |
| [Concave](evidence/xinyi-v2-serialization/screenshots/05-concave.png) | 295251: recessed outline, no folded roof; former failure |
| [Multipart](evidence/xinyi-v2-serialization/screenshots/06-multipart.png) | 293551 parts 0 and 1, preserved separate solids |
| [High-rise](evidence/xinyi-v2-serialization/screenshots/07-high-rise.png) | 294504: 153.81 m slender flat-topped prism |
| [Second high-rise](evidence/xinyi-v2-serialization/screenshots/08-high-rise-second.png) | 295825: 80.73 m intact prism |
| [Overview](evidence/xinyi-v2-serialization/screenshots/09-overview.png) | The same sparse representative set in ENU positions, not a full district |

## Evidence and reproduction

- [Numerical per-part report](evidence/xinyi-v2-serialization/numerical.json)
- [Exact representative GLB](evidence/xinyi-v2-serialization/representative-80.glb)
- [Independent bpy checks and imported mesh buffers](evidence/xinyi-v2-serialization/blender-imported.json)
- [GEOS strict results on imported buffers](evidence/xinyi-v2-serialization/blender-strict.json)
- [Final gate and visual review receipt](evidence/xinyi-v2-serialization/gate.json)

Pinned stack remains NumPy 2.3.5, Shapely 2.1.2, trimesh 5.1.0,
mapbox-earcut 2.1.0 and pyproj 3.7.2. Local numerical run: Python 3.12.10 on
Windows, 6.757 s excluding module startup, GLB 134,680 bytes. **26 tests pass**,
including the preserved old failure plus the new solution, negative tile
boundaries, cross-tile courtyard preservation and rejection of a collapsed hole.

```powershell
python -m unittest discover -s tests -v
python tools/citygen_v2/build_representative.py --glb unreal/Saved/SerializationSpace/fresh.glb --report unreal/Saved/SerializationSpace/fresh.json
```

Use a fresh output path: existing GLB/report evidence is never overwritten.
The projected source must match the locked hash. The workflow uploads the new
serialization report and GLB under separate filenames. For Blender reproduction,
import that GLB through official MCP into a separate scene, call
`blender_import_audit.audit_import(...)`, then run `check_blender_buffers.py`
against the exported buffers. `blender_visual_view.py` only adjusts visibility
and the view for screenshot review; it never changes vertex/face data.

No full Xinyi generation, Unreal import, facade/material polish, gameplay,
per-building repair hacks, manual footprint edits, triangle deletion or merges
of PR #3/#6/#7 were performed.
