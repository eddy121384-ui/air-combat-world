"""Top-down canopy coverage from ForestSpike ID passes, plus the geometric model it is compared against.

Measured: orthographic ID capture of the 1 km core (north up, east right, ortho width 1000 m, square px).
  forest-mask pixels   = analytic forest_binary at the pixel centre (the same function that places instances)
  instance pixels      = ID classes 5 (arm A) / 6 (arm B)
  cover                = instance pixels inside the mask / mask pixels   (what the review calls canopy coverage)
Model: each placed instance rasterised as a filled ellipse (width x depth of the imported LOD0 mesh, scaled, yawed)
on a 0.5 m grid, same union-over-mask definition. The measured/model ratio exposes the footprint heuristic.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

import fs_world as w
import fs_ids as I

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
INPUTS = REPO / "unreal" / "ForestSpike" / "Saved" / "ForestSpike" / "inputs"
# LOD0 footprints (x width, y depth) in metres, from the PR #18 manifest dimensions (Blender Z-up modelling frame)
FOOT = {"A": [(5.51, 5.90)],
        "B": [(8.28, 6.42), (7.81, 6.45), (9.68, 5.67), (2.98, 2.59)]}


def pool():
    meta = json.loads((INPUTS / "pool.json").read_text())
    a = np.fromfile(INPUTS / "pool.f32", "<f4").reshape(meta["count"], len(meta["columns"]))
    return a


def mask_px(px, ortho_m=1000.0):
    c = (np.arange(px) + 0.5) / px * ortho_m - ortho_m / 2.0
    E, N = np.meshgrid(c, c[::-1])        # row 0 = north
    return w.forest_binary(E, N), E, N


def measured(png, arm, px=2048):
    cls, _, exact, _ = I.load_id(png)
    m, _, _ = mask_px(px)
    inst = np.isin(cls, (5, 6))
    forest_px = int(m.sum())
    return {"image": str(png), "px": px, "forest_px": forest_px,
            "instance_px_in_forest": int((inst & m).sum()), "instance_px_outside_forest": int((inst & ~m).sum()),
            "ground_forest_px_visible": int(((cls == 2) & m).sum()),
            "cover": float((inst & m).sum() / forest_px),
            "codes_exact": float(exact.mean()),
            "sky_or_unknown_px": int((cls == 0).sum())}


def model_cover(arm, n, res_m=0.5):
    p = pool()[:n]
    px = int(round(w.CORE_M / res_m))
    grid = np.zeros((px, px), bool)
    c = (np.arange(px) + 0.5) * res_m - w.CORE_HALF
    foot = FOOT[arm]
    for e, nn, z, yaw, sc, var, col, u in p:
        fx, fy = foot[int(var)] if arm == "B" else foot[0]
        a, b = 0.5 * fx * sc, 0.5 * fy * sc
        r = max(a, b)
        i0, i1 = max(0, int((nn + w.CORE_HALF - r) / res_m)), min(px, int((nn + w.CORE_HALF + r) / res_m) + 2)
        j0, j1 = max(0, int((e + w.CORE_HALF - r) / res_m)), min(px, int((e + w.CORE_HALF + r) / res_m) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        Ex, Ny = np.meshgrid(c[j0:j1] - e, c[i0:i1] - nn)
        th = math.radians(float(yaw))
        u1 = Ex * math.cos(th) + Ny * math.sin(th)
        v1 = -Ex * math.sin(th) + Ny * math.cos(th)
        grid[i0:i1, j0:j1] |= (u1 / a) ** 2 + (v1 / b) ** 2 <= 1.0
    cE, cN = np.meshgrid(c, c)
    m = w.forest_binary(cE, cN)
    return float((grid & m).sum() / m.sum())


def poisson_cover(arm, n):
    """Closed-form random cover 1 - exp(-rho * A) with A the mean ellipse area; rho over the forest area."""
    c = np.linspace(-500, 500, 1001)
    E, N = np.meshgrid(c, c)
    forest_area = float(w.forest_binary(E, N).mean()) * w.CORE_M ** 2
    foot = FOOT[arm]
    if arm == "B":
        wts = [0.4, 0.2, 0.2, 0.2]
        a = sum(wt * math.pi / 4 * f[0] * f[1] for wt, f in zip(wts, foot))
    else:
        a = math.pi / 4 * foot[0][0] * foot[0][1]
    a *= (0.8 ** 2 + 0.8 * 1.25 + 1.25 ** 2) / 3.0           # E[s^2] for s ~ U(0.8, 1.25)
    return 1.0 - math.exp(-n / forest_area * a)
