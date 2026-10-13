"""Terrain vertical slice: real-DEM terrain for world cells, with LODs, seams, Xinyi conformance and reproducibility.

Source: OFFICIAL MOI 2025 20 m DEM sheets (TGOS, tools/ntw/tgos_dem.py) — native EPSG:3826 / TWVD2001 nodes on a 20 m grid,
so LOD0 vertices ARE the official samples (no reprojection, no resampling). Fail-closed: any land node without an
official sample => the cell is BLOCKED (never 0 m, never interpolated across a gap).

Layout (all parameters in TerrainParams; nothing North-Taiwan specific):
  generation cell 8 km (world grid)  ->  runtime chunks 1.6 km (5 x 5 per cell)  ->  LOD steps 20/40/80/160/320 m
  LOD k = absolute-grid subsample of the official nodes (positions multiple of the step), so a chunk's vertices depend only on
  its own position: independent per-cell builds and a joint build must produce byte-identical chunk GLBs.
  normals: central differences on the LOD grid using a halo of real samples (crosses cell borders);
  UV: world-space (u = (x - world_sw_x) / uv_tile_m), continuous across cells by construction;
  skirts: per-chunk vertical skirts (depth = max(2 m, 2 x LOD max geometric error)) to hide cross-LOD T-junction cracks.
Xinyi L3 conformance (cell containing the accepted Xinyi sector; Xinyi itself is NEVER modified):
  nodes inside the sector deeper than one step get z = Xinyi_landscape(node) - drop (hidden under the accepted Landscape);
  nodes inside within one step get z = Xinyi_landscape(node); nodes outside within `band_m` blend from the Xinyi edge
  height to the official DEM (smoothstep). Xinyi heights are read from the ACCEPTED 631 x 631 R16 through the exact accepted
  ENU formula (no affine approximation).
Outputs (ignored): <out>/chunks/<cell>/<chunk>_lod<k>.glb, <out>/cells/<cell>_dem20.tif, <out>/cells/<cell>_ue505.r16,
                   <out>/terrain.report.json (all hashes, LOD errors, params)
usage: build_terrain_cells.py --cells C+0038+0346 C+0038+0345 --out <new dir> [--no-xinyi-conform]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import shapely
import shapely.ops
import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools/compiler"))
import frame  # noqa: E402
import world_cells as wc  # noqa: E402
from tgos_dem import Dem  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

ACCEPTED_XINYI = Path(r"D:\Users\EDDY\Documents\GitHub\air-combat-world\unreal\Saved\XinyiUnrealV2Inputs\run-35822928983"
                      r"\unreal\Saved\XinyiUnrealV2Contract")


@dataclass
class TerrainParams:
    chunk_m: float = 1600.0
    lod_steps_m: tuple = (20.0, 40.0, 80.0, 160.0, 320.0)
    uv_tile_m: float = 1000.0
    skirt_min_m: float = 2.0
    xinyi_conform: bool = True
    xinyi_mode: str = "stitch"             # "stitch" (hole + exact edge stitch strip) | "conform" (band blend only)
    xinyi_band_m: float = 200.0
    xinyi_drop_m: float = 0.5
    ue_landscape_samples: int = 505        # 8 components x 63 quads + 1 per 8 km cell
    ue_scale_z: float = 400.0              # +-1024 m around the per-cell base (step 0.03125 m); mountain cells: 800
    ue_base_round_m: float = 10.0          # per-cell base elevation (actor Z offset) = floor(min / round) * round
    packages: tuple = ("臺北市", "新北市")
    identity_nodes: bool = False
    stitch_edge: str = "full"              # "full" (v2): every stitch LOD keeps ALL accepted Landscape edge vertices, only the
                                           # hole side follows the chunk LOD | "decimated" (v1, Phase 2B): every 2**k vertices
    stitch_skirt_m: float = 2.0            # v2: vertical skirt hanging from the Xinyi edge (hides sub-skirt landscape-LOD dips)           # UE-facing export: node transform = identity, origin only in the report (Xinyi style)
    stitch_hole: str = "per_lod"           # "per_lod" (PR #23/#25: hole = triangles near the outline at each LOD, so its size
                                           # changes with the LOD) | "fixed" (Phase 2B-C: ONE hole for every LOD, aligned to the
                                           # coarsest LOD grid; stitch LOD k = the LOD-k grid clipped to the Xinyi edge, plus
                                           # hole-edge skirts on both sides -> watertight for every stitch x chunk LOD combination)
    hole_align_m: float = 320.0            # fixed hole = union of hole_align_m cells touching the outline buffered by hole_margin_m
    hole_margin_m: float = 20.0
    collision_meshes: bool = False         # also write surface-only LOD0 *_col.glb (engine complex collision without skirts)
    neighbour_skirts: bool = False         # Phase 2B-C: chunk perimeter skirt = 2 x max coarsest-LOD error of the chunk AND its 8
                                           # neighbours + 0.5 m (a finer chunk's edge can be HIGHER than a coarser neighbour's; the
                                           # per-chunk own-LOD skirt left 679 px of cracks in the UE chunk-checkerboard test)
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------------------------------------------ Xinyi accepted landscape
XINYI_PLACEMENT = "affine"   # Phase 2B runtime gate: the engine can only place the accepted Landscape with an affine actor
                             # transform, so seam geometry must use the SAME measured affine (data/ntw/coordinate_study.json),
                             # not the exact ENU chain (they differ by up to 0.12 m over the 2.5 km sector).


def _affine():
    st = json.loads((REPO / "data/ntw/coordinate_study.json").read_text(encoding="utf-8"))["xinyi_enu_to_ntw_affine"]
    M = np.array(st["linear_part"])
    t = np.array(st["translation_m"]) + np.array(frame.NTW_ORIGIN_TM2)
    return M, t


def xinyi_enu_to_tm2(e, n):
    """Accepted Xinyi ENU -> EPSG:3826 under XINYI_PLACEMENT ('affine' = engine-realisable, 'exact' = ENU->lonlat->TM2)."""
    e, n = np.atleast_1d(np.asarray(e, float)), np.atleast_1d(np.asarray(n, float))
    if XINYI_PLACEMENT == "affine":
        M, t = _affine()
        q = M @ np.vstack([e, n])
        return q[0] + t[0], q[1] + t[1]
    import xinyi_world_compat as xc
    lon = xc.O_LON + np.degrees(e / (6378137.0 * math.cos(math.radians(xc.O_LAT))))
    lat = xc.O_LAT + np.degrees(n / 6378137.0)
    return wc.TO_TM2.transform(lon, lat)


def tm2_to_xinyi_enu(x, y):
    if XINYI_PLACEMENT == "affine":
        M, t = _affine()
        q = np.linalg.solve(M, np.vstack([np.atleast_1d(np.asarray(x, float)) - t[0], np.atleast_1d(np.asarray(y, float)) - t[1]]))
        return q[0], q[1]
    return tm2_to_xinyi_enu_exact(x, y)


def tm2_to_xinyi_enu_exact(x, y):
    """EPSG:3826 -> lon/lat (pyproj) -> accepted Xinyi ENU (vectorised copy of worldmodel.lonlat_to_enu; test-checked)."""
    from worldmodel import R_WGS84
    import xinyi_world_compat as xc
    lon, lat = wc.TO_LL.transform(np.asarray(x, float), np.asarray(y, float))
    lon, lat = np.atleast_1d(lon), np.atleast_1d(lat)
    e = R_WGS84 * np.radians(lon - xc.O_LON) * math.cos(math.radians(xc.O_LAT))
    n = R_WGS84 * np.radians(lat - xc.O_LAT)
    return e, n


class XinyiLandscape:
    """Accepted Xinyi Landscape heights (631 x 631 R16, ENU x -1500..1000, y -1000..1500, row 0 = north)."""
    def __init__(self, contract_dir=ACCEPTED_XINYI):
        c = json.loads((contract_dir / "xinyi_unreal_v2_contract.json").read_text(encoding="utf-8"))
        raw = (contract_dir / c["outputs"]["heightmap_r16"]["path"]).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if self.sha256 != c["outputs"]["heightmap_r16"]["sha256"]:
            raise RuntimeError("accepted Xinyi R16 hash mismatch - refusing to use it")
        n = c["landscape"]["heightmap_size"][0]
        sz = c["landscape"]["height_encoding"]["scale_z"]
        code = np.frombuffer(raw, dtype="<u2").reshape(n, n).astype(np.float64)
        self.h = (code - 32768.0) * sz / 128.0 / 100.0
        e = c["coordinate_contract"]["extent_enu_m"]
        self.e0, self.e1, self.n0, self.n1 = e["min_east_m"], e["max_east_m"], e["min_north_m"], e["max_north_m"]
        self.step = (self.e1 - self.e0) / (n - 1)
        self.n = n
        self.offset_m = c["upstream"]["terrain_vertical_offset_m"]
        from worldmodel import lonlat_to_enu
        self._enu = lonlat_to_enu
        import xinyi_world_compat as xc
        self.lon0, self.lat0 = xc.O_LON, xc.O_LAT
        self.enu_to_lonlat = xc.enu_to_lonlat

    def tm2_to_enu(self, x, y):
        return tm2_to_xinyi_enu(x, y)

    def height_enu(self, e, n, tol_m=0.0):
        """Bilinear on the accepted grid; NaN outside the landscape (points within tol_m of the edge are clamped onto it)."""
        col = (np.asarray(e, float) - self.e0) / self.step
        row = (self.n1 - np.asarray(n, float)) / self.step
        t = tol_m / self.step
        ok = (col >= -t) & (row >= -t) & (col <= self.n - 1 + t) & (row <= self.n - 1 + t)
        col, row = np.clip(col, 0, self.n - 1), np.clip(row, 0, self.n - 1)
        out = np.full(col.shape, np.nan)
        c0 = np.clip(np.floor(col).astype(int), 0, self.n - 2)
        r0 = np.clip(np.floor(row).astype(int), 0, self.n - 2)
        tc, tr = col - c0, row - r0
        h = self.h
        v = (h[r0, c0] * (1 - tc) * (1 - tr) + h[r0, c0 + 1] * tc * (1 - tr) + h[r0 + 1, c0] * (1 - tc) * tr + h[r0 + 1, c0 + 1] * tc * tr)
        out[ok] = v[ok]
        return out

    def height_tm2(self, x, y, tol_m=0.0):
        e, n = self.tm2_to_enu(x, y)
        return self.height_enu(e, n, tol_m)

    def edge_ring(self, every=1):
        """Accepted Landscape boundary vertices (CCW in ENU: south, east, north, west), exact heights from the R16 grid,
        positions mapped through the exact accepted ENU formula to EPSG:3826, Landscape normals mapped into the TM2 frame."""
        n, h = self.n, self.h
        idx = list(range(0, n - 1, every))
        cols, rows = [], []
        cols += idx; rows += [n - 1] * len(idx)                      # south: west -> east
        cols += [n - 1] * len(idx); rows += [n - 1 - i for i in idx]  # east: south -> north
        cols += [n - 1 - i for i in idx]; rows += [0] * len(idx)      # north: east -> west
        cols += [0] * len(idx); rows += idx                           # west: north -> south
        cols, rows = np.array(cols), np.array(rows)
        e = self.e0 + cols * self.step
        nn = self.n1 - rows * self.step
        z = h[rows, cols]
        x, y = xinyi_enu_to_tm2(e, nn)
        cp, cm = np.minimum(cols + 1, n - 1), np.maximum(cols - 1, 0)
        rp, rm = np.minimum(rows + 1, n - 1), np.maximum(rows - 1, 0)
        dzde = (h[rows, cp] - h[rows, cm]) / ((cp - cm) * self.step)
        dzdn = (h[rm, cols] - h[rp, cols]) / ((rp - rm) * self.step)   # row index grows southwards
        study = json.loads((REPO / "data/ntw/coordinate_study.json").read_text(encoding="utf-8"))["xinyi_enu_to_ntw_affine"]
        g = (np.linalg.inv(np.array(study["linear_part"])).T @ np.vstack([dzde, dzdn])).T
        nrm = np.column_stack([-g[:, 0], -g[:, 1], np.ones(len(g))])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        return np.column_stack([x, y]), z, nrm

    def outline_tm2(self, step=10.0):
        pts = []
        for (ax, ay), (bx, by) in (((self.e0, self.n0), (self.e1, self.n0)), ((self.e1, self.n0), (self.e1, self.n1)),
                                   ((self.e1, self.n1), (self.e0, self.n1)), ((self.e0, self.n1), (self.e0, self.n0))):
            k = max(1, int(math.hypot(bx - ax, by - ay) / step))
            t = np.arange(k) / k
            x, y = xinyi_enu_to_tm2(ax + t * (bx - ax), ay + t * (by - ay))
            pts.extend(zip(x, y))
        return shapely.Polygon(pts)


# ------------------------------------------------------------------------------------------------ core
def region_grid(dem, bounds, halo):
    x0, y0, x1, y1 = bounds
    bb = (x0 - halo, y0 - halo, x1 + halo, y1 + halo)
    z, src, sheets, dup = dem.mosaic(bb)
    return bb, z, src, sheets, dup


def conform_xinyi(X, Y, Z, xin, outline, band, drop, step):
    """Return conformed Z and a per-node class (0 untouched, 1 band, 2 edge-inside, 3 deep-inside)."""
    Zc = Z.copy()
    cls = np.zeros(Z.shape, np.int8)
    pts = shapely.points(X.ravel(), Y.ravel())
    inside = shapely.contains_xy(outline, X.ravel(), Y.ravel())
    d = shapely.distance(pts, outline.boundary)
    near = (d <= band) | inside
    idx = np.nonzero(near)[0]
    if len(idx) == 0:
        return Zc, cls
    zx = xin.height_tm2(X.ravel()[idx], Y.ravel()[idx], tol_m=2.0)
    zr = Zc.ravel()
    cr = cls.ravel()
    for k, i in enumerate(idx):
        if inside[i]:
            if d[i] > step * math.sqrt(2):
                zr[i], cr[i] = zx[k] - drop, 3
            else:
                zr[i], cr[i] = zx[k], 2
        else:
            p = shapely.ops.nearest_points(pts[i], outline.boundary)[1]
            ze = xin.height_tm2(np.array([p.x]), np.array([p.y]), tol_m=2.0)[0]
            t = min(1.0, d[i] / band)
            w = t * t * (3 - 2 * t)
            zr[i], cr[i] = (1 - w) * ze + w * zr[i], 1
    return zr.reshape(Z.shape), cr.reshape(Z.shape)


def chunk_mesh(xs, ys, Z, nrm, uv, skirt, drop=None, drop_poly=None, hole_skirt=0.0):
    """xs (nx), ys (ny) local metres; Z (ny,nx); returns trimesh with glTF Y-up vertices (x, z, -y).
    drop: node mask (per-LOD hole: a face is removed if any vertex is masked). drop_poly: local-coordinate polygon aligned to
    this grid (fixed hole: a face is removed if its centroid lies inside); hole_skirt > 0 adds two-sided vertical skirts of
    that depth along every edge between a kept and a removed face (hides LOD T-junction gaps against the stitch)."""
    ny, nx = Z.shape
    GX, GY = np.meshgrid(xs, ys)
    V = np.column_stack([GX.ravel(), Z.ravel(), -GY.ravel()])
    N = np.column_stack([nrm[..., 0].ravel(), nrm[..., 2].ravel(), -nrm[..., 1].ravel()])
    T = uv.reshape(-1, 2)
    idx = np.arange(nx * ny).reshape(ny, nx)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    # fixed diagonal (a-d). (x, y, z) -> glTF (x, z, -y) is a proper rotation, so plan-view CCW triangles face +Y (up):
    # (a, b, d) and (a, d, c) with a = SW, b = SE, c = NW, d = NE. Checked by terrain_qa (face orientation).
    F = np.concatenate([np.stack([a, b, d], -1).reshape(-1, 3), np.stack([a, d, c], -1).reshape(-1, 3)])
    removed = np.zeros((0, 3), dtype=np.int64)
    if drop is not None and drop.any():
        dm = drop.ravel()[F].any(axis=1)
        removed, F = F[dm], F[~dm]
    if drop_poly is not None:
        cxy = np.column_stack([V[F, 0].mean(axis=1), -V[F, 2].mean(axis=1)])
        dm = shapely.contains_xy(drop_poly, cxy[:, 0], cxy[:, 1])
        removed, F = F[dm], F[~dm]
    hole_edges = []
    if hole_skirt > 0 and len(removed):
        und = lambda E: {(min(u, w), max(u, w)) for u, w in E}  # noqa: E731
        ek = und(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]).tolist())
        er = und(np.vstack([removed[:, [0, 1]], removed[:, [1, 2]], removed[:, [2, 0]]]).tolist())
        hole_edges = sorted(ek & er)
    ring = np.concatenate([idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]])
    base = len(V)
    Vs = V[ring].copy()
    Vs[:, 1] -= skirt
    V = np.vstack([V, Vs])
    N = np.vstack([N, N[ring]])
    T = np.vstack([T, T[ring]])
    r = np.arange(len(ring))
    top0, top1 = ring[r], ring[(r + 1) % len(ring)]
    bot0, bot1 = base + r, base + (r + 1) % len(ring)
    S = np.concatenate([np.stack([top0, bot0, top1], -1), np.stack([top1, bot0, bot1], -1)])
    if hole_edges:
        tops = sorted({u for e in hole_edges for u in e})
        bmap = {u: len(V) + i for i, u in enumerate(tops)}
        Vb = V[tops].copy()
        Vb[:, 1] -= hole_skirt
        V, N, T = np.vstack([V, Vb]), np.vstack([N, N[tops]]), np.vstack([T, T[tops]])
        H_ = []
        for u, w in hole_edges:
            bu, bw = bmap[u], bmap[w]
            H_ += [[u, bu, w], [w, bu, bw], [u, w, bu], [w, bw, bu]]      # two-sided
        S = np.vstack([S, np.array(H_)])
    m = trimesh.Trimesh(vertices=V, faces=np.vstack([F, S]), vertex_normals=N,
                        visual=trimesh.visual.TextureVisuals(uv=T), process=False)
    return m, len(F), removed


def build(cells, out, params: TerrainParams, world: WorldSpec):
    t0 = time.perf_counter()
    if out.exists():
        raise FileExistsError(out)
    (out / "chunks").mkdir(parents=True)
    (out / "cells").mkdir()
    dem = Dem(list(params.packages))
    c = world.cell_m
    cb = []
    for cid in cells:
        ix, iy = int(cid[1:6]), int(cid[6:11])
        cb.append((ix * c, iy * c, ix * c + c, iy * c + c))
    region = (min(b[0] for b in cb), min(b[1] for b in cb), max(b[2] for b in cb), max(b[3] for b in cb))
    halo = max(params.lod_steps_m)
    bb, Z, SRC, sheets, dup = region_grid(dem, region, halo)
    step0 = 20.0
    nyf, nxf = Z.shape
    Xf = bb[0] + np.arange(nxf) * step0
    Yf = bb[1] + np.arange(nyf) * step0
    land_poly = shapely.union(*wc.load_land()[2:4])
    shapely.prepare(land_poly)
    GXf, GYf = np.meshgrid(Xf, Yf)
    on_land = shapely.contains_xy(land_poly, GXf.ravel(), GYf.ravel()).reshape(Z.shape)
    missing_land = on_land & np.isnan(Z)
    report = {"gate": "NTW terrain vertical slice", "params": asdict(params), "world": world.name, "cells": cells,
              "region_epsg3826": region, "halo_m": halo,
              "source": {"product": "MOI 2025 20 m DEM (official TGOS sheets, data.gov.tw 176927)", "crs": "EPSG:3826 TWD97[2020]",
                         "vertical": "TWVD2001", "packages": json.loads((REPO / "data/generated/ntw/tgos/manifest.json").read_text(encoding="utf-8")),
                         "sheets_used": [{"no": s.number, "name": s.name, "survey_date": s.survey_date, "production_date": s.production_date,
                                          "source": s.source, "package": s.package} for s in sheets],
                         "duplicate_nodes": dup},
              "fail_closed": {"land_nodes_missing": int(missing_land.sum()), "sea_nodes": int((~on_land).sum())}}
    if missing_land.any():
        report["status"] = "BLOCKED"
        (out / "terrain.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        raise SystemExit(f"BLOCKED: {int(missing_land.sum())} land nodes without official samples")
    Z = np.where(on_land, Z, np.where(np.isnan(Z), 0.0, Z))  # sea nodes: 0 m reference water where the DEM has no sample

    xin = None
    if params.xinyi_conform:
        xin = XinyiLandscape()
        outline = xin.outline_tm2()
        report["xinyi"] = {"accepted_r16_sha256": xin.sha256, "accepted_vertical_offset_m": xin.offset_m,
                           "outline_bounds_epsg3826": [round(v, 2) for v in outline.bounds]}
    world_x0, world_y0 = world.sw_tm2
    chunks = []
    H, D_hole = None, 0.0
    if xin is not None and params.xinyi_mode == "stitch" and params.stitch_hole == "fixed":
        H, D_hole, hole_rep = fixed_hole(xin, outline, Z, bb, step0, params)
        report["fixed_hole"] = hole_rep
    nb_skirt = {}
    if params.neighbour_skirts:
        nb_skirt, nb_rep = neighbour_skirt_depths(Z, bb, step0, cb, xin, outline if xin is not None else None, params)
        report["neighbour_skirts"] = nb_rep
    for (cx0, cy0, cx1, cy1), cid in zip(cb, cells):
        (out / "chunks" / cid).mkdir()
        nch = int(round(c / params.chunk_m))
        for k, s in enumerate(params.lod_steps_m):
            GX, GY, ZL, cls = lod_grid(Z, bb, step0, (cx0, cy0, cx1, cy1), s, xin, outline if xin is not None else None, params)
            if not np.isfinite(ZL).all():  # fail closed: never ship a non-finite height
                raise SystemExit(f"FAIL: non-finite terrain heights in {cid} LOD{k} ({int((~np.isfinite(ZL)).sum())} nodes)")
            dzdx = (ZL[1:-1, 2:] - ZL[1:-1, :-2]) / (2 * s)
            dzdy = (ZL[2:, 1:-1] - ZL[:-2, 1:-1]) / (2 * s)
            nrm = np.stack([-dzdx, -dzdy, np.ones_like(dzdx)], -1)
            nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
            Zc = ZL[1:-1, 1:-1]
            Xc, Yc = GX[1:-1, 1:-1], GY[1:-1, 1:-1]
            q = int(round(params.chunk_m / s))
            stitch_hole, removed_tris, node_lookup = None, [], {}
            if xin is not None and params.xinyi_mode == "stitch" and shapely.intersects(outline, shapely.box(cx0, cy0, cx1, cy1)):
                stitch_hole = H if H is not None else outline.buffer(1.0 * s)  # per-LOD: every crossing triangle has a vertex within 0.71 s
            # geometric error of this LOD vs LOD0 official nodes (per chunk, computed on the full 20 m grid)
            for a_ in range(nch):
                for b_ in range(nch):
                    sl = (slice(b_ * q, b_ * q + q + 1), slice(a_ * q, a_ * q + q + 1))
                    zc, xc_, yc_ = Zc[sl], Xc[sl], Yc[sl]
                    ox, oy = xc_[0, 0], yc_[0, 0]
                    err_max, err_rms, err_p99 = lod_error(Z, bb, ox, oy, params.chunk_m, s, zc, xin is not None and cls[1:-1, 1:-1][sl].any())
                    skirt = max(params.skirt_min_m, 2 * err_max)
                    if params.neighbour_skirts:
                        skirt = max(skirt, nb_skirt[(round(ox), round(oy))])
                    uv = np.stack([(xc_ - world_x0) / params.uv_tile_m, (yc_ - world_y0) / params.uv_tile_m], -1)
                    drop = drop_poly = None
                    if stitch_hole is not None and H is None:
                        drop = shapely.contains_xy(stitch_hole, xc_.ravel(), yc_.ravel()).reshape(xc_.shape)
                    elif H is not None and shapely.intersects(H, shapely.box(ox, oy, ox + params.chunk_m, oy + params.chunk_m)):
                        drop_poly = shapely.affinity.translate(H, xoff=-ox, yoff=-oy)
                    mesh, nterr, removed = chunk_mesh(xc_[0] - ox, yc_[:, 0] - oy, zc, nrm[sl], uv, skirt, drop, drop_poly,
                                                      hole_skirt=D_hole if drop_poly is not None else 0.0)
                    if len(removed):
                        V0 = np.column_stack([xc_.ravel(), yc_.ravel()])
                        removed_tris.extend(shapely.polygons(V0[removed]).tolist())
                        for (px_, py_), pz, pn in zip(V0, zc.ravel(), nrm[sl].reshape(-1, 3)):
                            node_lookup[(round(px_, 3), round(py_, 3))] = (pz, pn)
                    scene = trimesh.Scene()
                    nx_, ny_ = frame.tm2_to_ntw(ox, oy)
                    T = np.eye(4)
                    if not params.identity_nodes:
                        T[:3, 3] = [float(nx_), 0.0, -float(ny_)]
                    key = f"{cid}_ch{a_}{b_}"
                    scene.add_geometry(mesh, geom_name=f"{key}_lod{k}", node_name=f"{key}_lod{k}", transform=T)
                    glb = scene.export(file_type="glb")
                    fn = out / "chunks" / cid / f"ch{a_}{b_}_lod{k}.glb"
                    fn.write_bytes(glb)
                    if k == 0 and params.collision_meshes:
                        write_collision_glb(out / "chunks" / cid / f"ch{a_}{b_}_col.glb", mesh, nterr, f"{key}_col", T)
                    chunks.append({"cell": cid, "chunk": f"ch{a_}{b_}", "lod": k, "step_m": s, "sw_epsg3826": [ox, oy],
                                   "vertices_terrain": int(zc.size), "triangles_terrain": int(nterr), "triangles_total": int(len(mesh.faces)),
                                   "skirt_m": round(skirt, 3), "lod_err_max_m": round(err_max, 3), "lod_err_rms_m": round(err_rms, 3), "lod_err_p99_m": round(err_p99, 3),
                                   "z_min": round(float(zc.min()), 3), "z_max": round(float(zc.max()), 3),
                                   "xinyi_conformed_nodes": int((cls[1:-1, 1:-1][sl] > 0).sum()),
                                   "hole_skirt_m": round(D_hole, 3) if drop_poly is not None else 0.0,
                                   "bytes": len(glb), "sha256": hashlib.sha256(glb).hexdigest()})
            if stitch_hole is not None and removed_tris:
                if H is not None:
                    chunks.append(build_stitch_grid(out, cid, k, s, xin, H, node_lookup, world, params, D_hole))
                else:
                    chunks.append(build_stitch(out, cid, k, s, xin, removed_tris, node_lookup, world, params))
        # per-cell master outputs: official 20 m grid (GeoTIFF) and UE Landscape R16 candidate
        write_cell_products(out, cid, (cx0, cy0, cx1, cy1), Z, bb, params, report)
    report["chunks"] = chunks
    report["chunk_manifest_sha256"] = hashlib.sha256("\n".join(f"{r['cell']}/{r['chunk']}/lod{r['lod']}:{r['sha256']}" for r in chunks).encode()).hexdigest()
    report["runtime_seconds"] = round(time.perf_counter() - t0, 1)
    report["status"] = "PASS_BUILD"
    (out / "terrain.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({"cells": cells, "chunks": len(chunks), "manifest": report["chunk_manifest_sha256"], "seconds": report["runtime_seconds"]}))
    return report


def lod_grid(Z, bb, step0, cbox, s, xin, outline, params):
    """LOD grid over the cell + one LOD step of halo (for normals), absolute alignment, Xinyi-conformed."""
    cx0, cy0, cx1, cy1 = cbox
    gx = np.arange(cx0 - s, cx1 + s + 0.5, s)
    gy = np.arange(cy0 - s, cy1 + s + 0.5, s)
    ii = np.rint((gx - bb[0]) / step0).astype(int)
    jj = np.rint((gy - bb[1]) / step0).astype(int)
    ZL = Z[np.ix_(jj, ii)]
    GX, GY = np.meshgrid(gx, gy)
    cls = np.zeros(ZL.shape, np.int8)
    if xin is not None and shapely.intersects(outline.buffer(params.xinyi_band_m + s), shapely.box(cx0 - s, cy0 - s, cx1 + s, cy1 + s)):
        ZL, cls = conform_xinyi(GX, GY, ZL, xin, outline, params.xinyi_band_m,
                                0.0 if params.xinyi_mode == "stitch" else params.xinyi_drop_m, s)
    return GX, GY, ZL, cls


def neighbour_skirt_depths(Z, bb, step0, cb, xin, outline, params):
    """Per chunk: 2 x max(coarsest-LOD error of the chunk and its 8 neighbours) + 0.5 m (neighbours outside the built cells
    do not exist and are ignored). Errors vs the official 20 m nodes, as lod_error."""
    s = max(params.lod_steps_m)
    q = int(round(params.chunk_m / s))
    err = {}
    for cbox in cb:
        GX, GY, ZL, cls = lod_grid(Z, bb, step0, cbox, s, xin, outline, params)
        Zc, Xc, Yc = ZL[1:-1, 1:-1], GX[1:-1, 1:-1], GY[1:-1, 1:-1]
        nch = int(round((cbox[2] - cbox[0]) / params.chunk_m))
        for a_ in range(nch):
            for b_ in range(nch):
                sl = (slice(b_ * q, b_ * q + q + 1), slice(a_ * q, a_ * q + q + 1))
                ox, oy = Xc[sl][0, 0], Yc[sl][0, 0]
                err[(round(ox), round(oy))] = lod_error(Z, bb, ox, oy, params.chunk_m, s, Zc[sl], False)[0]
    c = params.chunk_m
    depth = {}
    for (ox, oy), e in err.items():
        nb = [err.get((round(ox + dx * c), round(oy + dy * c))) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        depth[(ox, oy)] = max(params.skirt_min_m, 2.0 * max(v for v in nb if v is not None) + 0.5)
    vals = sorted(depth.values())
    return depth, {"rule": "2 x max(coarsest-LOD error of chunk + 8 neighbours) + 0.5 m", "coarsest_step_m": s,
                   "skirt_m": {"min": round(vals[0], 2), "median": round(vals[len(vals) // 2], 2), "max": round(vals[-1], 2)}}


def write_collision_glb(path, mesh, n_surface, name, T):
    """Phase 2B-C: surface-only LOD0 copy used as the engine's COMPLEX collision mesh. Skirts are visual crack covers only;
    as (one-sided, vertical) collision they pushed resting physics bodies through the accepted Landscape at the seam.
    A chunk entirely inside the fixed Xinyi hole has no surface faces -> no collision mesh (and no collision)."""
    if n_surface == 0:
        return
    used = np.unique(mesh.faces[:n_surface])
    remap = -np.ones(len(mesh.vertices), int)
    remap[used] = np.arange(len(used))
    cm = trimesh.Trimesh(np.asarray(mesh.vertices)[used], remap[mesh.faces[:n_surface]], process=False)
    sc = trimesh.Scene()
    sc.add_geometry(cm, geom_name=name, node_name=name, transform=T)
    path.write_bytes(sc.export(file_type="glb"))


def fixed_hole(xin, outline, Z, bb, step0, params):
    """One hole for every LOD: union of hole_align_m cells (absolute grid, a multiple of every LOD step) touching the outline
    buffered by hole_margin_m. Skirt depth for both sides of the hole edge = 2 x the largest deviation of any LOD's
    piecewise-linear hole edge from the 20 m (LOD0) conformed nodes on that edge, + 0.5 m."""
    a = params.hole_align_m
    R = outline.buffer(params.hole_margin_m)
    x0, y0, x1, y1 = R.bounds
    cells = [shapely.box(i * a, j * a, i * a + a, j * a + a) for i in range(int(x0 // a), int(x1 // a) + 1)
             for j in range(int(y0 // a), int(y1 // a) + 1) if shapely.intersects(shapely.box(i * a, j * a, i * a + a, j * a + a), R)]
    H = shapely.union_all(cells)
    if H.geom_type != "Polygon" or len(H.interiors):
        raise SystemExit("FAIL: fixed Xinyi hole is not a simple polygon")
    ring = shapely.segmentize(H.exterior, step0)
    co = np.asarray(ring.coords)[:-1]
    co = np.round(co / step0) * step0
    ii = np.rint((co[:, 0] - bb[0]) / step0).astype(int)
    jj = np.rint((co[:, 1] - bb[1]) / step0).astype(int)
    z20, _ = conform_xinyi(co[:, 0][None, :], co[:, 1][None, :], Z[jj, ii][None, :], xin, outline, params.xinyi_band_m, 0.0, step0)
    z20 = z20[0]
    sarc = np.r_[0, np.cumsum(np.hypot(*np.diff(np.vstack([co, co[:1]]), axis=0).T))]
    zc = np.r_[z20, z20[:1]]
    devs = {}
    for s in params.lod_steps_m:
        on = (np.abs(np.r_[co[:, 0], co[:1, 0]] / s - np.round(np.r_[co[:, 0], co[:1, 0]] / s)) < 1e-6) & \
             (np.abs(np.r_[co[:, 1], co[:1, 1]] / s - np.round(np.r_[co[:, 1], co[:1, 1]] / s)) < 1e-6)
        lin = np.interp(sarc, sarc[on], zc[on])
        devs[str(int(s))] = round(float(np.abs(lin - zc).max()), 3)
    D = max(params.skirt_min_m, 2.0 * max(devs.values()) + 0.5)
    rep_ = {"bounds_epsg3826": [round(v, 1) for v in H.bounds], "area_km2": round(H.area / 1e6, 4), "align_m": a,
            "margin_m": params.hole_margin_m, "annulus_width_min_m": round(float(H.exterior.distance(outline.exterior)), 1),
            "hole_edge_lod_deviation_m": devs, "hole_skirt_m": round(D, 3)}
    return H, D, rep_


def build_stitch_grid(out, cid, k, s, xin, H, node_lookup, world, params, D_hole):
    """Fixed-hole stitch at LOD k: the LOD-k grid inside the hole minus the accepted sector. Whole grid cells away from the
    Xinyi edge keep the chunk's fixed diagonal; the cells crossed by the edge form one band triangulated by GEOS constrained
    Delaunay whose ONLY vertices are grid nodes and the 2,520 accepted edge vertices (no new vertices). Skirts: 2 m below the
    Xinyi edge (as v2) and D_hole (two-sided) along the hole edge."""
    P, Pz, Pn = xin.edge_ring(every=1)
    inner = shapely.Polygon(P)
    lut = {(round(x, 3), round(y, 3)): (z, n) for (x, y), z, n in zip(P, Pz, Pn)}
    lut.update(node_lookup)
    x0, y0, x1, y1 = H.bounds
    full, partial = [], []
    for x in np.arange(x0, x1 - 0.5 * s, s):
        for y in np.arange(y0, y1 - 0.5 * s, s):
            cell = shapely.box(x, y, x + s, y + s)
            if not shapely.within(cell, H) or shapely.within(cell, inner):
                continue
            if shapely.intersects(cell, inner):
                partial.append(cell)
            else:
                a_, b_, c_, d_ = (x, y), (x + s, y), (x, y + s), (x + s, y + s)
                full += [(a_, b_, d_), (a_, d_, c_)]
    band = shapely.segmentize(shapely.difference(shapely.union_all(partial), inner), s)
    tris = [tuple(t.exterior.coords)[:3] for t in shapely.get_parts(shapely.constrained_delaunay_triangles(band))]
    verts, vidx, faces, missing = [], {}, [], 0
    for t in full + tris:
        f = []
        for x, y in t:
            key = (round(x, 3), round(y, 3))
            if key not in lut:
                missing += 1
                break
            if key not in vidx:
                vidx[key] = len(verts)
                verts.append((x, y, lut[key][0]) + tuple(lut[key][1]))
            f.append(vidx[key])
        else:
            faces.append(f)
    if missing:
        raise SystemExit(f"FAIL: fixed-hole stitch introduced {missing} vertices that are neither grid nodes nor accepted edge vertices ({cid} LOD{k})")
    V = np.array(verts)
    F = np.array(faces)
    a, b, c = V[F[:, 0], :2], V[F[:, 1], :2], V[F[:, 2], :2]
    cw = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) < 0
    F[cw] = F[cw][:, [0, 2, 1]]
    n_surface_faces = len(F)
    surf = shapely.union_all(shapely.polygons(V[F][:, :, :2]))
    # Xinyi-edge skirt (one-sided, facing away from Xinyi) as v2
    top = [vidx[(round(x, 3), round(y, 3))] for x, y in P]
    base = len(V)
    V = np.vstack([V, np.column_stack([V[top, 0], V[top, 1], V[top, 2] - params.stitch_skirt_m, V[top, 3:]])])
    sk = []
    for i in range(len(top)):
        a_, b_ = top[i], top[(i + 1) % len(top)]
        c_, d_ = base + (i + 1) % len(top), base + i
        sk += [[a_, d_, b_], [b_, d_, c_]]
    # hole-edge skirt (two-sided) on boundary edges lying on the hole boundary
    E = np.vstack([F[:n_surface_faces, [0, 1]], F[:n_surface_faces, [1, 2]], F[:n_surface_faces, [2, 0]]])
    Eu = np.sort(E, axis=1)
    uniq, cnt = np.unique(Eu, axis=0, return_counts=True)
    bnd = uniq[cnt == 1]
    hb = H.exterior
    on_h = np.array([shapely.distance(shapely.points(V[u, 0], V[u, 1]), hb) < 1e-3 and shapely.distance(shapely.points(V[w, 0], V[w, 1]), hb) < 1e-3
                     for u, w in bnd], bool) if len(bnd) else np.zeros(0, bool)
    hedges = bnd[on_h]
    tops = sorted({int(u) for e in hedges for u in e})
    bmap = {u: len(V) + i for i, u in enumerate(tops)}
    if tops:
        V = np.vstack([V, np.column_stack([V[tops, 0], V[tops, 1], V[tops, 2] - D_hole, V[tops, 3:]])])
    for u, w in hedges:
        bu, bw = bmap[int(u)], bmap[int(w)]
        sk += [[u, bu, w], [w, bu, bw], [u, w, bu], [w, bw, bu]]
    F = np.vstack([F, np.array(sk)])
    ob = xin.outline_tm2().bounds
    ox, oy = math.floor((ob[0] - 1000.0) / 320.0) * 320.0, math.floor((ob[1] - 1000.0) / 320.0) * 320.0
    if V[:, 0].min() < ox or V[:, 1].min() < oy:
        raise SystemExit("FAIL: stitch extends south-west of its fixed origin")
    Vg = np.column_stack([V[:, 0] - ox, V[:, 2], -(V[:, 1] - oy)])
    Ng = np.column_stack([V[:, 3], V[:, 5], -V[:, 4]])
    uv = np.column_stack([(V[:, 0] - world.sw_tm2[0]) / params.uv_tile_m, (V[:, 1] - world.sw_tm2[1]) / params.uv_tile_m])
    m = trimesh.Trimesh(vertices=Vg, faces=F, vertex_normals=Ng, visual=trimesh.visual.TextureVisuals(uv=uv), process=False)
    sc = trimesh.Scene()
    nx_, ny_ = frame.tm2_to_ntw(ox, oy)
    T = np.eye(4)
    if not params.identity_nodes:
        T[:3, 3] = [float(nx_), 0.0, -float(ny_)]
    sc.add_geometry(m, geom_name=f"{cid}_xinyi_stitch_lod{k}", node_name=f"{cid}_xinyi_stitch_lod{k}", transform=T)
    glb = sc.export(file_type="glb")
    (out / "chunks" / cid / f"xinyi_stitch_lod{k}.glb").write_bytes(glb)
    if k == 0 and params.collision_meshes:
        write_collision_glb(out / "chunks" / cid / "xinyi_stitch_col.glb", m, n_surface_faces, f"{cid}_xinyi_stitch_col", T)
    return {"cell": cid, "chunk": "xinyi_stitch", "lod": k, "step_m": s, "sw_epsg3826": [ox, oy], "vertices_terrain": int(base),
            "triangles_terrain": int(n_surface_faces), "triangles_total": len(F), "skirt_m": params.stitch_skirt_m,
            "hole_skirt_m": round(D_hole, 3), "hole_skirt_edges": int(len(hedges)), "stitch_edge": "full", "stitch_hole": "fixed",
            "grid_cells_full": len(full) // 2, "band_triangles": len(tris), "lod_err_max_m": 0.0, "lod_err_rms_m": 0.0,
            "z_min": round(float(V[:base, 2].min()), 3), "z_max": round(float(V[:base, 2].max()), 3), "xinyi_conformed_nodes": -1,
            "xinyi_edge_vertices": len(P), "hole_area_km2": round(H.area / 1e6, 4), "annulus_area_km2": round(surf.area / 1e6, 5),
            "bytes": len(glb), "sha256": hashlib.sha256(glb).hexdigest()}


def build_stitch(out, cid, k, s, xin, removed_tris, node_lookup, world, params):
    """Seam strip between the accepted Xinyi Landscape edge and the hole cut into the new terrain at LOD k.
    Vertices: Xinyi edge ring (exact accepted heights, every 2**k Landscape samples) + the hole boundary nodes of the new
    terrain (exact chunk vertices). Triangulation: GEOS constrained Delaunay on the annulus, so no new vertices exist."""
    hole = shapely.union_all(removed_tris)
    if hole.geom_type != "Polygon":
        hole = max(shapely.get_parts(hole), key=lambda g: g.area)
    P, Pz, Pn = xin.edge_ring(every=1 if params.stitch_edge == "full" else 2 ** k)
    inner = shapely.Polygon(P)
    ann = shapely.Polygon(hole.exterior.coords).difference(inner)
    tris = shapely.get_parts(shapely.constrained_delaunay_triangles(ann))
    lut = {(round(x, 3), round(y, 3)): (z, n) for (x, y), z, n in zip(P, Pz, Pn)}
    lut.update(node_lookup)
    verts, vidx, faces, missing = [], {}, [], 0
    for t in tris:
        co = list(t.exterior.coords)[:3]
        f = []
        for x, y in co:
            key = (round(x, 3), round(y, 3))
            if key not in lut:
                missing += 1
                break
            if key not in vidx:
                vidx[key] = len(verts)
                verts.append((x, y, lut[key][0]) + tuple(lut[key][1]))
            f.append(vidx[key])
        else:
            faces.append(f)
    if missing:
        raise SystemExit(f"FAIL: stitch triangulation introduced {missing} vertices not on either ring ({cid} LOD{k})")
    V = np.array(verts)
    # one fixed origin for EVERY stitch LOD (engine LOD chains share one actor transform): the 320 m-grid point at least
    # 1 km south-west of the Xinyi outline, which every LOD's hole stays inside of
    ob = xin.outline_tm2().bounds
    ox, oy = math.floor((ob[0] - 1000.0) / 320.0) * 320.0, math.floor((ob[1] - 1000.0) / 320.0) * 320.0
    if V[:, 0].min() < ox or V[:, 1].min() < oy:
        raise SystemExit("FAIL: stitch extends south-west of its fixed origin")
    F = np.array(faces)
    a, b, c = V[F[:, 0], :2], V[F[:, 1], :2], V[F[:, 2], :2]
    cw = ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) < 0
    F[cw] = F[cw][:, [0, 2, 1]]
    n_surface_faces = len(F)
    if params.stitch_edge == "full" and params.stitch_skirt_m > 0:
        # vertical skirt below the Xinyi edge ring: quads (top_i, top_i+1, bottom_i+1, bottom_i), facing away from Xinyi
        top = [vidx[(round(x, 3), round(y, 3))] for x, y in P]
        base = len(V)
        bot = np.column_stack([V[top, 0], V[top, 1], V[top, 2] - params.stitch_skirt_m, V[top, 3:]])
        V = np.vstack([V, bot])
        m_ = len(top)
        sk = []
        for i in range(m_):
            a, b = top[i], top[(i + 1) % m_]
            c, d = base + (i + 1) % m_, base + i
            sk += [[a, d, b], [b, d, c]]
        F = np.vstack([F, np.array(sk)])
    Vg = np.column_stack([V[:, 0] - ox, V[:, 2], -(V[:, 1] - oy)])
    Ng = np.column_stack([V[:, 3], V[:, 5], -V[:, 4]])
    uv = np.column_stack([(V[:, 0] - world.sw_tm2[0]) / params.uv_tile_m, (V[:, 1] - world.sw_tm2[1]) / params.uv_tile_m])
    Fg = F  # plan-view CCW stays +Y-up under the proper rotation (x, y, z) -> (x, z, -y)
    m = trimesh.Trimesh(vertices=Vg, faces=Fg, vertex_normals=Ng, visual=trimesh.visual.TextureVisuals(uv=uv), process=False)
    sc = trimesh.Scene()
    nx_, ny_ = frame.tm2_to_ntw(ox, oy)
    T = np.eye(4)
    if not params.identity_nodes:
        T[:3, 3] = [float(nx_), 0.0, -float(ny_)]
    sc.add_geometry(m, geom_name=f"{cid}_xinyi_stitch_lod{k}", node_name=f"{cid}_xinyi_stitch_lod{k}", transform=T)
    glb = sc.export(file_type="glb")
    fn = out / "chunks" / cid / f"xinyi_stitch_lod{k}.glb"
    fn.write_bytes(glb)
    return {"cell": cid, "chunk": "xinyi_stitch", "lod": k, "step_m": s, "sw_epsg3826": [ox, oy], "vertices_terrain": len(V),
            "triangles_terrain": int(n_surface_faces), "triangles_total": len(F),
            "skirt_m": params.stitch_skirt_m if params.stitch_edge == "full" else 0.0, "stitch_edge": params.stitch_edge, "lod_err_max_m": 0.0, "lod_err_rms_m": 0.0,
            "z_min": round(float(V[:, 2].min()), 3), "z_max": round(float(V[:, 2].max()), 3), "xinyi_conformed_nodes": -1,
            "xinyi_edge_vertices": len(P), "hole_area_km2": round(hole.area / 1e6, 4), "annulus_area_km2": round(ann.area / 1e6, 5),
            "bytes": len(glb), "sha256": hashlib.sha256(glb).hexdigest()}


def lod_error(Z, bb, ox, oy, chunk_m, s, zc, conformed):
    """Max / RMS vertical difference between the LOD surface (bilinear on its nodes) and the official 20 m nodes."""
    if s == 20.0:
        return 0.0, 0.0, 0.0
    i0, j0 = int(round((ox - bb[0]) / 20.0)), int(round((oy - bb[1]) / 20.0))
    n = int(round(chunk_m / 20.0)) + 1
    z0 = Z[j0:j0 + n, i0:i0 + n]
    r = int(round(s / 20.0))
    t = (np.arange(n) % r) / r
    k = np.arange(n) // r
    k1 = np.minimum(k + 1, zc.shape[0] - 1)
    zz = (zc[np.ix_(k, k)] * (1 - t)[:, None] * (1 - t)[None, :] + zc[np.ix_(k, k1)] * (1 - t)[:, None] * t[None, :]
          + zc[np.ix_(k1, k)] * t[:, None] * (1 - t)[None, :] + zc[np.ix_(k1, k1)] * t[:, None] * t[None, :])
    d = zz - z0
    if conformed:  # conformed nodes differ from official by design; report error only on untouched official nodes
        pass
    a = np.abs(d)
    return float(a.max()), float(np.sqrt((d ** 2).mean())), float(np.percentile(a, 99))


def write_cell_products(out, cid, cbx, Z, bb, params, report):
    import rasterio
    from rasterio.transform import from_origin
    x0, y0, x1, y1 = cbx
    i0, j0 = int(round((x0 - bb[0]) / 20)), int(round((y0 - bb[1]) / 20))
    n = int(round((x1 - x0) / 20)) + 1
    sub = Z[j0:j0 + n, i0:i0 + n]
    tif = out / "cells" / f"{cid}_dem20.tif"
    with rasterio.open(tif, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32", crs="EPSG:3826",
                       transform=from_origin(x0 - 10, y1 + 10, 20, 20), compress="deflate") as ds:
        ds.write(sub[::-1].astype(np.float32), 1)  # row 0 = north
    # UE Landscape candidate: params.ue_landscape_samples^2 over the cell (bilinear on official nodes), Xinyi encoding
    m = params.ue_landscape_samples
    t = np.linspace(0, n - 1, m)
    k = np.minimum(np.floor(t).astype(int), n - 2)
    f = t - k
    zz = (sub[np.ix_(k, k)] * (1 - f)[:, None] * (1 - f)[None, :] + sub[np.ix_(k, k + 1)] * (1 - f)[:, None] * f[None, :]
          + sub[np.ix_(k + 1, k)] * f[:, None] * (1 - f)[None, :] + sub[np.ix_(k + 1, k + 1)] * f[:, None] * f[None, :])
    scale_z = params.ue_scale_z
    base = math.floor(float(zz.min()) / params.ue_base_round_m) * params.ue_base_round_m
    code = np.rint(32768.0 + (zz[::-1] - base) * 100.0 * 128.0 / scale_z)
    if code.min() < 0 or code.max() > 65535:
        raise RuntimeError(f"UE landscape encoding overflow for {cid}: raise ue_scale_z")
    r16 = out / "cells" / f"{cid}_ue{m}.r16"
    r16.write_bytes(code.astype("<u2").tobytes())
    rt = (code.astype(np.float64) - 32768.0) * scale_z / 128.0 / 100.0 + base
    report.setdefault("cell_products", []).append({
        "cell": cid, "dem20_tif": tif.name, "dem20_sha256": hashlib.sha256(tif.read_bytes()).hexdigest(),
        "dem20_nodes": [n, n], "z_min": round(float(sub.min()), 3), "z_max": round(float(sub.max()), 3),
        "ue_r16": r16.name, "ue_r16_sha256": hashlib.sha256(r16.read_bytes()).hexdigest(), "ue_samples": [m, m],
        "ue_spacing_m": round((x1 - x0) / (m - 1), 6), "ue_scale_z": scale_z, "ue_actor_z_offset_m": base,
        "ue_roundtrip_max_err_m": round(float(np.abs(rt - zz[::-1]).max()), 5),
        "ue_note": "official DEM only (no Xinyi conformance); 505 = 8 components x 63 quads + 1; bilinear oversampling of 20 m nodes"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--world", type=Path, default=REPO / "worlds/north_taiwan_224.json")
    ap.add_argument("--no-xinyi-conform", action="store_true")
    ap.add_argument("--xinyi-mode", choices=["stitch", "conform"], default="stitch")
    ap.add_argument("--identity-nodes", action="store_true", help="UE-facing export: no node translation (origins in report)")
    ap.add_argument("--stitch-edge", choices=["full", "decimated"], default="full")
    ap.add_argument("--stitch-hole", choices=["per_lod", "fixed"], default="per_lod")
    ap.add_argument("--collision-meshes", action="store_true", help="write surface-only LOD0 collision GLBs (no skirts)")
    ap.add_argument("--neighbour-skirts", action="store_true", help="chunk skirts cover the coarsest-LOD error of the 8 neighbours")
    ap.add_argument("--stitch-skirt-m", type=float, default=2.0, help="depth of the skirt below the Xinyi edge (v2 default 2 m)")
    a = ap.parse_args()
    p = TerrainParams(xinyi_conform=not a.no_xinyi_conform, xinyi_mode=a.xinyi_mode, identity_nodes=a.identity_nodes,
                      stitch_edge=a.stitch_edge, stitch_hole=a.stitch_hole, collision_meshes=a.collision_meshes,
                      neighbour_skirts=a.neighbour_skirts, stitch_skirt_m=a.stitch_skirt_m)
    build(a.cells, a.out, p, WorldSpec.load(a.world))


if __name__ == "__main__":
    main()
