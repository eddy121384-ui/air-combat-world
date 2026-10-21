"""North Taiwan forest world - DISTANCE-LAYER Landscape material (UnrealEditor-Cmd, with RHI): "near = forest, far = mountain form".

Creates M_NF_LandscapeDL_R<rev> and assigns it to NF_Terrain (+ optional fog values). Same LWC-safe node plumbing as nf_landscape.py
(rev 6 = the PR #46 look, kept as the "before"); the Custom HLSL is restructured into distance bands:
  0 - 1.2 km   understory under the 3D trees (trees carry the forest)
  1.2 - 3 km   baked game-tree canopy (two-scale height blend) + a crown-cluster layer; canopy shell rises (WPO)
  3.5 - 6 km   canopy detail -> MACRO forest colour: species blocks (cryptomeria dark blue-green, acacia olive, broadleaf) + stand tone
  7 - 11 km    macro -> mountain-form palette (less saturation, relief carried by the terrain skin)
and a terrain SKIN on every band, stronger with distance, from terrain_skin.py (T_NF_Terrain): ridges warmer / lighter, valleys cooler,
gullies darker, low openness darker, steep open slopes showing soil; grass golden on ridges, greener in hollows; volcanic bare ground.
Canopy normals fade out with distance (with them, backlit far forest read grey-white); vegetation specular lowered.
ACW_NF_DL_MOBILE=1 (mobile forest profile, rev 4+): the same graph gains `#if SHADING_PATH_MOBILE` branches that the mobile renderer
compiles - canopy shell / canopy colour on the MPC mobile distances (ShellStartM / ShellEndM), the baked canopy also UNDER the thinner
near trees (NearCanopyM: gaps between kept trees read as crowns, not as understory) and single-scale canopy normals (3 texture fetches
instead of 6). The world-sized masks (T_NF_Mask1 / Mask2 / Terrain / Roofs) are made never-stream: they cover the whole map, are
always on screen, and when they streamed in late after a cut the far forest showed blurred low-mip colour blocks.
Receipt: reports/nf_landscape_dl_<rev>.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, MAP, MAT, RUN, TEX, find_actor, lib, link, mel, terrain_meta, tools, write_report  # noqa: E402

REV = os.environ.get("ACW_NF_LMAT_REV", "1")
LEVEL = MAP + "/L_NF_Yangmingshan"
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rep = {"status": "FAIL_NF_LANDSCAPE", "rev": REV, "error": None}
PARAMS = {"CanopyBright": float(os.environ.get("ACW_NF_CANOPY_BRIGHT", "1.25")), "NormalStrength": 1.0}
# distance bands (cm) and terrain-skin strength near / far; material parameters, so a look tweak is a material-instance edit
BANDS = {k: float(os.environ.get("ACW_NF_DL_" + k, v)) for k, v in (("FA0", 350000.0), ("FA1", 600000.0), ("FB0", 700000.0),
                                                                   ("FB1", 1100000.0), ("SK0", 0.30), ("SK1", 1.0))}
CANOPY_TINT = tuple(float(x) for x in os.environ.get("ACW_NF_CANOPY_TINT", "0.92,1.0,1.18").split(","))

MOBILE = os.environ.get("ACW_NF_DL_MOBILE") == "1"
MPRE = """#if SHADING_PATH_MOBILE
SS = SSm; SE = SEm;
#endif
"""
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

if MOBILE:
    COMMON = MPRE + COMMON

BASE = COMMON + """float far1 = saturate((D - FA0) / (FA1 - FA0));
float far2 = saturate((D - FB0) / (FB1 - FB0));
float rg = TS.r * 2.0 - 1.0;
float3 skin = lerp(float3(0.80, 0.90, 0.86), float3(1.16, 1.09, 0.88), saturate(rg * 0.8 + 0.5));
float skinAO = lerp(0.48, 1.0, TS.a) * (1.0 - 0.45 * TS.g);
float skinK = SK0 + (SK1 - SK0) * far1;
float4 can = lerp(lerp(lerp(b2, b1, sb), lerp(a2, a1, sa), wa), lerp(c2, c1, sc), wc);
float4 cl = Texture2DSample(CB, CBSampler, UVC * 0.27 + 0.13);
float clump = lerp(0.70, 1.10, saturate(cl.a * 1.6 + (NB.r - 0.5) * 0.6));
float tone = saturate(NA.g * 0.6 + NA.b * 0.4 + (NB.r - 0.5) * 0.3);
float3 tint = lerp(float3(0.86, 0.95, 1.12), float3(1.20, 1.10, 0.82), tone);
float3 canopy = can.rgb * tint * Tint * Bright * lerp(0.55, 1.0, saturate(can.a * 2.2)) * lerp(1.0, clump, saturate(shell * 1.5));
float mtone = saturate(NA.g * 0.7 + NA.r * 0.3);
float3 mtint = lerp(float3(0.80, 0.92, 1.10), float3(1.26, 1.13, 0.80), mtone) * lerp(0.86, 1.10, NA.a);   // stand tone + ~30 m mottling
float3 macro = lerp(lerp(float3(0.0140, 0.0230, 0.0042), float3(0.0205, 0.0288, 0.0077), wa), float3(0.0095, 0.0178, 0.0084), wc) * mtint * Tint * Bright * 0.74;
float lum = dot(macro, float3(0.3, 0.59, 0.11));
float3 mount = lerp(macro, lum * float3(0.80, 1.05, 1.02), 0.15);
float3 farForest = lerp(lerp(canopy, macro, far1), mount, far2);
float3 under = lerp(float3(0.017, 0.023, 0.010), float3(0.030, 0.034, 0.016), NB.b);
float sh = shell;
#if SHADING_PATH_MOBILE
sh = max(shell, NC);
#endif
float3 forestC = lerp(under, farForest, sh);
float3 grass = lerp(float3(0.058, 0.074, 0.026), float3(0.11, 0.105, 0.046), saturate(NB.g * 0.8 + NB.a * 0.4)) * lerp(0.85, 1.12, NA.b);
grass = lerp(grass, grass * float3(1.18, 1.05, 0.80), saturate(rg));
grass = lerp(grass, grass * float3(0.85, 1.05, 0.95), saturate(-rg));
grass = lerp(grass, float3(0.085, 0.088, 0.040), far1 * 0.5);
float fa = NA.b * 3.1416;
float2 fq = float2(cos(fa) * UVB.x - sin(fa) * UVB.y, sin(fa) * UVB.x + cos(fa) * UVB.y) * float2(2.4, 1.2) + (NB.rg - 0.5) * 0.5;
float2 cb = floor(fq);
float ch = frac(sin(dot(cb, float2(12.9898, 78.233))) * 43758.5453);
float2 ff = frac(fq);
float bund = (min(min(ff.x, 1.0 - ff.x) * 2.4, min(ff.y, 1.0 - ff.y) * 1.2) < 0.06) ? 0.8 : 1.0;
float3 crops = lerp(float3(0.024, 0.040, 0.012), float3(0.055, 0.056, 0.028), ch) * lerp(0.9, 1.1, NB.a) * bund;
crops = lerp(crops, float3(0.036, 0.046, 0.018), far1);
float built = saturate(RF.r * 2.5);
float green = saturate(1.0 - built + (NB.g - 0.5) * 0.8) * 0.9;
float3 veg = lerp(float3(0.020, 0.030, 0.011), float3(0.040, 0.048, 0.019), NB.b);
float3 yard = lerp(lerp(float3(0.030, 0.031, 0.030), float3(0.050, 0.049, 0.045), NB.a), veg, green);
float rfar = saturate((D - 600000.0) / 250000.0);
float3 roofc = lerp(float3(0.07, 0.07, 0.066), float3(0.12, 0.11, 0.10), saturate(NB.a * 1.2));
float3 urban = lerp(yard, roofc, saturate(RF.r * 1.2) * rfar);
float3 water = float3(0.010, 0.020, 0.024);
float3 bare = lerp(float3(0.075, 0.070, 0.050), float3(0.105, 0.098, 0.066), NB.g);
float rest = saturate(1.0 - M1.r - M1.g - M1.b - M1.a - M2.b);
float tot = M1.r + M1.g + M1.b + M1.a + M2.b + rest + 1e-4;
float3 c = (forestC * M1.r + grass * M1.g + urban * M1.b + water * M1.a + crops * M2.b + bare * rest) / tot;
float soil = saturate((TS.b - 0.58) * 5.0) * saturate(1.0 - M1.r * 1.3 - M1.a - M1.b) * (0.6 + 0.4 * NB.b);
c = lerp(c, float3(0.070, 0.058, 0.042), soil);
float landw = 1.0 - M1.a;
c *= lerp(float3(1, 1, 1), lerp(float3(1, 1, 1), skin, skinK) * lerp(1.0, skinAO, saturate(skinK + 0.2)), landw);
float rough = (0.95 * (M1.r + M1.g + M2.b + rest) + 0.8 * M1.b + 0.06 * M1.a) / tot;
float beach = saturate(1.0 - Z / 400.0) * saturate(Z / 50.0) * (1.0 - M1.r);
c = lerp(c, float3(0.16, 0.14, 0.11), beach * 0.8);
if (Z < -60.0) { c = float3(0.018, 0.028, 0.030); rough = 0.3; }
return float4(c, rough);"""

NORMAL = COMMON + """#if SHADING_PATH_MOBILE
float3 n1 = lerp(lerp(Texture2DSample(NBr, NBrSampler, UVC).xyz, Texture2DSample(NAc, NAcSampler, UVC).xyz, wa),
                 Texture2DSample(NCr, NCrSampler, UVC).xyz, wc);
