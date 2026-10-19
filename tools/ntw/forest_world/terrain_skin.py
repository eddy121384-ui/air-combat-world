"""Terrain "skin" maps for the distance-layer Landscape material (offline, deterministic, from the same quantised Landscape heights).

T_NF_Terrain.png (2048^2, 12.9 m / texel, row 0 = north), all linear 0..1:
  R  ridge / valley index: multi-scale topographic position (50 / 200 / 600 m windows), 0.5 = planar, > 0.5 convex ridge, < 0.5 valley
  G  drainage: D8 flow accumulation at 20 m (log-scaled, channels only) - the dendritic gully network of the volcanic cones
  B  slope, 0..60 deg
  A  openness: 1 - concavity below the 300 m neighbourhood mean (deep valleys get less sky)
These are what make a mountain read as a mountain at 4-10 km, where individual trees and canopy texture are sub-pixel: ridgelines
lighter / warmer, gullies darker / greener, steep cuts showing soil.
    python tools/ntw/forest_world/terrain_skin.py <run_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

PX = 2048


def d8_accumulation(z):
    """D8 flow accumulation (cells) on grid z (row 0 = north); sea / NaN cells (z < 0) do not route."""
    ny, nx = z.shape
    zp = np.pad(z, 1, mode="edge")
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    best = np.zeros_like(z)
    rec = np.full(z.shape, -1, np.int64)
    idx = np.arange(ny * nx).reshape(ny, nx)
    for dy, dx in offs:
        drop = (z - zp[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]) / (1.4142 if dy and dx else 1.0)
        nb = np.clip(np.arange(ny)[:, None] + dy, 0, ny - 1) * nx + np.clip(np.arange(nx)[None, :] + dx, 0, nx - 1)
        m = drop > best
        best[m] = drop[m]
        rec[m] = nb[m]
    rec[z < 0] = -1
    order = np.argsort(-z, axis=None).tolist()
    r = rec.ravel().tolist()
    acc = [1.0] * (ny * nx)
    for i in order:
        j = r[i]
        if j >= 0:
            acc[j] += acc[i]
    return np.array(acc).reshape(ny, nx), idx


def main(run):
    run = Path(run)
    h = np.load(run / "height_q.npy").astype(np.float64)              # 10 m, 2647^2
    land = h > 0.3

    def tpi(win_px, scale_m):
        return np.tanh((h - ndimage.uniform_filter(h, size=win_px)) / scale_m)

    ridge = 0.5 + 0.5 * (0.35 * tpi(11, 8.0) + 0.40 * tpi(41, 25.0) + 0.25 * tpi(121, 60.0))
    gy, gx = np.gradient(h, 10.0)
    slope = np.clip(np.degrees(np.arctan(np.hypot(gx, gy))) / 60.0, 0, 1)
    concav = np.clip((ndimage.uniform_filter(h, size=61) - h) / 80.0, 0, 1)
    openness = 1.0 - 0.7 * concav
    z20 = h[::2, ::2]
    acc, _ = d8_accumulation(np.where(z20 > 0.3, z20, -1.0))
    chan = np.clip((np.log10(acc) - 1.3) / 2.2, 0, 1)                 # >~20 cells (8,000 m^2) starts a gully, full at ~3,000 cells
    chan = ndimage.zoom(chan, 2, order=1)[: h.shape[0], : h.shape[1]]
    chan = ndimage.gaussian_filter(np.maximum(chan, ndimage.grey_dilation(chan, size=2) * 0.7), 0.8)

    def to_px(a):
        return ndimage.zoom(a, PX / a.shape[0], order=1)[:PX, :PX]

    rgba = np.dstack([to_px(np.where(land, ridge, 0.5)), to_px(np.where(land, chan, 0.0)), to_px(slope), to_px(np.where(land, openness, 1.0))])
    Image.fromarray(np.round(np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA").save(run / "T_NF_Terrain.png")
    prev = np.dstack([rgba[..., 0], rgba[..., 1], rgba[..., 3]])
    Image.fromarray(np.round(np.clip(prev, 0, 1) * 255).astype(np.uint8)).resize((1024, 1024)).save(run / "terrain_skin_preview.png")
    stats = {"ridge_p05_p95": [float(np.percentile(ridge[land], 5)), float(np.percentile(ridge[land], 95))],
             "channel_fraction_gt_0_3": float((chan[land] > 0.3).mean()), "slope_deg_p90": float(np.percentile(slope[land], 90) * 60),
             "max_accumulation_cells_20m": float(acc.max())}
    (run / "terrain_skin.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
