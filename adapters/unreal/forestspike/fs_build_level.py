"""ForestSpike B0 stage 2: build /Game/ForestSpike/L_ForestSpike_B0 (UE5.8, UnrealEditor-Cmd).

Level contents (all new, isolated): fixed lighting rig, shared terrain (core + 6 km context), instance arms A and B
as HISMs placed from the deterministic pool (same positions for both arms; arm B splits by archetype).

Env: ACW_FS_N_A / ACW_FS_N_B   instance counts (default 26000 each; the capture stage re-places any count)
     ACW_FS_DS_M               instance end-cull distance in metres (default 600; the B0 gate sets the frozen d_S)
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from fs_common import INPUTS, LEVEL, MAT_DIR, lib, read_json, write_report  # noqa: E402
from fs_instances import ARCHETYPES, add_hism, load_pool, pivot_shift, place  # noqa: E402
from fs_rig import spawn_rig  # noqa: E402
N_A = int(os.environ.get("ACW_FS_N_A", "26000"))
N_B = int(os.environ.get("ACW_FS_N_B", "26000"))
DS_M = float(os.environ.get("ACW_FS_DS_M", "600"))


def main():
    assets = read_json(INPUTS.parent / "reports" / "fs_assets.report.json")
    if assets.get("status") != "PASS_FS_ASSETS":
        raise RuntimeError("run fs_build_assets.py first")
    meshes = assets["meshes"]
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if lib.does_asset_exist(LEVEL):
        lib.delete_asset(LEVEL)
    if not levels.new_level(LEVEL):
        raise RuntimeError("new_level failed: " + LEVEL)
    spawn_rig(actors)

    for label, key in (("FS_Terrain_Core", "Terrain_Core"), ("FS_Terrain_Context", "Terrain_Context")):
        m = lib.load_asset(meshes[key]["asset"])
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        a.set_actor_label(label)
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_static_mesh(m)
        a.set_actor_location(unreal.Vector(*pivot_shift(meshes[key])), False, False)
        c.set_material(0, lib.load_asset(MAT_DIR + "/MI_FS_Ground_SOn"))
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)

    pool, count, cols = load_pool()
    holder = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    holder.set_actor_label("FS_ArmA")
    ha = add_hism(holder, lib.load_asset(meshes["Tree_A"]["asset"]))
    place(ha, pool, cols, range(min(N_A, count)), pivot_shift(meshes["Tree_A"]))
    comps = [ha]
    arm_b = {}
    for vi, arch in enumerate(ARCHETYPES):
        hb_actor = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
        hb_actor.set_actor_label("FS_ArmB_" + arch)
        info = meshes["Tree_B_" + arch]
        hb = add_hism(hb_actor, lib.load_asset(info["asset"]))
        idx = [i for i in range(min(N_B, count)) if int(pool[i * cols + 5]) == vi]
        place(hb, pool, cols, idx, pivot_shift(info))
        hb.set_editor_property("visible", False)      # arm B is hidden in the saved level; captures toggle arms
        comps.append(hb)
        arm_b[arch] = len(idx)
    for c in comps:
        c.set_cull_distances(0.0, DS_M * 100.0)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        c.set_cast_shadow(True)
    counts = {"arm_a": int(ha.get_instance_count()), "arm_b": arm_b}
    if not levels.save_current_level():
        raise RuntimeError("save_current_level failed")
    return counts


try:
    counts = main()
    status, err = "PASS_FS_LEVEL", None
except Exception:  # noqa: BLE001
    counts, status, err = {}, "FAIL_FS_LEVEL", traceback.format_exc()
    unreal.log_error(err)
write_report("fs_level.report.json", {"status": status, "level": LEVEL, "instances": counts, "end_cull_m": DS_M, "error": err})
unreal.SystemLibrary.quit_editor()
