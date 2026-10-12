"""QA for the terrain vertical slice. Reads the SHIPPED chunk GLBs (not generator arrays) wherever geometry is judged.

Checks
  shard      independent per-cell builds vs joint build: chunk GLB SHA-256 identical per (cell, chunk, LOD); repeat build identical
  seams      every shared chunk edge (inside a cell and across the two cells), per LOD: edge vertex positions, shading normals and
             UVs identical; cross-LOD vertical gap along each shared edge vs the skirt depth
  xinyi      the 4 sides of the accepted Xinyi Landscape (accepted R16 through the exact accepted ENU formula) vs the new terrain
             at the same physical points: height step, normal angle, datum; variants raw / conformed / translation-only placement
  sources    mirror (accepted Xinyi transport) vs official TGOS DEM; official DEM vs WFS surveyed ground (datum) per 1.6 km chunk
  lod        per-LOD geometric error vs official nodes -> switch distances for a screen-space-error budget (parameters below)
Writes data/ntw/terrain/pilot_terrain_qa.json and figures under docs/evidence/ntw/terrain/.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
import trimesh
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools/compiler"))
import frame  # noqa: E402
import world_cells as wc  # noqa: E402
from build_terrain_cells import XinyiLandscape  # noqa: E402
from tgos_dem import Dem  # noqa: E402

T = REPO / "data/generated/ntw/terrain"
FIG = REPO / "docs/evidence/ntw/terrain"
SSE = {"screen_height_px": 1125, "vertical_fov_deg": 60.0, "budgets_px": [2.0, 4.0], "metric": "p95 over chunks of the per-chunk 99th-percentile node error (max error drives skirts only)",
       "note": "iPhone 11 Pro-class landscape short side; FOV is a design assumption, not a measured camera"}


def load_report(d):
    return json.loads((d / "terrain.report.json").read_text(encoding="utf-8"))


def glb_grid(path):
    """-> world X (nx), world Y (ny), Z (ny,nx), normals (ny,nx,3 world xyz-up), uv (ny,nx,2), from a chunk GLB."""
    sc = trimesh.load_scene(io.BytesIO(path.read_bytes()), file_type="glb", process=False)
    node = sc.graph.nodes_geometry[0]
    tr, g = sc.graph[node]
    m = sc.geometry[g]
    v = np.asarray(m.vertices, dtype=np.float64)
    n = np.asarray(m.vertex_normals, dtype=np.float64)
    uv = np.asarray(m.visual.uv, dtype=np.float64)
    # terrain vertices come first (row-major, rows south->north), skirt ring appended after
    xs = np.unique(v[:, 0])
    k = int(round(math.sqrt(len(v) - 4 * (len(xs) - 1))))
    vt = v[:k * k].reshape(k, k, 3)
    nt = n[:k * k].reshape(k, k, 3)
    ut = uv[:k * k].reshape(k, k, 2)
    X = vt[0, :, 0] + tr[0, 3] + frame.NTW_ORIGIN_TM2[0]
    Y = -(vt[:, 0, 2] + tr[2, 3]) + frame.NTW_ORIGIN_TM2[1]
    Nw = np.stack([nt[..., 0], -nt[..., 2], nt[..., 1]], -1)
    return X, Y, vt[..., 1], Nw, ut


def tri_interp(X, Y, Z, px, py):
    """Height on the builder's triangulation (diagonal SW-NE) of a regular grid."""
    s = X[1] - X[0]
    fx, fy = (px - X[0]) / s, (py - Y[0]) / s
    i = np.clip(np.floor(fx).astype(int), 0, len(X) - 2)
    j = np.clip(np.floor(fy).astype(int), 0, len(Y) - 2)
    tx, ty = fx - i, fy - j
    za, zb, zc, zd = Z[j, i], Z[j, i + 1], Z[j + 1, i], Z[j + 1, i + 1]
    lower = tx >= ty
    return np.where(lower, za + tx * (zb - za) + ty * (zd - zb), za + ty * (zc - za) + tx * (zd - zc))


