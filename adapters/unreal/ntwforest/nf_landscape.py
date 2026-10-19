"""North Taiwan forest world v1, Landscape material revision stage (UnrealEditor-Cmd, with RHI).

Creates M_NF_Landscape_R<rev> (+ imports the canopy bake textures once) and assigns it to NF_Terrain in L_NF_Yangmingshan; optional
lighting / fog values for the same map (ACW_NF_FOG_DENSITY, ACW_NF_SUN_AZ/EL). The v1 graph (nf_assets.py M_NF_Landscape) is kept
as evidence of the first-render failure: a Custom node fed with WorldPosition is not absolute under Large World Coordinates, so the
masks slid with the camera. Here every position-derived value (mask UV, canopy UV, block UV, camera distance, height) is computed with
standard LWC-safe nodes and only float values enter the Custom HLSL.

Far forest = the baked canopy of the game trees (nf_bake.py / pack_canopy.py): broad / acacia / crypt layers chosen by the species
fractions of the trees actually placed, each sampled at two scales and height-blended (crown-shaped transitions, no visible 96 m tile),
canopy normals bent onto the Landscape normal, gap darkening from the baked canopy height, stand-scale tone patches. Near forest =
understory under the 3D trees. Canopy shell (World Position Offset) as in v1.
Receipt: reports/nf_landscape_<rev>.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, MAP, MAT, RUN, TEX, find_actor, lib, link, mel, terrain_meta, tools, write_report  # noqa: E402

REV = os.environ.get("ACW_NF_LMAT_REV", "2")
LEVEL = MAP + "/L_NF_Yangmingshan"
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rep = {"status": "FAIL_NF_LANDSCAPE", "rev": REV, "error": None}
PARAMS = {"CanopyBright": float(os.environ.get("ACW_NF_CANOPY_BRIGHT", "1.25")), "NormalStrength": 1.0}
CANOPY_TINT = tuple(float(x) for x in os.environ.get("ACW_NF_CANOPY_TINT", "0.92,1.0,1.18").split(","))

COMMON = """float shell = saturate((D - SS) / (SE - SS));
float bias = (NB.g - 0.5) * 2.0 + (NA.a - 0.5);
float2 o2 = float2(0.37, 0.61);
float2 u2 = UVC * 0.731 + o2;
float4 b1 = Texture2DSample(CB, CBSampler, UVC); float4 b2 = Texture2DSample(CB, CBSampler, u2);
float sb = saturate((b1.a - b2.a) * 4.0 + bias * 1.5 + 0.5);
float4 a1 = Texture2DSample(CA, CASampler, UVC); float4 a2 = Texture2DSample(CA, CASampler, u2);
float sa = saturate((a1.a - a2.a) * 4.0 + bias * 1.5 + 0.5);
float4 c1 = Texture2DSample(CC, CCSampler, UVC); float4 c2 = Texture2DSample(CC, CCSampler, UVC + o2);
float sc = saturate((c1.a - c2.a) * 4.0 + bias * 1.5 + 0.5);
float wc = saturate(M2.r * 1.5 - 0.25);
float wa = saturate(M2.g * 1.5 - 0.25) * (1.0 - wc);
"""

BASE = COMMON + """float4 can = lerp(lerp(lerp(b2, b1, sb), lerp(a2, a1, sa), wa), lerp(c2, c1, sc), wc);
float tone = saturate(NA.g * 0.6 + NA.b * 0.4 + (NB.r - 0.5) * 0.3);
float3 tint = lerp(float3(0.86, 0.95, 1.12), float3(1.20, 1.10, 0.82), tone);
float3 canopy = can.rgb * tint * Tint * Bright * lerp(0.55, 1.0, saturate(can.a * 2.2));
float3 under = lerp(float3(0.017, 0.023, 0.010), float3(0.030, 0.034, 0.016), NB.b);
float3 forestC = lerp(under, canopy, shell);
float3 grass = lerp(float3(0.065, 0.080, 0.028), float3(0.12, 0.115, 0.05), saturate(NB.g * 0.8 + NB.a * 0.4)) * lerp(0.85, 1.12, NA.b);
float2 cb = floor(UVB * 1.6);
float ch = frac(sin(dot(cb, float2(12.9898, 78.233))) * 43758.5453);
float3 crops = lerp(float3(0.030, 0.045, 0.014), float3(0.070, 0.066, 0.034), ch) * lerp(0.9, 1.1, NB.a);   // paddies / vegetable plots / fallow
float built = saturate(RF.r * 2.5);                                   // local roof cover: dense town -> paved, sparse -> gardens / scrub
float green = saturate(1.0 - built + (NB.g - 0.5) * 0.8) * 0.9;
float3 veg = lerp(float3(0.020, 0.030, 0.011), float3(0.040, 0.048, 0.019), NB.b);
float3 yard = lerp(lerp(float3(0.030, 0.031, 0.030), float3(0.050, 0.049, 0.045), NB.a), veg, green);
float rfar = saturate((D - 600000.0) / 250000.0);
float3 roofc = lerp(float3(0.07, 0.07, 0.066), float3(0.12, 0.11, 0.10), saturate(NB.a * 1.2));
float3 urban = lerp(yard, roofc, saturate(RF.r * 1.2) * rfar);
float3 water = float3(0.010, 0.020, 0.024);
float rest = saturate(1.0 - M1.r - M1.g - M1.b - M1.a - M2.b);
float tot = M1.r + M1.g + M1.b + M1.a + M2.b + rest + 1e-4;
float3 c = (forestC * M1.r + grass * M1.g + urban * M1.b + water * M1.a + crops * M2.b + float3(0.06, 0.057, 0.046) * rest) / tot;
float rough = (0.9 * (M1.r + M1.g + M2.b + rest) + 0.8 * M1.b + 0.06 * M1.a) / tot;
float beach = saturate(1.0 - Z / 400.0) * saturate(Z / 50.0) * (1.0 - M1.r);
c = lerp(c, float3(0.16, 0.14, 0.11), beach * 0.8);
if (Z < -60.0) { c = float3(0.018, 0.028, 0.030); rough = 0.3; }
return float4(c, rough);"""

NORMAL = COMMON + """float3 n1 = lerp(lerp(lerp(Texture2DSample(NBr, NBrSampler, u2).xyz, Texture2DSample(NBr, NBrSampler, UVC).xyz, sb),
                        lerp(Texture2DSample(NAc, NAcSampler, u2).xyz, Texture2DSample(NAc, NAcSampler, UVC).xyz, sa), wa),
                   lerp(Texture2DSample(NCr, NCrSampler, UVC + o2).xyz, Texture2DSample(NCr, NCrSampler, UVC).xyz, sc), wc);
