"""Compile every XinyiLook Custom-node body with DXC inside a UE-shaped wrapper.

Mirrors how Unreal emits a Custom expression: a function taking
FMaterialPixelParameters + one parameter per input + `inout` per additional
output, called from a pixel shader. Targets ps_6_0 (DXIL, D3D12/SM6) and
SPIR-V (the Vulkan / Metal-via-cross path mobile builds rely on).

Usage: python tools/lookdev/check_hlsl.py --dxc /path/to/dxc
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_custom_code import (  # noqa: E402
    MATERIALS, SURFACE_OUTPUTS, WALLADS_INPUTS, custom_code, wallads_custom_code, wallads_uv_code,
)

HV = "2018"
TYPES = {1: "float", 2: "float2", 3: "float3", 4: "float4"}


def wrapper(material: str) -> str:
    inputs, _, _ = MATERIALS[material]
    params = ["FMaterialPixelParameters Parameters"]
    # texture-object inputs (components 0) arrive as <name> + <name>Sampler, as Unreal emits them
    params += ["Texture2D %s, SamplerState %sSampler" % (n, n) if c == 0 else "%s %s" % (TYPES[c], n)
               for n, c in inputs]
    params += ["inout %s %s" % (TYPES[c], n) for n, c in SURFACE_OUTPUTS]
    args = ["Parameters"]
    for i, (n, c) in enumerate(inputs):
        args.append("G_%s, G_%sSampler" % (n, n) if c == 0 else "In%d.%s" % (i, "xyzw"[:c]) if c > 1 else "In%d.x" % i)
    decl_in = "".join("float4 In%d : TEXCOORD%d, " % (i, i) for i, (n, c) in enumerate(inputs) if c)
    resources = "".join("Texture2D G_%s; SamplerState G_%sSampler;\n" % (n, n) for n, c in inputs if c == 0)
    return (
        "struct FMaterialPixelParameters { float4 SvPosition; };\n" + resources +
        "float3 CustomExpression0(" + ", ".join(params) + ")\n{\n" + custom_code(material) + "}\n"
        "float4 main(" + decl_in + "float4 Pos : SV_Position) : SV_Target\n{\n"
        "  FMaterialPixelParameters Parameters; Parameters.SvPosition = Pos;\n"
        "  float Rough = 0; float Metal = 0; float Spec = 0; float3 Emis = 0; float3 NrmWS = 0;\n"
        "  float3 b = CustomExpression0(" + ", ".join(args + ["Rough", "Metal", "Spec", "Emis", "NrmWS"]) + ");\n"
        "  return float4(b + Emis + NrmWS * 0.001, Rough + Metal + Spec);\n}\n"
    )


def wallads_wrappers() -> dict:
    """M_XinyiWallAds: the UV node (float2 return) and the surface node, same UE-shaped wrapper."""
    params = ["FMaterialPixelParameters Parameters"] + ["%s %s" % (TYPES[c], n) for n, c in WALLADS_INPUTS]
    args = ["Parameters"] + ["In%d.%s" % (i, "xyzw"[:c]) if c > 1 else "In%d.x" % i
                             for i, (n, c) in enumerate(WALLADS_INPUTS)]
    decl_in = "".join("float4 In%d : TEXCOORD%d, " % (i, i) for i in range(len(WALLADS_INPUTS)))
    head = "struct FMaterialPixelParameters { float4 SvPosition; };\n"
    main_open = ("float4 main(" + decl_in + "float4 Pos : SV_Position) : SV_Target\n{\n"
                 "  FMaterialPixelParameters Parameters; Parameters.SvPosition = Pos;\n")
    uv = (head + "float2 CustomExpression0(" + ", ".join(params) + ")\n{\n" + wallads_uv_code() + "}\n"
          + main_open + "  return float4(CustomExpression0(" + ", ".join(args) + "), 0, 1);\n}\n")
    surf_params = params + ["inout %s %s" % (TYPES[c], n) for n, c in SURFACE_OUTPUTS]
    surf = (head + "float3 CustomExpression0(" + ", ".join(surf_params) + ")\n{\n" + wallads_custom_code() + "}\n"
            + main_open + "  float Rough = 0; float Metal = 0; float Spec = 0; float3 Emis = 0; float3 NrmWS = 0;\n"
            "  float3 b = CustomExpression0(" + ", ".join(args + ["Rough", "Metal", "Spec", "Emis", "NrmWS"]) + ");\n"
            "  return float4(b + Emis + NrmWS * 0.001, Rough + Metal + Spec);\n}\n")
    return {"M_XinyiWallAds_UV": uv, "M_XinyiWallAds": surf}
    return {"M_XinyiWallAds_UV": uv, "M_XinyiWallAds": surf}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dxc", default="dxc")
    ap.add_argument("--hlsl-version", default="2018", choices=["2018", "2021"])
    args = ap.parse_args()
    global HV
    HV = args.hlsl_version
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        units = {mat: wrapper(mat) for mat in MATERIALS}
        units.update(wallads_wrappers())
        for mat, text in units.items():
            src = Path(td) / (mat + ".hlsl")
            src.write_text(text)
            for target in (["-T", "ps_6_0"], ["-T", "ps_6_0", "-spirv"]):
                r = subprocess.run([args.dxc, *target, "-E", "main", "-HV", HV, "-WX",
                                    "-Wno-conversion", "-Fo", str(Path(td) / "out.bin"), str(src)],
                                   capture_output=True, text=True)
                tag = "spirv" if "-spirv" in target else "dxil"
                if r.returncode != 0:
                    bad += 1
                    print("FAIL", mat, tag)
                    print(r.stderr[-3000:])
                else:
                    print("ok  ", mat, tag)
    if bad:
        raise SystemExit(f"{bad} HLSL compile failure(s)")
    print("XINYI_LOOK_HLSL_OK")


if __name__ == "__main__":
    main()
