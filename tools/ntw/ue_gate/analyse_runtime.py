"""Offline analysis of the Phase 2B UE runtime gate (raw outputs in D:/Users/EDDY/UEIsolated/gate_out/runtime_full, not committed).

Writes the compact committed result data/ntw/runtime/runtime_gate_result.json and image evidence under
docs/evidence/ntw/runtime/. Gates are evaluated here from engine measurements only; nothing is inferred from asset import.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
NTW = HERE.parent
REPO = NTW.parents[1]
sys.path.insert(0, str(NTW))
sys.path.insert(0, str(REPO / "tools/compiler"))
import build_terrain_cells as btc  # noqa: E402

GATE = Path("D:/Users/EDDY/UEIsolated/gate_out")
RAW = GATE / "runtime_full"            # configured-grid session (collision, precision, LOD matrix, altitude, 6 flights)
RAW2 = GATE / "runtime_followup"       # micro-offset traces + template-default-grid session (the full run's template
                                       # session aborted on a census assumption; re-run with the census relaxed)
OUT_JSON = REPO / "data/ntw/runtime/runtime_gate_result.json"
EVID = REPO / "docs/evidence/ntw/runtime"
ORIGIN = (296000.0, 2760000.0)
CELLS_BOX = (304000.0, 2760000.0, 312000.0, 2776000.0)

# acceptance thresholds, fixed BEFORE reading the full-run data (probe runs only exercised the harness)
TH = {"mesh_dz_max_m": 0.05, "landscape_dz_max_m": 0.10, "seam_step_max_m": 0.10, "actor_pos_err_max_cm": 0.5,
      "landscape_corner_err_max_cm": 1.0, "crack_px_max": 0, "ground_presence_ahead_m": [0, 500, 1000, 2000]}


def ue_to_tm2(x, y):
    return x / 100.0 + ORIGIN[0], -y / 100.0 + ORIGIN[1]


def tm2_to_ue(e, n):
    return (e - ORIGIN[0]) * 100.0, -(n - ORIGIN[1]) * 100.0


def pct(a, q):
    return None if len(a) == 0 else float(np.percentile(a, q))


def stats(a):
    a = np.asarray([v for v in a if v is not None and np.isfinite(v)], float)
    if len(a) == 0:
        return {"n": 0}
    return {"n": int(len(a)), "p50": round(pct(np.abs(a), 50), 4), "p99": round(pct(np.abs(a), 99), 4), "max": round(float(np.abs(a).max()), 4),
            "mean_signed": round(float(a.mean()), 4)}


# ------------------------------------------------------------------------------------------------------------- collision
def landscape_tri_heights(xin, e, n):
    """Heights of the two possible quad triangulations at ENU (e, n) (diagonal A: (c,r)-(c+1,r+1); B: (c+1,r)-(c,r+1))."""
    col = (e - xin.e0) / xin.step
    row = (xin.n1 - n) / xin.step
    c0 = np.clip(np.floor(col).astype(int), 0, xin.n - 2)
    r0 = np.clip(np.floor(row).astype(int), 0, xin.n - 2)
    u, v = col - c0, row - r0
    h = xin.h
    h00, h10, h01, h11 = h[r0, c0], h[r0, c0 + 1], h[r0 + 1, c0], h[r0 + 1, c0 + 1]
    a = np.where(u >= v, h00 + u * (h10 - h00) + v * (h11 - h10), h00 + v * (h01 - h00) + u * (h11 - h01))
    b = np.where(u + v <= 1, h00 + u * (h10 - h00) + v * (h01 - h00), h11 + (1 - u) * (h01 - h11) + (1 - v) * (h10 - h11))
    return a, b


class Reference:
    """Offline reference surfaces in EPSG:3826: shipped chunk LOD0 + stitch v2 LOD0 surface (prepare_gate_inputs) and the accepted
    Landscape as a mesh with the engine's measured quad diagonal (A), placed by the same affine."""
    def __init__(self):
        import trimesh
        import prepare_gate_inputs as pgi
        self.xin = xin = btc.XinyiLandscape()
        rep = json.loads((pgi.RUN / "terrain.report.json").read_text(encoding="utf-8"))
        sw = {(c["cell"], c["chunk"], c["lod"]): c["sw_epsg3826"] for c in rep["chunks"]}
        ms = [pgi.load_world_mesh(pgi.RUN / "chunks" / c / f"{ch}_lod0.glb", sw[(c, ch, 0)]) for (c, ch, lod) in sw if lod == 0 and ch.startswith("ch")]
        st = pgi.load_world_mesh(pgi.RUN / "chunks" / "C+0038+0346" / "xinyi_stitch_lod0.glb", sw[("C+0038+0346", "xinyi_stitch", 0)])
        nsurf = next(c["triangles_terrain"] for c in rep["chunks"] if c["chunk"] == "xinyi_stitch" and c["lod"] == 0)
        self.world = trimesh.util.concatenate(ms + [trimesh.Trimesh(st.vertices, st.faces[:nsurf], process=False)])
        self.n_stitch_faces = nsurf                       # the LAST nsurf faces of self.world are the stitch surface
        n = xin.n
        cc, rr = np.meshgrid(np.arange(n), np.arange(n))
        e, nn = xin.e0 + cc * xin.step, xin.n1 - rr * xin.step
        x, y = btc.xinyi_enu_to_tm2(e.ravel(), nn.ravel())
        V = np.column_stack([x, y, xin.h.ravel()])
        q = (rr[:-1, :-1] * n + cc[:-1, :-1]).ravel()
        F = np.vstack([np.column_stack([q, q + 1, q + n + 1]), np.column_stack([q, q + n + 1, q + n])])
        self.land = trimesh.Trimesh(V, F, process=False)
        # 20 m height grid of the shipped chunk LOD0 vertices (top surface: max z per node, skirts excluded) for ray-marching
        cv = np.vstack([m.vertices for m in ms])
        gx = np.rint((cv[:, 0] - CELLS_BOX[0]) / 20.0).astype(int)
        gy = np.rint((cv[:, 1] - CELLS_BOX[1]) / 20.0).astype(int)
        on = (np.abs(cv[:, 0] - (CELLS_BOX[0] + gx * 20.0)) < 1e-3) & (np.abs(cv[:, 1] - (CELLS_BOX[1] + gy * 20.0)) < 1e-3)
        self.grid = np.full((int((CELLS_BOX[3] - CELLS_BOX[1]) / 20) + 1, int((CELLS_BOX[2] - CELLS_BOX[0]) / 20) + 1), -np.inf)
        np.maximum.at(self.grid, (gy[on], gx[on]), cv[on, 2])
        self.grid[~np.isfinite(self.grid)] = np.nan

    def top_z(self, x, y):
        o = np.column_stack([x, y, np.full(len(x), 5000.0)])
        loc, ri, _ = self.world.ray.intersects_location(o, np.tile([0, 0, -1.0], (len(x), 1)), multiple_hits=False)
        z = np.full(len(x), np.nan)
        if len(ri):
            z[ri] = np.asarray(loc).reshape(-1, 3)[:, 2]
        return z

    def enu(self, x, y):
        return btc.tm2_to_xinyi_enu(np.asarray(x, float), np.asarray(y, float))

    def inside(self, e, n, tol=1e-4):
        x = self.xin
        return (e > x.e0 + tol) & (e < x.e1 - tol) & (n > x.n0 + tol) & (n < x.n1 - tol)

    def on_edge(self, e, n, tol=1e-4):
        x = self.xin
        span_e = (e >= x.e0 - tol) & (e <= x.e1 + tol)
        span_n = (n >= x.n0 - tol) & (n <= x.n1 + tol)
        return (((np.abs(e - x.e0) <= tol) | (np.abs(e - x.e1) <= tol)) & span_n) | (((np.abs(n - x.n0) <= tol) | (np.abs(n - x.n1) <= tol)) & span_e)


