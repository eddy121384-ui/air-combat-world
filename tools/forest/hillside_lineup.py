"""相思樹 lookdev v1: species lineup on the Xiangshan test terrain (UE visual check of the imported 相思樹 next to the 紅楠 chains).

    python tools/forest/hillside_lineup.py <terrain_dir>
Writes <terrain_dir>/instances_lineup.json (3 trees at scale 1 in a W-E row on the flat basin floor SW of the block: 紅楠 A (form A, the
chain passed to hf_build), 紅楠 crown B, 相思樹 (form C), 22 m apart) and views_lineup.json (the views.json schema: 3 stills - eye level,
32 deg oblique, ~200 m aerial - and the unchanged views.json flight, which hf_build needs for its flight map). Built with
run_hf_all.ps1 -Instances instances_lineup.json -ViewsFile views_lineup.json, so the lineup goes through the same build / fresh-process
material gate / native MRQ path as the forest.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hillside_scatter import Terrain  # noqa: E402

ROW_Y, ROW_X0, STEP = -324.0, -446.0, 22.0
TREES = [("A", 0, 8.377, 7.1), ("B", 3, 9.067, 6.07), ("C", 5, 8.22, 6.69)]  # form, leaf variant, sphere r, crown-centre z (hillside_mix / acacia_mix)


def main(d, with_j=False):
    d = Path(d)
    T = Terrain(d)
    V = json.loads((d / "views.json").read_text(encoding="utf-8"))
    h_ref = T.meta["landscape"]["h_ref_m"]
    inst = []
    trees = TREES + ([("J", 8, 12.78, 12.66)] if with_j else [])  # 柳杉 unreal v1: 4th tree, 24 m tall
    for k, (form, var, sr, cz) in enumerate(trees):
        x, y = ROW_X0 + k * STEP, ROW_Y
        z = float(T.height(x, y)[0]) - 0.25
        inst.append({"id": k, "form": form, "variant": var, "x_m": x, "y_m": y, "z_m": round(z, 3),
                     "ue_cm": [round(x * 100, 1), round(-y * 100, 1), round((z - h_ref) * 100, 1)], "yaw_deg": 0.0 if form != "C" else 180.0,
                     "lean_east_deg": 0.0, "lean_north_deg": 0.0, "scale_xy": 1.0, "scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0,
                     "crown_r_m": 7.0, "sphere_r_m": sr, "crown_z_m": cz})
    cx = ROW_X0 + STEP * (1.5 if with_j else 1.0)
    g = float(T.height(cx, ROW_Y)[0])

    def still(name, dist, height, pitch, bearing):
        # camera at `dist` m from the middle tree, opposite the viewing bearing (deg clockwise from north), `height` m above its ground
        b = math.radians(bearing)
        px, py = cx - dist * math.sin(b), ROW_Y - dist * math.cos(b)
        pz = float(T.height(px, py)[0]) + height
        return {"name": name, "agl_m": height, "pitch_deg": pitch, "bearing_deg": bearing, "pos_local_m": [round(px, 2), round(py, 2), round(pz, 2)],
                "ue_loc_cm": [round(px * 100, 1), round(-py * 100, 1), round((pz - h_ref) * 100, 1)], "ue_rot": [0.0, pitch, bearing - 90.0],
                "lod_calc_in_frustum": []}

    # aim the eye-level and oblique views at ~6 m above the row
    eye = still("lineup_eye", 78.0 if with_j else 58.0, 5.0, round(-math.degrees(math.atan2(-1.0, 58.0)), 2), 0.0)
    eye["pitch_deg"] = eye["ue_rot"][1] = 6.0 if with_j else 1.0  # with 柳杉: frame the 24 m crown
    od = 84.0 if with_j else 62.0
    obl = still("lineup_oblique", od, 6.0 + od * math.tan(math.radians(32)), -32.0, 15.0)
    air = still("lineup_aerial", 140.0, 6.0 + 140.0 * math.tan(math.radians(45)), -45.0, 30.0)
    views = dict(V)
    views["stills"] = [eye, obl, air]
    sfx = "_j" if with_j else ""  # python tools/forest/hillside_lineup.py <dir> j -> *_lineup_j.json (4 trees incl. 柳杉)
    views["instances_file"] = "instances_lineup%s.json" % sfx
    views["note"] = "species lineup (hillside_lineup.py); flight copied unchanged from views.json"
    (d / ("views_lineup%s.json" % sfx)).write_text(json.dumps(views, indent=0) + "\n", encoding="utf-8")
    (d / ("instances_lineup%s.json" % sfx)).write_text(json.dumps({"stats": {"trees": len(inst), "ground_m": g}, "h_ref_m": h_ref, "instances": inst}, indent=1) + "\n",
                                             encoding="utf-8")
    print(json.dumps(views["stills"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1], len(sys.argv) > 2 and sys.argv[2] == "j")
