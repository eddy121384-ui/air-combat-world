// ============================================================================
// XinyiLook Cloud Prototype v0 — UE volumetric-cloud density (renderer layer).
//
// This file is ONE renderer of the renderer-agnostic cloud state
// (tools/lookdev/clouds/cloud_state_v0.json -> build_clouds.py). It only reads
// the weather map; cloud placement / type never lives here, so the same state
// can later drive impostor cards, mobile sprites or in-cloud fog instead.
//
// Weather map (RGBA, wrap, uv = UE xy / tile):
//   x = fair-weather cumulus coverage (1 at a cell core, 0 at its rim)
//   y = cumulus top, normalised to the cloud layer
//   z = broken-layer coverage,  w = broken-layer thickness (normalised)
// hn = normalised altitude in the VolumetricCloud layer (CloudSampleAttribute).
//
// Units: metres. Same Custom-node dialect as xinyi_city.hlsl (wrapped in a
// struct, helpers before use, results through out parameters).
// XCL_LOW: one fewer noise octave (renderer LOW quality path).
// XCL_BROKEN_BASE is injected from clouds.report.json (broken_base_norm).
// ============================================================================

float xcl_hash(float3 p)
{
    p = frac(p * 0.3183099 + float3(0.71, 0.113, 0.419));
    p *= 17.0;
    return frac(p.x * p.y * p.z * (p.x + p.y + p.z));
}

// trilinear value noise, smoothstep fade, 0..1
float xcl_noise(float3 x)
{
    float3 i = floor(x);
    float3 f = frac(x);
    f = f * f * (3.0 - 2.0 * f);
    float a = xcl_hash(i);
    float b = xcl_hash(i + float3(1.0, 0.0, 0.0));
    float c = xcl_hash(i + float3(0.0, 1.0, 0.0));
    float d = xcl_hash(i + float3(1.0, 1.0, 0.0));
    float e = xcl_hash(i + float3(0.0, 0.0, 1.0));
    float g = xcl_hash(i + float3(1.0, 0.0, 1.0));
    float h = xcl_hash(i + float3(0.0, 1.0, 1.0));
    float k = xcl_hash(i + float3(1.0, 1.0, 1.0));
    return lerp(lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y),
                lerp(lerp(e, g, f.x), lerp(h, k, f.x), f.y), f.z);
}

float xcl_hash2(float2 p)
{
    float3 p3 = frac(float3(p.x, p.y, p.x) * 0.1031);
    p3 += dot(p3, float3(p3.y, p3.z, p3.x) + 33.33);
    return frac((p3.x + p3.y) * p3.z);
}

float xcl_noise2(float2 x)
{
    float2 i = floor(x);
    float2 f = frac(x);
    f = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(xcl_hash2(i), xcl_hash2(i + float2(1.0, 0.0)), f.x),
                lerp(xcl_hash2(i + float2(0.0, 1.0)), xcl_hash2(i + float2(1.0, 1.0)), f.x), f.y);
}

// Weather-map lookup with a two-octave domain warp (~+-450 m): the state's round cells become
// irregular cloud outlines without changing where the clouds are.
float2 xcl_weather_uv(float3 p, float tile)
{
    float2 q = float2(p.x, p.y);
    float2 w = float2(xcl_noise2(q / 1700.0), xcl_noise2(q / 1700.0 + 31.7)) - 0.5;
    w += (float2(xcl_noise2(q / 600.0 + 7.1), xcl_noise2(q / 600.0 + 53.9)) - 0.5) * 0.45;
    return (q + w * 650.0) / tile;
}

// Coverage shapes. lump = signed billow offset from the noise (0 for the conservative envelope).
// fair-weather cumulus: flat base, dome-limited top (higher parts need more coverage). The base
// band also needs extra coverage: with only the dome term the threshold is ~0 at the base, and the
// billows spread wide paper-thin skirts at the shared base altitude that read as horizontal stripes
// edge-on from below. Bases stay flat but no wider than the cloud body.
float xcl_cumulus(float4 wx, float hn, float covBias, float lump, float topScale, out float hc)
{
    hc = hn / max(wx.y * topScale, 0.08);
    float threshold = hc * hc * 0.85 + 0.3 * (1.0 - smoothstep(0.0, 0.3, hc));
    return saturate(wx.x + covBias + lump - threshold) * saturate(hc * 14.0) * saturate((1.12 - hc) * 8.0);
}

// broken layered field: a lumpy sheet between base and base + thickness
float xcl_broken(float4 wx, float hn, float covBias, float lump, out float bh)
{
    bh = (hn - XCL_BROKEN_BASE) / max(wx.w, 0.03);
    return saturate(wx.z * 1.1 + covBias + lump - abs(bh - 0.45) * 1.5) * saturate(bh * 10.0) * saturate((1.0 - bh) * 6.0);
}

// gain = density contrast (edge sharpness); fine = weight of the ~320 m lobes. HIGH keeps 2.2 / 0.45;
// LOW softens both: at LOW view-sample counts the sharp, fine density aliases into per-pixel grain.
void xcl_cloud(float3 p, float4 wx, float hn, float covBias, float gain, float fine,
               out float dens, out float env, out float ao)
{
    // conservative envelope: the largest possible billow offset (+0.6), lets the engine skip
    // empty space before any noise is evaluated
    float hc; float bh;
    env = max(xcl_cumulus(wx, hn, covBias, 0.6, 1.25, hc), xcl_broken(wx, hn, covBias, 0.6, bh));
    dens = 0.0;
    ao = 1.0;
    if (env > 0.0)
    {
        // Billows modulate the COVERAGE (not just the surface): ~900 m masses and ~320 m lobes
        // break each cell's dome into a cumulus. A slight upward shear tilts the towers.
        float3 q0 = p + float3(hc * 260.0, hc * 90.0, 0.0);
        // Rotate the noise domain: axis-aligned value-noise lattice planes are horizontal, and in a
        // thin cloud layer they slice every cell into shelves at the same altitudes (seen edge-on
        // as horizontal stripes). An orthonormal rotation tilts the lattice off the horizontal.
        float3 q = float3(dot(q0, float3(0.80, 0.36, 0.48)), dot(q0, float3(-0.60, 0.48, 0.64)), dot(q0, float3(0.0, -0.80, 0.60)));
        float n1 = xcl_noise(q / 900.0);
        float n2 = xcl_noise(q / 320.0 + 17.3);
        float lump = (n1 - 0.5) * 0.7 + (n2 - 0.5) * fine;
        // tower tops vary with the large billow (0.8 .. 1.25 x the cell top) so neighbours differ
        float shape = max(xcl_cumulus(wx, hn, covBias, lump, 0.8 + 0.45 * n1, hc), xcl_broken(wx, hn, covBias, lump * 0.8, bh));
#ifdef XCL_LOW
        float erode = 0.0;
#else
        // fine edge detail (~140 m), HIGH only; strongest on the upper, sunlit parts
        float erode = (1.0 - xcl_noise(q / 140.0 + 41.7)) * 0.16 * saturate(hc + 0.3);
#endif
        dens = saturate((shape - erode) * gain);
        // sky-light occlusion: grey-blue undersides, bright tops (never black)
        float hv = max(saturate(hc), saturate(bh) * step(0.001, wx.z));
        ao = lerp(0.6, 1.0, saturate(hv * 1.2));
    }
}
