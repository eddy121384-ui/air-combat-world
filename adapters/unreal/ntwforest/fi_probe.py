"""Far-LOD research probe (UnrealEditor-Cmd): tree mesh bounds / LODs, leaf + bark material shading, the distance keep / clump HLSL.
Receipt: reports/fi_probe.report.json. Read-only (nothing is saved)."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import FORM_BARK_SRC, FORM_LEAF_SRC, FORM_MESH, MAT, VARIANT_FORM, lib, mel, write_report  # noqa: E402

rep = {"status": "FAIL_FI_PROBE", "forms": {}, "materials": {}, "error": None}
try:
    for f, p in FORM_MESH.items():
        m = lib.load_asset(p)
        b = m.get_bounds()
        sm = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        rep["forms"][f] = {
            "path": p, "origin": [b.origin.x, b.origin.y, b.origin.z], "extent": [b.box_extent.x, b.box_extent.y, b.box_extent.z],
            "sphere": b.sphere_radius, "lods": m.get_num_lods(),
            "tris": [sm.get_number_verts(m, i) for i in range(m.get_num_lods())],
            "materials": [str(s.material_interface.get_path_name()) if s.material_interface else None for s in m.get_editor_property("static_materials")],
        }
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        d = {"shading": str(mat.get_editor_property("shading_model")), "blend": str(mat.get_editor_property("blend_mode")),
             "two_sided": mat.get_editor_property("two_sided"), "customs": []}
        for prop in (unreal.MaterialProperty.MP_OPACITY_MASK, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET):
            n = mel.get_material_property_input_node(mat, prop)
            stack = [n]
            seen = set()
            while stack:
                x = stack.pop()
                if x is None or x.get_name() in seen:
                    continue
                seen.add(x.get_name())
                if x.get_class().get_name() == "MaterialExpressionCustom":
                    d["customs"].append({"prop": str(prop), "desc": str(x.get_editor_property("description")),
                                         "inputs": [str(i.get_editor_property("input_name")) for i in x.get_editor_property("inputs")],
                                         "code": str(x.get_editor_property("code"))})
                stack.extend(mel.get_inputs_for_material_expression(mat, x) or [])
        rep["materials"][path] = d
    for v in VARIANT_FORM:
        mi = lib.load_asset(MAT + "/MI_NF_Leaf_V%d" % v)
        rep.setdefault("leaf_mi", {})[v] = str(mi.get_editor_property("parent").get_path_name()) if mi else None
    rep["status"] = "PASS_FI_PROBE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("fi_probe.report.json", rep)
unreal.SystemLibrary.quit_editor()
