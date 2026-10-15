"""TreeLookdev: flag the tree materials for use with (hierarchical) instanced static meshes and save them.

Why: the editor sets "Used with Instanced Static Meshes" in memory the first time a HISM draws a material, but standalone `-game` needs the flag
saved in the asset; without it the HISM draws the engine default (grey, opaque) material. PR #30 only used a plain StaticMeshComponent, so it never
needed it. Only the usage flag changes; the material graphs are untouched.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import MAT_DIR, lib, mel, write_report  # noqa: E402

rep = {"status": "FAIL_TL_FIX_USAGE", "materials": {}, "error": None}
try:
    for name in ("M_TL_LeafCards", "M_TL_Bark"):
        m = lib.load_asset(MAT_DIR + "/" + name)
        before = bool(m.get_editor_property("used_with_instanced_static_meshes"))
        mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
        mel.recompile_material(m)
        if not lib.save_asset(MAT_DIR + "/" + name):
            raise RuntimeError("save " + name)
        rep["materials"][name] = {"before": before, "after": bool(m.get_editor_property("used_with_instanced_static_meshes"))}
    rep["status"] = "PASS_TL_FIX_USAGE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("tl_fix_material_usage.report.json", rep)
unreal.SystemLibrary.quit_editor()
