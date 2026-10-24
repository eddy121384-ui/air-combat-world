"""Isolated mask experiment. Never rewrites xinyi_city.hlsl or baseline assets."""


def make_candidate(code):
    def once(old, new, count=1):
        nonlocal code
        if code.count(old) != count:
            raise RuntimeError('Baseline shader marker changed: ' + old[:80])
        code = code.replace(old, new)

    args = 'Texture2D facadeTx, SamplerState facadeS, Texture2D roofTx, SamplerState roofS, '
    once('Texture2D shopTx, SamplerState shopS, Texture2D planTx,',
         'Texture2D shopTx, SamplerState shopS, Texture2D planTx, ' + args, 2)
    once('float flags, float night, float fwp,\n             out float3 base',
         'float flags, float night, float fwp, ' + args + '\n             out float3 base')
    once('shopTx, shopS, planTx, bw, rw, mw, sw, ew);',
         'shopTx, shopS, planTx, facadeTx, facadeS, roofTx, roofS, bw, rw, mw, sw, ew);')
    once('flags, night, fwp, br, rr, mr, sr, er);',
         'flags, night, fwp, facadeTx, facadeS, roofTx, roofS, br, rr, mr, sr, er);')
    once('PlanTX, b, r, m, s, e, n);',
         'PlanTX, FacadeTX, FacadeTXSampler, RoofTX, RoofTXSampler, b, r, m, s, e, n);')

    # PNG V increases downwards. Height increases upwards; mirror U only.
    once('    float paneRough = lerp(0.13,', '''    float abMirror = frac(seed * 19.17) < 0.5 ? -1.0 : 1.0;
    float2 abFUV = float2(u * abMirror, -h) / 32.0 + float2(frac(seed * 31.1), frac(seed * 43.7));
    float2 abFDX = ddx(abFUV), abFDY = ddy(abFUV);
    float4 abFD = float4(0.0, 0.0, 0.0, 0.0);
    float abFW = isOldG * (1.0 - rooftop) * lerp(1.0, 0.6, step(1.5, arch));
    float abSolid = (1.0 - saturate(glassAmt)) * (1.0 - saturate(frame + cageCover + ac))
                  * (1.0 - arcade) * smoothstep(fh, fh * 1.5, h);
    [branch] if (abFW > 0.0)
    {
        abFD = (facadeTx.SampleGrad(facadeS, abFUV, abFDX, abFDY) * 255.0 - 128.0) / 24.0;
        float abFactor = clamp(1.0 + 0.10 * min(abFD.r, 0.0) + 0.07 * abFD.g
                              + 0.08 * min(abFD.b, 0.0) + 0.04 * abFD.a, 0.75, 1.12);
        c *= lerp(1.0, abFactor, abFW * abSolid);
    }
    float paneRough = lerp(0.13,''')
    once('    rough = lerp(rough, 0.35, frame);', '''    rough = lerp(rough, 0.35, frame);
    if (abFW * abSolid > 0.0)
        rough = clamp(rough + abFW * abSolid * (0.025 * abFD.r - 0.02 * abFD.g + 0.015 * abFD.a), 0.035, 0.98);''')

    once('    // flat concrete: a few large resurfacing / repair patches', '''    float2 abRUV = rp / 32.0 + float2(frac(seed * 31.1), frac(seed * 43.7));
    float2 abRDX = ddx(abRUV), abRDY = ddy(abRUV);
    float4 abRD = float4(0.0, 0.0, 0.0, 0.0);
    float abRW = isOld * (1.0 - sheetRoof);
    [branch] if (abRW > 0.0)
    {
        abRD = (roofTx.SampleGrad(roofS, abRUV, abRDX, abRDY) * 255.0 - 128.0) / 24.0;
        float abFactor = clamp(1.0 + 0.10 * abRD.r + 0.06 * abRD.g
                              + 0.08 * min(abRD.b, 0.0) + 0.04 * abRD.a, 0.75, 1.12);
        roofCol *= lerp(1.0, abFactor, abRW);
    }
    // flat concrete: a few large resurfacing / repair patches''')
    once('    rough = lerp(rough, 0.3, domeRoof);', '''    rough = lerp(rough, 0.3, domeRoof);
    if (abRW > 0.0)
        rough = clamp(rough + abRW * (0.04 * abRD.r - 0.03 * abRD.g + 0.02 * abRD.a), 0.035, 0.98);''')
    return code
