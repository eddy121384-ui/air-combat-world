"""GEOS strict checks on actual bpy-exported buffers, never original GLB data."""
import argparse
import json
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import shape
from strict_qa import strict_mesh_gate


def check(numerical_path, imported_path, output_path):
    numerical = json.loads(numerical_path.read_text(encoding='utf-8'))
    imported = json.loads(imported_path.read_text(encoding='utf-8'))
    assert numerical['output_glb_sha256'] == imported['glb_sha256']
    refs = {p['node_name']:(b,p) for b in numerical['buildings'] for p in b['mesh_parts']}
    assert set(refs) == {o['node_name'] for o in imported['objects']}
    rows = []
    for obj in imported['objects']:
        b,p = refs[obj['node_name']]
        enu = np.asarray(obj['vertices_local_enu'],dtype=np.float64)
        vertices = enu[:,[0,2,1]] * [1,1,-1]  # Blender Z-up -> glTF Y-up.
        mesh = trimesh.Trimesh(vertices=vertices,faces=obj['faces'],process=False)
        gate = strict_mesh_gate(mesh,shape(p['expected_footprint_local']),b['height_m'],precision='float32')
        gate.update(node_name=obj['node_name'],building_id=b['building_id'],polygon_index=b['polygon_index'])
        rows.append(gate)
    result = {'source':'GEOS coverage/hole/wall QA of bpy-exported imported buffers',
              'glb_sha256':imported['glb_sha256'], 'passed':sum(r['pass'] for r in rows),
              'failed':sum(not r['pass'] for r in rows),
              'bpy_independent_passed':imported['passed'], 'bpy_independent_failed':imported['failed'],
              'pass':imported['failed']==0 and all(r['pass'] for r in rows), 'parts':rows}
    assert not output_path.exists(), 'refusing to overwrite evidence'
    output_path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'parts'},indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--numerical',type=Path,required=True)
    parser.add_argument('--imported',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if not check(args.numerical,args.imported,args.out)['pass']:
        raise SystemExit(2)
