"""Run through official Blender MCP after importing the exact gated GLB.

Reads bpy mesh data without welding, triangulating, repairing or applying
transforms. Scalar double-precision predicates are independent of trimesh QA.
Exports imported buffers for a second GEOS coverage/hole/wall audit outside bpy.
"""
import collections
import hashlib
import json
import math
from pathlib import Path

import bpy


def audit_import(scene, numerical_path, glb_path, output_path):
    numerical = json.loads(Path(numerical_path).read_text(encoding='utf-8'))
    digest = hashlib.sha256(Path(glb_path).read_bytes()).hexdigest()
    assert numerical['selected_all_pass'] and digest == numerical['output_glb_sha256']
    expected = {p['node_name']:(b,p) for b in numerical['buildings'] for p in b['mesh_parts']}
    actual = {o.name:o for o in scene.objects if o.type == 'MESH'}
    assert actual.keys() == expected.keys(), 'imported node identity mismatch'
    totals = collections.Counter()
    rows = []
    for name, obj in actual.items():
        b, expected_part = expected[name]
        vertices = [tuple(float(c) for c in v.co) for v in obj.data.vertices]
        faces = [list(p.vertices) for p in obj.data.polygons]
        counts = collections.Counter()
        counts['nonfinite_vertices'] = sum(not all(math.isfinite(c) for c in v) for v in vertices)
        counts['nontriangle_faces'] = sum(len(f) != 3 for f in faces)
        edges = collections.Counter()
        balance = collections.Counter()
        volume = 0.
        height_error = expected_part['float32_glb_roundtrip']['tolerances']['height_m']
        for polygon, face in zip(obj.data.polygons,faces):
            if len(face) != 3:
                continue
            a,bv,c = [vertices[i] for i in face]
            u = [bv[i]-a[i] for i in range(3)]
            v = [c[i]-a[i] for i in range(3)]
            cross = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            length = math.sqrt(sum(x*x for x in cross))
            counts['zero_area_triangles'] += length/2 <= 1e-8
            roof = all(abs(vertices[i][2]-b['height_m']) <= height_error for i in face)
            base = all(abs(vertices[i][2]) <= height_error for i in face)
            nz = cross[2]/length if length else 0.
            counts['wrong_roof_triangles'] += roof and nz <= .999
            counts['wrong_base_triangles'] += base and nz >= -.999
            counts['blender_wrong_roof_polygon_normals'] += roof and polygon.normal.z <= .999
            counts['blender_wrong_base_polygon_normals'] += base and polygon.normal.z >= -.999
            volume += (a[0]*(bv[1]*c[2]-bv[2]*c[1]) + a[1]*(bv[2]*c[0]-bv[0]*c[2])
                       + a[2]*(bv[0]*c[1]-bv[1]*c[0]))/6
            for i,j in zip(face,face[1:]+face[:1]):
                # Exact-position topology only; no mutation of imported mesh.
                vi,vj = vertices[i],vertices[j]
                key = tuple(sorted((vi,vj)))
                edges[key] += 1
                balance[key] += 1 if vi < vj else -1
        counts['nonmanifold_edges'] = sum(n != 2 for n in edges.values())
        counts['inconsistent_edges'] = sum(n != 0 for n in balance.values())
        counts['nonpositive_volume'] = not math.isfinite(volume) or volume <= 0
        matrix = [[float(c) for c in r] for r in obj.matrix_world]
        ox,oy = b['tile_origin_enu_m']
        expected_matrix = [[1.,0.,0.,ox],[0.,1.,0.,oy],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        counts['wrong_tile_transforms'] = matrix != expected_matrix
        failures = [f'{k}:{int(v)}' for k,v in counts.items() if v]
        totals.update(counts)
        rows.append({'node_name':name,'building_id':b['building_id'],'polygon_index':b['polygon_index'],
                     'pass':not failures, 'failures':failures,'counts':dict(counts),
                     'volume_m3':volume,'vertices_local_enu':vertices,'faces':faces,'matrix_world':matrix})
    report = {'source':'official Blender MCP / bpy imported mesh buffers',
              'blender_version':bpy.app.version_string,'scene':scene.name,'glb_sha256':digest,
              'mesh_count':len(rows),'passed':sum(r['pass'] for r in rows),
              'failed':sum(not r['pass'] for r in rows),'totals':dict(totals),'objects':rows}
    output = Path(output_path)
    assert not output.exists(), 'refusing to overwrite evidence'
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k != 'objects'}
