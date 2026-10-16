"""Render the four review views (CAM_front / oblique / top / close) of a saved golden .blend (so the game export can read the .blend
while the slow final renders run).

blender -b <tree.blend> --python tools/treegen/tg_render_saved.py -- <out_dir> <tag> [samples=128] [res=1920x1080]
"""
import os
import sys

import bpy

a = sys.argv[sys.argv.index("--") + 1 :]
out, tag = a[0], a[1]
sc = bpy.context.scene
sc.cycles.samples = int(a[2]) if len(a) > 2 else 128
w, h = (a[3] if len(a) > 3 else "1920x1080").split("x")
sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
for v in ("front", "oblique", "top", "close"):
    sc.camera = bpy.data.objects["CAM_" + v]
    sc.render.filepath = os.path.join(out, "%s_%s.png" % (tag, v))
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
