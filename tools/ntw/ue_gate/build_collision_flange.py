"""Phase 2B-C: collision-only flange along the accepted Xinyi Landscape / stitch boundary (review #5501430227 P0 #1).

The PR #25 runtime gate found that rays placed EXACTLY on the shared boundary line hit neither the Landscape heightfield nor
the stitch (562 / 1,600 exact-line micro rays; every ray >= 0.5 mm off the line hit). The flange removes the coincident
boundary for physics only: a strip of width 2w centred on the 2,520 accepted edge vertices, w into the Landscape (heights =
the engine's Landscape triangulation, quad diagonal A, measured in PR #25) and w onto the stitch (heights = the shipped
stitch LOD0 surface, vertical ray). Corners use the shrunk / expanded rectangle (diagonal offsets). It is never rendered.
Writes chunks/C+0038+0346/xinyi_flange_w{cm}.glb (identity node, stitch origin) into the terrain run + a report.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
NTW = HERE.parent
REPO = NTW.parents[1]
sys.path.insert(0, str(NTW))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools/compiler"))
import build_terrain_cells as btc  # noqa: E402
from analyse_runtime import landscape_tri_heights  # noqa: E402


def enu_ring(xin):
    """The accepted edge vertices in ENU, CCW from the SW corner (south, east, north, west); 630 per side."""
    n = xin.n - 1
    st = xin.step
    s = [(xin.e0 + i * st, xin.n0) for i in range(n)]
    e = [(xin.e1, xin.n0 + i * st) for i in range(n)]
    no = [(xin.e1 - i * st, xin.n1) for i in range(n)]
    w = [(xin.e0, xin.n1 - i * st) for i in range(n)]
    return np.array(s + e + no + w)


def offsets(xin, R, w):
    """Inner (into the Landscape) and outer (onto the stitch) offset points; corners offset diagonally."""
    inn, out = R.copy(), R.copy()
    for i, (e, n) in enumerate(R):
        dx = (1 if abs(e - xin.e0) < 1e-6 else -1 if abs(e - xin.e1) < 1e-6 else 0)
        dy = (1 if abs(n - xin.n0) < 1e-6 else -1 if abs(n - xin.n1) < 1e-6 else 0)
        inn[i] = (e + dx * w, n + dy * w)
        out[i] = (e - dx * w, n - dy * w)
    return inn, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="joint_ue_local_v3")
    ap.add_argument("--widths-m", type=float, nargs="+", default=[0.10, 0.05])
    ap.add_argument("--apron", action="store_true", help="also write the RENDER apron: exact strip of +-0.5 m sunk 0.02 m (no collision)")
    a = ap.parse_args()
    run = REPO / "data/generated/ntw/terrain" / a.run
    rep = json.loads((run / "terrain.report.json").read_text(encoding="utf-8"))
    st = next(c for c in rep["chunks"] if c["chunk"] == "xinyi_stitch" and c["lod"] == 0)
    ox, oy = st["sw_epsg3826"]
    xin = btc.XinyiLandscape()
    R = enu_ring(xin)
    P, Pz, _ = xin.edge_ring(every=1)
    x, y = btc.xinyi_enu_to_tm2(R[:, 0], R[:, 1])
    dev = float(np.hypot(x - P[:, 0], y - P[:, 1]).max())
    if dev > 1e-6:
        raise SystemExit(f"FAIL: ENU ring does not reproduce the accepted edge ring ({dev} m)")
    sc = trimesh.load_scene(io.BytesIO((run / "chunks" / "C+0038+0346" / "xinyi_stitch_lod0.glb").read_bytes()), file_type="glb", process=False)
    m = list(sc.geometry.values())[0]
    v = np.asarray(m.vertices, float)
    surf = trimesh.Trimesh(np.column_stack([v[:, 0] + ox, -v[:, 2] + oy, v[:, 1]]), np.asarray(m.faces)[:st["triangles_terrain"]], process=False)
    out_rep = {"run": a.run, "origin_epsg3826": [ox, oy], "edge_vertices": len(R), "flanges": {}}
    import shapely
    # source triangles: the engine's Landscape triangulation (quad diagonal A) of the border quad ring, and the shipped stitch LOD0
    # surface within 10 m of the edge. The flange is these triangles CLIPPED to the strip -> coplanar with both (float precision).
    n_ = xin.n
    srcs = []
    for r in range(n_ - 1):
        for c in range(n_ - 1):
            if not (r in (0, n_ - 2) or c in (0, n_ - 2)):
                continue
            q = [(c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1)]
            for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
                e = np.array([xin.e0 + cc * xin.step for cc, rr in tri])
                nn = np.array([xin.n1 - rr * xin.step for cc, rr in tri])
                x, y = btc.xinyi_enu_to_tm2(e, nn)
                srcs.append(("L", np.column_stack([x, y, [xin.h[rr, cc] for cc, rr in tri]])))
    poly = shapely.Polygon(P)
    sv = np.asarray(surf.vertices)
    tris = shapely.polygons(sv[surf.faces][:, :, :2])
    near = shapely.distance(tris, poly.exterior) < 0.5        # every stitch triangle that reaches within 0.5 m of the edge
    for f in np.asarray(surf.faces)[near]:
        srcs.append(("S", sv[f]))
    jobs = [(w, f"xinyi_flange_w{int(round(w * 100)):02d}", 0.0) for w in a.widths_m]
    if a.apron:
        jobs.append((0.5, "xinyi_apron_w50", 0.02))
    for w, name, sink in jobs:
        strip_in = shapely.difference(poly, shapely.buffer(poly, -w, join_style="mitre"))
        strip_out = shapely.difference(shapely.buffer(poly, w, join_style="mitre"), poly)
        shapely.prepare(strip_in)
        shapely.prepare(strip_out)
        verts, vidx, F = [], {}, []
        n_src = {"L": 0, "S": 0}
        for kind, T3 in srcs:
            tri = shapely.Polygon(T3[:, :2])
            strip = strip_in if kind == "L" else strip_out
            if not shapely.intersects(tri, strip):
                continue
            piece = shapely.intersection(tri, strip)
            if piece.is_empty or piece.area < 1e-10:
                continue
            n_src[kind] += 1
            A = np.column_stack([T3[:, 0], T3[:, 1], np.ones(3)])
            coef = np.linalg.solve(A, T3[:, 2])                     # exact plane of the source triangle
            for g in shapely.get_parts(piece):
                if g.geom_type != "Polygon" or g.area < 1e-10:
                    continue
                for t in shapely.get_parts(shapely.constrained_delaunay_triangles(g)):
                    f = []
                    for x, y in list(t.exterior.coords)[:3]:
                        key = (round(x, 6), round(y, 6))
                        if key not in vidx:
                            vidx[key] = len(verts)
                            verts.append((x, y, coef[0] * x + coef[1] * y + coef[2] - sink))
                        f.append(vidx[key])
                    if len(set(f)) == 3:
                        F.append(f)
        V = np.array(verts)
        F = np.array(F)
        p0, p1, p2 = V[F[:, 0], :2], V[F[:, 1], :2], V[F[:, 2], :2]
        cw = ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0])) < 0
        F[cw] = F[cw][:, [0, 2, 1]]
        Vg = np.column_stack([V[:, 0] - ox, V[:, 2], -(V[:, 1] - oy)])
        mesh = trimesh.Trimesh(Vg, F, process=False)
        s2 = trimesh.Scene()
        s2.add_geometry(mesh, geom_name=name, node_name=name)
        (run / "chunks" / "C+0038+0346" / f"{name}.glb").write_bytes(s2.export(file_type="glb"))
        out_rep["flanges"][name] = {"width_each_side_m": w, "sunk_m": sink, "role": "render apron (no collision)" if sink else "collision-only flange",
                                    "method": "exact clip of Landscape (diag A) + stitch LOD0 triangles to the strip",
                                    "triangles": len(F), "source_triangles": n_src, "plan_area_m2": round(float(strip_in.area + strip_out.area), 2)}
    (run / "collision_flange.report.json").write_text(json.dumps(out_rep, indent=1), encoding="utf-8")
    print(json.dumps(out_rep, indent=1))


if __name__ == "__main__":
    main()
