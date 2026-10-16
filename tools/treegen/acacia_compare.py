"""Side-by-side species check on the shared golden stage: 紅楠 v1 (left) and 相思樹 v1 (right), same sun / sky / exposure.

blender -b <acacia_v1.blend> --python tools/treegen/acacia_compare.py -- <machilus_v1.blend> <out_dir> [--res 1920x1080] [--samples 96]
The 紅楠 golden is appended read-only (its file is never saved). Views: eye-level front, 32 deg oblique, orthographic top and a
far 'flight' view (~180 m slant, 85 mm) - the range at which a player has to tell the species apart.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1 :]
MACH, OUT = a[0], a[1]
res, samples = (1920, 1080), 96
for i, x in enumerate(a):
    if x == "--res":
        res = tuple(int(v) for v in a[i + 1].split("x"))
    if x == "--samples":
        samples = int(a[i + 1])
os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene
sc.cycles.samples = samples
sc.render.resolution_x, sc.render.resolution_y = res
for o in list(sc.objects):  # drop the single-tree cameras / scale figure; keep sun, ground, tree
    if o.type == "CAMERA" or o.name.startswith("TG_ScaleFigure"):
        bpy.data.objects.remove(o)
with bpy.data.libraries.load(MACH, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith("MachilusThunbergii_")]
for o in dst.objects:
    sc.collection.objects.link(o)
    o.location.x -= 10.0
for name in ("AcaciaConfusa_branches", "AcaciaConfusa_sprays"):
    bpy.data.objects[name].location.x += 9.0
bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.7, vertices=16, location=(0.0, -4.0, 0.85))


def cam(name, loc, tgt, lens=35.0, ortho=None):
    c = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    c.data.lens = lens
    c.data.clip_end = 3000
    if ortho:
        c.data.type, c.data.ortho_scale = "ORTHO", ortho
    sc.collection.objects.link(c)
    c.location = loc
    d = Vector(tgt) - Vector(loc)
    c.rotation_euler = (0, 0, 0) if abs(d.normalized().z) > 0.99 else d.to_track_quat("-Z", "Y").to_euler()
    return c


views = {
    "front": cam("C_front", (0, -46, 4.5), (0, 0, 6.2)),
    "oblique": cam("C_oblique", (24, -52, 36), (0, 0, 5.5), lens=40),
    "top": cam("C_top", (0, 0, 80), (0, 0, 0), ortho=42),
    "flight": cam("C_flight", (60, -150, 95), (0, 0, 6), lens=85),
}
for k, c in views.items():
    sc.camera = c
    sc.render.filepath = os.path.join(OUT, "pair_%s.png" % k)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
