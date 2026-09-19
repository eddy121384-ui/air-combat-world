# Mature-library Xinyi geometry spike

**Blocked at the representative sample gate. Do not import these outputs into
Unreal.** The pinned GIS is quantized to approximately 10 x 11 m. GEOS cannot
recover lost footprints; the sample also exposes topology/precision failures.
See [the result](../../docs/xinyi-robust-whitebox-v2-result.md).

The generator is independent of the old `_clean_ring -> _ear_clip -> extrude`
path. Only the unchanged WorldModel normalization/ENU/height/hero metadata is
reused. An adapter rejoins complete source rings because WorldModel v0 retains
only exteriors. No old compiler file or generated GLB is overwritten.

## Reproduce on Python 3.12

From the repository root, in PowerShell:

```powershell
python -m venv unreal/Saved/CitygenV2/venv
& unreal/Saved/CitygenV2/venv/Scripts/python.exe -m pip install -r tools/citygen_v2/requirements.txt
& unreal/Saved/CitygenV2/venv/Scripts/python.exe -m unittest discover -s tests -v
& unreal/Saved/CitygenV2/venv/Scripts/python.exe -m tools.citygen_v2.build --stage sample --out unreal/Saved/CitygenV2/run-01
& unreal/Saved/CitygenV2/venv/Scripts/python.exe -m tools.citygen_v2.diagnose unreal/Saved/CitygenV2/run-01
```

The sample command deliberately exits with a failure status when any selected
part fails mesh QA. Reports and diagnostic GLBs are still written. Use a fresh
output directory for each run; existing mesh directories are never replaced.
`--stage audit` creates only accounting, without any meshes.

Outputs:

- `accounting.json`: every input part reconciled into valid/repaired/rejected.
- `parts.jsonl`: per-part IDs, height provenance, validity reason, collapsed
  GEOS result components, suppressed hero status, output component counts.
- `sample.json`: explicit selection reasons, numerical failures, per-component
  QA, tile bounds/hashes, performance and dependency versions.
- `sample/xinyi_v2_*.glb`: parts passing local numerical tests, **not** certified
  city assets. Independent Blender found additional float32 degeneracies.
- `sample/FAILED_DIAGNOSTICS_DO_NOT_IMPORT_TO_UE.glb`: failed meshes for inspection.
- `diagnosis.json`: source/old-label cross-tabulation, edge incidence evidence,
  precision limitations, potential tile ownership counts (no full generation).

GEOS `make_valid(method='linework')` is applied only to invalid polygons. Exact
duplicate removal and zero-tolerance topology-preserving simplification are
also GEOS operations. Repaired polygon leaves are sorted by normalized WKB.
Nonpolygon remnants are recorded, not converted into invented building areas.
Area cutoff is 1e-6 m², triangle cutoff 1e-10 m². All threshold losses are logged.
Earcut is explicitly selected, so installing another backend cannot silently
change results. Library versions are pinned; determinism was verified for the
Windows/Python 3.12 stack, not across arbitrary GEOS/platform versions.

Each complete part belongs to one 500 m ENU cell by a GEOS representative point.
Building parts crossing cell boundaries remain intact. Tile vertices are local;
glTF node transforms locate them in the theater. Mesh export uses trimesh's flat
vertex splitting and explicit one-sided neutral grey material. GLB uses
`(east, up, -north)` meters; Blender imports back to `(east, north, up)`.

## Official Blender MCP inspection

Use `blender_official.execute_blender_code` to load the inspection helper and run:

```python
exec(compile(open('D:/AI Work/Skyfront/tools/citygen_v2/blender_inspect.py', encoding='utf-8').read(), 'blender_inspect.py', 'exec'))
result = inspect('D:/AI Work/Skyfront', 'D:/AI Work/Skyfront/unreal/Saved/CitygenV2/run-01')
```

It creates new scenes, imports unchanged meshes, and measures imported faces.
The old comparison file is the **existing local** old-pipeline GLB: verify its
SHA against the report before making historical comparisons. It is not silently
regenerated at the current checkout.

Use `view(scene, target, eye)` to inspect, then call `screenshot(path)` in the
next MCP call. Keep Blender visible, verify the scene title/actual frame, and
check the resulting image: minimized windows can return stale framebuffers.
No Blender mesh editing, manual modeling, material workarounds or geometry export
is performed. The `Accepted_Sample` scene name means local checks only; its final
Blender gate failed. An existing unsaved session is preserved.

## Deliberate stop

The CLI exposes audit and sample stages only. Full Xinyi, Taipei 101 v2 mesh,
Unreal import, and full-city streaming implementation were not attempted after
the sample failed. WorldModel still preserves the existing eight-record hero
suppression and known anchor; the existing 508 m hero remains untouched. This is
a reviewable failed production-method experiment, not a completed replacement.
