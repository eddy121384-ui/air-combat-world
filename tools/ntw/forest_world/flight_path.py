"""Camera flight + still poses for the forest world (offline, deterministic) -> <run>/views.json.

Flight: a fighter-style terrain-following pass, Tamsui river (Guandu) -> Beitou west hills -> Mianshan / Datun south flank ->
Zhuzihu valley -> Qixingshan east shoulder -> Qingtiangang grassland -> Huangzuishan ridge -> forested valleys -> Jinshan coast.
Centripetal Catmull-Rom through EPSG:3826 waypoints, resampled at constant ground speed; altitude = terrain envelope (max within
150 m) + per-waypoint AGL, climb/descent slope-limited, smoothed, then minimum clearance re-enforced. Camera looks along the path
(pitch = path angle + look-down), banks with turn rate.  Stills = fixed review / performance poses.

    python tools/ntw/forest_world/flight_path.py <run_dir> [--speed 240] [--fps 30]
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import ndimage

E0, N1, SP = 289_540.0, 2_800_000.0, 10.0
ORIGIN = (296_000.0, 2_760_000.0)
ROUTES = {
    # v1: Tamsui river -> Beitou west hills -> Datun south flank -> Zhuzihu -> Qingtiangang -> Jinshan (too much built-up foothill)
    "south": [(291_200, 2_778_900, 330), (294_000, 2_780_200, 260), (296_800, 2_781_700, 190), (299_700, 2_783_700, 170),
              (302_100, 2_784_500, 150), (304_100, 2_784_150, 140), (306_300, 2_783_700, 150), (307_900, 2_784_050, 120),
              (309_600, 2_785_200, 170), (311_300, 2_787_300, 160), (312_700, 2_789_300, 170), (314_200, 2_791_300, 260)],
    # v2 (hero): Sanzhi coast -> forested north flank of Datun / Zhuzishan -> saddle between Qixingshan and Zhuzishan ->
    # Qingtiangang grassland -> Huangzuishan ridge -> forested valleys -> Jinshan coast
    "north": [(295_600, 2_797_600, 260), (297_900, 2_794_400, 150), (300_200, 2_791_300, 130), (302_500, 2_789_100, 120),
              (304_400, 2_787_700, 120), (305_900, 2_786_400, 120), (307_400, 2_785_000, 110), (308_600, 2_784_300, 110),
              (310_000, 2_785_300, 130), (311_400, 2_787_400, 130), (312_600, 2_789_500, 150), (313_700, 2_791_900, 220)],
}


def ue(e, n, z):
    return [(e - ORIGIN[0]) * 100.0, -(n - ORIGIN[1]) * 100.0, z * 100.0]


def catmull(P, n_per):
    P = np.asarray(P, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + np.linalg.norm(p1 - p0) ** 0.5
        t2 = t1 + np.linalg.norm(p2 - p1) ** 0.5
        t3 = t2 + np.linalg.norm(p3 - p2) ** 0.5
        for t in np.linspace(t1, t2, n_per, endpoint=False):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    out.append(P[-2])
    return np.array(out)


def sample(grid, e, n):
    c = (np.atleast_1d(np.asarray(e, float)) - E0) / SP
    r = (N1 - np.atleast_1d(np.asarray(n, float))) / SP
    v = ndimage.map_coordinates(grid, [r, c], order=1, mode="nearest")
    return v if np.ndim(e) else float(v[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--speed", type=float, default=240.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--route", default="north", choices=sorted(ROUTES))
    ap.add_argument("--envelope-m", type=float, default=100.0)
    a = ap.parse_args()
    run = Path(a.run)
    h = np.load(run / "height_q.npy").astype(np.float64)
    WAYPOINTS = ROUTES[a.route]
    hmax = ndimage.maximum_filter(np.maximum(h, 0.0), size=int(2 * a.envelope_m / SP) + 1)   # terrain envelope radius, sea = 0
    wp = np.array([(w[0], w[1]) for w in WAYPOINTS])
    dense = catmull(wp, 400)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))]
    agl_wp = np.array([w[2] for w in WAYPOINTS], float)
    wp_s = np.array([seg[np.argmin(np.linalg.norm(dense - p, axis=1))] for p in wp])
    dt = 1.0 / a.fps
    s = np.arange(0.0, seg[-1], a.speed * dt)
    e = np.interp(s, seg, dense[:, 0])
    n = np.interp(s, seg, dense[:, 1])
    agl = np.interp(s, wp_s, agl_wp)
    z = sample(hmax, e, n) + agl
    ds = a.speed * dt
    max_dz = math.tan(math.radians(12.0)) * ds                          # climb / dive limit 12 deg
    for _ in range(2):                                                  # forward + backward envelope
        for i in range(1, len(z)):
            z[i] = max(z[i], z[i - 1] - max_dz)
        for i in range(len(z) - 2, -1, -1):
            z[i] = max(z[i], z[i + 1] - max_dz)
    z = ndimage.gaussian_filter1d(z, sigma=a.fps * 1.0, mode="nearest")
    z = np.maximum(z, sample(hmax, e, n) + 70.0)
    ground = sample(h, e, n)
    # orientation
    de, dn, dz = np.gradient(e), np.gradient(n), np.gradient(z)
    yaw = np.degrees(np.arctan2(-dn, de))                               # UE yaw: atan2(dY, dX), Y = -north
    yaw = np.degrees(np.unwrap(np.radians(yaw)))
    yaw = ndimage.gaussian_filter1d(yaw, sigma=a.fps * 0.4, mode="nearest")
    path_angle = np.degrees(np.arctan2(dz, np.hypot(de, dn)))
    pitch = ndimage.gaussian_filter1d(path_angle, sigma=a.fps * 0.6, mode="nearest") - 7.0
    turn = np.gradient(np.radians(yaw)) / dt                            # rad/s
    roll = np.clip(np.degrees(np.arctan(a.speed * turn / 9.81)) * 0.55, -55, 55)
    roll = ndimage.gaussian_filter1d(roll, sigma=a.fps * 0.5, mode="nearest")
    keys = [{"frame": i, "ue_loc_cm": ue(e[i], n[i], z[i]), "ue_rot": [float(roll[i]), float(pitch[i]), float(yaw[i])]} for i in range(len(s))]
    agl_true = z - ground
    stills = [
        {"name": "agl300_qixing", "pos": (303_400, 2_781_600, 300), "look": (305_790, 2_784_800, 1000)},
        {"name": "alt1500_overview", "pos": (300_000, 2_776_500, 1500), "look": (305_000, 2_786_000, 500)},
        {"name": "agl120_plantation", "pos": None, "look": None},   # filled below: lowest cryptomeria stand near the route
        {"name": "agl200_qingtiangang", "pos": (309_300, 2_782_600, 200), "look": (307_900, 2_784_100, 760)},
        {"name": "alt3000_wide", "pos": (296_000, 2_772_000, 3000), "look": (306_000, 2_789_000, 300)},
        {"name": "agl400_basin_edge", "pos": (301_500, 2_775_400, 400), "look": (303_500, 2_781_000, 350)},
    ]
    meta = {"stills": []}
    # plantation still: densest cryptomeria (form J) tile near the route
    idx = json.loads((run / "trees.json").read_text(encoding="utf-8"))
    best = max(idx["tiles"], key=lambda t: sum(g["count"] for g in t["groups"] if g["form"] == "J"))
    bx, by = best["center_ue_cm"]
    be, bn = bx / 100.0 + ORIGIN[0], -by / 100.0 + ORIGIN[1]
    stills[2]["pos"] = (be - 450, bn - 450, 140)
    stills[2]["look"] = (be, bn, None)
    for st in stills:
        pe, pn, pz = st["pos"]
        le, ln, lz = st["look"]
        g = sample(h, pe, pn)
        if st["name"].startswith("agl"):
            pz = max(g, 0.0) + pz
        if lz is None:
            lz = sample(h, le, ln) + 15.0
        d = np.array([le - pe, ln - pn, lz - pz])
        yaw_s = math.degrees(math.atan2(-d[1], d[0]))
        pitch_s = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
        meta["stills"].append({"name": st["name"], "ue_loc_cm": ue(pe, pn, pz), "ue_rot": [0.0, pitch_s, yaw_s], "ground_m": g, "cam_z_m": pz})
    views = {"fps": a.fps, "speed_mps": a.speed, "hfov_deg": 70.0, "still_hold_frames": 90,
             "flight": {"keys": keys, "frames": len(keys), "length_km": float(s[-1] / 1000.0),
                        "agl_m": {"min": float(agl_true.min()), "median": float(np.median(agl_true)), "max": float(agl_true.max())},
                        "waypoints_3826": WAYPOINTS, "route": a.route},
             "stills": meta["stills"]}
    (run / ("views.json" if a.route == "south" else "views_%s.json" % a.route)).write_text(json.dumps(views) + "\n", encoding="utf-8")
    print(json.dumps({"frames": len(keys), "seconds": len(keys) / a.fps, "length_km": views["flight"]["length_km"], "agl": views["flight"]["agl_m"],
                      "stills": [(x["name"], round(x["cam_z_m"]), round(x["ground_m"])) for x in meta["stills"]]}, indent=1))


if __name__ == "__main__":
    main()