def collision(inp, tr, micro_inp, micro_hits, ref):
    xin = ref.xin
    T = inp["traces"]
    H = tr["hits"]
    assert len(T) == len(H)
    XY = np.array([ue_to_tm2(t["ue"][0], t["ue"][1]) for t in T])
    E, N = ref.enu(XY[:, 0], XY[:, 1])
    za, zb = landscape_tri_heights(xin, E, N)
    li = [i for i, t in enumerate(T) if t["expect"] == "xinyi_landscape" and H[i] is not None and H[i][1] == "L"]
    zg = np.array([H[i][0] for i in li])
    eA, eB = np.abs(zg - za[li]).max(), np.abs(zg - zb[li]).max()
    diag = "A" if eA <= eB else "B"
    ztri = za if diag == "A" else zb
    # expectation corrections, decided AFTER the full run and disclosed in the result:
    #  (1) points exactly on the shared Landscape / stitch boundary line may legitimately hit either actor (expect 'either');
    #  (2) dem_nodes: random shipped-mesh vertices included skirt vertices (z - 2 m) and vertices orphaned inside the Xinyi hole;
    #      only top-surface vertices outside the accepted sector are DEM-node checks
    on_line = ref.on_edge(E, N)
    dem = np.array([t["set"] == "dem_nodes" for t in T])
    tz = np.full(len(T), np.nan)
    tz[dem] = ref.top_z(XY[dem, 0], XY[dem, 1])
    inside = ref.inside(E, N)
    excluded = Counter()
    expect, expz = [], []
    n_either = 0
    for i, t in enumerate(T):
        ex, z = t["expect"], t["exp_z"]
        if on_line[i] and t["set"].startswith(("corner", "xinyi")):
            ex, z = "either", float(ztri[i])
            n_either += 1
        if t["set"] == "dem_nodes":
            if inside[i]:
                ex = None
                excluded["dem_node_inside_accepted_landscape_orphan_vertex"] += 1
            elif not np.isfinite(tz[i]) or abs(tz[i] - z) > 0.001:
                ex = None
                excluded["dem_node_not_top_surface_skirt_vertex"] += 1
            else:
                ex = "chunk_or_stitch"      # hole-boundary nodes are shared by the chunk and the stitch (identical vertex)
        if ex is not None and ex != "either" and inside[i]:     # e.g. the chunk-seam line E 305,600 crosses the accepted sector
            ex = "xinyi_landscape"
        if ex == "xinyi_landscape":
            z = float(ztri[i])
        expect.append(ex)
        expz.append(z)
    by = defaultdict(list)
    for i, t in enumerate(T):
        if expect[i] is not None:
            by[t["set"]].append(i)
    # S3 = Phase 2B-C fixed-hole stitch; F = collision-only flange (exists only within w of the Xinyi edge)
    ok_kinds = {"xinyi_landscape": {"L", "F"}, "stitch": {"S2", "S3", "F"}, "chunk_or_stitch": {"C", "S2", "S3", "F"}, "chunk_vertex": {"C"},
                "either": {"L", "S2", "S3", "F"}}
    out = {"landscape_triangulation": {"diagonal": diag, "max_abs_dz_A_m": round(float(eA), 4), "max_abs_dz_B_m": round(float(eB), 4), "n": len(li),
                                       "note": "Landscape collision = quad split along diagonal A; landscape expectations use it (bilinear also reported)"},
           "expectation_corrections": {"exact_boundary_points_expect_either": n_either, "excluded": dict(excluded),
                                       "note": "decided after the full run (see doc); no engine data was changed"},
           "sets": {}}
    for name, idx in by.items():
        miss = [i for i in idx if H[i] is None]
        wrong = [i for i in idx if H[i] is not None and H[i][1] not in ok_kinds[expect[i]]]
        dz_land, dz_mesh, dz_bil = [], [], []
        for i in idx:
            if H[i] is None or expz[i] is None:
                continue
            (dz_land if H[i][1] == "L" else dz_mesh).append(H[i][0] - expz[i])
            if H[i][1] == "L" and T[i]["exp_z"] is not None:
                dz_bil.append(H[i][0] - T[i]["exp_z"])
        out["sets"][name] = {"n": len(idx), "misses": len(miss), "misses_on_exact_boundary": sum(1 for i in miss if on_line[i]),
                             "wrong_actor": len(wrong), "wrong_examples": [{"i": i, "expect": expect[i], "got": H[i][1]} for i in wrong[:5]],
                             "kinds": dict(Counter(H[i][1] for i in idx if H[i] is not None)),
                             "dz_mesh_m": stats(dz_mesh), "dz_landscape_vs_triangulation_m": stats(dz_land), "dz_landscape_vs_bilinear_m": stats(dz_bil),
                             "no_expectation": sum(1 for i in idx if expz[i] is None)}
    steps = {}
    for side in ("south", "east", "north", "west"):
        a = {t["s"]: h for t, h in zip(micro_inp, micro_hits) if t["set"] == "micro_" + side and t["off"] == -0.0005}
        b = {t["s"]: h for t, h in zip(micro_inp, micro_hits) if t["set"] == "micro_" + side and t["off"] == 0.0005}
        steps["xinyi_%s_at_1mm" % side] = stats([b[k][0] - a[k][0] for k in a if k in b and a[k] and b[k]])
        idx = [i for i in range(len(T)) if T[i]["set"] == "xinyi_" + side]
        inner = {T[i]["s"]: i for i in idx if T[i]["off"] == -0.05}
        outer = {T[i]["s"]: i for i in idx if T[i]["off"] == 0.05}
        raw, res = [], []
        for k, i in inner.items():
            j = outer.get(k)
            if j is None or H[i] is None or H[j] is None or expz[i] is None or expz[j] is None:
                continue
            raw.append(H[j][0] - H[i][0])
            res.append((H[j][0] - expz[j]) - (H[i][0] - expz[i]))
        steps["xinyi_%s_raw_at_10cm" % side] = stats(raw)
        steps["xinyi_%s_residual_at_10cm" % side] = stats(res)
    for name in ("cell_seam_N2768000", "chunk_seam_E305600", "chunk_seam_N2763200"):
        idx = [i for i in range(len(T)) if T[i]["set"] == name]
        neg = [i for i in idx if T[i]["off"] == -0.05]
        pos = [i for i in idx if T[i]["off"] == 0.05]
        pr = [(p_, q_) for p_, q_ in zip(pos, neg) if H[p_] and H[q_] and expz[p_] is not None and expz[q_] is not None]
        steps[name + "_raw_at_10cm"] = stats([H[p_][0] - H[q_][0] for p_, q_ in pr])
        steps[name + "_residual_at_10cm"] = stats([(H[p_][0] - expz[p_]) - (H[q_][0] - expz[q_]) for p_, q_ in pr])
    out["seam_steps_m"] = steps
    out["seam_steps_note"] = ("raw 10 cm steps include terrain slope (south edge up to ~2:1); continuity is judged at 1 mm separation "
                              "(Xinyi edges, micro traces) and by the slope-free residual (hit minus own expected surface on each side)")
    mesh_max = max((v["dz_mesh_m"].get("max", 0) for v in out["sets"].values()), default=0)
    land_max = max((v["dz_landscape_vs_triangulation_m"].get("max", 0) for v in out["sets"].values()), default=0)
    step_max = max(v.get("max", 0) for k, v in steps.items() if k.endswith(("_at_1mm", "_residual_at_10cm")))
    misses = sum(v["misses"] for v in out["sets"].values())
    misses_line = sum(v["misses_on_exact_boundary"] for v in out["sets"].values())
    wrong = sum(v["wrong_actor"] for v in out["sets"].values())
    out["gate"] = {"misses": misses, "misses_on_exact_boundary": misses_line, "wrong_actor": wrong, "mesh_dz_max_m": mesh_max,
                   "landscape_dz_max_m": land_max, "seam_step_max_m": step_max,
                   "status": "PASS" if (misses == 0 and wrong == 0 and mesh_max <= TH["mesh_dz_max_m"] and land_max <= TH["landscape_dz_max_m"]
                                        and step_max <= TH["seam_step_max_m"]) else "FAIL"}
    return out


