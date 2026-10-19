"""Leaf specular for the forest-world tint instances MI_NF_Leaf_V0..V9 (UnrealEditor-Cmd -nullrhi).

The source leaf graphs expose a "Specular" scalar (default 0.18). Seen from the air at grazing angles that specular reflects the bright
sky as a frosty sheen on the crown tops, the same failure the Landscape had (see nf_landscape_dl.py). Only the M_NF instances used by
the forest world are changed (ACW_NF_LEAF_SPEC, default 0.10); the M_TL_* look-dev materials and their instances are untouched.
Receipt: reports/nf_leaf_spec.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import LEAF_VARIANTS, MAT, lib, mel, write_report  # noqa: E402

val = float(os.environ.get("ACW_NF_LEAF_SPEC", "0.10"))
rep = {"status": "FAIL_NF_LEAF_SPEC", "specular": val, "instances": {}, "error": None}
try:
    for v in LEAF_VARIANTS:
        path = MAT + "/MI_NF_Leaf_V%d" % v
        mic = lib.load_asset(path)
        mel.set_material_instance_scalar_parameter_value(mic, "Specular", val)
        got = mel.get_material_instance_scalar_parameter_value(mic, "Specular")
        mel.update_material_instance(mic)
        lib.save_asset(path, only_if_is_dirty=False)
        rep["instances"][path] = got
    rep["status"] = "PASS_NF_LEAF_SPEC" if all(abs(x - val) < 1e-4 for x in rep["instances"].values()) else "FAIL_NF_LEAF_SPEC"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
write_report("nf_leaf_spec.report.json", rep)
unreal.SystemLibrary.quit_editor()
