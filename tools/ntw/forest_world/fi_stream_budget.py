"""Far-LOD research v2: offline sizing of the streamed impostor layer (resident instances per World Partition grid design).

Uses the real tree positions / ranks (same hash h as fi_build.py) and evaluates, at the A/B poses and along the flight leg, how many
impostor instances a grid layout keeps resident: a cell is resident when the 2D distance from the camera to the cell box is <= the grid's
loading range (UE World Partition rule). Prints resident instances / MB (64 B transform + 4 B per custom float) per design, plus the
"ideal" count (only trees whose impostor can be visible: hand-over distance <= D <= band end, kept share k(D)).
    python tools/ntw/forest_world/fi_stream_budget.py <run_dir>
"""
import array
import json
import math
import random
import struct
import sys
from pathlib import Path

import numpy as np

S = 3000.0
POSES = {"forest_layers": (4200.0, -31300.0), "mid_ridge": (11300.0, -22200.0), "basin_edge": (5500.0, -15400.0), "far_range": (18200.0, -32600.0),
         "flight_mid": (4200.0 + 1800 * math.cos(math.radians(49.3)), -31300.0 + 1800 * math.sin(math.radians(49.3)))}


def load(run):
    idx = json.loads((run / "trees.json").read_text(encoding="utf-8"))
    xs, ys, hs = [], [], []
    for t in idx["tiles"]:
        buf = (run / "trees" / t["file"]).read_bytes()
        (ng,), off = struct.unpack_from("<I", buf, 0), 4
        for gi in range(ng):
            form, var, n = struct.unpack_from("<cHI", buf, off)
            off += 7
            rec = np.frombuffer(buf[off:off + n * 72], dtype="<f8").reshape(n, 9)
            off += n * 72
            rng = random.Random("%s/%d/%s%d" % (t["file"], gi, form.decode(), var))
            r = np.array([rng.random() for _ in range(n)])
            xs.append(rec[:, 0] / 100.0)
            ys.append(rec[:, 1] / 100.0)
            hs.append((r * 157.31 + 0.137) % 1.0)
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(hs)


def resident(x, y, h, pose, grids, cell):
    """grids: list of (h_lo, h_hi, loading_range_m). Cells of `cell` m on a grid anchored at 0."""
    px, py = pose
    cx, cy = np.floor(x / cell), np.floor(y / cell)
    # distance from camera to each tree's cell box
    dx = np.maximum(np.maximum(cx * cell - px, px - (cx + 1) * cell), 0.0)
    dy = np.maximum(np.maximum(cy * cell - py, py - (cy + 1) * cell), 0.0)
    d = np.hypot(dx, dy)
    n = 0
    for lo, hi, rng in grids:
        n += int(((h >= lo) & (h < hi) & (d <= rng)).sum())
    return n


def ideal(x, y, h, pose, t_hand, end2, kmin=0.15):
    d = np.hypot(x - pose[0], y - pose[1])
    k = np.clip((S / np.maximum(d, 1.0)) ** 2, kmin, 1.0)
    return int(((d >= t_hand) & (d <= end2) & (h < k)).sum())


def main(run):
    x, y, h = load(Path(run))
    print("trees", len(x))
    end_v6 = 6500.0

    def band_grids(edges, end2, margin):
        out = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            last = end2 if lo <= 0 else min(S / math.sqrt(lo), end2)
            out.append((lo, hi, last + 200.0 + margin))
        return out

    designs = {
        "v2a_two_grids_2km (built)": ([(0.0, 0.45, 7900.0), (0.45, 1.01, 5500.0)], 2000.0),
        "five_band_grids_2km_end6.5": (band_grids([0.0, 0.15, 0.25, 0.45, 0.70, 1.01], end_v6, 800.0), 2000.0),
        "five_band_grids_1km_end6.5": (band_grids([0.0, 0.15, 0.25, 0.45, 0.70, 1.01], end_v6, 600.0), 1000.0),
        "three_grids_1km_end6.0": (band_grids([0.0, 0.25, 0.50, 1.01], 6000.0, 600.0), 1000.0),
        "four_grids_1km_end6.0": (band_grids([0.0, 0.25, 0.40, 0.65, 1.01], 6000.0, 600.0), 1000.0),
    }
    rows = {}
    for name, (grids, cell) in designs.items():
        rows[name] = {p: resident(x, y, h, pose, grids, cell) for p, pose in POSES.items()}
        rows[name]["grids"] = [(round(a, 2), round(b, 2), int(r)) for a, b, r in grids]
    rows["ideal_v6 (hand-over 2.2 km, end 6.5 km)"] = {p: ideal(x, y, h, pose, 2200.0, end_v6) for p, pose in POSES.items()}
    rows["ideal end 6.0"] = {p: ideal(x, y, h, pose, 2200.0, 6000.0) for p, pose in POSES.items()}
    for name, r in rows.items():
        worst = max(v for k, v in r.items() if k != "grids")
        print("%-42s worst %8d (%5.1f MB)  %s" % (name, worst, worst * 76 / 1048576.0, {k: v for k, v in r.items() if k != "grids"}))
        if "grids" in r:
            print("      grids", r["grids"])


if __name__ == "__main__":
    main(sys.argv[1])
