"""Far-LOD research: octahedral tree-impostor layer for the Yangmingshan forest (UnrealEditor-Cmd, WITH RHI).

Parts (ACW_FI_PARTS, comma list, default all):
  tex   import the fi_pack.py atlases (T_FI_BC_V<v> sRGB + coverage, T_FI_ND_V<v> object normal + depth) and build two Texture2DArrays
        (10 slices = the 10 tint variants), so ONE material / ONE component per cell draws every species (Kuro's Wuthering Waves talk: a
        dynamic texture array lets far trees batch into a handful of draws).
  mesh  SM_FI_Card: the engine 1 m plane (4 vertices) with bounds extended to hold the largest scaled impostor.
  mat   M_FI_Impostor (masked, two-sided foliage, 4 float4 vertex interpolators). Vertex stage: frame selection on the hemi-octahedron (3 nearest frames
        + barycentric weights), camera-facing card, per-frame card->frame UV projection, far thinning; pixel stage: 3-frame blend from the
        arrays, object normal -> world, hand-over dither.
  actors one HISM-holder actor per 2 km cell for the region around the A/B views (FI_Imp_<cx>_<cy>, tag FarImpostor, not spatially
        loaded) in /Game/NorthForest/Maps/L_NF_Yangmingshan. Same trees, ranks and transforms as the 3D forest (nf_trees_band.py).

Hand-over (no ring, no pop): the 3D tree with vanish rank r dissolves per pixel over [T(r) - Width, T(r)] with an interleaved-gradient
dither; the impostor of the SAME tree is drawn on exactly the complementary dither pixels, so every tree is swapped individually at the
distance the current graphics preset already removes it (PC curve on SM5, mobile twins on the mobile renderer, as the tree materials).
Far thinning (engineering choice, not from a talk): beyond S the impostor layer keeps a share k(D) = clamp((S / D)^2, Kmin, 1) of the
trees (hash of r, dithered over 3 % of k) and scales the survivors by min(D / S, ScMax): up to S * ScMax their screen size and density
stay constant (instance count grows only with log distance); the whole layer dithers out between END1 and END2, beyond which the
PR #49 terrain skin / macro forest colour carries the mountain form. Each impostor's normal is bent toward the macro terrain normal
under its tree with distance (fi_terrain_normal.py), so slope shading survives. HISMs are split into bands of that hash with end culls where the band is
fully thinned, so thinned trees are not submitted.
Receipt: reports/fi_build.report.json.
"""
import json
import math
import os
import random
import struct
import array
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, MAP, OUT, RUN, VARIANT_FORM, lib, mel, tools, write_report  # noqa: E402
from nf_common import link as _link  # noqa: E402


def link(a, out, b, pin):
    """nf_common.link; single-input nodes (Transform, TransformPosition, ComponentMask) expose their input as the unnamed pin."""
    try:
        _link(a, out, b, pin)
    except RuntimeError:
        if pin != "Input":
            raise
        _link(a, out, b, "")

ROOT = "/Game/FarLOD"
PACK = OUT / "fi_pack" / os.environ.get("ACW_FI_PACK_REV", "3")
PARTS = os.environ.get("ACW_FI_PARTS", "tex,mesh,mat,actors").split(",")
S_CM = float(os.environ.get("ACW_FI_S_CM", "300000"))
KMIN = float(os.environ.get("ACW_FI_KMIN", "0.15"))
SCMAX = float(os.environ.get("ACW_FI_SCMAX", "1.6"))   # survivors grow at most this much; beyond S * SCMAX the layer thins out over the terrain relief
TINT = [float(x) for x in os.environ.get("ACW_FI_TINT", "0.66,0.69,0.86").split(",")]   # 3D-vs-impostor calibration, docs section 3
END1, END2 = (float(x) for x in os.environ.get("ACW_FI_END_CM", "550000,700000").split(","))   # layer dithers out; beyond = PR #49 mountain form
BAND_EDGES = [0.0, KMIN, 0.25, 0.45, 0.70, 1.0]
CELL_TILES = int(os.environ.get("ACW_FI_CELL_TILES", "2"))   # N x N one-km forest tiles per impostor actor
# ism (default): UInstancedStaticMeshComponent, GPU-scene instance culling, one draw per component and pass, no per-cluster occlusion
# queries; hism: hierarchical clusters (measured: ~13 draws + ~8 occlusion queries per component, docs section 3)
COMP = os.environ.get("ACW_FI_COMP", "ism")
# A/B poses (UE cm, yaw deg): -ffgfxtest forest_layers, views_dl dl_mid_ridge / agl400_basin_edge / dl_far_range, end of the flight leg
CAMS = [(420000, -3130000, 49.3), (1130000, -2220000, -94.17), (550000, -1540000, -70.35), (1820000, -3260000, 141.84),
        (420000 + 450000 * math.cos(math.radians(49.3)), -3130000 + 450000 * math.sin(math.radians(49.3)), 49.3)]