# ------------------------------------------------------------------------------------------------------------- precision
def precision(prec):
    rep = json.loads((REPO / "data/generated/ntw/terrain/joint_ue_local/terrain.report.json").read_text(encoding="utf-8"))
    sw = {(c["cell"], c["chunk"]): c["sw_epsg3826"] for c in rep["chunks"] if c["lod"] == 0}
    errs = {}
    for a in prec["actors"]:
        lab, loc = a["label"], a["loc"]
        exp = None
        if "NTWChunk" in a["tags"]:
            _, cell, ch = lab.split("_", 2)
            exp = list(tm2_to_ue(*sw[(cell, ch)])) + [0.0]
        elif "NTWStitch" in a["tags"]:
            exp = list(tm2_to_ue(*sw[("C+0038+0346", "xinyi_stitch")])) + [0.0]
        elif "XinyiBuildings" in a["tags"]:
            ix, iy = (int(v) for v in lab.split("_")[-2:])
            x, y = btc.xinyi_enu_to_tm2(ix * 500.0, iy * 500.0)
            exp = list(tm2_to_ue(float(x[0]), float(y[0]))) + [0.0]
        if exp is None:
            continue
        k = a["tags"][0]
        e = math.dist(loc, exp)
        errs.setdefault(k, []).append(e)
    c = json.loads((btc.ACCEPTED_XINYI / "xinyi_unreal_v2_contract.json").read_text(encoding="utf-8"))
    ext, st = c["coordinate_contract"]["extent_enu_m"], c["landscape"]["sample_spacing_m"]
    corner_enu = {"q00": (ext["min_east_m"], ext["max_north_m"]), "q630_0": (ext["min_east_m"] + 630 * st, ext["max_north_m"]),
                  "q0_630": (ext["min_east_m"], ext["max_north_m"] - 630 * st), "q630_630": (ext["min_east_m"] + 630 * st, ext["max_north_m"] - 630 * st)}
    corners = {}
    for k, (e, n) in corner_enu.items():
        x, y = btc.xinyi_enu_to_tm2(e, n)
        exp = tm2_to_ue(float(x[0]), float(y[0]))
        got = prec["landscape"]["corners_cm"][k]
        corners[k] = round(math.dist(got[:2], exp), 4)
    probes = {k: {"readback_err_cm": round(math.dist(v["pie_cm"], {"near": (37.37, -61.61, 12345.67), "far": (11000000.37, -11000000.61, 12345.67)}[k]), 6),
                  "trace_top_err_cm": [t["err_cm"] for t in v["traces"] if t], "trace_hits": sum(1 for t in v["traces"] if t),
                  "runtime_move": "not applicable (Static mobility StaticMeshActor rejects runtime moves; delta %r)" % (v["moved_cm"],)}
              for k, v in prec["probes"].items()}
    out = {"actors_max_err_cm": {k: round(max(v), 6) for k, v in errs.items()}, "actors_n": {k: len(v) for k, v in errs.items()},
           "landscape_corner_err_cm": corners, "landscape": {k: prec["landscape"][k] for k in ("loc", "rot", "scale", "components", "border_components")},
           "probes": probes}
    worst = max(max(out["actors_max_err_cm"].values()), max(abs(e) for p in probes.values() for e in p["trace_top_err_cm"]),
                max(p["readback_err_cm"] for p in probes.values()))
    out["gate"] = {"worst_actor_err_cm": worst, "worst_corner_err_cm": max(corners.values()),
                   "status": "PASS" if worst <= TH["actor_pos_err_max_cm"] and max(corners.values()) <= TH["landscape_corner_err_max_cm"] else "FAIL"}
    return out


