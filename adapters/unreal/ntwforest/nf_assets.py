"""North Taiwan forest world v1, stage 1 (UnrealEditor-Cmd): textures, parameter collection and materials under /Game/NorthForest.

* T_NF_Mask1 / T_NF_Mask2 / T_NF_Noise (build_region.py / make_noise.py), linear, clamp (masks) / wrap (noise).
* MPC_NF_Forest: distance-thinning and canopy-shell distances (cm), so one set of numbers drives trees and terrain together and a
  scalability tier is a runtime parameter change, not a rebuild.
* Tree materials M_NF_*: DUPLICATES of the accepted species materials (originals untouched) with one addition - a per-instance
  distance-thinning keep mask: each tree i has its own vanish distance T_i = Near + (End - Near) * rand_i^Gamma and dissolves over
  FadeWidth with a screen-space interleaved-gradient dither, so the 3D forest thins gradually instead of a cull line. Bark becomes
  Masked for the same dissolve. MI_NF_Leaf_V0..V9 = the accepted hillside tint variants (parameters of the source graphs only).
* M_NF_Landscape: world-position sampled land-cover masks; forest = understory near the camera, a canopy colour at distance, and
  the far forest raised by a canopy shell (World Position Offset = local canopy height x distance blend) so ridgelines keep their
  forest silhouette after the 3D trees have thinned out.
* M_NF_Water: opaque sea surface.
Receipt: reports/nf_assets.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import (E, FORM_BARK_SRC, FORM_LEAF_SRC, LEAF_VARIANTS, MAT, RUN, SRC_MAT, TEX, VARIANT_FORM, ensure_dir, lib, link, mel,  # noqa: E402
                       terrain_meta, tools, write_report)

rep = {"status": "FAIL_NF_ASSETS", "textures": {}, "materials": {}, "error": None}
# PC tier defaults (metres): full density to 450 m, last tree gone by 2,400 m, canopy shell / colour from 700 to 2,000 m
MPC_DEFAULTS = {"NearFull": 45000.0, "ThinEnd": 240000.0, "FadeWidth": 12000.0, "ThinGamma": 1.6,
                "ShellStart": 70000.0, "ShellEnd": 200000.0, "ShellScale": 0.8}


def import_texture(name, srgb, clamp):
    path = TEX + "/" + name
    if lib.does_asset_exist(path):
        raise RuntimeError("refusing to overwrite " + path)
    task = unreal.AssetImportTask()
    for k, v in (("filename", str(RUN / (name + ".png"))), ("destination_path", TEX), ("destination_name", name), ("automated", True),
                 ("replace_existing", False), ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    tex = lib.load_asset(path)
    if tex is None:
        raise RuntimeError("texture import failed " + name)
    tex.set_editor_property("srgb", srgb)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    if clamp:
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    if not lib.save_asset(path):
        raise RuntimeError("save " + path)
    rep["textures"][name] = {"path": path, "size": [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()]}
    return tex


def mpc():
    path = MAT + "/MPC_NF_Forest"
    c = tools.create_asset("MPC_NF_Forest", MAT, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    params = []
    for k, v in MPC_DEFAULTS.items():
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", k)
        p.set_editor_property("default_value", v)
        params.append(p)
    c.set_editor_property("scalar_parameters", params)
    lib.save_asset(path)
    rep["mpc"] = {"path": path, "defaults_cm": MPC_DEFAULTS}
    return c


def cp(mat, coll, name, x, y):
    return E(mat, unreal.MaterialExpressionCollectionParameter, x, y, collection=coll, parameter_name=name)


def custom(mat, x, y, code, inputs, otype):
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    return E(mat, unreal.MaterialExpressionCustom, x, y, code=code, inputs=ins, output_type=otype, description="NF")


KEEP_HLSL = """float T = Near + (End - Near) * pow(saturate(R), Gamma);
float k = saturate((T - D) / Width);
float n = frac(52.9829189 * frac(dot(Pix + 5.588238 * (float)View.StateFrameIndexMod8, float2(0.06711056, 0.00583715))));
return (k > n) ? 1.0 : 0.0;"""


def keep_node(mat, coll, x, y):
    k = custom(mat, x, y, KEEP_HLSL, ["D", "R", "Pix", "Near", "End", "Width", "Gamma"], unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    d = E(mat, unreal.MaterialExpressionDistance, x - 300, y - 200)
    link(E(mat, unreal.MaterialExpressionWorldPosition, x - 550, y - 260), "", d, "A")
    link(E(mat, unreal.MaterialExpressionCameraPositionWS, x - 550, y - 160), "", d, "B")
    link(d, "", k, "D")
    link(E(mat, unreal.MaterialExpressionPerInstanceRandom, x - 300, y - 80), "", k, "R")
    link(E(mat, unreal.MaterialExpressionScreenPosition, x - 300, y), "PixelPosition", k, "Pix")
    for i, (pin, name) in enumerate((("Near", "NearFull"), ("End", "ThinEnd"), ("Width", "FadeWidth"), ("Gamma", "ThinGamma"))):
        link(cp(mat, coll, name, x - 300, y + 80 + 70 * i), "", k, pin)
    return k


def finish(mat, path):
    mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    mel.recompile_material(mat)
    if not lib.save_asset(path, only_if_is_dirty=False):
        raise RuntimeError("save " + path)
    rep["materials"][path] = {"ism": bool(mat.get_editor_property("used_with_instanced_static_meshes")),
                              "blend": str(mat.get_editor_property("blend_mode"))}
    if not rep["materials"][path]["ism"]:
        raise RuntimeError("ISM usage flag did not stick on " + path)


def tree_materials(coll):
    made = {}
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        dst = MAT + "/" + src.replace("M_TL_", "M_NF_")
        if not lib.duplicate_asset(SRC_MAT + "/" + src, dst):
            raise RuntimeError("duplicate %s" % src)
        mat = lib.load_asset(dst)
        leaf = "Leaf" in src
        keep = keep_node(mat, coll, -900, 1100)
        if leaf:
            alpha = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_OPACITY_MASK)
            if alpha is None:
                raise RuntimeError("no opacity input on " + src)
            mul = E(mat, unreal.MaterialExpressionMultiply, -150, 900)
            link(alpha, "A", mul, "A")
            link(keep, "", mul, "B")
            mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_OPACITY_MASK)
        else:
            mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
            mat.set_editor_property("opacity_mask_clip_value", 0.5)
            mel.connect_material_property(keep, "", unreal.MaterialProperty.MP_OPACITY_MASK)
        finish(mat, dst)
        made[src] = mat
    mics = {}
    for v, params in LEAF_VARIANTS.items():
        parent = made[FORM_LEAF_SRC[VARIANT_FORM[v]]]
        name = "MI_NF_Leaf_V%d" % v
        mic = tools.create_asset(name, MAT, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mic, parent)
        for k, val in params.items():
            if isinstance(val, tuple):
                mel.set_material_instance_vector_parameter_value(mic, k, unreal.LinearColor(val[0], val[1], val[2], 1.0))
                c = mel.get_material_instance_vector_parameter_value(mic, k)
                ok = all(abs(a - b) < 1e-4 for a, b in zip((c.r, c.g, c.b), val))
            else:
                mel.set_material_instance_scalar_parameter_value(mic, k, float(val))
                ok = abs(mel.get_material_instance_scalar_parameter_value(mic, k) - val) < 1e-4
            if not ok:
                raise RuntimeError("%s: %s not applied" % (name, k))
        mel.update_material_instance(mic)
        lib.save_asset(MAT + "/" + name)
        mics[v] = name
    rep["leaf_instances"] = mics


LAND_HLSL = """float2 uv = (WP.xy - float2(%(ox).1f, %(oy).1f)) / %(ext).1f;
float4 m1 = Texture2DSample(Mask1, Mask1Sampler, uv);
float4 m2 = Texture2DSample(Mask2, Mask2Sampler, uv);
float4 nA = Texture2DSample(Noise, NoiseSampler, WP.xy / 409600.0);
float4 nB = Texture2DSample(Noise, NoiseSampler, WP.xy / 25600.0 + 0.37);
float d = length(WP - Cam);
float shell = saturate((d - SS) / (SE - SS));
float tone = saturate(0.55 * nA.g + 0.45 * nA.b + 0.35 * (nB.r - 0.5));
float3 broad = lerp(float3(0.028, 0.044, 0.015), float3(0.060, 0.078, 0.025), tone);
float3 canopy = lerp(lerp(broad, float3(0.060, 0.070, 0.027), m2.g), float3(0.019, 0.031, 0.021), m2.r);
canopy *= lerp(0.70, 1.20, saturate(0.7 * nB.g + 0.5 * nB.b - 0.1));
float3 under = lerp(float3(0.017, 0.023, 0.010), float3(0.030, 0.034, 0.016), nB.b);
float3 forestC = lerp(under, canopy, shell);
float3 grass = lerp(float3(0.10, 0.11, 0.040), float3(0.17, 0.155, 0.065), nB.g) * lerp(0.85, 1.10, nA.b);
float3 crops = lerp(float3(0.07, 0.09, 0.03), float3(0.13, 0.13, 0.06), nB.r);
float3 urban = lerp(float3(0.085, 0.085, 0.08), float3(0.20, 0.19, 0.17), step(0.55, nB.b)) * lerp(0.8, 1.15, nB.a);
float3 water = float3(0.010, 0.020, 0.024);
float rest = saturate(1.0 - m1.r - m1.g - m1.b - m1.a - m2.b);
float tot = m1.r + m1.g + m1.b + m1.a + m2.b + rest + 1e-4;
float3 c = (forestC * m1.r + grass * m1.g + urban * m1.b + water * m1.a + crops * m2.b + float3(0.11, 0.10, 0.075) * rest) / tot;
float rough = (0.9 * (m1.r + m1.g + m2.b + rest) + 0.75 * m1.b + 0.06 * m1.a) / tot;
float beach = saturate(1.0 - WP.z / 400.0) * saturate(WP.z / 50.0) * (1.0 - m1.r);
c = lerp(c, float3(0.24, 0.21, 0.16), beach * 0.8);
if (WP.z < -60.0) { c = float3(0.018, 0.028, 0.030); rough = 0.3; }
return float4(c, rough);"""

WPO_HLSL = """float2 uv = (WP.xy - float2(%(ox).1f, %(oy).1f)) / %(ext).1f;
float4 m2 = Texture2DSampleLevel(Mask2, Mask2Sampler, uv, 0);
float shell = saturate((length(WP - Cam) - SS) / (SE - SS));
return float3(0.0, 0.0, m2.a * 3200.0 * shell * SK);"""


def landscape_material(coll, m1, m2, noise):
    T = terrain_meta()
    L = T["landscape"]
    ext = T["size"][0] - 1
    fmt = {"ox": L["location_cm"][0], "oy": L["location_cm"][1], "ext": ext * L["scale_xyz"][0]}
    path = MAT + "/M_NF_Landscape"
    mat = tools.create_asset("M_NF_Landscape", MAT, unreal.Material, unreal.MaterialFactoryNew())

    def wire(node, extra_masks=True):
        link(E(mat, unreal.MaterialExpressionWorldPosition, node.get_editor_property("material_expression_editor_x") - 400, 0), "", node, "WP")
        link(E(mat, unreal.MaterialExpressionCameraPositionWS, -1500, 100), "", node, "Cam")
        link(cp(mat, coll, "ShellStart", -1500, 200), "", node, "SS")
        link(cp(mat, coll, "ShellEnd", -1500, 280), "", node, "SE")

    base = custom(mat, -600, 0, LAND_HLSL % fmt, ["WP", "Cam", "Mask1", "Mask2", "Noise", "SS", "SE"], unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    wire(base)
    for nm, tex, y in (("Mask1", m1, 400), ("Mask2", m2, 520), ("Noise", noise, 640)):
        link(E(mat, unreal.MaterialExpressionTextureObjectParameter, -1100, y, parameter_name=nm, texture=tex), "", base, nm)
    rgb = E(mat, unreal.MaterialExpressionComponentMask, -250, 0, r=True, g=True, b=True, a=False)
    rough = E(mat, unreal.MaterialExpressionComponentMask, -250, 120, r=False, g=False, b=False, a=True)
    link(base, "", rgb, "")
    link(base, "", rough, "")
    mel.connect_material_property(rgb, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant, -250, 220, r=0.35), "", unreal.MaterialProperty.MP_SPECULAR)
    wpo = custom(mat, -600, 800, WPO_HLSL % fmt, ["WP", "Cam", "Mask2", "SS", "SE", "SK"], unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    wire(wpo)
    link(E(mat, unreal.MaterialExpressionTextureObjectParameter, -1100, 900, parameter_name="Mask2W", texture=m2), "", wpo, "Mask2")
    link(cp(mat, coll, "ShellScale", -1500, 1000), "", wpo, "SK")
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    mel.recompile_material(mat)
    lib.save_asset(path, only_if_is_dirty=False)
    rep["materials"][path] = {"uv_origin_cm": [fmt["ox"], fmt["oy"]], "extent_cm": fmt["ext"]}


def water_material():
    path = MAT + "/M_NF_Water"
    mat = tools.create_asset("M_NF_Water", MAT, unreal.Material, unreal.MaterialFactoryNew())
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant3Vector, -400, 0, constant=unreal.LinearColor(0.008, 0.020, 0.026, 1)),
                                  "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant, -400, 150, r=0.07), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant, -400, 250, r=0.5), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(mat)
    lib.save_asset(path, only_if_is_dirty=False)
    rep["materials"][path] = {}


try:
    if lib.does_directory_exist(MAT):
        raise RuntimeError(MAT + " exists: delete /Game/NorthForest/Materials+Textures explicitly to rebuild")
    for d in ("/Game/NorthForest", MAT, TEX):
        ensure_dir(d)
    m1 = import_texture("T_NF_Mask1", False, True)
    m2 = import_texture("T_NF_Mask2", False, True)
    noise = import_texture("T_NF_Noise", False, False)
    coll = mpc()
    tree_materials(coll)
    landscape_material(coll, m1, m2, noise)
    water_material()
    rep["status"] = "PASS_NF_ASSETS"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_assets.report.json", rep)
unreal.SystemLibrary.quit_editor()
