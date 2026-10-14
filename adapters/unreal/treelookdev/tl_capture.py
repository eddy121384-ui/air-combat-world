"""TreeLookdev stage 2 (UnrealEditor-Cmd): SceneCapture2D -> RGBA8 FINAL_COLOR_LDR -> PNG at the golden-reference cameras.

Spec (env ACW_TL_SPEC): {"set", "res": [w, h], "warmup": 30, "settle": 8,
                          "jobs": [{"name", "view": <views.json name>, "lod": -1|0|1|2, "tree": true, "ev": null|float}]}
Cameras come from <GAME>/views.json (Blender metres -> UE cm): same eye, forward vector and horizontal FOV / ortho width.
lod = -1 is the engine's automatic screen-size selection; 0/1/2 force a LOD (comparison only).
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import CAPTURES, LEVEL, b2u, b2u_dir, find_actor, views, write_report  # noqa: E402

SPEC = json.loads(Path(os.environ["ACW_TL_SPEC"]).read_text(encoding="utf-8"))
OUT = CAPTURES / SPEC["set"]
OUT.mkdir(parents=True, exist_ok=True)
W, H = SPEC.get("res", [1920, 1080])
WARMUP, SETTLE = int(SPEC.get("warmup", 30)), int(SPEC.get("settle", 8))
VIEWS = {v["name"]: v for v in views()["views"]}

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.load_level(LEVEL):
    raise RuntimeError("failed to load " + LEVEL)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
tree = find_actor(actors, "TL_Machilus").get_component_by_class(unreal.StaticMeshComponent)
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


pp_vol = find_actor(actors, "TL_PostProcess")
sky = find_actor(actors, "TL_SkyLight").get_component_by_class(unreal.SkyLightComponent)
STAGE = SPEC.get("stage", {})


def apply_stage(job):
    """Exposure / sky bounce live on the level actors (a capture-component override proved unreliable)."""
    st = dict(STAGE, **job.get("stage", {}))
    s = pp_vol.get_editor_property("settings")
    if "ev" in st:
        s.set_editor_property("auto_exposure_bias", float(st["ev"]))
    if "saturation" in st:
        s.set_editor_property("override_color_saturation", True)
        sat = float(st["saturation"])
        s.set_editor_property("color_saturation", unreal.Vector4(sat, sat, sat, 1.0))
    pp_vol.set_editor_property("settings", s)
    if "lower" in st:
        c = st["lower"]
        sky.set_lower_hemisphere_color(unreal.LinearColor(c[0], c[1], c[2], 1.0))
    if "sky" in st:
        sky.set_intensity(float(st["sky"]))
    sky.recapture_sky()


leaf_base = tree.get_material(1)
leaf_mid = unreal.MaterialLibrary.create_dynamic_material_instance(world, leaf_base)
tree.set_material(1, leaf_mid)
LEAF = SPEC.get("leaf", {})


def apply_leaf(job):
    for k, v in dict(LEAF, **job.get("leaf", {})).items():
        if isinstance(v, (list, tuple)):
            leaf_mid.set_vector_parameter_value(k, unreal.LinearColor(v[0], v[1], v[2], 1.0))
        else:
            leaf_mid.set_scalar_parameter_value(k, float(v))


def configure(job):
    apply_leaf(job)
    tree.set_visibility(bool(job.get("tree", True)), False)
    tree.set_forced_lod_model(int(job.get("lod", -1)) + 1)
    apply_stage(job)
    v = VIEWS[job["view"]]
    loc = b2u(v["loc"])
    if "ortho_m" in v:
        cap.set_editor_property("projection_type", unreal.CameraProjectionMode.ORTHOGRAPHIC)
        cap.set_editor_property("ortho_width", float(v["ortho_m"]) * 100.0)
        # straight down, image up = Blender +Y (= UE -Y): yaw -90 then pitch -90 (Rotator is roll, pitch, yaw)
        cap_actor.set_actor_location_and_rotation(loc, unreal.Rotator(0.0, -90.0, -90.0), False, True)
    else:
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
    write_report("tl_capture.%s.report.json" % SPEC["set"], {
        "status": "PASS_TL_CAPTURE" if ok else "FAIL_TL_CAPTURE", "set": SPEC["set"], "captures": state["captures"],
        "elapsed_s": time.monotonic() - state["t0"], "error": err})
    unreal.SystemLibrary.quit_editor()


def tick(_dt):
    try:
        if time.monotonic() - state["t0"] > float(SPEC.get("timeout_s", 1800)):
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
