"""Cheap Cloud Renderer v1 (EXPERIMENTAL): renderer inputs derived from the existing cloud state.

This is NOT a second placement system. It reads the cells that build_clouds.py already produced from
tools/lookdev/clouds/cloud_state_v0.json and only decides how the CHEAP renderer draws them:

  NEAR  cell (archetype, centre, radius, base, top) -> one analytic impostor = up to 8 ellipsoid lobes
        inside one inward-facing proxy box (the v0 representation, unchanged shapes)
  FAR   neighbouring cells merged into one cluster impostor (<= 8 cells): one broad, flattened lobe per
        cell (tops a little under the cell top, wider than the cell), flat deck lobes bridging the gaps
        between neighbours, a separate narrower tower lobe only on the few tall, narrow cells. Far
        clouds read as horizontal weather masses instead of many separate round puffs, and one proxy
        stands for up to 8 cells (fewer primitives in the far ring).
  The shader cross-fades the two by camera distance in OPTICAL DEPTH (near tau x (1 - w), far tau x w):
  the summed transmittance interpolates continuously, so the hand-over cannot pop.
  SHADOW the near lobes' optical depth integrated over three height bands into a tileable texture; a
        sun light function projects each band along the sun direction onto terrain / city.

The lobe layouts are renderer detail (like the volumetric renderer's billow noise), generated
deterministically from the state seed + cell / cluster index; gameplay keeps querying the
renderer-independent cells, never these lobes or clusters.

Input:  tools/lookdev/clouds/cloud_state_v0.json   (seed, tile size)
        unreal/Saved/XinyiLook/clouds/clouds_v0.cells.json   (build_clouds.py output)
Output: unreal/Saved/XinyiLook/clouds/cheap/
  clouds_v0.cheap.json      one record per drawn instance (cells near Xinyi + far clusters, both with
                            64 km wrap copies): role, UE location (cm), UE scale (proxy box half
                            extents, m) and the 36 custom-primitive-data floats the material reads:
                              [0..31]  8 lobes x (dx, dy, dz, w) in m, UE axes, box-relative, where
                                       w = radius (whole metres) + squash / 2 (per-lobe vertical
                                       squash packed in the fraction; 0 = unused lobe)
                              [32] cloud base z (box-relative m)  [33] role: +1 near cell, -1 far cluster
                              [34] per-cell variation seed 0..1   [35] bounding-sphere radius (m)
  cloud_cheap_box.glb       unit proxy box [-1, 1]^3 m with INWARD-facing triangles (only the far
                            side rasterises, once per pixel, also with the camera inside the box)
  cloud_cheap_noise_256.png RGBA8 value-noise lattice for the shader's 3D texture noise
                            (G = R shifted by (37, 17): one fetch gives two z slices)
  cloud_cheap_shadow_1024.png  RGBA8, tileable over tile_m (uv = UE xy / tile_m, like the weather map):
                            R / G / B = optical depth / SHADOW_TAU_MAX of the near lobes inside the
                            height bands SHADOW_BANDS_M (A = 255)
  cloud_cheap.report.json

Deterministic; numpy + stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from gltf_writer import write_glb  # noqa: E402

STATE = HERE / "cloud_state_v0.json"
CELLS = REPO / "unreal/Saved/XinyiLook/clouds/clouds_v0.cells.json"
OUT = REPO / "unreal/Saved/XinyiLook/clouds/cheap"
MAX_LOBES = 8
# Near cells are drawn out to NEAR_ZERO_M from the camera, far clusters out to FAR_ZERO_M; the review /
# flight cameras stay within ~15 km of Xinyi, so instances (incl. wrap copies) are spawned within
SPAWN_RADIUS_M = 42000.0       # ... this distance of the ENU origin for near cells
FAR_SPAWN_RADIUS_M = 76000.0   # ... and this for far clusters
ERODE_PAD = 1.16           # shader erosion may grow a lobe by up to ~15.5 %; the proxy must contain it
LINK_GAP_M = 1500.0        # cumulus cells whose rims are closer than this belong to one far cluster
MAX_CLUSTER_EXTENT_M = 7500.0
SHADOW_RES = 1024
SHADOW_BANDS_M = ((1250.0, 1750.0), (1750.0, 2400.0), (2400.0, 3400.0))
SHADOW_SIGMA = 0.03        # 1/m, the shader's day / dusk extinction (K1.x)
SHADOW_TAU_MAX = 6.0       # 8-bit range: tau 6 already transmits 0.25 %
SHADOW_BLUR_M = 90.0       # soft penumbra / edge diffusion


def cumulus_lobes(rng, r, base, top):
    """Fair-weather cumulus: one broad core (the cloud reads as a single mass, not a pile of balls),
    skirt lobes cut flat by the base plane, and an overlapping, leaning tower whose crown reaches the
    state's cell top (consecutive tower lobes overlap by ~half: no stacked 'snowman')."""
    h = top - base
    size = min(1.0, max(0.0, (r - 420.0) / 830.0))
    n = int(np.clip(round(4 + 3.0 * size + rng.uniform(-0.5, 1.5)), 4, MAX_LOBES))
    k = rng.uniform(0.80, 0.95)
    lobes = []
    rc = min(0.66 * r * rng.uniform(0.9, 1.1), (0.6 * h + 150.0) / k)
    zc = base + rc * k * 0.55
    lobes.append([rng.uniform(-0.08, 0.08) * r, rng.uniform(-0.08, 0.08) * r, zc, rc])
    n_skirt = max(2, (n - 1) // 2)
    a0 = rng.uniform(0, 2 * math.pi)
    for i in range(n_skirt):
        rho = r * rng.uniform(0.38, 0.52)
        rho = min(rho, (h + 120.0) / (k + 0.3))          # skirts never poke far above the cell top
        ang = a0 + 2 * math.pi * (i + rng.uniform(-0.25, 0.25)) / n_skirt
        d = max(0.0, r - rho) * rng.uniform(0.55, 1.0)
        # centre above the base: the plane cuts below the lobe's widest part -> rounded flanks over a
        # flat bottom (a cut through the widest part reads as a plate / lip)
        z = base + rho * k * rng.uniform(0.45, 0.8)
        lobes.append([d * math.cos(ang), d * math.sin(ang), z, rho])
    n_tower = n - 1 - n_skirt
    shear = rng.uniform(0.05, 0.18) * r                  # towers lean a little downwind (+east)
    for j in range(n_tower):
        f = (j + 1) / n_tower                            # 0..1 up the tower, last one is the crown
        rho = min(rc * rng.uniform(0.62, 0.8) * (1.0 - 0.25 * f), 0.55 * h + 80.0)
        z = zc + f * max(0.0, top - rho * k * 0.95 - zc)  # crown top = cell top
        spread = 0.22 + 0.4 * max(0.0, 1.0 - (top - zc) / max(r, 1.0))   # flat cells: bumps spread out
        ang = rng.uniform(0, 2 * math.pi)
        d = r * spread * math.sqrt(rng.uniform(0.2, 1.0))
        lobes.append([d * math.cos(ang) + shear * f, d * math.sin(ang), z, rho])
    return lobes, k


def broken_lobes(rng, r, base, top):
    """Broken stratocumulus patch: wide flattened lobes in a lumpy sheet."""
    th = top - base
    n = MAX_LOBES
    rhos = r * rng.uniform(0.32, 0.5, n)
    k = float(np.clip(0.75 * th / rhos.mean(), 0.2, 0.7))
    lobes = []
    for i in range(n):
        ang = rng.uniform(0, 2 * math.pi)
        d = max(0.0, r - 0.6 * rhos[i]) * math.sqrt(rng.uniform(0, 1))
        z = base + th * rng.uniform(0.2, 0.6)
        lobes.append([d * math.cos(ang), d * math.sin(ang), z, float(rhos[i])])
    return lobes, k


def wrapd(v, t):
    """Wrap a coordinate difference into [-t/2, t/2)."""
    return (v + t / 2) % t - t / 2


def clusters_of(cells, idx, T, gap, max_cells, max_extent):
    """Single-linkage groups of the given cells (rims closer than gap, 64 km wrap), then split along
    the principal axis until each group has <= max_cells and fits max_extent around its centroid."""
    parent = {i: i for i in idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a_ in range(len(idx)):
        for b_ in range(a_ + 1, len(idx)):
            i, j = idx[a_], idx[b_]
            ci, cj = cells[i], cells[j]
            d = math.hypot(wrapd(cj["centre_enu_m"][0] - ci["centre_enu_m"][0], T),
                           wrapd(cj["centre_enu_m"][1] - ci["centre_enu_m"][1], T))
            if d < ci["radius_m"] + cj["radius_m"] + gap:
                parent[find(i)] = find(j)
    groups = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    out = []
    todo = sorted(groups.values(), key=lambda g: min(g))
    while todo:
        g = todo.pop(0)
        ref = cells[g[0]]["centre_enu_m"]
        P = np.array([[ref[0] + wrapd(cells[i]["centre_enu_m"][0] - ref[0], T),
                       ref[1] + wrapd(cells[i]["centre_enu_m"][1] - ref[1], T)] for i in g])
        r = np.array([cells[i]["radius_m"] for i in g])
        c = P.mean(0)
        ext = float((np.linalg.norm(P - c, axis=1) + r).max())
        if len(g) <= max_cells and ext <= max_extent:
            out.append(sorted(g))
            continue
        ax = np.linalg.svd(P - c)[2][0]
        s = (P - c) @ ax
        cut = np.median(s)
        lo = [i for i, v in zip(g, s) if v <= cut]
        hi = [i for i, v in zip(g, s) if v > cut]
        if not hi:                                    # identical projections: split by index
            lo, hi = g[: len(g) // 2], g[len(g) // 2:]
        todo += [lo, hi]
    return sorted(out, key=lambda g: min(g)), parent


def far_cluster_lobes(rng, cells, g, T, broken):
    """FAR representation of one cluster: [e, n, z, radius, squash] lobes in ENU (relative to the
    cluster's first cell), with the cluster base.

    Far-field grammar: weather masses, not cartoon objects. Each cell becomes one broad lobe, wider
    than the cell (x1.15 .. 1.35) with its top at 0.72 .. 0.92 of the cell top above the base; cells
    are pulled a little toward their neighbours so a cluster merges into one irregular mass. Only
    tall, narrow cells (height > 1.5 x radius) keep a separate, narrower, slightly leaning tower lobe.
    Remaining lobes become flat decks on the shortest links between neighbours (the shared, ragged
    base deck seen under fair-weather cumulus) or, for a lone cell, offset flat satellites so the
    silhouette is never a single round dome."""
    ref = cells[g[0]]["centre_enu_m"]
    P = np.array([[wrapd(cells[i]["centre_enu_m"][0] - ref[0], T), wrapd(cells[i]["centre_enu_m"][1] - ref[1], T)] for i in g])
    cen = P.mean(0)
    base = min(float(cells[i]["base_m"]) for i in g)
    lobes, towers = [], []
    order = sorted(range(len(g)), key=lambda a: -cells[g[a]]["radius_m"])
    for a in order:
        c = cells[g[a]]
        r, h = float(c["radius_m"]), float(c["top_m"]) - float(c["base_m"])
        p = P[a] + (cen - P[a]) * rng.uniform(0.08, 0.2)
        p = p + rng.normal(0.0, 0.08 * r, 2)
        if broken:
            rho = r * rng.uniform(0.8, 0.95)
            hk = h * rng.uniform(0.75, 0.9)
            z = float(c["base_m"]) + 0.4 * hk
            lobes.append([p[0], p[1], z, rho, hk / rho])
            continue
        tall = h > 1.5 * r
        rho = r * rng.uniform(1.15, 1.35)
        hv = h * (rng.uniform(0.42, 0.55) if tall else rng.uniform(0.72, 0.92))
        hk = hv / 1.3                                   # centre 0.3 hk above the base: top = base + hv
        lobes.append([p[0], p[1], base + 0.3 * hk, rho, hk / rho])
        if tall:
            rt = r * rng.uniform(0.82, 0.98)               # broad turret, not a thin chimney
            ht = h * rng.uniform(0.8, 0.92)
            kt = min(1.8, (ht - 0.45 * hv) / (1.45 * rt))  # centre at 0.45 hv, top at base + ht
            ang = rng.uniform(0, 2 * math.pi)
            off = r * rng.uniform(0.1, 0.3)
            towers.append([p[0] + off * math.cos(ang) + 0.1 * r, p[1] + off * math.sin(ang),
                           base + 0.45 * hv, rt, kt])
    lobes = lobes[:MAX_LOBES]
    lobes += towers[:max(0, MAX_LOBES - len(lobes))]
    # bridges along the minimum spanning tree (shortest links first)
    if len(g) > 1 and len(lobes) < MAX_LOBES:
        edges = []
        inside, rest = {0}, set(range(1, len(g)))
        while rest:
            best = min(((np.linalg.norm(P[i] - P[j]), i, j) for i in inside for j in rest))
            edges.append(best)
            inside.add(best[2])
            rest.discard(best[2])
        for d, i, j in sorted(edges):
            if len(lobes) >= MAX_LOBES:
                break
            ci, cj = cells[g[i]], cells[g[j]]
            m = 0.5 * (P[i] + P[j]) + rng.normal(0.0, 0.1 * d, 2)
            rho = min(1600.0, max(0.55 * d, 0.6 * min(ci["radius_m"], cj["radius_m"])))
            hmin = min(ci["top_m"] - ci["base_m"], cj["top_m"] - cj["base_m"])
            hk = hmin * rng.uniform(0.35, 0.5) / 1.2       # thick enough not to read as stacked plates
            lobes.append([m[0], m[1], base + 0.2 * hk, rho, hk / rho])
    # lone cell: offset flat satellites (asymmetric silhouette)
    while len(g) == 1 and not broken and len(lobes) < 3:
        c = cells[g[0]]
        r, h = float(c["radius_m"]), float(c["top_m"]) - float(c["base_m"])
        ang = rng.uniform(0, 2 * math.pi)
        d = r * rng.uniform(0.7, 1.0)
        rho = r * rng.uniform(0.5, 0.7)
        hk = h * rng.uniform(0.2, 0.35) / 1.2
        lobes.append([P[0][0] + d * math.cos(ang), P[0][1] + d * math.sin(ang), base + 0.2 * hk, rho, hk / rho])
    for L in lobes:
        L[4] = float(np.clip(L[4], 0.12, 1.8))
    return lobes, base, ref


def pack_lobes(L, mid):
    """Box-relative UE-axis lobes, w = whole-metre radius + squash / 2 (see module docstring)."""
    cpd = []
    for e, n, z, rho, k in L:
        cpd += [e - mid[0], -(n - mid[1]), z - mid[2], float(max(1, round(rho))) + round(k / 2.0, 3)]
    return cpd + [0.0, 0.0, 0.0, 0.0] * (MAX_LOBES - len(L))


def box_of(L, base, pad):
    L = np.asarray(L, np.float64)
    ext_lo = np.array([(L[:, 0] - L[:, 3]).min(), (L[:, 1] - L[:, 3]).min(), base])
    ext_hi = np.array([(L[:, 0] + L[:, 3]).max(), (L[:, 1] + L[:, 3]).max(), (L[:, 2] + L[:, 3] * L[:, 4]).max()])
    mid = 0.5 * (ext_lo + ext_hi)
    half = 0.5 * (ext_hi - ext_lo) * pad + 5.0
    # bounding sphere of the padded lobes: horizontal radius dominates (squash <= 1.8 only on towers)
    reach = L[:, 3] * np.maximum(1.0, L[:, 4]) * pad
    bound = float((np.linalg.norm(L[:, :3] - mid, axis=1) + reach).max())
    return mid, half, bound


def lobe_prof(w2, s0, s1):
    """Integral over s in [s0, s1] of (w2 - s^2)^2 (same closed form as the shader's xcc_prof)."""
    return w2 * w2 * (s1 - s0) - (2.0 / 3.0) * w2 * (s1 ** 3 - s0 ** 3) + 0.2 * (s1 ** 5 - s0 ** 5)


def bake_shadow(shapes, cells, T):
    """Column optical depth of the NEAR lobes per height band (vertical chords, base-clipped), wrapped
    over the tile; returns uint8 RGBA (R, G, B = bands, A = 255) in the weather-map orientation
    (row = UE y = -north, col = UE x = east)."""
    n = SHADOW_RES
    px = T / n
    tau = np.zeros((len(SHADOW_BANDS_M), n, n))
    for s, c in zip(shapes, cells):
        e0, n0 = c["centre_enu_m"]
        for e, nn, z, rho, k in s["lobes5"]:
            ux, uy = (e0 + e) % T, (-(n0 + nn)) % T
            r_px = int(math.ceil(rho / px)) + 1
            cj, ci = int(ux / px), int(uy / px)
            js = np.arange(cj - r_px, cj + r_px + 1)
            is_ = np.arange(ci - r_px, ci + r_px + 1)
            dx = (js + 0.5) * px - ux
            dy = (is_ + 0.5) * px - uy
            w2 = 1.0 - (dx[None, :] ** 2 + dy[:, None] ** 2) / (rho * rho)
            ok = w2 > 0
            w = np.sqrt(np.where(ok, w2, 0.0))
            hk = rho * k
            for b, (z0, z1) in enumerate(SHADOW_BANDS_M):
                lo = np.maximum(-w, (max(z0, s["base"]) - z) / hk)
                hi = np.minimum(w, (z1 - z) / hk)
                v = np.where(ok & (hi > lo), hk * lobe_prof(w2, lo, np.maximum(hi, lo)), 0.0)
                tau[b][np.ix_(is_ % n, js % n)] += v * SHADOW_SIGMA
    # gaussian blur (wrapped, separable): soft edges, no texel stair-steps on the ground
    sig = SHADOW_BLUR_M / px
    rad = int(math.ceil(3 * sig))
    ker = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sig) ** 2)
    ker /= ker.sum()
    for b in range(len(SHADOW_BANDS_M)):
        for ax in (0, 1):
            tau[b] = sum(wgt * np.roll(tau[b], sh, axis=ax) for sh, wgt in zip(range(-rad, rad + 1), ker))
    rgb = np.clip(np.round(tau / SHADOW_TAU_MAX * 255.0), 0, 255).astype(np.uint8)
    out = np.full((n, n, 4), 255, np.uint8)
    out[..., :3] = np.moveaxis(rgb, 0, -1)
    return out, tau


def png_rgba8(path: Path, rgba: np.ndarray):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def inward_box(path: Path):
    """Unit box [-1, 1]^3 (glTF game frame) whose triangles face INTO the box."""
    pos, nrm, idx = [], [], []
    for axis in range(3):
        for sgn in (1.0, -1.0):
            n = np.zeros(3)
            n[axis] = sgn
            u = np.zeros(3)
            u[(axis + 1) % 3] = 1.0
            v = np.cross(n, u)                            # u x v = n (outward)
            c = n
            q = [c - u - v, c + u - v, c + u + v, c - u + v]
            b = len(pos)
            pos += q
            nrm += [-n] * 4
            idx += [[b, b + 2, b + 1], [b, b + 3, b + 2]]  # reversed winding: front face looks inward
    write_glb(path, [{"name": "M_XinyiClouds_Cheap", "positions": np.array(pos, np.float32),
                      "normals": np.array(nrm, np.float32), "indices": np.array(idx, np.uint32)}],
              "cloud_cheap_box")


def main():
    st = json.loads(STATE.read_text(encoding="utf-8"))
    cells_doc = json.loads(CELLS.read_text(encoding="utf-8"))
    if cells_doc.get("state") != STATE.name:
        raise SystemExit("cells file was not built from %s" % STATE.name)
    T = float(cells_doc["tile_m"])
    seed = int(st["seed"])
    cells = cells_doc["cells"]
    OUT.mkdir(parents=True, exist_ok=True)

    # NEAR: per-cell lobes (v0 shapes; the cell's uniform squash is now stored per lobe)
    shapes = []
    for ci, c in enumerate(cells):
        rng = np.random.default_rng([seed, 0x0C4EA9, ci])
        broken = c["archetype"] != "fair_weather_cumulus"
        fn = broken_lobes if broken else cumulus_lobes
        lobes, k = fn(rng, float(c["radius_m"]), float(c["base_m"]), float(c["top_m"]))
        L5 = [list(map(float, L)) + [float(k)] for L in lobes]
        mid, half, bound = box_of(L5, float(c["base_m"]), ERODE_PAD)
        shapes.append({"lobes5": L5, "mid": mid, "half": half, "seed01": float(rng.uniform()),
                       "bound": bound, "base": float(c["base_m"])})

    # FAR: clusters of neighbouring cells (cumulus and broken patches grouped separately)
    cum = [i for i, c in enumerate(cells) if c["archetype"] == "fair_weather_cumulus"]
    brk = [i for i, c in enumerate(cells) if c["archetype"] != "fair_weather_cumulus"]
    groups = [(g, False) for g in clusters_of(cells, cum, T, LINK_GAP_M, MAX_LOBES, MAX_CLUSTER_EXTENT_M)[0]]
    groups += [(g, True) for g in clusters_of(cells, brk, T, 0.0, MAX_LOBES, 9000.0)[0]]
    far = []
    for gi, (g, broken) in enumerate(groups):
        rng = np.random.default_rng([seed, 0x0FA2C1, gi])
        L5, base, ref = far_cluster_lobes(rng, cells, g, T, broken)
        mid, half, bound = box_of(L5, base, ERODE_PAD)
        far.append({"cells": g, "broken": broken, "lobes5": L5, "ref": ref, "mid": mid, "half": half,
                    "seed01": float(rng.uniform()), "bound": bound, "base": base})

    inst = []

    def emit(role, key, s, e0, n0, radius):
        for ox in (-T, 0.0, T):
            for oy in (-T, 0.0, T):
                e, n = e0 + ox + s["mid"][0], n0 + oy + s["mid"][1]
                if math.hypot(e, n) > radius:
                    continue
                cpd = pack_lobes(s["lobes5"], s["mid"])
                cpd += [s["base"] - s["mid"][2], 1.0 if role == "near" else -1.0, s["seed01"], s["bound"]]
                inst.append({
                    "role": role, key[0]: key[1], "wrap": [int(ox / T), int(oy / T)],
                    "ue_location_cm": [round(e * 100.0, 1), round(-n * 100.0, 1), round(s["mid"][2] * 100.0, 1)],
                    "ue_scale": [round(float(s["half"][0]), 3), round(float(s["half"][1]), 3), round(float(s["half"][2]), 3)],
                    "cpd": [round(float(v), 3) for v in cpd],
                })
    for ci, (c, s) in enumerate(zip(cells, shapes)):
        emit("near", ("cell", ci), s, c["centre_enu_m"][0], c["centre_enu_m"][1], SPAWN_RADIUS_M)
    for gi, s in enumerate(far):
        emit("far", ("cluster", gi), s, s["ref"][0], s["ref"][1], FAR_SPAWN_RADIUS_M)
    doc = {"schema": "acw.cloud_cheap/1", "role": "Cheap Cloud Renderer v1 (experimental) inputs; derived "
           "from clouds_v0.cells.json, renderer detail only (not cloud state)", "state": STATE.name,
           "cells_file": CELLS.name, "tile_m": T, "spawn_radius_m": {"near": SPAWN_RADIUS_M, "far": FAR_SPAWN_RADIUS_M},
           "max_lobes": MAX_LOBES, "clusters": [{"cells": s["cells"], "broken": s["broken"]} for s in far],
           "instances": inst}
    (OUT / "clouds_v0.cheap.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    inward_box(OUT / "cloud_cheap_box.glb")

    shadow, tau = bake_shadow(shapes, cells, T)
    png_rgba8(OUT / "cloud_cheap_shadow_1024.png", shadow)

    # value-noise lattice for the iq-style texture 3D noise: G(i, j) = R(i + 37, j + 17)
    nrng = np.random.default_rng([seed, 0x0A015E])
    r = nrng.integers(0, 256, (256, 256), dtype=np.int64)
    b = nrng.integers(0, 256, (256, 256), dtype=np.int64)
    g = np.roll(np.roll(r, -17, axis=0), -37, axis=1)
    a = np.roll(np.roll(b, -17, axis=0), -37, axis=1)
    noise = np.stack([r, g, b, a], axis=-1).astype(np.uint8)
    png_rgba8(OUT / "cloud_cheap_noise_256.png", noise)

    lobes_n = [len(s["lobes5"]) for s in shapes]
    sizes = [len(s["cells"]) for s in far]
    # every cell is drawn by exactly one far cluster (accounting check, fails closed)
    owned = sorted(i for s in far for i in s["cells"])
    if owned != list(range(len(cells))):
        raise SystemExit("far clusters do not partition the cells")
    near_n = sum(1 for i in inst if i["role"] == "near")
    rep = {
        "status": "PASS_CLOUD_CHEAP",
        "experimental": True,
        "version": 1,
        "tile_m": T,
        "state": str(STATE.relative_to(REPO)).replace("\\", "/"),
        "seed": seed,
        "cells": len(cells),
        "instances": len(inst),
        "near_instances": near_n,
        "far_instances": len(inst) - near_n,
        "wrap_copies": sum(1 for i in inst if i["wrap"] != [0, 0]),
        "lobes_per_cell": {"min": min(lobes_n), "max": max(lobes_n), "mean": round(float(np.mean(lobes_n)), 2)},
        "far_clusters": {"count": len(far), "broken": sum(1 for s in far if s["broken"]),
                         "cells_per_cluster": {"min": min(sizes), "max": max(sizes), "mean": round(float(np.mean(sizes)), 2)},
                         "tower_lobes": sum(1 for s in far for L in s["lobes5"] if L[4] > 1.0)},
        "max_proxy_half_extent_m": {"near": [round(float(max(s["half"][i] for s in shapes)), 1) for i in range(3)],
                                    "far": [round(float(max(s["half"][i] for s in far)), 1) for i in range(3)]},
        "shadow": {"bands_m": SHADOW_BANDS_M, "sigma": SHADOW_SIGMA, "tau_max": SHADOW_TAU_MAX, "blur_m": SHADOW_BLUR_M,
                   "texel_m": T / SHADOW_RES,
                   "shadowed_area_fraction_tau_gt_0_5": round(float((tau.sum(0) > 0.5).mean()), 4)},
        "cheap_json_sha256": hashlib.sha256((OUT / "clouds_v0.cheap.json").read_bytes()).hexdigest(),
        "noise_sha256": hashlib.sha256((OUT / "cloud_cheap_noise_256.png").read_bytes()).hexdigest(),
        "shadow_sha256": hashlib.sha256((OUT / "cloud_cheap_shadow_1024.png").read_bytes()).hexdigest(),
    }
    (OUT / "cloud_cheap.report.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(rep))


if __name__ == "__main__":
    main()
