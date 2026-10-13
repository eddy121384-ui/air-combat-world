"""Decode ForestSpike ID passes and validate them against the analytic world (numpy / Pillow).

Pixel code (see shaders/fs_forest.hlsl): R = class * 40, (G << 8 | B) = round(slant_range_m * 7), A = 255.
  class 0 sky/none, 1 core open ground, 2 core forest ground, 3 context open ground, 4 context forest ground,
        5 tree arm A, 6 tree arm B
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

import fs_world as w

CLS_NAMES = {0: "sky", 1: "core_open", 2: "core_forest_ground", 3: "ctx_open", 4: "ctx_forest_ground",
             5: "tree_A", 6: "tree_B"}
RANGE_SCALE = 7.0


def load_id(path):
    im = np.asarray(Image.open(path).convert("RGBA")).astype(np.int32)
    r = im[..., 0]
    cls = np.rint(r / 40.0).astype(np.int32)
    exact = np.abs(r - cls * 40) <= 1
    rng = (im[..., 1] * 256 + im[..., 2]) / RANGE_SCALE
    return cls, rng, exact, im


def ray_dirs(w_px, h_px, heading_deg, pitch_deg, fov_h_deg):
    h, p = math.radians(heading_deg), math.radians(pitch_deg)
    f = np.array([math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    up = np.cross(right, f)
    th = math.tan(math.radians(fov_h_deg) / 2.0)
    tv = th * h_px / w_px
    x = ((np.arange(w_px) + 0.5) / w_px * 2.0 - 1.0) * th
    y = (1.0 - (np.arange(h_px) + 0.5) / h_px * 2.0) * tv
    X, Y = np.meshgrid(x, y)
    d = f[None, None, :] + X[..., None] * right[None, None, :] + Y[..., None] * up[None, None, :]
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def terrain_hit_range(eye, dirs, tmax=9000.0):
    """Analytic ray / terrain intersection distance (m) per ray; NaN when the ray leaves the context or never hits."""
    shp = dirs.shape[:-1]
    d = dirs.reshape(-1, 3)
    t = np.zeros(len(d))
    hit = np.full(len(d), np.nan)
    alive = np.ones(len(d), bool)
    e0, n0, u0 = eye
    step = 2.0
    prev_above = np.ones(len(d), bool)
    cur_t = 0.0
    while cur_t < tmax and alive.any():
        cur_t += step
        idx = np.where(alive)[0]
        pe, pn, pu = e0 + d[idx, 0] * cur_t, n0 + d[idx, 1] * cur_t, u0 + d[idx, 2] * cur_t
        out = (np.abs(pe) > w.CTX_HALF) | (np.abs(pn) > w.CTX_HALF)
        h = w.height(pe, pn)
        below = pu < h
        # bisection refine for rays that just crossed
        cross = below & ~out
        if cross.any():
            ci = idx[cross]
            lo = np.full(len(ci), cur_t - step)
            hi = np.full(len(ci), cur_t)
            for _ in range(14):
                mid = 0.5 * (lo + hi)
                me, mn, mu = e0 + d[ci, 0] * mid, n0 + d[ci, 1] * mid, u0 + d[ci, 2] * mid
                b = mu < w.height(me, mn)
                hi = np.where(b, mid, hi)
                lo = np.where(b, lo, mid)
            hit[ci] = 0.5 * (lo + hi)
            alive[ci] = False
        alive[idx[out]] = False
        step = min(step * 1.01, 12.0)
    return hit.reshape(shp)