CAMS = [CAMS[int(i)] for i in os.environ.get("ACW_FI_CAMS", "0,1,2,3,4").split(",")]
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
rep = {"status": "FAIL_FI_BUILD", "parts": PARTS, "error": None, "warnings": []}

VS_HLSL = r"""
const float N = 16.0;
float4 FD[4] = { %(FD)s };
float2 FE[4] = { %(FE)s };   // horizontal crown radius, vertical half extent (mesh bounds box)
float slice = floor(CD + 1e-4);
float r = saturate(CD - slice);
int f = slice < 2.5 ? 0 : (slice < 4.5 ? 1 : (slice < 7.5 ? 2 : 3));
float3 C = FD[f].xyz;
float R = FD[f].w;
float rr = saturate(r);
#if SHADING_PATH_MOBILE
Near = NearM; End = EndM; Width = WidthM; Gamma = GammaM; rr = saturate(r / max(KeepM, 0.01));
#endif
float T = Near + (End - Near) * pow(rr, Gamma);
float h = frac(r * 157.31 + 0.137);
float k = clamp(S * S / max(Dist * Dist, 1.0), Kmin, 1.0);
float fade = saturate((k - h) / 0.03) * saturate((End2 - Dist) / (End2 - End1));
float sc = clamp(Dist / S, 1.0, ScMax);
float3 vn = Vl / max(length(Vl), 1e-3);
float3 hv = vn;
hv.z = max(hv.z, 0.0);
hv /= (abs(hv.x) + abs(hv.y) + hv.z);
float2 g = (float2(hv.x + hv.y, hv.x - hv.y) * 0.5 + 0.5) * (N - 1.0);
float2 b = clamp(floor(g), 0.0, N - 2.0);
float2 fr = g - b;
float2 fs[3];
float3 w;
if (fr.x + fr.y <= 1.0) { fs[0] = b; fs[1] = b + float2(1, 0); fs[2] = b + float2(0, 1); w = float3(1.0 - fr.x - fr.y, fr.x, fr.y); }
else { fs[0] = b + float2(1, 1); fs[1] = b + float2(0, 1); fs[2] = b + float2(1, 0); w = float3(fr.x + fr.y - 1.0, 1.0 - fr.x, 1.0 - fr.y); }
float3 hint = abs(vn.z) < 0.999 ? float3(0, 0, 1) : float3(1, 0, 0);
float3 cr = normalize(cross(hint, vn));
float3 cu = cross(vn, cr);
// card fitted to the silhouette at this view elevation (not the bounding sphere): thin conifers cost ~45 %% less masked area
float2 hs = float2(min(FE[f].x, R), min(R, FE[f].y * sqrt(saturate(1.0 - vn.z * vn.z)) + FE[f].x * abs(vn.z)));
float2 q2 = (UV - 0.5) * float2(2.0, -2.0) * hs;
float3 q = cr * q2.x + cu * q2.y;
float2 uvs[3];
for (int i = 0; i < 3; i++)
{
    float2 ee = fs[i] / (N - 1.0) * 2.0 - 1.0;
    float2 t = float2(ee.x + ee.y, ee.x - ee.y) * 0.5;
    float3 d = normalize(float3(t.x, t.y, 1.0 - abs(t.x) - abs(t.y)));
    float3 h2 = abs(d.z) < 0.999 ? float3(0, 0, 1) : float3(1, 0, 0);
    float3 ra = normalize(cross(h2, d));
    float3 ua = cross(d, ra);
    uvs[i] = float2(0.5 + %(SR)s * dot(q, ra) / (2.0 * R), 0.5 - %(SU)s * dot(q, ua) / (2.0 * R));
}
UVA = uvs[0]; UVB = uvs[1]; UVC = uvs[2];
IAB = float2(fs[0].x + fs[0].y * N, fs[1].x + fs[1].y * N);
ICS = float2(fs[2].x + fs[2].y * N, slice);
WAB = w.xy;
TF = float2(T, fade);
bool hidden = (Dist < T - Width - 3000.0) || (fade <= 0.0);
return hidden ? float3(0, 0, 0) : (C + q) * sc;
"""

