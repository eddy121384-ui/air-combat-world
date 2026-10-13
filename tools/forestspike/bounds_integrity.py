"""Reconstruct all-LOD render bounds from preserved source GLBs (not UE readback)."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh

p = argparse.ArgumentParser()
p.add_argument('--repo', type=Path, required=True)
p.add_argument('--build', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
build = json.loads(a.build.read_text(encoding='utf-8'))
rows = {}
for key, rec in build['meshes'].items():
    if key == 'Tree_A':
        rows[key] = {'render_sphere_radius_cm': rec['policy']['sphere_radius_cm'],
                     'method': 'UE cached sphere for unchanged 28/28/28 automatic copies; independently bracketed by native render controls'}
        continue
    lods = []
    for lod in range(3):
        file = a.repo/'assets/forestspike/b0/models'/f'{key.removeprefix("Tree_B_")}_lod{lod}.glb'
        vertices = trimesh.load(file, force='scene').to_geometry().vertices * 100
        low, high = vertices.min(axis=0), vertices.max(axis=0)
        origin, extent = (low+high)/2, (high-low)/2
        radius = float(np.linalg.norm(vertices-origin, axis=1).max())
        lods.append({'file': str(file.relative_to(a.repo)).replace('\\', '/'),
                     'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                     'source_origin_cm': origin.tolist(), 'source_extent_cm': extent.tolist(), 'radius_cm': radius})
    # FBoxSphereBounds::Builder appends using operator+: union AABB center,
    # min(AABB diagonal, max(distance to old center + old sphere radius)).
    origin = np.array(lods[0]['source_origin_cm'])
    extent = np.array(lods[0]['source_extent_cm'])
    radius = lods[0]['radius_cm']
    for lod in lods[1:]:
        other, other_extent = np.array(lod['source_origin_cm']), np.array(lod['source_extent_cm'])
        low, high = np.minimum(origin-extent, other-other_extent), np.maximum(origin+extent, other+other_extent)
        center, size = (low+high)/2, (high-low)/2
        radius = min(float(np.linalg.norm(size)), max(float(np.linalg.norm(origin-center))+radius,
                                                      float(np.linalg.norm(other-center))+lod['radius_cm']))
        origin, extent = center, size
    error = abs(lods[0]['radius_cm']-rec['policy']['sphere_radius_cm'])
    assert error < 0.01, (key, error)
    rows[key] = {'render_sphere_radius_cm': radius, 'cached_lod0_radius_cm': rec['policy']['sphere_radius_cm'],
                 'lod0_cached_check_error_cm': error, 'all_lod_source_bounds': lods,
                 'method': 'Source-derived all-LOD FBoxSphereBounds union; axis permutation/reflection preserves radius. Not a direct RenderData Python readback.'}
out = {'status': 'PASS_FS_B01_SOURCE_BOUNDS_RECONSTRUCTION', 'meshes': rows,
       'scope': 'Diagnostic boundary placement only; common registered screen thresholds are unchanged. Native automatic draw/color controls independently validate predictions.',
       'engine_method': {'StaticMeshBuilder.cpp': 'MeshBoundsBuilder adds every LOD SourceMeshBounds at 1169; assigns RenderData.Bounds at 1211',
                         'BoxSphereBounds.h': 'Builder append/operator+ at 454-466',
                         'StaticMesh.cpp': 'GetBounds returns ExtendedBounds; editor UpdateBounds prefers CachedMeshDescriptionBounds (LOD0) at 7285-7317'}}
with a.out.open('x', encoding='utf-8') as f:
    json.dump(out, f, indent=2)
print({key: row['render_sphere_radius_cm'] for key, row in rows.items()})
