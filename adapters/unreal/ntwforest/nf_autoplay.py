"""Toggle NF_PerfSequence auto-play in L_NF_Yangmingshan (UnrealEditor-Cmd -nullrhi).

ACW_NF_AUTOPLAY=1 for real-time performance runs (the perf sequence drives NF_Cam), 0 for Movie Render Queue renders: with auto-play on,
the level's own sequence player and MRQ's player both drive NF_Cam and the level's player can win (seen in render nf_flight_n_05: the
perf sequence's held stills were rendered instead of the flight). Receipt: reports/nf_autoplay.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAP, find_actor, write_report  # noqa: E402

on = os.environ.get("ACW_NF_AUTOPLAY", "0") == "1"
rep = {"status": "FAIL_NF_AUTOPLAY", "auto_play": on, "error": None}
try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load")
    a = find_actor("NF_PerfSequence")
    ps = a.get_editor_property("playback_settings")
    ps.set_editor_property("auto_play", on)
    a.set_editor_property("playback_settings", ps)
    if not les.save_current_level():
        raise RuntimeError("save")
    rep["sequence"] = a.get_editor_property("level_sequence_asset").get_path_name()
    rep["status"] = "PASS_NF_AUTOPLAY"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
write_report("nf_autoplay.report.json", rep)
unreal.SystemLibrary.quit_editor()
