"""Probe: can Epic's ImpostorBaker (Editor Utility Widget) be driven from editor Python? (research spike, no side effects)"""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(__file__))
import unreal
from tl_common import write_report, lib
rep = {"status": "FAIL_PROBE"}
try:
    plug = [a for a in lib.list_assets("/ImpostorBaker", recursive=True)]
    rep["assets"] = [str(a) for a in plug]
    for name in ("EUW_Generate_Impostor_using_Preset", "EUW_Impostor_Editor", "AssetAction_StaticMeshImpostor", "BP_Generate_ImpostorSprites"):
        a = lib.load_asset("/ImpostorBaker/BP/" + name)
        rep[name] = None if a is None else a.get_class().get_name()
        if a is not None:
            gc = a.generated_class() if hasattr(a, "generated_class") else None
            rep[name + "_class"] = str(gc)
            if gc is not None:
                cdo = unreal.get_default_object(gc)
                rep[name + "_members"] = [m for m in dir(cdo) if not m.startswith("_")][:400]
    rep["status"] = "PASS_PROBE"
except Exception:
    rep["error"] = traceback.format_exc()
write_report("tl_probe_impostor.report.json", rep)
unreal.SystemLibrary.quit_editor()
