"""TreeLookdev budget experiment, stage 2 (UnrealEditor-Cmd): SceneCapture2D PNGs of candidates A / B / C at the same cameras.

Spec (env ACW_TL_SPEC): {"set", "res": [w, h], "warmup", "settle",
  "jobs": [{"name", "view": <views_budget.json name>, "cand": "A"|"B"|"C"|"D", "mode": "single"|"patch", "lod": -1|0|1|2|3}]}
Same method / stage as tl_capture.py (calibrated look-dev level, unchanged); lod = -1 is the engine's automatic screen-size selection.
Every candidate (single tree + 100-instance HISM patch) is pre-built hidden in the level; a job only toggles visibility.
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_budget_common import PATH, make_patch  # noqa: E402
from tl_common import CAPTURES, GAME, LEVEL, b2u, b2u_dir, find_actor, lib, write_report  # noqa: E402

SPEC = json.loads(Path(os.environ["ACW_TL_SPEC"]).read_text(encoding="utf-8"))
OUT = CAPTURES / SPEC["set"]
OUT.mkdir(parents=True, exist_ok=True)
W, H = SPEC.get("res", [1920, 1080])
WARMUP, SETTLE = int(SPEC.get("warmup", 40)), int(SPEC.get("settle", 10))
VIEWS = {v["name"]: v for v in json.loads((GAME / "views_budget.json").read_text(encoding="utf-8"))["views"]}

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.load_level(LEVEL):
    raise RuntimeError("failed to load " + LEVEL)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

# the original tree actor becomes candidate A single; B / C single + all patches are extra hidden actors
COMPS = {}
orig = find_actor(actors, "TL_Machilus")
COMPS[("A", "single")] = orig.get_component_by_class(unreal.StaticMeshComponent)
for key in ("B", "C", "D"):
    mesh = lib.load_asset(PATH[key])
    a = actors.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0))
    a.set_actor_label("TL_Machilus_" + key)
    COMPS[(key, "single")] = a.get_component_by_class(unreal.StaticMeshComponent)
for key in ("A", "B", "C", "D"):
    COMPS[(key, "patch")] = make_patch(actors, lib.load_asset(PATH[key]), "TL_Patch_" + key)

rt = unreal.RenderingLibrary.create_render_target2d(world, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                    unreal.LinearColor(0, 0, 0, 1), False)
cap_actor = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 100000))
cap_actor.set_actor_label("TL_Capture_Transient")
cap = cap_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
for prop, val in (("texture_target", rt), ("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),
                  ("capture_every_frame", False), ("capture_on_movement", False), ("always_persist_rendering_state", True)):
    cap.set_editor_property(prop, val)
for cmd in ("r.ScreenPercentage 100", "r.MotionBlurQuality 0", "r.RayTracing 0", "foliage.ForceLOD -1", "r.ForceLOD -1"):
    unreal.SystemLibrary.execute_console_command(world, cmd)
state = {"i": 0, "phase": "prep", "n": 0, "t0": time.monotonic(), "captures": []}
PNG = b"\x89PNG\r\n\x1a\n"


def configure(job):
    for comp in COMPS.values():
        comp.set_visibility(False, False)
    comp = COMPS[(job["cand"], job["mode"])]
    comp.set_visibility(True, False)
    comp.set_forced_lod_model(int(job.get("lod", -1)) + 1)
    v = VIEWS[job["view"]]
    loc = b2u(v["loc"])
    cap.set_editor_property("projection_type", unreal.CameraProjectionMode.PERSPECTIVE)
    cap.set_editor_property("fov_angle", float(v["hfov_deg"]))
    d = b2u_dir(v["fwd"])
    tgt = unreal.Vector(loc.x + d.x * 1e5, loc.y + d.y * 1e5, loc.z + d.z * 1e5)
    cap_actor.set_actor_location_and_rotation(loc, unreal.MathLibrary.find_look_at_rotation(loc, tgt), False, True)


def export(job):
    out = OUT / (job["name"] + ".png")
    if out.exists():
        out.unlink()
    cap.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, str(OUT), out.name)
    with out.open("rb") as fh:
        if fh.read(8) != PNG:
            raise RuntimeError("not a PNG: %s" % out)
    (OUT / (job["name"] + ".json")).write_text(json.dumps({"job": job, "view": VIEWS[job["view"]], "res": [W, H]}, indent=1))
    state["captures"].append(job["name"])


def finish(ok, err=None):
    try:
        unreal.unregister_slate_post_tick_callback(handle)
    except Exception:  # noqa: BLE001
        pass
    write_report("tl_budget_capture.%s.report.json" % SPEC["set"], {
        "status": "PASS_TL_BUDGET_CAPTURE" if ok else "FAIL_TL_BUDGET_CAPTURE", "set": SPEC["set"], "captures": state["captures"],
        "elapsed_s": time.monotonic() - state["t0"], "error": err})
    unreal.SystemLibrary.quit_editor()


def tick(_dt):
    try:
        if time.monotonic() - state["t0"] > float(SPEC.get("timeout_s", 3000)):
            raise RuntimeError("capture timed out")
        if state["i"] >= len(SPEC["jobs"]):
            finish(True)
            return
        job = SPEC["jobs"][state["i"]]
        if state["phase"] == "prep":
            configure(job)
            try:
                unreal.AutomationLibrary.finish_loading_before_screenshot()
            except Exception:  # noqa: BLE001
                pass
            state["phase"], state["n"] = "warm", 0
            return
        if state["phase"] in ("warm", "settle"):
            cap.capture_scene()
            state["n"] += 1
            limit = WARMUP if state["phase"] == "warm" else SETTLE
            if state["n"] >= limit:
                state["phase"], state["n"] = ("settle", 0) if state["phase"] == "warm" else ("shoot", 0)
            return
        export(job)
        state["i"] += 1
        state["phase"] = "prep"
    except Exception:  # noqa: BLE001
        finish(False, traceback.format_exc())


handle = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
