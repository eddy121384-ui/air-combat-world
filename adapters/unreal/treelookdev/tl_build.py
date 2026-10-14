"""TreeLookdev stage 1 (UnrealEditor-Cmd): import the 紅楠 game version, build materials, LODs and the look-dev level.

Inputs (from tools/treegen/machilus_game.py + machilus_game_textures.py): <GAME>/glb/machilus_lod{0,1,2}.glb,
<GAME>/textures/*.png, <GAME>/views.json. Output receipt: reports/tl_build.report.json.

Materials are plain material graphs (no custom HLSL):
* M_TL_LeafCards: Masked, two-sided, Two Sided Foliage shading. BaseColor = atlas x lerp(TintLo, TintHi, VC.R)
  x lerp(OcclMin, 1, VC.G); subsurface = BaseColor x SSSColor x SSS; normal = atlas normal flattened toward the
  (crown-blended) vertex normal; opacity mask = atlas alpha (clip 0.4, mips scaled for alpha coverage).
* M_TL_Bark: opaque; tileable bark, lerp to the young-twig colour by VC.R (the golden shader's radius blend).
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import (GAME, LEVEL, LOD_SCREENS, MAT_DIR, MESH_DIR, ROOT, TEX_DIR, b2u, b2u_dir, ensure_dir, lib, mel,  # noqa: E402
                       tools, views, write_report)

sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
report = {"status": "FAIL_TL_BUILD", "textures": {}, "materials": [], "mesh": {}, "error": None}


# ----------------------------------------------------------------------------- textures
def import_texture(png, name, srgb, normal=False, alpha_coverage=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(png))
    task.set_editor_property("destination_path", TEX_DIR)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    tools.import_asset_tasks([task])
    path = TEX_DIR + "/" + name
    tex = lib.load_asset(path)
    if tex is None:
        raise RuntimeError("texture import failed: %s" % png)
    tex.set_editor_property("srgb", srgb)
    if normal:
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
    if alpha_coverage is not None:
        for prop, val in (("do_scale_mips_for_alpha_coverage", True),
                          ("alpha_coverage_thresholds", unreal.Vector4(0.0, 0.0, 0.0, alpha_coverage))):
            try:
                tex.set_editor_property(prop, val)
            except Exception as exc:  # noqa: BLE001
                unreal.log_warning("texture %s: %s (%s)" % (name, prop, exc))
    lib.save_asset(path)
    rec = {"path": path, "size": [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()],
           "compression": str(tex.get_editor_property("compression_settings")), "srgb": srgb}
    try:
        rec["memory_bytes"] = int(tex.blueprint_get_memory_size())
    except Exception as exc:  # noqa: BLE001
        rec["memory_bytes"] = "n/a: %s" % exc
    report["textures"][name] = rec
    return tex


# ----------------------------------------------------------------------------- materials
def fresh_material(name):
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        lib.delete_asset(path)
    mat = tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    return mat, path


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(mat, name, val, x, y):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=val)


def vec(mat, name, rgb, x, y):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
             default_value=unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))


def tex_param(mat, name, tex, x, y, normal=False):
    t = E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=tex)
    t.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if normal
                          else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    return t


def link(a, out, b, pin):
    if not mel.connect_material_expressions(a, out, b, pin):
        raise RuntimeError("connect failed %s.%s -> %s" % (a.get_name(), out, pin))


def finish(mat, path):
    mel.recompile_material(mat)
    lib.save_asset(path)
    report["materials"].append(path)


def leaf_material(bc, nm):
    mat, path = fresh_material("M_TL_LeafCards")
    for prop, val in (("blend_mode", unreal.BlendMode.BLEND_MASKED), ("two_sided", True),
                      ("shading_model", next(getattr(unreal.MaterialShadingModel, n) for n in dir(unreal.MaterialShadingModel)
                                             if "FOLIAGE" in n.upper())),
                      ("opacity_mask_clip_value", 0.4)):
        mat.set_editor_property(prop, val)
    t = tex_param(mat, "LeafBC", bc, -1400, 0)
    n = tex_param(mat, "LeafN", nm, -1400, 500, normal=True)
    vc = E(mat, unreal.MaterialExpressionVertexColor, -1400, -400)
    lo, hi = vec(mat, "TintLo", (0.82, 0.86, 0.8), -1100, -500), vec(mat, "TintHi", (1.18, 1.12, 1.0), -1100, -350)
    tint = E(mat, unreal.MaterialExpressionLinearInterpolate, -850, -400)
    link(lo, "", tint, "A")
    link(hi, "", tint, "B")
    link(vc, "R", tint, "Alpha")
    occ = E(mat, unreal.MaterialExpressionLinearInterpolate, -850, -200, const_b=1.0)
    link(scalar(mat, "OcclMin", 0.2, -1100, -200), "", occ, "A")
    link(vc, "G", occ, "Alpha")
    m1 = E(mat, unreal.MaterialExpressionMultiply, -650, -100)
    link(t, "RGB", m1, "A")
    link(tint, "", m1, "B")
    m2 = E(mat, unreal.MaterialExpressionMultiply, -450, -100)
    link(m1, "", m2, "A")
    link(occ, "", m2, "B")
    m3 = E(mat, unreal.MaterialExpressionMultiply, -250, -100)
    link(m2, "", m3, "A")
    link(scalar(mat, "Brightness", 0.42, -450, 50), "", m3, "B")
    mel.connect_material_property(m3, "", unreal.MaterialProperty.MP_BASE_COLOR)
    sss = E(mat, unreal.MaterialExpressionMultiply, -250, 150)
    link(m3, "", sss, "A")
    link(vec(mat, "SSSColor", (0.75, 0.95, 0.3), -450, 200), "", sss, "B")
    sss2 = E(mat, unreal.MaterialExpressionMultiply, -50, 150)
    link(sss, "", sss2, "A")
    link(scalar(mat, "SSS", 0.4, -250, 300), "", sss2, "B")
    mel.connect_material_property(sss2, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    flat = E(mat, unreal.MaterialExpressionLinearInterpolate, -650, 500)
    link(n, "RGB", flat, "A")
    link(E(mat, unreal.MaterialExpressionConstant3Vector, -900, 650, constant=unreal.LinearColor(0, 0, 1, 1)), "", flat, "B")
    link(scalar(mat, "NormalFlatten", 0.35, -900, 750), "", flat, "Alpha")
    mel.connect_material_property(flat, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(scalar(mat, "Roughness", 0.72, -250, 400), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, "Specular", 0.2, -250, 480), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(t, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    finish(mat, path)
    return mat


def bark_material(bc, nm):
    mat, path = fresh_material("M_TL_Bark")
    t = tex_param(mat, "BarkBC", bc, -900, 0)
    n = tex_param(mat, "BarkN", nm, -900, 400, normal=True)
    vc = E(mat, unreal.MaterialExpressionVertexColor, -900, -300)
    lp = E(mat, unreal.MaterialExpressionLinearInterpolate, -500, 0)
    link(t, "RGB", lp, "A")
    link(vec(mat, "TwigColor", (0.06, 0.05, 0.026), -700, -150), "", lp, "B")
    link(vc, "R", lp, "Alpha")
    # same stage compensation as the leaves: the UE stage is brighter (EV +0.8, sky 4) than the Cycles stage
    bb = E(mat, unreal.MaterialExpressionMultiply, -300, 0)
    link(lp, "", bb, "A")
    link(scalar(mat, "BarkBrightness", 0.5, -500, 150), "", bb, "B")
    mel.connect_material_property(bb, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(n, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(scalar(mat, "Roughness", 0.88, -500, 300), "", unreal.MaterialProperty.MP_ROUGHNESS)
    finish(mat, path)
    return mat


def flat_material(name, rgb, rough):
    mat, path = fresh_material(name)
    c = E(mat, unreal.MaterialExpressionConstant3Vector, -500, 0, constant=unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1))
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(mat, "Roughness", rough, -500, 200), "", unreal.MaterialProperty.MP_ROUGHNESS)
    finish(mat, path)
    return mat


# ----------------------------------------------------------------------------- mesh
def import_mesh(glb, dest):
    if lib.does_directory_exist(dest):
        lib.delete_directory(dest)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    if not mgr.import_asset(dest, unreal.InterchangeManager.create_source_data(str(glb)), params):
        raise RuntimeError("Interchange import failed: %s" % glb)
    found = [(str(p).split(".")[0], lib.load_asset(p)) for p in lib.list_assets(dest, recursive=True)]
    meshes = [(p, o) for p, o in found if o is not None and o.get_class().get_name() == "StaticMesh"]
    if len(meshes) != 1:
        raise RuntimeError("%s produced %d static meshes" % (glb, len(meshes)))
    return meshes[0]


def audit(mesh):
    b = mesh.get_bounds()
    out = {"lods": mesh.get_num_lods(), "screens": list(sub.get_lod_screen_sizes(mesh)),
           "triangles": [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
           "vertices": [sub.get_number_verts(mesh, i) for i in range(mesh.get_num_lods())],
           "sections": [mesh.get_num_sections(i) for i in range(mesh.get_num_lods())],
           "slots": [str(m.get_editor_property("material_slot_name")) for m in mesh.static_materials],
           "section_slots": [[sub.get_lod_material_slot(mesh, i, s) for s in range(mesh.get_num_sections(i))]
                             for i in range(mesh.get_num_lods())],
           "bounds_origin_cm": [b.origin.x, b.origin.y, b.origin.z], "bounds_extent_cm": [b.box_extent.x, b.box_extent.y, b.box_extent.z],
           "sphere_radius_cm": b.sphere_radius}
    return out


def build_tree(m_bark, m_leaf):
    path, mesh = import_mesh(GAME / "glb" / "machilus_lod0.glb", MESH_DIR + "/Machilus")
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    report["mesh"]["imported_lod0"] = audit(mesh)
    for lod in (1, 2):
        r = sub.import_lod(mesh, lod, str(GAME / "glb" / ("machilus_lod%d.glb" % lod)))
        report["mesh"]["import_lod%d" % lod] = r
    for lod in range(mesh.get_num_lods()):
        bs = sub.get_lod_build_settings(mesh, lod)
        for prop, val in (("recompute_normals", False), ("recompute_tangents", True), ("use_mikk_t_space", True),
                          ("use_full_precision_u_vs", True), ("remove_degenerates", False), ("generate_lightmap_u_vs", False)):
            try:
                bs.set_editor_property(prop, val)
            except Exception as exc:  # noqa: BLE001
                unreal.log_warning("build settings %s: %s" % (prop, exc))
        sub.set_lod_build_settings(mesh, lod, bs)
    # material slots: glTF primitive 0 = bark, 1 = leaf cards, in every LOD
    mats = [unreal.StaticMaterial(material_interface=m_bark, material_slot_name="Bark"),
            unreal.StaticMaterial(material_interface=m_leaf, material_slot_name="LeafCards")]
    mesh.set_editor_property("static_materials", mats)
    for lod in range(mesh.get_num_lods()):
        for s in range(mesh.get_num_sections(lod)):
            sub.set_lod_material_slot(mesh, min(s, 1), lod, s)
    if not sub.set_lod_screen_sizes(mesh, LOD_SCREENS):
        raise RuntimeError("set_lod_screen_sizes failed")
    lib.save_asset(path)
    report["mesh"]["asset"] = path
    report["mesh"]["final"] = audit(mesh)
    return mesh


# ----------------------------------------------------------------------------- level
def spawn(cls, label, loc=(0.0, 0.0, 0.0), rot=None):
    a = actors.spawn_actor_from_class(cls, unreal.Vector(*loc), rot or unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    return a


def mesh_actor(label, mesh, mat, loc, scale):
    a = spawn(unreal.StaticMeshActor, label, loc)
    c = a.get_component_by_class(unreal.StaticMeshComponent)
    c.set_static_mesh(mesh)
    if mat is not None:
        c.set_material(0, mat)
    a.set_actor_scale3d(unreal.Vector(*scale))
    return a


def build_level(tree, m_ground, m_grey):
    if lib.does_asset_exist(LEVEL):
        # it is the editor startup map, so it cannot be deleted while loaded: rebuild its content in place
        if not levels.load_level(LEVEL):
            raise RuntimeError("load_level failed")
        for a in list(actors.get_all_level_actors()):
            actors.destroy_actor(a)
    elif not levels.new_level(LEVEL):
        raise RuntimeError("new_level failed")
    v = views()
    sun = spawn(unreal.DirectionalLight, "TL_Sun", (0, 0, 50000))
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.set_actor_rotation(unreal.MathLibrary.make_rot_from_x(b2u_dir(v["sun_travel_dir_blender"])), False)
    for prop, val in (("atmosphere_sun_light", True), ("light_source_angle", 0.6), ("dynamic_shadow_distance_movable_light", 60000.0),
                      ("dynamic_shadow_cascades", 4), ("cascade_distribution_exponent", 2.5), ("contact_shadow_length", 0.03)):
        try:
            sc.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("sun %s: %s" % (prop, exc))
    sc.set_intensity(SUN_LUX)
    sc.set_light_color(unreal.LinearColor(1.0, 0.96, 0.9, 1.0))
    ac = spawn(unreal.SkyAtmosphere, "TL_SkyAtmosphere").get_component_by_class(unreal.SkyAtmosphereComponent)
    ac.set_editor_property("aerial_perspective_start_depth", 2.0)
    sky = spawn(unreal.SkyLight, "TL_SkyLight", (0, 0, 30000))
    skc = sky.get_component_by_class(unreal.SkyLightComponent)
    skc.set_mobility(unreal.ComponentMobility.MOVABLE)
    skc.set_editor_property("real_time_capture", True)
    skc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
    skc.set_intensity(SKY_INTENSITY)
    skc.set_editor_property("lower_hemisphere_is_black", True)
    skc.set_lower_hemisphere_color(unreal.LinearColor(0.5, 0.55, 0.3, 1.0))  # ground bounce (Cycles has it; a black lower hemisphere blacks out the crown underside)
    pp = spawn(unreal.PostProcessVolume, "TL_PostProcess")
    pp.set_editor_property("unbound", True)
    s = pp.get_editor_property("settings")
    for prop, val in (("override_auto_exposure_method", True), ("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL),
                      ("override_auto_exposure_apply_physical_camera_exposure", True), ("auto_exposure_apply_physical_camera_exposure", False),
                      ("override_auto_exposure_bias", True), ("auto_exposure_bias", EXPOSURE_EV),
                      ("override_bloom_intensity", True), ("bloom_intensity", 0.0),
                      ("override_motion_blur_amount", True), ("motion_blur_amount", 0.0),
                      ("override_vignette_intensity", True), ("vignette_intensity", 0.0),
                      ("override_color_saturation", True), ("color_saturation", unreal.Vector4(0.9, 0.9, 0.9, 1.0))):
        try:
            s.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("pp %s: %s" % (prop, exc))
    pp.set_editor_property("settings", s)
    plane = lib.load_asset("/Engine/BasicShapes/Plane")
    cyl = lib.load_asset("/Engine/BasicShapes/Cylinder")
    mesh_actor("TL_Ground", plane, m_ground, (0, 0, 0), (4000, 4000, 1))
    mesh_actor("TL_ScaleFigure_1p7m", cyl, m_grey, (400.0, 300.0, 85.0), (0.44, 0.44, 1.7))
    t = mesh_actor("TL_Machilus", tree, None, (0, 0, 0), (1, 1, 1))
    t.get_component_by_class(unreal.StaticMeshComponent).set_editor_property("cast_shadow", True)
    levels.save_current_level()


SUN_LUX = float(os.environ.get("ACW_TL_SUN_LUX", "11.0"))
SKY_INTENSITY = float(os.environ.get("ACW_TL_SKY", "4.0"))
EXPOSURE_EV = float(os.environ.get("ACW_TL_EV", "0.8"))

try:
    for d in (ROOT, TEX_DIR, MAT_DIR, MESH_DIR):
        ensure_dir(d)
    T = GAME / "textures"
    bc = import_texture(T / "T_Machilus_LeafAtlas_BC.png", "T_Machilus_LeafAtlas_BC", True, alpha_coverage=0.4)
    nm = import_texture(T / "T_Machilus_LeafAtlas_N.png", "T_Machilus_LeafAtlas_N", False, normal=True)
    bbc = import_texture(T / "T_Machilus_Bark_BC.png", "T_Machilus_Bark_BC", True)
    bnm = import_texture(T / "T_Machilus_Bark_N.png", "T_Machilus_Bark_N", False, normal=True)
    m_leaf = leaf_material(bc, nm)
    m_bark = bark_material(bbc, bnm)
    m_ground = flat_material("M_TL_Ground", (0.045, 0.055, 0.022), 0.95)
    m_grey = flat_material("M_TL_Grey", (0.25, 0.25, 0.26), 0.6)
    tree = build_tree(m_bark, m_leaf)
    build_level(tree, m_ground, m_grey)
    report["lighting"] = dict(sun_lux=SUN_LUX, sky=SKY_INTENSITY, exposure_ev=EXPOSURE_EV)
    report["status"] = "PASS_TL_BUILD"
except Exception:  # noqa: BLE001
    report["error"] = traceback.format_exc()
    unreal.log_error(report["error"])
write_report("tl_build.report.json", report)
unreal.SystemLibrary.quit_editor()
