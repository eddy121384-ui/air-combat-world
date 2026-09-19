"""Read-only source/legacy accounting and mature-backend failure diagnosis.

This audit calls the unchanged legacy triangulator solely to cross-tabulate its
old skip labels. The v2 generator never uses that triangulator.
"""
from collections import Counter
import json
import math
from pathlib import Path
import argparse

import numpy as np
import trimesh
import shapely

from tools.citygen_v2.build import audit, sha, write_json


def diagnose(output):
    summary, rows, parts, wm = audit()
    sample = json.loads((output/'sample.json').read_text())
    from tools.compiler.geo import triangulate  # historical classification only
    legacy = {}
    for b in wm['buildings']:
        if b['suppressed']:
            continue
        for i, p in enumerate(b['polygons']):
            results = list(triangulate([p['footprint_enu']]))
            status = ('emitted' if any(t for r,t in results) else
                      'zero_area' if any(len(r)<3 for r,t in results) else 'self_intersecting')
            legacy[f"{b['id']}/part-{i}"] = status
    cross = Counter(legacy[r['key']]+' -> '+r['outcome'] for r in rows if r['key'] in legacy)
    failures = []
    for f in sample['failures']:
        p = parts[f['key']][f['component']]
        row = next(r for r in rows if r['key'] == f['key'])
        mesh = trimesh.creation.extrude_polygon(p, row['height_m'], engine='earcut')
        contacts = [p.exterior.intersection(h).wkt for h in p.interiors]
        counts = np.bincount(mesh.edges_unique_inverse)
        failures.append({**f, 'polygon_valid':p.is_valid, 'footprint_wkt':p.wkt,
                         'height_m':row['height_m'], 'shell_hole_contacts':contacts,
                         'shell_hole_distance_m':[p.exterior.distance(h) for h in p.interiors],
                         'double_precision_watertight':mesh.is_watertight,
                         'double_precision_min_triangle_area_m2':float(mesh.area_faces.min()),
                         'edge_incidence_not_two':int(np.count_nonzero(counts!=2)),
                         'bad_edges':[{'positions':mesh.vertices[e].tolist(),'incidence':int(c)}
                                      for e,c in zip(mesh.edges_unique[counts!=2],counts[counts!=2])]})
    tile_owners = Counter()
    for row in rows:
        if row['suppressed'] or not parts[row['key']]:
            continue
        point = shapely.union_all(parts[row['key']]).representative_point()
        tile_owners[f'{math.floor(point.x/500)},{math.floor(point.y/500)}'] += 1
    result = {
        'source_sha256':summary['source_sha256'], 'legacy_to_geos':dict(cross),
        'rejected_repair_types':dict(Counter(r['repair_result_type'] for r in rows if r['outcome']=='rejected')),
        'sample_failure_diagnosis':failures, 'potential_500m_ownership_tiles':dict(tile_owners),
        'nonhero_polygonal_parts':sum(tile_owners.values()),
        'nonhero_polygonal_features':len({r['feature_id'] for r in rows if parts[r['key']] and not r['suppressed']}),
        'sample_labels':dict(Counter(tag for tags in sample['selection_reasons'].values() for tag in tags)),
        'sample_triangular_components':sum(r['output_triangle_footprints'] for r in rows if r['key'] in sample['selected_parts']),
        'sample_all_file_bytes':sum(p.stat().st_size for p in (output/'sample').glob('*.glb')),
        'all_glb_hashes':{p.name:sha(p) for p in sorted((output/'sample').glob('*.glb'))},
    }
    write_json(output/'diagnosis.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('sample_failure_diagnosis','all_glb_hashes')},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('output',type=Path)
    diagnose(parser.parse_args().output)
