"""ForestSpike B0 stage 3: SceneCapture2D capture jobs (UE5.8, UnrealEditor-Cmd).

Backend: SceneCapture2D -> RenderTarget(RGBA8) -> FINAL_COLOR_LDR -> PNG (the accepted XinyiLook backend).
Spec: JSON file named by env ACW_FS_SPEC (written by tools/forestspike/make_spec.py):
  {"set": "name", "res": [1920, 1080], "warmup": 24, "settle": 6, "id_gamma": 1.0, "jobs": [ job, ... ]}
  job = {"name", "kind": "visual" | "id" | "topdown", "pose": {eye_enu, heading_deg, pitch_deg, fov_h_deg},
         "arm": "A" | "B" | "none", "count_a", "count_b", "s_core", "s_ctx", "und", "ds_m", "ws_m"}
  topdown job: {"name", "kind": "topdown", "arm", "counts": [n, ...], "ortho_m": 1000, "px": 2048}
Outputs <captures>/<set>/<name>.png (+ .json sidecar) and reports/fs_capture.<set>.report.json.
The ID pass renders every instance (no end cull) with unlit emissive pixel codes; classification for any
candidate d_S happens offline (tools/forestspike/analyze_ids.py).
"""
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from fs_common import CAPTURES, INPUTS, LEVEL, MAT_DIR, enu_to_ue_cm, find_actor, lib, read_json, write_report  # noqa: E402
from fs_instances import ARCHETYPES, load_pool, pivot_shift, place  # noqa: E402

SPEC = json.loads(Path(os.environ["ACW_FS_SPEC"]).read_text(encoding="utf-8"))
OUT = CAPTURES / SPEC["set"]
OUT.mkdir(parents=True, exist_ok=True)
W, H = SPEC.get("res", [1920, 1080])
WARMUP = int(SPEC.get("warmup", 24))
SETTLE = int(SPEC.get("settle", 6))
ID_GAMMA = float(SPEC.get("id_gamma", 1.0))
TIMEOUT = float(SPEC.get("timeout_s", 1800))
FAR_END_CULL_CM = 2.0e6
ID_FLAGS_OFF = SPEC.get("id_flags_off", ["Atmosphere", "Fog", "VolumetricFog", "PostProcessing", "AntiAliasing"])

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.load_level(LEVEL):
    raise RuntimeError("failed to load " + LEVEL)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assets = read_json(INPUTS.parent / "reports" / "fs_assets.report.json")
meshes = assets["meshes"]
pool, pool_count, pool_cols = load_pool()


def comp_of(label, cls=unreal.StaticMeshComponent):
    a = find_actor(actors, label)
    if a is None:
        raise RuntimeError("missing level actor " + label)
    return a.get_component_by_class(cls)


terrain = [comp_of("FS_Terrain_Core"), comp_of("FS_Terrain_Context")]
hism_a = comp_of("FS_ArmA", unreal.HierarchicalInstancedStaticMeshComponent)
hism_b = [comp_of("FS_ArmB_" + a, unreal.HierarchicalInstancedStaticMeshComponent) for a in ARCHETYPES]

mid_ground = unreal.MaterialLibrary.create_dynamic_material_instance(world, lib.load_asset(MAT_DIR + "/M_FS_Ground"))
mid_a = unreal.MaterialLibrary.create_dynamic_material_instance(world, lib.load_asset(MAT_DIR + "/MI_FS_Tree_A"))
mid_b = unreal.MaterialLibrary.create_dynamic_material_instance(world, lib.load_asset(MAT_DIR + "/MI_FS_Tree_B"))
for t in terrain:
    t.set_material(0, mid_ground)
hism_a.set_material(0, mid_a)
for h in hism_b:
    h.set_material(0, mid_b)

rt = unreal.RenderingLibrary.create_render_target2d(
    world, W, H, unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(0, 0, 0, 1), False)
rts = {(W, H): rt}


def rt_for(w_px, h_px):
    if (w_px, h_px) not in rts:
        rts[(w_px, h_px)] = unreal.RenderingLibrary.create_render_target2d(
            world, w_px, h_px, unreal.TextureRenderTargetFormat.RTF_RGBA8, unreal.LinearColor(0, 0, 0, 1), False)
    return rts[(w_px, h_px)]


