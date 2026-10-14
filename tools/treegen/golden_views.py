"""Render the golden reference .blend at extra camera specs (views.json), read-only (the .blend is never saved).

blender -b <golden.blend> -noaudio --python tools/treegen/golden_views.py -- <views.json> <out_dir> <view,view,...> [samples]

The golden stage ground is 400 m; the AGL cameras sit outside it, so the ground is enlarged x10 in memory
(same 4 km ground as the UE level). Everything else - sun, sky, exposure, tree - is the golden scene as committed.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1 :]
spec = {v["name"]: v for v in json.load(open(a[0]))["views"]}
out_dir, names = os.path.abspath(a[1]), a[2].split(",")  # absolute: Blender resolves relative render paths oddly
samples = int(a[3]) if len(a) > 3 else 112
os.makedirs(out_dir, exist_ok=True)
sc = bpy.context.scene
sc.cycles.samples = samples
bpy.data.objects["TG_Ground"].scale = (10.0, 10.0, 1.0)
for n in names:
    v = spec[n]
    cam = bpy.data.objects.new("CAM_" + n + "_x", bpy.data.cameras.new("CAM_" + n + "_x"))
    sc.collection.objects.link(cam)
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.lens = cam.data.sensor_width / 2 / math.tan(math.radians(v["hfov_deg"]) / 2)
    cam.data.clip_end = 5000
    cam.location = v["loc"]
    cam.rotation_euler = Vector(v["fwd"]).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.filepath = os.path.join(out_dir, "v1_%s.png" % n)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)
