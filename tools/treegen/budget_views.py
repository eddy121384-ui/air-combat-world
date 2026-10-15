"""Extra slant-distance cameras for the tree-budget experiment (research/forest-tree-lod-budget-v1).

python tools/treegen/budget_views.py <game_out_dir>

Writes <game_out_dir>/views_budget.json = views.json + sl150 / sl300 / sl500 / sl1000: same bearing and depression
angle (~16.7 deg, the agl50 camera: eye = target + d * u, u = normalize(40, -140, 44)), same target (0, 0, 6), 60 deg hfov.
The distance is the SLANT distance from the camera to the tree centre, not AGL.
"""
import json
import os
import sys

import numpy as np

game = sys.argv[1]
v = json.load(open(os.path.join(game, "views.json")))
tgt = np.array([0.0, 0.0, 6.0])
u = np.array([40.0, -140.0, 44.0])
u /= np.linalg.norm(u)
have = {x["name"] for x in v["views"]}
for d in (150, 300, 500, 1000):
    name = "sl%d" % d
    if name in have:
        continue
    eye = tgt + d * u
    f = (tgt - eye) / np.linalg.norm(tgt - eye)
    v["views"].append(dict(name=name, loc=[round(float(x), 4) for x in eye], fwd=[round(float(x), 6) for x in f],
                           hfov_deg=60.0, res=[1920, 1080], slant_m=d, agl_m=round(float(eye[2] - 0.0), 2)))
v["note"] += "; sl* views added by tools/treegen/budget_views.py"
json.dump(v, open(os.path.join(game, "views_budget.json"), "w"), indent=1)
print([(x["name"], x.get("slant_m"), x.get("agl_m")) for x in v["views"] if x["name"].startswith("sl")])
