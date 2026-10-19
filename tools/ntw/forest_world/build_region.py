"""North Taiwan forest world v1 - region builder (offline, deterministic).

Region: Yangmingshan / Tatun volcano group + north coast + Shilin/Beitou basin edge + Guanyinshan, EPSG:3826
E 289,540-316,000 / N 2,773,540-2,800,000 (26.46 km square). Chosen so that the official MOI 2025 20 m DEM (TGOS sheets of
Taipei City + New Taipei City, read with tools/ntw/tgos_dem.py) has NO missing land node: the Keelung City sheets (east) and the
Taoyuan gap (south-west) are outside it.

Inputs (read only):
* TGOS 20 m DEM sheet ZIPs (data/generated/ntw/tgos or --tgos-dir), nodes used exactly; 10 m Landscape vertices between nodes are an
  interpolating bicubic spline (every official 20 m node is reproduced, before 16-bit quantisation).
* data/ntw/forest/inputs_v1/esri2021_20m.tif (PR #39 land-cover clip, Esri/Sentinel-2 2021, CC BY 4.0). Only the source "Trees" class
  becomes forest; grass / crops / urban / water / bare stay open.

Art-direction species policy v1 (NOT a survey - PR #39 / PR #38 could not obtain official forest-type polygons, HTTP 403):
* 柳杉 Cryptomeria plantation stands: Voronoi parcels (~280 m) of tree cover at 320-980 m, slope <= 32 deg, >= 75 % tree cover,
  30 % of eligible parcels (seeded) -> straight-edged dark plantation blocks in rows, as seen on Yangmingshan's mid slopes.
* 相思樹 Acacia: low hills (< ~420 m), favoured on convex upper slopes, in low-frequency clumps (old charcoal / erosion plantings).
* 紅楠 (form A, chain T) + 紅楠 second crown form B: all other tree cover; form B favoured on ridges / edges. Above ~750 m trees are
  shorter (wind-pruned summit forest); summit grassland (箭竹 / 芒草) comes from the land-cover grass class, never planted.
No new species; a few open-land trees (rangeland / crops) avoid cookie-cut forest edges.

Outputs (data/generated/ntw/forest_world/<run>/, git-ignored): terrain.r16 / terrain.json / height_q.npy, mask PNGs for the Landscape
material, trees/tile_<ix>_<iy>.bin + trees.json (per 1 km tile, per form/variant), preview PNGs, manifest.json (hashes, stats).

    python tools/ntw/forest_world/build_region.py --out data/generated/ntw/forest_world/v1 [--tgos-dir <dir>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from scipy import ndimage
from scipy.interpolate import RectBivariateSpline
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from tools.ntw.tgos_dem import Dem  # noqa: E402

E0, N0 = 289_540.0, 2_773_540.0          # south-west corner (on the official 20 m node grid)
SPACING = 10.0                           # Landscape vertex spacing (m)
COMPONENTS, SECTIONS, SECTION_QUADS = 21, 2, 63
QUADS = COMPONENTS * SECTIONS * SECTION_QUADS          # 2646
SIZE = QUADS + 1                                       # 2647 vertices
EXTENT = QUADS * SPACING                               # 26,460 m
E1, N1 = E0 + EXTENT, N0 + EXTENT
ORIGIN = (296_000.0, 2_760_000.0)        # WorldSpec runtime origin (worlds/north_taiwan_224.json): UE X=(E-oE)*100, Y=-(N-oN)*100
SCALE_Z = 256.0                          # 1 raw unit = 2 cm, range +-655 m around H_REF
H_REF = 540.0
TILE_M = 1000.0                          # tree tile = World Partition actor granularity
MASK_PX = 2048                           # Landscape material mask textures (12.9 m / texel)
SEED = 20261019
CLASS = {"water": 1, "trees": 2, "flooded": 4, "crops": 5, "built": 7, "bare": 8, "unknown": 10, "range": 11}

# form -> (variants, scale range); meshes are bound in Unreal (adapters/unreal/ntwforest/nf_common.py)
FORMS = {"A": ((0, 1, 2), (0.85, 1.25)), "B": ((3, 4), (0.80, 1.15)), "C": ((5, 6, 7), (0.80, 1.15)), "J": ((8, 9), (0.85, 1.10))}
# nominal tree height at scale 1 (m), used for the canopy-shell height mask only
FORM_H = {"A": 10.3, "B": 7.7, "C": 9.0, "J": 20.5}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def smooth_noise(shape, cell_px, rng, octaves=2):
    """Deterministic value noise in [0,1] (bicubic-upsampled random lattice), `cell_px` pixels per lattice cell."""
    out = np.zeros(shape, np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        c = max(cell_px / (2 ** o), 2.0)
        g = rng.random((int(shape[0] / c) + 4, int(shape[1] / c) + 4)).astype(np.float32)
        z = ndimage.zoom(g, c, order=3)[: shape[0], : shape[1]]
        out += amp * z
        tot += amp
        amp *= 0.5
    out /= tot
    lo, hi = np.percentile(out, 1), np.percentile(out, 99)
    return np.clip((out - lo) / (hi - lo), 0, 1)


def terrain(out, tgos_dir):
    bbox = (E0 - 40, N0 - 40, E1 + 40, N1 + 40)
    with Dem(packages=["臺北市", "新北市"], cache_dir=tgos_dir) as d:
        z20, _, sheets, dup = d.mosaic(bbox)          # rows south -> north
        sheet_meta = sorted({(s.package, s.number) for s in sheets})
    land = ~np.isnan(z20)
    with rasterio.open(REPO / "data/ntw/forest/inputs_v1/esri2021_20m.tif") as r:   # land cover on the same 20 m node grid (centre sample)
        inv = ~r.transform
        cc, rr = inv * (E0 - 40 + 20.0 * np.arange(z20.shape[1]) + 0.01, np.full(z20.shape[1], 0.0))
        _, rr = inv * (np.full(z20.shape[0], E0), N0 - 40 + 20.0 * np.arange(z20.shape[0]) + 0.01)
        lcn = r.read(1)[np.floor(rr).astype(int)[:, None], np.floor(cc).astype(int)[None, :]]
    land_without_node = int(((lcn != CLASS["water"]) & (lcn != 0) & ~land).sum())
    # sea / no-node fill: a gently shelving sea floor below the 0 m water plane (never a land surface)
    dist = ndimage.distance_transform_edt(~land) * 20.0
    nearest = ndimage.distance_transform_edt(~land, return_distances=False, return_indices=True)
    coast_h = z20[tuple(nearest)]
    zf = np.where(land, z20, np.minimum(coast_h, 0.0) - np.minimum(2.0 + 0.03 * dist, 45.0))
    ys = N0 - 40 + 20.0 * np.arange(z20.shape[0])
    xs = E0 - 40 + 20.0 * np.arange(z20.shape[1])
    spl = RectBivariateSpline(ys, xs, zf, kx=3, ky=3, s=0)
    e = E0 + SPACING * np.arange(SIZE)
    n = N1 - SPACING * np.arange(SIZE)                 # row 0 = north
    h = spl(n[::-1], e)[::-1].astype(np.float64)       # spline wants increasing y
    raw_f = 32768.0 + (h - H_REF) * 128.0 * (100.0 / SCALE_Z)
    if raw_f.min() < 0 or raw_f.max() > 65535:
        raise SystemExit("height range does not fit uint16")
    raw = np.round(raw_f).astype("<u2")
    raw.tofile(out / "terrain.r16")
    hq = ((raw.astype(np.float64) - 32768.0) / 128.0 * (SCALE_Z / 100.0) + H_REF).astype(np.float32)
    np.save(out / "height_q.npy", hq)
    # node reproduction check (official node vs quantised Landscape vertex at the same position)
    node_rows = slice(0, SIZE, 2)
    jj = np.arange(0, SIZE, 2)
    ni = ((n[jj] - (N0 - 40)) / 20.0).round().astype(int)
    ei = ((e[jj] - (E0 - 40)) / 20.0).round().astype(int)
    official = z20[np.ix_(ni, ei)]
    diff = np.abs(hq[node_rows, node_rows] - official)
    land_nodes = ~np.isnan(official)
    landmask10 = ndimage.zoom(land.astype(np.uint8), 2, order=0)
    land_frac = float(np.mean(~np.isnan(official)))
    meta = {
        "source": {"dataset": "MOI 2025 20 m DEM sheets (TGOS, data.gov.tw 176927)", "packages": ["臺北市", "新北市"],
                   "sheets": len(sheet_meta), "duplicate_nodes": dup, "tgos_dir": str(tgos_dir)},
        "crs": "EPSG:3826 / TWVD2001", "bbox_3826": [E0, N0, E1, N1], "spacing_m": SPACING, "size": [SIZE, SIZE],
        "landscape": {"components": [COMPONENTS, COMPONENTS], "num_subsections": SECTIONS, "subsection_quads": SECTION_QUADS,
                      "scale_xyz": [SPACING * 100.0, SPACING * 100.0, SCALE_Z],
                      "location_cm": [(E0 - ORIGIN[0]) * 100.0, -(N1 - ORIGIN[1]) * 100.0, H_REF * 100.0], "h_ref_m": H_REF,
                      "z_rule": "UE Z cm = location.z + (raw - 32768) / 128 * scale_z  (= TWVD2001 height * 100)"},
        "ue_frame": "WorldSpec north_taiwan_224: UE X = (E - 296000) * 100, UE Y = -(N - 2760000) * 100, UE Z = height * 100",
        "official_nodes_in_region": int(land_nodes.sum()), "landcover_land_px_without_dem_node": land_without_node, "land_fraction": land_frac,
        "official_node_max_abs_diff_m": float(np.nanmax(diff)), "quantisation_m": SCALE_Z / 128.0 / 100.0,
        "sea_fill": "no official node = sea (outside DEM coverage): min(coast height, 0) - min(2 + 0.03*dist, 45) m",
        "height_m": {"min": float(hq.min()), "max": float(hq.max())},
    }
    return hq, meta, landmask10


def landcover():
    with rasterio.open(REPO / "data/ntw/forest/inputs_v1/esri2021_20m.tif") as r:
        w = rasterio.windows.from_bounds(E0, N0, E1, N1, r.transform)
        lc = r.read(1, window=w)                       # row 0 = north, 1323 x 1323 at 20 m
    if lc.shape != (1323, 1323):
        raise SystemExit("unexpected land-cover window %s" % (lc.shape,))
    return lc


def species(hq, lc, rng):
    """Per-10 m-pixel fields used by the scatter (row 0 = north)."""
    lc10 = np.repeat(np.repeat(lc, 2, 0), 2, 1)[:SIZE, :SIZE]
    lc10 = np.pad(lc10, ((0, SIZE - lc10.shape[0]), (0, SIZE - lc10.shape[1])), mode="edge")
    trees = lc10 == CLASS["trees"]
    gy, gx = np.gradient(hq.astype(np.float64), SPACING)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    tpi = hq - ndimage.uniform_filter(hq, size=31)     # +-150 m window: ridges > 0, valleys < 0
    # Cryptomeria plantation parcels: Voronoi of jittered seeds every ~280 m
    sp = 28
    sy, sx = np.mgrid[sp // 2:SIZE:sp, sp // 2:SIZE:sp]
    seeds = np.stack([sy.ravel() + rng.integers(-sp // 3, sp // 3 + 1, sy.size),
                      sx.ravel() + rng.integers(-sp // 3, sp // 3 + 1, sx.size)], 1).clip(0, SIZE - 1)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    _, parcel = cKDTree(seeds).query(np.stack([yy.ravel(), xx.ravel()], 1), workers=-1)
    parcel = parcel.reshape(SIZE, SIZE)
    npar = len(seeds)
    cnt = np.bincount(parcel.ravel(), minlength=npar)
    tcnt = np.bincount(parcel.ravel(), weights=trees.ravel(), minlength=npar)
    hmean = np.bincount(parcel.ravel(), weights=hq.ravel(), minlength=npar) / np.maximum(cnt, 1)
    smean = np.bincount(parcel.ravel(), weights=slope.ravel(), minlength=npar) / np.maximum(cnt, 1)
    eligible = (hmean >= 320) & (hmean <= 980) & (smean <= 32) & (tcnt / np.maximum(cnt, 1) >= 0.75)
    district = smooth_noise((SIZE, SIZE), 150, rng, octaves=1)[seeds[:, 0], seeds[:, 1]]   # ~1.5 km plantation districts
    chosen = eligible & (rng.random(npar) < np.where(district > 0.45, 0.55, 0.06))
    crypt = chosen[parcel] & trees
    # Acacia clumps on low convex slopes
    p_ac = np.clip((420.0 - hq) / 300.0, 0, 1) * np.clip(0.55 + 0.45 * tpi / 12.0, 0.1, 1.0)
    ac_noise = smooth_noise((SIZE, SIZE), 22, rng)     # ~220 m clumps
    acacia = trees & ~crypt & (ac_noise < 0.75 * p_ac)
    # tone patches (shared by all broadleaf forms): stand-scale (~120 m) and grove-scale (~40 m)
    tone = 0.65 * smooth_noise((SIZE, SIZE), 12, rng) + 0.35 * smooth_noise((SIZE, SIZE), 4, rng)
    ridge = np.clip(tpi / 10.0, -1, 1)
    edge = trees & ~ndimage.binary_erosion(trees, iterations=2)
    return dict(lc10=lc10, trees=trees, slope=slope, tpi=tpi, ridge=ridge, crypt=crypt, acacia=acacia, tone=tone, edge=edge,
                parcels={"total": int(npar), "eligible": int(eligible.sum()), "chosen": int(chosen.sum())})


def scatter(hq, F, rng):
    """Jittered-grid candidates, accepted per pixel probability; returns structured arrays (E, N, Z, form, variant, scale...)."""
    out = []
    lc10 = F["lc10"]

    def candidates(spacing, mask_px, rows=False):
        k = spacing / SPACING
        ny = int(SIZE / k)
        gy, gx = np.mgrid[0:ny, 0:ny].astype(np.float64)
        if rows:   # plantation rows: small jitter along rows, tiny across
            py, px = (gy + 0.5 + rng.normal(0, 0.06, gy.shape)) * k, (gx + 0.5 + rng.normal(0, 0.18, gx.shape)) * k
        else:
            py, px = (gy + rng.random(gy.shape)) * k, (gx + rng.random(gx.shape)) * k
        py, px = py.ravel(), px.ravel()
        ok = (py < SIZE - 1) & (px < SIZE - 1)
        py, px = py[ok], px[ok]
        iy, ix = py.astype(int), px.astype(int)
        sel = mask_px[iy, ix]
        return py[sel], px[sel], iy[sel], ix[sel]

    def keep(py, px, iy, ix, prob):
        m = rng.random(len(py)) < prob
        return py[m], px[m], iy[m], ix[m]

    # broadleaf + acacia, 7.5 m jittered grid (178 candidates / ha)
    broad = F["trees"] & ~F["crypt"]
    py, px, iy, ix = candidates(7.5, broad)
    p = np.where(F["edge"][iy, ix], 0.45, 0.62)
    py, px, iy, ix = keep(py, px, iy, ix, p)
    is_ac = F["acacia"][iy, ix]
    ridge = F["ridge"][iy, ix]
    tone = F["tone"][iy, ix]
    u = rng.random(len(py))
    is_b = ~is_ac & (u < 0.25 + 0.30 * np.clip(ridge, 0, 1) + 0.20 * F["edge"][iy, ix])
    form = np.where(is_ac, "C", np.where(is_b, "B", "A"))
    out.append((py, px, iy, ix, form, tone))
    # open-land trees: rangeland / crops / flooded vegetation (sparse, 7.5 m grid, very low probability)
    open_p = np.zeros(lc10.shape, np.float32)
    open_p[lc10 == CLASS["range"]] = 0.035
    open_p[lc10 == CLASS["crops"]] = 0.02
    open_p[lc10 == CLASS["flooded"]] = 0.05
    py, px, iy, ix = candidates(7.5, open_p > 0)
    py, px, iy, ix = keep(py, px, iy, ix, open_p[iy, ix])
    form = np.where(rng.random(len(py)) < 0.5, "B", "A")
    form = np.where(hq[iy, ix] < 250, np.where(rng.random(len(py)) < 0.5, "C", form), form)
    out.append((py, px, iy, ix, form, F["tone"][iy, ix]))
    # cryptomeria plantation rows, 6 m spacing (~280 / ha), 4 % gaps
    py, px, iy, ix = candidates(6.0, F["crypt"], rows=True)
    py, px, iy, ix = keep(py, px, iy, ix, np.where(F["edge"][iy, ix], 0.85, 0.96))
    out.append((py, px, iy, ix, np.full(len(py), "J"), F["tone"][iy, ix]))

    py = np.concatenate([o[0] for o in out]); px = np.concatenate([o[1] for o in out])
    iy = np.concatenate([o[2] for o in out]); ix = np.concatenate([o[3] for o in out])
    form = np.concatenate([o[4] for o in out]); tone = np.concatenate([o[5] for o in out])
    n = len(py)
    # bilinear height on the quantised Landscape grid, sunk 0.3 m (never floats over either Landscape triangle diagonal)
    fy, fx = py - iy, px - ix
    h00, h01, h10, h11 = hq[iy, ix], hq[iy, ix + 1], hq[iy + 1, ix], hq[iy + 1, ix + 1]
    za = np.where(fx > fy, h00 + fx * (h01 - h00) + fy * (h11 - h01), h00 + fy * (h10 - h00) + fx * (h11 - h10))  # diagonal 00-11
    zb = np.where(fx + fy < 1, h00 + fx * (h01 - h00) + fy * (h10 - h00), h11 + (1 - fx) * (h10 - h11) + (1 - fy) * (h01 - h11))
    z = np.minimum(za, zb) - 0.3
    E = E0 + px * SPACING
    N = N1 - py * SPACING
    # variant from tone patches (+ ridge = sunnier / lighter, valley = darker)
    t = np.clip(tone + 0.15 * F["ridge"][iy, ix], 0, 1)
    var = np.zeros(n, np.int16)
    for f, (vs, (s0, s1)) in FORMS.items():
        m = form == f
        q = np.clip((t[m] * len(vs)).astype(int), 0, len(vs) - 1)
        var[m] = np.array(vs)[q]
    # scale: base range, taller in valleys, shorter on high ridges / summits (wind-pruned)
    s_lo = np.array([FORMS[f][1][0] for f in "ABCJ"]); s_hi = np.array([FORMS[f][1][1] for f in "ABCJ"])
    fi = np.searchsorted(np.array(list("ABCJ")), form)
    s = s_lo[fi] + (s_hi[fi] - s_lo[fi]) * rng.random(n)
    s *= 1.0 - 0.08 * F["ridge"][iy, ix]
    h = hq[iy, ix]
    s *= np.where(form == "J", 1.0, np.clip(1.0 - (h - 700.0) / 400.0 * 0.35, 0.6, 1.0))
    sx = s * (0.92 + 0.16 * rng.random(n)); sy = s * (0.92 + 0.16 * rng.random(n))
    sz = s * np.where(form == "J", 0.95 + 0.1 * rng.random(n), 0.9 + 0.2 * rng.random(n))
    yaw = rng.random(n) * 360.0
    lean = np.where(form == "J", 1.0, 3.5) * rng.normal(0, 1, (2, n))
    return dict(E=E, N=N, Z=z, form=form, var=var, sx=sx, sy=sy, sz=sz, yaw=yaw, lean_e=lean[0], lean_n=lean[1])


def write_tiles(out, T):
    td = out / "trees"
    td.mkdir(exist_ok=True)
    tix = np.floor((T["E"] - E0) / TILE_M).astype(int)
    tiy = np.floor((N1 - T["N"]) / TILE_M).astype(int)        # tile row 0 = north
    ntile = int(np.ceil(EXTENT / TILE_M))
    index = []
    code = {f: i for i, f in enumerate("ABCJ")}
    order = np.lexsort((T["var"], [code[f] for f in T["form"]], tix, tiy))
    keys = tiy[order] * 1000 + tix[order]
    bounds = np.flatnonzero(np.diff(keys)) + 1
    for chunk in np.split(order, bounds):
        if len(chunk) == 0:
            continue
        ty, tx = int(tiy[chunk[0]]), int(tix[chunk[0]])
        name = "tile_%02d_%02d.bin" % (tx, ty)
        groups = []
        with open(td / name, "wb") as fh:
            gkey = np.array([code[f] * 100 + v for f, v in zip(T["form"][chunk], T["var"][chunk])])
            gb = np.flatnonzero(np.diff(gkey)) + 1
            parts = np.split(chunk, gb)
            fh.write(struct.pack("<I", len(parts)))
            for part in parts:
                f, v = T["form"][part[0]], int(T["var"][part[0]])
                rec = np.stack([(T["E"][part] - ORIGIN[0]) * 100.0, -(T["N"][part] - ORIGIN[1]) * 100.0, T["Z"][part] * 100.0,
                                T["yaw"][part], T["sx"][part], T["sy"][part], T["sz"][part], T["lean_e"][part], T["lean_n"][part]], 1)
                fh.write(struct.pack("<cHI", f.encode(), v, len(part)))
                fh.write(rec.astype("<f8").tobytes())       # doubles: UE world coordinates reach ~4,000,000 cm
                groups.append({"form": f, "variant": v, "count": int(len(part))})
        cx = E0 + (tx + 0.5) * TILE_M
        cy = N1 - (ty + 0.5) * TILE_M
        index.append({"file": name, "tx": tx, "ty": ty, "center_ue_cm": [(cx - ORIGIN[0]) * 100.0, -(cy - ORIGIN[1]) * 100.0],
                      "count": int(len(chunk)), "groups": groups})
    return index, ntile


def masks(out, hq, lc, F, T):
    """Two RGBA8 mask textures over the region (row 0 = north) for the Landscape material."""
    k = MASK_PX / lc.shape[0]

    def field20(classes):
        m = np.isin(lc, classes).astype(np.float32)
        m = ndimage.gaussian_filter(m, 0.6)
        return ndimage.zoom(m, k, order=1)[:MASK_PX, :MASK_PX]

    forest = field20([CLASS["trees"]])
    grass = field20([CLASS["range"]])
    urban = field20([CLASS["built"]])
    water = field20([CLASS["water"]])
    crops = field20([CLASS["crops"], CLASS["bare"], CLASS["flooded"]])
    # species fractions from the PLACED trees (so the far canopy matches what the near trees are)
    px = np.clip(((T["E"] - E0) / EXTENT * MASK_PX).astype(int), 0, MASK_PX - 1)
    py = np.clip(((N1 - T["N"]) / EXTENT * MASK_PX).astype(int), 0, MASK_PX - 1)
    allc = np.bincount(py * MASK_PX + px, minlength=MASK_PX * MASK_PX).reshape(MASK_PX, MASK_PX).astype(np.float32)

    def frac(sel, sigma=1.0):
        c = np.bincount(py[sel] * MASK_PX + px[sel], minlength=MASK_PX * MASK_PX).reshape(MASK_PX, MASK_PX).astype(np.float32)
        return ndimage.gaussian_filter(c, sigma) / np.maximum(ndimage.gaussian_filter(allc, sigma), 1e-3)

    crypt = frac(T["form"] == "J")
    acacia = frac(T["form"] == "C")
    # canopy-shell height: mean nominal tree top height x local tree cover, metres / 32
    htop = np.array([FORM_H[f] for f in T["form"]]) * T["sz"]
    hsum = np.bincount(py * MASK_PX + px, weights=htop, minlength=MASK_PX * MASK_PX).reshape(MASK_PX, MASK_PX)
    hmean = ndimage.gaussian_filter(hsum, 1.5) / np.maximum(ndimage.gaussian_filter(allc, 1.5), 1e-3)
    shell = np.clip(hmean * ndimage.gaussian_filter(forest, 1.5) / 32.0, 0, 1)
    to8 = lambda a: np.clip(np.round(a * 255), 0, 255).astype(np.uint8)  # noqa: E731
    m1 = np.stack([to8(forest), to8(grass), to8(urban), to8(water)], -1)
    m2 = np.stack([to8(crypt), to8(acacia), to8(crops), to8(shell)], -1)
    Image.fromarray(m1, "RGBA").save(out / "T_NF_Mask1.png")
    Image.fromarray(m2, "RGBA").save(out / "T_NF_Mask2.png")
    return m1, m2


def previews(out, hq, F, T):
    gy, gx = np.gradient(hq.astype(np.float64), SPACING)
    slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    hs = np.sin(np.radians(40)) * np.cos(slope) + np.cos(np.radians(40)) * np.sin(slope) * np.cos(np.radians(315) - aspect)
    pal = {1: (40, 70, 140), 2: (52, 105, 45), 4: (60, 120, 120), 5: (200, 190, 90), 7: (150, 150, 150), 8: (170, 140, 110),
           10: (255, 255, 255), 11: (180, 190, 95)}
    lc10 = F["lc10"]
    rgb = np.zeros(lc10.shape + (3,), np.float32)
    for c, v in pal.items():
        rgb[lc10 == c] = v
    rgb[F["acacia"]] = (120, 140, 40)
    rgb[F["crypt"]] = (15, 55, 45)
    rgb[hq < 0] = (30, 50, 110)
    rgb *= np.clip(hs, 0.25, 1.0)[..., None] * 1.25
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((1323, 1323), Image.LANCZOS).save(out / "preview_species.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tgos-dir", default=str(REPO / "data/generated/ntw/tgos"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    hq, tmeta, _ = terrain(out, Path(a.tgos_dir))
    (out / "terrain.json").write_text(json.dumps(tmeta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    lc = landcover()
    F = species(hq, lc, rng)
    T = scatter(hq, F, rng)
    index, ntile = write_tiles(out, T)
    masks(out, hq, lc, F, T)
    previews(out, hq, F, T)
    area = lambda m: float(m.sum() * SPACING * SPACING / 1e6)  # noqa: E731
    counts = {f: int((T["form"] == f).sum()) for f in "ABCJ"}
    lcc = {k: float((lc == v).sum() * 400 / 1e6) for k, v in CLASS.items()}
    manifest = {
        "schema": "ntw-forest-world-v1", "seed": SEED, "bbox_3826": [E0, N0, E1, N1], "tile_m": TILE_M, "tiles": [ntile, ntile],
        "tile_files": len(index), "terrain": tmeta, "landcover_km2": lcc,
        "forest_km2": area(F["trees"]), "cryptomeria_stand_km2": area(F["crypt"]), "acacia_zone_km2": area(F["acacia"]),
        "parcels": F["parcels"], "trees": {"total": int(len(T["E"])), "per_form": counts,
                                           "per_ha_forest": float(len(T["E"]) / max(area(F["trees"]) * 100, 1e-9))},
        "species_policy": "art-direction v1 (see module docstring); NOT a forest-type survey",
        "outputs": {p.name: sha(p) for p in sorted(out.glob("*")) if p.is_file() and p.suffix in (".r16", ".png", ".npy")},
        "build_s": round(time.time() - t0, 1),
    }
    (out / "trees.json").write_text(json.dumps({"tile_m": TILE_M, "origin_3826": ORIGIN, "record": "x_cm,y_cm,z_cm,yaw_deg,sx,sy,sz,lean_e_deg,lean_n_deg (float64)",
                                                "tiles": index}, indent=0) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("forest_km2", "cryptomeria_stand_km2", "acacia_zone_km2", "parcels", "trees", "tile_files", "build_s")}, indent=1))
    print(json.dumps({k: tmeta[k] for k in ("landcover_land_px_without_dem_node", "official_node_max_abs_diff_m", "land_fraction", "height_m")}, indent=1))


if __name__ == "__main__":
    main()
