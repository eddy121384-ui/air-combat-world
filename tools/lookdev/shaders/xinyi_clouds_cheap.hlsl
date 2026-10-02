// ============================================================================
// XinyiLook Cheap Cloud Renderer v1 (EXPERIMENTAL) - analytic lobe impostor.
//
// One renderer of the renderer-agnostic cloud state (cloud_state_v0.json ->
// build_clouds.py cells -> build_cloud_cheap.py). Near, each cloud cell is drawn
// as ONE translucent proxy box (inward-facing: its far side rasterises once per
// pixel, also with the camera inside); far away, one proxy per cluster of
// neighbouring cells draws their merged, flatter far-field mass. The two hand
// over by camera distance in optical depth (continuous, no popping).
// The pixel shader intersects the view ray analytically with the proxy's <= 8
// ellipsoid lobes (per-lobe vertical squash):
//   * optical depth = sum of closed-form chord integrals of a (1 - r^2)^2
//     density profile  -> order-independent inside a cell (no lobe sorting),
//     rotation-invariant (no billboard swing), true parallax, soft edges;
//   * chords are clipped by the cell base plane (flat cumulus bases) and by
//     the opaque scene depth (soft terrain / building intersection);
//   * one world-anchored texture-noise fbm (2-3 octaves by distance) erodes the
//     lobe silhouettes; a one-step noise derivative toward the sun shades billows;
//   * lighting at the first visible point: analytic sun transmittance through
//     the lobes (self-shadow) with a multiple-scattering floor, a dual-lobe
//     phase on thin parts (silver lining), smooth-union lobe normal, sky-light
//     ambient with a vertical gradient (darker bases);
//   * distance LOD: fine noise, lobe normal and the sun pass fade to cheap
//     approximations with distance (smooth bands, no popping).
// Camera inside a lobe: the chord starts at the camera -> dense, lit mist, and
// the lobe density AT the camera blends in a uniform lit fog (local in-cloud fog).
//
// Units: metres (UE world / 100). Same Custom-node dialect as the other
// XinyiLook shaders (struct-wrapped, helpers before use, out parameters).
// ============================================================================

// iq-style 3D value noise from a 256^2 lattice texture: G(i, j) = R(i + 37, j + 17)
float xcc_n3(Texture2D T, SamplerState S, float3 x)
{
    float3 p = floor(x);
    float3 f = frac(x);
    f = f * f * (3.0 - 2.0 * f);
    float2 uv = (p.xy + float2(37.0, 17.0) * p.z) + f.xy;
    float2 rg = T.SampleLevel(S, (uv + 0.5) / 256.0, 0.0).xy;
    return lerp(rg.x, rg.y, f.z);
}

// integral over normalised ray coordinate s in [s0, s1] of the lobe profile (w2 - s^2)^2
float xcc_prof(float w2, float s0, float s1)
{
    float a3 = s1 * s1 * s1 - s0 * s0 * s0;
    float a5 = s1 * s1 * s1 * s1 * s1 - s0 * s0 * s0 * s0 * s0;
    return w2 * w2 * (s1 - s0) - (2.0 / 3.0) * w2 * a3 + 0.2 * a5;
}

float xcc_hg(float c, float g)
{
    float g2 = g * g;
    return (1.0 - g2) / pow(max(1.0 + g2 - 2.0 * g * c, 1e-4), 1.5);   // x 4pi: isotropic = 1
}

// sun optical depth (without sigma) from box-relative point p along unit direction l
// L[i] = (centre, radius), S3[i] = per-lobe normalising scale (1, 1, 1 / squash) / radius
float xcc_sun_depth(float4 L[8], float3 S3[8], float3 p, float3 l)
{
    float acc = 0.0;
    [unroll] for (int i = 0; i < 8; i++)
    {
        if (L[i].w > 0.0)
        {
            float3 s3 = S3[i];
            float3 oo = (p - L[i].xyz) * s3;
            float3 dd = l * s3;
            float a = dot(dd, dd);
            float b = dot(oo, dd);
            float w2 = 1.0 - (dot(oo, oo) - b * b / a);
            if (w2 > 0.0)
            {
                float sc = rsqrt(a);
                float w = sqrt(w2);
                float s0 = max(-w, b * sc);   // s at t = 0: (0 - tc) / sc = (b / a) * sqrt(a)
                if (w > s0)
                    acc += sc * xcc_prof(w2, s0, w);
            }
        }
    }
    return acc;
}

