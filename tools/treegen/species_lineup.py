"""Species lineup on the shared golden stage: the opened golden .blend stays at x = 0, other goldens are appended read-only beside it.

blender -b <tree.blend> --python tools/treegen/species_lineup.py -- <out_dir> <res WxH> <samples> <other.blend>:<ObjectPrefix>:<x_m> [...]
Views: eye-level front, 32 deg oblique, orthographic top, far 'flight' view (~200 m slant, 85 mm).
"""
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1 :]
OUT, (W, H), SPP = a[0], [int(v) for v in a[1].split("x")], int(a[2])
os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene
sc.cycles.samples = SPP
sc.render.resolution_x, sc.render.resolution_y = W, H
for o in list(sc.objects):
    if o.type == "CAMERA" or o.name.startswith("TG_ScaleFigure"):
        bpy.data.objects.remove(o)
for spec in a[3:]:
    path, prefix, x = spec.rsplit(":", 2)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith(prefix + "_")]
    for o in dst.objects:
        sc.collection.objects.link(o)
        o.location.x += float(x)
bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.7, vertices=16, location=(5.0, -6.0, 0.85))


def cam(name, loc, tgt, lens=35.0, ortho=None):
    c = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    c.data.lens, c.data.clip_end = lens, 3000
    if ortho:
        c.data.type, c.data.ortho_scale = "ORTHO", ortho
    sc.collection.objects.link(c)
    c.location = loc
    d = Vector(tgt) - Vector(loc)
    c.rotation_euler = (0, 0, 0) if abs(d.normalized().z) > 0.99 else d.to_track_quat("-Z", "Y").to_euler()
    return c


for k, c in {"front": cam("C_front", (0, -66, 6.0), (0, 0, 10.5)), "oblique": cam("C_oblique", (30, -70, 48), (0, 0, 8.0), lens=40),
             "top": cam("C_top", (0, 0, 90), (0, 0, 0), ortho=52), "flight": cam("C_flight", (70, -170, 110), (0, 0, 8), lens=85)}.items():
    sc.camera = c
    sc.render.filepath = os.path.join(OUT, "lineup_%s.png" % k)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