cap_actor = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 100000))
cap_actor.set_actor_label("FS_Capture_Transient")
cap = cap_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
cap.set_editor_property("texture_target", rt)
cap.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
cap.set_editor_property("capture_every_frame", False)
cap.set_editor_property("capture_on_movement", False)
cap.set_editor_property("always_persist_rendering_state", True)
for cmd in ("r.ScreenPercentage 100", "r.MotionBlurQuality 0", "r.RayTracing 0"):
    unreal.SystemLibrary.execute_console_command(world, cmd)

# expand topdown sweeps into one step per count
steps = []
for j in SPEC["jobs"]:
    if j["kind"] == "topdown":
        for n in j["counts"]:
            s = dict(j)
            s["name"] = "%s_n%d" % (j["name"], n)
            s["count_%s" % j["arm"].lower()] = n
            steps.append(s)
    else:
        steps.append(j)

cur = {"a": None, "b": None, "dbg": None, "mode": None, "gamma": None, "ortho": None}
state = {"i": 0, "phase": "prep", "n": 0, "t0": time.monotonic(), "captures": [], "placement_s": 0.0, "rt": rt, "res": (W, H)}
PNG = b"\x89PNG\r\n\x1a\n"


def set_flags(dbg):
    flags = []
    for name in (ID_FLAGS_OFF if dbg else []):
        s = unreal.EngineShowFlagsSetting()
        s.set_editor_property("show_flag_name", name)
        s.set_editor_property("enabled", False)
        flags.append(s)
    cap.set_editor_property("show_flag_settings", flags)


def configure(job):
    kind = job["kind"]
    dbg = kind in ("id", "topdown")
    arm = job.get("arm", "none")
    ds_cm = FAR_END_CULL_CM if dbg else float(job.get("ds_m", 600.0)) * 100.0
    t0 = time.monotonic()
    if arm == "A" and cur["a"] != job.get("count_a", cur["a"] or 26000):
        n = int(job.get("count_a", 26000))
        place(hism_a, pool, pool_cols, range(min(n, pool_count)), pivot_shift(meshes["Tree_A"]))
        cur["a"] = n
    if arm == "B" and cur["b"] != job.get("count_b", cur["b"] or 26000):
        n = int(job.get("count_b", 26000))
        for vi, (h, arch) in enumerate(zip(hism_b, ARCHETYPES)):
            idx = [i for i in range(min(n, pool_count)) if int(pool[i * pool_cols + 5]) == vi]
            place(h, pool, pool_cols, idx, pivot_shift(meshes["Tree_B_" + arch]))
        cur["b"] = n
    state["placement_s"] += time.monotonic() - t0
    hism_a.set_visibility(arm == "A", False)
    for h in hism_b:
        h.set_visibility(arm == "B", False)
    for h in [hism_a] + hism_b:
        h.set_cull_distances(0.0, ds_cm)
    mid_ground.set_scalar_parameter_value("Dbg", 1.0 if dbg else 0.0)
    mid_ground.set_scalar_parameter_value("IdGamma", ID_GAMMA)
    mid_ground.set_scalar_parameter_value("SCore", float(job.get("s_core", 1)))
    mid_ground.set_scalar_parameter_value("SCtx", float(job.get("s_ctx", 1)))
    mid_ground.set_scalar_parameter_value("Und", float(job.get("und", 1)))
    mid_ground.set_scalar_parameter_value("dS", float(job.get("ds_m", 600.0)))
    mid_ground.set_scalar_parameter_value("wS", float(job.get("ws_m", 120.0)))
    for m in (mid_a, mid_b):
        m.set_scalar_parameter_value("Dbg", 1.0 if dbg else 0.0)
        m.set_scalar_parameter_value("IdGamma", ID_GAMMA)
    set_flags(dbg)