# ------------------------------------------------------------------------------------------------------------- LOD matrix
def magenta(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    m = (np.minimum(a[..., 0], a[..., 2]) - a[..., 1]) > 60
    return m


CRACK_CLASSES = ("xinyi_seam", "stitch_hole_side", "landscape_component_boundary", "landscape_interior", "chunk_seam", "chunk_interior",
                 "no_reference_hit")


def camera_rays(cam, px, py, w=960, h=540):
    """World (EPSG:3826) rays of SceneCapture pixels: horizontal FOV, look-at rotation (no roll), as captured."""
    P = np.array(ue_to_tm2(cam["loc"][0], cam["loc"][1]) + (cam["loc"][2] / 100.0,))
    T = np.array(ue_to_tm2(cam["target"][0], cam["target"][1]) + (cam["target"][2] / 100.0,))
    f = (T - P) / np.linalg.norm(T - P)
    r = np.cross(f, [0.0, 0.0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    th = math.tan(math.radians(cam["fov"] / 2.0))
    sx = (2.0 * (px + 0.5) / w - 1.0) * th
    sy = (1.0 - 2.0 * (py + 0.5) / h) * th * h / w
    d = f[None, :] + sx[:, None] * r[None, :] + sy[:, None] * u[None, :]
    d /= np.linalg.norm(d, axis=1)[:, None]
    return np.tile(P, (len(px), 1)), d


def surface_z(ref, x, y):
    """Reference terrain height: accepted Landscape (diagonal A) inside the sector, shipped 20 m chunk grid (bilinear) outside."""
    e, n = ref.enu(x, y)
    za, _ = landscape_tri_heights(ref.xin, e, n)
    gx = (x - CELLS_BOX[0]) / 20.0
    gy = (y - CELLS_BOX[1]) / 20.0
    ok = (gx >= 0) & (gy >= 0) & (gx < ref.grid.shape[1] - 1) & (gy < ref.grid.shape[0] - 1)
    i, j = np.clip(np.floor(gy).astype(int), 0, ref.grid.shape[0] - 2), np.clip(np.floor(gx).astype(int), 0, ref.grid.shape[1] - 2)
    u, v = gx - j, gy - i
    G = ref.grid
    zg = G[i, j] * (1 - u) * (1 - v) + G[i, j + 1] * u * (1 - v) + G[i + 1, j] * (1 - u) * v + G[i + 1, j + 1] * u * v
    zg = np.where(ok, zg, np.nan)
    ins = ref.inside(e, n, tol=0.0)
    return np.where(ins, za, zg), e, n


def classify_cracks(ref, cam, xs, ys, max_samples=120):
    """Back-project crack pixels (ray-march, 2 m steps then linear refinement) onto the LOD0 reference and name the feature."""
    if len(xs) > max_samples:
        k = np.linspace(0, len(xs) - 1, max_samples).astype(int)
        xs, ys = xs[k], ys[k]
    o, d = camera_rays(cam, xs.astype(float), ys.astype(float))
    t = np.arange(5.0, 9000.0, 2.0)
    P = o[:, None, :] + t[None, :, None] * d[:, None, :]
    zs, _, _ = surface_z(ref, P[..., 0].ravel(), P[..., 1].ravel())
    zs = zs.reshape(P.shape[:2])
    below = np.nan_to_num(P[..., 2] - zs, nan=1.0) <= 0
    out = Counter()
    x = ref.xin
    for k in range(len(xs)):
        idx = np.argmax(below[k])
        if not below[k, idx]:
            out["no_reference_hit"] += 1
            continue
        if idx > 0:
            a0 = P[k, idx - 1, 2] - zs[k, idx - 1]
            a1 = P[k, idx, 2] - zs[k, idx]
            f = a0 / (a0 - a1) if np.isfinite(a0) and a0 != a1 else 1.0
            q = P[k, idx - 1] + f * (P[k, idx] - P[k, idx - 1])
        else:
            q = P[k, idx]
        e, n = ref.enu(np.array([q[0]]), np.array([q[1]]))
        e, n = float(e[0]), float(n[0])
        if ref.inside(np.array([e]), np.array([n]), tol=0.0)[0]:
            d_in = min(e - x.e0, x.e1 - e, n - x.n0, x.n1 - n)
            if d_in < 6.0:
                out["xinyi_seam"] += 1
                continue
            col, row = (e - x.e0) / x.step, (x.n1 - n) / x.step
            dc = min(col % 126, 126 - col % 126) * x.step
            dr = min(row % 126, 126 - row % 126) * x.step
            out["landscape_component_boundary" if min(dc, dr) < 6.0 else "landscape_interior"] += 1
        else:
            d_out = math.hypot(max(x.e0 - e, 0.0, e - x.e1), max(x.n0 - n, 0.0, n - x.n1))
            if d_out < 6.0:
                out["xinyi_seam"] += 1
            elif d_out < 400.0:
                out["stitch_hole_side"] += 1
            else:
                gx = (q[0] - 304000.0) % 1600.0
                gy = (q[1] - 2760000.0) % 1600.0
                out["chunk_seam" if min(gx, 1600 - gx, gy, 1600 - gy) < 6.0 else "chunk_interior"] += 1
    return {k: int(v) for k, v in out.items() if v}, len(xs)


def lod_matrix(shots, ref, cams):
    rows = []
    for s_ in shots:
        m = magenta(RAW / "img" / s_["file"])
        ys, xs = np.nonzero(m)
        row = dict(s_, crack_px=int(m.sum()), bbox=None if len(xs) == 0 else [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())])
        if len(xs):
            cls, nsamp = classify_cracks(ref, cams[s_["camera"]], xs, ys)
            row["crack_classes_sampled"] = cls
            row["crack_px_est_by_class"] = {k: round(v * len(xs) / nsamp, 1) for k, v in cls.items()}
        rows.append(row)
    agg = defaultdict(lambda: {"cams": 0, "cams_with_crack": 0, "crack_px_total": 0, "crack_px_max": 0, "worst_camera": None,
                               "crack_px_est_by_class": Counter()})
    for r in rows:
        if r["combo"] == "auto_debugcolour":
            continue
        k = (r["stitch"], r["policy"], r["combo"])
        g = agg[k]
        g["cams"] += 1
        g["crack_px_total"] += r["crack_px"]
        for c, v in r.get("crack_px_est_by_class", {}).items():
            g["crack_px_est_by_class"][c] += v
        if r["crack_px"] > 0:
            g["cams_with_crack"] += 1
        if r["crack_px"] > g["crack_px_max"]:
            g["crack_px_max"], g["worst_camera"] = r["crack_px"], r["camera"]
    table = []
    for k, v in sorted(agg.items()):
        v = dict(v)
        v["crack_px_est_by_class"] = {c: round(x, 1) for c, x in sorted(v["crack_px_est_by_class"].items())}
        v["seam_crack_px_est"] = round(sum(x for c, x in v["crack_px_est_by_class"].items() if c in ("xinyi_seam", "stitch_hole_side", "chunk_seam")), 1)
        table.append(dict(stitch=k[0], policy=k[1], combo=k[2], **v))
    return rows, table


# ------------------------------------------------------------------------------------------------------------- flights
def load_memory(raw):
    p = raw / "memory_runtime.csv"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        r = list(csv.DictReader(fh))
    return np.array([[float(x["wall"]), float(x["rss_bytes"]), float(x["private_bytes"])] for x in r])


def flights(raws):
    out = {}
    curves = {}
    files = []
    for raw in raws:
        mem_ = load_memory(raw)
        files += [(raw, mem_, f) for f in sorted((raw / "flights").glob("*.json"))]
    for raw, mem, f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        d["_dir"] = str(raw)
        F = d["frames"]
        if not F:
            out[d["tag"]] = {"frames": 0}
            continue
        dt = np.array([r[1] for r in F])
        cap_frames = set()
        if d["captures"]:
            # the frame AFTER a capture carries the GPU read-back stall; exclude both from timing statistics
            ts = [c["t"] for c in d["captures"]]
            t_acc = np.cumsum(dt) / 1000.0
            for t in ts:
                j = int(np.searchsorted(t_acc, t))
                cap_frames.update({j, j + 1})
        keep = np.array([i not in cap_frames for i in range(len(F))])
        dk = dt[keep]
        med = float(np.median(dk))
        ux, uy = d["dir"]
        sx, sy = ue_to_tm2(d["start_cm"][0], d["start_cm"][1])
        ahead_m = [a / 100.0 for a in d["ahead_cm"]]
        cov = {}
        for j, a in enumerate(ahead_m):
            exp_n = got_n = 0
            first_miss = None
            for r in F:
                s = r[3] + a
                x, y = sx + ux * s, sy - uy * s
                inside = CELLS_BOX[0] <= x <= CELLS_BOX[2] and CELLS_BOX[1] <= y <= CELLS_BOX[3]
                if not inside:
                    continue
                exp_n += 1
                if r[9][j] != "-":
                    got_n += 1
                elif first_miss is None:
                    first_miss = r[3]
            cov["%d" % a] = {"expected_frames": exp_n, "terrain_present_frames": got_n,
                             "presence": round(got_n / exp_n, 4) if exp_n else None, "first_miss_at_s_m": first_miss}
        mrow = {}
        if mem is not None:
            w0, w1 = F[0][0], F[-1][0]
            sel = mem[(mem[:, 0] >= w0) & (mem[:, 0] <= w1)]
            if len(sel):
                mrow = {"rss_mb_min": round(sel[:, 1].min() / 2**20, 1), "rss_mb_max": round(sel[:, 1].max() / 2**20, 1),
                        "private_mb_max": round(sel[:, 2].max() / 2**20, 1), "rss_mb_delta": round((sel[-1, 1] - sel[0, 1]) / 2**20, 1)}
        out[d["tag"]] = {"agl_m": d["agl_m"], "elapsed_s": d["elapsed_s"], "frames": len(F), "timed_frames": int(keep.sum()),
                         "streaming_wait_before_s": d["streaming_wait_s"], "cells_before": d["cells_before"],
                         "dt_ms": {"p50": round(med, 2), "p95": round(pct(dk, 95), 2), "p99": round(pct(dk, 99), 2), "max": round(float(dk.max()), 2)},
                         "hitches_over_2x_median": int((dk > 2 * med).sum()), "hitches_over_100ms": int((dk > 100).sum()),
                         "chunk_actors": [int(min(r[4] for r in F)), int(max(r[4] for r in F))],
                         "cells_activated": [min(r[6] for r in F), max(r[6] for r in F)], "cells_total": F[0][7],
                         "streaming_complete_fraction": round(sum(r[8] for r in F) / len(F), 4),
                         "ground_presence": cov, "memory": mrow, "captures": len(d["captures"])}
        curves[d["tag"]] = d
    return out, curves


# ------------------------------------------------------------------------------------------------------------- evidence images
def tile(path, w=320, h=180, label=None, px=None):
    im = Image.open(path).convert("RGB").resize((w, h), Image.LANCZOS)
    if label:
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, w, 14], fill=(0, 0, 0))
        dr.text((3, 1), label + ("" if px is None else "  crack px=%d" % px), fill=(255, 255, 0) if px else (200, 255, 200))
    return im


