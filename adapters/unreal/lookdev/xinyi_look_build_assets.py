"""XinyiLook stage 1: materials + asset import (UE5.8, UnrealEditor-Cmd).

Creates, under /Game/XinyiLook:
  Materials/MPC_XinyiLook      Night / LitFrac / EmissiveScale (time of day)
  Materials/M_XinyiCity         ordinary buildings (shared HLSL, hero path off)
  Materials/M_Taipei101         hero tower (shared HLSL, hero path on)
  Materials/M_XinyiGround       Landscape (ground data texture + shared HLSL)
  Materials/M_XinyiRoadPaint    road paint geometry
  Materials/M_XinyiBackdrop     basin mountain ring
  Materials/M_XinyiFoliage      instanced street / park trees
  Textures/T_XinyiGround        2048^2 road SDF / green / class / water (linear)
  Textures/T_XinyiCampus        2048^2 Grade-A campus / court signed distance + surface id (linear, box mips)
  Meshes/Tiles/<tile>/...       25 look tiles (triangle soup = accepted tiles)
  Meshes/Hero, Backdrop, Paint, Tree

Every surface material is one Custom node running
tools/lookdev/shaders/xinyi_city.hlsl — the exact source the look-dev preview
renders — wrapped in a struct (no engine plugin / shader directory needed).
Per-vertex data travels in UV channels only (no vertex-colour import policy).

Fails closed on: missing inputs, UV-channel loss, tile bounds drift vs the
accepted contract (> 2 cm), missing assets after save.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.environ.get("ACW_REPO_ROOT", ""), "adapters", "unreal", "lookdev"))
sys.path.insert(0, os.path.join(os.environ.get("ACW_REPO_ROOT", ""), "tools", "lookdev"))
import unreal  # noqa: E402
from ue_custom_code import (  # noqa: E402
    CLOUD_INPUTS, MATERIALS, cloud_custom_code, cloud_weather_uv_code, custom_code, extent_uv_code, ground_uv_code,
    source_bbox_defines,
)
from xinyi_look_clouds_cheap import build_cheap_assets  # noqa: E402
from xinyi_look_common import (  # noqa: E402
    CONTRACT_DIR, LOOK_OUT, MAT_DIR, MESH_DIR, MPC_PATH, SHADER, TEX_DIR, E0, E1, N0, N1,  # noqa: F401
    ensure_dir, lib, max_err, mel, mesh_bounds, read_json, tile_key, tools, write_report,
)

EXTENT_TOLERANCE_CM = 2.0
failures = []
created = {}


# ---------------------------------------------------------------------------
# Material construction helpers
# ---------------------------------------------------------------------------

def fresh_material(name):
    """Create, or rebuild in place (keeps references from an existing look level)."""
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        mat = lib.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError("failed to create material %s" % path)
    # iPhone-class discipline: opaque, full precision for world-space hashing,
    # no tessellation / refraction / translucency anywhere in this layer.
    for prop, val in (
        ("float_precision_mode", unreal.MaterialFloatPrecisionMode.MFPM_FULL),
        ("tangent_space_normal", False),
    ):
        try:
            mat.set_editor_property(prop, val)
        except Exception as exc:  # property names drift between engine versions
            unreal.log_warning("material %s: cannot set %s (%s)" % (name, prop, exc))
    return mat, path


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def mpc_param(mat, mpc, name, x, y):
    e = expr(mat, unreal.MaterialExpressionCollectionParameter, x, y)
    e.set_editor_property("collection", mpc)
    e.set_editor_property("parameter_name", name)
    return e


def texcoord(mat, index, x, y):
    return expr(mat, unreal.MaterialExpressionTextureCoordinate, x, y, coordinate_index=index)


def world_pos_m(mat, x, y):
    wp = expr(mat, unreal.MaterialExpressionWorldPosition, x, y)
    div = expr(mat, unreal.MaterialExpressionDivide, x + 180, y, const_b=100.0)
    mel.connect_material_expressions(wp, "", div, "A")
    return div


def custom(mat, x, y, code, inputs, outputs, desc, out_type=None):
    c = expr(mat, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("code", code)
    c.set_editor_property("description", desc)
    c.set_editor_property("output_type", out_type or unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    outs = []
    for n, t in outputs:
        co = unreal.CustomOutput()
        co.set_editor_property("output_name", n)
        co.set_editor_property("output_type", t)
        outs.append(co)
    c.set_editor_property("additional_outputs", outs)
    return c


F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3

SURFACE_OUTPUTS = [("Rough", F1), ("Metal", F1), ("Spec", F1), ("Emis", F3), ("NrmWS", F3)]


def finish_surface(mat, node, emis_scale, x, y, normal=True):
    mel.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(node, "Rough", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(node, "Metal", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(node, "Spec", unreal.MaterialProperty.MP_SPECULAR)
    mul = expr(mat, unreal.MaterialExpressionMultiply, x, y)
    mel.connect_material_expressions(node, "Emis", mul, "A")
    mel.connect_material_expressions(emis_scale, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if normal:
        mel.connect_material_property(node, "NrmWS", unreal.MaterialProperty.MP_NORMAL)


def save_material(mat, path):
    mel.recompile_material(mat)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    created[path] = "Material"


def build_mpc():
    if lib.does_asset_exist(MPC_PATH):
        mpc = lib.load_asset(MPC_PATH)          # update in place; materials are rebuilt below
    else:
        mpc = tools.create_asset("MPC_XinyiLook", MAT_DIR, unreal.MaterialParameterCollection,
                                 unreal.MaterialParameterCollectionFactoryNew())
    params = []
    for name, default in (("Night", 0.0), ("LitFrac", 0.08), ("EmissiveScale", 1.0)):
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", name)
        p.set_editor_property("default_value", default)
        params.append(p)
    mpc.set_editor_property("scalar_parameters", params)
    if not lib.save_asset(MPC_PATH):
        raise RuntimeError("failed to save MPC")
    created[MPC_PATH] = "MaterialParameterCollection"
    return mpc


def build_city_material(mpc, name, hero):
    mat, path = fresh_material(name)
    wp = world_pos_m(mat, -1200, -300)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -150)
    uv0, uv1, uv2 = texcoord(mat, 0, -1200, 0), texcoord(mat, 1, -1200, 120), texcoord(mat, 2, -1200, 240)
    night = mpc_param(mat, mpc, "Night", -1200, 360)
    lit = mpc_param(mat, mpc, "LitFrac", -1200, 480)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -700, 0, custom_code(name), [n for n, _ in MATERIALS[name][0]], SURFACE_OUTPUTS, name)
    wire(((wp, "WP"), (n, "N"), (uv0, "UV0"), (uv1, "UV1"), (uv2, "UV2"),
          (night, "Night"), (lit, "LitFrac")), node)
    finish_surface(mat, node, es, -300, 300)
    save_material(mat, path)
    return mat


def ground_uv(mat, wp, x, y):
    c = custom(mat, x, y, ground_uv_code(E0, E1, N0, N1), ["WP"], [], "XinyiGroundUV", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    mel.connect_material_expressions(wp, "", c, "WP")
    return c


def ground_sample(mat, tex, uv, x, y, grayscale=False):
    s = expr(mat, unreal.MaterialExpressionTextureSample, x, y)
    s.set_editor_property("texture", tex)
    s.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE if grayscale
                          else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    mel.connect_material_expressions(uv, "", s, "UVs")
    return s


def wire(src_pin_pairs, node):
    """Connect (expression, input pin[, output pin]) tuples into a Custom node.

    Texture samples must be wired from their "RGBA" / "R" outputs explicitly:
    the default output is RGB, and float3 -> float4 does not compile.
    """
    for item in src_pin_pairs:
        src, pin = item[0], item[1]
        out = item[2] if len(item) > 2 else ""
        if not mel.connect_material_expressions(src, out, node, pin):
            raise RuntimeError("failed to connect %s -> %s" % (out or "default", pin))


def build_ground_material(mpc, tex, lamp_tex, campus_tex, src_bbox=None):
    mat, path = fresh_material("M_XinyiGround")
    wp = world_pos_m(mat, -1400, -200)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -60)
    uv = ground_uv(mat, wp, -1100, 100)
    gt = ground_sample(mat, tex, uv, -900, 100)
    ct = ground_sample(mat, campus_tex, uv, -900, 180)
    lamp = ground_sample(mat, lamp_tex, uv, -900, 260, grayscale=True)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    extra = source_bbox_defines(src_bbox) if src_bbox else ""
    node = custom(mat, -600, 0, custom_code("M_XinyiGround", extra), [n for n, _ in MATERIALS["M_XinyiGround"][0]], SURFACE_OUTPUTS, "M_XinyiGround")
    wire(((wp, "WP"), (n, "N"), (gt, "GT", "RGBA"), (ct, "CT", "RGBA"), (lamp, "LAMP", "R"), (night, "Night")), node)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


def build_paint_material(mpc, tex, lamp_tex):
    mat, path = fresh_material("M_XinyiRoadPaint")
    wp = world_pos_m(mat, -1400, -200)
    uv2 = texcoord(mat, 2, -1200, -40)
    uv = ground_uv(mat, wp, -1100, 100)
    gt = ground_sample(mat, tex, uv, -900, 100)
    lamp = ground_sample(mat, lamp_tex, uv, -900, 260, grayscale=True)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code("M_XinyiRoadPaint"), [n for n, _ in MATERIALS["M_XinyiRoadPaint"][0]], SURFACE_OUTPUTS, "M_XinyiRoadPaint")
    wire(((wp, "WP"), (uv2, "UV2"), (gt, "GT", "RGBA"), (lamp, "LAMP", "R"), (night, "Night")), node)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


def build_backdrop_material(mpc, far_tex, far_extent):
    mat, path = fresh_material("M_XinyiBackdrop")
    wp = world_pos_m(mat, -1400, -200)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -60)
    uv2 = texcoord(mat, 2, -1200, 60)
    if far_tex is not None:
        e0, e1, n0, n1 = far_extent
        fuv = custom(mat, -1100, 200, extent_uv_code(e0, e1, n0, n1), ["WP"], [], "FarCityUV",
                     unreal.CustomMaterialOutputType.CMOT_FLOAT2)
        mel.connect_material_expressions(wp, "", fuv, "WP")
        fc = ground_sample(mat, far_tex, fuv, -900, 200)
    else:
        fc = expr(mat, unreal.MaterialExpressionConstant4Vector, -900, 200,
                  constant=unreal.LinearColor(0.0, 0.0, 0.0, 0.0))
    night = mpc_param(mat, mpc, "Night", -1200, 360)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code("M_XinyiBackdrop"), [n_ for n_, _ in MATERIALS["M_XinyiBackdrop"][0]],
                  SURFACE_OUTPUTS, "M_XinyiBackdrop")
    wire(((wp, "WP"), (n, "N"), (uv2, "UV2"), (fc, "FC", "RGBA" if far_tex is not None else ""), (night, "Night")), node)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


def scalar_param(mat, name, default, x, y):
    e = expr(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", default)
    return e


def vector_param(mat, name, default, x, y):
    e = expr(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(*default))
    return e


def build_cloud_material(weather, cloud_rep, low):
    """Cloud Prototype v0 volumetric-cloud material (Volume domain, additive).

    Density comes from tools/lookdev/shaders/xinyi_clouds.hlsl reading the renderer-agnostic
    weather map; HIGH / LOW differ only in noise octaves and multi-scattering octaves.
    """
    name = "M_XinyiClouds_Low" if low else "M_XinyiClouds_High"
    # Always a brand-new asset: delete_all_material_expressions (fresh_material's in-place rebuild)
    # does not remove the Volumetric Advanced Output node, so a second rebuild had two of them, failed
    # to compile ("only one Volumetric Advanced Output node") and silently rendered no clouds.
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path) and not lib.delete_asset(path):
        raise RuntimeError("cannot delete %s for a clean rebuild" % path)
    mat, path = fresh_material(name)
    # blend first: switching the domain recompiles, and a Volume + Opaque intermediate logs an error
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    # Without this usage flag the cloud compute permutations are never compiled; the cloud renderer
    # then falls back to the default surface material and asserts (domain == MD_Volume).
    mat.set_editor_property("used_with_volumetric_cloud", True)
    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_VOLUME)
    wp = world_pos_m(mat, -1500, -200)
    uv = custom(mat, -1250, 100, cloud_weather_uv_code(cloud_rep["tile_m"]), ["WP"], [], "CloudWeatherUV",
                unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    mel.connect_material_expressions(wp, "", uv, "WP")
    wx = expr(mat, unreal.MaterialExpressionTextureSample, -1000, 100)
    wx.set_editor_property("texture", weather)
    wx.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    for prop, val in (("mip_value_mode", unreal.TextureMipValueMode.TMVM_MIP_LEVEL), ("const_mip_value", 0)):
        try:
            wx.set_editor_property(prop, val)
        except Exception as exc:
            unreal.log_warning("%s: cannot set %s (%s)" % (name, prop, exc))
    mel.connect_material_expressions(uv, "", wx, "UVs")
    # Per-time-of-day renderer calibration is material-instance parameters (set on a dynamic
    # instance by xinyi_look_clouds.apply_clouds), NOT the city MPC: the volumetric cloud pass did
    # not see per-world MPC values (coverage / extinction / dusk fill had no effect).
    cov = scalar_param(mat, "CloudCoverage", 0.0, -1200, 460)
    # density contrast + fine-lobe weight: defaults are the HIGH look; LOW softens them per profile
    gain = scalar_param(mat, "CloudDensityGain", 2.2, -1200, 560)
    fine = scalar_param(mat, "CloudFineLump", 0.45, -1200, 660)
    ext = scalar_param(mat, "CloudExtinction", 0.02, -600, 420)
    node = custom(mat, -750, 0, cloud_custom_code(low, cloud_rep["broken_base_norm"], cloud_rep["renderer_layer_m"][0],
                                                      cloud_rep["renderer_layer_height_m"]), [n for n, _ in CLOUD_INPUTS],
                  [("Env", F1), ("AO", F1)], name, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    wire(((wp, "WP"), (wx, "WX", "RGBA"), (cov, "COV"), (gain, "GAIN"), (fine, "FINE")), node)
    mul = expr(mat, unreal.MaterialExpressionMultiply, -400, 200)
    mel.connect_material_expressions(node, "", mul, "A")
    mel.connect_material_expressions(ext, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)      # extinction
    albedo = expr(mat, unreal.MaterialExpressionConstant3Vector, -400, -120,
                  constant=unreal.LinearColor(0.96, 0.96, 0.97, 1.0))
    mel.connect_material_property(albedo, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(node, "AO", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    # Multi-scattering approximation + dual-lobe phase (bright silver lining, soft interiors).
    adv = expr(mat, unreal.MaterialExpressionVolumetricAdvancedMaterialOutput, -400, 450)
    for prop, val in (("const_phase_g", 0.6), ("const_phase_g2", -0.3), ("const_phase_blend", 0.35),
                      ("const_multi_scattering_contribution", 0.75), ("const_multi_scattering_occlusion", 0.3),
                      ("ground_contribution", True),
                      ("const_multi_scattering_eccentricity", 0.55),
                      ("multi_scattering_approximation_octave_count", 1 if low else 2)):
        try:
            adv.set_editor_property(prop, val)
        except Exception as exc:
            failures.append({"material": name, "property": prop, "error": str(exc)[:120]})
    if not mel.connect_material_expressions(node, "Env", adv, "ConservativeDensity"):
        failures.append({"material": name, "error": "ConservativeDensity pin not connected"})
    # per time-of-day multiple-scattering strength, overrides the constant above
    ms = scalar_param(mat, "CloudMultiScatter", 0.75, -700, 620)
    if not mel.connect_material_expressions(ms, "", adv, "MultiScatteringContribution"):
        failures.append({"material": name, "error": "MultiScatteringContribution pin not connected"})
    # per time-of-day cool sky fill (black by day): emissive x the underside occlusion so shaded cores
    # pick up a little sky colour instead of falling to brown
    amb = vector_param(mat, "CloudAmbient", (0.0, 0.0, 0.0, 0.0), -700, -320)
    # emission must scale with extinction (density): per-metre emission integrates along the ray, so
    # a density-independent term filled the whole layer with glow. amb x AO x sigma_t gives a fill
    # that saturates at ~amb x (1 - transmittance) inside clouds and is zero in clear air.
    amb_ao = expr(mat, unreal.MaterialExpressionMultiply, -500, -320)
    mel.connect_material_expressions(amb, "", amb_ao, "A")
    mel.connect_material_expressions(node, "AO", amb_ao, "B")
    emis = expr(mat, unreal.MaterialExpressionMultiply, -300, -320)
    mel.connect_material_expressions(amb_ao, "", emis, "A")
    mel.connect_material_expressions(mul, "", emis, "B")
    mel.connect_material_property(emis, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    save_material(mat, path)
    if mel.get_statistics(mat).get_editor_property("num_pixel_shader_instructions") <= 0:
        failures.append({"material": name, "error": "cloud material did not compile"})
    return mat


def build_instanced_material(mpc, name):
    """Shared builder for instanced materials (per-instance variant in custom data 0)."""
    mat, path = fresh_material(name)
    for prop, val in (("two_sided", True), ("used_with_instanced_static_meshes", True)):
        try:
            mat.set_editor_property(prop, val)
        except Exception as exc:
            unreal.log_warning("%s: cannot set %s (%s)" % (name, prop, exc))
    wp = world_pos_m(mat, -1400, -200)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -60)
    uv2 = texcoord(mat, 2, -1200, 60)
    var = expr(mat, unreal.MaterialExpressionPerInstanceCustomData, -1200, 180, data_index=0)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code(name), [n for n, _ in MATERIALS[name][0]], SURFACE_OUTPUTS, name)
    wire(((wp, "WP"), (n, "N"), (uv2, "UV2"), (var, "Variant"), (night, "Night")), node)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def import_texture(png, name, grayscale=False, address=unreal.TextureAddress.TA_CLAMP, box_mips=False):
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
    # data texture: linear, lossless (SDF edges + class ids must not be BC-crushed)
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE if grayscale
                            else unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("address_x", address)
    tex.set_editor_property("address_y", address)
    if box_mips:
        # signed-distance masks: plain box-filtered mips (no sharpening lobes), so a mip average of the
        # 1-Lipschitz field moves by at most ~half its footprint (the shader insets by that)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    created[path] = "Texture2D"
    return tex


def add_auto_lods(mesh):
    """LOD1 50% / LOD2 25% for instanced props and trees (engine reduction)."""
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    opts = unreal.EditorScriptingMeshReductionOptions()
    settings = []
    for pct, screen in ((1.0, 1.0), (0.5, 0.12), (0.25, 0.04)):
        r = unreal.EditorScriptingMeshReductionSettings()
        r.set_editor_property("percent_triangles", pct)
        r.set_editor_property("screen_size", screen)
        settings.append(r)
    opts.set_editor_property("reduction_settings", settings)
    opts.set_editor_property("auto_compute_lod_screen_size", False)
    return int(sub.set_lods(mesh, opts))


def import_mesh(glb, dest, material, min_uv_channels):
    if lib.does_directory_exist(dest):
        lib.delete_directory(dest)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    source = unreal.InterchangeManager.create_source_data(str(glb))
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    if not mgr.import_asset(dest, source, params):
        raise RuntimeError("Interchange import_asset returned false: %s" % glb)
    meshes = []
    for p in lib.list_assets(dest, recursive=True):
        obj = lib.load_asset(p)
        if obj is not None and obj.get_class().get_name() == "StaticMesh":
            meshes.append((str(p).split(".")[0], obj))
    if len(meshes) != 1:
        raise RuntimeError("%s produced %d StaticMesh assets, expected 1" % (glb, len(meshes)))
    path, mesh = meshes[0]
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    # Mobile-first: no Nanite; keep authored normals; full-precision UVs carry
    # metre-scale facade coordinates + packed data; never drop triangles.
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    bs = sub.get_lod_build_settings(mesh, 0)
    for prop, val in (("recompute_normals", False), ("recompute_tangents", True),
                      ("use_full_precision_u_vs", True), ("remove_degenerates", False),
                      ("generate_lightmap_u_vs", False)):
        try:
            bs.set_editor_property(prop, val)
        except Exception as exc:
            unreal.log_warning("build settings %s: %s" % (prop, exc))
    sub.set_lod_build_settings(mesh, 0, bs)
    uvs = int(sub.get_num_uv_channels(mesh, 0))
    if uvs < min_uv_channels:
        raise RuntimeError("%s imported with %d UV channels, expected >= %d" % (glb, uvs, min_uv_channels))
    for i in range(max(1, len(mesh.static_materials))):
        mesh.set_material(i, material)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    created[path] = "StaticMesh"
    return path, mesh


def main():
    t0 = time.perf_counter()
    for d in (MAT_DIR, TEX_DIR, MESH_DIR):
        ensure_dir(d)

    look = read_json(LOOK_OUT / "look_tiles.report.json")
    hero = read_json(LOOK_OUT / "hero/taipei101.anchor.json")
    backdrop = read_json(LOOK_OUT / "backdrop/taipei_basin_backdrop.json")
    ground = read_json(LOOK_OUT / "ground/ground.report.json")
    landmarks = read_json(LOOK_OUT / "hero/landmark_roofs.json")
    contract = read_json(CONTRACT_DIR / "xinyi_unreal_v2_contract.json")
    if look.get("status") != "PASS_LOOK_TILES" or len(look["tiles"]) != 25:
        raise RuntimeError("look tiles report is not PASS_LOOK_TILES with 25 tiles")
    crow = {r["tile"]: r for r in contract["tiles"]}

    mpc = build_mpc()
    tex = import_texture(LOOK_OUT / "ground/xinyi_ground_2048.png", "T_XinyiGround")
    lamp_tex = import_texture(LOOK_OUT / "ground/xinyi_ground_light_1024.png", "T_XinyiGroundLight", grayscale=True)
    m_city = build_city_material(mpc, "M_XinyiCity", hero=False)
    m_hero = build_city_material(mpc, "M_Taipei101", hero=True)
    far_rep_path = LOOK_OUT / "farcity/far_city.report.json"
    far_rep = read_json(far_rep_path) if far_rep_path.is_file() else None
    campus_tex = import_texture(LOOK_OUT / "ground" / ground["campus"]["texture"], "T_XinyiCampus", box_mips=True)
    m_ground = build_ground_material(mpc, tex, lamp_tex, campus_tex,
                                     far_rep["xinyi_source_bbox_enu_m"] if far_rep else None)
    m_paint = build_paint_material(mpc, tex, lamp_tex)
    far_tex = import_texture(LOOK_OUT / "farcity/far_city_1024.png", "T_TaipeiFarCity") if far_rep else None
    m_back = build_backdrop_material(mpc, far_tex, far_rep["texture_extent_enu_m"] if far_rep else None)
    m_tree = build_instanced_material(mpc, "M_XinyiFoliage")
    m_props = build_instanced_material(mpc, "M_XinyiProps")  # also street lamps
    # Cloud Prototype v0 (renderer layer over the renderer-agnostic cloud state)
    cloud_rep_path = LOOK_OUT / "clouds/clouds.report.json"
    cloud_rep = read_json(cloud_rep_path) if cloud_rep_path.is_file() else None
    clouds = None
    if cloud_rep:
        weather = import_texture(LOOK_OUT / "clouds" / cloud_rep["weather_map"], "T_XinyiCloudWeather",
                                 address=unreal.TextureAddress.TA_WRAP)
        for low in (False, True):
            build_cloud_material(weather, cloud_rep, low)
        try:   # finish the cloud shader maps here so later stages load them from the DDC
            unreal.AutomationLibrary.finish_loading_before_screenshot()
        except Exception as exc:
            unreal.log_warning("finish_loading_before_screenshot: %s" % exc)
        clouds = {"high": "M_XinyiClouds_High", "low": "M_XinyiClouds_Low", "weather": "T_XinyiCloudWeather",
                  "weather_sha256": cloud_rep["weather_sha256"]}
        # Cheap Cloud Renderer v0 (experimental, opt-in only; nothing is placed in the level)
        try:
            clouds["cheap"] = build_cheap_assets()
        except Exception as exc:
            failures.append({"cheap_clouds": str(exc)[:400]})
    roofs = read_json(LOOK_OUT / "rooftops/rooftops.report.json")

    tiles = []
    for row in look["tiles"]:
        tile = row["tile"]
        try:
            path, mesh = import_mesh(LOOK_OUT / "tiles" / row["path"], MESH_DIR + "/Tiles/" + tile_key(tile), m_city, 3)
            origin, extent = mesh_bounds(mesh)
            exp_extent = crow[tile]["runtime_expected_ue_local_bounds_extent_cm"]
            err = max_err(extent, exp_extent)
            if err > EXTENT_TOLERANCE_CM:
                raise RuntimeError("extent drift %.3f cm vs accepted runtime tile" % err)
            tiles.append({
                "tile": tile, "asset_path": path, "triangles": row["triangles"],
                "imported_bounds_origin_cm": origin, "imported_bounds_extent_cm": extent,
                "expected_local_bounds_origin_cm": crow[tile]["runtime_expected_ue_local_bounds_origin_cm"],
                "tile_world_translation_cm": crow[tile]["expected_ue_translation_cm"],
                "extent_error_cm": err,
            })
        except Exception as exc:
            failures.append({"tile": tile, "error": str(exc)})

    singles = {}
    for key, glb, dest, mat, uvn, exp in (
        ("hero", LOOK_OUT / "hero/taipei101.glb", MESH_DIR + "/Hero", m_hero, 3, hero["expected_ue_local_bounds"]),
        ("landmarks", LOOK_OUT / "hero/landmark_roofs.glb", MESH_DIR + "/Landmarks", m_city, 3,
         landmarks["expected_ue_local_bounds"]),
        ("backdrop", LOOK_OUT / "backdrop/taipei_basin_backdrop.glb", MESH_DIR + "/Backdrop", m_back, 3,
         backdrop["expected_ue_local_bounds"]),
        ("paint", LOOK_OUT / "ground/xinyi_road_paint.glb", MESH_DIR + "/RoadPaint", m_paint, 3,
         ground["paint_expected_ue_local_bounds"]),
        ("campus_paint", LOOK_OUT / "ground" / ground["campus"]["paint_mesh"], MESH_DIR + "/CampusPaint", m_paint, 3,
         ground["campus"]["paint_expected_ue_local_bounds"]),
        ("tree", LOOK_OUT / "ground/xinyi_tree.glb", MESH_DIR + "/Tree", m_tree, 3,
         ground["tree_expected_ue_local_bounds"]),
        ("forest", LOOK_OUT / "ground/xinyi_forest_clump.glb", MESH_DIR + "/Forest", m_tree, 3,
         ground["forest_expected_ue_local_bounds"]),
        ("lamp", LOOK_OUT / "ground/xinyi_lamp.glb", MESH_DIR + "/Lamp", None, 3,
         ground["lamp_expected_ue_local_bounds"]),
    ):
        if mat is None:
            mat = m_props
        try:
            path, mesh = import_mesh(glb, dest, mat, uvn)
            if key in ("tree", "forest", "lamp"):
                add_auto_lods(mesh)
                lib.save_asset(path)
            origin, extent = mesh_bounds(mesh)
            err = max_err(extent, exp["extent_cm"])
            if err > EXTENT_TOLERANCE_CM:
                raise RuntimeError("extent drift %.3f cm" % err)
            singles[key] = {"asset_path": path, "imported_bounds_origin_cm": origin,
                            "expected_bounds_origin_cm": exp["origin_cm"], "extent_error_cm": err}
        except Exception as exc:
            failures.append({"asset": key, "error": str(exc)})

    props = {}
    for t, row in roofs["types"].items():
        try:
            path, mesh = import_mesh(LOOK_OUT / "rooftops" / row["mesh"], MESH_DIR + "/Roof/" + t, m_props, 3)
            if row["triangles"] >= 24:
                add_auto_lods(mesh)
                lib.save_asset(path)
            origin, extent = mesh_bounds(mesh)
            err = max_err(extent, row["expected_ue_local_bounds"]["extent_cm"])
            if err > EXTENT_TOLERANCE_CM:
                raise RuntimeError("extent drift %.3f cm" % err)
            props[t] = {"asset_path": path, "imported_bounds_origin_cm": origin,
                        "expected_bounds_origin_cm": row["expected_ue_local_bounds"]["origin_cm"],
                        "instances": row["instances"]}
        except Exception as exc:
            failures.append({"prop": t, "error": str(exc)})

    far = []
    for row in (far_rep or {}).get("chunks", []):
        try:
            key = "c%+03d_%+03d" % tuple(row["chunk"])
            path, mesh = import_mesh(LOOK_OUT / "farcity" / row["path"], MESH_DIR + "/FarCity/" + key.replace("+", "p").replace("-", "m"), m_city, 3)
            origin, extent = mesh_bounds(mesh)
            err = max_err(extent, row["expected_ue_local_bounds"]["extent_cm"])
            if err > EXTENT_TOLERANCE_CM:
                raise RuntimeError("extent drift %.3f cm" % err)
            far.append({"chunk": row["chunk"], "asset_path": path, "imported_bounds_origin_cm": origin,
                        "expected_bounds_origin_cm": row["expected_ue_local_bounds"]["origin_cm"],
                        "ue_actor_location_cm": row["ue_actor_location_cm"]})
        except Exception as exc:
            failures.append({"far_city_chunk": row["chunk"], "error": str(exc)})

    status = ("PASS_LOOK_ASSETS" if not failures and len(tiles) == 25 and len(singles) == 8
              and len(props) == len(roofs["types"]) else "FAIL_LOOK_ASSETS")
    report = {
        "status": status,
        "materials": {"city": "M_XinyiCity", "hero": "M_Taipei101", "ground": "M_XinyiGround",
                      "paint": "M_XinyiRoadPaint", "backdrop": "M_XinyiBackdrop", "foliage": "M_XinyiFoliage",
                      "props": "M_XinyiProps",
                      "clouds": clouds,
                      "mpc": MPC_PATH},
        "shader_source": str(SHADER),
        "tiles": tiles,
        "singles": singles,
        "rooftop_props": props,
        "far_city_chunks": far,
        "created": created,
        "failures": failures,
        "elapsed_seconds": time.perf_counter() - t0,
        "scope": "visual layer under /Game/XinyiLook only; /Game/XinyiV2 untouched",
    }
    write_report("look_assets.report.json", report)
    if status != "PASS_LOOK_ASSETS":
        raise RuntimeError("XinyiLook asset stage failed: %s" % json.dumps(failures)[:2000])


main()