float3 cn = n1 * 2.0 - 1.0;
float k = saturate(M1.r * 1.3) * shell * NS;
return normalize(VN + float3(cn.xy, 0.0) * k / max(cn.z, 0.25));"""

WPO = """float shell = saturate((D - SS) / (SE - SS));
return float3(0.0, 0.0, M2A * 3200.0 * shell * SK);"""


def import_tex(name, srgb, normal=False):
    path = TEX + "/" + name
    if lib.does_asset_exist(path):
        return lib.load_asset(path)
    task = unreal.AssetImportTask()
    for k, v in (("filename", str(RUN / (name + ".png"))), ("destination_path", TEX), ("destination_name", name), ("automated", True),
                 ("replace_existing", False), ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    t = lib.load_asset(path)
    t.set_editor_property("srgb", srgb)
    if normal:   # world-space normals packed 0.5 + 0.5 n: keep linear, uncompressed-ish, no normal-map swizzle
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    lib.save_asset(path)
    return t


def custom(mat, x, y, code, inputs, otype):
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    return E(mat, unreal.MaterialExpressionCustom, x, y, code=code, inputs=ins, output_type=otype, description="NF" + REV)


def build():
    T = terrain_meta()
    L = T["landscape"]
    ext = (T["size"][0] - 1) * L["scale_xyz"][0]
    ox, oy = L["location_cm"][0], L["location_cm"][1]
    coll = lib.load_asset(MAT + "/MPC_NF_Forest")
    tex = {k: lib.load_asset(TEX + "/" + k) for k in ("T_NF_Mask1", "T_NF_Mask2", "T_NF_Noise")}
    tex["T_NF_Roofs"] = import_tex("T_NF_Roofs", False)
    for t in ("Broad", "Acacia", "Crypt"):
        tex["BC" + t] = import_tex("T_NF_Canopy_%s_BC" % t, True)
        tex["N" + t] = import_tex("T_NF_Canopy_%s_N" % t, False, True)
    name = "M_NF_Landscape_R" + REV
    if lib.does_asset_exist(MAT + "/" + name):
        raise RuntimeError(name + " exists: use a new ACW_NF_LMAT_REV")
    mat = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("tangent_space_normal", False)
    wp = E(mat, unreal.MaterialExpressionWorldPosition, -2600, 0)
    xy = E(mat, unreal.MaterialExpressionComponentMask, -2400, 0, r=True, g=True, b=False, a=False)
    link(wp, "", xy, "")
    zc = E(mat, unreal.MaterialExpressionComponentMask, -2400, 120, r=False, g=False, b=True, a=False)
    link(wp, "", zc, "")
    xs = E(mat, unreal.MaterialExpressionComponentMask, -2400, 240, r=True, g=False, b=False, a=False)
    ys = E(mat, unreal.MaterialExpressionComponentMask, -2400, 320, r=False, g=True, b=False, a=False)
    link(wp, "", xs, "")
    link(wp, "", ys, "")
    # mask UV = (xy - origin) / extent
    sub = E(mat, unreal.MaterialExpressionSubtract, -2200, 0)
    link(xy, "", sub, "A")
    link(E(mat, unreal.MaterialExpressionConstant2Vector, -2400, -120, r=ox, g=oy), "", sub, "B")
    uvm = E(mat, unreal.MaterialExpressionDivide, -2050, 0, const_b=ext)
    link(sub, "", uvm, "A")

    def scaled(src, k, x, y):
        m = E(mat, unreal.MaterialExpressionMultiply, x, y, const_b=k)
        link(src, "", m, "A")
        return m

    def sample(t, uv, x, y):
        s = E(mat, unreal.MaterialExpressionTextureSample, x, y, texture=t)
        cs = t.get_editor_property("compression_settings")
        st = (unreal.MaterialSamplerType.SAMPLERTYPE_MASKS if cs == unreal.TextureCompressionSettings.TC_MASKS
              else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR if t.get_editor_property("srgb") else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        s.set_editor_property("sampler_type", st)
        link(uv, "", s, "UVs")
        return s

    m1 = sample(tex["T_NF_Mask1"], uvm, -1800, -200)
    m2 = sample(tex["T_NF_Mask2"], uvm, -1800, 100)
    na = sample(tex["T_NF_Noise"], scaled(xy, 1.0 / 409600.0, -2050, 400), -1800, 400)
    nbuv = E(mat, unreal.MaterialExpressionAdd, -2000, 600, const_b=0.37)
    link(scaled(xy, 1.0 / 25600.0, -2200, 600), "", nbuv, "A")
    nb = sample(tex["T_NF_Noise"], nbuv, -1800, 700)
    # canopy UV = (Y / 96 m, -X / 96 m): the bake image's column axis is world +Y and its row axis world -X
    uvc = E(mat, unreal.MaterialExpressionAppendVector, -2000, 900)
    link(scaled(ys, 1.0 / 9600.0, -2200, 850), "", uvc, "A")
    link(scaled(xs, -1.0 / 9600.0, -2200, 950), "", uvc, "B")
    uvb = scaled(xy, 1.0 / 4000.0, -2050, 1100)                       # 40 m town blocks / 25 m fields
    dist = E(mat, unreal.MaterialExpressionDistance, -2050, 1250)
    link(wp, "", dist, "A")
    link(E(mat, unreal.MaterialExpressionCameraPositionWS, -2300, 1300), "", dist, "B")

    def cp(nm, x, y):
        return E(mat, unreal.MaterialExpressionCollectionParameter, x, y, collection=coll, parameter_name=nm)

    def tobj(nm, t, x, y):
        return E(mat, unreal.MaterialExpressionTextureObjectParameter, x, y, parameter_name=nm, texture=t)

    common_in = {"M1": (m1, "RGBA"), "M2": (m2, "RGBA"), "NA": (na, "RGBA"), "NB": (nb, "RGBA"), "UVC": (uvc, ""), "D": (dist, ""),
                 "SS": (cp("ShellStart", -1500, 1400), ""), "SE": (cp("ShellEnd", -1500, 1480), "")}
    texin = {"CB": tobj("CanopyBroad", tex["BCBroad"], -1300, 1600), "CA": tobj("CanopyAcacia", tex["BCAcacia"], -1300, 1700),
             "CC": tobj("CanopyCrypt", tex["BCCrypt"], -1300, 1800)}
    base = custom(mat, -700, 0, BASE, list(common_in) + list(texin) + ["UVB", "Z", "Bright", "Tint", "RF"], unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    for k, (n, pin) in common_in.items():
        link(n, pin, base, k)
    for k, n in texin.items():
        link(n, "", base, k)
    link(uvb, "", base, "UVB")
    link(sample(tex["T_NF_Roofs"], uvm, -1800, 1000), "RGBA", base, "RF")
    link(zc, "", base, "Z")
    link(E(mat, unreal.MaterialExpressionScalarParameter, -1300, 1950, parameter_name="CanopyBright", default_value=PARAMS["CanopyBright"]), "", base, "Bright")
    link(E(mat, unreal.MaterialExpressionVectorParameter, -1300, 2050, parameter_name="CanopyTint",
           default_value=unreal.LinearColor(CANOPY_TINT[0], CANOPY_TINT[1], CANOPY_TINT[2], 1)), "", base, "Tint")
    rgb = E(mat, unreal.MaterialExpressionComponentMask, -400, 0, r=True, g=True, b=True, a=False)
    rough = E(mat, unreal.MaterialExpressionComponentMask, -400, 120, r=False, g=False, b=False, a=True)
    link(base, "", rgb, "")
    link(base, "", rough, "")
    mel.connect_material_property(rgb, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant, -400, 220, r=0.35), "", unreal.MaterialProperty.MP_SPECULAR)
    ntex = {"NBr": tobj("CanopyBroadN", tex["NBroad"], -1300, 2200), "NAc": tobj("CanopyAcaciaN", tex["NAcacia"], -1300, 2300),
            "NCr": tobj("CanopyCryptN", tex["NCrypt"], -1300, 2400)}
    nrm = custom(mat, -700, 600, NORMAL, list(common_in) + list(texin) + list(ntex) + ["VN", "NS"], unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    for k, (n, pin) in common_in.items():
        link(n, pin, nrm, k)
    for k, n in dict(texin, **ntex).items():
        link(n, "", nrm, k)
    link(E(mat, unreal.MaterialExpressionVertexNormalWS, -1300, 2500), "", nrm, "VN")
    link(E(mat, unreal.MaterialExpressionScalarParameter, -1300, 2600, parameter_name="NormalStrength", default_value=PARAMS["NormalStrength"]), "", nrm, "NS")
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    wpo = custom(mat, -700, 1200, WPO, ["M2A", "D", "SS", "SE", "SK"], unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    link(m2, "A", wpo, "M2A")
    link(dist, "", wpo, "D")
    link(cp("ShellStart", -1000, 1300), "", wpo, "SS")
    link(cp("ShellEnd", -1000, 1380), "", wpo, "SE")
    link(cp("ShellScale", -1000, 1460), "", wpo, "SK")
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    mel.recompile_material(mat)
    lib.save_asset(MAT + "/" + name, only_if_is_dirty=False)
    rep["material"] = MAT + "/" + name
    rep["params"] = dict(PARAMS, CanopyTint=CANOPY_TINT)
    return mat


def apply(mat):
    if not les.load_level(LEVEL):
        raise RuntimeError("load " + LEVEL)
    n = 0
    for a in ues.get_all_level_actors():
        if a.get_class().get_name() in ("Landscape", "LandscapeStreamingProxy"):
            a.set_editor_property("landscape_material", mat)
            n += 1
    if os.environ.get("ACW_NF_FOG_DENSITY"):
        for a in ues.get_all_level_actors():
            if a.get_class().get_name() == "ExponentialHeightFog":
                c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
                c.set_editor_property("fog_density", float(os.environ["ACW_NF_FOG_DENSITY"]))
                c.set_editor_property("fog_height_falloff", float(os.environ.get("ACW_NF_FOG_FALLOFF", "0.035")))
                rep["fog"] = {"density": float(os.environ["ACW_NF_FOG_DENSITY"]), "falloff": float(os.environ.get("ACW_NF_FOG_FALLOFF", "0.035"))}
    if not les.save_current_level():
        raise RuntimeError("save level")
    rep["landscape_actors"] = n


try:
    m = build()
    apply(m)
    rep["status"] = "PASS_NF_LANDSCAPE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_landscape_%s.report.json" % REV, rep)
unreal.SystemLibrary.quit_editor()
