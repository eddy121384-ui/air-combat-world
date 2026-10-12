// ForestSpike B0 shared shading (HLSL, pasted into UE Custom nodes wrapped in a struct, same technique as
// tools/lookdev/ue_custom_code.py). Units are metres. World frame: UE X = east, UE Y = -north, Z up, so the
// ENU position is (WP.x, -WP.y).
//
// Design intent (a test fixture, not final art): ground = open grass / dark forest understory; the far canopy
// layer "S" fades in on the forest-mask ground with distance (core) or everywhere (shared context). Trees are
// one opaque vertex-colour material shared by every N arm so arms differ only in geometry/placement.
//
// ID pass: when Dbg > 0.5 every surface is unlit-emissive with a pixel code decoded offline
//   R = class * 40 / 255      class: 1 core open ground, 2 core forest ground, 3 context open ground,
//                                    4 context forest ground, 5 tree arm A, 6 tree arm B; 0 = sky / nothing
//   G, B = hi / lo byte of round(slant_range_m * 7)    (range up to 9362 m, 0.14 m resolution)
// The class / range codes are written through fs_idenc(), which inverts the render-target transfer curve so the
// byte read back from the PNG equals the intended code (calibrated by fs_capture.py --calibrate).

float fs_hash(float2 p)
{
    p = frac(p * float2(0.1031, 0.1030));
    p += dot(p, p.yx + 33.33);
    return frac((p.x + p.y) * p.x);
}

float fs_vnoise(float2 p)
{
    float2 i = floor(p);
    float2 f = frac(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = fs_hash(i);
    float b = fs_hash(i + float2(1.0, 0.0));
    float c = fs_hash(i + float2(0.0, 1.0));
    float d = fs_hash(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// 0..1 canopy value at crown scale; octaves fade to their mean when the pixel footprint (m) approaches their
// wavelength, so the far layer carries no shimmer-prone detail below ~half a crown per pixel.
float fs_crown(float2 en, float fw)
{
    float w1 = 1.0 - smoothstep(0.25, 0.75, fw / 9.0);
    float w2 = 1.0 - smoothstep(0.25, 0.75, fw / 4.5);
    float n1 = fs_vnoise(en / 9.0);
    float n2 = fs_vnoise(en / 4.5 + 37.1);
    return saturate(0.5 + 1.15 * w1 * (n1 - 0.5) + 0.55 * w2 * (n2 - 0.5));
}

// encode a 0..255 byte so that the 8-bit value read back from the capture equals it (sRGB transfer when GAMMA)
float fs_idenc(float byte_value, float gamma)
{
    float v = saturate(byte_value / 255.0);
    float lin = (v <= 0.04045) ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4);
    return lerp(v, lin, gamma);
}

float3 fs_idcolor(float cls, float range_m, float gamma)
{
    float u = floor(clamp(range_m, 0.0, 9362.0) * 7.0 + 0.5);
    float hi = floor(u / 256.0);
    float lo = u - hi * 256.0;
    return float3(fs_idenc(cls * 40.0, gamma), fs_idenc(hi, gamma), fs_idenc(lo, gamma));
}

// Ground. FC / FX = core / context field samples (R forest coverage, G edge distance, B slope).
void fs_ground(float3 WP, float3 N, float3 Cam, float4 FC, float4 FX,
               float SCore, float SCtx, float dS, float wS, float Und, float Dbg, float IdGamma,
               out float3 base, out float rough, out float spec, out float3 emis, out float3 nrm)
{
    float2 en = float2(WP.x, -WP.y);
    float inCore = step(abs(en.x), 500.0) * step(abs(en.y), 500.0);
    float forest = smoothstep(0.35, 0.65, lerp(FX.r, FC.r, inCore));
    float dist = length(WP - Cam);
    float fw = max(length(float2(ddx(en.x), ddx(en.y))), length(float2(ddy(en.x), ddy(en.y))));

    // open ground: grass with slow value variation
    float lowN = fs_vnoise(en / 140.0);
    float fineN = fs_vnoise(en / 3.0);
    float3 grass = float3(0.062, 0.100, 0.030) * (0.8 + 0.5 * lowN) * (0.92 + 0.16 * lerp(fineN, 0.5, saturate(fw / 3.0)));
    float3 litter = float3(0.014, 0.019, 0.011) * (0.8 + 0.4 * lowN);
    float3 understory = lerp(grass, litter, Und);

    // far canopy layer S
    float sOn = lerp(SCtx, SCore * smoothstep(dS - wS, dS, dist), inCore);
    float c = fs_crown(en, fw);
    float patch = fs_vnoise(en / 170.0 + 11.0);
    float3 dark = float3(0.010, 0.026, 0.014);
    float3 lit = lerp(float3(0.040, 0.078, 0.024), float3(0.066, 0.092, 0.020), smoothstep(0.55, 0.85, patch));
    float3 canopy = lerp(dark, lit, pow(c, 1.3));
    float3 forestCol = lerp(understory, canopy, sOn);
    base = lerp(grass, forestCol, forest);
    rough = 0.9;
    spec = 0.2;
    emis = float3(0.0, 0.0, 0.0);
    nrm = normalize(N);
    // crown relief for the canopy layer: perturb the normal with the crown noise gradient (near footprints only)
    [branch] if (sOn * forest > 0.01 && fw < 5.0)
    {
        float e = 1.2;
        float cx = fs_crown(en + float2(e, 0.0), fw) - c;
        float cy = fs_crown(en + float2(0.0, e), fw) - c;
        float k = 2.2 * (1.0 - saturate(fw / 5.0)) * sOn * forest;
        // ENU gradient -> UE world (X east, Y = -north)
        nrm = normalize(nrm + float3(-cx * k, cy * k, 0.0));
    }

    [branch] if (Dbg > 0.5)
    {
        float cls = lerp(lerp(3.0, 4.0, step(0.5, forest)), lerp(1.0, 2.0, step(0.5, forest)), inCore);
        base = float3(0.0, 0.0, 0.0);
        rough = 1.0;
        spec = 0.0;
        emis = fs_idcolor(cls, dist, IdGamma);
        nrm = normalize(N);
    }
}

// Tree: one opaque vertex-colour material for every N arm (A / B / later C-D share it).
void fs_tree(float3 WP, float3 N, float3 Cam, float3 VC, float var01, float u01, float Dbg, float ArmId, float IdGamma,
             out float3 base, out float rough, out float spec, out float3 emis, out float3 nrm)
{
    float3 c = VC * (0.82 + 0.36 * u01);
    float3 yg = float3(1.14, 1.06, 0.62);
    c = lerp(c, c * yg, smoothstep(0.80, 1.0, var01) * 0.8);
    base = c;
    rough = 0.85;
    spec = 0.25;
    emis = float3(0.0, 0.0, 0.0);
    nrm = normalize(N);
    [branch] if (Dbg > 0.5)
    {
        base = float3(0.0, 0.0, 0.0);
        rough = 1.0;
        spec = 0.0;
        emis = fs_idcolor(ArmId, length(WP - Cam), IdGamma);
    }
}
