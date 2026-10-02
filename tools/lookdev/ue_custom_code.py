"""Unreal Custom-node code for XinyiLook materials (pure Python, no unreal import).

Shared by adapters/unreal/lookdev/xinyi_look_build_assets.py (which pastes the
result into MaterialExpressionCustom.code) and tools/lookdev/check_hlsl.py
(which compiles the same text with DXC inside a UE-shaped wrapper function).
"""
from __future__ import annotations

from pathlib import Path

SHADER = Path(__file__).resolve().parent / "shaders" / "xinyi_city.hlsl"

SURFACE_OUTPUTS = [("Rough", 1), ("Metal", 1), ("Spec", 1), ("Emis", 3), ("NrmWS", 3)]

# name -> (inputs [(name, components)], call, defines)
MATERIALS = {
    "M_XinyiCity": (
        [("WP", 3), ("N", 3), ("UV0", 2), ("UV1", 2), ("UV2", 2), ("Night", 1), ("LitFrac", 1)],
        "xl.xc_city(WP, N, UV0, UV1, xl.xc_unpack(UV2), Night, LitFrac, b, r, m, s, e, n);",
        "#define XC_NO_HERO 1\n",
    ),
    "M_Taipei101": (
        [("WP", 3), ("N", 3), ("UV0", 2), ("UV1", 2), ("UV2", 2), ("Night", 1), ("LitFrac", 1)],
        "xl.xc_city(WP, N, UV0, UV1, xl.xc_unpack(UV2), Night, LitFrac, b, r, m, s, e, n);",
        "",
    ),
    "M_XinyiGround": (
        [("WP", 3), ("N", 3), ("GT", 4), ("LAMP", 1), ("Night", 1)],
        "xl.xc_ground(WP, N, GT, LAMP, Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
        "",
    ),
    "M_XinyiRoadPaint": (
        [("WP", 3), ("UV2", 2), ("GT", 4), ("LAMP", 1), ("Night", 1)],
        "xl.xc_paint(WP, xl.xc_unpack(UV2), GT, LAMP, Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
        "",
    ),
    "M_XinyiBackdrop": (
        [("WP", 3), ("N", 3), ("UV2", 2), ("FC", 4), ("Night", 1)],
        "xl.xc_backdrop(WP, N, float4(UV2.x, UV2.y, 0.5, 1.0), FC, Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
        "",
    ),
    "M_XinyiFoliage": (
        [("WP", 3), ("N", 3), ("UV2", 2), ("Variant", 1), ("Night", 1)],
        "float4 vc = float4(UV2.x, UV2.y, Variant, 1.0);\n"
        "xl.xc_foliage(WP, N, vc, vc.x * 10.0, Night, b, r, m, s, e);",
        "",
    ),
    "M_XinyiProps": (
        [("WP", 3), ("N", 3), ("UV2", 2), ("Variant", 1), ("Night", 1)],
        "xl.xc_prop(WP, N, xl.xc_unpack(UV2), Variant, Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
        "",
    ),
}


def custom_code(material: str, extra_defines: str = "") -> str:
    """Body pasted into the Custom node: shared HLSL wrapped in a struct."""
    _, call, defines = MATERIALS[material]
    defines = extra_defines + defines
    src = SHADER.read_text(encoding="utf-8")
    return (
        defines
        + "struct XinyiLookFns {\n" + src + "\n};\n"
        + "XinyiLookFns xl;\n"
        + "float3 b; float r; float m; float s; float3 e; float3 n = float3(0.0, 0.0, 1.0);\n"
        + call + "\n"
        + "Rough = r; Metal = m; Spec = s; Emis = e; NrmWS = n;\nreturn b;\n"
    )


CLOUD_SHADER = Path(__file__).resolve().parent / "shaders" / "xinyi_clouds.hlsl"
CLOUD_INPUTS = [("WP", 3), ("WX", 4), ("COV", 1), ("GAIN", 1), ("FINE", 1)]
PLANET_RADIUS_M = 6360000.0   # SkyAtmosphere / VolumetricCloud default; planet top at the world origin