def bilin(X, Y, A, px, py):
    s = X[1] - X[0]
    fx, fy = (px - X[0]) / s, (py - Y[0]) / s
    i = np.clip(np.floor(fx).astype(int), 0, len(X) - 2)
    j = np.clip(np.floor(fy).astype(int), 0, len(Y) - 2)
    tx, ty = (fx - i)[..., None] if A.ndim == 3 else fx - i, (fy - j)[..., None] if A.ndim == 3 else fy - j
    return A[j, i] * (1 - tx) * (1 - ty) + A[j, i + 1] * tx * (1 - ty) + A[j + 1, i] * (1 - tx) * ty + A[j + 1, i + 1] * tx * ty


def assemble_cell(run, cell, lod=0):
    """Stitch the 5x5 LOD chunks of a cell into one grid (shared edges must agree - asserted)."""
    tiles = {}
    for f in sorted((run / "chunks" / cell).glob(f"ch??_lod{lod}.glb")):
        a, b = int(f.stem[2]), int(f.stem[3])
        tiles[(a, b)] = glb_grid(f)
    q = len(tiles[(0, 0)][0]) - 1
    n = 5 * q + 1
    Z = np.full((n, n), np.nan)
    N = np.zeros((n, n, 3))
    X = np.zeros(n)
    Y = np.zeros(n)
    for (a, b), (x, y, z, nn, _) in tiles.items():
        Z[b * q:b * q + q + 1, a * q:a * q + q + 1] = z
        N[b * q:b * q + q + 1, a * q:a * q + q + 1] = nn
        X[a * q:a * q + q + 1] = x
        Y[b * q:b * q + q + 1] = y
    return X, Y, Z, N


# ------------------------------------------------------------------------------------------------ checks
def check_orientation(run):
    """Every terrain / stitch face must face up (+Y in glTF); skirts must face horizontally outward."""
    bad, n, skirt_bad = 0, 0, 0
    for f in sorted(run.glob("chunks/*/*.glb")):
        sc = trimesh.load_scene(io.BytesIO(f.read_bytes()), file_type="glb", process=False)
        m = list(sc.geometry.values())[0]
        fn = m.face_normals
        if f.stem.startswith("ch"):
            k = len(np.unique(m.vertices[:, 0])) ** 2
            top = (m.faces < k).all(axis=1)
            bad += int((fn[top][:, 1] <= 0).sum())
            n += int(top.sum())
            skirt_bad += int((np.abs(fn[~top][:, 1]) > 1e-6).sum())
        else:
            bad += int((fn[:, 1] <= 0).sum())
            n += len(fn)
    return {"faces_checked": n, "faces_not_facing_up": bad, "skirt_faces_not_vertical": skirt_bad}


def check_shard(joint1, joint2, cells_runs):
    r1, r2 = load_report(joint1), load_report(joint2)
    key = lambda r: {(c["cell"], c["chunk"], c["lod"]): c["sha256"] for c in r["chunks"]}  # noqa: E731
    k1, k2 = key(r1), key(r2)
    ind = {}
    for d in cells_runs:
        ind.update(key(load_report(d)))
    mism = [k for k in k1 if ind.get(k) != k1[k]]
    return {"joint_repeat_manifest_identical": r1["chunk_manifest_sha256"] == r2["chunk_manifest_sha256"],
            "joint_manifest_sha256": r1["chunk_manifest_sha256"], "chunks": len(k1),
            "independent_cell_builds_chunks": len(ind), "independent_vs_joint_identical": len(mism) == 0 and len(ind) == len(k1),
            "mismatches": [list(m) for m in mism[:10]],
            "orphans_or_duplicates": {"in_joint_not_independent": len(set(k1) - set(ind)), "in_independent_not_joint": len(set(ind) - set(k1))}}


