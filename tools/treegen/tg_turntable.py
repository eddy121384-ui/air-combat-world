"""Quick silhouette check: render a saved tree .blend from N azimuths at a given elevation (low cost).

blender -b <file.blend> --python tools/treegen/tg_turntable.py -- <out_prefix> [n=6] [elev_deg=35] [samples=12] [res=640x360] [target_z=7] [dist=36]
"""
import math
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1 :]
prefix = a[0]
n = int(a[1]) if len(a) > 1 else 6
elev = math.radians(float(a[2]) if len(a) > 2 else 35)
samples = int(a[3]) if len(a) > 3 else 12
w, h = (a[4] if len(a) > 4 else "640x360").split("x")
sc = bpy.context.scene
sc.cycles.samples = samples
sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
br = bpy.data.objects["MachilusThunbergii_branches"] if "MachilusThunbergii_branches" in bpy.data.objects else None
target = Vector((0, 0, float(a[5]) if len(a) > 5 else 7.0))  # optional target height / distance (tall 柳杉: 12 / 58)
dist = float(a[6]) if len(a) > 6 else 36.0
cam = bpy.data.objects.new("CAM_tt", bpy.data.cameras.new("CAM_tt"))
cam.data.lens = 35
sc.collection.objects.link(cam)
sc.camera = cam
for k in range(n):
    az = 2 * math.pi * k / n
    loc = target + Vector((math.cos(elev) * math.sin(az), -math.cos(elev) * math.cos(az), math.sin(elev))) * dist
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{prefix}_az{int(math.degrees(az)):03d}.png"
    bpy.ops.render.render(write_still=True)