shell = max(shell, NC);
#else
float3 n1 = lerp(lerp(lerp(Texture2DSample(NBr, NBrSampler, u2).xyz, Texture2DSample(NBr, NBrSampler, UVC).xyz, sb),
                        lerp(Texture2DSample(NAc, NAcSampler, u2).xyz, Texture2DSample(NAc, NAcSampler, UVC).xyz, sa), wa),
                   lerp(Texture2DSample(NCr, NCrSampler, UVC + o2).xyz, Texture2DSample(NCr, NCrSampler, UVC).xyz, sc), wc);
#endif
float3 cn = n1 * 2.0 - 1.0;
float k = saturate(M1.r * 1.3) * shell * NS * (1.0 - saturate((D - 250000.0) / 250000.0));   // far: geometric relief only
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
    tex["T_NF_Terrain"] = import_tex("T_NF_Terrain", False)
    if MOBILE:   # world-sized masks: always resident
        for k in ("T_NF_Mask1", "T_NF_Mask2", "T_NF_Roofs", "T_NF_Terrain"):
            tex[k].set_editor_property("never_stream", True)
            lib.save_asset(TEX + "/" + k, only_if_is_dirty=False)
        rep["never_stream"] = ["T_NF_Mask1", "T_NF_Mask2", "T_NF_Roofs", "T_NF_Terrain"]
    for t in ("Broad", "Acacia", "Crypt"):
        tex["BC" + t] = import_tex("T_NF_Canopy_%s_BC" % t, True)
        tex["N" + t] = import_tex("T_NF_Canopy_%s_N" % t, False, True)
    name = "M_NF_LandscapeDL_R" + REV
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
    if MOBILE:
        common_in.update({"SSm": (cp("ShellStartM", -1500, 1560), ""), "SEm": (cp("ShellEndM", -1500, 1640), ""),
                          "NC": (cp("NearCanopyM", -1500, 1720), "")})
    texin = {"CB": tobj("CanopyBroad", tex["BCBroad"], -1300, 1600), "CA": tobj("CanopyAcacia", tex["BCAcacia"], -1300, 1700),
             "CC": tobj("CanopyCrypt", tex["BCCrypt"], -1300, 1800)}
    base = custom(mat, -700, 0, BASE, list(common_in) + list(texin) + ["UVB", "Z", "Bright", "Tint", "RF", "TS"] + list(BANDS), unreal.CustomMaterialOutputType.CMOT_FLOAT4)
    for k, (n, pin) in common_in.items():
        link(n, pin, base, k)
    for k, n in texin.items():
        link(n, "", base, k)
    link(uvb, "", base, "UVB")
    link(sample(tex["T_NF_Roofs"], uvm, -1800, 1000), "RGBA", base, "RF")
    link(sample(tex["T_NF_Terrain"], uvm, -1800, 1150), "RGBA", base, "TS")
    for i, (k, v) in enumerate(BANDS.items()):
        link(E(mat, unreal.MaterialExpressionScalarParameter, -1300, 2700 + 80 * i, parameter_name=k, default_value=v), "", base, k)
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
    # specular: ~0 on land (a canopy / grass sward has almost no coherent specular; with 0.18 the grazing-angle Fresnel reflection of the
    # sky turned backlit far forest grey-lavender - shown by a fog-off diagnostic render), water keeps 0.5
    spec = E(mat, unreal.MaterialExpressionLinearInterpolate, -400, 220, const_a=float(os.environ.get("ACW_NF_LAND_SPEC", "0.02")), const_b=0.5)
    link(m1, "A", spec, "Alpha")
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
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
    wpo = custom(mat, -700, 1200, (MPRE if MOBILE else "") + WPO, ["M2A", "D", "SS", "SE", "SK"] + (["SSm", "SEm"] if MOBILE else []),
                 unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    if MOBILE:
        link(cp("ShellStartM", -1000, 1540), "", wpo, "SSm")
        link(cp("ShellEndM", -1000, 1620), "", wpo, "SEm")
    link(m2, "A", wpo, "M2A")
    link(dist, "", wpo, "D")
    link(cp("ShellStart", -1000, 1300), "", wpo, "SS")
    link(cp("ShellEnd", -1000, 1380), "", wpo, "SE")
    link(cp("ShellScale", -1000, 1460), "", wpo, "SK")
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    mel.recompile_material(mat)
    lib.save_asset(MAT + "/" + name, only_if_is_dirty=False)
    rep["material"] = MAT + "/" + name
    rep["params"] = dict(PARAMS, CanopyTint=CANOPY_TINT, bands=BANDS)
    return mat


def apply(mat):
    if not les.load_level(LEVEL):
        raise RuntimeError("load " + LEVEL)
    n = 0
    for a in ues.get_all_level_actors():
        if a.get_class().get_name() in ("Landscape", "LandscapeStreamingProxy"):
            a.modify()
            a.set_editor_property("landscape_material", mat)
            n += 1
    if os.environ.get("ACW_NF_FOG_DENSITY"):
        for a in ues.get_all_level_actors():
            if a.get_class().get_name() == "ExponentialHeightFog":
                a.modify()
                c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
                c.modify()
                c.set_editor_property("fog_density", float(os.environ["ACW_NF_FOG_DENSITY"]))
                c.set_editor_property("fog_height_falloff", float(os.environ.get("ACW_NF_FOG_FALLOFF", "0.035")))
                if os.environ.get("ACW_NF_FOG_START_CM"):
                    c.set_editor_property("start_distance", float(os.environ["ACW_NF_FOG_START_CM"]))
                if os.environ.get("ACW_NF_FOG_MAXOPACITY"):
                    c.set_editor_property("fog_max_opacity", float(os.environ["ACW_NF_FOG_MAXOPACITY"]))
                if os.environ.get("ACW_NF_FOG_COLOR"):
                    fc = [float(x) for x in os.environ["ACW_NF_FOG_COLOR"].split(",")]
                    c.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(fc[0], fc[1], fc[2], 1.0))
                rep["fog"] = {"density": float(os.environ["ACW_NF_FOG_DENSITY"]), "falloff": float(os.environ.get("ACW_NF_FOG_FALLOFF", "0.035"))}
    if os.environ.get("ACW_NF_ATM_MIE"):
        for a in ues.get_all_level_actors():
            if a.get_class().get_name() == "SkyAtmosphere":
                c = a.get_component_by_class(unreal.SkyAtmosphereComponent)
                atm = {"mie_scattering_scale": float(os.environ["ACW_NF_ATM_MIE"]),
                       "mie_anisotropy": float(os.environ.get("ACW_NF_ATM_MIE_ANISO", "0.8")),
                       "aerial_pespective_view_distance_scale": float(os.environ.get("ACW_NF_ATM_AP_SCALE", "1.0"))}
                for k, v in atm.items():
                    c.set_editor_property(k, v)
                a.modify()
                rep["atmosphere"] = atm
    if not les.save_current_level():
        raise RuntimeError("save level")
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    rep["landscape_actors"] = n


try:
    m = build()
    apply(m)
    rep["status"] = "PASS_NF_LANDSCAPE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_landscape_dl_%s.report.json" % REV, rep)
unreal.SystemLibrary.quit_editor()
