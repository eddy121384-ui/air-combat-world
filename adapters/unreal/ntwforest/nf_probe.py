"""Probe: project opens, bridge plugin classes exist, the four species meshes and source materials load (no writes)."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import FORM_BARK_SRC, FORM_LEAF_SRC, FORM_MESH, SRC_MAT, lib, write_report  # noqa: E402

rep = {"status": "FAIL_NF_PROBE", "error": None}
try:
    rep["bridge"] = hasattr(unreal, "XinyiLandscapeLibrary")
    rep["gate_lib"] = hasattr(unreal, "NtwGateLibrary")
    rep["meshes"] = {}
    for f, p in FORM_MESH.items():
        m = lib.load_asset(p)
        rep["meshes"][f] = None if m is None else {"lods": m.get_num_lods(), "bounds_r_cm": m.get_bounds().sphere_radius,
                                                   "tris": [m.get_num_triangles(i) for i in range(m.get_num_lods())],
                                                   "screens": [str(x) for x in unreal.EditorStaticMeshLibrary.get_lod_screen_sizes(m)]}
    rep["materials"] = {n: lib.does_asset_exist(SRC_MAT + "/" + n) for n in set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())}
    leaf = lib.load_asset(SRC_MAT + "/M_TL_LeafCards")
    node = unreal.MaterialEditingLibrary.get_material_property_input_node(leaf, unreal.MaterialProperty.MP_OPACITY_MASK)
    rep["leaf_opacity_node"] = None if node is None else node.get_class().get_name()
    ok = rep["bridge"] and rep["gate_lib"] and all(rep["meshes"].values()) and all(rep["materials"].values())
    rep["status"] = "PASS_NF_PROBE" if ok else "FAIL_NF_PROBE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
write_report("nf_probe.report.json", rep)
unreal.SystemLibrary.quit_editor()
