"""Per-tree LOD-switch step detector on the native flight frames (project venv: numpy + Pillow).

python tools/treegen/flight_pop_local.py <flight_paths.json> <movies_dir> <rev> <out.json>

For every tree and every frame where its CALCULATED LOD changes (A: LOD1<->2 ..., D: also 2<->3; same slant formula as flight_analyze.py), take a window
around the tree's projected crown (camera pose from the sequence keys, 60 deg hfov, crown radius 7.85 m * scale, window half-size = 1.0 x projected radius,
at 960x540 luminance, 3x3 box blur) and compute
    step   = mean |I(f) - I(f-1)| inside the window
    ratio  = step / median(step at f-8..f+8 excluding f-1..f+1)
i.e. how much larger the frame-to-frame change is at the switch than at the neighbouring frames of the same window (camera motion alone gives ~1).
Control: the same ratio for random (tree, frame) pairs where that tree does NOT switch (same sampling of windows), per candidate. Reported per
(candidate, transition) as n / median / p90 / p99 / max, plus the control. Windows are skipped when the crown is < 6 px or clipped by the frame border.
A tree's calculated switch is not verified against the engine; the ratio therefore also dilutes if the true switch frame differs by a few frames.
"""
import json
import math
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from flight_analyze import CUTS, TREES, _one, box, pose  # noqa: E402

W, H = 960, 540
FPX = (W / 2) / math.tan(math.radians(30.0))


def project(path, n):
    ks = path["keys"]
    f = [k["frame"] for k in ks]
    rot = np.stack([np.interp(np.arange(n), f, [k["rot"][i] for k in ks]) for i in range(3)], 1)
    pos = pose(path, n)
    out = np.zeros((n, len(TREES), 3))  # u, v, z
    for i in range(n):
        pitch, yaw = math.radians(rot[i, 1]), math.radians(rot[i, 2])
        fwd = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
        right = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
        up = np.array([-math.sin(pitch) * math.cos(yaw), -math.sin(pitch) * math.sin(yaw), math.cos(pitch)])
        d = np.column_stack([TREES[:, 0], TREES[:, 1], np.full(len(TREES), 6.0 + 1.0)]) - pos[i]
        z = d @ fwd
        out[i, :, 0] = W / 2 + FPX * (d @ right) / np.maximum(z, 1e-3)
        out[i, :, 1] = H / 2 - FPX * (d @ up) / np.maximum(z, 1e-3)
        out[i, :, 2] = z
    return pos, out


def ratio(step, f, k):
    nb = [step[g] for g in range(f - 8, f + 9) if 0 <= g < len(step) and abs(g - f) > 1 and not np.isnan(step[g])]
    return step[f] / (np.median(nb) + 1e-6) if len(nb) >= 6 and not np.isnan(step[f]) else None


def main():
    pj, mov, rev, out = sys.argv[1:5]
    P = json.load(open(pj))["paths"]
    rng = random.Random(1)
    res = {}
    with ProcessPoolExecutor(max_workers=12) as pool:
        for pid, path in P.items():
            n = None
            rec = {}
            pos, prj = project(path, path["keys"][-1]["frame"])
            n = len(pos)
            for cand in "AD":
                folder = os.path.join(mov, "mrq_%s_%s_%s" % (cand, pid, rev), "frames")
                if not os.path.isdir(folder):
                    continue
                m = min(n, len(os.listdir(folder)))
                X = np.stack(list(pool.map(_one, [os.path.join(folder, "frame_%04d.png" % f) for f in range(m)], chunksize=8)))
                X = box(X, 3)
                dist = np.sqrt(((pos[:m, None, :2] - TREES[None, :, :2]) ** 2).sum(-1) + (pos[:m, None, 2] - 6.0) ** 2)
                lod = sum((3.08 * 8.377 * TREES[None, :, 2] / dist < c).astype(int) for c in CUTS[cand])
                trans = {}
                control = []

                def window_ratio(t, f):
                    u, v, z = prj[f, t]
                    s = TREES[t, 2]
                    r = FPX * 7.85 * s / z
                    if r < 6 or z <= 1:
                        return None
                    x0, x1, y0, y1 = int(u - r), int(u + r), int(v - r), int(v + r)
                    if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H:
                        return None
                    step = np.full(m, np.nan)
                    for g in range(max(1, f - 9), min(m, f + 10)):
                        # the window follows the tree: re-project per frame
                        ug, vg, zg = prj[g, t]
                        rg = FPX * 7.85 * s / zg
                        a0, a1, b0, b1 = int(ug - rg), int(ug + rg), int(vg - rg), int(vg + rg)
                        if a0 < 0 or b0 < 0 or a1 >= W or b1 >= H or a1 - a0 < 4:
                            continue
                        c0, c1, d0, d1 = int(ug - rg), int(ug + rg), int(vg - rg), int(vg + rg)
                        step[g] = float(np.abs(X[g, b0:b1, a0:a1] - X[g - 1, b0:b1, a0:a1]).mean())
                    return ratio(step, f, 0)

                sw = [(f, t) for f in range(10, m - 10) for t in np.flatnonzero(lod[f] != lod[f - 1])]
                for f, t in sw:
                    r = window_ratio(t, f)
                    if r is not None:
                        trans.setdefault("%d->%d" % (lod[f - 1][t], lod[f][t]), []).append(r)
                swset = set(sw)
                tries = 0
                while len(control) < 400 and tries < 4000:
                    tries += 1
                    f, t = rng.randrange(10, m - 10), rng.randrange(len(TREES))
                    if (f, t) in swset or any((g, t) in swset for g in range(f - 8, f + 9)):
                        continue
                    r = window_ratio(t, f)
                    if r is not None:
                        control.append(r)
                st = lambda v: dict(n=len(v), median=round(float(np.median(v)), 3), p90=round(float(np.percentile(v, 90)), 3), p99=round(float(np.percentile(v, 99)), 3), max=round(float(max(v)), 3)) if v else None  # noqa: E731
                rec[cand] = dict(transitions={k: st(v) for k, v in sorted(trans.items())}, control=st(control))
                print(pid, cand, json.dumps(rec[cand]), flush=True)
            res[pid] = rec
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
