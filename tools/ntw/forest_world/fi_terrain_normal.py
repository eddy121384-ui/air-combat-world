"""Far-LOD research: macro terrain normal per 10 m DEM node for the impostor layer (fi_build.py stores it per tree instance).

Why: an impostor's baked normal belongs to an upright tree, so a forest of impostors loses the SLOPE shading that makes a far range read
as ridges and valleys (PR #49 rule: far = mountain form). The impostor material bends its normal toward this terrain normal with distance.
Normal from the same quantised DEM as the Landscape (height_q.npy), Gaussian-smoothed (sigma 3 nodes = 30 m), in UE axes (X east,
Y south, Z up). Output: <out>/fi_terrain_normal.bin = int8 (nx, ny) * 127 per node, row-major (row 0 = north = UE Y -4,000,000 cm),
and fi_terrain_normal.json (grid, orientation check against the tree heights).
    python tools/ntw/forest_world/fi_terrain_normal.py <run_dir> <out_dir>
"""
import array
import json
import struct
import sys
from pathlib import Path

import numpy as np


def blur(h, sigma):
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(h, r, mode="edge")
    p = sum(k[i] * p[:, i:i + h.shape[1]] for i in range(2 * r + 1))
    return sum(k[i] * p[i:i + h.shape[0], :] for i in range(2 * r + 1))


def main(run, out):
    run, out = Path(run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t = json.loads((run / "terrain.json").read_text(encoding="utf-8"))
    h = np.load(run / "height_q.npy").astype(np.float64)
    sp = t["spacing_m"]
    x0, y0 = t["landscape"]["location_cm"][:2]
    # orientation check: sampled DEM height under the trees of a few tiles vs the trees' own z
    idx = json.loads((run / "trees.json").read_text(encoding="utf-8"))
    errs = []
    for tl in sorted(idx["tiles"], key=lambda q: -q["count"])[:3]:
        buf = (run / "trees" / tl["file"]).read_bytes()
        (ng,), off = struct.unpack_from("<I", buf, 0), 4
        for _ in range(ng):
            _, _, n = struct.unpack_from("<cHI", buf, off)
            off += 7
            rec = array.array("d")
            rec.frombytes(buf[off:off + n * 72])
            off += n * 72
            for i in range(0, n, 97):
                x, y, z = rec[i * 9:i * 9 + 3]
                c, r = int(round((x - x0) / (sp * 100))), int(round((y - y0) / (sp * 100)))
                if 0 <= r < h.shape[0] and 0 <= c < h.shape[1]:
                    errs.append(abs(h[r, c] * 100 - z))
    err = float(np.median(errs))
    if err > 300:
        raise SystemExit("DEM orientation check failed: median |h - tree z| = %.0f cm" % err)
    hs = blur(h, 3.0)
    gx = np.gradient(hs, axis=1) / sp            # dz / dX (east)
    gy = np.gradient(hs, axis=0) / sp            # dz / dY (south, rows grow southward)
    n = np.dstack([-gx, -gy, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    q = np.clip(np.round(n[..., :2] * 127), -127, 127).astype(np.int8)
    (out / "fi_terrain_normal.bin").write_bytes(q.tobytes())
    meta = {"size": list(h.shape), "spacing_cm": sp * 100, "origin_cm": [x0, y0], "sigma_m": 3 * sp, "encoding": "int8 nx, ny * 127, row-major",
            "orientation_check_median_abs_cm": round(err, 1), "orientation_samples": len(errs),
            "slope_deg_p50_p90": [float(np.degrees(np.arccos(np.percentile(n[..., 2], 50)))), float(np.degrees(np.arccos(np.percentile(n[..., 2], 10))))]}
    (out / "fi_terrain_normal.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main(*sys.argv[1:])