// clip the ray interval [tLo, tHi] to z >= baseZ (box-relative o, unit d)
float2 xcc_base_clip(float3 o, float3 d, float baseZ, float tLo, float tHi)
{
    if (abs(d.z) > 1e-5)
    {
        float tb = (baseZ - o.z) / d.z;
        if (d.z > 0.0) tLo = max(tLo, tb); else tHi = min(tHi, tb);
    }
    else if (o.z < baseZ)
    {
        tHi = -1.0;
    }
    return float2(tLo, tHi);
}


// wp  far-side proxy pixel (world m)     cam camera (world m)     obj proxy box centre (world m)
// l0..l7 lobes (box-relative centre m, w = whole-metre radius + vertical squash / 2; w = 0: unused)
// prm = (base z rel, role: +1 near cell / -1 far cluster, variation seed, bounding-sphere radius m)
// sunDir unit vector toward the sun, sunE sun illuminance at the cloud, skyUp / skyDown sky-light radiance
// sceneDepth / pixelDepth view-space depths (any common unit) of the opaque scene and of this pixel
// k1 = (sigma 1/m, erosion, density noise, ambient scale)   k2 = (sun scale, silver, fade end m, MS floor)
// k3 = near -> far hand-over (start m, end m), far fade-out (start m, end m), camera to proxy centre
// glow = city glow on cloud bases (night)
void xcc_cloud(float3 wp, float3 cam, float3 obj,
               float4 l0, float4 l1, float4 l2, float4 l3, float4 l4, float4 l5, float4 l6, float4 l7,
               float4 prm, float3 sunDir, float3 sunE, float3 skyUp, float3 skyDown,
               float sceneDepth, float pixelDepth, Texture2D nt, SamplerState ns,
               float4 k1, float4 k2, float4 k3, float3 glow, out float3 color, out float alpha)
{
    color = float3(0.0, 0.0, 0.0);
    alpha = 0.0;
    float3 o = cam - obj;
    // representation weight by camera distance to the proxy: near cells hand over to far clusters by
    // scaling optical depth (near x (1 - w), far x w), so the summed transmittance interpolates
    // continuously (no alpha pop); the far clusters fade out at the far end. The proxies are culled by
    // the engine just outside the band where their weight reaches zero.
    float far = prm.y < 0.0 ? 1.0 : 0.0;
    float dc = length(o);
    float hand = smoothstep(k3.x, k3.y, dc);
    float lodW = lerp(1.0 - hand, hand * (1.0 - smoothstep(k3.z, k3.w, dc)), far);
    if (lodW <= 0.0)
        return;
    float3 dv = wp - cam;
    float dlen = max(length(dv), 1e-3);
    float3 d = dv / dlen;
    // opaque scene distance along this ray (depths are view-space z, the ratio converts to ray length)
    float tHi = sceneDepth / max(pixelDepth, 1e-4) * dlen;
    float tLo = 0.0;
    // early out: bounding sphere of all (eroded) lobes
    {
        float b = dot(o, d);
        float disc = b * b - (dot(o, o) - prm.w * prm.w);
        if (disc <= 0.0)
            return;
        float sd = sqrt(disc);
        tLo = max(tLo, -b - sd);
        tHi = min(tHi, -b + sd);
    }
    float baseZ = prm.x;
    // conservative base clip (the noise-jittered base below never sits lower than baseZ - 50 m)
    float2 tr = xcc_base_clip(o, d, baseZ - 50.0, tLo, tHi);
    tLo = tr.x;
    tHi = tr.y;
    if (tHi <= tLo)
        return;

    // decode lobes: radius = whole metres, per-lobe vertical squash in the fraction
    float4 L[8] = { l0, l1, l2, l3, l4, l5, l6, l7 };
    float3 S3[8];
    [unroll] for (int u = 0; u < 8; u++)
    {
        float rr = floor(L[u].w);
        float kk = max(frac(L[u].w) * 2.0, 0.05);
        L[u].w = rr;
        S3[u] = float3(1.0, 1.0, 1.0 / kk) / max(rr, 1.0);
    }

    // pass 1: closest approach per lobe (normalised squared miss distance h2, metres per unit scl)
    float tc[8]; float h2[8]; float scl[8];
    float tW = 0.0;
    float wSum = 0.0;
    float topW = 0.0;
    float dcam = 0.0;
    float top = baseZ;
    [unroll] for (int i = 0; i < 8; i++)
    {
        float3 s3 = S3[i];
        float3 oo = (o - L[i].xyz) * s3;
        float3 dd = d * s3;
        float a = dot(dd, dd);
        float b = dot(oo, dd);
        tc[i] = -b / a;
        h2[i] = L[i].w > 0.0 ? dot(oo, oo) - b * b / a : 9.0;
        float rc = L[i].w > 0.0 ? max(0.0, 1.0 - dot(oo, oo)) : 0.0;   // lobe density at the camera
        dcam += rc * rc;
        scl[i] = rsqrt(a);
        // smooth weights: the noise point must be continuous across lobe boundaries (a "nearest lobe"
        // switch makes the erosion jump and draws hard arcs)
        float wl = max(0.0, 1.3 - h2[i]);
        wl *= wl;
        tW += wl * tc[i];
        wSum += wl;
        topW += wl * (L[i].z + 1.0 / S3[i].z);
        top = L[i].w > 0.0 ? max(top, L[i].z + 1.0 / S3[i].z) : top;   // lobe top = z + radius * squash
    }
    if (wSum <= 0.0)
        return;
    float tN = clamp(tW / wSum, tLo, tHi);

    // world-anchored erosion noise at the weighted lobe closest approach (does not swim with the view)
    float3 pn = cam + d * tN;
    float n0 = xcc_n3(nt, ns, pn * (1.0 / 600.0) + prm.z * 17.0);   // large octave: far silhouettes
    float n1 = xcc_n3(nt, ns, pn * (1.0 / 170.0) + prm.z * 31.0);
    float fineW = saturate((9000.0 - tN) / 5000.0);   // fine octave only near: no far shimmer
    float n2 = 0.5;
    [branch] if (fineW > 0.0)
        n2 = lerp(0.5, xcc_n3(nt, ns, pn * (1.0 / 55.0) + 3.7), fineW);
    float nearF = saturate((3500.0 - tN) / 2000.0);   // third, finest octave only close up
    float n3 = 0.5;
    [branch] if (nearF > 0.0)
        n3 = lerp(0.5, xcc_n3(nt, ns, pn * (1.0 / 19.0) + 11.3), nearF);
    float fbm = n0 * 0.3 + n1 * 0.35 + n2 * 0.22 + n3 * 0.13;
    // far clusters: an extra ~2.4 km octave (domain-scale irregularity) breaks the merged lobes into
    // ragged, asymmetric masses instead of smooth ellipsoid outlines
    float nB = 0.5;
    [branch] if (far > 0.0)
        nB = lerp(0.5, xcc_n3(nt, ns, pn * (1.0 / 2400.0) + prm.z * 7.0), 1.6);
    // erosion acts on the outer shell only (E * h2): cores stay solid, edges billow; E >= -0.15
    // bounds the growth to ~8.5 % of a lobe radius (inside the proxy pad)
    float E = clamp((fbm - 0.45) * 4.0 * k1.y + (nB - 0.5) * 2.2, -0.15, 3.0);
    // denser up close: the soft (1 - r^2)^2 edge band is ~0.3 lobe radii, which near the camera spans
    // hundreds of pixels and reads out of focus; a higher sigma narrows it so the fine erosion shows
    float sigma = k1.x * (1.0 + k1.z * (fbm - 0.5) * 2.0) * lerp(2.5, 1.0, saturate((tN - 1500.0) / 8000.0));
    // ragged, gently undulating base instead of a razor-flat plate
    tr = xcc_base_clip(o, d, baseZ + (n0 - 0.5) * 70.0 + (n1 - 0.5) * 30.0, tLo, tHi);
    tLo = tr.x;
    tHi = tr.y;

    // pass 2: optical depth of the eroded lobes over [tLo, tHi]
    float tau = 0.0;
    float tIn = 1e9;
    float tInW = 0.0;
    float wIn = 0.0;
    float softS = 150.0 + 0.02 * tLo;
    [unroll] for (int j = 0; j < 8; j++)
    {
        // min(h2, 1): w2 must fall monotonically with h2, or a negative E re-opens phantom shells
        // far outside the lobe (clipped only by the bounding sphere -> hard arcs and shards)
        float w2 = 1.0 - h2[j] * (1.0 + E * min(h2[j], 1.0));
        if (w2 > 0.0)
        {
            float w = sqrt(w2);
            float s0 = max(-w, (tLo - tc[j]) / scl[j]);
            float s1 = min(w, (tHi - tc[j]) / scl[j]);
            if (s1 > s0)
            {
                float tj = scl[j] * xcc_prof(w2, s0, s1);
                tau += tj;
                tIn = min(tIn, tc[j] + s0 * scl[j]);
                float tin = tc[j] + s0 * scl[j];
                float wj = tj * exp(-(tin - tLo) / softS);   // front-biased, fades in with tj
                tInW += wj * tin;
                wIn += wj;
            }
        }
    }
    tau *= lodW;
    if (tau * sigma < 1e-3)
        return;
    // lighting point: about one mean free path behind a soft minimum of the lobe entries, weighted by
    // optical depth and biased to the front (softS). Not the hard minimum: a front lobe's eroded edge
    // fading in must not make the lit point jump (dark contours); not a plain tau average: a thick back
    // lobe would pull the lit point deep behind the front lobes (dark, over-shadowed balls)
    float tE = wIn > 1e-20 ? tInW / wIn : tIn;
    float tP = min(tE + min(1.0 / max(sigma, 1e-4), 120.0), tHi);
    tau *= sigma;
    float3 P = o + d * tP;
    // height in the cloud for lighting: v0 cells use the whole cell; a far cluster uses the tops of the
    // lobes around the ray (a low deck between towers is lit like a cloud top, not like a tower's base)
    float topL = lerp(top, topW / wSum, far);
    float hf = saturate((P.z - baseZ) / max(topL - baseZ, 1.0));

    // smooth-union lobe normal (weights fall to zero at 1.26 radii); fades to "up" far away
    float nearW = saturate((18000.0 - tIn) / 6000.0);
    float3 nrm = float3(0.0, 0.0, 1.0);
    [branch] if (nearW > 0.0)
    {
        float3 g = float3(0.0, 0.0, 1e-3);
        [unroll] for (int m = 0; m < 8; m++)
        {
            if (L[m].w > 0.0)
            {
                float3 q = (P - L[m].xyz) * S3[m];
                float wgt = max(0.0, 1.6 - dot(q, q));
                g += wgt * wgt * q * S3[m] * L[m].w;
            }
        }
        nrm = normalize(lerp(float3(0.0, 0.0, 1.0), normalize(g), nearW));
    }

    // sun: analytic transmittance through the cell's lobes + multiple-scattering floor; far away a
    // height-based approximation (tops lit, bases shaded) replaces the lobe pass
    // inside the cloud the light is mostly multiply scattered: a much higher floor keeps the mist a
    // bright, diffuse grey-white instead of darkening with depth
    float msFloor = lerp(k2.w, 0.6, saturate(1.0 - tIn / 200.0) * (1.0 - far));
    // far clusters are broad, flat masses: a sun ray through a whole deck is long, but their light is
    // mostly multiply scattered - a higher floor keeps distant decks from reading as grey slabs
    msFloor *= lerp(1.0, 2.2, far);
    float cosT = dot(d, sunDir);
    // height-based far approximation: tops lit; sides lit when the sun is behind the viewer (we see the
    // sunlit faces), shaded when looking toward the sun
    float Tfar = lerp(msFloor, 1.0, saturate(hf * hf + (1.0 - hf * hf) * 0.75 * saturate(0.5 - 0.5 * cosT) * far));
    float sunW = saturate((30000.0 - tIn) / 8000.0);
    float Ts = Tfar;
    [branch] if (sunW > 0.0)
    {
        float tauS = sigma * xcc_sun_depth(L, S3, P, sunDir);
        Ts = lerp(Tfar, max(exp(-tauS), msFloor * exp(-tauS * lerp(0.08, 0.03, far))), sunW);
    }
    float edge = exp(-tau * 0.5);
    float ph = lerp(1.0, lerp(xcc_hg(cosT, 0.6), xcc_hg(cosT, -0.2), 0.35), edge * k2.y);
    float lam = lerp(0.72, 1.0, saturate(dot(nrm, sunDir) * 0.5 + 0.5));
    float albedo = 0.92 * lerp(0.94, 1.04, frac(prm.z * 7.31));      // per-cell brightness variation
    float detail = lerp(0.84, 1.05, fbm);                            // cauliflower shading from the same noise
    // billow self-shadow: one noise step toward the sun from the lit point (directional derivative)
    float bump = 1.0;
    [branch] if (fineW > 0.0)
    {
        float3 Pw = obj + P;
        float b0 = xcc_n3(nt, ns, Pw * (1.0 / 90.0) + 5.3);
        float b1 = xcc_n3(nt, ns, (Pw + sunDir * 35.0) * (1.0 / 90.0) + 5.3);
        bump = saturate(1.0 + (b0 - b1) * 1.6 * fineW);
    }
    float3 sunL = sunE * (k2.x * albedo / 3.14159265) * Ts * lam * ph * detail * bump;

    // sky ambient: lit tops, darker grey-blue bases
    float3 amb = skyUp * saturate(0.62 + 0.38 * nrm.z) + skyDown * saturate(0.38 - 0.38 * nrm.z);
    amb *= lerp(lerp(0.5, 0.75, far), 1.0, hf) * k1.w * albedo * detail;   // far bases lighter (no dark seams)
    float3 gl = glow * (1.0 - hf) * saturate(0.5 - 0.5 * nrm.z);

    color = sunL + amb + gl;
    alpha = (1.0 - exp(-tau)) * saturate((k2.z - tIn) / 8000.0);

    // local fog with the camera inside the cloud: the density at the camera fades in a uniform, lit
    // mist (diffuse multiple-scattering light, no lobe normal), so lobe structure dissolves into fog
    // (near cells only: far clusters are never drawn around the camera)
    float mistA = saturate(dcam * 2.0) * lodW * (1.0 - far);
    [branch] if (mistA > 0.0)
    {
        float3 mist = sunE * (k2.x * albedo / 3.14159265) * lerp(0.55, 0.9, hf)
                    + (skyUp * 0.62 + skyDown * 0.38) * lerp(0.5, 1.0, hf) * k1.w * albedo + glow;
        color = lerp(color, mist, mistA);
        alpha = max(alpha, mistA);
    }
}