PS_HLSL = r"""
const float N = 16.0;
float2 UVA = P0.xy, UVB = P0.zw, UVC = P1.xy, IAB = P1.zw, ICS = P2.xy, WAB = P2.zw, YAW = P3.xy, TF = P3.zw;
float2 uv[3] = { UVA, UVB, UVC };
float idx[3] = { IAB.x, IAB.y, ICS.x };
float w[3] = { WAB.x, WAB.y, 1.0 - WAB.x - WAB.y };
float3 col = 0; float3 nrm = 0; float a = 0; float dz = 0;
for (int i = 0; i < 3; i++)
{
    float2 l = uv[i];
    float inside = (l.x >= 0.0 && l.x <= 1.0 && l.y >= 0.0 && l.y <= 1.0) ? 1.0 : 0.0;
    l = clamp(l, 0.5 / FPX, 1.0 - 0.5 / FPX);
    float cy = floor((idx[i] + 0.5) / N);
    float2 at = (float2(idx[i] - cy * N, cy) + l) / N;
    float4 s = Texture2DArraySample(BC, BCSampler, float3(at, ICS.y));
    float4 t = Texture2DArraySample(ND, NDSampler, float3(at, ICS.y));
    float ww = w[i] * inside * s.a;
    col += s.rgb * ww; nrm += (t.rgb * 2.0 - 1.0) * ww; dz += (t.a * 2.0 - 1.0) * ww; a += w[i] * inside * s.a;
}
float inv = 1.0 / max(a, 1e-4);
col *= inv; dz *= inv;
nrm = normalize(nrm * inv + float3(0, 0, 1e-4));
float2 yx = normalize(YAW + float2(1e-5, 0));
Nrm = float3(yx.x * nrm.x - yx.y * nrm.y, yx.y * nrm.x + yx.x * nrm.y, nrm.z);
// far = mountain form: bend toward the tree's macro terrain normal (fi_terrain_normal.py) with distance
float3 nt = float3(P4.xy, sqrt(saturate(1.0 - dot(P4.xy, P4.xy))));
Nrm = normalize(lerp(Nrm, nt, saturate((D - TerrStart) / max(TerrEnd - TerrStart, 1.0)) * TerrMax));
#if SHADING_PATH_MOBILE
Width = WidthM;
#endif
float k3 = saturate((TF.x - D) / Width);
float n = frac(52.9829189 * frac(dot(Pix + 5.588238 * (float)View.StateFrameIndexMod8, float2(0.06711056, 0.00583715))));
Mask = (a > 0.5 && k3 <= n && n < TF.y) ? 1.0 : 0.0;
return col * ColorGain * lerp(1.0, saturate(0.5 + 0.5 * dz) * 1.4, Occ);
"""


def setp(obj, props, tag):
    for k, v in props.items():
        try:
            obj.set_editor_property(k, v)
        except Exception as exc:  # noqa: BLE001
            rep["warnings"].append("%s %s: %s" % (tag, k, exc))


