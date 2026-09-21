"""Diagnose Blender glTF axis conversion on one validated Xinyi building tile."""
import argparse, sys, json
from pathlib import Path
import bpy
from mathutils import Vector

argv=sys.argv
argv=argv[argv.index("--")+1:] if "--" in argv else []
p=argparse.ArgumentParser()
p.add_argument("--buildings",type=Path,required=True)
a=p.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
glb=sorted(a.buildings.glob("*.glb"))[0]
bpy.ops.import_scene.gltf(filepath=str(glb),merge_vertices=False,import_shading="NORMALS")
objs=[o for o in bpy.data.objects if o.type=="MESH"]
rows=[]
for o in objs[:20]:
    pts=[o.matrix_world @ Vector(c) for c in o.bound_box]
    rows.append({
      "name":o.name,
      "location":list(o.location),
      "rotation_euler":list(o.rotation_euler),
      "scale":list(o.scale),
      "matrix_world":[list(r) for r in o.matrix_world],
      "world_bounds_min":[min(p[i] for p in pts) for i in range(3)],
      "world_bounds_max":[max(p[i] for p in pts) for i in range(3)],
      "local_bounds_min":[min(c[i] for c in o.bound_box) for i in range(3)],
      "local_bounds_max":[max(c[i] for c in o.bound_box) for i in range(3)],
      "parent":o.parent.name if o.parent else None,
    })
print(json.dumps({"glb":glb.name,"objects":rows},indent=2))
