"""Far-LOD research: octahedral impostor bake of the world's tree variants (UnrealEditor-Cmd, WITH RHI).

Method (published: Ryan Brucks' octahedral impostors, the basis of UE's experimental ImpostorBaker plugin; Kuro's Wuthering Waves
mobile far forest is also a ring-of-cameras impostor bake): every tree variant is photographed by an orthographic camera from N x N
directions on a HEMI-octahedron (upper hemisphere; trees are seen from the side or above), the views are packed into one atlas,
and at runtime a camera-facing card blends the 3 frames nearest to the actual view direction.

Inputs are the SAME meshes (LOD3 = the clump-card LOD the 3D forest draws at the hand-over distance) and the SAME world materials (M_NF_* bark + MI_NF_Leaf_V<n>) the 3D forest uses, so the impostor
colour / crown pattern matches the tree it replaces. Per form (A, B, C, J): world normal + scene depth (geometry is shared by the
form's tint variants); per variant (0-9): base colour.
Captures: SceneCapture2D ortho, width = 2 R (R = mesh bounding-sphere radius), FRAME_PX per frame, from 200 m along the frame axis.
Output: <ACW_NF_OUT>/fi_bake/<rev>/{F}_{nd|dp}_{k:03d}, V{v}_bc_{k:03d} (OpenEXR half) + fi_bake.json (frame axes, the capture camera's
actual right / up vectors, R, centre) for tools/ntw/forest_world/fi_pack.py. Nothing in /Game/NorthForest is modified; the bake level is
/Game/FarLOD/Maps/L_FI_Bake_<rev>. Receipt: reports/fi_bake.report.json.
"""
import json
import math
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import FORM_BARK_SRC, FORM_MESH, MAT, OUT, VARIANT_FORM, lib, write_report  # noqa: E402

N = int(os.environ.get("ACW_FI_FRAMES", "16"))
FRAME_PX = int(os.environ.get("ACW_FI_CAPTURE_PX", "256"))
LOD = int(os.environ.get("ACW_FI_LOD", "3"))   # the LOD the 3D trees actually draw beyond ~300 m (clump cards)
REV = os.environ.get("ACW_FI_REV", "1")
DIST = 20000.0
LEVEL = "/Game/FarLOD/Maps/L_FI_Bake_" + REV
DST = OUT / "fi_bake" / REV
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rl = unreal.RenderingLibrary
ml = unreal.MathLibrary
rep = {"status": "FAIL_FI_BAKE", "frames": N, "capture_px": FRAME_PX, "lod": LOD, "rev": REV, "error": None}