def cloud_custom_code(low: bool, broken_base_norm: float, layer_bottom_m: float, layer_height_m: float) -> str:
    """Cloud Prototype v0 density Custom node (UE volumetric renderer).

    The normalised layer altitude is computed here from the sample position (altitude above the
    planet sphere whose top sits at the world origin), matching the VolumetricCloud layer set from
    the same report. Returns density; additional outputs Env (conservative density) and AO.
    """
    defines = "#define XCL_BROKEN_BASE (%.5f)\n" % broken_base_norm
    if low:
        defines += "#define XCL_LOW 1\n"
    return (
        defines
        + "struct XinyiCloudFns {\n" + CLOUD_SHADER.read_text(encoding="utf-8") + "\n};\n"
        + "XinyiCloudFns xcl;\n"
        + "float alt = length(WP + float3(0.0, 0.0, %.1f)) - %.1f;\n" % (PLANET_RADIUS_M, PLANET_RADIUS_M)
        + "float hn = saturate((alt - %.1f) / %.1f);\n" % (layer_bottom_m, layer_height_m)
        + "float d; float e; float o;\n"
        + "xcl.xcl_cloud(WP, WX, hn, COV, GAIN, FINE, d, e, o);\n"
        + "Env = e; AO = o;\nreturn d;\n"
    )


def cloud_weather_uv_code(tile_m: float) -> str:
    """Custom node: domain-warped weather-map UV (xcl_weather_uv) from the sample position (m)."""
    return (
        "#define XCL_BROKEN_BASE (0.0)\n"
        + "struct XinyiCloudFns {\n" + CLOUD_SHADER.read_text(encoding="utf-8") + "\n};\n"
        + "XinyiCloudFns xcl;\n"
        + "return xcl.xcl_weather_uv(WP, %.1f);\n" % tile_m
    )


CHEAP_CLOUD_SHADER = Path(__file__).resolve().parent / "shaders" / "xinyi_clouds_cheap.hlsl"
# Cheap Cloud Renderer v0 (experimental) Custom-node inputs; NT is a Texture Object (NT + NTSampler)
CHEAP_CLOUD_INPUTS = (["WP", "CAM", "OBJ"] + ["L%d" % i for i in range(8)]
                      + ["PRM", "SUND", "SUNE", "SKYU", "SKYD", "SD", "PD", "NT", "K1", "K2", "GLOW"])


def cheap_cloud_custom_code() -> str:
    """Cheap Cloud Renderer v0: analytic lobe impostor. Returns emissive colour; output Alpha = opacity."""
    return (
        "struct XinyiCheapCloudFns {\n" + CHEAP_CLOUD_SHADER.read_text(encoding="utf-8") + "\n};\n"
        + "XinyiCheapCloudFns xcc;\n"
        + "float3 c; float a;\n"
        + "xcc.xcc_cloud(WP, CAM, OBJ, L0, L1, L2, L3, L4, L5, L6, L7, PRM, SUND, SUNE, SKYU, SKYD, SD, PD,"
        + " NT, NTSampler, K1, K2, GLOW, c, a);\n"
        + "Alpha = a;\nreturn c;\n"
    )


def source_bbox_defines(bbox_enu) -> str:
    """Xinyi building-source bbox (E0, E1, N0, N1 in ENU m) for the ground material.

    The accepted Landscape (2.5 km) is larger than the WFS building source bbox, and the far city
    skips the source bbox, so the band between them has buildings from neither layer.
    """
    e0, e1, n0, n1 = bbox_enu
    return ("#define XC_SRC_E0 (%.1f)\n#define XC_SRC_E1 (%.1f)\n"
            "#define XC_SRC_N0 (%.1f)\n#define XC_SRC_N1 (%.1f)\n" % (e0, e1, n0, n1))


def extent_uv_code(e0: float, e1: float, n0: float, n1: float) -> str:
    """World (UE cm/100) -> 0..1 UV over an ENU extent; UE Y = -north."""
    return "return float2((WP.x - (%.1f)) / %.1f, (WP.y + (%.1f)) / %.1f);" % (e0, e1 - e0, n1, n1 - n0)


def ground_uv_code(e0: float, e1: float, n0: float, n1: float) -> str:
    # UE Y = -north
    return "return float2((WP.x - (%.1f)) / %.1f, (WP.y + %.1f) / %.1f);" % (e0, e1 - e0, n1, n1 - n0)
