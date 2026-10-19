"""Distance-layer look-dev views: <run>/views_dl.json = the PR #46 north flight + the 6 PR #46 review stills + 4 distance-layer stills.

The new stills each look across the whole 0-1.5 / 1.5-4 / 4-8 / 8+ km band structure of the Tatun group (camera ground distance to the
look-at point in brackets):
  dl_layers_north   250 m AGL on the Sanzhi north slope -> Qixingshan (~8 km): every band in one frame
  dl_far_range      400 m over the Jinshan coast -> Zhuzishan / Qixingshan (~10 km): far mountain form + air perspective
  dl_mid_ridge      180 m AGL south of Qingtiangang -> Zhuzishan (~7 km): grassland, forest edge, mid-distance canopy
  dl_datun_west     350 m AGL west of Mianshan -> Datun / Qixing (~6-9 km): long ridge silhouettes
    python tools/ntw/forest_world/dl_views.py <run_dir>
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from flight_path import sample, ue  # noqa: E402

NEW = [
    ("dl_layers_north", (300_200, 2_791_300, 250, True), (305_790, 2_784_800, 900)),
    ("dl_far_range", (314_200, 2_792_600, 400, False), (305_800, 2_786_000, 700)),
    ("dl_mid_ridge", (307_300, 2_782_200, 180, True), (306_760, 2_789_610, 900)),
    ("dl_datun_west", (297_000, 2_786_500, 350, True), (302_650, 2_785_670, 900)),
]


def main(run):
    run = Path(run)
    v = json.loads((run / "views_north.json").read_text(encoding="utf-8"))
    h = np.load(run / "height_q.npy").astype(np.float64)
    for name, (pe, pn, pz, agl), (le, ln, lz) in NEW:
        g = sample(h, pe, pn)
        z = max(g, 0.0) + pz if agl else pz
        d = (le - pe, ln - pn, lz - z)
        yaw = math.degrees(math.atan2(-d[1], d[0]))
        pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
        v["stills"].append({"name": name, "ue_loc_cm": ue(pe, pn, z), "ue_rot": [0.0, pitch, yaw], "ground_m": g, "cam_z_m": z,
                            "look_dist_km": math.hypot(d[0], d[1]) / 1000.0})
    (run / "views_dl.json").write_text(json.dumps(v) + "\n", encoding="utf-8")
    print([(s["name"], round(s["cam_z_m"]), round(s.get("look_dist_km", 0), 1)) for s in v["stills"]])


if __name__ == "__main__":
    main(sys.argv[1])
