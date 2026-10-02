"""Cheap Cloud Renderer v0 (EXPERIMENTAL) - UE5.8 adapter (editor Python).

A third cloud renderer next to the volumetric HIGH / LOW profiles in xinyi_look_clouds.py, built on
the SAME renderer-agnostic cloud state:

  cloud_state_v0.json -> build_clouds.py -> clouds_v0.cells.json      (state: where / what kind)
                      -> build_cloud_cheap.py -> clouds_v0.cheap.json (CHEAP renderer detail: lobes)

Every cell is one StaticMeshActor holding an inward-facing unit proxy box scaled to the cell's lobe
bounds; its 8 lobes + base plane + squash + variation seed + bounding radius travel in the 36
custom-primitive-data floats.
M_XinyiClouds_Cheap (translucent, unlit, no depth test) intersects the view ray analytically with
the lobes (tools/lookdev/shaders/xinyi_clouds_cheap.hlsl). One primitive per cell keeps the engine's
per-primitive translucency sort between cells; inside a cell the optical depth is order-independent.

Nothing here is saved into the look level: the cheap actors are spawned transiently by the capture
process only when ACW_XINYI_LOOK_CLOUDS=cheap, so OFF / LOW / HIGH and the saved level are unchanged.
"""
import json

import unreal
from xinyi_look_common import LOOK_OUT, LOOK_PREFIX, MAT_DIR, MESH_DIR, REPO, TEX_DIR, ensure_dir, lib, mel, tools

CHEAP_DIR = LOOK_OUT / "clouds" / "cheap"
MATERIAL = MAT_DIR + "/M_XinyiClouds_Cheap"
NOISE = TEX_DIR + "/T_XinyiCloudNoise"
BOX_DIR = MESH_DIR + "/CloudCheapBox"
LABEL = LOOK_PREFIX + "CheapCloud_"
CULL_CM = 4.9e6          # proxy boxes beyond ~49 km are culled; the shader fades them out from ~38 km
# The impostors are the only translucency in the look scene, so the separate (after-DOF) translucency
# pass renders them at QUARTER resolution (480 x 270 at 1080p, bilinear upsample): the cost is mostly
# per-pixel shading (UHD 770, move phase over OFF: 100 % +4..+39 ms, 50 % +4..+13 ms, 25 % +1..+6 ms)
# and the soft subject hides the lower resolution. Global renderer setting, applied only in the cheap
# capture process.
CVARS = {"r.SeparateTranslucencyScreenPercentage": 25}

# Per-time-of-day calibration (material-instance parameters; lighting itself comes from the sky
# atmosphere sun and the real-time sky light, so DAY / DUSK / NIGHT follow the accepted rig).
#   K1 = (sigma 1/m, erosion, density noise, ambient scale)
#   K2 = (sun scale, silver lining, fade end m, multiple-scattering floor)
#   GLOW = city light on cloud bases (night only)
# Dusk: as in the volumetric renderer, multiply-scattered orange sun flooding the shaded volumes gives
# flat ochre cotton balls; a low MS floor + double sky fill keeps warm tops / edges over cool bodies.
TOD = {
    "day": {"K1": (0.03, 1.0, 0.45, 0.75), "K2": (1.0, 1.0, 46000.0, 0.2), "GLOW": (0.0, 0.0, 0.0)},
    "dusk": {"K1": (0.03, 1.0, 0.45, 1.5), "K2": (0.9, 1.0, 46000.0, 0.08), "GLOW": (0.0, 0.0, 0.0)},
    "night": {"K1": (0.03, 1.0, 0.45, 0.75), "K2": (1.0, 0.6, 46000.0, 0.2), "GLOW": (0.02, 0.014, 0.008)},
}


# ---------------------------------------------------------------------------------------------
# asset stage
# ---------------------------------------------------------------------------------------------

def _expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def _connect(src, out, dst, pin, failures):
    if not mel.connect_material_expressions(src, out, dst, pin):
        failures.append("connect %s.%s -> %s" % (src.get_class().get_name(), out or "default", pin))