def part_tex():
    out = {}
    for d in (ROOT + "/Textures",):
        if not lib.does_directory_exist(d):
            lib.make_directory(d)
    for kind, srgb in (("BC", True), ("ND", False)):
        texs = []
        for v in range(10):
            src = PACK / ("T_FI_%s_V%d.png" % (kind, v))
            t = unreal.AssetImportTask()
            setp(t, {"filename": str(src), "destination_path": ROOT + "/Textures", "automated": True, "replace_existing": True, "save": False}, "import")
            tools.import_asset_tasks([t])
            tex = lib.load_asset(ROOT + "/Textures/T_FI_%s_V%d" % (kind, v))
            if tex is None:
                raise RuntimeError("import " + str(src))
            setp(tex, {"srgb": srgb, "compression_settings": unreal.TextureCompressionSettings.TC_DEFAULT,
                       "mip_gen_settings": unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP, "lod_group": unreal.TextureGroup.TEXTUREGROUP_WORLD}, "tex")
            if kind == "BC":   # keep the alpha-tested coverage of far mips (UE "scale mips for alpha coverage")
                setp(tex, {"do_scale_mips_for_alpha_coverage": True, "alpha_coverage_thresholds": unreal.Vector4(0, 0, 0, 0.5)}, "tex")
            lib.save_asset(tex.get_path_name(), only_if_is_dirty=False)
            texs.append(tex)
        name = "T_FI_%s_Array" % kind
        path = ROOT + "/Textures/" + name
        arr = lib.load_asset(path)
        if arr is None:
            fac = unreal.Texture2DArrayFactory()
            setp(fac, {"initial_textures": texs}, "factory")
            arr = tools.create_asset(name, ROOT + "/Textures", unreal.Texture2DArray, fac)
        setp(arr, {"srgb": srgb, "compression_settings": unreal.TextureCompressionSettings.TC_DEFAULT}, "array")
        if kind == "BC":
            setp(arr, {"do_scale_mips_for_alpha_coverage": True, "alpha_coverage_thresholds": unreal.Vector4(0, 0, 0, 0.5)}, "array")
        setp(arr, {"source_textures": texs}, "array")
        lib.save_asset(path, only_if_is_dirty=False)
        n = len(arr.get_editor_property("source_textures"))
        out[name] = {"slices": n, "srgb": arr.get_editor_property("srgb")}
        if n != 10:
            raise RuntimeError("%s has %d slices" % (name, n))
    rep["tex"] = out


def part_mesh():
    if not lib.does_directory_exist(ROOT + "/Meshes"):
        lib.make_directory(ROOT + "/Meshes")
    path = ROOT + "/Meshes/SM_FI_Card"
    if not lib.does_asset_exist(path):
        lib.duplicate_asset("/Engine/BasicShapes/Plane", path)
    m = lib.load_asset(path)
    sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    # largest impostor: cryptomeria R 13 m, centre 12.7 m up, x 2.5 far scale, instance scale <= 1.3
    setp(m, {"positive_bounds_extension": unreal.Vector(5500, 5500, 9500), "negative_bounds_extension": unreal.Vector(5500, 5500, 500)}, "mesh")
    lib.save_asset(path, only_if_is_dirty=False)
    rep["mesh"] = {"path": path, "verts": sms.get_number_verts(m, 0), "lods": m.get_num_lods()}
    if rep["mesh"]["verts"] != 4:
        raise RuntimeError("card mesh has %d vertices" % rep["mesh"]["verts"])


def custom(mat, x, y, code, inputs, otype, outs=()):
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    node = E(mat, unreal.MaterialExpressionCustom, x, y, code=code, inputs=ins, output_type=otype, description="FI")
    if outs:
        ao = []
        for n, t in outs:
            o = unreal.CustomOutput()
            o.set_editor_property("output_name", n)
            o.set_editor_property("output_type", t)
            ao.append(o)
        node.set_editor_property("additional_outputs", ao)
    return node


