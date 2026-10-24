# Xinyi cap winding repair — stopped at raw GLB review gate

Date: 2026-09-20 (Asia/Taipei). Issue: [#2](https://github.com/eddy121384-ui/air-combat-world/issues/2).

The requested minimal extrusion repair is implemented and its regression tests
pass. **The complete solid-white-box acceptance gate does not pass.** Independent
Blender inspection and a separate raw GLB cross-product check both find 190
downward-facing roof triangles, 190 upward-facing base triangles, and 20
zero-area triangles remaining in the ordinary building mesh. Unreal reimport
was therefore not started, following the handoff's explicit stop-before-Unreal gate.

## Phase 0 — repository setup: complete

- Cloned `eddy121384-ui/air-combat-world` into `D:\AI Work\Skyfront`.
- Verified remote `main` and checked out the exact canonical baseline
  `08afe383d1b89a745f78f17d1930a75f045cec7a`.
- GitHub searches returned no matching issue or open PR; created issue #2.
- Branch: `feat/taipei-volume-integrity-repair-home`.
- No `AGENTS.md` was present in the repository or the checked ancestor locations.
- No unrelated branch was modified.

## Phase 1 — smallest winding repair: complete

Code commit: `66171ce87faeee1c31116909c4ae8d31b85e294f`.

Files changed:

- `tools/compiler/geo.py`: in `extrude()`, emit roof `(a,b,c)` and base
  `(a,c,b)`; correct the roof comment. Wall code is unchanged.
- `tests/test_geo_normals.py`: six tests, each covering rectangle and concave L
  footprints with both input ring orientations. Verify roof +Y, base -Y,
  outward walls, unchanged 12/20 triangle counts, stored normals consistent
  with geometry, and closed fixtures with oppositely paired geometric edges.

Before the repair, the roof, base, and edge-pairing tests failed for all four
fixture variants (12 subtest failures); wall/count/normal-consistency tests passed.
After the repair and regeneration:

```powershell
python -m unittest discover -s tests -v
# Ran 18 tests; OK; no skipped tests
```

The suite emits an existing `ResourceWarning` for the unclosed read handle in
`export_glb.py:100`; that unrelated code was not changed.

## Phase 2 — regenerated GLBs: inspection complete, acceptance failed

Used the committed sample input without fetching new data or changing WorldModel
logic. Commands:

```powershell
python tools/compiler/worldmodel.py
python tools/compiler/build_tile.py
python tools/compiler/build_greybox_tile.py
```

Generated files remain gitignored per repository policy:

- `data/generated/taipei/xinyi_tile_2km.glb`
- `data/generated/taipei/xinyi_tile_2km_greybox.glb`
- WorldModel JSON and both existing compiler reports.

Both GLBs were also generated at the baseline before editing `geo.py` and kept
locally under `unreal/Saved/VolumeIntegrity/before/` for exact comparison.

Unchanged counts: 11,132 source/WorldModel features, 8 hero-suppressed features,
5,819 extruded buildings (3,289 low / 2,250 mid / 280 high). Skip counters remain
`zero_area=5296`, `self_intersecting=10`, `building_fully_skipped=5305`.
These are recorded for scope preservation, not investigated in this repair.

### Independent inspection

Official Blender Lab MCP imported each GLB into a new inspection scene in
Blender 5.2.0. The existing default scene was preserved. No imported mesh was
edited, repaired, or exported. Blender converts GLB +Y-up to Blender +Z-up;
checks use world-space cross products of imported triangle positions.

The elevated viewport has **backface culling enabled**. Many ordinary roofs
are now visible and surrounding buildings read as solid masses. The closeup
still shows cap gaps, so this is not a full visual pass.

| Ordinary mesh | Triangles | Roof up | Roof down (bad) | Base down | Base up (bad) | Zero-area triangles |
|---|---:|---:|---:|---:|---:|---:|
| Low | 45,200 | 7,637 | 111 | 7,637 | 111 | 14 |
| Mid | 33,604 | 5,848 | 72 | 5,848 | 72 | 6 |
| High | 4,408 | 787 | 7 | 787 | 7 | 0 |
| Full ordinary mesh | 83,212 | 14,272 | 190 | 14,272 | 190 | 20 |

The full mesh and three greybox buckets represent the same buildings; their
counts must not be added together. The 20 degenerate triangles are already in
the baseline GLB and are distinct from the 5,296 `zero_area` skipped input parts.

Raw binary decoding independently agrees with Blender. Exact before/after checks
asserted:

- GLB JSON metadata, indices, triangle counts, and bounds are identical.
- All 28,944 ordinary cap triangles have only their second/third vertices
  exchanged, their normals negated, and matching UVs exchanged.
- All 54,268 wall triangles, normals, and UVs are exactly unchanged.
- Ground and hero mesh positions, normals, UVs, and indices are exactly unchanged.
- No nonfinite imported vertices. Taipei 101 height remains 508 m; ordinary-city
  bounds remain 2097.9423 x 2148.4661 m.

**Important limitation:** the baseline cap directions were mixed. Before the
swap, 14,272 nondegenerate roofs faced down and 190 faced up; after the swap,
these directions reverse. The global cap repair therefore corrects most roofs
but is insufficient for the real dataset. No additional triangulation or
precision fix was attempted. The evidence establishes the failure, not its full
upstream cause. The unit tests establish correctness for the specified simple
fixtures, not all real-data geometry.

One reproducible bad example is triangle 811 of `layerA_city_massing` (triangle
647 of `layerA_low`), in GLB Y-up meters:

```text
(-907.7634887695312, 5.96999979019165, 901.6878662109375)
(-897.6771850585938, 5.96999979019165, 901.6878662109375)
(-887.5909423828125, 5.96999979019165, 912.81982421875)
stored normal: (0, -1, 0)
```

### Evidence files

- [Blender exhaustive inspection](evidence/xinyi-blender-inspection.json)
- [Raw before/after comparison, hashes and bad-triangle examples](evidence/xinyi-raw-glb-comparison.json)
- [Blender overview, culling enabled](evidence/xinyi-winding-blender-overview.png)
- [Blender closeup, culling enabled](evidence/xinyi-winding-blender-closeup.png)

The independent raw comparison script is retained locally at
`unreal/Saved/VolumeIntegrity/compare_glbs.py`. All checks completed without an
assertion failure. Screenshot images are direct Blender captures, not mockups.

## Phase 3 — Unreal: not started

The handoff states: "If Blender/raw GLB still looks wrong, STOP before Unreal."
The cap-direction failures trigger that gate. No Unreal assets, maps, materials,
lighting, transforms, collision settings, Nanite, SM6, Lumen, or VSM were changed.
The 11/11 actors, fresh-session persistence, Lit view, and Unreal screenshots
remain **unverified for the repaired GLBs**.

Environment preflight only: official Unreal MCP tools were not exposed to this
task; the repository's existing `mcp_probe.py tools/list` client found the known
`127.0.0.1:8000/mcp` endpoint refused the connection. The running Unreal process
had no project argument. The repository project already enables the official
`ModelContextProtocol` and `AllToolsets` plugins. No alternative MCP or new
integration was introduced. This preflight is secondary to the failed GLB gate.

## Phase 4 — review gate

Stopped earlier than successful Unreal verification. The branch is suitable for
review of the narrow recipe and the newly measured blocker, not for approval as
a completed volume-integrity repair. Do not merge or proceed to Unreal until
the raw-geometry gate is resolved and rechecked.

## Phases 5–6 — deferred

Prepared follow-up scope only: after review, use a separate issue/branch for
"Audit #2: Xinyi 11,132 source features to 5,819 extrusions / zero_area 5,296."
Reconcile feature-level and polygon-part-level accounting against the pinned
sample and report evidence before changing ingestion or triangulation. That
audit was not started and its issue/branch was not created.

Visual-upgrade planning and implementation are deferred until both geometry
issues are under control. No facade, gameplay, new city compiler, or alternative
city-building workflow work was started.
