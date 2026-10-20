"""Runtime gate: shader statistics of the forest-world materials (UnrealEditor-Cmd, with RHI; read only).

MaterialEditingLibrary.get_statistics on the desktop shader platform: vertex / pixel instruction counts and sampler count. The sampler
count is the first mobile hard limit to check (ES3.1: 16 samplers per pixel shader). Receipt: reports/nf_mat_stats.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAT, lib, write_report  # noqa: E402

NAMES = ["M_NF_LandscapeDL_R3", "M_NF_LeafCards", "M_NF_AcaciaW_LeafCards", "M_NF_Cryptomeria_LeafCards", "M_NF_Bark", "M_NF_Building_R6", "M_NF_Water"]
rep = {"status": "FAIL_NF_MAT_STATS", "materials": {}, "error": None}
try:
    for n in NAMES:
        m = lib.load_asset(MAT + "/" + n)
        if m is None:
            rep["materials"][n] = None
            continue
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        s = unreal.MaterialEditingLibrary.get_statistics(m)
        rep["materials"][n] = {k: s.get_editor_property(k) for k in ("num_vertex_shader_instructions", "num_pixel_shader_instructions", "num_samplers",
                                                                       "num_vertex_texture_samples", "num_pixel_texture_samples",
                                                                       "num_virtual_texture_samples", "num_uv_scalars", "num_interpolator_scalars")}
        rep["materials"][n]["blend_mode"] = str(m.get_editor_property("blend_mode"))
    rep["status"] = "PASS_NF_MAT_STATS"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
write_report("nf_mat_stats.report.json", rep)
unreal.SystemLibrary.quit_editor()