def part_mat():
    meta = json.loads((PACK / "fi_pack.json").read_text(encoding="utf-8"))
    sr, su = meta["cam_sign_right_up"]
    fd = []
    for f in ("A", "B", "C", "J"):
        c, R = meta["forms"][f]["center"], meta["forms"][f]["R"]
        fd.append("float4(%.3f, %.3f, %.3f, %.3f)" % (c[0], c[1], c[2], R))
    fe = []
    for f in ("A", "B", "C", "J"):
        ex = meta["forms"][f]["extent"]
        fe.append("float2(%.1f, %.1f)" % (max(ex[0], ex[1]) * 1.05, ex[2] * 1.03))
    vs_code = VS_HLSL % {"FD": ", ".join(fd), "FE": ", ".join(fe), "SR": "%.1f" % sr, "SU": "%.1f" % su}
    if not lib.does_directory_exist(ROOT + "/Materials"):
        lib.make_directory(ROOT + "/Materials")
    path = ROOT + "/Materials/M_FI_Impostor"
    if lib.does_asset_exist(path):   # rebuilt in place: the impostor HISMs in the map reference it
        mat = lib.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset("M_FI_Impostor", ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    setp(mat, {"blend_mode": unreal.BlendMode.BLEND_MASKED, "shading_model": unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE,
               "two_sided": True, "tangent_space_normal": False, "opacity_mask_clip_value": 0.5}, "mat")
    coll = lib.load_asset("/Game/NorthForest/Materials/MPC_NF_Forest")
    F2, F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT2, unreal.CustomMaterialOutputType.CMOT_FLOAT3
    F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
    # ---- vertex stage
    zero = E(mat, unreal.MaterialExpressionConstant3Vector, -2400, -600, constant=unreal.LinearColor(0, 0, 0, 0))
    pivot = E(mat, unreal.MaterialExpressionTransformPosition, -2200, -600,
              transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL,
              transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD)
    link(zero, "", pivot, "Input")
    cam = E(mat, unreal.MaterialExpressionCameraPositionWS, -2200, -450)
    vw = E(mat, unreal.MaterialExpressionSubtract, -2000, -520)
    link(cam, "", vw, "A")
    link(pivot, "", vw, "B")
    vl = E(mat, unreal.MaterialExpressionTransform, -1800, -520, transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD,
           transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    link(vw, "", vl, "Input")
    dist = E(mat, unreal.MaterialExpressionDistance, -1800, -400)
    link(cam, "", dist, "A")
    link(pivot, "", dist, "B")
    cd = E(mat, unreal.MaterialExpressionPerInstanceCustomData, -1800, -300, data_index=0)
    uv0 = E(mat, unreal.MaterialExpressionTextureCoordinate, -1800, -220, coordinate_index=0)
    vs_ins = ["Vl", "UV", "CD", "Dist", "Near", "End", "Width", "Gamma", "NearM", "EndM", "WidthM", "GammaM", "KeepM", "S", "Kmin", "ScMax", "End1", "End2"]
    vs = custom(mat, -1300, -500, vs_code, vs_ins, F3,
                [("UVA", F2), ("UVB", F2), ("UVC", F2), ("IAB", F2), ("ICS", F2), ("WAB", F2), ("TF", F2)])
    link(vl, "", vs, "Vl")
    link(uv0, "", vs, "UV")
    link(cd, "", vs, "CD")
    link(dist, "", vs, "Dist")
    y = -100
    for pin, name in (("Near", "NearFull"), ("End", "ThinEnd"), ("Width", "FadeWidth"), ("Gamma", "ThinGamma"), ("NearM", "NearFullM"),
                      ("EndM", "ThinEndM"), ("WidthM", "FadeWidthM"), ("GammaM", "ThinGammaM"), ("KeepM", "RankKeepM")):
        link(E(mat, unreal.MaterialExpressionCollectionParameter, -1800, y, collection=coll, parameter_name=name), "", vs, pin)
        y += 60
    for pin, val in (("S", S_CM), ("Kmin", KMIN), ("ScMax", SCMAX), ("End1", END1), ("End2", END2)):
        link(E(mat, unreal.MaterialExpressionScalarParameter, -1800, y, parameter_name="FI_" + pin, default_value=val), "", vs, pin)
        y += 60
    l2w = E(mat, unreal.MaterialExpressionTransform, -900, -500, transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
            transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(vs, "", l2w, "Input")
    wpos = E(mat, unreal.MaterialExpressionWorldPosition, -1100, -700)
    try:
        wpos.set_editor_property("world_position_shader_offset", unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    except Exception as exc:  # noqa: BLE001
        rep["warnings"].append("worldpos: %s" % exc)
    back = E(mat, unreal.MaterialExpressionSubtract, -900, -700)
    link(pivot, "", back, "A")
    link(wpos, "", back, "B")
    wpo = E(mat, unreal.MaterialExpressionAdd, -700, -600)
    link(l2w, "", wpo, "A")
    link(back, "", wpo, "B")
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    xaxis = E(mat, unreal.MaterialExpressionConstant3Vector, -1100, -850, constant=unreal.LinearColor(1, 0, 0, 0))
    yaw = E(mat, unreal.MaterialExpressionTransform, -900, -850, transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
            transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(xaxis, "", yaw, "Input")
    yaw2 = E(mat, unreal.MaterialExpressionComponentMask, -700, -850, r=True, g=True, b=False, a=False)
    link(yaw, "", yaw2, "Input")
    # VS -> PS: four float4 Vertex Interpolators (UVA|UVB, UVC|IAB, ICS|WAB, YAW|TF)
    ps_ins = ["P0", "P1", "P2", "P3", "P4", "TerrStart", "TerrEnd", "TerrMax", "D", "Pix", "BC", "ND", "Width", "WidthM", "FPX", "ColorGain", "Occ"]
    ps = custom(mat, -300, 200, PS_HLSL, ps_ins, F3, [("Nrm", F3), ("Mask", F1)])
    for i, ((na, a), (nb, b)) in enumerate(((("UVA", vs), ("UVB", vs)), (("UVC", vs), ("IAB", vs)), (("ICS", vs), ("WAB", vs)), (("", yaw2), ("TF", vs)))):
        ap = E(mat, unreal.MaterialExpressionAppendVector, -500, -300 + 120 * i)
        link(a, na, ap, "A")
        link(b, nb, ap, "B")
        vi = E(mat, unreal.MaterialExpressionVertexInterpolator, -400, -300 + 120 * i)
        link(ap, "", vi, "VS")
        link(vi, "PS", ps, "P%d" % i)
    tn = E(mat, unreal.MaterialExpressionAppendVector, -600, 300)
    link(E(mat, unreal.MaterialExpressionPerInstanceCustomData, -800, 280, data_index=1), "", tn, "A")
    link(E(mat, unreal.MaterialExpressionPerInstanceCustomData, -800, 340, data_index=2), "", tn, "B")
    vi4 = E(mat, unreal.MaterialExpressionVertexInterpolator, -450, 300)
    link(tn, "", vi4, "VS")
    link(vi4, "PS", ps, "P4")
    for i, (pin, val) in enumerate((("TerrStart", 200000.0), ("TerrEnd", 600000.0), ("TerrMax", 0.6))):
        link(E(mat, unreal.MaterialExpressionScalarParameter, -700, 1100 + 60 * i, parameter_name="FI_" + pin, default_value=val), "", ps, pin)
    pd = E(mat, unreal.MaterialExpressionDistance, -700, 520)
    link(E(mat, unreal.MaterialExpressionWorldPosition, -900, 500), "", pd, "A")
    link(E(mat, unreal.MaterialExpressionCameraPositionWS, -900, 560), "", pd, "B")
    link(pd, "", ps, "D")
    link(E(mat, unreal.MaterialExpressionScreenPosition, -700, 600), "PixelPosition", ps, "Pix")
    for pin, tex, st in (("BC", "T_FI_BC_Array", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR), ("ND", "T_FI_ND_Array", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)):
        to = E(mat, unreal.MaterialExpressionTextureObject, -700, 680 if pin == "BC" else 740, texture=lib.load_asset(ROOT + "/Textures/" + tex))
        setp(to, {"sampler_type": st}, "texobj")
        link(to, "", ps, pin)
    link(E(mat, unreal.MaterialExpressionCollectionParameter, -700, 800, collection=coll, parameter_name="FadeWidth"), "", ps, "Width")
    link(E(mat, unreal.MaterialExpressionCollectionParameter, -700, 860, collection=coll, parameter_name="FadeWidthM"), "", ps, "WidthM")
    link(E(mat, unreal.MaterialExpressionConstant, -700, 920, r=float(meta["out_px"])), "", ps, "FPX")
    tint = E(mat, unreal.MaterialExpressionVectorParameter, -900, 980, parameter_name="FI_Tint", default_value=unreal.LinearColor(TINT[0], TINT[1], TINT[2], 1))
    tm = E(mat, unreal.MaterialExpressionComponentMask, -700, 980, r=True, g=True, b=True, a=False)
    link(tint, "", tm, "Input")
    link(tm, "", ps, "ColorGain")
    link(E(mat, unreal.MaterialExpressionScalarParameter, -700, 1040, parameter_name="FI_Occlusion", default_value=0.0), "", ps, "Occ")
    mel.connect_material_property(ps, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(ps, "Nrm", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(ps, "Mask", unreal.MaterialProperty.MP_OPACITY_MASK)
    sss = E(mat, unreal.MaterialExpressionMultiply, 0, 400)
    link(ps, "", sss, "A")
    link(E(mat, unreal.MaterialExpressionScalarParameter, -200, 460, parameter_name="FI_SubsurfaceGain", default_value=float(os.environ.get("ACW_FI_SSS", "0.25"))), "", sss, "B")
    mel.connect_material_property(sss, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionScalarParameter, 0, 520, parameter_name="FI_Specular", default_value=0.10), "",
                                  unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionScalarParameter, 0, 580, parameter_name="FI_Roughness", default_value=0.85), "",
                                  unreal.MaterialProperty.MP_ROUGHNESS)
    mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    mel.recompile_material(mat)
    lib.save_asset(path, only_if_is_dirty=False)
    m2 = lib.load_asset(path)
    rep["mat"] = {"path": path, "ism": bool(m2.get_editor_property("used_with_instanced_static_meshes")),
                  "vs_hlsl": vs_code, "s_cm": S_CM, "kmin": KMIN, "scmax": SCMAX, "tint": TINT}
    stats = mel.get_statistics(m2)
    rep["mat"]["stats"] = {k: str(stats.get_editor_property(k)) for k in ("num_vertex_shader_instructions", "num_pixel_shader_instructions",
                                                                          "num_samplers", "num_vertex_texture_samples", "num_pixel_texture_samples")}
    if not rep["mat"]["ism"]:
        raise RuntimeError("ISM usage did not stick")


def read_tile(path):
    buf = open(path, "rb").read()
    (ng,), off, groups = struct.unpack_from("<I", buf, 0), 4, []
    for _ in range(ng):
        form, var, n = struct.unpack_from("<cHI", buf, off)
        off += 7
        rec = array.array("d")
        rec.frombytes(buf[off:off + n * 9 * 8])
        off += n * 9 * 8
        groups.append((form.decode(), var, n, rec))
    return groups


def in_region(cx, cy):
    for x, y, yaw in CAMS:
        dx, dy = cx - x, cy - y
        d = math.hypot(dx, dy)
        if d > END2 + 50000:
            continue
        a = (math.degrees(math.atan2(dy, dx)) - yaw + 180) % 360 - 180
        if d <= 150000 or abs(a) <= 70:
            return True
    return False


def add_hism(actor, mesh):
    cls = unreal.InstancedStaticMeshComponent if COMP == "ism" else unreal.HierarchicalInstancedStaticMeshComponent
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    params = unreal.AddNewSubobjectParams()
    params.set_editor_property("parent_handle", sds.k2_gather_subobject_data_for_instance(actor)[0])
    params.set_editor_property("new_class", cls)
    h, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("add_new_subobject failed")
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(unreal.SubobjectDataBlueprintFunctionLibrary.get_data(h))
    comp.set_static_mesh(mesh)
    return comp


def part_actors():
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    for a in ues.get_all_level_actors():   # rebuild: drop a previous impostor layer
        if a.get_actor_label().startswith("FI_Imp_"):
            ues.destroy_actor(a)
    mesh = lib.load_asset(ROOT + "/Meshes/SM_FI_Card")
    mat = lib.load_asset(ROOT + "/Materials/M_FI_Impostor")
    idx = json.loads((RUN / "trees.json").read_text(encoding="utf-8"))
    cells = {}
    for t in idx["tiles"]:
        if in_region(*t["center_ue_cm"]):
            cells.setdefault((t["tx"] // CELL_TILES, t["ty"] // CELL_TILES), []).append(t)
    tmeta = json.loads((PACK / "fi_terrain_normal.json").read_text(encoding="utf-8"))
    tnorm = array.array("b")
    tnorm.frombytes((PACK / "fi_terrain_normal.bin").read_bytes())
    trows, tcols = tmeta["size"]
    tsp, (tx0, ty0) = tmeta["spacing_cm"], tmeta["origin_cm"]

    def terrain_n(x, y):
        c = min(max(int(round((x - tx0) / tsp)), 0), tcols - 1)
        r = min(max(int(round((y - ty0) / tsp)), 0), trows - 1)
        k = 2 * (r * tcols + c)
        return tnorm[k] / 127.0, tnorm[k + 1] / 127.0

    culls = [int(END2 + 10000) if lo <= 0 else int(min(S_CM / math.sqrt(lo) + 20000, END2 + 10000)) for lo in BAND_EDGES[:-1]]
    rep["band_edges"], rep["band_culls_cm"] = BAND_EDGES, culls
    total, comps, per_band = 0, 0, [0] * (len(BAND_EDGES) - 1)
    for (cx, cy), tiles in sorted(cells.items()):
        x0 = sum(t["center_ue_cm"][0] for t in tiles) / len(tiles)
        y0 = sum(t["center_ue_cm"][1] for t in tiles) / len(tiles)
        holder = ues.spawn_actor_from_class(unreal.Actor, unreal.Vector(x0, y0, 0.0))
        holder.set_actor_label("FI_Imp_%02d_%02d" % (cx, cy))
        holder.set_folder_path(unreal.Name("FI_FarImpostors"))
        holder.set_editor_property("tags", [unreal.Name("FarImpostor")])
        holder.set_editor_property("is_spatially_loaded", False)
        bands = [([], []) for _ in culls]
        for t in tiles:
            for gi, (form, var, n, rec) in enumerate(read_tile(RUN / "trees" / t["file"])):
                rng = random.Random("%s/%d/%s%d" % (t["file"], gi, form, var))   # == nf_trees_band.py ranks
                ranks = [rng.random() for _ in range(n)]
                for i in range(n):
                    r = ranks[i]
                    hh = (r * 157.31 + 0.137) % 1.0
                    b = next(k for k in range(len(culls)) if hh < BAND_EDGES[k + 1] or k == len(culls) - 1)
                    x, y, z, yw, sx, sy, sz, le, ln = rec[i * 9:(i + 1) * 9]
                    z_up = unreal.Vector(math.tan(math.radians(le)), -math.tan(math.radians(ln)), 1.0)
                    yr = math.radians(yw)
                    rot = unreal.MathLibrary.make_rot_from_zx(z_up, unreal.Vector(math.cos(yr), math.sin(yr), 0.0))
                    bands[b][0].append(unreal.Transform(unreal.Vector(x, y, z), rot, unreal.Vector(sx, sy, sz)))
                    bands[b][1].append((var + min(r, 0.9999),) + terrain_n(x, y))
        for b, (xf, data) in enumerate(bands):
            if not xf:
                continue
            h = add_hism(holder, mesh)
            h.set_material(0, mat)
            h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            h.set_cast_shadow(False)
            h.set_cull_distances(0, culls[b])
            # camera-facing WPO must not force every impostor into the velocity pass (same per-component switch as the tree HISMs,
            # nf_gate_prep.py); measured +2.6..8.6 ms on the UHD 770 without it
            setp(h, {"visible_in_ray_tracing": False, "affect_distance_field_lighting": False, "world_position_offset_writes_velocity": False}, "hism")
            h.set_num_custom_data_floats(3)   # slice + vanish rank, terrain normal x, y
            h.add_instances(xf, False, True)
            for k, v in enumerate(data):
                for j in range(3):
                    h.set_custom_data_value(k, j, v[j], False)
            if h.get_instance_count() != len(xf):
                raise RuntimeError("instance count")
            total += len(xf)
            per_band[b] += len(xf)
            comps += 1
        unreal.log("FI_BUILD cell %d,%d tiles=%d total=%d" % (cx, cy, len(tiles), total))
    rep["actors"] = {"component_class": COMP, "cell_tiles": CELL_TILES, "cells": len(cells), "components": comps, "instances": total, "per_band": per_band,
                     "tiles": sum(len(v) for v in cells.values())}
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save")


try:
    for p in PARTS:
        {"tex": part_tex, "mesh": part_mesh, "mat": part_mat, "actors": part_actors}[p]()
    rep["status"] = "PASS_FI_BUILD"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("fi_build.report.json", rep)
unreal.SystemLibrary.quit_editor()