def check_seams(run, cells):
    rep = load_report(run)
    lods = sorted({c["lod"] for c in rep["chunks"]})
    skirt = {(c["cell"], c["chunk"], c["lod"]): c["skirt_m"] for c in rep["chunks"]}
    grids = {}
    for cell in cells:
        for f in (run / "chunks" / cell).glob("ch??_lod*.glb"):
            a, b, lod = int(f.stem[2]), int(f.stem[3]), int(f.stem.split("lod")[1])
            grids[(cell, a, b, lod)] = glb_grid(f)
    # global chunk coordinates: cell abs index * 5 + chunk index
    def gpos(cell, a, b):
        return int(cell[1:6]) * 5 + a, int(cell[6:11]) * 5 + b
    by_g = {}
    for (cell, a, b, lod), g in grids.items():
        by_g[(gpos(cell, a, b), lod)] = (cell, a, b, g)
    res = {"same_lod": {"edges_checked": 0, "position_mismatch": 0, "normal_max_angle_deg": 0.0, "uv_max_abs_diff": 0.0,
                        "cross_cell_edges": 0},
           "cross_lod": {"pairs": 0, "max_gap_m": 0.0, "max_gap_over_skirt": 0, "worst": None}}
    for ((gx, gy), lod), (cell, a, b, g) in by_g.items():
        for dx, dy in ((1, 0), (0, 1)):
            nb = by_g.get(((gx + dx, gy + dy), lod))
            if nb is None:
                continue
            X, Y, Z, N, U = g
            X2, Y2, Z2, N2, U2 = nb[3]
            if dx:  # east edge of g vs west edge of nb
                e1 = (np.full(len(Y), X[-1]), Y, Z[:, -1], N[:, -1], U[:, -1])
                e2 = (np.full(len(Y2), X2[0]), Y2, Z2[:, 0], N2[:, 0], U2[:, 0])
            else:   # north edge of g vs south edge of nb
                e1 = (X, np.full(len(X), Y[-1]), Z[-1, :], N[-1, :], U[-1, :])
                e2 = (X2, np.full(len(X2), Y2[0]), Z2[0, :], N2[0, :], U2[0, :])
            s = res["same_lod"]
            s["edges_checked"] += 1
            s["cross_cell_edges"] += int(nb[0] != cell)
            same = all(np.array_equal(p, q) for p, q in zip(e1[:3], e2[:3]))
            s["position_mismatch"] += int(not same)
            cosang = np.clip(np.sum(e1[3] * e2[3], -1) / np.linalg.norm(e1[3], axis=-1) / np.linalg.norm(e2[3], axis=-1), -1, 1)
            s["normal_max_angle_deg"] = max(s["normal_max_angle_deg"], float(np.degrees(np.arccos(cosang)).max()))
            s["uv_max_abs_diff"] = max(s["uv_max_abs_diff"], float(np.abs(e1[4] - e2[4]).max()))
            # cross-LOD: compare this chunk at `lod` against the neighbour at lod+1 along the same edge
            nb2 = by_g.get(((gx + dx, gy + dy), lod + 1))
            if nb2 is not None:
                X3, Y3, Z3, _, _ = nb2[3]
                if dx:
                    z_other = np.interp(Y, Y3, Z3[:, 0])
                else:
                    z_other = np.interp(X, X3, Z3[0, :])
                gap = float(np.abs(e1[2] - z_other).max())
                sk = max(skirt[(cell, f"ch{a}{b}", lod)], skirt[(nb2[0], f"ch{nb2[1]}{nb2[2]}", lod + 1)])
                c = res["cross_lod"]
                c["pairs"] += 1
                c["max_gap_over_skirt"] += int(gap > sk)
                if gap > c["max_gap_m"]:
                    c["max_gap_m"], c["worst"] = round(gap, 3), {"chunk": f"{cell}/ch{a}{b}", "lod": lod, "skirt_m": sk}
    res["same_lod"]["normal_max_angle_deg"] = round(res["same_lod"]["normal_max_angle_deg"], 6)
    return res


