"""Host-side inputs for the Phase 2B UE runtime gate (positions in UE cm; UE origin = (296000, 2760000) EPSG:3826).

  * collision trace sets with EXPECTED heights:
      - the 4 Xinyi edges (every 2 m) at perpendicular offsets -2/-0.5/-0.05 (inside, accepted Landscape) and +0.05/+0.5/+2 m
        (outside, stitch); the 4 corners (+-3 m grid, 0.25 m); the cell seam N = 2,768,000 and two chunk seams (+-0.05 m);
        interior DEM nodes (exact official heights at chunk vertices)
      - expected inside = accepted R16 bilinear; expected outside / chunks = the SHIPPED meshes (vertical ray cast)
  * cameras for the LOD-combination crack matrix and the altitude series
  * terrain-following flight paths (150 / 300 / 600 / 800 m AGL) crossing the cell seam and the Xinyi sector at 300 m/s
Writes D:/Users/EDDY/UEIsolated/gate_out/gate_inputs.json and a copy of the expectations next to it.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
NTW = HERE.parent
REPO = NTW.parents[1]
sys.path.insert(0, str(NTW))
sys.path.insert(0, str(REPO / "tools/compiler"))
import build_terrain_cells as btc  # noqa: E402
import frame  # noqa: E402

OUT = Path("D:/Users/EDDY/UEIsolated/gate_out/gate_inputs.json")
ORIGIN = (296000.0, 2760000.0)
# terrain run whose SHIPPED meshes define the expected heights (Phase 2B-C: the fixed-hole run joint_ue_local_v3)
RUN = REPO / "data/generated/ntw/terrain" / os.environ.get("ACW_GATE_TERRAIN_RUN_NAME", "joint_ue_local")


def ue(e, n, z=0.0):
    return [(e - ORIGIN[0]) * 100.0, -(n - ORIGIN[1]) * 100.0, z * 100.0]


def load_world_mesh(path, sw):
    sc = trimesh.load_scene(io.BytesIO(path.read_bytes()), file_type="glb", process=False)
    m = list(sc.geometry.values())[0]
    v = np.asarray(m.vertices, float)
    W = np.column_stack([sw[0] + v[:, 0], sw[1] - v[:, 2], v[:, 1]])
    return trimesh.Trimesh(W, np.asarray(m.faces), process=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    rep = json.loads((RUN / "terrain.report.json").read_text(encoding="utf-8"))
    sw = {(c["cell"], c["chunk"], c["lod"]): c["sw_epsg3826"] for c in rep["chunks"]}
    meshes = [load_world_mesh(RUN / "chunks" / c / f"{ch}_lod0.glb", sw[(c, ch, 0)]) for (c, ch, l) in sw if l == 0 and ch.startswith("ch")]
    stitch = load_world_mesh(RUN / "chunks" / "C+0038+0346" / "xinyi_stitch_lod0.glb", sw[("C+0038+0346", "xinyi_stitch", 0)])
    nsurf = next(c["triangles_terrain"] for c in rep["chunks"] if c["chunk"] == "xinyi_stitch" and c["lod"] == 0)
    stitch = trimesh.Trimesh(stitch.vertices, stitch.faces[:nsurf], process=False)
    world = trimesh.util.concatenate(meshes + [stitch])
    xin = btc.XinyiLandscape()

    def mesh_z(e, n):
        o = np.column_stack([e, n, np.full(len(e), 5000.0)])
        d = np.tile([0, 0, -1.0], (len(e), 1))
        loc, ri, _ = world.ray.intersects_location(o, d, multiple_hits=False)
        z = np.full(len(e), np.nan)
        if len(ri):
            z[ri] = np.asarray(loc).reshape(-1, 3)[:, 2]
        return z

    traces = []
    sides = {"south": ((xin.e0, xin.n0), (xin.e1, xin.n0), (0, -1)), "east": ((xin.e1, xin.n0), (xin.e1, xin.n1), (1, 0)),
             "north": ((xin.e1, xin.n1), (xin.e0, xin.n1), (0, 1)), "west": ((xin.e0, xin.n1), (xin.e0, xin.n0), (-1, 0))}
    for side, ((ea, na), (eb, nb), (ox, oy)) in sides.items():
        t = np.linspace(0, 1, 1251)[1:-1]
        e0, n0 = ea + t * (eb - ea), na + t * (nb - na)
        for off in (-2.0, -0.5, -0.05, 0.05, 0.5, 2.0):
            e, n = e0 + off * ox, n0 + off * oy                      # ENU; positive offset = outside the sector
            x, y = btc.xinyi_enu_to_tm2(e, n)
            exp = xin.height_enu(e, n) if off < 0 else mesh_z(x, y)
            for i in range(len(e)):
                traces.append({"set": f"xinyi_{side}", "off": off, "s": float(t[i]), "ue": ue(x[i], y[i]), "exp_z": None if not np.isfinite(exp[i]) else float(exp[i]),
                               "expect": "xinyi_landscape" if off < 0 else "stitch"})
    corners = {"SW": (xin.e0, xin.n0), "SE": (xin.e1, xin.n0), "NE": (xin.e1, xin.n1), "NW": (xin.e0, xin.n1)}
    for cname, (ce, cn) in corners.items():
        g = np.arange(-3.0, 3.0001, 0.25)
        GE, GN = np.meshgrid(ce + g, cn + g)
        e, n = GE.ravel(), GN.ravel()
        x, y = btc.xinyi_enu_to_tm2(e, n)
        inside = (e > xin.e0) & (e < xin.e1) & (n > xin.n0) & (n < xin.n1)
        exp = np.where(inside, xin.height_enu(e, n, tol_m=0.0), mesh_z(x, y))
        for i in range(len(e)):
            traces.append({"set": f"corner_{cname}", "off": None, "ue": ue(x[i], y[i]), "exp_z": None if not np.isfinite(exp[i]) else float(exp[i]),
                           "expect": "xinyi_landscape" if inside[i] else "stitch"})
    seams = [("cell_seam_N2768000", lambda s: (304000 + s, 2768000.0)), ("chunk_seam_E305600", lambda s: (305600.0, 2760000 + s)),
             ("chunk_seam_N2763200", lambda s: (304000 + s, 2763200.0))]
    for name, f in seams:
        s = np.arange(10.0, 8000.0 if "N" in name.split("_")[-1] else 16000.0, 2.0)
        for d in (-0.05, 0.05):
            pts = np.array([f(v) for v in s])
            if name.startswith("chunk_seam_E"):
                pts[:, 0] += d
            else:
                pts[:, 1] += d
            exp = mesh_z(pts[:, 0], pts[:, 1])
            for i in range(len(pts)):
                traces.append({"set": name, "off": d, "ue": ue(pts[i, 0], pts[i, 1]), "exp_z": None if not np.isfinite(exp[i]) else float(exp[i]),
                               "expect": "chunk_or_stitch"})
    rng = np.random.default_rng(20261013)
    nodes = []
    for m in meshes:
        idx = rng.choice(len(m.vertices), 40, replace=False)
        nodes += [m.vertices[i] for i in idx if m.vertices[i][2] > -100]
    for (e, n, z) in nodes:
        traces.append({"set": "dem_nodes", "off": None, "ue": ue(e, n), "exp_z": float(z), "expect": "chunk_vertex"})

    # cameras (looking at edge midpoints from outside, grazing; plus corners and the cell seam)
    cams = []
    for side, ((ea, na), (eb, nb), (ox, oy)) in sides.items():
        em, nm = (ea + eb) / 2, (na + nb) / 2
        for dist, agl in ((250.0, 40.0), (900.0, 150.0)):
            tx, ty = btc.xinyi_enu_to_tm2(np.array([em]), np.array([nm]))
            cx, cy = btc.xinyi_enu_to_tm2(np.array([em + ox * dist]), np.array([nm + oy * dist]))
            gz = float(xin.height_enu(np.array([em]), np.array([nm]))[0])
            cams.append({"name": f"edge_{side}_{int(dist)}m", "loc": ue(cx[0], cy[0], gz + agl), "target": ue(tx[0], ty[0], gz), "fov": 50.0})
    for cname, (ce, cn) in corners.items():
        sx = 1 if ce == xin.e0 else -1
        sy = 1 if cn == xin.n0 else -1
        cx, cy = btc.xinyi_enu_to_tm2(np.array([ce - sx * 300]), np.array([cn - sy * 300]))
        tx, ty = btc.xinyi_enu_to_tm2(np.array([ce]), np.array([cn]))
        gz = float(xin.height_enu(np.array([ce]), np.array([cn]), tol_m=1.0)[0])
        cams.append({"name": f"corner_{cname}", "loc": ue(cx[0], cy[0], gz + 60), "target": ue(tx[0], ty[0], gz), "fov": 50.0})
    cams.append({"name": "cell_seam_low", "loc": ue(309000, 2766500, 260), "target": ue(309000, 2768000, 40), "fov": 50.0})
    alt = []
    for agl in (150, 300, 600, 800, 3000):
        alt.append({"name": f"alt_{agl}m", "loc": ue(303500, 2764500, agl + 20), "target": ue(306800, 2769800, 20), "fov": 60.0})

    # flight paths: south edge of cell B -> north across the cell seam and the Xinyi sector, terrain-following AGL
    p0, p1 = np.array([305200.0, 2760400.0]), np.array([307400.0, 2775600.0])
    L = float(np.linalg.norm(p1 - p0))
    s = np.arange(0, L + 1, 50.0)
    pts = p0 + np.outer(s / L, p1 - p0)
    gz = mesh_z(pts[:, 0], pts[:, 1])
    gz = np.where(np.isfinite(gz), gz, np.nanmax(gz))
    win = 1200 // 50
    env = np.array([gz[max(0, i - win):i + win + 1].max() for i in range(len(gz))])   # +-1.2 km terrain envelope
    paths = {}
    for agl in (150, 300, 600, 800):
        z = env + agl
        paths[str(agl)] = [ue(e, n, zz) for (e, n), zz in zip(pts, z)]
    # micro-offset set (follow-up of the full run: 26 rays EXACTLY on the north boundary line missed both actors): 400 samples
    # per edge at +-0.5 / 1 / 5 mm and exactly 0 - separates an exact-line degeneracy from a real sliver gap
    micro = []
    for side, ((ea, na), (eb, nb), (ox, oy)) in sides.items():
        t = np.linspace(0, 1, 402)[1:-1]
        e0, n0 = ea + t * (eb - ea), na + t * (nb - na)
        for off in (-0.005, -0.001, -0.0005, 0.0, 0.0005, 0.001, 0.005):
            x, y = btc.xinyi_enu_to_tm2(e0 + off * ox, n0 + off * oy)
            for i in range(len(t)):
                micro.append({"set": f"micro_{side}", "off": off, "s": float(t[i]), "ue": ue(x[i], y[i]), "exp_z": None,
                              "expect": "xinyi_landscape" if off < 0 else ("either" if off == 0 else "stitch")})
    # ---- Phase 2B-C: high-speed sweeps across the boundary (300 m/s = 10 m / 5 m per frame at 30 / 60 fps)
    # each segment STARTS above and ENDS below the exact local surface (Landscape triangulation inside, shipped mesh outside),
    # so a continuous collision surface MUST report a blocking hit; crossing points lie EXACTLY on the boundary line
    from analyse_runtime import landscape_tri_heights

    def surf_enu(e, n):
        e, n = np.atleast_1d(e), np.atleast_1d(n)
        x, y = btc.xinyi_enu_to_tm2(e, n)
        ins = (e > xin.e0) & (e < xin.e1) & (n > xin.n0) & (n < xin.n1)
        za, _ = landscape_tri_heights(xin, e, n)
        zm = mesh_z(x, y)
        return np.where(ins, za, zm), x, y
    sweeps = []
    rngs = np.random.default_rng(7)
    for side, ((ea, na), (eb, nb), (ox_, oy_)) in sides.items():
        for t_ in np.sort(rngs.uniform(0.02, 0.98, 40)):
            ce, cn = ea + t_ * (eb - ea), na + t_ * (nb - na)
            tx, ty = (eb - ea) / 2500.0, (nb - na) / 2500.0       # along-edge unit
            for dname, (dx, dy) in (("in", (-ox_, -oy_)), ("out", (ox_, oy_)), ("in45", (-ox_ + tx, -oy_ + ty)), ("out45", (ox_ + tx, oy_ + ty))):
                L_ = math.hypot(dx, dy)
                dx, dy = dx / L_, dy / L_
                for Lh in (10.0, 5.0):
                    for prof, (above, below) in (("steep", (0.5, 1.0)), ("grazing", (0.2, 0.2))):
                        se, sn, ee, en = ce - dx * Lh / 2, cn - dy * Lh / 2, ce + dx * Lh / 2, cn + dy * Lh / 2
                        z2, x2, y2 = surf_enu(np.array([se, ee]), np.array([sn, en]))
                        if not np.isfinite(z2).all():
                            continue
                        for r_ in (0.0, 0.05, 0.5):
                            sweeps.append({"set": side, "dir": dname, "len_m": Lh, "profile": prof, "radius_m": r_, "t": float(t_),
                                           "start": ue(x2[0], y2[0], z2[0] + above + r_), "end": ue(x2[1], y2[1], z2[1] - below)})
    for cname, (ce, cn) in corners.items():
        for ang in range(0, 360, 45):
            dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            for Lh in (10.0, 5.0):
                for prof, (above, below) in (("steep", (0.5, 1.0)), ("grazing", (0.2, 0.2))):
                    se, sn, ee, en = ce - dx * Lh / 2, cn - dy * Lh / 2, ce + dx * Lh / 2, cn + dy * Lh / 2
                    z2, x2, y2 = surf_enu(np.array([se, ee]), np.array([sn, en]))
                    if not np.isfinite(z2).all():
                        continue
                    for r_ in (0.0, 0.05, 0.5):
                        sweeps.append({"set": "corner_" + cname, "dir": "a%d" % ang, "len_m": Lh, "profile": prof, "radius_m": r_, "t": 0.0,
                                       "start": ue(x2[0], y2[0], z2[0] + above + r_), "end": ue(x2[1], y2[1], z2[1] - below)})
    # physics drop probes: 6 points exactly on each edge line + the 4 corners
    drops = []
    for side, ((ea, na), (eb, nb), _o) in sides.items():
        for t_ in (0.1, 0.25, 0.4, 0.55, 0.7, 0.9):
            ce, cn = ea + t_ * (eb - ea), na + t_ * (nb - na)
            z1, x1, y1 = surf_enu(np.array([ce]), np.array([cn]))
            zz = float(xin.height_enu(np.array([ce]), np.array([cn]), tol_m=0.01)[0])
            drops.append({"set": side, "t": t_, "ue_xy": ue(x1[0], y1[0])[:2], "surface_z_m": zz})
    for cname, (ce, cn) in corners.items():
        x1, y1 = btc.xinyi_enu_to_tm2(np.array([ce]), np.array([cn]))
        zz = float(xin.height_enu(np.array([ce]), np.array([cn]), tol_m=0.01)[0])
        drops.append({"set": "corner_" + cname, "t": 0.0, "ue_xy": ue(x1[0], y1[0])[:2], "surface_z_m": zz})
    # controls: the same along-edge positions 1 m INSIDE (accepted Landscape) and 1 m OUTSIDE (stitch)
    drops_in, drops_out = [], []
    for side, ((ea, na), (eb, nb), (ox_, oy_)) in sides.items():
        for t_ in (0.1, 0.25, 0.4, 0.55, 0.7, 0.9):
            ce, cn = ea + t_ * (eb - ea), na + t_ * (nb - na)
            for lst, off in ((drops_in, -1.0), (drops_out, 1.0)):
                e_, n_ = ce + off * ox_, cn + off * oy_
                z1, x1, y1 = surf_enu(np.array([e_]), np.array([n_]))
                lst.append({"set": side, "t": t_, "off_m": off, "ue_xy": ue(x1[0], y1[0])[:2], "surface_z_m": float(z1[0])})
    for cname, (ce, cn) in corners.items():
        sx = 1 if ce == xin.e0 else -1
        sy = 1 if cn == xin.n0 else -1
        for lst, off in ((drops_in, -1.0), (drops_out, 1.0)):
            e_, n_ = ce - off * sx, cn - off * sy
            z1, x1, y1 = surf_enu(np.array([e_]), np.array([n_]))
            lst.append({"set": "corner_" + cname, "t": 0.0, "off_m": off, "ue_xy": ue(x1[0], y1[0])[:2], "surface_z_m": float(z1[0])})
    # automatic-LOD dolly paths: from 120 m to 7 km out and 40 m to 2.5 km up, looking at an edge / corner point
    dolly = []
    for name, (te, tn, ue_, un_) in (("south", ((xin.e0 + xin.e1) / 2, xin.n0, 0, -1)), ("east", (xin.e1, (xin.n0 + xin.n1) / 2, 1, 0)),
                                     ("north", ((xin.e0 + xin.e1) / 2, xin.n1, 0, 1)), ("west", (xin.e0, (xin.n0 + xin.n1) / 2, -1, 0)),
                                     ("corner_SE", (xin.e1, xin.n0, 0.7071, -0.7071)), ("corner_NW", (xin.e0, xin.n1, -0.7071, 0.7071))):
        gz_d = float(xin.height_enu(np.array([te]), np.array([tn]), tol_m=1.0)[0])
        tx_, ty_ = btc.xinyi_enu_to_tm2(np.array([te]), np.array([tn]))
        steps = []
        for f_ in np.linspace(0, 1, 30):
            dist = 120.0 * (7000.0 / 120.0) ** f_
            alt_d = 40.0 * (2500.0 / 40.0) ** f_
            cx_, cy_ = btc.xinyi_enu_to_tm2(np.array([te + ue_ * dist]), np.array([tn + un_ * dist]))
            steps.append({"loc": ue(cx_[0], cy_[0], gz_d + alt_d), "dist_m": round(dist, 1), "alt_m": round(alt_d, 1)})
        dolly.append({"name": name, "target": ue(tx_[0], ty_[0], gz_d), "steps": steps, "fov": 50.0})
    inp = {"origin_epsg3826": ORIGIN, "terrain_run": RUN.name, "traces": traces, "micro_traces": micro, "sweeps": sweeps, "drops": drops, "drops_in": drops_in, "drops_out": drops_out,
           "dolly": dolly, "cameras": cams, "altitude_cameras": alt, "flight": {
        "speed_mps": 300.0, "length_m": L, "paths": paths, "terrain_profile_m": gz.tolist(), "envelope_m": env.tolist()},
        "lod_matrix": [["auto", None, None], ["L0_S0", 0, 0], ["L0_S2", 0, 2], ["L0_S4", 0, 4], ["L1_S0", 1, 0], ["L2_S0", 2, 0],
                       ["L3_S0", 3, 0], ["L2_S2", 2, 2], ["L3_S4", 3, 4]],
        "far_offset_test_cm": [11000000.0, -11000000.0]}
    args.out.write_text(json.dumps(inp), encoding="utf-8")
    print(args.out, len(traces), "traces", len(sweeps), "sweeps", len(drops), "drops", len(cams), "cams", {k: len(v) for k, v in paths.items()}, "path m", round(L))


if __name__ == "__main__":
    main()
