"""Runtime gate prep (UnrealEditor-Cmd -nullrhi): make L_NF_Yangmingshan ready to cook / package as a self-running game scene.

1. Velocity, scoped: PR #50 disabled WPO velocity for the WHOLE project (r.Velocity.EnableVertexDeformation=0) because the tree materials'
   slow distance-driven WPO forced every tree into a velocity pass. A global switch would also break motion vectors of any future
   animated WPO material (wind, water, flags, rotors) under TSR / motion blur. Here the same effect is applied per primitive:
   world_position_offset_writes_velocity = False on every tree HISM only (17,351 components), so the global cvar can be removed.
2. NF_PerfSequence auto-play ON (LS_NF_Perf_P: 3 held review stills, then the 117 s / 240 m/s hero flight) - the packaged game has no
   Movie Render Queue; the level sequence drives the camera and World Partition streams around it exactly as in a player flight.
Receipt: reports/nf_gate_prep.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAP, find_actor, write_report  # noqa: E402

PROP = "world_position_offset_writes_velocity"
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
rep = {"status": "FAIL_NF_GATE_PREP", "error": None}
try:
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    wpl = unreal.WorldPartitionBlueprintLibrary
    wpl.load_actors([d.get_editor_property("guid") for d in wpl.get_actor_descs() if str(d.get_editor_property("label")).startswith("NF_Trees_")])
    n, before = 0, set()
    for a in ues.get_all_level_actors():
        if not a.get_actor_label().startswith("NF_Trees_"):
            continue
        a.modify()
        for h in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            before.add(bool(h.get_editor_property(PROP)))
            h.modify()
            h.set_editor_property(PROP, False)
            n += 1
    rep["tree_hism"] = n
    rep["velocity_flag_before"] = sorted(before)
    lsa = find_actor("NF_PerfSequence")
    ps = lsa.get_editor_property("playback_settings")
    ps.set_editor_property("auto_play", True)
    lsa.modify()
    lsa.set_editor_property("playback_settings", ps)
    rep["auto_play_sequence"] = lsa.get_editor_property("level_sequence_asset").get_path_name()
    les.save_current_level()
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save dirty packages")
    rep["status"] = "PASS_NF_GATE_PREP" if n == 17351 else "FAIL_NF_GATE_PREP"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_gate_prep.report.json", rep)
unreal.SystemLibrary.quit_editor()