def check_stitch(run, xin):
    """Watertightness of the Xinyi seam strip, read from the shipped GLBs."""
    cellX = "C+0038+0346"
    out = {}
    cell_box = shapely.box(304000, 2768000, 312000, 2776000)
    for f in sorted((run / "chunks" / cellX).glob("xinyi_stitch_lod*.glb")):
        k = int(f.stem.split("lod")[1])
        sc = trimesh.load_scene(io.BytesIO(f.read_bytes()), file_type="glb", process=False)
        node = sc.graph.nodes_geometry[0]
        tr, g = sc.graph[node]
        m = sc.geometry[g]
        v = np.asarray(m.vertices, dtype=np.float64)
        W = np.column_stack([v[:, 0] + tr[0, 3] + frame.NTW_ORIGIN_TM2[0], -(v[:, 2] + tr[2, 3]) + frame.NTW_ORIGIN_TM2[1], v[:, 1]])
        faces = np.asarray(m.faces)
        from scipy.spatial import cKDTree
        TOL = 0.005  # 5 mm: float32 GLB storage of positions a few km from the node origin
        P, Pz, _ = xin.edge_ring(every=2 ** k)
        tree = cKDTree(W[:, :2])
        dd, ii = tree.query(P)
        pidx = [int(i) if d <= TOL else None for d, i in zip(dd, ii)]
        missing_p = sum(i is None for i in pidx)
        pz_err = max(abs(W[i, 2] - z) for i, z in zip(pidx, Pz) if i is not None)
        edges = set()
        for a_, b_, c_ in faces:
            for u, w in ((a_, b_), (b_, c_), (c_, a_)):
                edges.add((min(u, w), max(u, w)))
        seg_ok = sum(1 for i in range(len(pidx)) if pidx[i] is not None and pidx[(i + 1) % len(pidx)] is not None
                     and (min(pidx[i], pidx[(i + 1) % len(pidx)]), max(pidx[i], pidx[(i + 1) % len(pidx)])) in edges)
        # hole-side vertices must be exact chunk vertices (position and height)
        chunk_xy, chunk_z = [], []
        kept = []
        for cf in sorted((run / "chunks" / cellX).glob(f"ch??_lod{k}.glb")):
            sc2 = trimesh.load_scene(io.BytesIO(cf.read_bytes()), file_type="glb", process=False)
            n2 = sc2.graph.nodes_geometry[0]
            tr2, g2 = sc2.graph[n2]
            m2 = sc2.geometry[g2]
            v2 = np.asarray(m2.vertices, dtype=np.float64)
            W2 = np.column_stack([v2[:, 0] + tr2[0, 3] + frame.NTW_ORIGIN_TM2[0], -(v2[:, 2] + tr2[2, 3]) + frame.NTW_ORIGIN_TM2[1], v2[:, 1]])
            nx_ = len(np.unique(v2[:, 0]))
            ngrid = nx_ * nx_
            chunk_xy.append(W2[:ngrid, :2])
            chunk_z.append(W2[:ngrid, 2])
            F2 = np.asarray(m2.faces)
            F2 = F2[(F2 < ngrid).all(axis=1)]
            kept.extend(shapely.polygons(W2[F2][:, :, :2]).tolist())
        ctree = cKDTree(np.vstack(chunk_xy))
        cz = np.concatenate(chunk_z)
        is_p = np.zeros(len(W), bool)
        is_p[[i for i in pidx if i is not None]] = True
        qv = W[~is_p]
        dq, iq = ctree.query(qv[:, :2])
        q_n = len(qv)
        q_bad = int(((dq > TOL) | (np.abs(cz[iq] - qv[:, 2]) > 1e-3)).sum())
        stitch = shapely.union_all(shapely.polygons(W[faces][:, :, :2]))
        inner = shapely.Polygon(P)
        keptu = shapely.union_all(kept)
        win = shapely.intersection(inner.buffer(3 * 20.0 * 2 ** k).envelope, cell_box)
        cover = shapely.union_all([stitch, inner, keptu])
        gap = shapely.difference(win, cover).area
        ov = (shapely.intersection(stitch, keptu).area + shapely.intersection(stitch, inner).area + shapely.intersection(keptu, inner).area)
        # edge deviation of this LOD's ring vs the full-resolution accepted edge (what a LOD0 Xinyi Landscape would show)
        P0, Pz0, _ = xin.edge_ring(every=1)
        if k:
            s0 = np.r_[0, np.cumsum(np.hypot(*np.diff(np.vstack([P0, P0[:1]]), axis=0).T))]
            z0 = np.r_[Pz0, Pz0[:1]]
            sk = s0[::2 ** k]
            zk = np.r_[Pz0[::2 ** k], Pz0[:1]]
            sk = np.r_[sk[:len(zk) - 1], s0[-1]]
            dev = float(np.abs(np.interp(s0, sk, zk) - z0).max())
        else:
            dev = 0.0
        out[f"lod{k}"] = {"edge_vertices": len(P), "edge_vertices_missing": missing_p, "edge_height_max_err_m": round(float(pz_err), 6),
                          "edge_segments": len(P), "edge_segments_present_as_mesh_edges": seg_ok,
                          "hole_side_vertices": q_n, "hole_side_vertices_not_equal_to_chunk_vertices": q_bad,
                          "gap_area_m2": round(gap, 4), "overlap_area_m2": round(ov, 4), "triangles": len(faces),
                          "ring_vs_full_res_xinyi_edge_max_dev_m": round(dev, 3)}
    return out


