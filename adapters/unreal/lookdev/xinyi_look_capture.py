"""XinyiLook stage 3: fresh-process reopen check + hero-shot capture (UE5.8).

Runs in a new UnrealEditor-Cmd process after the level stage, so loading the
look level here is also the fresh-reopen persistence check (25 look tiles,
hero, backdrop, paint, tree HISM, Landscape material).

Rendering uses the accepted SceneCapture2D backend (runbook section 20):
SceneCapture2D -> RenderTarget(RGBA8) -> FINAL_COLOR_LDR -> PNG. Camera poses
and light presets are read from tools/lookdev/preview/shots.json, so each
Unreal frame has a like-for-like preview frame for comparison.

Time-of-day changes are transient; the level is never saved here.
Env: ACW_XINYI_LOOK_TOD    comma list (default "day,dusk,night")
     ACW_XINYI_LOOK_SHOTS  comma list (default: the 8 look-dev shots; cloud review shots from
                           tools/lookdev/clouds/cloud_review_shots.json may be listed too)
     ACW_XINYI_LOOK_CLOUDS off | low | high (default off: the accepted city suite stays cloud-
                           independent). low / high frames get a "__clouds-<quality>" suffix.
     ACW_XINYI_LOOK_PERF   optional comma list of shots to time after the captures: per shot,
                           PERF_N SceneCapture renders each followed by a 1-pixel readback
                           (forces a GPU sync), giving a same-view frame-time proxy.
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.environ.get("ACW_REPO_ROOT", ""), "adapters", "unreal", "lookdev"))
import unreal  # noqa: E402
from xinyi_look_common import (  # noqa: E402
    LOOK_LEVEL, LOOK_OUT, LOOK_PREFIX, RUNTIME_PREFIX, SHOTS, TERRAIN_LABEL, enu_to_ue_cm, lib, write_report,
)
from xinyi_look_clouds import apply_clouds, finish_shaders  # noqa: E402
from xinyi_look_tod import apply_tod  # noqa: E402

OUT = LOOK_OUT / "unreal" / "captures"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1920, 1080
WARMUP = 24
SETTLE = 8
TIMEOUT = 900.0
PNG = b"\x89PNG\r\n\x1a\n"

cfg = json.loads(SHOTS.read_text(encoding="utf-8"))
tods = [t for t in os.environ.get("ACW_XINYI_LOOK_TOD", "day,dusk,night").split(",") if t]
shots = [s for s in os.environ.get("ACW_XINYI_LOOK_SHOTS", ",".join(cfg["shots"])).split(",") if s]
CLOUD_SHOTS = SHOTS.parent.parent / "clouds" / "cloud_review_shots.json"
shot_specs = dict(cfg["shots"])
if CLOUD_SHOTS.is_file():
    shot_specs.update(json.loads(CLOUD_SHOTS.read_text(encoding="utf-8"))["shots"])
clouds_q = os.environ.get("ACW_XINYI_LOOK_CLOUDS", "off") or "off"
suffix = "" if clouds_q == "off" else "__clouds-%s" % clouds_q
perf_shots = [s for s in os.environ.get("ACW_XINYI_LOOK_PERF", "").split(",") if s]
PERF_WARM = 16
PERF_N = 40

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.load_level(LOOK_LEVEL):
    raise RuntimeError("failed to load %s" % LOOK_LEVEL)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

# ---- fresh-reopen persistence check -----------------------------------------
labels = {a.get_actor_label(): a for a in actors.get_all_level_actors()}
reopen = {
    "look_tiles": 0,
    "hero": LOOK_PREFIX + "Taipei101" in labels,
    "backdrop": LOOK_PREFIX + "BasinBackdrop" in labels,
    "paint": LOOK_PREFIX + "RoadPaint" in labels,
    "trees": 0,
    "landscape_material": None,
}
for label, a in labels.items():
    if label.startswith(RUNTIME_PREFIX):
        mesh = a.get_component_by_class(unreal.StaticMeshComponent).get_editor_property("static_mesh")
        if mesh is not None and "/Game/XinyiLook/" in mesh.get_path_name():
            reopen["look_tiles"] += 1
tree_actor = labels.get(LOOK_PREFIX + "Trees")
if tree_actor is not None:
    h = tree_actor.get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    reopen["trees"] = int(h.get_instance_count()) if h else 0
terrain = labels.get(TERRAIN_LABEL)
if terrain is not None:
    m = terrain.get_editor_property("landscape_material")
    reopen["landscape_material"] = m.get_path_name() if m else None
reopen_ok = (reopen["look_tiles"] == 25 and reopen["hero"] and reopen["backdrop"] and reopen["paint"]
             and reopen["trees"] > 0 and reopen["landscape_material"]
             and "M_XinyiGround" in reopen["landscape_material"])

# ---- capture rig ------------------------------------------------------------------
rt = unreal.RenderingLibrary.create_render_target2d(
    world, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(0, 0, 0, 1), False)
cap_actor = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 100000))
cap_actor.set_actor_label("XinyiLookCapture_Transient")
cap = cap_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
cap.set_editor_property("texture_target", rt)
cap.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
cap.set_editor_property("capture_every_frame", False)
cap.set_editor_property("capture_on_movement", False)
cap.set_editor_property("always_persist_rendering_state", True)
for cmd in ("r.ScreenPercentage 100", "r.MotionBlurQuality 0", "r.RayTracing 0"):
    unreal.SystemLibrary.execute_console_command(world, cmd)

queue = [(t, s) for t in tods for s in shots]
state = {"i": 0, "phase": "tod", "n": 0, "t0": time.monotonic(), "captures": [], "tod": None,
         "clouds": None, "perf": None}


def gpu_sync():
    """Block until the GPU has finished the last capture (1-pixel readback)."""
    unreal.RenderingLibrary.read_render_target_pixel(world, rt, 0, 0)


def run_perf():
    """Same-view frame-time proxy: PERF_N SceneCapture renders at W x H, each GPU-synchronised."""
    out = {}
    for shot in perf_shots:
        set_view(shot_specs[shot])
        for _ in range(PERF_WARM):
            cap.capture_scene()
        gpu_sync()
        ms = []
        for _ in range(PERF_N):
            t = time.perf_counter()
            cap.capture_scene()
            gpu_sync()
            ms.append((time.perf_counter() - t) * 1000.0)
        ms.sort()
        out[shot] = {"n": PERF_N, "median_ms": round(ms[len(ms) // 2], 2), "p10_ms": round(ms[len(ms) // 10], 2),
                     "p90_ms": round(ms[(len(ms) * 9) // 10], 2), "min_ms": round(ms[0], 2)}
    return {"method": "SceneCapture2D %dx%d FINAL_COLOR_LDR, capture_scene + 1px readback per sample "
                      "(GPU-synchronised wall time; includes a fixed readback / submit overhead)" % (W, H),
            "gpu": unreal.SystemLibrary.get_rhi_adapter_name() if hasattr(unreal.SystemLibrary, "get_rhi_adapter_name") else None,
            "clouds": clouds_q, "tod": state["tod"], "shots": out}


def set_view(spec):
    loc = enu_to_ue_cm(*spec["eye"])
    tgt = enu_to_ue_cm(*spec["target"])
    rot = unreal.MathLibrary.find_look_at_rotation(loc, tgt)
    cap_actor.set_actor_location_and_rotation(loc, rot, False, True)
    cap.set_editor_property("fov_angle", float(spec["fov"]))


def export(name):
    out = OUT / (name + ".png")
    if out.exists():
        out.unlink()
    cap.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, str(OUT), out.name)
    with out.open("rb") as fh:
        if fh.read(8) != PNG:
            raise RuntimeError("not a PNG: %s" % out)
    state["captures"].append({"name": name, "path": str(out), "bytes": out.stat().st_size})


def finish(ok, err=None):
    try:
        unreal.unregister_slate_post_tick_callback(handle)
    except Exception:
        pass
    status = "PASS_LOOK_CAPTURE" if ok and reopen_ok else "FAIL_LOOK_CAPTURE"
    write_report("look_capture.report.json", {
        "status": status,
        "reopen": reopen,
        "reopen_ok": bool(reopen_ok),
        "backend": "SceneCapture2D -> RTF_RGBA8 -> SCS_FINAL_COLOR_LDR -> export_render_target",
        "tods": tods,
        "shots": shots,
        "captures": state["captures"],
        "clouds": state["clouds"],
        "perf": state["perf"],
        "error": err,
        "level_saved": False,
        "elapsed_seconds": time.monotonic() - state["t0"],
    })
    try:
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    except Exception:
        pass
    unreal.SystemLibrary.quit_editor()


def tick(_dt):
    try:
        if time.monotonic() - state["t0"] > TIMEOUT:
            raise RuntimeError("capture timed out")
        if state["i"] >= len(queue):
            if perf_shots:
                state["perf"] = run_perf()
            finish(True)
            return
        tod, shot = queue[state["i"]]
        spec = shot_specs[shot]
        if state["tod"] != tod:
            apply_tod(world, actors, tod)
            state["clouds"] = apply_clouds(world, actors, clouds_q, tod)
            finish_shaders()   # no shader / streaming fallback in the first frames of a preset
            state["tod"] = tod
            state["phase"] = "warm"
            state["n"] = 0
        set_view(spec)
        if state["phase"] == "warm":
            cap.capture_scene()
            state["n"] += 1
            if state["n"] >= WARMUP:
                state["phase"] = "settle"
                state["n"] = 0
            return
        if state["phase"] == "settle":
            cap.capture_scene()
            state["n"] += 1
            if state["n"] >= SETTLE:
                state["phase"] = "shoot"
            return
        export("%s__%s%s" % (shot, tod, suffix))
        state["i"] += 1
        state["phase"] = "settle"
        state["n"] = 0
    except Exception:
        finish(False, traceback.format_exc())


if not reopen_ok:
    finish(False, "fresh-reopen check failed: %s" % json.dumps(reopen))
else:
    handle = unreal.register_slate_post_tick_callback(tick)
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
