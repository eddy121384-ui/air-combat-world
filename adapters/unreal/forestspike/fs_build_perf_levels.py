"""ForestSpike B0 stage 4: build standalone-game perf levels (UE5.8, UnrealEditor-Cmd).

Each config becomes its own saved level /Game/ForestSpike/Perf/L_FSP_<name> (arm visibility, instance counts, cull
distance, ground material instance with the S state, a CameraActor that is the player's view, optionally a Level
Sequence that flies a pose list at a fixed 60 fps timeline). The standalone game (-game, no editor viewport) then runs
the level under the CSV profiler; no Python is needed at run time.

Env: ACW_FS_PERF_SPEC  json: {"configs": [ {"name", "arm": "A"|"B", "s": 0|1, "und": 0|1, "ds_m", "ws_m",
                              "count_a", "count_b", "pose": {...} | "path": {"poses": [...], "fps": 60, "frames_per_pose": 120}} ]}
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from fs_common import INPUTS, LEVEL, MAT_DIR, ROOT, enu_to_ue_cm, find_actor, lib, mel, read_json, tools, write_report  # noqa: E402
from fs_instances import ARCHETYPES, load_pool, pivot_shift, place  # noqa: E402

SPEC = json.loads(Path(os.environ["ACW_FS_PERF_SPEC"]).read_text(encoding="utf-8"))
PERF_DIR = ROOT + "/Perf"
built = []


def aim(p):
    import math
    h, pt = math.radians(p["heading_deg"]), math.radians(p["pitch_deg"])
    loc = enu_to_ue_cm(*p["eye_enu"])
    d = (math.sin(h) * math.cos(pt), math.cos(h) * math.cos(pt), math.sin(pt))
    tgt = unreal.Vector(loc.x + d[0] * 100000.0, loc.y - d[1] * 100000.0, loc.z + d[2] * 100000.0)
    return loc, unreal.MathLibrary.find_look_at_rotation(loc, tgt)


def make_mic(name, parent, scalars):
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        mic = lib.load_asset(path)
    else:
        mic = tools.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mic.set_editor_property("parent", parent)
    for k, v in scalars.items():
        mel.set_material_instance_scalar_parameter_value(mic, k, float(v))
    mel.update_material_instance(mic)
    lib.save_asset(path)
    return mic


def add_sequence(actors, cfg, cam):
    """Level Sequence that moves `cam` through the pose list; 60 fps; auto-plays at game start."""
    path = cfg["path"]
    fps = int(path.get("fps", 60))
    fpp = int(path.get("frames_per_pose", 120))
    poses = path["poses"]
    seq_name = "LS_FSP_" + cfg["name"]
    seq = tools.create_asset(seq_name, PERF_DIR, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    total = fpp * (len(poses) - 1) + 1
    seq.set_playback_start(0)
    seq.set_playback_end(total)
    binding = seq.add_possessable(cam)
    track = binding.add_track(unreal.MovieScene3DTransformTrack)
    section = track.add_section()
    section.set_range(0, total)
    ch = list(section.get_all_channels())      # loc x y z, rot x y z (roll pitch yaw), scale x y z
    unreal.log("FS_SEQ channels: %s" % [str(c.get_name()) if hasattr(c, "get_name") else str(c) for c in ch])
    for i, p in enumerate(poses):
        loc, rot = aim(p)
        f = unreal.FrameNumber(i * fpp)
        vals = [loc.x, loc.y, loc.z, rot.roll, rot.pitch, rot.yaw, 1.0, 1.0, 1.0]
        for c, v in zip(ch, vals):
            c.add_key(f, float(v), 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, unreal.MovieSceneKeyInterpolation.LINEAR)
    cut = seq.add_track(unreal.MovieSceneCameraCutTrack)
    cs = cut.add_section()
    cs.set_range(0, total)
    cs.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding))
    lib.save_asset(PERF_DIR + "/" + seq_name)
    lsa = actors.spawn_actor_from_class(unreal.LevelSequenceActor, unreal.Vector(0, 0, 0))
    lsa.set_actor_label("FS_Sequence")
    lsa.set_editor_property("level_sequence_asset", seq)
    ps = lsa.get_editor_property("playback_settings")
    ps.set_editor_property("auto_play", True)
    ps.set_editor_property("loop_count", unreal.MovieSceneSequenceLoopCount(0))
    lsa.set_editor_property("playback_settings", ps)
    return total


def build(cfg, meshes, pool, count, cols):
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not levels.load_level(LEVEL):
        raise RuntimeError("load " + LEVEL)
    arm = cfg["arm"]
    ds = float(cfg.get("ds_m", 500.0))
    comp = lambda label: find_actor(actors, label).get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)  # noqa: E731
    ha = comp("FS_ArmA")
    hb = [comp("FS_ArmB_" + a) for a in ARCHETYPES]
    if arm == "A":
        place(ha, pool, cols, range(min(int(cfg["count_a"]), count)), pivot_shift(meshes["Tree_A"]))
        for h in hb:
            h.clear_instances()
    else:
        ha.clear_instances()
        n = int(cfg["count_b"])
        for vi, (h, a) in enumerate(zip(hb, ARCHETYPES)):
            idx = [i for i in range(min(n, count)) if int(pool[i * cols + 5]) == vi]
            place(h, pool, cols, idx, pivot_shift(meshes["Tree_B_" + a]))
    ha.set_editor_property("visible", arm == "A")
    for h in hb:
        h.set_editor_property("visible", arm == "B")
    for h in [ha] + hb:
        h.set_cull_distances(0.0, ds * 100.0)
    gp = lib.load_asset(MAT_DIR + "/M_FS_Ground")
    mic = make_mic("MI_FSP_" + cfg["name"], gp, {"SCore": cfg["s"], "SCtx": cfg["s"], "Und": cfg.get("und", 0), "dS": ds,
                                                  "wS": float(cfg.get("ws_m", 100.0))})
    for label in ("FS_Terrain_Core", "FS_Terrain_Context"):
        find_actor(actors, label).get_component_by_class(unreal.StaticMeshComponent).set_material(0, mic)
    pose = cfg.get("pose") or cfg["path"]["poses"][0]
    loc, rot = aim(pose)
    cam = actors.spawn_actor_from_class(unreal.CameraActor, loc, rot)
    cam.set_actor_label("FS_PerfCamera")
    cc = cam.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", float(pose["fov_h_deg"]))
    cc.set_editor_property("aspect_ratio", 16.0 / 9.0)
    cc.set_editor_property("constrain_aspect_ratio", True)
    cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    frames = 0
    if "path" in cfg:
        frames = add_sequence(actors, cfg, cam)
    dest = PERF_DIR + "/L_FSP_" + cfg["name"]
    if lib.does_asset_exist(dest):
        lib.delete_asset(dest)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, dest):
        raise RuntimeError("save_map failed: " + dest)
    built.append({"name": cfg["name"], "level": dest, "sequence_frames": frames})


def main():
    assets = read_json(INPUTS.parent / "reports" / "fs_assets.report.json")
    meshes = assets["meshes"]
    if not lib.does_directory_exist(PERF_DIR):
        lib.make_directory(PERF_DIR)
    pool, count, cols = load_pool()
    for cfg in SPEC["configs"]:
        build(cfg, meshes, pool, count, cols)


try:
    main()
    status, err = "PASS_FS_PERF_LEVELS", None
except Exception:  # noqa: BLE001
    status, err = "FAIL_FS_PERF_LEVELS", traceback.format_exc()
    unreal.log_error(err)
write_report("fs_perf_levels.report.json", {"status": status, "levels": built, "error": err})
unreal.SystemLibrary.quit_editor()
