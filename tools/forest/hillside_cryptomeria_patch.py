"""柳杉 unreal v1: a small 柳杉 plantation block inside the existing 象山 two-species forest (in-scene recognisability check, not a forest study).

    python tools/forest/hillside_cryptomeria_patch.py <terrain_dir> [cx cy]
Reads instances_acacia.json (PR #36 forest B: 紅楠 A + crown B + 相思樹, read only) and writes instances_cryptomeria.json (+ cryptomeria_patch.json):
every tree whose crown centre lies in a 46 m x 40 m block (rotated 20 deg, centred at cx, cy; default (-15, 20) m - north of the flyover line,
in view of all stills) is removed and replaced by a plantation: rows 4.0 m apart, trees 4.0 m apart in the row (+-0.4 m jitter, 6 % gaps),
even-aged (height 18-23 m: scale_z 0.74-0.95 of the 24.3 m golden), crowded crowns narrower (scale_xy 0.72-0.86), random yaw, lean <= 2 deg,
leaf tints 8 (as imported) / 9 (lighter, 30 % on the block's sunnier half). Plantation = regular spacing, even age, sharp block edges - the
look of the 頂山-石梯嶺 stands. Everything outside the block is unchanged.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from hillside_scatter import Terrain  # noqa: E402

J_SPHERE_R, J_CROWN_Z = 12.78, 12.66  # m at scale 1 (UE bounds of the imported 柳杉 mesh)
SIZE, ROT, ROW, STEP = (46.0, 40.0), 20.0, 4.0, 4.0
SEED = 20261019


def main(d, cx=-15.0, cy=20.0):
    d = Path(d)
    T = Terrain(d)
    src = json.loads((d / "instances_acacia.json").read_text(encoding="utf-8"))
    h_ref = src["h_ref_m"]
    rng = np.random.default_rng(SEED)
    c, s = math.cos(math.radians(ROT)), math.sin(math.radians(ROT))

    def local(x, y):
        dx, dy = x - cx, y - cy
        return dx * c + dy * s, -dx * s + dy * c

    def inside(x, y, pad=0.0):
        u, v = local(x, y)
        return abs(u) <= SIZE[0] / 2 + pad and abs(v) <= SIZE[1] / 2 + pad

    keep, removed = [], {}
    for it in src["instances"]:
        ccx, ccy = it.get("crown_centre_m", [it["x_m"], it["y_m"]])
        if inside(ccx, ccy):
            removed[it["form"]] = removed.get(it["form"], 0) + 1
        else:
            keep.append(it)
    new = []
    gx, gy = T.sample(T.gx, cx, cy)[0], T.sample(T.gy, cx, cy)[0]
    down = math.atan2(-gy, -gx)
    for i in np.arange(-SIZE[0] / 2 + ROW / 2, SIZE[0] / 2, ROW):
        for j in np.arange(-SIZE[1] / 2 + STEP / 2, SIZE[1] / 2, STEP):
            if rng.random() < 0.06:
                continue
            u, v = i + rng.uniform(-0.4, 0.4), j + rng.uniform(-0.4, 0.4)
            x, y = cx + u * c - v * s, cy + u * s + v * c
            sl = float(T.sample(T.slope, x, y)[0])
            z = float(T.height(x, y)[0]) - (0.25 + 0.35 * math.tan(math.radians(min(sl, 60.0))))
            sxy, sz = rng.uniform(0.72, 0.86), rng.uniform(0.74, 0.95)
            sunny = (u * math.cos(down) + v * math.sin(down)) > 0  # downslope half
            var = 9 if rng.random() < (0.3 if sunny else 0.1) else 8
            new.append({"id": 100000 + len(new), "form": "J", "variant": var, "x_m": round(x, 3), "y_m": round(y, 3), "z_m": round(z, 3),
                        "ue_cm": [round(x * 100, 1), round(-y * 100, 1), round((z - h_ref) * 100, 1)], "yaw_deg": round(rng.uniform(0, 360), 2),
                        "lean_east_deg": round(rng.uniform(-2, 2), 2), "lean_north_deg": round(rng.uniform(-2, 2), 2),
                        "scale_xy": round(sxy, 4), "scale_x": round(sxy, 4), "scale_y": round(sxy, 4), "scale_z": round(sz, 4),
                        "crown_r_m": round(3.6 * sxy, 3), "sphere_r_m": J_SPHERE_R, "crown_z_m": J_CROWN_Z, "crown_centre_m": [round(x, 3), round(y, 3)]})
    out = keep + new
    st = {"centre_m": [cx, cy], "size_m": SIZE, "rotation_deg": ROT, "spacing_m": [ROW, STEP], "removed_by_form": removed,
          "cryptomeria_added": len(new), "variants": {"8": sum(1 for n in new if n["variant"] == 8), "9": sum(1 for n in new if n["variant"] == 9)},
          "trees_total": len(out), "height_m": [round(24.3 * min(n["scale_z"] for n in new), 1), round(24.3 * max(n["scale_z"] for n in new), 1)]}
    (d / "instances_cryptomeria.json").write_text(json.dumps({"stats": st, "h_ref_m": h_ref, "instances": out}, indent=0) + "\n", encoding="utf-8")
    (d / "cryptomeria_patch.json").write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(st))


if __name__ == "__main__":
    main(sys.argv[1], *(float(a) for a in sys.argv[2:4]))