def sheet(tiles, cols, path):
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    S = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    for i, t in enumerate(tiles):
        S.paste(t, ((i % cols) * w, (i // cols) * h))
    S.save(path, optimize=True)
    return path.name


def crack_crop(row, path, pad=60):
    im = Image.open(RAW / "img" / row["file"]).convert("RGB")
    x0, y0, x1, y1 = row["bbox"]
    box = (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))
    c = im.crop(box)
    s = max(1, int(480 / max(c.width, 1)))
    c = c.resize((c.width * s, c.height * s), Image.NEAREST)
    c.save(path, optimize=True)
    return path.name


def charts(curves, path):
    """Three stacked panels (PIL, no plotting dependency): frame dt (log), loaded chunk actors, terrain present ahead."""
    tags = [t for t in curves if "captured" not in t]
    cols = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40), (148, 103, 189), (140, 86, 75), (227, 119, 194),
            (127, 127, 127), (188, 189, 34), (23, 190, 207)]
    W, PH, L, R, T = 1200, 230, 70, 260, 30
    im = Image.new("RGB", (W, T + 3 * PH + 40), "white")
    dr = ImageDraw.Draw(im)
    dr.text((L, 8), "UE5.8 PIE, 300 m/s flights over the two 8 km cells - desktop iGPU (Intel UHD 770), NOT mobile", fill="black")
    smax = max(r[3] for t in tags for r in curves[t]["frames"]) / 1000.0
    panels = [("frame dt ms (log 10..1000)", lambda r: math.log10(max(r[1], 10.0)), 1.0, 3.0),
              ("loaded chunk actors (0..50)", lambda r: r[4], 0.0, 50.0),
              ("terrain present 0/0.5/1/2 km ahead (0..4)", lambda r: sum(1 for ch in r[9][:4] if ch != "-"), 0.0, 4.0)]
    for pi, (name, fn, lo, hi) in enumerate(panels):
        y0 = T + pi * PH
        dr.rectangle([L, y0 + 10, W - R, y0 + PH - 20], outline=(120, 120, 120))
        dr.text((L, y0 - 2), name, fill="black")
        for ti, t in enumerate(tags):
            F = curves[t]["frames"]
            pts = [(L + (W - R - L) * (r[3] / 1000.0) / smax, y0 + PH - 20 - (PH - 30) * (min(max(fn(r), lo), hi) - lo) / (hi - lo)) for r in F]
            dr.line(pts, fill=cols[ti % len(cols)], width=1)
            if pi == 0:
                dr.text((W - R + 10, T + 14 * ti), t, fill=cols[ti % len(cols)])
    dr.text((L, T + 3 * PH + 5), "x: distance flown 0..%.1f km (path crosses cell seam N 2,768,000 and the Xinyi sector)" % smax, fill="black")
    im.save(path, optimize=True)
    return path.name


