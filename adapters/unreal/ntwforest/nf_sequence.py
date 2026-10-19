"""North Taiwan forest world v1, stage 3 (UnrealEditor-Cmd): camera + Level Sequences in L_NF_Yangmingshan (views.json).

* NF_Cam (CameraActor, 70 deg hfov, 16:9), not spatially loaded.
* LS_NF_Flight: the terrain-following flyover (linear keys every frame). LS_NF_Stills: each review pose held still_hold_frames.
  LS_NF_Perf: each still held 8 s, then the flight - played by NF_PerfSequence (auto-play, not spatially loaded) in standalone -game
  performance runs. MRQ renders LS_NF_Flight / LS_NF_Stills with -LevelSequence.
Receipt: reports/nf_sequence.report.json.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAP, RUN, find_actor, lib, tools, write_report  # noqa: E402

LEVEL = MAP + "/L_NF_Yangmingshan"
SEQ_DIR = MAP.replace("/Maps", "/Sequences")
PERF_HOLD_S = 8
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V = json.loads((RUN / "views.json").read_text(encoding="utf-8"))
rep = {"status": "FAIL_NF_SEQUENCE", "sequences": {}, "error": None}


def camera():
    old = find_actor("NF_Cam")
    if old is not None:
        raise RuntimeError("NF_Cam exists: the map already has sequences")
    s0 = V["stills"][0]
    cam = ues.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(*s0["ue_loc_cm"]), unreal.Rotator(*s0["ue_rot"]))
    cam.set_actor_label("NF_Cam")
    cc = cam.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", V["hfov_deg"])
    cc.set_editor_property("aspect_ratio", 16.0 / 9.0)
    cc.set_editor_property("constrain_aspect_ratio", True)
    cam.set_editor_property("is_spatially_loaded", False)
    return cam


def sequence(name, keys, interp, cam):
    if not lib.does_directory_exist(SEQ_DIR):
        lib.make_directory(SEQ_DIR)
    seq = tools.create_asset(name, SEQ_DIR, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    end = keys[-1]["frame"]
    seq.set_display_rate(unreal.FrameRate(V["fps"], 1))
    seq.set_clock_source(unreal.UpdateClockSource.TICK)
    seq.set_playback_start(0)
    seq.set_playback_end(end + 1)
    binding = seq.add_possessable(cam)
    section = binding.add_track(unreal.MovieScene3DTransformTrack).add_section()
    section.set_range(0, end + 1)
    ch = list(section.get_all_channels())
    for k in keys:
        vals = list(k["ue_loc_cm"]) + list(k["ue_rot"])
        for c, val in zip(ch[:6], vals):
            c.add_key(unreal.FrameNumber(k["frame"]), float(val), 0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, interp)
    for c in ch[6:9]:
        c.add_key(unreal.FrameNumber(0), 1.0, 0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, unreal.MovieSceneKeyInterpolation.CONSTANT)
    cut = seq.add_track(unreal.MovieSceneCameraCutTrack).add_section()
    cut.set_range(0, end + 1)
    cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding))
    if not lib.save_asset(seq.get_path_name()):
        raise RuntimeError("save " + name)
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    bound = [o.get_path_name() for b in seq.get_bindings() for o in unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq, b, w)]
    if cam.get_path_name() not in bound:
        raise RuntimeError("camera not bound in " + name)
    rep["sequences"][name] = {"path": seq.get_path_name(), "frames": end + 1}
    return seq


def held(stills, hold, start=0):
    keys = []
    for i, s in enumerate(stills):
        keys.append(dict(frame=start + i * hold, ue_loc_cm=s["ue_loc_cm"], ue_rot=s["ue_rot"]))
    last = stills[-1]
    keys.append(dict(frame=start + len(stills) * hold - 1, ue_loc_cm=last["ue_loc_cm"], ue_rot=last["ue_rot"]))
    return keys


try:
    if not les.load_level(LEVEL):
        raise RuntimeError("load " + LEVEL)
    cam = camera()
    sequence("LS_NF_Flight", V["flight"]["keys"], unreal.MovieSceneKeyInterpolation.LINEAR, cam)
    hold = V["still_hold_frames"]
    sequence("LS_NF_Stills", held(V["stills"], hold), unreal.MovieSceneKeyInterpolation.CONSTANT, cam)
    ph = PERF_HOLD_S * V["fps"]
    pk = held(V["stills"], ph)
    off = len(V["stills"]) * ph
    pk += [dict(frame=k["frame"] + off, ue_loc_cm=k["ue_loc_cm"], ue_rot=k["ue_rot"]) for k in V["flight"]["keys"]]
    perf = sequence("LS_NF_Perf", pk, unreal.MovieSceneKeyInterpolation.CONSTANT, cam)
    # the flight part of the perf sequence must interpolate: CONSTANT keys every frame are equivalent at a fixed frame step
    rep["perf_layout"] = {"still_hold_frames": ph, "stills": [s["name"] for s in V["stills"]], "flight_start_frame": off, "fps": V["fps"]}
    lsa = ues.spawn_actor_from_class(unreal.LevelSequenceActor, unreal.Vector(0, 0, 0))
    lsa.set_actor_label("NF_PerfSequence")
    lsa.set_editor_property("level_sequence_asset", perf)
    ps = lsa.get_editor_property("playback_settings")
    ps.set_editor_property("auto_play", True)
    ps.set_editor_property("loop_count", unreal.MovieSceneSequenceLoopCount(0))
    ps.set_editor_property("finish_completion_state_override", unreal.MovieSceneCompletionModeOverride.FORCE_KEEP_STATE)
    lsa.set_editor_property("playback_settings", ps)
    lsa.set_editor_property("is_spatially_loaded", False)
    if not les.save_current_level():
        raise RuntimeError("save level")
    rep["status"] = "PASS_NF_SEQUENCE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_sequence.report.json", rep)
unreal.SystemLibrary.quit_editor()
