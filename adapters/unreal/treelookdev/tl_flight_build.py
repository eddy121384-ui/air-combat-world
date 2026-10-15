"""TreeLookdev moving-camera gate, stage 1 (UnrealEditor-Cmd): one map + one Level Sequence per (condition, flight path).

conditions: A (baseline 紅楠 patch), D (balanced chain patch), E (empty ground, same stage) ; paths from <GAME>/flight_paths.json
(tools/treegen/flight_paths.py). Construction follows the accepted ForestSpike B1a recipe: build the map, save it, RELOAD the saved map, then create
the Level Sequence against the reloaded world's camera (Save-As leaves the old world active and breaks the binding), save, spawn an auto-play
LevelSequenceActor (FORCE_KEEP_STATE), save again. Env ACW_TL_FLIGHT_ONLY = comma list of conds (default A,D,E).
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_budget_common import setup_tree  # noqa: E402
from tl_common import GAME, LEVEL, ROOT, ensure_dir, find_actor, lib, write_report  # noqa: E402

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
FLIGHT = ROOT + "/" + os.environ.get("ACW_TL_FLIGHT_DIR", "Flight")  # a new folder per exposure / revision (re-saving a map over a deleted one failed)
P = json.loads((GAME / "flight_paths.json").read_text(encoding="utf-8"))
CONDS = os.environ.get("ACW_TL_FLIGHT_ONLY", "A,D,E").split(",")
EV = os.environ.get("ACW_TL_FLIGHT_EV")  # absolute manual exposure bias for the native renders (the PR #30 stage value is +0.8, calibrated in SceneCapture)
report = {"status": "FAIL_TL_FLIGHT_BUILD", "maps": [], "error": None, "exposure_ev": EV}


def pose(k):
    p = k["pos_m"]
    return unreal.Vector(p[0] * 100.0, p[1] * 100.0, p[2] * 100.0), unreal.Rotator(k["rot"][0], k["rot"][1], k["rot"][2])


def bindings(seq, world):
    return [{"name": str(b.get_name()), "objects": [o.get_path_name() for o in unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq, b, world)]}
            for b in seq.get_bindings()]


def make_sequence(cam, world, name, path):
    seq = tools.create_asset("LS_" + name, FLIGHT, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    end = path["keys"][-1]["frame"]
    seq.set_display_rate(unreal.FrameRate(P["fps"], 1))
    seq.set_clock_source(unreal.UpdateClockSource.TICK)
    seq.set_playback_start(0)
    seq.set_playback_end(end)
    binding = seq.add_possessable(cam)
    section = binding.add_track(unreal.MovieScene3DTransformTrack).add_section()
    section.set_range(0, end)
    channels = list(section.get_all_channels())
    for k in path["keys"]:
        loc, rot = pose(k)
        for c, v in zip(channels, [loc.x, loc.y, loc.z, rot.roll, rot.pitch, rot.yaw, 1, 1, 1]):
            c.add_key(unreal.FrameNumber(k["frame"]), float(v), 0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, unreal.MovieSceneKeyInterpolation.LINEAR)
    cut = seq.add_track(unreal.MovieSceneCameraCutTrack).add_section()
    cut.set_range(0, end)
    cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding))
    if not lib.save_asset(seq.get_path_name()):
        raise RuntimeError("save sequence")
    lsa = actors.spawn_actor_from_class(unreal.LevelSequenceActor, unreal.Vector())
    lsa.set_actor_label("TL_Flight_Sequence")
    lsa.set_editor_property("level_sequence_asset", seq)
    ps = lsa.get_editor_property("playback_settings")
    ps.set_editor_property("auto_play", True)
    ps.set_editor_property("loop_count", unreal.MovieSceneSequenceLoopCount(0))
    ps.set_editor_property("finish_completion_state_override", unreal.MovieSceneCompletionModeOverride.FORCE_KEEP_STATE)
    lsa.set_editor_property("playback_settings", ps)
    b = bindings(seq, world)
    if not any(cam.get_path_name() in x["objects"] for x in b):
        raise RuntimeError("camera not bound: %s" % b)
    return seq.get_path_name(), b


def one(cond, pid, path):
    name = "%s_%s" % (cond, pid)
    dest = FLIGHT + "/L_TLF_" + name
    if lib.does_asset_exist(dest):
        lib.delete_asset(dest)
    if not levels.load_level(LEVEL):
        raise RuntimeError("load " + LEVEL)
    if cond == "E":
        actors.destroy_actor(find_actor(actors, "TL_Machilus"))
    else:
        setup_tree(actors, "patch", cond)
    if EV is not None:
        pp = find_actor(actors, "TL_PostProcess")
        st = pp.get_editor_property("settings")
        st.set_editor_property("override_auto_exposure_bias", True)
        st.set_editor_property("auto_exposure_bias", float(EV))
        pp.set_editor_property("settings", st)
    loc, rot = pose(path["keys"][0])
    cam = actors.spawn_actor_from_class(unreal.CameraActor, loc, rot)
    cam.set_actor_label("TL_FlightCamera")
    cc = cam.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", P["hfov_deg"])
    cc.set_editor_property("aspect_ratio", 16.0 / 9.0)
    cc.set_editor_property("constrain_aspect_ratio", True)
    cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, dest):
        raise RuntimeError("save_map " + dest)
    del world, cam, cc
    if not levels.load_level(dest):
        raise RuntimeError("reload " + dest)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != dest:
        raise RuntimeError("wrong world after reload: " + world.get_path_name())
    cam = find_actor(actors, "TL_FlightCamera")
    seq_path, b = make_sequence(cam, world, name, path)
    if not levels.save_current_level():
        raise RuntimeError("save level")
    report["maps"].append({"cond": cond, "path": pid, "map": dest, "sequence": seq_path, "bindings": b, "frames": path["keys"][-1]["frame"]})


try:
    ensure_dir(FLIGHT)
    for cond in CONDS:
        for pid, path in P["paths"].items():
            one(cond, pid, path)
    report["status"] = "PASS_TL_FLIGHT_BUILD"
except Exception:  # noqa: BLE001
    report["error"] = traceback.format_exc()
    unreal.log_error(report["error"])
write_report("tl_flight_build.report.json", report)
unreal.SystemLibrary.quit_editor()
