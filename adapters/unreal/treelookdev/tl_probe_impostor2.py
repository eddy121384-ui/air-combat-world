"""Probe 2 (GUI editor): drive Epic's AssetAction_StaticMeshImpostor on a COPY of the baseline tree and watch what it creates."""
import os, sys, time, traceback
sys.path.insert(0, os.path.dirname(__file__))
import unreal
from tl_common import write_report, lib, ROOT

SRC = ROOT + "/Meshes/Machilus/machilus_lod0/StaticMeshes/machilus_lod0"
DST_DIR = ROOT + "/ImpostorProbe"
DST = DST_DIR + "/IM_Source"
try:
    eps = unreal.get_default_object(unreal.EditorPerformanceSettings)
    eps.set_editor_property("throttle_cpu_when_not_foreground", False)
    eps.set_editor_property("monitor_editor_performance", False)
except Exception as exc:
    unreal.log_warning("perf settings: %s" % exc)
st = {"t0": time.monotonic(), "phase": "start", "n": 0, "log": []}
before = set()


def snapshot():
    return set(str(a) for a in lib.list_assets(ROOT, recursive=True))


def finish(status, err=None):
    try:
        unreal.unregister_slate_post_tick_callback(h)
    except Exception:
        pass
    after = snapshot()
    write_report("tl_probe_impostor2.report.json", {"status": status, "new_assets": sorted(after - before), "log": st["log"], "error": err,
                                                     "elapsed": time.monotonic() - st["t0"]})
    unreal.SystemLibrary.quit_editor()


def tick(dt):
    try:
        el = time.monotonic() - st["t0"]
        if el > 300:
            finish("TIMEOUT")
            return
        if st["phase"] == "start":
            st["n"] += 1
            if st["n"] < 120:  # let the editor UI settle
                return
            if not lib.does_directory_exist(DST_DIR):
                lib.make_directory(DST_DIR)
            if lib.does_asset_exist(DST):
                lib.delete_asset(DST)
            if not lib.duplicate_asset(SRC, DST):
                raise RuntimeError("duplicate failed")
            before.update(snapshot())
            lib.sync_browser_to_objects([DST])
            st["phase"], st["n"] = "sel", 0
            return
        if st["phase"] == "sel":
            st["n"] += 1
            if st["n"] < 30:
                return
            sel = unreal.EditorUtilityLibrary.get_selected_assets()
            st["log"].append("selected: %s" % [str(s.get_path_name()) for s in sel])
            bp = lib.load_asset("/ImpostorBaker/BP/AssetAction_StaticMeshImpostor")
            gc = bp.generated_class()
            cdo = unreal.get_default_object(gc)
            cdo.run()
            st["log"].append("run() called at %.1fs" % el)
            st["phase"], st["n"] = "wait", 0
            return
        if st["phase"] == "wait":
            st["n"] += 1
            if st["n"] % 120 == 0:
                new = snapshot() - before
                st["log"].append("t=%.0fs new assets: %d" % (el, len(new)))
                if len(new) > 3 and st["n"] > 600:
                    finish("PASS_PROBE2")
    except Exception:
        finish("FAIL_PROBE2", traceback.format_exc())


h = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
