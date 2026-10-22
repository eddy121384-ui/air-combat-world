"""Far-LOD research: retune the impostor runtime grids (cell size / loading range / 2D / origin) without rebuilding the actors.
ACW_FI_GRIDS = "FI_B0:200000:680000,FI_B1:200000:680000" (name:cell_cm:range_cm). Streaming cells are generated from the actor
descriptors at runtime / cook, so a partition change is enough. Receipt: reports/fi_grids.report.json."""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAP, write_report  # noqa: E402

rep = {"status": "FAIL_FI_GRIDS", "error": None}
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    world = unreal.EditorLevelLibrary.get_editor_world()
    lib = unreal.SkyfrontFarLodLibrary
    rep["set"] = []
    for item in os.environ["ACW_FI_GRIDS"].split(","):
        name, cell, rng = item.split(":")
        rep["set"].append(json.loads(lib.ensure_runtime_partition(world, name, int(cell), int(rng), 0)).get("set_ok"))
        rep["set"].append(json.loads(lib.set_runtime_partition_shape(world, name, True, 54000.0, 0.0)).get("set_ok"))
    rep["now"] = json.loads(lib.describe_runtime_partitions(world))
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save")
    rep["status"] = "PASS_FI_GRIDS"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("fi_grids.report.json", rep)
unreal.SystemLibrary.quit_editor()