def micro_traces():
    T = json.loads((GATE / "gate_inputs.json").read_text(encoding="utf-8"))["micro_traces"]
    H = json.loads((RAW2 / "micro_traces.json").read_text(encoding="utf-8"))["hits"]
    tab = defaultdict(Counter)
    for t, h in zip(T, H):
        tab["%s %+.4f" % (t["set"].split("_")[1], t["off"])][h[1] if h else "miss"] += 1
    off_line = [(t, h) for t, h in zip(T, H) if t["off"] != 0.0]
    return {"samples_per_edge_offset": 400, "offsets_m": sorted({t["off"] for t in T}),
            "table": {k: dict(v) for k, v in sorted(tab.items())},
            "all_offline_rays_hit": all(h is not None for _, h in off_line),
            "offline_wrong_actor": sum(1 for t, h in off_line if h and h[1] != ("L" if t["off"] < 0 else "S2")),
            "exact_line_misses": sum(1 for t, h in zip(T, H) if t["off"] == 0.0 and h is None),
            "exact_line_rays": sum(1 for t in T if t["off"] == 0.0)}


def main():
    inp = json.loads((GATE / "gate_inputs.json").read_text(encoding="utf-8"))
    run = json.loads((RAW / "runtime.json").read_text(encoding="utf-8"))
    run2 = json.loads((RAW2 / "runtime.json").read_text(encoding="utf-8"))
    tr = json.loads((RAW / "traces.json").read_text(encoding="utf-8"))
    prec = json.loads((RAW / "precision.json").read_text(encoding="utf-8"))
    shots = json.loads((RAW / "lod_matrix.json").read_text(encoding="utf-8"))
    EVID.mkdir(parents=True, exist_ok=True)
    ref = Reference()
    micro_inp = inp["micro_traces"]
    micro_hits = json.loads((RAW2 / "micro_traces.json").read_text(encoding="utf-8"))["hits"]
    col = collision(inp, tr, micro_inp, micro_hits, ref)
    pre = precision(prec)
    rows, table = lod_matrix(shots, ref, {c["name"]: c for c in inp["cameras"]})
    fl, curves = flights([RAW, RAW2])
    micro = micro_traces()
    col["micro_offset_traces"] = micro
    exact_only = col["gate"]["misses"] == col["gate"]["misses_on_exact_boundary"] and micro["all_offline_rays_hit"]
    g = col["gate"]
    if g["status"] == "FAIL" and g["wrong_actor"] == 0 and g["mesh_dz_max_m"] <= TH["mesh_dz_max_m"] and             g["landscape_dz_max_m"] <= TH["landscape_dz_max_m"] and g["seam_step_max_m"] <= TH["seam_step_max_m"] and exact_only:
        g["status"] = "FAIL (exact-boundary rays only)"
        g["note"] = ("every miss is a ray placed EXACTLY on the shared Landscape/stitch boundary line; all rays offset by >= 0.5 mm "
                     "hit (micro_offset_traces) -> no gap >= 0.5 mm; zero-width coincident-boundary degeneracy, see doc")

    # LOD gates
    def combo_rows(stitch, policy, pred):
        return [t for t in table if t["stitch"] == stitch and t["policy"] == policy and pred(t["combo"])]
    matched = lambda c: c == "auto" or c.split("_")[1][1:] == c.split("_")[2][1:]   # stitch LOD == chunk LOD
    prod = [t for t in table if t["stitch"] == "v2" and (t["policy"] == "border0" or t["combo"].startswith("L0") or t["combo"] == "auto") and matched(t["combo"])]
    prod = [t for t in prod if not (t["combo"] == "auto" and t["policy"] == "none") and not (t["combo"].startswith("L") and not t["combo"].startswith("L0") and t["policy"] == "none")]
    lod_gate = {
        "candidate_policy": "stitch v2 + Xinyi border landscape components forced to LOD0 + stitch mesh LOD == neighbouring chunk LOD",
        "candidate_policy_rows": prod,
        "candidate_policy_crack_px": sum(t["crack_px_total"] for t in prod),
        "mixed_stitch_chunk_lod_rows": [t for t in table if t["combo"] != "auto" and not matched(t["combo"])],
        "landscape_lod_without_policy_rows": [t for t in table if t["policy"] == "none" and t["combo"] != "auto" and not t["combo"].startswith("L0")],
        "v1_rows_with_cracks": [t for t in table if t["stitch"] == "v1" and t["crack_px_total"] > 0],
        "auto_lod_rows": [t for t in table if t["combo"] == "auto"],
    }
    by_cls = Counter()
    for t in prod:
        by_cls.update(t["crack_px_est_by_class"])
    lod_gate["candidate_policy_crack_px_est_by_class"] = {k: round(v, 1) for k, v in sorted(by_cls.items())}
    lod_gate["candidate_policy_seam_crack_px_est"] = round(sum(t["seam_crack_px_est"] for t in prod), 1)
    lod_gate["status"] = ("PASS (candidate policy only)" if lod_gate["candidate_policy_crack_px"] <= TH["crack_px_max"] else
                          "FAIL" + (" (no crack located on the Xinyi / stitch / chunk seams; the remaining cracks sit inside the accepted "
                                    "Landscape at component borders between forced-LOD0 border components and coarser interior components)"
                                    if lod_gate["candidate_policy_seam_crack_px_est"] == 0 else ""))

    # evidence sheets
    ev = {}
    byname = {r["file"]: r for r in rows}
    cams = [c["name"] for c in inp["cameras"]]
    for cam in ("edge_south_250m", "edge_east_250m", "corner_SE", "corner_NW"):
        tl = []
        for stitch, policy, combo in (("v2", "none", "auto"), ("v2", "border0", "auto"), ("v2", "none", "L3_T0_C0"), ("v2", "border0", "L3_T0_C0"),
                                      ("v1", "none", "L0_T2_C2"), ("v2", "none", "L0_T2_C2"), ("v2", "none", "L0_T0_C2"), ("v2", "border0", "L3_T3_C3")):
            fn = "lod_%s_%s_%s_%s.png" % (stitch, policy, combo, cam)
            if fn in byname:
                tl.append(tile(RAW / "img" / fn, label="%s %s %s" % (stitch, policy, combo), px=byname[fn]["crack_px"]))
        if tl:
            ev["lod_sheet_" + cam] = sheet(tl, 4, EVID / ("lod_matrix_%s.png" % cam))
    worst = sorted([r for r in rows if r["crack_px"] > 0 and r["combo"] != "auto_debugcolour"], key=lambda r: -r["crack_px"])
    picks = {}
    for r in worst:
        k = (r["stitch"], r["policy"], r["combo"])
        if k not in picks:
            picks[k] = r
    keys = [("v2", "none", "L0_T0_C2"), ("v2", "none", "L3_T0_C0"), ("v1", "none", "L3_T0_C0"), ("v1", "border0", "L3_T4_C4"),
            ("v2", "border0", "L3_T0_C0"), ("v2", "none", "auto"), ("v2", "border0", "auto")]
    for k in keys:
        if k in picks:
            r = picks[k]
            ev["crack_crop_%s_%s_%s" % k] = crack_crop(r, EVID / ("crack_%s_%s_%s_%s.png" % (k[0], k[1], k[2], r["camera"])))
    tl = [tile(RAW / "img" / ("debug_v2_auto_%s.png" % c), label="v2 auto (stitch red) " + c) for c in cams if (RAW / "img" / ("debug_v2_auto_%s.png" % c)).exists()]
    if tl:
        ev["debug_colour_sheet"] = sheet(tl, 4, EVID / "seam_debug_colour_views.png")
    alt = [s for s in run["steps"] if s["name"] == "altitude_series"]
    if alt:
        tl = [tile(RAW / "img" / s["file"], label="%s %s" % (s["camera"], s["policy"])) for s in alt[0]["shots"]]
        ev["altitude_sheet"] = sheet(tl, 5, EVID / "altitude_series_auto_lod.png")
    for tag, d in curves.items():
        if d["captures"]:
            caps = d["captures"][::max(1, len(d["captures"]) // 12)][:12]
            tl = [tile(Path(d["_dir"]) / "img" / c["file"], label="%s t=%.0fs s=%.1fkm" % (tag.split("_agl")[0], c["t"], c["s_m"] / 1000)) for c in caps]
            ev["flight_" + tag] = sheet(tl, 4, EVID / ("flight_%s.png" % tag))
    ev["flight_chart"] = charts(curves, EVID / "flight_frame_streaming.png")

    # streaming gates
    conf = {k: v for k, v in fl.items() if k.startswith("configured") and "captured" not in k}
    tmpl = {k: v for k, v in fl.items() if k.startswith("template") and "captured" not in k}

    def presence_ok(f):
        return all((f["ground_presence"].get(str(a), {}).get("presence") or 0) >= 1.0 for a in TH["ground_presence_ahead_m"]
                   if f["ground_presence"].get(str(a), {}).get("expected_frames"))
    stream_gate = {"configured_grid_1600m_8km": {"flights": list(conf), "terrain_presence_ok": all(presence_ok(f) for f in conf.values()),
                                                  "hitches_over_100ms": {k: v["hitches_over_100ms"] for k, v in conf.items()}},
                   "template_default_grid_252m_768m": {"flights": list(tmpl), "terrain_presence_ok": all(presence_ok(f) for f in tmpl.values()),
                                                        "hitches_over_100ms": {k: v["hitches_over_100ms"] for k, v in tmpl.items()}}}
    stream_gate["status"] = ("PASS (desktop PIE streaming of 2 cells; mobile NOT TESTED)" if stream_gate["configured_grid_1600m_8km"]["terrain_presence_ok"]
                             else "FAIL")
    stream_gate["template_grid_expected_failure_reproduced"] = not stream_gate["template_default_grid_252m_768m"]["terrain_presence_ok"]

    res = {"schema": "ntw.runtime_gate.v1", "engine": "Unreal Engine 5.8 (installed build), UnrealEditor.exe PIE, D3D12",
           "hardware": "i7-12700, Intel UHD Graphics 770 (integrated), 15.6 GB RAM - desktop development PC, NOT mobile",
           "level": "/Game/NTWGate/L_NTWGate (isolated project D:/Users/EDDY/UEIsolated/NTWRuntimeGate; never the formal project)",
           "thresholds": TH,
           "runs": {"full": {"status": run.get("status"), "seconds": run.get("seconds"),
                             "note": "configured-grid session COMPLETED (pie_ended); the template-grid session then aborted on the strict actor "
                                     "census (only 4/50 chunks inside the 768 m range) - re-run in 'followup'",
                             "error_tail": (run.get("error") or "")[-300:]},
                    "followup": {"status": run2.get("status"), "seconds": run2.get("seconds")}},
           "configured_session_completed": any(s["name"] == "pie_ended" and s.get("session") == "configured" for s in run["steps"]),
           "pie_sessions": [s for r_ in (run, run2) for s in r_["steps"] if s["name"] in ("session_grid", "pie_started", "pie_ended", "warmup")],
           "collision": col, "precision": pre, "lod": {"table": table, "gate": lod_gate}, "flights": fl, "streaming_gate": stream_gate,
           "evidence": ev, "not_tested": ["mobile hardware / packaged build frame time and memory", "HLOD", "Nanite terrain", "vegetation",
                                          "network", "more than two 8 km cells"]}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"collision": col["gate"], "precision": pre["gate"], "lod": {k: lod_gate[k] for k in ("status", "candidate_policy_crack_px")},
                      "streaming": {k: stream_gate[k] for k in ("status", "template_grid_expected_failure_reproduced")}}, indent=1))


if __name__ == "__main__":
    main()
