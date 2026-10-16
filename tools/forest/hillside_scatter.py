"""Hillside forest look-dev v1: deterministic 紅楠 (D balanced) placement on the Xiangshan test terrain.

Not a forest system: one offline pass whose output (instance transforms) is written into Unreal HISMs. Rules, all global
(no per-tree edits):

* block: 250 m x 250 m centred on the terrain grid (local metres, x = east, y = north);
* topography from the same quantised heightmap the Landscape uses: slope, and a 30 m topographic position index
  (TPI = height - mean height within 30 m; > 0 ridge / convex, < 0 valley / concave);
* crown radius: log-normal (median 5.6 m, sigma 0.27), x1.15 in valleys, x0.85 on ridges, x0.88 on slopes > 35 deg,
  +-8 % with the cluster field, ~4 % emergent crowns 7-8.6 m; clamped 3.4-8.6 m. Instance XY scale = crown radius / 7.5 m
  (the D mesh crown radius);
* clusters and gaps: smoothed-noise fields (35 m cluster, 16 m gap). The cluster field modulates acceptance and spacing
  (clumps interlock more); where the gap score is lowest (8 % of the block) no tree is placed (tree-fall / light gaps);
  slopes > 45 deg keep only 45 % of candidates (rock / slip faces);
* pass 1 (canopy trees): dart throwing in random order, centres >= k x (r_i + r_j) apart, k = 0.50 - 0.08 x cluster
  (0.42-0.62; crowns interlock 40-60 %: the D crown is a dome whose widest ring is well below its nominal radius, so
  k ~ 0.64 left bare floor visible between crowns in the first native render);
* pass 2 (canopy closure): any free hole wider than 3 m outside the gaps gets a crown of 1.8 x its inscribed radius
  (3.4-6.5 m), a random hole among the wider ones each time, until none is left;
* height: z-scale = xy-scale x U(1.0, 1.25) (crowded crowns are narrower / taller than the open-grown golden tree),
  x1.07 valley, x0.93 ridge; X / Y scale = xy-scale x a, / a with a = U(0.9, 1.1) (mildly elliptical crowns); yaw U(0, 360); downslope lean 0.12 x slope (cap 6 deg) + U(-2, 2) deg; trunk base sunk
  0.25 m + 0.35 m x tan(slope) below the centre height;
* variants: 3 leaf tints (existing M_TL_LeafCards parameters, one HISM each), chosen from a 25 m noise field + 25 %
  random, so neighbours often share a tone.

    python tools/forest/hillside_scatter.py <terrain_dir> [seed]

Writes <terrain_dir>/instances.json, scatter_stats.json, scatter_map.png (crown discs over hillshade).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates, uniform_filter

BLOCK_HALF = 125.0
MESH_CROWN_R = 7.5  # D mesh crown radius at scale 1 (golden dome r_xy 7.6 / 7.3)
MESH_SPHERE_R = 8.377  # UE bounds sphere radius of the D mesh at scale 1 (m)
OVERLAP_K = 0.50
CANDIDATES = 2500
GAP_PCT = 8.0
FILL_MIN_HOLE_M = 3.0
SEED = 20261016


class Terrain:
    def __init__(self, d):
        self.meta = json.loads((d / "terrain.json").read_text(encoding="utf-8"))
        self.h = np.load(d / "terrain_height.npy").astype(np.float64)
        self.sp = self.meta["spacing_m"]
        self.n = self.h.shape[0]
        self.half = (self.n - 1) * self.sp / 2.0
        gy, gx = np.gradient(self.h, self.sp)
        self.gx, self.gy = gx, -gy  # d/dx east, d/dy north (rows go south)
        self.slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        k = int(round(60.0 / self.sp)) | 1
        self.tpi = self.h - uniform_filter(self.h, size=k, mode="nearest")

    def rc(self, x, y):
        return (self.half - np.asarray(y)) / self.sp, (np.asarray(x) + self.half) / self.sp

    def sample(self, arr, x, y, order=1):
        r, c = self.rc(x, y)
        return map_coordinates(arr, [np.atleast_1d(r), np.atleast_1d(c)], order=order, mode="nearest")

    def height(self, x, y):
        """Bilinear on the quantised grid (the Landscape's own vertex heights)."""
        return self.sample(self.h, x, y)


def noise(rng, n, sigma):
    f = gaussian_filter(rng.standard_normal((n, n)), sigma, mode="wrap")
    return (f - f.mean()) / f.std()


def main(d, seed=SEED):
    d = Path(d)
    T = Terrain(d)
    rng = np.random.default_rng(seed)
    # noise fields on a 1 m grid over the block (+ margin)
    N = 300
    g_cluster = noise(rng, N, 35.0 / 2.355)
    g_gap = noise(rng, N, 16.0 / 2.355)
    g_tone = noise(rng, N, 25.0 / 2.355)

    def field(f, x, y):
        c = np.clip(np.asarray(x) + N / 2, 0, N - 1)
        r = np.clip(N / 2 - np.asarray(y), 0, N - 1)
        return map_coordinates(f, [np.atleast_1d(r), np.atleast_1d(c)], order=1)

    gap_score = 0.6 * g_gap + 0.4 * g_cluster
    gap_thr = np.percentile(gap_score[N // 2 - 125:N // 2 + 125, N // 2 - 125:N // 2 + 125], GAP_PCT)

    # candidates
    M = CANDIDATES
    cx = rng.uniform(-BLOCK_HALF, BLOCK_HALF, M)
    cy = rng.uniform(-BLOCK_HALF, BLOCK_HALF, M)
    slope = T.sample(T.slope, cx, cy)
    tpi = T.sample(T.tpi, cx, cy)
    clus = field(g_cluster, cx, cy)
    gaps = field(gap_score, cx, cy) < gap_thr
    r = np.exp(rng.normal(math.log(5.6), 0.27, M))
    r *= np.where(tpi < -2.0, 1.15, np.where(tpi > 2.0, 0.85, 1.0))
    r *= np.where(slope > 35.0, 0.88, 1.0)
    r *= 1.0 + 0.08 * np.clip(clus, -1.5, 1.5)
    emergent = rng.random(M) < 0.04
    r[emergent] = rng.uniform(7.0, 8.6, emergent.sum())
    r = np.clip(r, 3.4, 8.6)
    accept_p = np.clip(0.75 + 0.2 * clus, 0.3, 1.0) * np.where(slope > 45.0, 0.45, 1.0)
    keep = (~gaps) & (rng.random(M) < accept_p)
    # random insertion order (size-first saturates the block with maximum crowns); spacing factor follows the cluster field:
    # clumps interlock more, thin stands less
    kk = np.clip(OVERLAP_K - 0.08 * clus, OVERLAP_K - 0.08, OVERLAP_K + 0.12)
    cand = np.stack([cx[keep], cy[keep], r[keep], kk[keep]], 1)

    # dart throwing on a spatial hash
    cell = 2 * 8.6 * (OVERLAP_K + 0.12)
    grid = {}
    placed = []
    for x, y, rr, k_i in cand:
        i, j = int((x + 200) // cell), int((y + 200) // cell)
        ok = True
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for k in grid.get((i + di, j + dj), ()):
                    px, py, pr, pk = placed[k]
                    if (px - x) ** 2 + (py - y) ** 2 < (0.5 * (pk + k_i) * (pr + rr)) ** 2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid.setdefault((i, j), []).append(len(placed))
            placed.append((x, y, rr, k_i))
    n_pass1 = len(placed)

    # pass 2, canopy closure: free canopy space that is not a designated gap is taken by a crown sized to the hole
    # (a random hole among the wider ones; crown = 1.8 x the hole's inscribed radius, 3.4-6.5 m) until no free hole wider than
    # FILL_MIN_HOLE_M remains. Rasters at 0.5 m over the block.
    res = 0.5
    m = int(2 * BLOCK_HALF / res)
    yy, xx = np.mgrid[0:m, 0:m]
    xc = -BLOCK_HALF + (xx + 0.5) * res
    yc = BLOCK_HALF - (yy + 0.5) * res
    gap_px = field(gap_score, xc.ravel(), yc.ravel()).reshape(m, m) < gap_thr

    def stamp(mask, x0, y0, r0):
        r_, c_ = int((BLOCK_HALF - y0) / res), int((x0 + BLOCK_HALF) / res)
        rad = int(r0 / res) + 1
        a0, a1, b0, b1 = max(r_ - rad, 0), min(r_ + rad + 1, m), max(c_ - rad, 0), min(c_ + rad + 1, m)
        mask[a0:a1, b0:b1] |= (xc[a0:a1, b0:b1] - x0) ** 2 + (yc[a0:a1, b0:b1] - y0) ** 2 <= r0 ** 2

    covered = np.zeros((m, m), bool)
    for px_, py_, pr_, _ in placed:
        stamp(covered, px_, py_, pr_)
    while True:
        free = ~(covered | gap_px)
        edt = distance_transform_edt(free) * res
        e = float(edt.max())
        if e < FILL_MIN_HOLE_M / 2.0:
            break
        cand_px = np.argwhere(edt >= max(0.5 * e, FILL_MIN_HOLE_M / 2.0))  # any wide-enough hole, not only the widest: keeps the closure pass irregular
        r_, c_ = cand_px[rng.integers(len(cand_px))]
        x0, y0 = float(xc[r_, c_]), float(yc[r_, c_])
        r0 = float(np.clip(1.8 * edt[r_, c_] * rng.uniform(0.9, 1.1), 3.4, 6.5))
        placed.append((x0, y0, r0, OVERLAP_K))
        stamp(covered, x0, y0, r0)

    P = np.array(placed)
    x, y, rr = P[:, 0], P[:, 1], P[:, 2]
    n = len(P)
    sl = T.sample(T.slope, x, y)
    tp = T.sample(T.tpi, x, y)
    gx, gy = T.sample(T.gx, x, y), T.sample(T.gy, x, y)
    z = T.height(x, y) - (0.25 + 0.35 * np.tan(np.radians(np.minimum(sl, 60.0))))
    s = rr / MESH_CROWN_R
    sz = s * rng.uniform(1.0, 1.25, n) * np.where(tp < -2.0, 1.07, np.where(tp > 2.0, 0.93, 1.0))
    aniso = rng.uniform(0.9, 1.1, n)  # mildly elliptical crowns (x / y scale ratio 0.82-1.22) so one dome silhouette repeats less
    yaw = rng.uniform(0, 360, n)
    lean = np.minimum(0.12 * sl, 6.0)
    down = np.degrees(np.arctan2(-gy, -gx))  # azimuth (deg from east, ccw) of steepest descent
    tone = field(g_tone, x, y)
    variant = np.where(tone > 0.55, 1, np.where(tone < -0.55, 2, 0))
    rnd = rng.random(n) < 0.25
    variant[rnd] = rng.integers(0, 3, rnd.sum())
    lean_x = lean * np.cos(np.radians(down)) + rng.uniform(-2, 2, n)  # tilt toward +east (deg)
    lean_y = lean * np.sin(np.radians(down)) + rng.uniform(-2, 2, n)  # tilt toward +north (deg)

    h_ref = T.meta["landscape"]["h_ref_m"]
    inst = []
    for k in range(n):
        inst.append({"id": k, "x_m": round(float(x[k]), 3), "y_m": round(float(y[k]), 3), "z_m": round(float(z[k]), 3),
                     "ue_cm": [round(float(x[k]) * 100, 1), round(-float(y[k]) * 100, 1), round((float(z[k]) - h_ref) * 100, 1)],
                     "yaw_deg": round(float(yaw[k]), 2), "lean_east_deg": round(float(lean_x[k]), 2), "lean_north_deg": round(float(lean_y[k]), 2),
                     "scale_xy": round(float(s[k]), 4), "scale_x": round(float(s[k] * aniso[k]), 4), "scale_y": round(float(s[k] / aniso[k]), 4),
                     "scale_z": round(float(sz[k]), 4), "crown_r_m": round(float(rr[k]), 3),
                     "variant": int(variant[k])})

    # planned crown cover: union of nominal crown discs on a 0.5 m raster
    cov = np.zeros((m, m), bool)
    for k in range(n):
        stamp(cov, x[k], y[k], rr[k])
    nn = []
    for k in range(n):
        dd = np.hypot(x - x[k], y - y[k])
        dd[k] = 1e9
        nn.append(dd.min())
    nn = np.array(nn)
    # Clark-Evans aggregation index (R < 1 clustered, 1 random, > 1 regular)
    ce = nn.mean() / (0.5 / math.sqrt(n / (2 * BLOCK_HALF) ** 2))
    stats = {
        "seed": seed, "block_m": 2 * BLOCK_HALF, "trees": n, "trees_pass1_canopy": n_pass1, "trees_pass2_closure": n - n_pass1, "trees_per_ha": n / ((2 * BLOCK_HALF) ** 2 / 1e4),
        "variants": {str(v): int((variant == v).sum()) for v in range(3)},
        "crown_r_m": {"min": float(rr.min()), "median": float(np.median(rr)), "max": float(rr.max()), "p10": float(np.percentile(rr, 10)),
                      "p90": float(np.percentile(rr, 90))},
        "crown_width_m_median": float(2 * np.median(rr)),
        "scale_xy": {"min": float(s.min()), "max": float(s.max())},
        "tree_height_m_est": {"min": float(14.2 * sz.min()), "median": float(14.2 * np.median(sz)), "max": float(14.2 * sz.max())},
        "planned_crown_cover": float(cov.mean()),
        "gap_area_fraction_rule": GAP_PCT / 100.0, "gap_area_fraction_raster": float(gap_px.mean()),
        "nearest_neighbour_m": {"mean": float(nn.mean()), "min": float(nn.min())},
        "clark_evans_R": float(ce),
        "slope_deg_at_trees": {"mean": float(sl.mean()), "max": float(sl.max())},
        "rules": {"overlap_k": OVERLAP_K, "fill_min_hole_m": FILL_MIN_HOLE_M, "mesh_crown_r_m": MESH_CROWN_R, "mesh_sphere_r_m": MESH_SPHERE_R,
                  "candidates": M, "accepted_after_gaps_and_density": int(keep.sum())},
    }
    (d / "instances.json").write_text(json.dumps({"stats": stats, "h_ref_m": h_ref, "instances": inst}, indent=0) + "\n", encoding="utf-8")
    (d / "scatter_stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")

    # map: hillshade crop + crown discs (colour = variant)
    hs = Image.open(d / "terrain_hillshade.png").convert("RGB")
    c0 = (T.n - 1) / 2.0
    px = BLOCK_HALF / T.sp
    crop = hs.crop((int(c0 - px - 10), int(c0 - px - 10), int(c0 + px + 11), int(c0 + px + 11))).resize((1060, 1060), Image.BILINEAR)
    sc = 1060 / (2 * BLOCK_HALF + 20 * T.sp)
    ov = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    cols = [(40, 140, 40, 120), (170, 190, 40, 120), (20, 90, 110, 120)]
    for k in range(n):
        u, v = (x[k] + BLOCK_HALF + 10 * T.sp) * sc, (BLOCK_HALF - y[k] + 10 * T.sp) * sc
        dr.ellipse((u - rr[k] * sc, v - rr[k] * sc, u + rr[k] * sc, v + rr[k] * sc), fill=cols[variant[k]], outline=(0, 0, 0, 160))
    out = Image.alpha_composite(crop.convert("RGBA"), ov).convert("RGB")
    ImageDraw.Draw(out).text((8, 8), "%d trees, planned crown cover %.1f %%, 250 m block, N up" % (n, 100 * cov.mean()), fill=(255, 0, 0))
    out.save(d / "scatter_map.png")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else SEED)