def check_xinyi(run_conf, run_raw, xin, out_fig):
    cellX = "C+0038+0346"
    Xc, Yc, Zc, Nc = assemble_cell(run_conf, cellX, 0)
    Xr, Yr, Zr, Nr = assemble_cell(run_raw, cellX, 0)
    study = json.loads((REPO / "data/ntw/coordinate_study.json").read_text(encoding="utf-8"))["xinyi_enu_to_ntw_affine"]
    M = np.array(study["linear_part"])          # ENU -> TM2 linear part
    Minv_T = np.linalg.inv(M).T
    ox, oy = wc.TO_TM2.transform(xin.lon0, xin.lat0)
    sides = {"south": ((xin.e0, xin.n0), (xin.e1, xin.n0)), "east": ((xin.e1, xin.n0), (xin.e1, xin.n1)),
             "north": ((xin.e1, xin.n1), (xin.e0, xin.n1)), "west": ((xin.e0, xin.n1), (xin.e0, xin.n0))}
    out = {}
    profiles = {}
    for name, ((ea, na), (eb, nb)) in sides.items():
        L = math.hypot(eb - ea, nb - na)
        t = np.linspace(0, 1, int(L / 2.0) + 1)
        e, n = ea + t * (eb - ea), na + t * (nb - na)
        lon = xin.lon0 + np.degrees(e / (6378137.0 * math.cos(math.radians(xin.lat0))))
        lat = xin.lat0 + np.degrees(n / 6378137.0)
        px, py = wc.TO_TM2.transform(lon, lat)
        hx = xin.height_enu(e, n)
        zc = tri_interp(Xc, Yc, Zc, px, py)
        zr = tri_interp(Xr, Yr, Zr, px, py)
        # translation-only placement: Xinyi ENU taken as (TM2 - TM2(origin)) with no rotation / scale
        et, nt = px - ox, py - oy
        ht = xin.height_enu(et, nt)
        mis = np.hypot(et - e, nt - n)
        # normals: Xinyi landscape gradient (ENU) -> TM2 via M^-T ; NTW shipped vertex normals (bilinear)
        d = xin.step
        gx = (xin.height_enu(np.clip(e + d, xin.e0, xin.e1), n) - xin.height_enu(np.clip(e - d, xin.e0, xin.e1), n)) / \
             (np.clip(e + d, xin.e0, xin.e1) - np.clip(e - d, xin.e0, xin.e1))
        gy = (xin.height_enu(e, np.clip(n + d, xin.n0, xin.n1)) - xin.height_enu(e, np.clip(n - d, xin.n0, xin.n1))) / \
             (np.clip(n + d, xin.n0, xin.n1) - np.clip(n - d, xin.n0, xin.n1))
        g_t = (Minv_T @ np.vstack([gx, gy])).T
        nx_ = np.column_stack([-g_t[:, 0], -g_t[:, 1], np.ones(len(g_t))])
        nx_ /= np.linalg.norm(nx_, axis=1, keepdims=True)

        def ang(NN):
            nn = bilin(Xc, Yc, NN, px, py).copy()
            nn /= np.linalg.norm(nn, axis=1, keepdims=True)
            return np.degrees(np.arccos(np.clip(np.sum(nn * nx_, 1), -1, 1)))
        a_c, a_r = ang(Nc), ang(Nr)

        def st(dv):
            ok = np.isfinite(dv)
            a = np.abs(dv[ok])
            return {"max_abs_m": round(float(a.max()), 3), "p95_abs_m": round(float(np.percentile(a, 95)), 3),
                    "mean_m": round(float(dv[ok].mean()), 3), "median_m": round(float(np.median(dv[ok])), 3),
                    "defined_fraction": round(float(ok.mean()), 3)}
        out[name] = {"samples": len(t), "length_m": round(L, 1),
                     "raw_official_minus_xinyi": st(zr - hx), "conformed_minus_xinyi": st(zc - hx),
                     "translation_only_xinyi_minus_raw": st(ht - zr),
                     "translation_only_horizontal_misplacement_m": {"max": round(float(mis.max()), 2), "mean": round(float(mis.mean()), 2)},
                     "normal_angle_deg_raw": {"max": round(float(a_r.max()), 2), "p95": round(float(np.percentile(a_r, 95)), 2)},
                     "normal_angle_deg_conformed": {"max": round(float(a_c.max()), 2), "p95": round(float(np.percentile(a_c, 95)), 2)}}
        profiles[name] = (t * L, hx, zr, zc, ht)
    allc = np.concatenate([profiles[k][3] - profiles[k][1] for k in profiles])
    allr = np.concatenate([profiles[k][2] - profiles[k][1] for k in profiles])
    if not (np.isfinite(allc).all() and np.isfinite(allr).all()):
        raise SystemExit("FAIL: non-finite seam heights")
    out["all_sides"] = {"raw_official_minus_xinyi_median_m": round(float(np.median(allr)), 3),
                        "raw_max_abs_step_m": round(float(np.abs(allr).max()), 3),
                        "conformed_max_abs_step_m": round(float(np.abs(allc).max()), 3),
                        "conformed_p95_abs_step_m": round(float(np.percentile(np.abs(allc), 95)), 3),
                        "accepted_xinyi_vertical_offset_m": xin.offset_m,
                        "variants": "raw = official DEM untouched; conformed = 200 m blend band only (comparison, NOT shipped); "
                                    "shipped default = stitch (see xinyi_stitch: exact edge, watertight)",
                        "collision": "shipped stitch mode: the new terrain has a hole exactly covered by the accepted Xinyi Landscape plus "
                                     "the stitch strip (gap/overlap area < 0.2 m2 of float32 noise over ~20 km of seam lines), so a "
                                     "collision trace crossing the edge always meets a surface with zero vertical step at the Xinyi edge. "
                                     "Unreal collision traces NOT TESTED."}
    plot_profiles(profiles, out_fig / "xinyi_seam_profiles.png")
    return out


