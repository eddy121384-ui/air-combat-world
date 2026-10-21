"""North Taiwan forest - mobile forest profile: a sky dome for the MOBILE renderer (UnrealEditor-Cmd, with RHI).

The map's sky is the SkyAtmosphere component. The desktop renderer draws it as a full-screen pass; the mobile renderer only builds the
atmosphere LUTs and expects a sky-dome mesh with an "Is Sky" material (UE 5.8 SkyAtmosphereRendering.cpp: "Mobile must use a skydome
mesh with a sky material"). Without one the ES3.1 preview showed a black sky above the fog band - and a black real-time sky-light
capture, so the whole mobile forest went dark.

M_NF_SkyDome: unlit, opaque, Is Sky, emissive = SkyAtmosphereViewLuminance + SkyAtmosphereLightDiskLuminance (the same atmosphere,
read from its LUTs). It renders on BOTH renderers: the first version clipped itself on SM5 (Feature Level Switch on the opacity mask) to
leave the PC sky untouched, but the desktop renderer stops drawing its own atmosphere sky as soon as a sky mesh is in the scene ("your
scene contains a skydome mesh with a sky material but it does not cover that part of the screen") - so the dome is the sky everywhere.
Actor NF_SkyDome: /Engine/EngineSky/SM_SkySphere scaled to ~150 km radius, not spatially loaded, no shadow, no collision.
Re-running updates the material in place (rev 2: opaque). Receipt: reports/nf_mobile_sky.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, MAP, MAT, find_actor, lib, link, mel, tools, write_report  # noqa: E402

rep = {"status": "FAIL_NF_MOBILE_SKY", "error": None}
RADIUS_CM = 1.5e7
try:
    path = MAT + "/M_NF_SkyDome"
    if lib.does_asset_exist(path):
        mat = lib.load_asset(path)
        rep["material"] = "updated"
    else:
        mat = tools.create_asset("M_NF_SkyDome", MAT, unreal.Material, unreal.MaterialFactoryNew())
        add = E(mat, unreal.MaterialExpressionAdd, -300, 0)
        link(E(mat, unreal.MaterialExpressionSkyAtmosphereViewLuminance, -600, -60), "", add, "A")
        link(E(mat, unreal.MaterialExpressionSkyAtmosphereLightDiskLuminance, -600, 60), "", add, "B")
        mel.connect_material_property(add, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        rep["material"] = "created"
    for k, v in (("shading_model", unreal.MaterialShadingModel.MSM_UNLIT), ("blend_mode", unreal.BlendMode.BLEND_OPAQUE),
                 ("two_sided", True), ("is_sky", True)):
        mat.set_editor_property(k, v)
    mel.recompile_material(mat)
    lib.save_asset(path, only_if_is_dirty=False)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    if find_actor("NF_SkyDome"):
        rep["status"] = "PASS_NF_MOBILE_SKY"
        raise SystemExit
    mesh = lib.load_asset("/Engine/EngineSky/SM_SkySphere")
    r = mesh.get_bounds().get_editor_property("sphere_radius")
    a = ues.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0))
    a.set_actor_label("NF_SkyDome")
    a.set_actor_scale3d(unreal.Vector(1, 1, 1) * (RADIUS_CM / r))
    a.set_editor_property("is_spatially_loaded", False)
    c = a.static_mesh_component
    c.set_material(0, mat)
    c.set_cast_shadow(False)
    c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    rep["dome"] = {"mesh_radius_cm": r, "scale": RADIUS_CM / r}
    les.save_current_level()
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save")
    rep["status"] = "PASS_NF_MOBILE_SKY"
except SystemExit:
    pass
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_mobile_sky.report.json", rep)
unreal.SystemLibrary.quit_editor()
