"""Cheap Cloud Renderer v1 (EXPERIMENTAL) - UE5.8 adapter (editor Python).

A third cloud renderer next to the volumetric HIGH / LOW profiles in xinyi_look_clouds.py, built on
the SAME renderer-agnostic cloud state:

  cloud_state_v0.json -> build_clouds.py -> clouds_v0.cells.json      (state: where / what kind)
                      -> build_cloud_cheap.py -> clouds_v0.cheap.json (CHEAP renderer detail: lobes)

Every cell (near) and every cluster of neighbouring cells (far) is one StaticMeshActor holding an
inward-facing unit proxy box scaled to its lobe bounds; its 8 lobes (per-lobe squash packed in the
radius fraction) + base plane + role + variation seed + bounding radius travel in the 36
custom-primitive-data floats. Near cells hand over to far clusters by camera distance (K3); each proxy
is distance-culled by the engine just outside the band where the shader has faded it to zero.
Cloud shadows: M_XinyiCloudShadow_Cheap, a sun light function over the baked band optical depth
(T_XinyiCloudShadow), set on the sun only in the cheap capture process.
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
SHADOW_MATERIAL = MAT_DIR + "/M_XinyiCloudShadow_Cheap"
SHADOW_TEX = TEX_DIR + "/T_XinyiCloudShadow"
BOX_DIR = MESH_DIR + "/CloudCheapBox"
LABEL = LOOK_PREFIX + "CheapCloud_"
# Representation bands (m, camera to proxy centre): near cells full to 12 km, handed over to the far
# clusters by 22 km; far clusters fade out 50 -> 60 km. Engine culling sits CULL_PAD_M outside each
# zero-weight edge, so a proxy is only culled once the shader has already faded it out.
BANDS = (12000.0, 22000.0, 50000.0, 60000.0)
CULL_PAD_M = 600.0
# The impostors are the only translucency in the look scene, so the separate (after-DOF) translucency
# pass renders them at QUARTER resolution (480 x 270 at 1080p, bilinear upsample): the cost is mostly
# per-pixel shading (UHD 770, move phase over OFF: 100 % +4..+39 ms, 50 % +4..+13 ms, 25 % +1..+6 ms)
# and the soft subject hides the lower resolution. Global renderer setting, applied only in the cheap
# capture process. At 25 % most of the remaining cost is fixed (v1 probes: proxies drawn with ~0 px
# already cost +3 .. +4 ms, the cloud shadow light function ~1 ms), not cloud pixel shading.
CVARS = {"r.SeparateTranslucencyScreenPercentage": 25}

# Per-time-of-day calibration (material-instance parameters; lighting itself comes from the sky
# atmosphere sun and the real-time sky light, so DAY / DUSK / NIGHT follow the accepted rig).
#   K1 = (sigma 1/m, erosion, density noise, ambient scale)
#   K2 = (sun scale, silver lining, fade end m, multiple-scattering floor)
#   GLOW = city light on cloud bases (night only)
# Dusk: as in the volumetric renderer, multiply-scattered orange sun flooding the shaded volumes gives
# flat ochre cotton balls; a low MS floor + double sky fill keeps warm tops / edges over cool bodies.
# K2.z (v0's tIn alpha fade end) now sits beyond the far band; distance fading is K3's job.
#   SHADOW = cloud-shadow strength on the sun (0 = none, 1 = full band transmittance)
TOD = {
    "day": {"K1": (0.03, 1.0, 0.45, 0.75), "K2": (1.0, 1.0, 68000.0, 0.2), "GLOW": (0.0, 0.0, 0.0), "SHADOW": 0.8},
    "dusk": {"K1": (0.03, 1.0, 0.45, 1.5), "K2": (0.9, 1.0, 68000.0, 0.08), "GLOW": (0.0, 0.0, 0.0), "SHADOW": 0.6},
    "night": {"K1": (0.03, 1.0, 0.45, 0.75), "K2": (1.0, 0.6, 68000.0, 0.2), "GLOW": (0.02, 0.014, 0.008), "SHADOW": 0.4},
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


def _import_data_texture(png, name, path):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(CHEAP_DIR / png))
    task.set_editor_property("destination_path", TEX_DIR)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    tools.import_asset_tasks([task])
    tex = lib.load_asset(path)
    if tex is None:
        raise RuntimeError("%s import failed" % name)
    # data: linear, uncompressed, bilinear (the shaders rely on hardware interpolation), wrap
    for prop, val in (("srgb", False),
                      ("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP),
                      ("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS),
                      ("filter", unreal.TextureFilter.TF_BILINEAR),
                      ("address_x", unreal.TextureAddress.TA_WRAP), ("address_y", unreal.TextureAddress.TA_WRAP),
                      ("never_stream", True)):
        tex.set_editor_property(prop, val)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    return tex


def _import_noise():
    return _import_data_texture("cloud_cheap_noise_256.png", "T_XinyiCloudNoise", NOISE)


def build_shadow_material(tex):
    """M_XinyiCloudShadow_Cheap: sun light function (grey multiplier) over the baked band optical depth."""
    import sys
    sys.path.insert(0, str(REPO / "tools" / "lookdev"))
    from ue_custom_code import CHEAP_SHADOW_INPUTS, cheap_shadow_custom_code
    failures = []
    if lib.does_asset_exist(SHADOW_MATERIAL) and not lib.delete_asset(SHADOW_MATERIAL):
        raise RuntimeError("cannot delete %s for a clean rebuild" % SHADOW_MATERIAL)
    mat = tools.create_asset("M_XinyiCloudShadow_Cheap", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_LIGHT_FUNCTION)
    mat.set_editor_property("float_precision_mode", unreal.MaterialFloatPrecisionMode.MFPM_FULL)
    wp = _expr(mat, unreal.MaterialExpressionWorldPosition, -1200, -200)
    wpm = _expr(mat, unreal.MaterialExpressionDivide, -1000, -200, const_b=100.0)
    _connect(wp, "", wpm, "A", failures)
    node = _expr(mat, unreal.MaterialExpressionCustom, -500, 0)
    node.set_editor_property("code", cheap_shadow_custom_code())
    node.set_editor_property("description", "M_XinyiCloudShadow_Cheap")
    node.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ins = []
    for n in CHEAP_SHADOW_INPUTS:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    node.set_editor_property("inputs", ins)
    _connect(wpm, "", node, "WP", failures)
    tobj = _expr(mat, unreal.MaterialExpressionTextureObject, -1000, 100)
    tobj.set_editor_property("texture", tex)
    tobj.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    _connect(tobj, "", node, "ST", failures)
    for k, (pin, v) in enumerate((("SUNV", (0.0, 0.0, 1.0, 0.0)), ("SHP", (0.0, 1.0, 64000.0, 6.0)),
                                  ("BANDZ", (1500.0, 2075.0, 2900.0, 0.0)))):
        p = _expr(mat, unreal.MaterialExpressionVectorParameter, -1000, 200 + k * 90)
        p.set_editor_property("parameter_name", "CheapShadow" + pin)
        p.set_editor_property("default_value", unreal.LinearColor(*v))
        _connect(p, "RGBA" if pin == "SHP" else "", node, pin, failures)
    if not mel.connect_material_property(node, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR):
        failures.append("shadow emissive pin")
    mel.recompile_material(mat)
    if not lib.save_asset(SHADOW_MATERIAL):
        raise RuntimeError("failed to save %s" % SHADOW_MATERIAL)
    return mat, failures


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
    for k, (pin, v) in enumerate((("K1", day["K1"]), ("K2", day["K2"]), ("K3", BANDS), ("GLOW", day["GLOW"] + (0.0,)))):
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
    shadow_tex = _import_data_texture("cloud_cheap_shadow_1024.png", "T_XinyiCloudShadow", SHADOW_TEX)
    _, shadow_fail = build_shadow_material(shadow_tex)
    failures += shadow_fail
    if failures:
        raise RuntimeError("cheap cloud material: %s" % "; ".join(failures))
    r = json.loads(rep.read_text(encoding="utf-8"))
    return {"material": MATERIAL, "noise": NOISE, "proxy_box": box, "pixel_shader_instructions": n_ps,
            "shadow_material": SHADOW_MATERIAL, "shadow_texture": SHADOW_TEX,
            "cheap_json_sha256": r["cheap_json_sha256"], "shadow_sha256": r.get("shadow_sha256")}


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
        if it["role"] == "near":
            c.set_editor_property("ld_max_draw_distance", (BANDS[1] + CULL_PAD_M) * 100.0)
        else:
            c.set_editor_property("min_draw_distance", (BANDS[0] - CULL_PAD_M) * 100.0)
            c.set_editor_property("ld_max_draw_distance", (BANDS[3] + CULL_PAD_M) * 100.0)
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
    mid.set_vector_parameter_value("CheapCloudK3", unreal.LinearColor(*BANDS))
    g = cal["GLOW"]
    mid.set_vector_parameter_value("CheapCloudGLOW", unreal.LinearColor(g[0], g[1], g[2], 0.0))
    for a in spawned:
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_material(0, mid)
        c.set_visibility(True)
    for k, v in CVARS.items():
        unreal.SystemLibrary.execute_console_command(world, "%s %s" % (k, v))
    shadow = apply_cheap_shadow(world, actors, cal["SHADOW"])
    roles = {}
    for a in spawned:
        r = "far" if a.get_component_by_class(unreal.StaticMeshComponent).get_editor_property("min_draw_distance") > 0 else "near"
        roles[r] = roles.get(r, 0) + 1
    return {"quality": "cheap", "material": MATERIAL, "instances": len(spawned), "roles": roles, "bands_m": BANDS,
            "params": cal, "cvars": CVARS, "shadow": shadow}


def apply_cheap_shadow(world, actors, strength):
    """Cloud shadows: the baked band optical depth as a light function on the sun (cheap path only).
    The volumetric cloud shadow stays off (apply_clouds 'off'); the saved level never carries this."""
    rep = json.loads((CHEAP_DIR / "cloud_cheap.report.json").read_text(encoding="utf-8"))
    mat = lib.load_asset(SHADOW_MATERIAL)
    if mat is None or "shadow" not in rep:
        raise RuntimeError("cheap cloud shadow missing (run the offline build + asset stage)")
    sun = None
    for a in actors.get_all_level_actors():
        if a.get_actor_label() == LOOK_PREFIX + "Sun":
            sun = a
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    fwd = sun.get_actor_forward_vector()          # light travel direction (UE axes)
    to_sun = (-fwd.x, -fwd.y, -fwd.z)
    sh = rep["shadow"]
    bandz = [0.5 * (z0 + z1) for z0, z1 in sh["bands_m"]]
    mid = unreal.MaterialLibrary.create_dynamic_material_instance(world, mat)
    mid.set_vector_parameter_value("CheapShadowSUNV", unreal.LinearColor(to_sun[0], to_sun[1], to_sun[2], 0.0))
    mid.set_vector_parameter_value("CheapShadowSHP", unreal.LinearColor(float(strength), 1.0, float(rep.get("tile_m", 64000.0)),
                                                                        float(sh["tau_max"])))
    mid.set_vector_parameter_value("CheapShadowBANDZ", unreal.LinearColor(bandz[0], bandz[1], bandz[2], 0.0))
    sc.set_light_function_material(mid)
    for prop, val in (("light_function_fade_distance", 1.0e7), ("disabled_brightness", 1.0)):
        sc.set_editor_property(prop, val)
    return {"material": SHADOW_MATERIAL, "strength": strength, "to_sun": [round(v, 4) for v in to_sun],
            "band_mid_m": bandz, "fade_distance_cm": 1.0e7}
