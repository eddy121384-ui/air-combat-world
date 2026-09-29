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
        [("WP", 3), ("N", 3), ("GT", 4), ("Night", 1)],
        "xl.xc_ground(WP, N, GT, Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
        "",
    ),
    "M_XinyiRoadPaint": (
        [("WP", 3), ("UV2", 2), ("GT", 4), ("Night", 1)],
        "xl.xc_paint(WP, xl.xc_unpack(UV2), GT, Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
        "",
    ),
    "M_XinyiBackdrop": (
        [("WP", 3), ("N", 3), ("UV2", 2), ("Night", 1)],
        "xl.xc_backdrop(WP, N, float4(UV2.x, UV2.y, 0.5, 1.0), Night, max(fwidth(WP.x), fwidth(WP.y)), b, r, m, s, e);",
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


def custom_code(material: str) -> str:
    """Body pasted into the Custom node: shared HLSL wrapped in a struct."""
    _, call, defines = MATERIALS[material]
    src = SHADER.read_text(encoding="utf-8")
    return (
        defines
        + "struct XinyiLookFns {\n" + src + "\n};\n"
        + "XinyiLookFns xl;\n"
        + "float3 b; float r; float m; float s; float3 e; float3 n = float3(0.0, 0.0, 1.0);\n"
        + call + "\n"
        + "Rough = r; Metal = m; Spec = s; Emis = e; NrmWS = n;\nreturn b;\n"
    )


def ground_uv_code(e0: float, e1: float, n0: float, n1: float) -> str:
    # UE Y = -north
    return "return float2((WP.x - (%.1f)) / %.1f, (WP.y + %.1f) / %.1f);" % (e0, e1 - e0, n1, n1 - n0)
