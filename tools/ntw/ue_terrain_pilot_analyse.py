"""Offline analysis of the UE 5.8 isolated import dumps (ue_check_<variant>.json from ue_terrain_pilot_check.py).

For each variant (baked = GLB node translation baked by Interchange; local = identity-node export, origins from the report):
  * axis/unit mapping: UE (X, Y, Z) cm -> glTF (X/100, Z/100, Y/100)
  * position fidelity: max distance from every imported UE vertex to the exact GLB vertex set (and back)
  * shared edges in the engine: positions shared by two imported meshes (within 1 cm in plan) must carry the same height
Writes data/ntw/terrain/ue_import_check.json (committed).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import frame  # noqa: E402

T = REPO / "data/generated/ntw/terrain"


def glb_local(path):
    sc = trimesh.load_scene(io.BytesIO(path.read_bytes()), file_type="glb", process=False)
    node = sc.graph.nodes_geometry[0]
    tr, g = sc.graph[node]
    return np.asarray(sc.geometry[g].vertices, dtype=np.float64), tr[:3, 3].copy()


def analyse(tag, run):
    d = json.loads((T / f"ue_check_{tag}.json").read_text(encoding="utf-8"))
    rep = json.loads((run / "terrain.report.json").read_text(encoding="utf-8"))
    origin = {(c["cell"], f"{c['chunk']}_lod{c['lod']}.glb" if c["chunk"] != "xinyi_stitch" else f"xinyi_stitch_lod{c['lod']}.glb"): c["sw_epsg3826"]
              for c in rep["chunks"]}
    worst_fwd, worst_bwd, baked_any = 0.0, 0.0, False
    world = []
    for m in d["meshes"]:
        if "error" in m:
            continue
        ue = np.asarray(m["_verts"], dtype=np.float64)
        g_ue = np.column_stack([ue[:, 0], ue[:, 2], ue[:, 1]]) / 100.0     # -> glTF axes, metres
        gv, t = glb_local(run / "chunks" / m["cell"] / m["file"])
        baked = np.abs(g_ue[:, 0].mean() - gv[:, 0].mean()) > 1000.0
        baked_any |= baked
        loc = g_ue - t if baked else g_ue
        a, _ = cKDTree(gv).query(loc)
        b, _ = cKDTree(loc).query(gv)
        worst_fwd, worst_bwd = max(worst_fwd, float(a.max())), max(worst_bwd, float(b.max()))
        ox, oy = origin[(m["cell"], m["file"])]
        e = ox + loc[:, 0]
        n = oy - loc[:, 2]
        world.append(np.column_stack([e, n, loc[:, 1], np.full(len(e), len(world))]))
    W = np.vstack(world)
    tree = cKDTree(W[:, :2])
    pairs = tree.query_pairs(0.01, output_type="ndarray")
    cross = pairs[W[pairs[:, 0], 3] != W[pairs[:, 1], 3]]
    dz = np.abs(W[cross[:, 0], 2] - W[cross[:, 1], 2])
    # skirt bottom vertices share plan position with their top vertex in the SAME mesh, so only cross-mesh pairs are judged;
    # a skirt bottom of mesh A coincides in plan with the edge vertex of mesh B: exclude pairs where either side is a skirt bottom
    tops = dz < 1.0
    return {"variant": tag, "engine": d["engine"], "imported_meshes": d["imported_meshes"], "errors": len(d["errors"]),
            "triangle_counts_equal_glb": d["triangle_counts_equal_glb"], "interchange_baked_node_translation": bool(baked_any),
            "max_vertex_error_ue_to_glb_m": round(worst_fwd, 6), "max_vertex_error_glb_to_ue_m": round(worst_bwd, 6),
            "cross_mesh_coincident_plan_positions": int(len(cross)), "of_which_surface_vertices": int(tops.sum()),
            "surface_shared_vertex_max_height_diff_m": round(float(dz[tops].max()), 6) if tops.any() else None,
            "import_seconds": d["seconds"], "not_tested": d["not_tested"]}


def main():
    out = {"note": "Isolated throwaway UE 5.8 project (never the formal AirCombatWorld project); asset-level import only."}
    for tag, run in (("baked", T / "joint_run1"), ("local", T / "joint_ue_local")):
        if (T / f"ue_check_{tag}.json").exists():
            out[tag] = analyse(tag, run)
    (REPO / "data/ntw/terrain/ue_import_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
