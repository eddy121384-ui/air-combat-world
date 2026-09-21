"""Read an existing GLB's raw buffers to diagnose strict gate failures.

Does not change source, meshes, triangulation, thresholds, or selected IDs.
Used with the original PR #6 CI artifact, independently of trimesh GLB loading.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from shapely.geometry import shape
from geometry import extrude_geos_polygon
from strict_qa import strict_mesh_gate
import trimesh


def raw_meshes(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', data)
    if magic != b'glTF' or version != 2 or length != len(data):
        raise ValueError('invalid GLB header')
    doc, binary, offset = None, None, 12
    while offset < len(data):
        size, kind = struct.unpack_from('<I4s',data,offset)
        chunk = data[offset+8:offset+8+size]
        if kind == b'JSON':
            doc = json.loads(chunk)
        elif kind == b'BIN\0':
            binary = chunk
        offset += 8+size
    def accessor(index):
        a = doc['accessors'][index]
        view = doc['bufferViews'][a['bufferView']]
        dtype = {5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
        width = {'SCALAR':1,'VEC3':3}[a['type']]
        start = view.get('byteOffset',0)+a.get('byteOffset',0)
        stride = view.get('byteStride',np.dtype(dtype).itemsize*width)
        return np.ndarray((a['count'],width),dtype=dtype,buffer=binary,
                          offset=start,strides=(stride,np.dtype(dtype).itemsize)).copy()
    result = {}
    for node in doc['nodes']:
        if 'mesh' not in node:
            continue
        if any(k in node for k in ['matrix','translation','rotation','scale']):
            raise ValueError('diagnostic expects PR #6 identity-transform nodes')
        primitives = doc['meshes'][node['mesh']]['primitives']
        if len(primitives) != 1 or primitives[0].get('mode',4) != 4:
            raise ValueError('diagnostic expects one triangle primitive per node')
        p = primitives[0]
        vertices = accessor(p['attributes']['POSITION']).astype(np.float64)
        faces = accessor(p['indices']).reshape(-1,3)
        result[node['name']] = (vertices,faces)
    return result


def diagnose(report_path, baseline_glb, output):
    report = json.loads(report_path.read_text())
    raw = raw_meshes(baseline_glb)
    failures, totals = [], {'zero_area_triangles':0,'wrong_roof_triangles':0,
                            'wrong_base_triangles':0,'nonfinite_vertices':0,'wrong_wall_triangles':0}
    passed = 0
    for b in report['buildings']:
        building_pass = True
        for part in b['mesh_parts']:
            footprint = shape(part['expected_footprint_enu'])
            v,f = raw[part['node_name']]
            mesh = trimesh.Trimesh(vertices=v,faces=f,process=False)
            gate = strict_mesh_gate(mesh,footprint,b['height_m'],precision='float32')
            building_pass &= gate['pass']
            for key in totals:
                totals[key] += gate.get(key,0)
            if gate['pass']:
                continue
            original = extrude_geos_polygon(footprint,b['height_m'])
            same_faces = bool(np.array_equal(original.faces,f))
            if not same_faces:
                raise ValueError('Cannot correlate raw face index to regenerated double mesh')
            tri = v[f]
            cross = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            roof = np.all(np.isclose(tri[:,:,1],b['height_m'],atol=gate['tolerances']['height_m'],rtol=0),axis=1)
            examples = []
            for index in np.flatnonzero(roof & (cross[:,1] < 0)):
                t64 = original.triangles[index]
                area64 = float(np.cross(t64[1]-t64[0],t64[2]-t64[0])[1]/2)
                examples.append({'face_index':int(index),'signed_area_float64_m2':area64,
                                 'signed_area_float32_m2':float(cross[index,1]/2),
                                 'float64_triangle_gltf_m':t64.tolist(),
                                 'raw_float32_triangle_gltf_m':tri[index].tolist()})
            failures.append({'building_id':b['building_id'],'polygon_index':b['polygon_index'],
                             'repaired_part_index':part['repaired_part_index'],
                             'failures':gate['failures'], 'identical_face_indices':same_faces,
                             'max_coordinate_rounding_m':float(np.max(abs(v-original.vertices))),
                             'cap_overlap_m2':gate['caps']['roof']['overlap_m2'],
                             'flipped_roof_triangles':examples})
        passed += int(building_pass)
    result = {'baseline_glb_sha256':hashlib.sha256(baseline_glb.read_bytes()).hexdigest(),
              'baseline_report_sha256':report['baseline_selection']['baseline_report_sha256'],
              'source_sha256':report['input']['sha256'],
              'raw_buffer_decoder':'struct/NumPy accessors, no trimesh loader or mesh repair',
              'raw_glb_parts_pass':passed,'raw_glb_parts_fail':len(report['buildings'])-passed,
              'raw_glb_totals':totals,'failures':failures,
              'cause':'Near-collinear cap triangles reverse signed area under global-coordinate float32 quantization; topology and positive volume alone do not detect this.',
              'blender':'not_run_numerical_gate_failed','screenshots':[],
              'final_verdict':'FAIL; not ready for full Xinyi tiled generation'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'failures'},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--baseline-glb',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    diagnose(args.report,args.baseline_glb,args.out)
