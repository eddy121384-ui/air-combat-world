"""Forest performance A/B: put L_NF_Yangmingshan into one named configuration (UnrealEditor-Cmd -nullrhi).

ACW_NF_CFG = JSON object, any of:
  "mpc":       {param: value, ...}   MPC_NF_Forest defaults (NearFull, ThinEnd, FadeWidth, ThinGamma, ShellStart, ShellEnd, ClumpGain, ...)
  "wp_range_cm": int                 World Partition runtime grid loading range (cell size stays 1 km)
  "landscape": "<material name>"     material asset in /Game/NorthForest/Materials assigned to NF_Terrain
  "sun_shadow_cm": float             directional light dynamic shadow distance
Only what is given is changed; the receipt records the full resulting state. HISM end cull distances are NOT changed here (they stay at
the PR #49 4.3 km); shorter culls are applied at run time with foliage.MaxEndCullDistance, so the map is never rebuilt for an A/B.
Receipt: reports/nf_perfcfg.report.json.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAP, MAT, lib, write_report  # noqa: E402

cfg = json.loads(os.environ.get("ACW_NF_CFG", "{}"))
rep = {"status": "FAIL_NF_PERFCFG", "cfg": cfg, "error": None}
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
try:
    if "mpc" in cfg:
        c = lib.load_asset(MAT + "/MPC_NF_Forest")
        params = list(c.get_editor_property("scalar_parameters"))
        for p in params:
            nm = str(p.get_editor_property("parameter_name"))
            if nm in cfg["mpc"]:
                p.set_editor_property("default_value", float(cfg["mpc"][nm]))
        c.set_editor_property("scalar_parameters", params)
        lib.save_asset(MAT + "/MPC_NF_Forest", only_if_is_dirty=False)
    rep["mpc"] = {str(p.get_editor_property("parameter_name")): p.get_editor_property("default_value")
                  for p in lib.load_asset(MAT + "/MPC_NF_Forest").get_editor_property("scalar_parameters")}
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    if "wp_range_cm" in cfg:
        rep["grid"] = json.loads(unreal.NtwGateLibrary.configure_runtime_grid(100000, int(cfg["wp_range_cm"])))
    rep["grid_now"] = json.loads(unreal.NtwGateLibrary.describe_runtime_grid())
    for a in ues.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn in ("Landscape", "LandscapeStreamingProxy"):
            if "landscape" in cfg:
                a.modify()
                a.set_editor_property("landscape_material", lib.load_asset(MAT + "/" + cfg["landscape"]))
            rep["landscape_material"] = a.get_editor_property("landscape_material").get_name()
        if cn == "DirectionalLight":
            sc = a.get_component_by_class(unreal.DirectionalLightComponent)
            if "sun_shadow_cm" in cfg:
                a.modify()
                sc.modify()
                sc.set_editor_property("dynamic_shadow_distance_movable_light", float(cfg["sun_shadow_cm"]))
            rep["sun_shadow_cm"] = sc.get_editor_property("dynamic_shadow_distance_movable_light")
    les.save_current_level()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    rep["status"] = "PASS_NF_PERFCFG"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
write_report("nf_perfcfg.report.json", rep)
unreal.SystemLibrary.quit_editor()