// ----------------------------------------------------------------------------
// Cheap cloud shadow (sun light function). The offline bake integrates the near
// lobes' optical depth over three height bands into a tileable texture (R / G / B
// = band tau / tauMax, uv = UE xy / tile like the weather map). Each band is
// sampled where the sun ray from the shaded point crosses the band's middle, so
// low suns stretch shadows along the sun azimuth. World-anchored: no swimming.
// wp shaded point (world m)  sunDir unit vector toward the sun
// shp = (strength 0..1, tau scale, tile m, tauMax)   bandZ = band mid heights (m)
// ----------------------------------------------------------------------------
float xcc_shadow(float3 wp, float3 sunDir, Texture2D st, SamplerState ss, float4 shp, float3 bandZ)
{
    float sz = max(sunDir.z, 0.04);
    float tau = 0.0;
    [unroll] for (int b = 0; b < 3; b++)
    {
        float h = b == 0 ? bandZ.x : (b == 1 ? bandZ.y : bandZ.z);
        float t = (h - wp.z) / sz;
        if (t > 0.0)
        {
            float2 uv = (wp.xy + sunDir.xy * t) / shp.z;
            float4 v = st.SampleLevel(ss, uv, 0.0);
            tau += b == 0 ? v.x : (b == 1 ? v.y : v.z);
        }
    }
    return lerp(1.0, exp(-tau * shp.w * shp.y), shp.x);
}