def norm(v):
    m = math.sqrt(sum(c * c for c in v))
    return tuple(c / m for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def hemi_dec(ex, ey):
    """Hemi-octahedral decode, e in [-1, 1]^2 -> unit vector with z >= 0 (same formula as the runtime HLSL)."""
    tx, ty = (ex + ey) * 0.5, (ex - ey) * 0.5
    return norm((tx, ty, 1.0 - abs(tx) - abs(ty)))


def frame_axes(d):
    """Frame basis shared with the runtime HLSL: right = normalize(cross(hint, d)), up = cross(d, right)."""
    hint = (0.0, 0.0, 1.0) if abs(d[2]) < 0.999 else (1.0, 0.0, 0.0)
    r = norm(cross(hint, d))
    return r, cross(d, r)


def vec(t):
    return unreal.Vector(t[0], t[1], t[2])


def make_capture(world, source):
    rt = rl.create_render_target2d(world, FRAME_PX, FRAME_PX, unreal.TextureRenderTargetFormat.RTF_RGBA16F, unreal.LinearColor(0, 0, 0, 0), False)
    cap = ues.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    c = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
    c.set_editor_property("projection_type", unreal.CameraProjectionMode.ORTHOGRAPHIC)
    c.set_editor_property("capture_source", source)
    c.set_editor_property("texture_target", rt)
    c.set_editor_property("capture_every_frame", False)
    c.set_editor_property("capture_on_movement", False)
    c.set_editor_property("primitive_render_mode", unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
    return cap, c, rt


try:
    t0 = time.time()
    DST.mkdir(parents=True, exist_ok=True)
    if not lib.does_directory_exist("/Game/FarLOD/Maps"):
        lib.make_directory("/Game/FarLOD/Maps")
    if lib.does_asset_exist(LEVEL):
        raise RuntimeError(LEVEL + " exists: use a new ACW_FI_REV")
    if not les.new_level(LEVEL):
        raise RuntimeError("new_level")
    world = unreal.EditorLevelLibrary.get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, "r.TextureStreaming 0")   # full-resolution leaf textures in every capture
    meshes = {f: lib.load_asset(p) for f, p in FORM_MESH.items()}
    barks = {f: lib.load_asset(MAT + "/" + s.replace("M_TL_", "M_NF_")) for f, s in FORM_BARK_SRC.items()}
    leaves = {v: lib.load_asset(MAT + "/MI_NF_Leaf_V%d" % v) for v in VARIANT_FORM}
    actors, forms = {}, {}
    for v, f in sorted(VARIANT_FORM.items()):
        a = ues.spawn_actor_from_object(meshes[f], unreal.Vector(v * 100000.0, 0.0, 0.0), unreal.Rotator(0, 0, 0))
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_material(0, barks[f])
        c.set_material(1, leaves[v])
        c.set_editor_property("forced_lod_model", LOD + 1)   # 1-based
        c.set_editor_property("cast_shadow", False)
        actors[v] = a
    for f, m in meshes.items():
        b = m.get_bounds()
        sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        rep.setdefault("lod_screen_sizes", {})[f] = [round(x, 4) for x in sms.get_lod_screen_sizes(m)]
        forms[f] = {"center": [b.origin.x, b.origin.y, b.origin.z], "R": b.sphere_radius * 1.02, "extent": [b.box_extent.x, b.box_extent.y, b.box_extent.z]}
    caps = {k: make_capture(world, s) for k, s in (("bc", unreal.SceneCaptureSource.SCS_BASE_COLOR), ("nd", unreal.SceneCaptureSource.SCS_NORMAL),
                                                  ("dp", unreal.SceneCaptureSource.SCS_SCENE_DEPTH))}
    frames = []
    for j in range(N):
        for i in range(N):
            d = hemi_dec(i / (N - 1) * 2.0 - 1.0, j / (N - 1) * 2.0 - 1.0)
            r, u = frame_axes(d)
            frames.append({"i": i, "j": j, "d": d, "right": r, "up": u})
    # warm-up: one capture of every variant, then block on shader compilation / texture loading
    for v, a in actors.items():
        _, c, _ = caps["bc"]
        c.clear_show_only_components()
        c.show_only_actor_components(a, False)
        c.set_editor_property("ortho_width", forms[VARIANT_FORM[v]]["R"] * 2.0)
        c.capture_scene()
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    sign_seen = set()
    n_exp = 0
    for v, a in sorted(actors.items()):
        f = VARIANT_FORM[v]
        first = v == min(k for k, ff in VARIANT_FORM.items() if ff == f)
        fc, R = forms[f]["center"], forms[f]["R"]
        loc0 = a.get_actor_location()
        center = (loc0.x + fc[0], loc0.y + fc[1], loc0.z + fc[2])
        kinds = ("bc", "nd", "dp") if first else ("bc",)
        for k, fr in enumerate(frames):
            d, up = fr["d"], fr["up"]
            rot = ml.make_rot_from_xz(vec(tuple(-x for x in d)), vec(up))
            pos = vec(tuple(center[q] + d[q] * DIST for q in range(3)))
            cam_r = rot.get_right_vector()
            cam_u = rot.get_up_vector()
            sr = dot((cam_r.x, cam_r.y, cam_r.z), fr["right"])
            su = dot((cam_u.x, cam_u.y, cam_u.z), up)
            sign_seen.add((round(sr), round(su)))
            if v == 0:
                fr["cam_right"], fr["cam_up"] = [cam_r.x, cam_r.y, cam_r.z], [cam_u.x, cam_u.y, cam_u.z]
            for kind in kinds:
                cap, c, rt = caps[kind]
                cap.set_actor_location_and_rotation(pos, rot, False, False)
                c.clear_show_only_components()
                c.show_only_actor_components(a, False)
                c.set_editor_property("ortho_width", R * 2.0)
                c.capture_scene()
                name = ("V%d_bc_%03d" % (v, k)) if kind == "bc" else ("%s_%s_%03d" % (f, kind, k))
                rl.export_render_target(world, rt, str(DST), name)
                n_exp += 1
        unreal.log("FI_BAKE variant %d done (%d exports, %.0f s)" % (v, n_exp, time.time() - t0))
    if len(sign_seen) != 1:
        raise RuntimeError("capture camera basis is not consistent with the frame axes: %s" % sorted(sign_seen))
    meta = {"frames": N, "capture_px": FRAME_PX, "lod": LOD, "dist_cm": DIST, "forms": forms, "variant_form": {str(k): f for k, f in VARIANT_FORM.items()},
            "cam_sign_right_up": list(next(iter(sign_seen))), "frame_list": frames}
    (DST / "fi_bake.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    les.save_current_level()
    rep.update(exports=n_exp, seconds=round(time.time() - t0, 1), out=str(DST), forms=forms, cam_sign_right_up=meta["cam_sign_right_up"])
    rep["status"] = "PASS_FI_BAKE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("fi_bake.report.json", rep)
unreal.SystemLibrary.quit_editor()