def _import_noise():
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(CHEAP_DIR / "cloud_cheap_noise_256.png"))
    task.set_editor_property("destination_path", TEX_DIR)
    task.set_editor_property("destination_name", "T_XinyiCloudNoise")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    tools.import_asset_tasks([task])
    tex = lib.load_asset(NOISE)
    if tex is None:
        raise RuntimeError("noise texture import failed")
    # lattice data: linear, uncompressed, bilinear (the shader relies on hardware interpolation), wrap
    for prop, val in (("srgb", False),
                      ("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP),
                      ("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                      ("filter", unreal.TextureFilter.TF_BILINEAR),
                      ("address_x", unreal.TextureAddress.TA_WRAP), ("address_y", unreal.TextureAddress.TA_WRAP),
                      ("never_stream", True)):
        tex.set_editor_property(prop, val)
    if not lib.save_asset(NOISE):
        raise RuntimeError("failed to save %s" % NOISE)
    return tex


def _import_box(mat):
    if lib.does_directory_exist(BOX_DIR):
        lib.delete_directory(BOX_DIR)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    source = unreal.InterchangeManager.create_source_data(str(CHEAP_DIR / "cloud_cheap_box.glb"))
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    if not mgr.import_asset(BOX_DIR, source, params):
        raise RuntimeError("Interchange import of the cheap-cloud proxy box failed")
    meshes = [lib.load_asset(p) for p in lib.list_assets(BOX_DIR, recursive=True)]
    meshes = [(m.get_path_name().split(".")[0], m) for m in meshes if m is not None and m.get_class().get_name() == "StaticMesh"]
    if len(meshes) != 1:
        raise RuntimeError("proxy box import produced %d meshes" % len(meshes))
    path, mesh = meshes[0]
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    for i in range(max(1, len(mesh.static_materials))):
        mesh.set_material(i, mat)
    b = mesh.get_bounds()
    ext = [float(b.box_extent.x), float(b.box_extent.y), float(b.box_extent.z)]
    org = [float(b.origin.x), float(b.origin.y), float(b.origin.z)]
    if max(abs(e - 100.0) for e in ext) > 0.5 or max(abs(o) for o in org) > 0.5:
        raise RuntimeError("proxy box bounds %s / %s, expected a centred 200 cm cube" % (org, ext))
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    return path


def build_material(noise):
    """M_XinyiClouds_Cheap: Surface / Translucent / Unlit, depth test off (the shader clips by scene depth)."""
    import sys
    sys.path.insert(0, str(REPO / "tools" / "lookdev"))
    from ue_custom_code import CHEAP_CLOUD_INPUTS, cheap_cloud_custom_code
    failures = []
    if lib.does_asset_exist(MATERIAL) and not lib.delete_asset(MATERIAL):
        raise RuntimeError("cannot delete %s for a clean rebuild" % MATERIAL)
    mat = tools.create_asset("M_XinyiClouds_Cheap", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    for prop, val in (("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT),
                      ("shading_model", unreal.MaterialShadingModel.MSM_UNLIT),
                      ("float_precision_mode", unreal.MaterialFloatPrecisionMode.MFPM_FULL),
                      ("disable_depth_test", True),
                      ("translucency_pass", unreal.MaterialTranslucencyPass.MTP_AFTER_DOF),
                      ("use_translucency_vertex_fog", False),
                      ("compute_fog_per_pixel", True),
                      ("two_sided", False)):
        mat.set_editor_property(prop, val)

    def div100(src, x, y):
        dv = _expr(mat, unreal.MaterialExpressionDivide, x, y, const_b=100.0)
        _connect(src, "", dv, "A", failures)
        return dv

    wp = div100(_expr(mat, unreal.MaterialExpressionWorldPosition, -1600, -400), -1400, -400)
    cam = div100(_expr(mat, unreal.MaterialExpressionCameraPositionWS, -1600, -320), -1400, -320)
    obj = div100(_expr(mat, unreal.MaterialExpressionObjectPositionWS, -1600, -240), -1400, -240)
    node = _expr(mat, unreal.MaterialExpressionCustom, -700, 0)
    node.set_editor_property("code", cheap_cloud_custom_code())
    node.set_editor_property("description", "M_XinyiClouds_Cheap")
    node.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ins = []
    for n in CHEAP_CLOUD_INPUTS:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    node.set_editor_property("inputs", ins)
    co = unreal.CustomOutput()
    co.set_editor_property("output_name", "Alpha")
    co.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    node.set_editor_property("additional_outputs", [co])
    for src, pin in ((wp, "WP"), (cam, "CAM"), (obj, "OBJ")):
        _connect(src, "", node, pin, failures)
    # lobes + cell parameters: vector parameters bound to custom primitive data
    for i, pin in enumerate(["L%d" % i for i in range(8)] + ["PRM"]):
        p = _expr(mat, unreal.MaterialExpressionVectorParameter, -1300, -120 + i * 90)
        p.set_editor_property("parameter_name", "CheapCloud" + pin)
        p.set_editor_property("use_custom_primitive_data", True)
        p.set_editor_property("primitive_data_index", 4 * i)
        _connect(p, "RGBA", node, pin, failures)
    sund = _expr(mat, unreal.MaterialExpressionSkyAtmosphereLightDirection, -1300, 720, light_index=0)
    sune = _expr(mat, unreal.MaterialExpressionSkyAtmosphereLightIlluminance, -1300, 800, light_index=0)
    _connect(sund, "", node, "SUND", failures)
    _connect(sune, "", node, "SUNE", failures)
    for k, (pin, z) in enumerate((("SKYU", 1.0), ("SKYD", -1.0))):
        s = _expr(mat, unreal.MaterialExpressionSkyLightEnvMapSample, -1300, 880 + k * 110)
        dirc = _expr(mat, unreal.MaterialExpressionConstant3Vector, -1500, 880 + k * 110,
                     constant=unreal.LinearColor(0.0, 0.0, z, 0.0))
        rough = _expr(mat, unreal.MaterialExpressionConstant, -1500, 940 + k * 110, r=1.0)
        _connect(dirc, "", s, "Direction", failures)
        _connect(rough, "", s, "Roughness", failures)
        _connect(s, "", node, pin, failures)
    _connect(_expr(mat, unreal.MaterialExpressionSceneDepth, -1300, 1120), "", node, "SD", failures)
    _connect(_expr(mat, unreal.MaterialExpressionPixelDepth, -1300, 1180), "", node, "PD", failures)
    tobj = _expr(mat, unreal.MaterialExpressionTextureObject, -1300, 1240)
    tobj.set_editor_property("texture", noise)
    tobj.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    _connect(tobj, "", node, "NT", failures)
    day = TOD["day"]
    for k, (pin, v) in enumerate((("K1", day["K1"]), ("K2", day["K2"]), ("GLOW", day["GLOW"] + (0.0,)))):
        p = _expr(mat, unreal.MaterialExpressionVectorParameter, -1300, 1320 + k * 90)
        p.set_editor_property("parameter_name", "CheapCloud" + pin)
        p.set_editor_property("default_value", unreal.LinearColor(*v))
        _connect(p, "RGBA" if pin != "GLOW" else "", node, pin, failures)
    if not mel.connect_material_property(node, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        failures.append("emissive pin")
    if not mel.connect_material_property(node, "Alpha", unreal.MaterialProperty.MP_OPACITY):
        failures.append("opacity pin")
    mel.recompile_material(mat)
    if not lib.save_asset(MATERIAL):
        raise RuntimeError("failed to save %s" % MATERIAL)
    try:
        unreal.AutomationLibrary.finish_loading_before_screenshot()
    except Exception as exc:
        unreal.log_warning("finish_loading_before_screenshot: %s" % exc)
    n_ps = mel.get_statistics(mat).get_editor_property("num_pixel_shader_instructions")
    if n_ps <= 0:
        failures.append("M_XinyiClouds_Cheap did not compile")
    return mat, int(n_ps), failures


def build_cheap_assets():
    """Asset stage hook: noise texture, material, proxy box. Returns a receipt; fails closed."""
    rep = CHEAP_DIR / "cloud_cheap.report.json"
    if not rep.is_file():
        return None
    for d in (MAT_DIR, TEX_DIR, MESH_DIR):
        ensure_dir(d)
    noise = _import_noise()
    mat, n_ps, failures = build_material(noise)
    box = _import_box(mat)
    if failures:
        raise RuntimeError("cheap cloud material: %s" % "; ".join(failures))
    return {"material": MATERIAL, "noise": NOISE, "proxy_box": box, "pixel_shader_instructions": n_ps,
            "cheap_json_sha256": json.loads(rep.read_text(encoding="utf-8"))["cheap_json_sha256"]}


# ---------------------------------------------------------------------------------------------
# capture-process renderer (transient actors, never saved)
# ---------------------------------------------------------------------------------------------

def _cheap_actors(actors):
    return [a for a in actors.get_all_level_actors() if a.get_actor_label().startswith(LABEL)]


def spawn_cheap(actors):
    have = _cheap_actors(actors)
    if have:
        return have
    doc = json.loads((CHEAP_DIR / "clouds_v0.cheap.json").read_text(encoding="utf-8"))
    box = None
    for p in lib.list_assets(BOX_DIR, recursive=True):
        o = lib.load_asset(p)
        if o is not None and o.get_class().get_name() == "StaticMesh":
            box = o
    if box is None:
        raise RuntimeError("cheap-cloud proxy box missing (run the asset stage)")
    out = []
    for k, it in enumerate(doc["instances"]):
        a = actors.spawn_actor_from_object(box, unreal.Vector(*it["ue_location_cm"]))
        a.set_actor_label("%s%04d" % (LABEL, k))
        a.set_actor_scale3d(unreal.Vector(*it["ue_scale"]))
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_cast_shadow(False)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        c.set_editor_property("ld_max_draw_distance", CULL_CM)
        c.set_custom_primitive_data_float_array(0, [float(v) for v in it["cpd"]])
        out.append(a)
    return out


def apply_cheap(world, actors, tod):
    """Show the cheap renderer with the per-ToD calibration. The volumetric actor must be OFF."""
    mat = lib.load_asset(MATERIAL)
    if mat is None:
        raise RuntimeError("cheap cloud material missing: %s" % MATERIAL)
    spawned = spawn_cheap(actors)
    mid = unreal.MaterialLibrary.create_dynamic_material_instance(world, mat)
    cal = TOD.get(tod, TOD["day"])
    for n in ("K1", "K2"):
        mid.set_vector_parameter_value("CheapCloud" + n, unreal.LinearColor(*cal[n]))
    g = cal["GLOW"]
    mid.set_vector_parameter_value("CheapCloudGLOW", unreal.LinearColor(g[0], g[1], g[2], 0.0))
    for a in spawned:
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_material(0, mid)
        c.set_visibility(True)
    for k, v in CVARS.items():
        unreal.SystemLibrary.execute_console_command(world, "%s %s" % (k, v))
    return {"quality": "cheap", "material": MATERIAL, "instances": len(spawned), "params": cal, "cvars": CVARS}
