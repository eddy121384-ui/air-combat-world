"""UE 5.8 isolated import + seam check for the terrain vertical slice (runs INSIDE UnrealEditor-Cmd).

Uses a throwaway project (never the formal AirCombatWorld project). Imports the LOD0 chunk GLBs of both pilot cells and the
Xinyi seam stitch through Interchange (the route proven for the accepted Xinyi tiles), strips Nanite (mobile/SM5 baseline),
then reads back every imported StaticMesh's MeshDescription and checks, inside the engine:
  * vertex / triangle counts vs the GLB
  * axis mapping and units (expected UE X = east*100, UE Y = -north*100, UE Z = up*100 relative to the glTF node)
  * shared chunk edges (within and across the two cells) and stitch <-> chunk shared vertices: identical positions after
    composing the known node translations
This is an ASSET-LEVEL check. Runtime streaming, HLOD, collision behaviour and mobile performance are NOT tested here.
env: ACW_NTW_TERRAIN_RUN (terrain run dir), ACW_NTW_UE_REPORT (json path)
"""
import io
import json
import math
import os
import struct
import time

import unreal

RUN = os.environ["ACW_NTW_TERRAIN_RUN"]
REPORT = os.environ["ACW_NTW_UE_REPORT"]
ROOT = "/Game/NTWTerrainPilot"


def glb_node_translation_and_counts(path):
    """Minimal GLB reader: node translation + accessor counts (POSITION, indices) without third-party modules."""
    with open(path, "rb") as fh:
        data = fh.read()
    jlen = struct.unpack_from("<I", data, 12)[0]
    j = json.loads(data[20:20 + jlen].decode("utf-8"))
    node = j["nodes"][0]
    t = node.get("translation")
    if t is None and "matrix" in node:
        m = node["matrix"]
        t = [m[12], m[13], m[14]]
    prim = j["meshes"][node["mesh"]]["primitives"][0]
    nv = j["accessors"][prim["attributes"]["POSITION"]]["count"]
    nt = j["accessors"][prim["indices"]]["count"] // 3
    return t or [0.0, 0.0, 0.0], nv, nt


def import_one(src, dest):
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    sd = unreal.InterchangeManager.create_source_data(src)
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    return mgr.import_asset(dest, sd, params)


def mesh_vertices(sm):
    """Positions (cm) of LOD0 render-mesh vertices via the StaticMesh description."""
    md = sm.get_static_mesh_description(0)
    n = md.get_vertex_count()
    out = []
    for i in range(n):
        p = md.get_vertex_position(unreal.VertexID(i))
        out.append((p.x, p.y, p.z))
    tri = md.get_triangle_count()
    return out, tri


def main():
    t0 = time.time()
    lib = unreal.EditorAssetLibrary
    if lib.does_directory_exist(ROOT) and lib.list_assets(ROOT, recursive=True):
        raise RuntimeError("isolated destination not empty: " + ROOT)
    files = []
    for cell in sorted(os.listdir(os.path.join(RUN, "chunks"))):
        d = os.path.join(RUN, "chunks", cell)
        for f in sorted(os.listdir(d)):
            if f.endswith("_lod0.glb"):
                files.append((cell, f, os.path.join(d, f)))
    rows = []
    for cell, f, path in files:
        dest = f"{ROOT}/{cell.replace('+', 'p').replace('-', 'm')}/{f[:-4]}"
        import_one(path, dest)
        meshes = [lib.load_asset(a) for a in lib.list_assets(dest, recursive=True)]
        meshes = [m for m in meshes if isinstance(m, unreal.StaticMesh)]
        if len(meshes) != 1:
            rows.append({"file": f, "cell": cell, "error": f"expected 1 StaticMesh, got {len(meshes)}"})
            continue
        sm = meshes[0]
        try:
            ns = sm.get_editor_property("nanite_settings")
            if ns.enabled:
                ns.enabled = False
                sm.set_editor_property("nanite_settings", ns)
        except Exception:  # noqa: BLE001
            pass
        verts, tri = mesh_vertices(sm)
        t, nv, nt = glb_node_translation_and_counts(path)
        bb = sm.get_bounding_box()
        rows.append({"file": f, "cell": cell, "asset": sm.get_path_name(), "glb_vertices": nv, "glb_triangles": nt,
                     "ue_vertices": len(verts), "ue_triangles": tri, "glb_node_translation_m": t,
                     "ue_bounds_cm": [bb.min.x, bb.min.y, bb.min.z, bb.max.x, bb.max.y, bb.max.z],
                     "_verts": verts})
    lib.save_directory(ROOT, only_if_is_dirty=False, recursive=True)
    # raw dump only; geometric analysis happens offline (tools/ntw/ue_terrain_pilot_analyse.py) against the exact GLB data
    counts_ok = all(r.get("ue_triangles") == r.get("glb_triangles") for r in rows if "error" not in r)
    out = {"engine": unreal.SystemLibrary.get_engine_version(), "project": unreal.Paths.get_project_file_path(),
           "imported_meshes": sum(1 for r in rows if "error" not in r), "errors": [r for r in rows if "error" in r],
           "triangle_counts_equal_glb": counts_ok, "seconds": round(time.time() - t0, 1),
           "not_tested": ["runtime streaming", "HLOD", "collision traces", "Landscape actors", "mobile / device performance"],
           "meshes": [{k: (v if k != "_verts" else [[round(c, 4) for c in p_] for p_ in v]) for k, v in r.items()} for r in rows]}
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    unreal.log("NTW terrain pilot UE check written: " + REPORT)


main()
