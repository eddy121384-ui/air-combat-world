"""Probe (kept for the failure log): parameter names of M_TL_LeafCards and whether a MIC setter finds them."""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(__file__))
import unreal
from tl_common import MAT_DIR, lib, mel, tools, write_report
rep = {"status": "FAIL", "error": None}
try:
    p = lib.load_asset(MAT_DIR + "/M_TL_LeafCards")
    rep["vector"] = [str(n) for n in mel.get_vector_parameter_names(p)]
    rep["scalar"] = [str(n) for n in mel.get_scalar_parameter_names(p)]
    mic = tools.create_asset("MI_HF_Probe", "/Game/HillsideForest", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mic, p)
    rep["parent_after_set"] = mic.get_editor_property("parent").get_path_name() if mic.get_editor_property("parent") else None
    rep["set_vec"] = mel.set_material_instance_vector_parameter_value(mic, "TintHi", unreal.LinearColor(1, 1, 1, 1))
    rep["set_vec_name"] = mel.set_material_instance_vector_parameter_value(mic, unreal.Name("TintHi"), unreal.LinearColor(1, 1, 1, 1))
    rep["set_scalar"] = mel.set_material_instance_scalar_parameter_value(mic, "Brightness", 0.5)
    rep["get_vec"] = str(mel.get_material_instance_vector_parameter_value(mic, "TintHi"))
    rep["mic_vector_names"] = [str(n) for n in mel.get_vector_parameter_names(mic)]
    lib.delete_asset("/Game/HillsideForest/MI_HF_Probe")
    rep["status"] = "PASS"
except Exception:
    rep["error"] = traceback.format_exc()
write_report("hf_probe_params.report.json", rep)
unreal.SystemLibrary.quit_editor()
