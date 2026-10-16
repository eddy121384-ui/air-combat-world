"""Hillside forest look-dev v1: camera poses (50 / 200 / 500 m AGL stills, one short flyover) + calculated LOD mix.

All stills look along compass bearing 45 deg (north-east, up the sunlit south-west flank toward the 象山 summit ridge) so the
mid-morning sun (azimuth 140 deg, elevation 47 deg; mid-October ~10:30 Taipei) comes from the right: side light that shows
crown relief (the flyover is a short eastbound canopy pass along the summit ridge, sun front-right). AGL = camera height above the terrain directly below it. For each still the pitch / stand-off is picked from a
small grid by ray-marching the heightmap (trees ignored) to maximise the share of the frame that lands inside the 250 m forest
block, with a sky band (50 m: 5-30 % sky so the horizon stays in frame; 200 / 500 m: <= 15 %); the block is smaller than a 500 m AGL footprint, so bare test terrain around it is unavoidable there.

LOD mix: screen size = 3.08 x R / d (UE ComputeBoundsScreenSize at 60 deg hfov, 16:9; R = 8.377 m x instance scale), D chain
thresholds 1.0 / 0.5 / 0.15 / 0.06 -> LOD0 / 1 / 2 / 3. CALCULATED per instance, not read from the engine (HISM selects LODs
per cluster node, so the engine can differ near a threshold).

    python tools/forest/hillside_views.py <terrain_dir> [instances_file views_file]
Writes <terrain_dir>/views.json (default; mix v0: instances_mix.json -> views_mix.json, same poses, LOD mix of the mixed forest).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from hillside_scatter import BLOCK_HALF, MESH_SPHERE_R, Terrain  # noqa: E402

HFOV = 60.0
ASPECT = 16.0 / 9.0
BEARING = 45.0
SUN = {"azimuth_deg": 140.0, "elevation_deg": 47.0}
LOD_CUTS = (0.5, 0.15, 0.06)
FPS = 60
STILL_HOLD = 48  # frames each still pose is held in the stills sequence (TAA / streaming settle); the last one is the still


def dir_from(bearing, pitch):
    b, p = math.radians(bearing), math.radians(pitch)
    return np.array([math.sin(b) * math.cos(p), math.cos(b) * math.cos(p), math.sin(p)])


def ue_rot(bearing, pitch):
    return [0.0, pitch, bearing - 90.0]  # roll, pitch, yaw (UE yaw 0 = east, 90 = south)


def rays(bearing, pitch, nx=48, ny=27):
    tx = math.tan(math.radians(HFOV / 2))
    ty = tx / ASPECT
    f = dir_from(bearing, pitch)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    out = []
    for j in range(ny):
        for i in range(nx):
            sx = (2 * (i + 0.5) / nx - 1) * tx
            sy = (1 - 2 * (j + 0.5) / ny) * ty
            d = f + sx * r + sy * u
            out.append(d / np.linalg.norm(d))
    return np.array(out)


def score(T, cam, bearing, pitch):
    D = rays(bearing, pitch)
    t = np.full(len(D), np.nan)
    p = cam[None, :].copy().repeat(len(D), 0)
    alive = np.ones(len(D), bool)
    step = 2.0
    for k in range(1, 2000):
        q = cam[None, :] + D * (k * step)
        inside_grid = (np.abs(q[:, 0]) < T.half - 2) & (np.abs(q[:, 1]) < T.half - 2)
        hit = alive & inside_grid & (q[:, 2] <= T.height(q[:, 0], q[:, 1]))
        t[hit] = k * step
        p[hit] = q[hit]
        alive &= ~hit & inside_grid
        if not alive.any():
            break
    ground = ~np.isnan(t)
    inblock = ground & (np.abs(p[:, 0]) <= BLOCK_HALF) & (np.abs(p[:, 1]) <= BLOCK_HALF)
    return {"in_block": float(inblock.mean()), "ground_outside_block": float((ground & ~inblock).mean()), "sky_or_off_grid": float((~ground).mean()),
            "median_hit_dist_m": float(np.nanmedian(t)) if ground.any() else None}


def pose_for_agl(T, agl, pitch, target):
    """Stand-off along -BEARING from the target so that the camera, at `agl` above its own ground, looks at the target with `pitch`."""
    back = -dir_from(BEARING, 0.0)[:2]
    d = 100.0
    for _ in range(60):
        xy = np.array(target[:2]) + back * d
        z = float(T.height(xy[0], xy[1])[0]) + agl
        d_new = (z - target[2]) / math.tan(math.radians(-pitch))
        if abs(d_new - d) < 0.05:
            break
        d = 0.5 * d + 0.5 * d_new
    return np.array([xy[0], xy[1], z])


def lod_mix(T, inst, cam, bearing, pitch, frustum=True):
    f = dir_from(bearing, pitch)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    tx = math.tan(math.radians(HFOV / 2))
    ty = tx / ASPECT
    cnt = [0, 0, 0, 0]
    for it in inst:
        R = it.get("sphere_r_m", MESH_SPHERE_R) * max(it.get("scale_x", it["scale_xy"]), it.get("scale_y", it["scale_xy"]), it["scale_z"])
        c = np.array([it["x_m"], it["y_m"], it["z_m"] + it.get("crown_z_m", 7.1) * it["scale_z"]])
        v = c - cam
        dist = float(np.linalg.norm(v))
        if frustum:
            z = v @ f
            if z <= -R or abs(v @ r) > z * tx + R * 1.2 or abs(v @ u) > z * ty + R * 1.2:
                continue
        ss = 3.08 * R / max(dist, 1.0)
        cnt[sum(ss < c_ for c_ in LOD_CUTS)] += 1
    return cnt


def main(d, inst_file="instances.json", out_file="views.json"):
    d = Path(d)
    T = Terrain(d)
    inst = json.loads((d / inst_file).read_text(encoding="utf-8"))["instances"]
    h_ref = T.meta["landscape"]["h_ref_m"]
    centre = (0.0, 0.0, float(T.height(0.0, 0.0)[0]) + 8.0)
    stills = []
    search = {
        50: [(p, s) for p in (-4, -7, -10, -13, -16) for s in (-120, -100, -80, -60)],  # pose inside the block's south-west part
        200: [(p, 0) for p in (-18, -22, -26, -30, -35, -40)],
        500: [(p, 0) for p in (-30, -35, -40, -45, -50, -55)],
    }
    for agl, grid in search.items():
        best = None
        for pitch, s in grid:
            if agl == 50:
                xy = np.array([s, s]) * 1.0  # along the block's SW-NE diagonal
                cam = np.array([xy[0], xy[1], float(T.height(xy[0], xy[1])[0]) + agl])
            else:
                cam = pose_for_agl(T, agl, pitch, centre)
            sc = score(T, cam, BEARING, pitch)
            # 50 m: a flight view keeps a strip of horizon (5-30 % sky); higher views: at most 15 % sky
            lo, cap = (0.05, 0.30) if agl == 50 else (0.0, 0.15)
            key = sc["in_block"] - (10.0 if not lo <= sc["sky_or_off_grid"] <= cap else 0.0)
            if best is None or key > best[0]:
                best = (key, pitch, cam, sc)
        _, pitch, cam, sc = best
        ground_z = float(T.height(cam[0], cam[1])[0])
        stills.append({"name": "agl%d" % agl, "agl_m": round(cam[2] - ground_z, 2), "pitch_deg": pitch, "bearing_deg": BEARING,
                       "pos_local_m": [round(float(v), 2) for v in cam],
                       "ue_loc_cm": [float(cam[0]) * 100, -float(cam[1]) * 100, (float(cam[2]) - h_ref) * 100], "ue_rot": ue_rot(BEARING, pitch),
                       "frame_composition": sc, "lod_calc_in_frustum": lod_mix(T, inst, cam, BEARING, pitch),
                       "slant_to_block_centre_m": round(float(np.linalg.norm(cam - np.array(centre))), 1)})

    # flyover: a short canopy pass eastbound (bearing 90) along the summit ridge line y = -20 m toward the 象山 peak, 300 m at 40 m/s
    # (7.5 s), 70 m above a 250 m moving average of the ground (a smoothed line, not a contour hug). The camera aims at the ground 90 m
    # ahead (+10 m canopy; ~-38 deg), smoothed over 1 s, clamped to [-50, -20] deg, so the frame stays on the 250 m block while the aim
    # point sweeps it west -> east. Rejected on the way (native frames looked at sky or at the bare test terrain): r3 bearing 45 diagonal,
    # pitch = path climb - 10 deg (-36..+12 deg); r4 diagonal, 250 m aim; r5 eastbound, 160 m aim, clamp -8 deg - a forward-looking
    # camera at 50-90 m AGL sees 200-400 m ahead, more than the block.
    fb, y0 = 90.0, -20.0
    speed, length, agl_f, ahead = 40.0, 300.0, 70.0, 90.0
    nfr = int(length / speed * FPS)
    fwd = dir_from(fb, 0.0)[:2]
    side = np.array([0.0, y0])
    s_all = np.linspace(-length / 2 - 300, length / 2 + 400, 3001)
    xy_all = side[None, :] + fwd[None, :] * s_all[:, None]
    g_all = T.height(xy_all[:, 0], xy_all[:, 1])
    k = int(250 / (s_all[1] - s_all[0])) | 1
    g_s = np.convolve(np.pad(g_all, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    ss = -260.0 + speed * np.arange(nfr + 1) / FPS  # camera x -260 -> +40 m: the aim point (60-90 m ahead on this upslope) sweeps the block
    zz = np.interp(ss, s_all, g_s) + agl_f
    raw_pitch = np.degrees(np.arctan2(np.interp(ss + ahead, s_all, g_all) + 10.0 - zz, ahead))
    sm = np.convolve(np.pad(raw_pitch, FPS // 2, mode="edge"), np.ones(FPS + 1) / (FPS + 1), mode="valid")
    pitches = np.clip(sm, -50.0, -20.0)
    keys = []
    for fr in range(nfr + 1):
        x, y = side + fwd * ss[fr]
        z = float(zz[fr])
        pitch = float(pitches[fr])
        cam = np.array([x, y, z])
        keys.append({"frame": fr, "pos_local_m": [round(float(x), 2), round(float(y), 2), round(z, 2)],
                     "agl_m": round(z - float(T.height(x, y)[0]), 2),
                     "ue_loc_cm": [float(x) * 100, -float(y) * 100, (z - h_ref) * 100], "ue_rot": ue_rot(fb, pitch),
                     "lod_calc_in_frustum": lod_mix(T, inst, cam, fb, pitch) if fr % 6 == 0 else None})
    out = {"hfov_deg": HFOV, "aspect": ASPECT, "fps": FPS, "bearing_deg": BEARING, "sun": SUN, "h_ref_m": h_ref, "lod_cuts": LOD_CUTS,
           "still_hold_frames": STILL_HOLD, "stills": stills,
           "flight": {"name": "fly_e_ridge_50mps", "bearing_deg": fb, "line_y_m": y0, "speed_mps": speed, "length_m": length, "agl_target_m": agl_f, "aim_ahead_m": ahead,
                      "frames": nfr, "agl_range_m": [min(k_["agl_m"] for k_ in keys), max(k_["agl_m"] for k_ in keys)], "keys": keys}}
    out["instances_file"] = inst_file
    (d / out_file).write_text(json.dumps(out, indent=0) + "\n", encoding="utf-8")
    for s_ in stills:
        print(s_["name"], s_["pitch_deg"], s_["pos_local_m"], s_["frame_composition"], s_["lod_calc_in_frustum"], s_["slant_to_block_centre_m"])
    print("flight agl range", out["flight"]["agl_range_m"], "frames", nfr)


if __name__ == "__main__":
    main(*sys.argv[1:4])
