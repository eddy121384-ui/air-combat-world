"""North Taiwan forest world v1, canopy bake (UnrealEditor-Cmd, with RHI): tileable top-down canopy textures FROM THE GAME TREES.

Why: the far forest is the Landscape's canopy layer; if its colour / crown pattern is invented it never matches the near 3D trees and the
hand-over reads as a seam (ForestSpike B1a F10 failure). So the canopy layer is an orthographic bake of the same meshes / materials /
tint variants / densities the world uses.

Three 96 m tiles (toroidal placement: trees crossing an edge are repeated on the opposite edge, so each tile wraps seamlessly):
  broad  = 紅楠 A 65 % / crown B 35 %, variants 0-4;  acacia = 相思樹 C 70 % + A/B;  crypt = 柳杉 J rows 6 m.
Ground under the trees = the Landscape understory colour. Trees are StaticMeshActors forced to LOD1 (the far LODs are clump cards of the
same atlas). Captures (SceneCapture2D, orthographic, 1024 px = 9.4 cm / px): BaseColor, world Normal, SceneDepth -> canopy height.
Written to <ACW_NF_OUT>/bake/<tile>_{basecolor,normal,depth} (OpenEXR, half float; no extension) via RenderingLibrary.export_render_target; the 8-bit packing for
import is done offline (tools/ntw/forest_world/pack_canopy.py). Receipt: reports/nf_bake.report.json.
"""
import math
import os
import random
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import FORM_BARK_SRC, FORM_MESH, MAP, MAT, OUT, VARIANT_FORM, lib, write_report  # noqa: E402

TILE_M = 96.0
PX = 1024
BAKE = MAP + "/L_NF_CanopyBake_" + os.environ.get("ACW_NF_BAKE_REV", "2")   # one map per bake attempt
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rl = unreal.RenderingLibrary
rep = {"status": "FAIL_NF_BAKE", "tiles": {}, "error": None}
SCALE = {"A": (0.85, 1.25), "B": (0.80, 1.15), "C": (0.80, 1.15), "J": (0.85, 1.10)}
SEP = 25000.0   # tiles are laid out 250 m apart on the bake ground


def poisson(rng, n_target, r_min):
    pts = []
    tries = 0
    while len(pts) < n_target and tries < n_target * 60:
        tries += 1
        p = (rng.uniform(0, TILE_M), rng.uniform(0, TILE_M))
        ok = True
        for q in pts:
            dx = abs(p[0] - q[0]); dy = abs(p[1] - q[1])
            dx, dy = min(dx, TILE_M - dx), min(dy, TILE_M - dy)
            if dx * dx + dy * dy < r_min * r_min:
                ok = False
                break
        if ok:
            pts.append(p)
    return pts


def layout(kind, rng):
    trees = []
    if kind == "crypt":
        for i in range(16):
            for j in range(16):
                if rng.random() < 0.04:
                    continue
                trees.append(((i + 0.5) * 6.0 + rng.gauss(0, 0.35), (j + 0.5) * 6.0 + rng.gauss(0, 1.0), "J", rng.choice((8, 8, 9))))
        return trees
    n = int(TILE_M * TILE_M / 1e4 * 121)            # world density: 121 trees / ha of tree cover
    for (x, y) in poisson(rng, n, 5.2):
        u = rng.random()
        if kind == "acacia":
            f = "C" if u < 0.7 else ("A" if u < 0.88 else "B")
        else:
            f = "A" if u < 0.65 else "B"
        v = rng.choice([k for k, ff in VARIANT_FORM.items() if ff == f])
        trees.append((x, y, f, v))
    return trees


def place(kind, ox, oy, meshes, barks, leaves, rng):
    n = 0
    for (x, y, f, v) in layout(kind, rng):
        s = rng.uniform(*SCALE[f])
        for dx in (-TILE_M, 0.0, TILE_M):
            for dy in (-TILE_M, 0.0, TILE_M):
                px, py = x + dx, y + dy
                if not (-14 <= px <= TILE_M + 14 and -14 <= py <= TILE_M + 14):
                    continue
                a = ues.spawn_actor_from_object(meshes[f], unreal.Vector(ox + px * 100.0, oy + py * 100.0, 0.0),
                                                unreal.Rotator(0, 0, rng.uniform(0, 360)) if f != "J" else unreal.Rotator(0, 0, rng.uniform(0, 360)))
                a.set_actor_scale3d(unreal.Vector(s, s, s * rng.uniform(0.92, 1.08)))
                c = a.get_component_by_class(unreal.StaticMeshComponent)
                c.set_material(0, barks[f])
                c.set_material(1, leaves[v])
                c.set_editor_property("forced_lod_model", 2)   # 1-based: 2 = LOD1
                n += 1
    return n