def set_view(job):
    if job["kind"] == "topdown":
        ow = float(job.get("ortho_m", 1000.0)) * 100.0
        px = int(job.get("px", 2048))
        state["rt"], state["res"] = rt_for(px, px), (px, px)
        cap.set_editor_property("texture_target", state["rt"])
        cap.set_editor_property("projection_type", unreal.CameraProjectionMode.ORTHOGRAPHIC)
        cap.set_editor_property("ortho_width", ow)
        cap_actor.set_actor_location_and_rotation(unreal.Vector(0.0, 0.0, float(job.get("cam_z_m", 1000.0)) * 100.0), unreal.Rotator(0.0, -90.0, -90.0), False, True)
        return
    p = job["pose"]
    state["rt"], state["res"] = rt, (W, H)
    cap.set_editor_property("texture_target", rt)
    cap.set_editor_property("projection_type", unreal.CameraProjectionMode.PERSPECTIVE)
    e, n, u = p["eye_enu"]
    h, pt = math.radians(p["heading_deg"]), math.radians(p["pitch_deg"])
    d = (math.sin(h) * math.cos(pt), math.cos(h) * math.cos(pt), math.sin(pt))     # ENU direction
    loc = enu_to_ue_cm(e, n, u)
    tgt = unreal.Vector(loc.x + d[0] * 100000.0, loc.y - d[1] * 100000.0, loc.z + d[2] * 100000.0)
    cap_actor.set_actor_location_and_rotation(loc, unreal.MathLibrary.find_look_at_rotation(loc, tgt), False, True)
    cap.set_editor_property("fov_angle", float(p["fov_h_deg"]))


def gpu_sync():
    unreal.RenderingLibrary.read_render_target_pixel(world, rt, 0, 0)


def export(name, job):
    out = OUT / (name + ".png")
    if out.exists():
        out.unlink()
    cap.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, state["rt"], str(OUT), out.name)
    with out.open("rb") as fh:
        if fh.read(8) != PNG:
            raise RuntimeError("not a PNG: %s" % out)
    side = {"name": name, "job": job, "res": list(state["res"]), "id_gamma": ID_GAMMA, "counts": {"a": cur["a"], "b": cur["b"]}}
    (OUT / (name + ".json")).write_text(json.dumps(side, indent=1))
    state["captures"].append({"name": name, "bytes": out.stat().st_size})


def finish(ok, err=None):
    try:
        unreal.unregister_slate_post_tick_callback(handle)
    except Exception:  # noqa: BLE001
        pass
    write_report("fs_capture.%s.report.json" % SPEC["set"], {
        "status": "PASS_FS_CAPTURE" if ok else "FAIL_FS_CAPTURE", "set": SPEC["set"], "res": [W, H],
        "captures": state["captures"], "placement_s": state["placement_s"],
        "elapsed_s": time.monotonic() - state["t0"], "rhi_adapter": unreal.SystemLibrary.get_rhi_adapter_name()
        if hasattr(unreal.SystemLibrary, "get_rhi_adapter_name") else None, "error": err})
    try:
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    except Exception:  # noqa: BLE001
        pass
    unreal.SystemLibrary.quit_editor()


def tick(_dt):
    try:
        if time.monotonic() - state["t0"] > TIMEOUT:
            raise RuntimeError("capture timed out")
        if state["i"] >= len(steps):
            finish(True)
            return
        job = steps[state["i"]]
        if state["phase"] == "prep":
            configure(job)
            try:
                unreal.AutomationLibrary.finish_loading_before_screenshot()
            except Exception as exc:  # noqa: BLE001
                unreal.log_warning("finish_loading_before_screenshot: %s" % exc)
            state["phase"], state["n"] = "warm", 0
        set_view(job)
        if state["phase"] == "warm":
            cap.capture_scene()
            state["n"] += 1
            if state["n"] >= WARMUP:
                state["phase"], state["n"] = "settle", 0
            return
        if state["phase"] == "settle":
            cap.capture_scene()
            state["n"] += 1
            if state["n"] >= SETTLE:
                state["phase"] = "shoot"
            return
        export(job["name"], job)
        state["i"] += 1
        # same material / count state for the next job is re-applied cheaply; warm-up restarts only on a state change
        state["phase"], state["n"] = "prep", 0
    except Exception:  # noqa: BLE001
        finish(False, traceback.format_exc())


handle = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
