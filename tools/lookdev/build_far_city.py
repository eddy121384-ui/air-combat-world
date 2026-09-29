"""Build the far-LOD Taipei basin city from real WFS statistics.

Input: data/lookdev_cache/far_city_generalized.npz (tools/lookdev/generalize_far_city.py)

Replaces the procedural "city carpet" with real data, split by perceptual cost:

1. Data texture (no geometry) for the whole basin floor:
   far_city_1024.png  RGBA8 over the backdrop extent (ENU, row 0 = north)
     R = building coverage, G = area-weighted mean height / 100 m,
     B = p90 height / 150 m, A = 255 where WFS data exists (Taipei City)
   The backdrop shader shades roofs/streets/night light density from it.
2. Geometry only where the silhouette matters:
   - 50 m cells with p90 >= MID_M: one massing box per cell
     (footprint from real coverage, height from real stats, 3 m quantized),
   - every WFS record >= 50 m: an oriented box from its minimum rotated
     rectangle (the real far skyline).
   Everything inside the accepted Xinyi source bbox is skipped (the full
   detail tiles own it). Chunked into 2.5 km GLBs (chunk-local origin) that
   reuse the M_XinyiCity vertex contract (UV0 facade, UV1 height/floor,
   UV2 packed archetype/seed).
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import enu_origin_from_city_yaml, lonlat_to_enu  # noqa: E402

CITY = REPO / "cities/taipei/city.yaml"
SRC = REPO / "data/lookdev_cache/far_city_generalized.npz"
BACKDROP = REPO / "unreal/Saved/XinyiLook/backdrop/taipei_basin_backdrop.json"
OUT = REPO / "unreal/Saved/XinyiLook/farcity"
XINYI_SOURCE_BBOX_LL = (121.5546, 25.0247, 121.5744, 25.0427)
MID_M = 20.0
CHUNK_M = 2500.0
TEX = 1024
ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE = 2, 3, 4


def enu_fn():
    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    to_ll = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)

    def f(x, y):
        lon, lat = to_ll.transform(np.asarray(x, float), np.asarray(y, float))
        lon, lat = np.atleast_1d(lon), np.atleast_1d(lat)
        out = np.array([lonlat_to_enu(float(a), float(b), lon0, lat0) for a, b in zip(lon, lat)])
        return out[:, 0], out[:, 1]
    return f, lon0, lat0


class Chunk:
    def __init__(self, key):
        self.key = key
        self.cx = (key[0] + 0.5) * CHUNK_M
        self.cy = (key[1] + 0.5) * CHUNK_M
        self.pos, self.nrm, self.uv0, self.uv1, self.uv2, self.idx = [], [], [], [], [], []

    def box(self, cx, cy, w, d, ang_deg, z0, h, arch, seed):
        """Oriented box: 4 walls with facade UVs + roof (no hidden bottom)."""
        a = math.radians(ang_deg)
        ux, uy = math.cos(a), math.sin(a)
        vx, vy = -uy, ux
        corners = [(cx - ux * w / 2 - vx * d / 2, cy - uy * w / 2 - vy * d / 2),
                   (cx + ux * w / 2 - vx * d / 2, cy + uy * w / 2 - vy * d / 2),
                   (cx + ux * w / 2 + vx * d / 2, cy + uy * w / 2 + vy * d / 2),
                   (cx - ux * w / 2 + vx * d / 2, cy - uy * w / 2 + vy * d / 2)]
        fh = 3.3 if arch != ARCH_OFFICE else 3.9
        code = (arch * 16, seed, 90 if arch != ARCH_OFFICE else 30, 0)
        per = 0.0
        for i in range(4):
            p0, p1 = corners[i], corners[(i + 1) % 4]
            L = math.dist(p0, p1)
            n = ((p1[1] - p0[1]) / L, -(p1[0] - p0[0]) / L, 0.0)
            q = [(p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z0 + h), (p0[0], p0[1], z0 + h)]
            uv = [(per, 0.0), (per + L, 0.0), (per + L, h), (per, h)]
            self._quad(q, n, uv, h, fh, code)
            per += L
        q = [(c[0], c[1], z0 + h) for c in corners]
        self._quad(q, (0.0, 0.0, 1.0), [(c[0], c[1]) for c in corners], h, fh, code)

    def _quad(self, q, n, uv, h, fh, code):
        b = len(self.pos)
        for (x, y, z), t in zip(q, uv):
            self.pos.append((x - self.cx, y - self.cy, z))
            self.nrm.append(n)
            self.uv0.append(t)
            self.uv1.append((h, fh))
            self.uv2.append(code)
        self.idx += [(b, b + 1, b + 2), (b, b + 2, b + 3)]

    def write(self, path):
        p = np.asarray(self.pos, float)
        nn = np.asarray(self.nrm, float)
        game = np.column_stack([p[:, 0], p[:, 2], -p[:, 1]]).astype(np.float32)
        gn = np.column_stack([nn[:, 0], nn[:, 2], -nn[:, 1]]).astype(np.float32)
        write_glb(path, [{"name": "XinyiCity", "positions": game, "normals": gn,
                          "uv0": np.asarray(self.uv0, np.float32), "uv1": np.asarray(self.uv1, np.float32),
                          "uv2": pack_rgba8(np.asarray(self.uv2, np.uint8)),
                          "indices": np.asarray(self.idx, np.uint32)}], mesh_name="SM_FarCity_%d_%d" % self.key)
        return ue_local_bounds_cm(game), len(self.idx)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    d = np.load(SRC)
    cell = float(d["cell_m"])
    to_enu, lon0, lat0 = enu_fn()
    (bx0, by0), (bx1, by1) = [lonlat_to_enu(lon, lat, lon0, lat0) for lon, lat in
                              ((XINYI_SOURCE_BBOX_LL[0], XINYI_SOURCE_BBOX_LL[1]),
                               (XINYI_SOURCE_BBOX_LL[2], XINYI_SOURCE_BBOX_LL[3]))]

    def in_xinyi(e, n):
        return (e > bx0) & (e < bx1) & (n > by0) & (n < by1)

    # cell centres -> ENU
    cx3826 = (d["ix"] + 0.5) * cell
    cy3826 = (d["iy"] + 0.5) * cell
    ce, cn = to_enu(cx3826, cy3826)
    cov, hm, hp, gr = d["coverage"], d["h_mean"], d["h_p90"], d["ground"]

    # ---- data texture over the backdrop extent --------------------------------
    bk = json.loads(BACKDROP.read_text())
    E0, E1, N0, N1 = bk["extent_enu_m"]
    img = np.zeros((TEX, TEX, 4), np.float32)
    px = ((ce - E0) / (E1 - E0) * TEX).astype(int)
    py = ((N1 - cn) / (N1 - N0) * TEX).astype(int)
    ok = (px >= 0) & (px < TEX) & (py >= 0) & (py < TEX)
    acc = np.zeros((TEX, TEX, 4), np.float64)
    cnt = np.zeros((TEX, TEX), np.float64)
    for x, y, c, a, b in zip(px[ok], py[ok], cov[ok], hm[ok], hp[ok]):
        acc[y, x] += (c, a, b, 1.0)
        cnt[y, x] += 1.0
    nz = cnt > 0
    img[nz, 0] = np.clip(acc[nz, 0] / cnt[nz], 0, 1)
    img[nz, 1] = np.clip(acc[nz, 1] / cnt[nz] / 100.0, 0, 1)
    img[nz, 2] = np.clip(acc[nz, 2] / cnt[nz] / 150.0, 0, 1)
    img[nz, 3] = 1.0
    # fill 1-px holes so the carpet is continuous
    from scipy import ndimage
    for ch in range(3):
        blur = ndimage.uniform_filter(img[..., ch], 3)
        img[..., ch] = np.where(nz, img[..., ch], blur * 1.2)
    img[..., 3] = np.maximum(img[..., 3], ndimage.uniform_filter(img[..., 3], 3) > 0.3)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(OUT / "far_city_1024.png", optimize=True)

    # ---- massing geometry ------------------------------------------------------
    chunks = {}

    def chunk_for(e, n):
        k = (int(math.floor(e / CHUNK_M)), int(math.floor(n / CHUNK_M)))
        if k not in chunks:
            chunks[k] = Chunk(k)
        return chunks[k]

    rng = np.random.default_rng(101)
    mids = (hp >= MID_M) & (cov >= 0.12) & ~in_xinyi(ce, cn)
    for e, n, c, a, b, g in zip(ce[mids], cn[mids], cov[mids], hm[mids], hp[mids], gr[mids]):
        # footprint area follows the real coverage; aspect / position are
        # jittered inside the cell so the 50 m lattice does not read as a grid
        area = cell * cell * min(0.8, max(0.08, c * 1.1))
        aspect = rng.uniform(0.55, 1.8)
        w = min(cell * 0.95, math.sqrt(area * aspect))
        dd = min(cell * 0.95, area / w)
        ox = rng.uniform(-0.5, 0.5) * (cell - w)
        oy = rng.uniform(-0.5, 0.5) * (cell - dd)
        h = max(6.0, round((0.55 * a + 0.45 * b) * rng.uniform(0.85, 1.15) / 3.0) * 3.0)
        arch = ARCH_HUAXIA if h < 40 else ARCH_RESTOWER
        chunk_for(e, n).box(e + ox, n + oy, w, dd, rng.uniform(-4.0, 4.0), g, h, arch, int(rng.integers(0, 256)))

    tw = d["towers"]
    te, tn = to_enu(tw[:, 0], tw[:, 1]) if len(tw) else (np.array([]), np.array([]))
    tower_n = 0
    for (x, y, w, dd, ang, h, g), e, n in zip(tw, te, tn):
        if in_xinyi(np.array([e]), np.array([n]))[0] or w < 3 or dd < 3:
            continue
        arch = ARCH_OFFICE if (w * dd > 900 or h > 90) else ARCH_RESTOWER
        # EPSG:3826 grid ~ ENU here (both near-conformal, ~1 deg apart at most)
        chunk_for(e, n).box(e, n, w, dd, ang, g, h, arch, int(rng.integers(0, 256)))
        tower_n += 1

    manifest = []
    tris = 0
    for k, ch in sorted(chunks.items()):
        name = "farcity_%+03d_%+03d.glb" % k
        bounds, t = ch.write(OUT / name)
        tris += t
        manifest.append({"chunk": list(k), "path": name, "origin_enu_m": [ch.cx, ch.cy],
                         "ue_actor_location_cm": [ch.cx * 100.0, -ch.cy * 100.0, 0.0],
                         "expected_ue_local_bounds": bounds, "triangles": t})
    report = {
        "status": "PASS_FAR_CITY",
        "role": "far LOD only; accepted Xinyi source bbox skipped",
        "texture": "far_city_1024.png", "texture_extent_enu_m": [E0, E1, N0, N1],
        "mid_cells": int(mids.sum()), "towers": tower_n, "chunks": manifest, "triangles": tris,
        "xinyi_source_bbox_enu_m": [bx0, bx1, by0, by1],
    }
    (OUT / "far_city.report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("mid_cells", "towers", "triangles")}), len(manifest), "chunks")


if __name__ == "__main__":
    main()