def capture(label, ox, oy, source, fmt, name):
    rt = rl.create_render_target2d(unreal.EditorLevelLibrary.get_editor_world(), PX, PX, fmt, unreal.LinearColor(0, 0, 0, 0), False)
    cap = ues.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(ox + TILE_M * 50.0, oy + TILE_M * 50.0, 20000.0), unreal.Rotator(0, -90, 0))
    c = cap.get_component_by_class(unreal.SceneCaptureComponent2D)
    c.set_editor_property("projection_type", unreal.CameraProjectionMode.ORTHOGRAPHIC)
    c.set_editor_property("ortho_width", TILE_M * 100.0)
    c.set_editor_property("capture_source", source)
    c.set_editor_property("texture_target", rt)
    c.set_editor_property("capture_every_frame", False)
    c.set_editor_property("capture_on_movement", False)
    c.capture_scene()
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    c.capture_scene()
    rl.export_render_target(unreal.EditorLevelLibrary.get_editor_world(), rt, str(OUT / "bake"), name)
    ues.destroy_actor(cap)
    return name


try:
    (OUT / "bake").mkdir(parents=True, exist_ok=True)
    if lib.does_asset_exist(BAKE):
        raise RuntimeError(BAKE + " exists: use a new ACW_NF_BAKE_REV")
    if not les.new_level(BAKE):
        raise RuntimeError("new_level")
    meshes = {f: lib.load_asset(p) for f, p in FORM_MESH.items()}
    barks = {f: lib.load_asset(MAT + "/" + s.replace("M_TL_", "M_NF_")) for f, s in FORM_BARK_SRC.items()}
    leaves = {v: lib.load_asset(MAT + "/MI_NF_Leaf_V%d" % v) for v in VARIANT_FORM}
    # ground: understory colour of M_NF_Landscape (dark, mottled average), a big plane under all tiles
    gm = lib.load_asset(MAT + "/M_NF_BakeGround")
    if gm is None:
        gm = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_NF_BakeGround", MAT, unreal.Material, unreal.MaterialFactoryNew())
        mel = unreal.MaterialEditingLibrary
        col = mel.create_material_expression(gm, unreal.MaterialExpressionConstant3Vector, -300, 0)
        col.set_editor_property("constant", unreal.LinearColor(0.0235, 0.0285, 0.013, 1))
        mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
        mel.recompile_material(gm)
        lib.save_asset(MAT + "/M_NF_BakeGround")
    g = ues.spawn_actor_from_object(lib.load_asset("/Engine/BasicShapes/Plane"), unreal.Vector(30000, 0, -30), unreal.Rotator(0, 0, 0))
    g.set_actor_scale3d(unreal.Vector(1200, 400, 1))
    g.get_component_by_class(unreal.StaticMeshComponent).set_material(0, gm)
    rng = random.Random(20261019)
    for i, kind in enumerate(("broad", "acacia", "crypt")):
        ox, oy = i * SEP, 0.0
        n = place(kind, ox, oy, meshes, barks, leaves, rng)
        rep["tiles"][kind] = {"actors": n, "origin_cm": [ox, oy]}
    unreal.EditorLevelLibrary.editor_invalidate_viewports()
    unreal.AutomationLibrary.finish_loading_before_screenshot()   # block on shader compilation / streaming before any capture
    for i, kind in enumerate(("broad", "acacia", "crypt")):
        ox, oy = i * SEP, 0.0
        rep["tiles"][kind]["files"] = [
            capture(kind, ox, oy, unreal.SceneCaptureSource.SCS_BASE_COLOR, unreal.TextureRenderTargetFormat.RTF_RGBA16F, kind + "_basecolor"),
            capture(kind, ox, oy, unreal.SceneCaptureSource.SCS_NORMAL, unreal.TextureRenderTargetFormat.RTF_RGBA16F, kind + "_normal"),
            capture(kind, ox, oy, unreal.SceneCaptureSource.SCS_SCENE_DEPTH, unreal.TextureRenderTargetFormat.RTF_RGBA16F, kind + "_depth")]
    rep["tile_m"], rep["px"], rep["capture_height_cm"] = TILE_M, PX, 20000.0
    les.save_current_level()
    rep["status"] = "PASS_NF_BAKE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_bake.report.json", rep)
unreal.SystemLibrary.quit_editor()
