"""TreeLookdev stage 3 (UnrealEditor-Cmd): standalone-game perf levels, one per (view, variant).

/Game/TreeLookdev/Perf/L_TLP_<view>_<variant>: the look-dev level + a CameraActor (player 0 view) at the views.json
camera; variant "tree" keeps the game tree with automatic LOD, "empty" removes it (same stage, same camera).
The -game process then runs under the CSV profiler with GPU per-pass stats (tools/treegen/run_tl_perf.ps1).
Env ACW_TL_PERF_VIEWS = comma list (default front,close,agl50,agl200).
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import LEVEL, ROOT, b2u, b2u_dir, find_actor, lib, views, write_report  # noqa: E402

PERF = ROOT + "/Perf"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
names = os.environ.get("ACW_TL_PERF_VIEWS", "front,close,agl50,agl200").split(",")
built, err = [], None
try:
    if not lib.does_directory_exist(PERF):
        lib.make_directory(PERF)
    V = {v["name"]: v for v in views()["views"]}
    for name in names:
        for variant in ("tree", "empty"):
            if not levels.load_level(LEVEL):
                raise RuntimeError("load " + LEVEL)
            v = V[name]
            loc = b2u(v["loc"])
            d = b2u_dir(v["fwd"])
            rot = unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(loc.x + d.x * 1e5, loc.y + d.y * 1e5, loc.z + d.z * 1e5))
            cam = actors.spawn_actor_from_class(unreal.CameraActor, loc, rot)
            cam.set_actor_label("TL_PerfCamera")
            cc = cam.get_component_by_class(unreal.CameraComponent)
            cc.set_editor_property("field_of_view", float(v["hfov_deg"]))
            cc.set_editor_property("aspect_ratio", 16.0 / 9.0)
            cc.set_editor_property("constrain_aspect_ratio", True)
            cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
            if variant == "empty":
                actors.destroy_actor(find_actor(actors, "TL_Machilus"))
            dest = PERF + "/L_TLP_%s_%s" % (name, variant)
            if lib.does_asset_exist(dest):
                lib.delete_asset(dest)
            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            if not unreal.EditorLoadingAndSavingUtils.save_map(world, dest):
                raise RuntimeError("save_map failed: " + dest)
            built.append(dest)
    status = "PASS_TL_PERF_LEVELS"
except Exception:  # noqa: BLE001
    status, err = "FAIL_TL_PERF_LEVELS", traceback.format_exc()
    unreal.log_error(err)
write_report("tl_perf_levels.report.json", {"status": status, "levels": built, "error": err})
unreal.SystemLibrary.quit_editor()
