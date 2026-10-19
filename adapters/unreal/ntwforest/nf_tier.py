"""North Taiwan forest world v1: write a forest scalability preset into MPC_NF_Forest (UnrealEditor-Cmd -nullrhi).

Tree thinning and the canopy shell read MPC_NF_Forest, so a tier is just these numbers (cm). This stage writes the DEFAULTS of the
collection (what an un-scripted game run uses); a shipping game would set the same values at startup with
SetScalarParameterValue on the collection (one Blueprint/C++ call per value) together with the tier's cvars
(foliage.MaxEndCullDistance = ThinEnd + 200 m clamps the HISM end cull so faded-out trees are not even submitted).
    ACW_NF_TIER = pc | mobile      Receipt: reports/nf_tier.report.json
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAT, lib, write_report  # noqa: E402

PRESETS = {
    # PC: full density to 450 m, last tree by 2.4 km, canopy colour / shell 0.7 -> 2.0 km
    "pc": {"NearFull": 45000.0, "ThinEnd": 240000.0, "FadeWidth": 12000.0, "ThinGamma": 1.6, "ShellStart": 70000.0, "ShellEnd": 200000.0, "ShellScale": 0.8},
    # mobile: full density to 250 m, last tree by 1.1 km, canopy colour / shell 0.3 -> 0.9 km
    "mobile": {"NearFull": 25000.0, "ThinEnd": 110000.0, "FadeWidth": 8000.0, "ThinGamma": 1.6, "ShellStart": 30000.0, "ShellEnd": 90000.0, "ShellScale": 0.8},
}
tier = os.environ.get("ACW_NF_TIER", "pc")
rep = {"status": "FAIL_NF_TIER", "tier": tier, "error": None}
try:
    c = lib.load_asset(MAT + "/MPC_NF_Forest")
    params = list(c.get_editor_property("scalar_parameters"))
    for p in params:
        nm = str(p.get_editor_property("parameter_name"))
        if nm in PRESETS[tier]:
            p.set_editor_property("default_value", PRESETS[tier][nm])
    c.set_editor_property("scalar_parameters", params)
    lib.save_asset(MAT + "/MPC_NF_Forest", only_if_is_dirty=False)
    rep["values"] = {str(p.get_editor_property("parameter_name")): p.get_editor_property("default_value")
                     for p in lib.load_asset(MAT + "/MPC_NF_Forest").get_editor_property("scalar_parameters")}
    rep["status"] = "PASS_NF_TIER" if all(abs(rep["values"][k] - v) < 1e-3 for k, v in PRESETS[tier].items()) else "FAIL_NF_TIER"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
write_report("nf_tier.report.json", rep)
unreal.SystemLibrary.quit_editor()