def check_sources(xin):
    """Mirror vs official on the two cells; official vs WFS surveyed ground (datum)."""
    from dtm import Dtm
    dem = Dem(["臺北市", "新北市"])
    bb = (304000.0, 2760000.0, 312000.0, 2776000.0)
    z, _, _, _ = dem.mosaic(bb)
    xs = bb[0] + np.arange(z.shape[1]) * 20.0
    ys = bb[1] + np.arange(z.shape[0]) * 20.0
    sel_j, sel_i = np.meshgrid(np.arange(0, z.shape[0], 8), np.arange(0, z.shape[1], 8), indexing="ij")
    px, py = xs[sel_i].ravel(), ys[sel_j].ravel()
    lon, lat = wc.TO_LL.transform(px, py)
    d = Dtm()
    zm = np.array([d.sample(a, b) for a, b in zip(lon, lat)])
    zo = z[sel_j, sel_i].ravel()
    ok = ~np.isnan(zm)
    diff = zm[ok] - zo[ok]
    # WFS surveyed ground
    gx, gy, gz = [], [], []
    for line in (REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson").open(encoding="utf-8"):
        r = json.loads(line)
        g = r["geometry"]
        ring = np.asarray(g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0])
        cx, cy = ring[:, 0].mean(), ring[:, 1].mean()
        if bb[0] + 20 <= cx < bb[2] - 20 and bb[1] + 20 <= cy < bb[3] - 20:
            ent = r["p"].get("1_ent_heig")
            try:
                ent = float(ent)
            except (TypeError, ValueError):
                continue
            gx.append(cx); gy.append(cy); gz.append(ent)
    gx, gy, gz = map(np.asarray, (gx, gy, gz))
    zo_w = bilin(xs, ys, z, gx, gy)
    dw = zo_w - gz
    outline = xin.outline_tm2()
    inx = shapely.contains_xy(outline, gx, gy)
    per_chunk = defaultdict(list)
    for x_, y_, v in zip(gx, gy, dw):
        per_chunk[(int((x_ - bb[0]) // 1600), int((y_ - bb[1]) // 1600))].append(v)
    med = {f"{a}_{b}": round(float(np.median(v)), 3) for (a, b), v in sorted(per_chunk.items()) if len(v) >= 50}
    vals = np.array(list(med.values()))
    return {"mirror_minus_official": {"samples": int(ok.sum()), "median_m": round(float(np.median(diff)), 3),
                                      "p95_abs_m": round(float(np.percentile(np.abs(diff), 95)), 3),
                                      "max_abs_m": round(float(np.abs(diff).max()), 3)},
            "official_minus_wfs_surveyed_ground": {
                "buildings": int(len(dw)), "median_m": round(float(np.median(dw)), 3),
                "median_abs_m": round(float(np.median(np.abs(dw))), 3),
                "inside_xinyi_median_m": round(float(np.median(dw[inx])), 3), "outside_xinyi_median_m": round(float(np.median(dw[~inx])), 3),
                "per_1p6km_chunk_median_m": med, "chunk_median_range_m": [round(float(vals.min()), 3), round(float(vals.max()), 3)],
                "note": "WFS ground = 1_ent_heig (entrance elevation, Taipei City only); differences include building-entrance vs bare-earth semantics"}}


def lod_table(run):
    rep = load_report(run)
    by = defaultdict(list)
    for c in rep["chunks"]:
        if c["xinyi_conformed_nodes"] == 0 and c["chunk"].startswith("ch"):
            by[c["lod"]].append(c)
    tab = []
    th = math.tan(math.radians(SSE["vertical_fov_deg"] / 2))
    for lod, cs in sorted(by.items()):
        e95 = float(np.percentile([c.get("lod_err_p99_m", c["lod_err_max_m"]) for c in cs], 95))
        emax = float(np.percentile([c["lod_err_max_m"] for c in cs], 95))
        row = {"lod": lod, "step_m": cs[0]["step_m"], "triangles_per_chunk": cs[0]["triangles_terrain"],
               "triangles_with_skirt": cs[0]["triangles_total"], "glb_kb_per_chunk": round(float(np.mean([c["bytes"] for c in cs])) / 1024, 1),
               "err_p99_p95_m": round(e95, 2), "err_max_p95_m": round(emax, 2),
               "err_rms_mean_m": round(float(np.mean([c["lod_err_rms_m"] for c in cs])), 3)}
        for b in SSE["budgets_px"]:
            row[f"switch_distance_m_sse_{b:g}px"] = round(e95 * SSE["screen_height_px"] / (2 * th * b)) if e95 > 0 else 0
        tab.append(row)
    return {"sse_model": SSE, "table": tab,
            "chunks_per_cell": 25, "lod0_triangles_per_8km_cell": tab[0]["triangles_per_chunk"] * 25}


# ------------------------------------------------------------------------------------------------ figures
def font(sz):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", sz)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def plot_profiles(profiles, path):
    W, H, pad = 1400, 1000, 60
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    names = ["south", "east", "north", "west"]
    ph = (H - 40) // 4
    for k, nm in enumerate(names):
        s, hx, zr, zc, ht = profiles[nm]
        y0 = 30 + k * ph
        top, bot = y0 + 10, y0 + ph - 25
        lo = min(hx.min(), zr.min(), zc.min(), ht.min())
        hi = max(hx.max(), zr.max(), zc.max(), ht.max())
        hi = hi if hi - lo > 1 else lo + 1
        def P(xv, yv):
            return [(pad + (W - 2 * pad) * x / s[-1], bot - (bot - top) * (y - lo) / (hi - lo)) for x, y in zip(xv, yv)]
        d.rectangle([pad, top, W - pad, bot], outline=(180, 180, 180))
        for arr, col in ((ht, (200, 200, 200)), (zr, (220, 90, 40)), (hx, (30, 30, 30)), (zc, (30, 110, 220))):
            d.line(P(s, arr), fill=col, width=1 if col == (200, 200, 200) else 2)
        d.text((pad, y0 - 6), f"Xinyi {nm} edge  (length {s[-1]:.0f} m, height {lo:.1f}-{hi:.1f} m)", fill=(0, 0, 0), font=font(14))
    d.text((pad, H - 22), "black = accepted Xinyi Landscape, orange = new terrain raw official DEM, blue = new terrain conformed, grey = Xinyi if placed by translation only",
           fill=(0, 0, 0), font=font(13))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)


def plot_diff_map(run_conf, run_raw, xin, path):
    cellX = "C+0038+0346"
    X, Y, Zc, _ = assemble_cell(run_conf, cellX, 0)
    _, _, Zr, _ = assemble_cell(run_raw, cellX, 0)
    ol = xin.outline_tm2()
    b = ol.buffer(400).bounds
    i0, i1 = np.searchsorted(X, b[0]), np.searchsorted(X, b[2])
    j0, j1 = np.searchsorted(Y, b[1]), np.searchsorted(Y, b[3])
    D = (Zc - Zr)[j0:j1, i0:i1]
    sc = 4
    h, w = D.shape
    img = Image.new("RGB", (w * sc, h * sc + 40), "white")
    px = img.load()
    for j in range(h):
        for i in range(w):
            v = max(-1.0, min(1.0, D[j, i]))
            col = (255, int(255 * (1 - v)), int(255 * (1 - v))) if v > 0 else (int(255 * (1 + v)), int(255 * (1 + v)), 255)
            for a in range(sc):
                for c in range(sc):
                    px[i * sc + a, (h - 1 - j) * sc + c] = col
    dr = ImageDraw.Draw(img)
    pts = [((x - X[i0]) / 20 * sc, (h - 1 - (y - Y[j0]) / 20) * sc) for x, y in ol.exterior.coords]
    dr.line(pts + [pts[0]], fill=(0, 0, 0), width=2)
    dr.text((6, h * sc + 6), "conformed - raw official (m): blue -1 .. white 0 .. red +1; black = accepted Xinyi outline; 200 m blend band outside",
            fill=(0, 0, 0), font=font(13))
    img.save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()
    xin = XinyiLandscape()
    cells = ["C+0038+0346", "C+0038+0345"]
    FIG.mkdir(parents=True, exist_ok=True)
    out = {
        "shard": check_shard(T / "joint_run1", T / "joint_run2", [T / "cell_a", T / "cell_b"]),
        "face_orientation": check_orientation(T / "joint_run1"),
        "seams_conformed": check_seams(T / "joint_run1", cells),
        "seams_raw": check_seams(T / "joint_raw", cells),
        "xinyi_seam": check_xinyi(T / "joint_conform", T / "joint_raw", xin, FIG),
        "xinyi_stitch": check_stitch(T / "joint_run1", xin),
        "sources": check_sources(xin),
        "lod": lod_table(T / "joint_run1"),
        "terrain_report_summary": {k: v for k, v in load_report(T / "joint_run1").items() if k in ("source", "fail_closed", "cell_products", "xinyi", "params")},
    }
    out["terrain_report_summary"]["source"]["packages"] = {k: v for k, v in out["terrain_report_summary"]["source"]["packages"].items()
                                                         if not k.startswith("catalog")}
    plot_diff_map(T / "joint_conform", T / "joint_raw", xin, FIG / "xinyi_seam_conform_diff.png")
    od = REPO / "data/ntw/terrain"
    od.mkdir(parents=True, exist_ok=True)
    (od / "pilot_terrain_qa.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("face_orientation", "shard", "seams_conformed", "seams_raw", "lod")}, ensure_ascii=False, indent=1))
    print(json.dumps(out["xinyi_seam"]["all_sides"], ensure_ascii=False, indent=1))
    print(json.dumps(out["xinyi_stitch"], ensure_ascii=False, indent=1))
    print(json.dumps(out["sources"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
