// ============================================================================
// XinyiLook city surface shader — single source for Unreal and the look-dev
// preview renderer.
//
// Dialect: the common subset of HLSL and GLSL ES 3.0. The preview prepends a
// macro prelude (float3->vec3, frac->fract, lerp->mix, saturate->clamp...).
// Unreal wraps the whole file in `struct XinyiCity { ... };` inside a Custom
// node, so: no globals, no static data, no local structs, no scalar swizzles,
// helpers declared before use, results returned through `out` parameters.
//
// Units: metres. World Z is up. All inputs come from the look vertex contract
// (tools/lookdev/build_look_tiles.py):
//   uv0   walls: (perimeter m, height above surveyed ground m)
//         roofs: tile-local (east, north) m
//   uv1   (record height m, visual floor height m)
//   vc    xc_unpack(TEXCOORD_2): r = (archetype*16+variant)/255, g = seed/255,
//         b = weathering, a = flags/255 (bit0 core, bit1 anchor, bit2 podium part, bit3 rooftop
//         structure; bits 4-6: school walls bit4 = corridor side, other walls = street frontage role,
//         0 = no frontage contract -> accepted grammar; see xc_wall)
//   archetypes 0 low, 1 walkup, 2 huaxia, 3 res_tower, 4 office_glass, 5 commercial_podium,
//         6 civic, 7 school. The accepted wall / roof functions only know 0..6 (open-ended tests such as
//         step(5.5, arch) would treat 7 as civic): school pixels are routed explicitly in xc_city to
//         xc_school_wall / xc_school_roof, which replace every output, so no accepted branch (civic,
//         podium, tower, shop-house, landmark roof) ever reaches a school pixel. The accepted functions are
//         kept text-identical so every non-school pixel compiles and computes exactly as before.
//
// Cost discipline (iPhone 11 Pro-class lower bound): ALU only, no textures,
// no loops, every high-frequency pattern is fwidth-filtered toward its mean
// so distant facades converge to stable averages instead of shimmering.
// ============================================================================

// TEXCOORD_2 carries RGBA8 data packed as (R*256+G, B*256+A); returns 0..1.
// Xinyi WFS building-source bbox (ENU m), injected by the Unreal ground material builder.
// Defaults put the whole Landscape "inside" (no stand-in band) for the preview renderer.
// Taipei Street Reality v0E storefront plan texture (tools/lookdev/build_storefronts.py): 2048^2 over the
// ground extent (east -1500..1000 m, north -1000..1500 m), read with Texture.Load in xc_wall.
#ifndef XC_PLAN_E0
#define XC_PLAN_E0 (-1500.0)
#define XC_PLAN_N1 (1500.0)
#define XC_PLAN_PX (1.220703125)
#define XC_PLAN_RES 2048
#endif
#ifndef XC_SRC_E0
#define XC_SRC_E0 (-1.0e6)
#define XC_SRC_E1 (1.0e6)
#define XC_SRC_N0 (-1.0e6)
#define XC_SRC_N1 (1.0e6)
#endif

float4 xc_unpack(float2 d)
{
    float r = floor(d.x / 256.0 + 1e-4);
    float g = d.x - r * 256.0;
    float b = floor(d.y / 256.0 + 1e-4);
    float a = d.y - b * 256.0;
    return float4(r, g, b, a) / 255.0;
}

float xc_hash11(float p)
{
    p = frac(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return frac(p);
}

float xc_hash21(float2 p)
{
    float3 p3 = frac(float3(p.x, p.y, p.x) * 0.1031);
    p3 += dot(p3, float3(p3.y, p3.z, p3.x) + 33.33);
    return frac((p3.x + p3.y) * p3.z);
}

float xc_hash31(float3 p)
{
    float3 p3 = frac(p * 0.1031);
    p3 += dot(p3, float3(p3.z, p3.y, p3.x) + 31.32);
    return frac((p3.x + p3.y) * p3.z);
}

float xc_noise1(float x)
{
    float i = floor(x);
    float f = frac(x);
    float u = f * f * (3.0 - 2.0 * f);
    return lerp(xc_hash11(i), xc_hash11(i + 1.0), u);
}

float xc_noise2(float2 p)
{
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * (3.0 - 2.0 * f);
    float a = xc_hash21(i);
    float b = xc_hash21(i + float2(1.0, 0.0));
    float c = xc_hash21(i + float2(0.0, 1.0));
    float d = xc_hash21(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, u.x), lerp(c, d, u.x), u.y);
}

// Band-limited value noise: fades to its mean (0.5) once the lattice period
// drops below ~2 pixels, so distant terrain never shows lattice moire.
float xc_fnoise(float2 p, float freq, float fw)
{
    return lerp(0.5, xc_noise2(p * freq), 1.0 - smoothstep(0.2, 0.5, fw * freq));
}

// Anti-aliased box: 1 inside [a,b] of a periodic coordinate t in [0,1).
// w = filter width in the same units. Returns coverage (0..1).
float xc_box(float t, float a, float b, float w)
{
    float hw = max(w, 1e-4) * 0.5;
    return saturate((min(t + hw, b) - max(t - hw, a)) / (2.0 * hw));
}

// Filtered periodic thin line of relative width lw at t=0 (period 1).
float xc_line(float t, float lw, float w)
{
    float d = min(t, 1.0 - t);
    return 1.0 - smoothstep(lw * 0.5 - w, lw * 0.5 + w, d);
}

// Fade factor for detail with period `period` given screen-space derivative
// `fw` of the coordinate: 1 = fully resolved, 0 = sub-pixel (use the mean).
float xc_detail(float fw, float period)
{
    return 1.0 - smoothstep(0.18, 0.55, fw / max(period, 1e-4));
}

float3 xc_pick4(float r, float3 a, float3 b, float3 c, float3 d)
{
    float3 x = lerp(a, b, step(0.25, r));
    x = lerp(x, c, step(0.5, r));
    return lerp(x, d, step(0.75, r));
}

float3 xc_pick6(float r, float3 a, float3 b, float3 c, float3 d, float3 e, float3 f)
{
    float3 x = lerp(a, b, step(0.1667, r));
    x = lerp(x, c, step(0.3333, r));
    x = lerp(x, d, step(0.5, r));
    x = lerp(x, e, step(0.6667, r));
    return lerp(x, f, step(0.8333, r));
}

// Taipei rooftop sheet-metal palette (index 0..15, tools/lookdev/build_rooftops.py SHEET_NAMES; the
// builder draws indices with district weights). Sun-faded, oxidised, matte: pale desaturated green-greys,
// off-white / neutral greys, muted maroon / faded reds; blue-greys are a rare accent (Roofscape v2 step 0:
// blue was ~25 % of the mix, the orthophoto sample says 1-4 %). No saturated toy colours.
// Painted whole-roof sheet colour index (no instance data): r is mapped through the cumulative SHEET_W_OLD
// weights (build_rooftops.py), so painted roofs (old roofs, surveyed rooftop records, far city) follow the
// same mix as the instanced rooms. r2 is unused (kept for the call sites).
float xc_sheet_paint_index(float r, float r2)
{
    // cumulative SHEET_W_OLD / 100 for slots 0..14: [1 2 3 10 17 23 36 39 55 67 73 86 90 93 98]
    float i = step(0.01, r) + step(0.02, r) + step(0.03, r) + step(0.10, r) + step(0.17, r) + step(0.23, r)
            + step(0.36, r) + step(0.39, r) + step(0.55, r) + step(0.67, r) + step(0.73, r) + step(0.86, r)
            + step(0.90, r) + step(0.93, r) + step(0.98, r);
    return i;
}

float3 xc_sheet16(float i)
{
    float3 c = float3(0.26, 0.31, 0.37);                                  // 0 slate blue-grey (rare)
    c = lerp(c, float3(0.20, 0.28, 0.40), step(0.5, i));                  // 1 faded blue (rare accent, subdued)
    c = lerp(c, float3(0.38, 0.45, 0.52), step(1.5, i));                  // 2 light blue-grey
    c = lerp(c, float3(0.30, 0.13, 0.10), step(2.5, i));                   // 3 muted brick / maroon
    c = lerp(c, float3(0.34, 0.17, 0.12), step(3.5, i));                   // 4 oxidised faded red
    c = lerp(c, float3(0.26, 0.14, 0.11), step(4.5, i));                   // 5 red-brown
    c = lerp(c, float3(0.27, 0.37, 0.28), step(5.5, i));                  // 6 pale sage green
    c = lerp(c, float3(0.22, 0.33, 0.30), step(6.5, i));                  // 7 grey-teal (desaturated)
    c = lerp(c, float3(0.36, 0.44, 0.37), step(7.5, i));                  // 8 pale green-grey
    c = lerp(c, float3(0.46, 0.47, 0.47), step(8.5, i));                  // 9 galvanised
    c = lerp(c, float3(0.32, 0.33, 0.33), step(9.5, i));                  // 10 weathered galvanised
    c = lerp(c, float3(0.62, 0.62, 0.59), step(10.5, i));                 // 11 off-white
    c = lerp(c, float3(0.55, 0.49, 0.38), step(11.5, i));                 // 12 beige
    c = lerp(c, float3(0.66, 0.64, 0.58), step(12.5, i));                 // 13 cream
    c = lerp(c, float3(0.30, 0.41, 0.39), step(13.5, i));                 // 14 pale grey-teal
    return lerp(c, float3(0.38, 0.28, 0.20), step(14.5, i));              // 15 rusting galvanised
}

// Weathering of a sheet-metal colour: sun fade on up-facing sheets, rust bloom / soot streaks, and
// mismatched patch panels (re-roofed strips) on roofs. p = world xy (m), up = N.z, seed per instance.
// q = patch-strip coordinates (m): (across-strip, along-strip). Painted roofs / walls pass the legacy diagonal
// world frame (x + y, x - y); instanced covers pass their own ridge frame (roofscape v2 step 2).
float3 xc_sheet_weather(float3 c, float2 p, float2 q, float z, float up, float seed, float fwp)
{
    float lum = dot(c, float3(0.3, 0.59, 0.11));
    c = lerp(c, lum.xxx * 1.08, saturate(up) * 0.12);                     // UV-faded tops
    float rust = saturate(xc_fnoise(p * 0.9 + seed * 17.0 + z * 0.3, 1.1, fwp) * 1.6 - 0.55);
    c = lerp(c, c * float3(0.92, 0.72, 0.58) + float3(0.03, 0.01, 0.0), rust * 0.3);
    float soot = xc_fnoise(float2(p.x + p.y, z * 3.0) + seed * 5.0, 0.6, fwp);
    c *= 1.0 - soot * 0.12 * (1.0 - saturate(up));                        // streaky walls
    // patch panels: 0.9 m strips, a few replaced in galvanised or another faded colour
    float2 pc = float2(floor(q.x / 0.9), floor(q.y / 2.4));
    float ph = xc_hash21(pc + seed * 13.0);
    float patch = step(0.9, ph) * saturate(up * 2.0 - 0.6) * xc_detail(fwp, 1.0);
    float3 pcol = lerp(float3(0.45, 0.46, 0.46), xc_sheet16(floor(frac(ph * 7.3) * 16.0)) * 0.95, step(0.95, ph));
    return lerp(c, pcol, patch * 0.85);
}

// Tile / cladding colour families that actually dominate Taipei streets.
float3 xc_tile_palette(float r, float arch)
{
    // walkup / low: 1970s-80s mosaic tile — cream, salmon-beige, pistachio,
    // brick, dusty ochre, grey-white
    float3 old = xc_pick6(r,
        float3(0.62, 0.56, 0.45), float3(0.60, 0.47, 0.41), float3(0.49, 0.53, 0.47),
        float3(0.40, 0.26, 0.19), float3(0.60, 0.52, 0.36), float3(0.63, 0.62, 0.58));
    // huaxia: 45 mm square tile — white, grey, beige, chocolate, two-tone
    float3 mid = xc_pick6(r,
        float3(0.66, 0.65, 0.61), float3(0.52, 0.52, 0.50), float3(0.60, 0.54, 0.45),
        float3(0.36, 0.28, 0.23), float3(0.55, 0.50, 0.46), float3(0.47, 0.48, 0.46));
    // new residential towers: stone / porcelain — warm grey, taupe, sand
    float3 modern = xc_pick4(r,
        float3(0.58, 0.55, 0.50), float3(0.46, 0.43, 0.40), float3(0.66, 0.62, 0.55),
        float3(0.38, 0.38, 0.38));
    float3 c = old;
    c = lerp(c, mid, step(1.5, arch));
    c = lerp(c, modern, step(2.5, arch));
    return c * 0.82;
}

float3 xc_glass_palette(float r)
{
    // Xinyi curtain walls: blue-green, grey-blue, silver, bronze-grey
    return xc_pick4(r,
        float3(0.10, 0.19, 0.20), float3(0.12, 0.15, 0.20),
        float3(0.24, 0.27, 0.29), float3(0.13, 0.12, 0.11));
}

float3 xc_sign_palette(float r)
{
    // shop signage: red, warm yellow, white, blue, green, orange
    return xc_pick6(r,
        float3(0.75, 0.08, 0.06), float3(0.95, 0.72, 0.10), float3(0.92, 0.92, 0.88),
        float3(0.08, 0.28, 0.70), float3(0.08, 0.55, 0.28), float3(0.95, 0.40, 0.06));
}

float3 xc_window_light(float r, float warmBias)
{
    // Taipei homes: many cool-white fluorescent / LED rooms, some warm, a few
    // TV-blue. Offices skew cool-neutral.
    float3 cool = float3(0.70, 0.86, 1.00);
    float3 warm = float3(1.00, 0.60, 0.28);
    float3 neutral = float3(1.00, 0.86, 0.66);
    float3 tv = float3(0.45, 0.60, 1.00);
    float3 c = lerp(cool, neutral, step(0.45 - warmBias * 0.3, r));
    c = lerp(c, warm, step(0.72 - warmBias * 0.3, r));
    return lerp(c, tv, step(0.95, r));
}

// ----------------------------------------------------------------------------
// Schools (ARCH_SCHOOL = 7, School & Campus Identity v0A): Taiwanese reinforced-concrete classroom
// wings. variant = campus palette (one per campus), seed = building group, flags bit4 = wall that faces
// the schoolyard (open-corridor side, baked by build_look_tiles.py). Pale tile / render, restrained
// brick-red / ochre accents, strong floor bands, a regular classroom bay rhythm; the corridor side is a
// parapet, a dark recessed corridor strip and columns. No shop signs, arcades, iron cages, AC rows or
// sheet-metal additions. Every pattern converges to its mean once unresolved (no shimmer).
// ----------------------------------------------------------------------------
void xc_school_wall(float u, float h, float H, float fh, float variant, float seed, float weather, float flags,
                    float night, float litFrac, float fwu, float fwh,
                    out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float corridor = step(0.5, frac(floor(flags * 255.0 / 16.0 + 0.001) * 0.5));   // bit4
    float pal = (variant + 0.5) / 16.0;                                             // campus constant
    float3 wall = xc_pick4(pal, float3(0.63, 0.59, 0.49), float3(0.64, 0.63, 0.59),
                           float3(0.57, 0.58, 0.57), float3(0.63, 0.58, 0.49));
    wall *= 0.95 + 0.08 * frac(seed * 13.7);                       // wing-to-wing tile batch
    float3 accent = xc_pick4(frac(pal * 3.0 + 0.4), float3(0.42, 0.175, 0.125), float3(0.56, 0.39, 0.18),
                             float3(0.47, 0.24, 0.16), float3(0.52, 0.35, 0.19));
    float3 lightC = wall * 1.08 + 0.03;                            // beams / slab edges
    float3 glass = float3(0.22, 0.265, 0.28);                       // classroom glazing: pale, sky-tinted
    float fi = floor(h / fh);
    float fv = frac(h / fh);
    float fwf = fwh / fh;
    float bw = 4.5 * (0.95 + 0.1 * frac(pal * 7.1));               // classroom bay (2 per classroom)
    float bu = u / bw;
    float bi = floor(bu);
    float fu = frac(bu);
    float fwb = fwu / bw;
    float fu2 = frac(bu * 0.5);                                     // classroom (2 bays): corridor columns
    float dFloor = xc_detail(fwh, fh);
    float dBay = xc_detail(fwu, bw);
    float dRoom = xc_detail(fwu, bw * 2.0);
    float upper = step(0.5, fi);
    // floor band: beam + slab edge, the strong horizontal line of a classroom wing
    float band = max(xc_box(fv, 0.86, 1.0, fwf), xc_box(fv, 0.0, 0.035, fwf));
    // --- window side: enclosed classroom wall. Accent sill stripe, one window bay per structural bay
    // between solid piers, a centre mullion, pale glazing (reads lighter than the corridor recess)
    float col = lerp(0.26, 1.0 - xc_box(fu, 0.10, 0.90, fwb), dBay);
    float sill = xc_box(fv, 0.12, 0.25, fwf);
    float winV = xc_box(fv, 0.32, 0.80, fwf);
    float win = winV * lerp(0.74, xc_box(fu, 0.10, 0.90, fwb) * (1.0 - xc_box(fu, 0.475, 0.525, fwb)), dBay);
    float frames = max(xc_line(frac(fu * 4.0), 0.06, fwb * 4.0), xc_box(fv, 0.62, 0.645, fwf)) * win * dBay;
    float3 cw = wall;
    cw = lerp(cw, accent, sill);
    cw = lerp(cw, glass, win);
    cw = lerp(cw, float3(0.60, 0.61, 0.60), frames * 0.85);       // aluminium frames / transom
    cw = lerp(cw, lightC, col * winV * (1.0 - band) * 0.8);       // piers
    cw = lerp(cw, lightC, band);
    float3 mW = lightC * 0.25 + accent * 0.13 + glass * 0.355 + wall * 0.26;
    // --- corridor side: continuous parapet with an accent cap over a deep, dark recessed corridor; one
    // slender column per classroom (not per bay), so the recess reads as an unbroken horizontal band
    float par = xc_box(fv, 0.0, 0.34, fwf) * upper;
    float cap = xc_box(fv, 0.25, 0.34, fwf) * upper;
    float rec = xc_box(fv, 0.0, 0.86, fwf) * (1.0 - par);
    float ccol = lerp(0.05, 1.0 - xc_box(fu2, 0.025, 0.975, fwb * 0.5), dRoom);
    float backWin = xc_box(fu, 0.20, 0.64, fwb) * xc_box(fv, 0.44, 0.78, fwf) * dBay;
    float3 shade = lerp(wall * 0.085, wall * 0.17 + 0.01, backWin * 0.45) * lerp(0.6, 1.0, smoothstep(0.30, 0.80, 1.0 - fv));   // darker under the slab
    float3 cc = wall;
    cc = lerp(cc, shade, rec * (1.0 - ccol));
    cc = lerp(cc, accent, cap);
    cc = lerp(cc, lightC, band);
    float3 mC = lightC * 0.175 + (wall * 0.215 + accent * 0.09) * upper
              + wall * 0.115 * lerp(0.825, 0.525, upper);
    float3 c = lerp(lerp(mW, mC, corridor), lerp(cw, cc, corridor), dFloor);
    // roof parapet: light render with an accent coping, no sheet / signage
    c = lerp(c, lerp(lightC * 0.96, accent, 0.5), step(H - 0.95, h));
    float glassAmt = lerp(0.355, win, dFloor) * (1.0 - corridor);
    // night: schools are mostly dark; a few classrooms / offices and corridor runs stay lit
    float cellR = xc_hash31(float3(floor(bi / 2.0), fi, seed * 97.0));
    float3 fl = float3(0.82, 0.92, 1.0);
    float litW = step(1.0 - litFrac * 0.2, cellR);
    float corrR = xc_hash21(float2(floor(bi / 4.0), fi + seed * 7.0));
    float litC = step(0.86, corrR);
    float3 eN = fl * (win * litW * 0.22 * (1.0 - corridor) + rec * (1.0 - ccol) * litC * 0.12 * corridor);
    float3 eF = fl * lerp(0.355 * litFrac * 0.2 * 0.22, 0.50 * 0.14 * 0.12, corridor);
    // humid weathering: parapet run-off, top grime, splash at the base (no window-sill streaks of the
    // shop-house grid), then the same distance contact ramp as the accepted walls
    float runLen = 3.0 + 16.0 * xc_noise1(u * 0.17 + seed * 7.0);
    float runoff = saturate(xc_noise1(u * 0.45 + seed * 23.0) * 1.8 - 0.8) * smoothstep(H - runLen, H - 0.6, h);
    runoff = lerp(0.05, runoff, xc_detail(fwu, 2.2));
    float streak = saturate(xc_noise1(u * 1.9 + seed * 17.0) * 1.4 - 0.35) * 0.4;
    float grime = saturate((streak * 0.7 + smoothstep(H - 2.5 * fh, H, h) * 0.5
                            + (1.0 - smoothstep(0.0, 1.2, h)) * 0.6 + runoff * 0.8) * weather);
    c *= 1.0 - grime * 0.42;
    float farF = 1.0 - xc_detail(fwh, fh * 4.0);
    float contact = (1.0 - smoothstep(0.0, lerp(4.0, 20.0, farF), h)) * farF;
    float contactNight = (1.0 - smoothstep(0.0, lerp(4.0, 14.0, farF), h)) * farF;
    c = lerp(c * (1.0 - contactNight * 0.65), lerp(c, float3(0.085, 0.095, 0.075), contact * 0.7), 1.0 - night);
    float wear = xc_fnoise(float2(u, h), 0.15, max(fwu, fwh));
    rough = lerp(lerp(0.80, 0.92, grime * 0.5) + (wear - 0.5) * 0.14, 0.12, glassAmt);
    metal = 0.0;
    spec = lerp(0.42, 0.75, glassAmt);
    emis = lerp(eF, eN, dFloor * dBay) * night;
    base = c;
}

// School roofs: bare concrete or green / grey PU waterproofing per wing, ponding stains; never sheet
// metal, no painted equipment grid (real tank / bulkhead props from build_rooftops.py)
void xc_school_roof(float3 wpos, float seed, float weather, float fwp,
                    out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float rs = frac(seed * 3.31 + 0.27);
    float3 roofCol = lerp(float3(0.44, 0.43, 0.41), float3(0.25, 0.37, 0.30), step(0.45, rs));
    roofCol = lerp(roofCol, float3(0.39, 0.42, 0.41), step(0.85, rs));
    float stain = xc_fnoise(p + seed * 37.0, 0.35, fwp);
    float stain2 = xc_fnoise(p - seed * 5.4, 1.3, fwp);
    roofCol *= 1.0 - saturate(stain * 0.9 - 0.25) * 0.35 * weather - stain2 * 0.10;
    base = roofCol;
    rough = 0.9;
    metal = 0.0;
    spec = 0.35;
    emis = float3(0.0, 0.0, 0.0);
}

// ----------------------------------------------------------------------------
// Walls
// ----------------------------------------------------------------------------
// ----------------------------------------------------------------------------
// Taipei Street Reality v0E storefront atlas (tools/lookdev/build_shop_atlas.py, 2048^2, sRGB + emissive A):
//   h4 cells 512 x 128 at y 0..1024 (4 per row): 0-3 convenience, 4-5 breakfast, 6-7 breakfast menu strip,
//      8-13 food, 14-16 beverage, 17-21 pharmacy / clinic, 22-31 neighbourhood retail
//   h2 cells 512 x 256 at y 1024..2048 (4 per row): 0-3 breakfast, 4-5 food, 6-7 pharmacy / clinic, 8-15 retail
// cat: 1 convenience, 2 breakfast, 3 food, 4 beverage, 5 medical, 6 / 7 retail / ordinary, 8 menu strip.
// Returns (origin x, origin y, width, height) in texels; tall = 1 picks h2 where the category has h2 cells.
// ----------------------------------------------------------------------------
float xc_eq(float a, float b)
{
    return 1.0 - step(0.5, abs(a - b));
}

float4 xc_shop_cell(float cat, float sd, float tall)
{
    tall *= 1.0 - xc_eq(cat, 1.0) - xc_eq(cat, 4.0) - xc_eq(cat, 8.0);
    float f4 = 22.0;
    float n4 = 10.0;
    f4 = lerp(f4, 0.0, xc_eq(cat, 1.0));  n4 = lerp(n4, 4.0, xc_eq(cat, 1.0));
    f4 = lerp(f4, 4.0, xc_eq(cat, 2.0));  n4 = lerp(n4, 2.0, xc_eq(cat, 2.0));
    f4 = lerp(f4, 6.0, xc_eq(cat, 8.0));  n4 = lerp(n4, 2.0, xc_eq(cat, 8.0));
    f4 = lerp(f4, 8.0, xc_eq(cat, 3.0));  n4 = lerp(n4, 6.0, xc_eq(cat, 3.0));
    f4 = lerp(f4, 14.0, xc_eq(cat, 4.0)); n4 = lerp(n4, 3.0, xc_eq(cat, 4.0));
    f4 = lerp(f4, 17.0, xc_eq(cat, 5.0)); n4 = lerp(n4, 5.0, xc_eq(cat, 5.0));
    float f2 = 8.0;
    float n2 = 8.0;
    f2 = lerp(f2, 0.0, xc_eq(cat, 2.0));  n2 = lerp(n2, 4.0, xc_eq(cat, 2.0));
    f2 = lerp(f2, 4.0, xc_eq(cat, 3.0));  n2 = lerp(n2, 2.0, xc_eq(cat, 3.0));
    f2 = lerp(f2, 6.0, xc_eq(cat, 5.0));  n2 = lerp(n2, 2.0, xc_eq(cat, 5.0));
    float f = lerp(f4, f2, tall);
    float n = lerp(n4, n2, tall);
    float idx = f + sd - n * floor(sd / n);
    float row = floor(idx / 4.0);
    float col = idx - row * 4.0;
    return float4(col * 512.0, lerp(row * 128.0, 1024.0 + row * 256.0, tall), 512.0, lerp(128.0, 256.0, tall));
}

// One atlas cell fitted into a rectangle (lp: x 0..1 left to right, y 0..1 bottom to top; aspect = width / height).
// The cell keeps its aspect (letterboxed); outside it the board continues in the cell's own margin colour (same
// row, so rims stay continuous). blank = 1 shows only that margin (an empty stretch of a continuous fascia).
// dxy = d(lp.x)/dx, d(lp.x)/dy, d(lp.y)/dx, d(lp.y)/dy: explicit gradients, so this may run inside a branch.
float4 xc_shop_sample(Texture2D tx, SamplerState ss, float4 cell, float2 lp, float aspect, float4 dxy, float blank)
{
    float k = aspect * cell.w / cell.z;
    float kx = max(k, 1.0);
    float ky = max(1.0 / k, 1.0);
    float2 c = float2(0.5 + (lp.x - 0.5) * kx, 0.5 - (lp.y - 0.5) * ky);
    float outX = max(step(c.x, 0.0), step(1.0, c.x));
    float outY = max(step(c.y, 0.0), step(1.0, c.y));
    c.x = lerp(c.x, 0.05, max(outX, blank));
    c = lerp(c, float2(0.05, 0.5), outY);
    float2 uv = (cell.xy + c * cell.zw) / 2048.0;
    float2 gx = float2(dxy.x * kx, -dxy.z * ky) * cell.zw / 2048.0;
    float2 gy = float2(dxy.y * kx, -dxy.w * ky) * cell.zw / 2048.0;
    return tx.SampleGrad(ss, uv, gx, gy);
}

void xc_wall(float u, float h, float H, float fh, float arch, float variant, float seed,
             float weather, float flags, float3 wpos, float night, float litFrac,
             float fwu, float fwh, float4 dUH, float2 tW, float2 nH,
             Texture2D shopTx, SamplerState shopS, Texture2D planTx,
             out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float isOffice = step(3.5, arch) * (1.0 - step(4.5, arch));
    float isCivic = step(5.5, arch);
    float isPodium = step(4.5, arch) * (1.0 - isCivic);
    float isTower = step(2.5, arch) * (1.0 - step(3.5, arch));
    float isOld = 1.0 - step(2.5, arch);            // low / walkup / huaxia
    float core = frac(floor(flags * 255.0 + 0.5) * 0.5) * 2.0;   // bit0
    float podiumPart = step(0.5, frac(floor(flags * 255.0 / 4.0 + 0.001) * 0.5));  // bit2
    float rooftop = step(0.5, frac(floor(flags * 255.0 / 8.0 + 0.001) * 0.5));     // bit3
    // street frontage role (bits 4-6, build_look_tiles.py FRONT_*): 1 rear / side, 2 service alley,
    // 3 / 4 street (local / major road), 5 commercial corner side street, 6 / 7 commercial frontage (local / major).
    // 0 = no frontage contract (far city, landmarks, rooftop-structure records): every frontage term below then
    // reduces exactly to the accepted grammar (lerp(x, y, 0) == x).
    float fA = floor(flags * 255.0 + 0.5);
    float front = floor(fA / 16.0 + 0.001) - 8.0 * floor(fA / 128.0 + 0.001);
    float known = step(0.5, front);
    float fRear = known * (1.0 - step(1.5, front));
    float fStreet = step(2.5, front);                // local+ street (any building)
    float fComm = step(4.5, front);                  // commercial frontage (primary or corner side)
    float fPrim = step(5.5, front);
    float fMajor = step(3.5, front) * (1.0 - step(4.5, front)) + step(6.5, front);
    float isHuaxia = step(1.5, arch) * (1.0 - step(2.5, arch));

    float floorsTotal = max(1.0, floor(H / fh + 0.5));
    float fi = floor(h / fh);
    float fv = frac(h / fh);
    float fromTop = floorsTotal - 1.0 - fi;

    // --- bay rhythm per archetype -------------------------------------------
    float bw = lerp(3.6, 3.1, step(1.5, arch));                 // walkup 3.6 / huaxia 3.1
    bw = lerp(bw, 3.9, isTower);
    bw = lerp(bw, 1.5, isOffice);                               // curtain-wall module
    bw = lerp(bw, 7.5, isPodium);
    bw *= 0.9 + 0.2 * frac(seed * 7.13);
    float bu = u / bw;
    float bi = floor(bu);
    float fu = frac(bu);
    float fwb = fwu / bw;
    float fwf = fwh / fh;
    float dBay = xc_detail(fwu, bw);
    float dFloor = xc_detail(fwh, fh);
    float dFine = xc_detail(fwu, 0.25);

    float cellR = xc_hash31(float3(bi, fi, seed * 97.0));
    float colR = xc_hash21(float2(bi, seed * 53.0));

    // --- wall material -------------------------------------------------------
    float palR = frac(seed * 3.731 + variant * 0.071);
    float3 wall = xc_tile_palette(palR, arch);
    // --- facade finish family (per building constant: no shimmer) ------------------
    // glazed tile (semi-gloss), painted render on ~30 % of old stock (matte, washed pastel),
    // porcelain / stone panels on towers; plus a muted warm / cool cast and +-9 % value
    float finR = frac(seed * 6.17 + variant * 0.113);
    float painted = isOld * step(0.70, finR);
    float3 paint = xc_pick4(frac(finR * 5.3), float3(0.50, 0.53, 0.49), float3(0.58, 0.55, 0.47),
                            float3(0.47, 0.51, 0.54), float3(0.56, 0.48, 0.45));
    wall = lerp(wall, paint * 0.9, painted);
    float3 cast = lerp(float3(1.035, 1.0, 0.95), float3(0.96, 0.99, 1.04), frac(seed * 4.71));
    wall *= (0.91 + 0.18 * frac(seed * 13.7)) * cast;
    float wallRough = lerp(0.58, 0.88, painted);
    wallRough = lerp(wallRough, 0.50, isTower);
    float wallSpec = lerp(0.5, 0.32, painted);
    // office glass family: reflective-coated (tinted mirror) or clear low-E (interior visible)
    float coated = isOffice * step(0.45, frac(seed * 3.97));
    // two-tone huaxia / tower bases (granite-look first floors)
    float baseFloors = lerp(1.0, 2.0, step(0.5, frac(seed * 5.3)));
    float stoneBase = (1.0 - step(baseFloors * fh, h)) * (1.0 - isOffice) * step(1.5, arch);
    wall = lerp(wall, float3(0.30, 0.29, 0.28), stoneBase * 0.8);
    // mosaic tile grain (only resolved near the camera)
    float tileGrain = xc_hash21(floor(float2(u, h) / 0.1)) - 0.5;
    wall *= 1.0 + tileGrain * 0.10 * dFine * isOld;

    // --- column rhythm: a short repeating bay pattern per building ------------
    // (living-room window / bathroom window / balcony / solid pier), so facades
    // read as designed buildings instead of random window noise.
    float P = 2.0 + floor(frac(seed * 11.3) * 3.0);
    float slot = bi - P * floor(bi / P);
    float colT = xc_hash21(float2(slot, seed * 71.0));
    float tBalc = step(lerp(0.78, 0.55, step(1.5, arch)), colT) * (1.0 - isOffice) * (1.0 - isPodium);
    float tNarrow = step(0.60, colT) * (1.0 - tBalc) * isOld;
    float tPier = step(0.52, colT) * (1.0 - step(0.60, colT)) * isOld * step(0.5, frac(seed * 3.1));
    float wx0 = lerp(0.12, 0.16, isTower);
    float wx1 = lerp(0.88, 0.84, isTower);
    float wy0 = lerp(0.30, 0.16, isTower);
    float wy1 = 0.82;
    wx0 = lerp(wx0, 0.36, tNarrow); wx1 = lerp(wx1, 0.64, tNarrow); wy0 = lerp(wy0, 0.46, tNarrow);
    float win = xc_box(fu, wx0, wx1, fwb) * xc_box(fv, wy0, wy1, fwf) * (1.0 - tPier);
    // balcony: recessed bay, solid tiled knee wall, sliding door behind
    float balc = tBalc * xc_box(fv, 0.0, 0.93, fwf) * xc_box(fu, 0.04, 0.96, fwb);
    float knee = balc * (1.0 - step(0.36, fv));
    float door = balc * xc_box(fu, 0.18, 0.82, fwb) * xc_box(fv, 0.36, 0.86, fwf);
    // enclosed balconies (陽台外推) on old stock: aluminium windows at the front
    float enclosed = tBalc * isOld * step(0.45, frac(seed * 9.7 + slot * 0.31));
    win = max(win, max(door, enclosed * balc * step(0.36, fv)));
    // curtain wall: nearly full glass, spandrel at the slab
    float cw = xc_box(fv, 0.14, 0.97, fwf);
    win = lerp(win, cw, isOffice);
    float podGlass = step(0.55, xc_hash21(float2(fi, seed * 11.0))) * xc_box(fv, 0.25, 0.85, fwf);
    win = lerp(win, podGlass, isPodium);
    // aluminium frames + mid mullion on residential windows
    float frameOuter = xc_box(fu, wx0 - 0.03, wx1 + 0.03, fwb) * xc_box(fv, wy0 - 0.03, wy1 + 0.03, fwf) * (1.0 - tPier) * (1.0 - balc);
    float midM = xc_line(frac((fu - wx0) / max(wx1 - wx0, 0.05) + 0.5), 0.04, fwb * 2.0) * win * isOld;
    float frame = saturate(frameOuter - win + midM) * dBay * (1.0 - isOffice) * (1.0 - isPodium);
    // average coverage for far-distance filtering
    float winMean = lerp(0.42, 0.83, isOffice);
    winMean = lerp(winMean, 0.27, isPodium);
    win = lerp(winMean, win, dBay * dFloor);
    balc *= dBay * dFloor;
    knee *= dBay * dFloor;

    // reflective tinted residential glass (green / blue / bronze / clear)
    float3 resGlass = xc_pick4(frac(seed * 2.17 + slot * 0.13),
        float3(0.12, 0.17, 0.16), float3(0.11, 0.13, 0.17), float3(0.14, 0.12, 0.10), float3(0.16, 0.17, 0.17));
    float3 glassCol = lerp(resGlass, xc_glass_palette(frac(seed * 1.37)), isOffice + isTower * 0.3);
    // curtains / blinds behind residential glass
    glassCol = lerp(glassCol, float3(0.45, 0.42, 0.36), step(0.72, cellR) * isOld * 0.5);
    // clear office glass shows the interior: dark floor plate, brighter ceiling band (mean far away)
    float ceilBand = lerp(0.2, smoothstep(0.72, 0.92, fv), dFloor);
    float3 interior = lerp(float3(0.045, 0.047, 0.05), float3(0.13, 0.13, 0.125), ceilBand);
    glassCol = lerp(glassCol, interior, isOffice * (1.0 - coated) * 0.75);

    // --- iron window cages (鐵窗) + AC units — the Taipei signature ------------
    float cageP = lerp(0.62, 0.34, step(1.5, arch));            // walkups most caged
    cageP *= lerp(1.0, 0.45, step(4.0, fi));                     // fewer high up
    cageP *= isOld * (1.0 - core * 0.7);
    cageP *= 1.0 - fRear * 0.2;                                  // rear / side walls: a little less clutter
    float caged = step(1.0 - cageP, frac(cellR * 7.1));
    float barsV = xc_line(frac(u / 0.13), 0.22, fwu / 0.13);
    float barsH = xc_line(frac(h / 0.42), 0.12, fwh / 0.42);
    float cageBars = max(barsV, barsH) * xc_detail(fwu, 0.26);
    float cageMask = caged * xc_box(fu, wx0 - 0.04, wx1 + 0.04, fwb) * xc_box(fv, wy0 - 0.05, wy1 + 0.04, fwf);
    float3 cageCol = lerp(float3(0.62, 0.62, 0.60), float3(0.25, 0.17, 0.12), step(0.6, frac(cellR * 13.7)));
    // far away a cage reads as a lighter, busier window
    float cageCover = lerp(0.45, cageBars, xc_detail(fwu, 0.26)) * cageMask * (1.0 - tPier);

    float acP = lerp(0.55, 0.35, step(1.5, arch)) * (isOld + isTower * 0.5) * (1.0 - isOffice);
    // street / alley walls: condensers hang in fixed columns (same side of the window, a few floors skipped), the
    // regular stacks of a Taipei street front; rear / side walls keep the unorganised scatter at 70 % density
    float acColR = xc_hash21(float2(slot, seed * 37.0));
    float acStackW = known * (1.0 - fRear);
    float acScatter = step(1.0 - acP * (1.0 - fRear * 0.3), frac(cellR * 3.7));
    float acStack = step(1.0 - acP * 1.35, acColR) * step(0.22, frac(cellR * 3.7));
    float hasAC = lerp(acScatter, acStack, acStackW) * step(0.5, fi);
    float acLeft = lerp(step(0.5, frac(cellR * 5.9)), step(0.5, frac(acColR * 5.9)), acStackW);
    float acx0 = lerp(0.60, 0.06, acLeft);
    float ac = hasAC * xc_box(fu, acx0, acx0 + 0.24, fwb) * xc_box(fv, 0.05, 0.25, fwf) * dBay;
    float acGrille = xc_line(frac(u / 0.05), 0.3, fwu / 0.05) * xc_detail(fwu, 0.1);
    float3 acCol = lerp(float3(0.74, 0.72, 0.66), float3(0.34, 0.34, 0.33), acGrille * 0.6);

    // --- floor slabs / balcony edges / curtain-wall mullions ------------------
    float slab = xc_box(fv, 0.0, lerp(0.07, 0.10, isTower), fwf) * dFloor;
    float mull = xc_line(fu, 0.05, fwb) * isOffice * dBay;
    float spandrel = (1.0 - xc_box(fv, 0.14, 0.97, fwf)) * isOffice * dFloor;

    // --- street level: 騎樓 arcade + shopfronts + signage band ------------------
    // Frontage-aware: shopfronts only on commercial frontage (primary + corner side street); sign density follows
    // the role (major commercial road > local > corner side > plain street > alley > none on rear / side walls),
    // huaxia answers a step weaker than walk-up / low shop-houses.
    float street = (1.0 - step(fh * 1.05, h)) * (1.0 - podiumPart * 0.0);
    float arcade = 0.0;
    float signBand = 0.0;
    float hasSign = 0.0;
    float signR = 1.0;
    float signCell = 0.0;
    float shutter = 1.0;
    float3 shop = float3(0.0, 0.0, 0.0);
    float3 signFace = float3(0.0, 0.0, 0.0);
    float3 storeE = float3(0.0, 0.0, 0.0);      // night glow of the shopfront (x arcade in the night block)
    float3 signE = float3(0.0, 0.0, 0.0);       // night glow of the board (x signBand * hasSign)
    float3 dayE = float3(0.0, 0.0, 0.0);        // daytime interior glow (convenience store / clinic, x arcade)
    // Everything shopfront / arcade / sign-board lives in the bottom 1.72 floors (signTop <= 1.72): above that every
    // mask below is exactly 0, so those pixels skip the work (coherent per floor band).
    [branch] if (h < fh * 1.72)
    {
    arcade = street * isOld * (1.0 - core * 0.6) * lerp(1.0, fComm, known);
    float signTop = lerp(1.55, 1.72, known * fPrim * fMajor);     // taller sign boards on major commercial roads
    signBand = step(fh * 1.02, h) * (1.0 - step(fh * signTop, h)) * isOld * (1.0 - core * 0.8);
    // one board grid per building (3.1-6.2 m boards, Taipei Street Reality v0E): atlas text never jumps at a bay line
    float signW = bw * lerp(1.0, 1.6, frac(seed * 5.71));
    signCell = floor(u / signW);
    signR = xc_hash21(float2(signCell, seed * 29.0));
    float signThr = 1.01;                                         // rear / side: none
    signThr = lerp(signThr, 0.92, step(1.5, front));             // service alley
    signThr = lerp(signThr, 0.85, fStreet);                       // street wall of a non-commercial building
    signThr = lerp(signThr, 0.60, fComm);                         // corner side street
    signThr = lerp(signThr, 0.35, fPrim);                         // commercial frontage
    signThr = lerp(signThr, 0.22, fPrim * fMajor);                // ... on a collector / arterial
    signThr += 0.1 * isHuaxia * fComm;
    hasSign = step(lerp(0.35, signThr, known), signR);
    float bandH = max((signTop - 1.02) * fh, 0.3);
    float sv = (h - fh * 1.02) / bandH;
    float bx = frac(u / signW);
    float boardEdge = (1.0 - xc_box(bx, 0.012, 0.988, fwu / signW)) * xc_detail(fwu, 0.5);
    float boardGrime = saturate(1.0 - sv) * frac(signR * 5.3) * 0.14 * xc_detail(fwh, 0.4);

    // storefront plan (build_storefronts.py): one texel fetch at this board's centre, 1.4 m out from the wall, on
    // old-stock commercial frontage only. 0 = no plan (boards there show neighbourhood-retail atlas cells).
    float pv = 0.0;
    [branch] if (isOld * known * fComm > 0.0)
    {
        float2 pc = wpos.xy + tW * ((signCell + 0.5) * signW - u) + nH * 1.4;
        int2 tp = int2(floor((pc.x - XC_PLAN_E0) / XC_PLAN_PX), floor((pc.y + XC_PLAN_N1) / XC_PLAN_PX));
        if (tp.x >= 0 && tp.y >= 0 && tp.x < XC_PLAN_RES && tp.y < XC_PLAN_RES)
            pv = floor(planTx.Load(int3(tp, 0)).r * 255.0 + 0.5);
    }
    float cat = floor(pv / 32.0);
    float plan = step(0.5, cat);
    float plit = step(0.5, frac(floor(pv / 16.0) * 0.5));
    float pseed = pv - 16.0 * floor(pv / 16.0);
    float isCvs = xc_eq(cat, 1.0);
    float isBf = xc_eq(cat, 2.0);
    float isFood = xc_eq(cat, 3.0);
    float isBev = xc_eq(cat, 4.0);
    float isMed = xc_eq(cat, 5.0);
    float special = isCvs + isBf + isFood + isBev + isMed;
    hasSign = max(hasSign, special);
    hasSign *= 1.0 - isCvs * step(0.55, sv);                    // convenience store: a ~1 m fascia, wall above
    float sCat = lerp(6.0, cat, plan);
    float sSeed = lerp(floor(signR * 16.0), pseed, plan);
    float gv = h / (fh * 1.05);
    float inMenu = isBf * street * step(0.60, gv) * (1.0 - step(0.80, gv)) * (1.0 - step(0.5, night));
    // light-box boards: most are lit at night even where the shop below has its shutter down
    float boardLit = lerp(step(0.2, signR), max(plit, step(0.35, frac(signR * 3.3))), plan);

    // one atlas sample: the shop board in the sign band, or the breakfast menu strip above the counter
    float4 stx = float4(0.0, 0.0, 0.0, 0.0);
    [branch] if (signBand * hasSign + inMenu > 0.0)
    {
        float4 sCell = xc_shop_cell(lerp(sCat, 8.0, inMenu), sSeed, step(signW / bandH, 2.8));
        float rectH = lerp(bandH * lerp(1.0, 0.55, isCvs), 0.20 * fh * 1.05, inMenu);
        float ly = lerp(sv / lerp(1.0, 0.55, isCvs), (gv - 0.60) / 0.20, inMenu);
        float blank = isCvs * step(0.5, xc_hash21(float2(signCell, seed * 17.0))) * (1.0 - inMenu);
        stx = xc_shop_sample(shopTx, shopS, sCell, float2(bx, ly), signW / rectH,
                             float4(dUH.x / signW, dUH.y / signW, dUH.z / rectH, dUH.w / rectH), blank);
    }
    // board face: atlas, sun-faded / yellowed with age, grime toward the bottom, dark rim (convenience stores: one
    // continuous fascia, no rim between boards)
    float sAge = frac(signR * 7.7) * (1.0 - isCvs * 0.7);
    float3 face = stx.rgb;
    face = lerp(face, dot(face, float3(0.3, 0.59, 0.11)) * float3(1.04, 1.0, 0.9), sAge * 0.35) * (1.0 - sAge * 0.15);
    face *= 1.0 - boardGrime;
    signFace = lerp(face, float3(0.12, 0.12, 0.12), boardEdge * 0.8 * known * (1.0 - isCvs));
    signE = face * stx.a * boardLit * lerp(2.0, 1.1, isCvs);

    // shopfront behind the arcade, per category. Open shops show a lived-in interior (goods on shelves, a lit ceiling
    // strip, dark floor) that averages to its mean once the 0.5 m cells are sub-pixel; closed ones a rolling shutter.
    shutter = step(lerp(0.55, lerp(0.55, 0.72, fPrim), known), xc_hash21(float2(signCell, 3.0)));
    float bfClosed = isBf * step(0.5, night);                   // breakfast shops close by early afternoon
    shutter = lerp(shutter, bfClosed, special);
    float fgv = fwh / (fh * 1.05);
    float dGoods = xc_detail(fwu, 0.55);
    float gq = xc_hash21(float2(floor(u / 0.55), floor(gv / 0.16) + seed * 3.0));
    float3 goodsC = xc_pick4(gq, float3(0.52, 0.20, 0.15), float3(0.20, 0.30, 0.48), float3(0.58, 0.50, 0.30),
                             float3(0.28, 0.42, 0.28)) * 0.6 + 0.12;
    goodsC = lerp(float3(0.33, 0.28, 0.22), goodsC, dGoods);
    float shelf = xc_line(frac(gv / 0.16), 0.20, fgv / 0.16) * step(0.10, gv) * (1.0 - step(0.76, gv)) * dGoods;
    float3 inter = lerp(goodsC, float3(0.20, 0.19, 0.18), shelf);
    inter = lerp(inter, float3(0.66, 0.64, 0.58), step(0.82, gv));                     // lit ceiling strip
    inter = lerp(inter, float3(0.14, 0.13, 0.12), 1.0 - step(0.08, gv));              // floor / threshold
    float3 rollC = float3(0.42, 0.42, 0.42) * (1.0 - xc_line(frac(gv / 0.035), 0.3, fgv / 0.035) * xc_detail(fwh, 0.07) * 0.25);
    float openLit = lerp(step(0.25, signR), plit, plan);
    // ordinary / retail: dim interior seen from the street (commercial front a little brighter)
    shop = lerp(inter * lerp(0.45, 0.62, known * fComm), rollC, shutter);
    float3 warmL = lerp(float3(1.0, 0.80, 0.55), float3(0.92, 0.96, 1.0), step(0.6, signR));
    storeE = warmL * (inter * 0.9 + 0.12) * (1.0 - shutter) * openLit;
    float3 storeDay = float3(0.0, 0.0, 0.0);
    [branch] if (special * (1.0 - bfClosed) > 0.0)
    {
        // one category per unit: only its own grammar is evaluated
        float3 sp;
        float3 eC;
        [branch] if (isCvs > 0.5)
        {
            // convenience store: bright cool interior, goods on shelves, lit ceiling, a few posters on the glass,
            // dark aluminium mullions every 1.5 m, kick plate
            float sMull = xc_line(frac(u / 1.5), 0.035, fwu / 1.5);
            sp = lerp(float3(0.60, 0.62, 0.62), inter * 1.25 + 0.08, step(0.10, gv) * (1.0 - step(0.76, gv)));
            sp = lerp(sp, float3(0.88, 0.89, 0.88), step(0.82, gv));
            float pU = floor(u / 3.0);
            float poster = xc_box(frac(u / 3.0), 0.12, 0.42, fwu / 3.0) * xc_box(gv, 0.52, 0.74, fgv)
                         * step(0.55, xc_hash21(float2(pU, seed * 3.0)));
            sp = lerp(sp, xc_pick4(xc_hash21(float2(pU, seed * 5.0)), float3(0.50, 0.10, 0.08), float3(0.08, 0.20, 0.45),
                                   float3(0.62, 0.48, 0.10), float3(0.10, 0.38, 0.22)), poster);
            sp = lerp(sp, float3(0.10, 0.11, 0.12), max(sMull * xc_detail(fwu, 0.4), 1.0 - step(0.05, gv)) * 0.9);
            eC = float3(0.92, 0.97, 1.0) * 0.85;
        }
        else if (isBf > 0.5)
        {
            // breakfast: warm interior, stainless counter with the griddle edge, menu strip (atlas) above the counter
            sp = lerp(float3(0.42, 0.36, 0.27), inter * 1.1, 0.35);
            sp = lerp(sp, float3(0.52, 0.53, 0.54), 1.0 - step(0.32, gv));
            sp = lerp(sp, float3(0.10, 0.10, 0.10), xc_box(gv, 0.30, 0.335, fgv));
            sp = lerp(sp, stx.rgb, inMenu);
            sp = lerp(sp, float3(0.30, 0.28, 0.25), step(0.86, gv));
            eC = float3(0.0, 0.0, 0.0);
        }
        else if (isFood > 0.5)
        {
            // noodle / bento / local food: darker warm interior, stainless counter, white tile wall with red menu tags
            sp = float3(0.30, 0.23, 0.16);
            sp = lerp(sp, float3(0.58, 0.57, 0.53), step(0.55, gv) * (1.0 - step(0.92, gv)));
            sp = lerp(sp, float3(0.45, 0.08, 0.06), xc_box(frac(u / 0.7), 0.1, 0.9, fwu / 0.7) * xc_box(gv, 0.68, 0.80, fgv));
            sp = lerp(sp, float3(0.50, 0.51, 0.52), 1.0 - step(0.30, gv));
            eC = float3(1.0, 0.75, 0.45) * 0.6;
        }
        else if (isBev > 0.5)
        {
            // beverage: bright counter, colourful menu panel band
            sp = inter * 0.9;
            sp = lerp(sp, xc_pick4(frac(floor(u / 0.9) * 0.37 + seed), float3(0.10, 0.45, 0.45), float3(0.70, 0.35, 0.10),
                                   float3(0.20, 0.50, 0.20), float3(0.70, 0.30, 0.40)),
                      xc_box(gv, 0.62, 0.85, fgv) * xc_box(frac(u / 0.9), 0.06, 0.94, fwu / 0.9));
            sp = lerp(sp, float3(0.62, 0.62, 0.58), 1.0 - step(0.38, gv));
            eC = float3(1.0, 0.90, 0.75) * 0.65;
        }
        else
        {
            // pharmacy / clinic: enclosed clean glazing, frosted lower film, aluminium mullions
            sp = lerp(float3(0.55, 0.58, 0.58), inter * 1.1 + 0.1, 0.3);
            sp = lerp(sp, float3(0.70, 0.72, 0.72), 1.0 - step(0.35, gv));
            sp = lerp(sp, float3(0.30, 0.31, 0.32), xc_line(frac(u / 1.2), 0.04, fwu / 1.2) * xc_detail(fwu, 0.3));
            eC = float3(0.88, 0.95, 1.0) * 0.6;
        }
        shop = sp;
        storeE = eC * lerp(plit, 1.0, isCvs) * shop;
        storeDay = shop * float3(0.92, 0.97, 1.0) * (0.30 * isCvs + 0.10 * isMed);       // lit interior by day
    }
    shop = lerp(shop, wall * 0.9, (1.0 - xc_box(fu, 0.06, 0.94, fwb)) * dBay * known);
    dayE = storeDay;
    }

    // --- compose base colour ------------------------------------------------------
    float3 c = wall;
    c = lerp(c, wall * 0.35, balc * (1.0 - win));               // balcony recess shade
    c = lerp(c, wall * 0.9, knee);                               // tiled knee wall
    c = lerp(c, glassCol, win);
    c = lerp(c, float3(0.62, 0.63, 0.62), frame * 0.9);          // aluminium frames
    // piers between bays: slightly different tile tone
    c *= 1.0 - tPier * 0.08;
    c = lerp(c, cageCol, cageCover * 0.85);
    c = lerp(c, acCol, ac);
    c = lerp(c, wall * 1.12 + 0.03, slab * (isTower + step(1.5, arch) * 0.6) * (1.0 - isOffice));
    c = lerp(c, float3(0.70, 0.72, 0.72), mull * 0.85);
    c = lerp(c, lerp(xc_glass_palette(frac(seed * 1.37)) * 0.6, float3(0.10, 0.10, 0.11), 0.5), spandrel);
    // arcade: deep shade with shop glow; rolling shutters on some bays
    // commercial frontage: fewer closed shutters on the primary front, a faintly lit shop interior and a tiled
    // 騎樓 pier at every bay line
    c = lerp(c, shop, arcade * 0.92);
    c = lerp(c, signFace, signBand * hasSign);

    // quiet ground floor: old stock on a known non-commercial wall (rear / side, alley, residential street) gets
    // scooter-garage roll-up shutters and steel doors toward the street / alley, small high barred windows and a rare
    // back door on rear / side walls, over a darker tiled plinth. Per-building-coherent branch (ground floor only).
    float gfQuiet = street * isOld * known * (1.0 - fComm);
    [branch] if (gfQuiet > 0.0)
    {
        float gR = xc_hash21(float2(bi, seed * 41.0));
        float onSt = 1.0 - fRear;
        float roll = step(gR, 0.40) * onSt;
        float door = step(lerp(0.88, 0.40, onSt), gR) * step(gR, lerp(1.01, 0.62, onSt));
        float rollM = roll * xc_box(fu, 0.07, 0.93, fwb) * xc_box(fv, 0.0, 0.82, fwf);
        float doorM = door * xc_box(fu, 0.30, 0.64, fwb) * xc_box(fv, 0.0, 0.74, fwf);
        float winM = (1.0 - roll) * (1.0 - door) * xc_box(fu, 0.30, 0.70, fwb) * xc_box(fv, 0.50, 0.80, fwf);
        float gRib = xc_line(frac(h / 0.09), 0.35, fwh / 0.09) * xc_detail(fwh, 0.18);
        float3 rollC = lerp(float3(0.50, 0.51, 0.50), float3(0.36, 0.37, 0.37), gRib * 0.5) * (0.8 + 0.2 * frac(gR * 7.3));
        float3 doorC = lerp(float3(0.17, 0.16, 0.15), float3(0.30, 0.13, 0.10), step(0.5, frac(gR * 13.1)));
        float3 gq = wall * lerp(0.84, 1.0, step(0.12, fv));
        gq = lerp(gq, rollC, rollM);
        gq = lerp(gq, doorC, doorM);
        gq = lerp(gq, lerp(glassCol * 0.7, cageCol, cageBars * 0.8), winM);
        // far: area-weighted mean of the same features (no shimmer)
        float rc = 0.28 * onSt;
        float dc = lerp(0.03, 0.055, onSt);
        float wc = lerp(0.106, 0.046, onSt);
        float3 gMean = wall * 0.95 * (1.0 - rc - dc - wc) + float3(0.43, 0.44, 0.43) * rc
                     + float3(0.22, 0.15, 0.13) * dc + glassCol * 0.6 * wc;
        c = lerp(c, lerp(gMean, gq, dBay * dFloor), gfQuiet);
    }
    // residential towers on a street: a glazed entrance lobby across the ground floor (rear / side walls keep the
    // accepted stone base); office / civic / podium facades get no street treatment here
    float lobby = isTower * fStreet * street;
    float lobGlass = lerp(0.62, xc_box(fu, 0.10, 0.90, fwb) * xc_box(fv, 0.06, 0.88, fwf), dBay * dFloor) * lobby;
    c = lerp(c, float3(0.085, 0.09, 0.09), lobGlass);
    // the replaced ground floors carry no residential window frames into the material response / sill streaks
    float gfMask = 1.0 - max(gfQuiet, lobby);
    frame *= gfMask;

    // metal-sheet rooftop additions (頂樓加蓋) on small rooftop records
    float ribs = xc_line(frac(u / 0.2), 0.3, fwu / 0.2) * xc_detail(fwu, 0.4);
    // only surveyed rooftop records pay for the palette / weathering (branch: most wall pixels skip it)
    [branch] if (rooftop * isOld > 0.0)
    {
        float3 sheet = xc_sheet16(xc_sheet_paint_index(frac(seed * 2.9 + variant * 0.13), frac(seed * 4.7)));
        sheet = xc_sheet_weather(sheet, wpos.xy, float2(wpos.x + wpos.y, wpos.x - wpos.y), wpos.z, 0.0, seed, max(fwu, fwh));
        c = lerp(c, sheet * (1.0 - ribs * 0.25), rooftop * isOld);
    }

    // parapet cap: light concrete band at the roof line
    float parapet = step(H - 0.45, h) * (1.0 - isOffice);
    c = lerp(c, float3(0.58, 0.57, 0.54), parapet * 0.8);

    // --- humid weathering: sill streaks, top grime, splash at the base -------
    float streakN = xc_noise1(u * 1.9 + seed * 17.0);
    float underSill = (1.0 - smoothstep(0.0, wy0, fv)) * xc_box(fu, wx0, wx1, fwb) * dBay * gfMask;
    float streak = saturate(streakN * 1.4 - 0.35) * (0.4 + 0.6 * underSill);
    float topGrime = smoothstep(H - 2.5 * fh, H, h) * 0.5;
    float splash = 1.0 - smoothstep(0.0, 1.2, h);
    // parapet run-off: sparse vertical rain streaks of varying length below the roof line,
    // a faint average darkening once their ~2 m spacing is sub-pixel
    float runLen = 3.0 + 16.0 * xc_noise1(u * 0.17 + seed * 7.0);
    float runoff = saturate(xc_noise1(u * 0.45 + seed * 23.0) * 1.8 - 0.8) * smoothstep(H - runLen, H - 0.6, h);
    runoff = lerp(0.05, runoff, xc_detail(fwu, 2.2));
    // rear / side / alley walls are the unmaintained back of house: heavier streaks and humid cast
    float backW = known * (1.0 - fStreet);
    float grime = saturate((streak * 0.7 + topGrime + splash * 0.6 + runoff * 0.8) * weather * (1.0 + 0.18 * backW));
    grime *= 1.0 - isOffice * 0.8;
    c *= 1.0 - grime * 0.42;
    c = lerp(c, c * float3(0.92, 0.95, 0.92), weather * 0.5 * isOld * (1.0 + 0.6 * backW));   // green-grey humid cast
    // distance contact: at aircraft range a block keeps no arcade / splash detail at its foot, so a
    // short occlusion ramp grounds it into the floor. Gated on a ~4-floor period (on from mid range,
    // where single floors may still resolve) and off up close, so near Xinyi facades are unchanged.
    float farF = 1.0 - xc_detail(fwh, fh * 4.0);
    // Taller at range (far-city boxes on slopes expose their downhill base) and tinted toward
    // shaded ground rather than black, so the foot reads as terrain / street shade, not a seam.
    float contact = (1.0 - smoothstep(0.0, lerp(4.0, 20.0, farF), h)) * farF;
    // Night keeps the previous short multiply: the real-time SkyLight captures distant geometry as
    // night ambient, and the deeper tinted base measurably dimmed the night mountain silhouettes.
    float contactNight = (1.0 - smoothstep(0.0, lerp(4.0, 14.0, farF), h)) * farF;
    c = lerp(c * (1.0 - contactNight * 0.65), lerp(c, float3(0.085, 0.095, 0.075), contact * 0.7), 1.0 - night);

    // --- material response ------------------------------------------------------
    // Glass is dielectric (F0 ~0.06-0.08 via Specular); only coated curtain wall gets a little
    // metallic tint. Residential float glass is slightly hazy and varies per pane near the camera.
    float glassAmt = win * (1.0 - cageCover * 0.7) * (1.0 - arcade) * (1.0 - gfQuiet);
    glassAmt = lerp(glassAmt, 1.0, lobGlass);
    float paneRough = lerp(0.13, 0.08 + 0.12 * frac(cellR * 41.0), dBay * dFloor);
    float glassRough = lerp(paneRough, lerp(0.07, 0.035, coated), isOffice);
    // low-frequency wear (~7 m blotches, filtered to its mean at distance) and matte grime
    float wear = xc_fnoise(float2(u, h), 0.15, max(fwu, fwh));
    float wr = lerp(wallRough, 0.92, grime * 0.5) + (wear - 0.5) * 0.14;
    rough = lerp(wr, glassRough, glassAmt);
    rough = lerp(rough, 0.55, ac);
    rough = lerp(rough, 0.35, frame);
    metal = mull * 0.9 + ac * 0.1 + frame * 0.6 + glassAmt * coated * 0.3;
    spec = lerp(wallSpec, lerp(0.75, 1.0, coated), glassAmt);

    // --- night -------------------------------------------------------------------
    // Night == 0 is a global (material parameter collection) value: the whole emissive block is skipped by day
    float3 e = float3(0.0, 0.0, 0.0);
    [branch] if (night > 0.0)
    {
    float litP = litFrac * lerp(1.0, 0.6, isOffice);
    litP *= 1.0 - step(0.5, rooftop) * 0.6;
    float floorZone = lerp(xc_hash21(float2(fi, seed * 5.0)), xc_hash31(float3(floor(bi / 8.0), fi, seed * 5.0)), 0.35);   // office floors lit as bands
    float litR = lerp(cellR, floorZone, isOffice);
    float lit = step(1.0 - litP, litR);
    float curtain = lerp(0.55 + 0.45 * frac(cellR * 23.0), 0.15 + 0.85 * frac(cellR * 31.0), step(0.5, isOld + isTower));
    float3 lightCol = xc_window_light(frac(cellR * 17.3), isOffice * 0.2 + isPodium);
    float winLight = win * (1.0 - cageCover * 0.5) * (1.0 - arcade) * (1.0 - balc * 0.5) * (1.0 - gfQuiet) * (1.0 - lobby);
    // far distance: average lit coverage instead of per-window noise
    float litMean = litP * winMean * lerp(0.8, 0.45, isOffice);
    float bandLit = step(1.0 - litP, xc_hash21(float2(fi, seed * 5.0))) * winMean;
    float farLit = lerp(litMean, bandLit * 0.7, isOffice * dFloor);
    float winEmis = lerp(farLit, lit * winLight * curtain, dBay * dFloor);
    e = lightCol * winEmis * lerp(0.24, 0.30, isOffice);
    // shopfronts and signs carry the street at night
    // shopfronts and shop boards (v0E storefront plan): per-category glow from the street band; many stay dark
    e += storeE * arcade;
    e += signE * signBand * hasSign;
    // podium LED / logo panels (department stores)
    float led = isPodium * step(0.7, xc_hash21(float2(floor(u / 18.0), seed * 3.0))) * xc_box(fv, 0.15, 0.9, fwf)
              * step(fh * 1.5, h) * lerp(1.0, fStreet, known);           // street-facing walls only
    e += xc_sign_palette(frac(seed * 4.1 + floor(u / 18.0) * 0.37)) * led * 0.9;
    e += float3(1.0, 0.86, 0.64) * lobGlass * 0.3;                          // lit tower lobbies
    // tower crowns: a lit band under the parapet on some towers
    float crown = step(H - fh * 0.9, h) * (1.0 - step(H - 0.5, h)) * step(0.78, frac(seed * 8.3)) * (isTower + isOffice);
    e += float3(0.95, 0.95, 1.0) * crown * 0.45;
    }
    // --- civic landmarks (registry-driven): stone walls, deep piers, tall windows
    float cbu = u / 4.2;
    float cfu = frac(cbu);
    float cfw = fwu / 4.2;
    float cWin = xc_box(cfu, 0.30, 0.70, cfw) * xc_box(fv, 0.16, 0.86, fwf);
    float cPier = 1.0 - xc_box(cfu, 0.18, 0.82, cfw);
    float3 stone = lerp(float3(0.52, 0.50, 0.46), float3(0.70, 0.66, 0.56), step(14.5, variant));
    float domeV = step(13.5, variant) * (1.0 - step(14.5, variant));      // Taipei Dome: white panels
    stone = lerp(stone, float3(0.74, 0.75, 0.76), domeV);
    float3 civ = lerp(stone * 0.55, stone, cPier * 0.6 + 0.4);
    civ = lerp(civ, float3(0.06, 0.065, 0.07), cWin * dBay);
    civ = lerp(civ, lerp(stone * 0.55, stone, 0.64) * (1.0 - 0.28 * 0.16), (1.0 - dBay));
    civ *= 1.0 - grime * 0.2;
    c = lerp(c, civ, isCivic);
    rough = lerp(rough, lerp(0.75, 0.2, cWin * dBay), isCivic);
    metal = lerp(metal, 0.0, isCivic);
    spec = lerp(spec, 0.5, isCivic);
    float3 civE = float3(1.0, 0.8, 0.55) * (cWin * 0.25 * step(0.5, cellR) + 0.06) * dBay
                + float3(1.0, 0.82, 0.6) * 0.05 * (1.0 - dBay);
    e = lerp(e, civE + stone * 0.10, isCivic);            // warm floodlit stone at night

    emis = e * night + dayE * arcade * (1.0 - night);
    base = c;
}

// ----------------------------------------------------------------------------
// Roofs — the largest visible surface from an aircraft.
// ----------------------------------------------------------------------------
void xc_roof(float3 wpos, float H, float arch, float variant, float seed, float weather,
             float flags, float night, float fwp,
             out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float isOld = 1.0 - step(2.5, arch);
    float isOffice = step(3.5, arch) * (1.0 - step(4.5, arch));
    float rooftop = step(0.5, frac(floor(flags * 255.0 / 8.0 + 0.001) * 0.5));
    float r = frac(seed * 5.77 + variant * 0.061);

    // Taipei roof finishes: bare concrete, green / grey-green waterproof coat,
    // terracotta-tile pavers, metal-sheet additions (blue / white / rust)
    float3 concrete = float3(0.43, 0.42, 0.40);
    float3 greenCoat = float3(0.26, 0.40, 0.31);
    float3 greyCoat = float3(0.38, 0.43, 0.42);
    float3 paver = float3(0.47, 0.33, 0.27);
    float3 roofCol = xc_pick4(r, concrete, greenCoat, greyCoat, lerp(concrete, paver, 0.5));
    roofCol = lerp(roofCol, float3(0.30, 0.31, 0.32), isOffice * 0.7);  // tower roofs: dark membrane

    // painted sheet roofs (surveyed rooftop records, some old roofs): the shared rooftop palette, so the
    // far read matches the instanced 頂樓加蓋 rooms
    float sheetRoof = max(rooftop, step(0.72, frac(seed * 1.9)) * isOld);
    [branch] if (sheetRoof > 0.0)        // per-building constant: coherent branch
    {
        float3 sheet = xc_sheet16(xc_sheet_paint_index(frac(seed * 2.9 + variant * 0.13), frac(seed * 4.7)));
        sheet = xc_sheet_weather(sheet, p, float2(p.x + p.y, p.x - p.y), wpos.z, 1.0, seed, fwp);
        float ribs = xc_line(frac(p.x / 0.25), 0.3, fwp / 0.25) * xc_detail(fwp, 0.5);
        roofCol = lerp(roofCol, sheet * (1.0 - ribs * 0.3), sheetRoof);
    }

    // ponding stains + soot
    float stain = xc_fnoise(p + seed * 37.0, 0.35, fwp);
    float stain2 = xc_fnoise(p - seed * 5.4, 1.3, fwp);
    roofCol *= 1.0 - saturate(stain * 0.9 - 0.25) * 0.35 * weather - stain2 * 0.10;

    // per-building rotated frame: no world-axis alignment on flat roofs
    float ra = frac(seed * 7.13) * 1.5708;
    float2 rp = float2(p.x * cos(ra) + p.y * sin(ra), -p.x * sin(ra) + p.y * cos(ra));

    // flat concrete: a few large resurfacing / repair patches (11 m cells, ~1 in 4 holds one) and a broad stain.
    // Mid-frequency only (4-8 m shapes, 9 m fade scale), so it survives ~150-800 m and dissolves with distance.
    float2 pcell = floor(rp / 11.0);
    float2 pf = frac(rp / 11.0);
    float ph1 = xc_hash21(pcell + seed * 3.7);
    float ph2 = xc_hash21(pcell + seed * 9.1 + 41.0);
    float2 pa = 0.08 + 0.22 * float2(frac(ph1 * 17.0), frac(ph1 * 29.0));
    float2 pb = pa + 0.42 + 0.30 * float2(frac(ph2 * 13.0), frac(ph2 * 31.0));
    float patchBox = xc_box(pf.x, pa.x, min(pb.x, 0.97), fwp / 11.0) * xc_box(pf.y, pa.y, min(pb.y, 0.97), fwp / 11.0);
    float cw = (1.0 - sheetRoof) * (1.0 - isOffice) * xc_detail(fwp, 9.0);
    float patchOn = step(0.76, ph1) * patchBox * cw;
    roofCol = lerp(roofCol, roofCol * lerp(0.84, 1.14, step(0.5, ph2)) + lerp(0.0, 0.01, step(0.5, ph2)), patchOn * 0.8);
    float broad = xc_fnoise(rp + seed * 11.0, 7.0, fwp);
    roofCol *= 1.0 - saturate(broad * 1.2 - 0.4) * 0.16 * weather * cw;

    // equipment clutter read (tanks, condensers, solar heaters) on a sparse rotated 4 m grid,
    // with a fake sun-side shadow; resolves only when close enough
    float2 cell = floor(rp / 4.0);
    float2 fp = frac(rp / 4.0);
    float cr = xc_hash21(cell + seed * 3.0);
    float has = step(0.88, cr) * (1.0 - sheetRoof * 0.6);
    float2 cc = float2(0.25 + 0.5 * frac(cr * 7.0), 0.25 + 0.5 * frac(cr * 13.0));
    float box = xc_box(fp.x, cc.x - 0.12, cc.x + 0.12, fwp / 4.0) * xc_box(fp.y, cc.y - 0.09, cc.y + 0.09, fwp / 4.0);
    float2 sh = fp - float2(0.05, -0.05);
    float shadow = xc_box(sh.x, cc.x - 0.12, cc.x + 0.12, fwp / 4.0) * xc_box(sh.y, cc.y - 0.09, cc.y + 0.09, fwp / 4.0);
    float dCl = xc_detail(fwp, 1.0);
    float3 equip = lerp(float3(0.72, 0.72, 0.70), float3(0.55, 0.57, 0.60), step(0.8, cr));
    roofCol = lerp(roofCol, roofCol * 0.55, shadow * has * dCl * (1.0 - box));
    roofCol = lerp(roofCol, equip, box * has * dCl);

    float isCivic = step(5.5, arch);
    float imperial = isCivic * step(14.5, variant);
    float tileRows = xc_line(frac(wpos.z / 0.33), 0.25, max(fwidth(wpos.z), 1e-4) / 0.33) * xc_detail(max(fwidth(wpos.z), 1e-4), 0.66);
    // Sun Yat-sen Memorial Hall glazed tile: weathered golden, not lemon (0.74/0.52/0.12 read as
    // flat saturated yellow from the air)
    float3 glazed = float3(0.60, 0.46, 0.21) * (1.0 - tileRows * 0.35);
    roofCol = lerp(roofCol, float3(0.42, 0.41, 0.39), isCivic * (1.0 - imperial));
    roofCol = lerp(roofCol, glazed, imperial);
    float domeRoof = isCivic * step(13.5, variant) * (1.0 - step(14.5, variant));
    float panel = max(xc_line(frac(p.x / 6.0), 0.04, fwp / 6.0), xc_line(frac(p.y / 6.0), 0.04, fwp / 6.0)) * xc_detail(fwp, 12.0);
    roofCol = lerp(roofCol, float3(0.80, 0.81, 0.82) * (1.0 - panel * 0.25), domeRoof);
    base = roofCol;
    rough = lerp(0.9, 0.5, sheetRoof);
    rough = lerp(rough, 0.28, imperial);                 // glaze sheen
    rough = lerp(rough, 0.3, domeRoof);
    metal = sheetRoof * 0.3 + domeRoof * 0.55;
    spec = 0.35;
    // a few lit rooftop spots (stair lamps) at night
    float lamp = step(0.97, cr) * box;
    emis = float3(1.0, 0.8, 0.55) * lamp * 0.5 * night;
}

// ----------------------------------------------------------------------------
// Taipei 101 hero surface (vertex contract in tools/lookdev/build_taipei101.py)
// ----------------------------------------------------------------------------
void xc_taipei101(float3 wpos, float2 uv0, float3 vc4rgb, float glassFlag, float3 N,
                  float night, float fwu, float fwh,
                  out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float section = floor(vc4rgb.x * 255.0 + 0.5);
    float tsec = vc4rgb.y;
    float isModule = step(0.5, section) * (1.0 - step(8.5, section));
    float isOrn = step(19.5, section);
    float u = uv0.x;
    float h = uv0.y;
    float fh = 4.2;
    float fv = frac(h / fh);
    // double-glazed blue-green glass, strong vertical mullions every 1.4 m
    float mull = xc_line(frac(u / 1.4), 0.09, fwu / 1.4) * xc_detail(fwu, 1.4);
    float floorLine = xc_line(fv, 0.10, fwh / fh) * xc_detail(fwh, fh) * 0.6;
    // blue-green, not yellow-green: under warm dusk light a green-heavy tint drifts olive
    float3 glass = float3(0.075, 0.15, 0.20);
    // slight darkening at the foot of each module (under the ledge above)
    glass *= lerp(0.8, 1.05, tsec);
    float3 frame = float3(0.52, 0.58, 0.56);
    float3 c = lerp(glass, frame, saturate(mull + floorLine) * 0.8);
    float3 trim = float3(0.56, 0.60, 0.58);
    float3 gold = float3(0.80, 0.60, 0.26);
    c = lerp(trim, c, glassFlag);
    // pinnacle housing + spire: darker brushed steel. As light diffuse trim the thin spire caught
    // the low sun and read near-white at dusk; mostly-specular steel takes the sky colour instead.
    float isPin = step(9.5, section) * (1.0 - step(10.5, section)) * (1.0 - glassFlag);
    c = lerp(c, float3(0.40, 0.43, 0.43), isPin);
    c = lerp(c, gold, isOrn);
    // spandrel band at each slab: opaque fritted glass, a touch lighter and rougher than the vision
    // glass, so the floor rhythm reads in backlight where the reflection alone goes flat
    float spandrel = (1.0 - xc_box(fv, 0.16, 0.92, fwh / fh)) * xc_detail(fwh, fh) * glassFlag;
    c = lerp(c, float3(0.16, 0.22, 0.23), spandrel * 0.7 * (1.0 - isOrn));
    base = c;
    float paneR = 0.055 + 0.03 * xc_hash21(float2(floor(u / 1.4), floor(h / fh))) * xc_detail(fwu, 2.8);
    rough = lerp(0.45, paneR, glassFlag * (1.0 - saturate(mull + floorLine)));
    rough = lerp(rough, 0.22, spandrel);
    rough = lerp(rough, 0.35, isOrn);
    rough = lerp(rough, 0.38, isPin);
    metal = lerp(0.6, 0.12, glassFlag) * (1.0 - isOrn) + isOrn * 0.9;
    metal = lerp(metal, 0.8, isPin);
    spec = lerp(0.5, 0.8, glassFlag * (1.0 - isOrn));      // insulated glass F0 ~0.064
    // Night: warm-white floodlit modules brightening toward each flared top,
    // lit corner notches, glowing crown; office floors partially lit inside.
    float band = smoothstep(0.35, 1.0, tsec) * isModule;
    float officeLit = step(0.6, xc_hash21(float2(floor(u / 2.8), floor(h / fh)))) * glassFlag;
    float3 flood = float3(1.0, 0.78, 0.45);
    // Floodlights have a fixed luminance; how bright they read is the exposure's job. Dusk exposes
    // ~1.3 EV brighter than night, so a flood ramp linear in `night` (0.5 at dusk) put the tier
    // tops on screen brighter than at night and clipped them cream-white. Ramping the floods as
    // night^3 overall (night^2 here, x night below) keeps dusk floods ~0.3x their night read.
    float floodOn = night * night;
    float3 e = flood * band * band * 0.9 * glassFlag * floodOn;
    e += float3(0.85, 0.93, 1.0) * officeLit * xc_box(fv, 0.2, 0.85, fwh / fh) * 0.08 * (1.0 - band) * xc_detail(fwu, 5.6);
    e += flood * isModule * 0.04 * glassFlag * floodOn;
    e += flood * step(9.5, section) * (1.0 - step(10.5, section)) * floodOn;   // pinnacle (was near-white at dusk)
    e += gold * isOrn * 0.6 * floodOn;
    emis = e * night;
}

// ----------------------------------------------------------------------------
// Entry point shared by every building surface.
// vc = COLOR_0 normalised. N = world normal (Z up). fw* = fwidth of coords.
// ----------------------------------------------------------------------------
void xc_city(float3 wpos, float3 N, float2 uv0, float2 uv1, float4 vc,
             float night, float litFrac, Texture2D shopTx, SamplerState shopS, Texture2D planTx,
             out float3 base, out float rough, out float metal, out float spec, out float3 emis,
             out float3 nrm)
{
    float fwu = fwidth(uv0.x);
    float fwh = fwidth(uv0.y);
    float fwp = max(fwidth(wpos.x), fwidth(wpos.y));
    // wall frame for the storefront layer (screen derivatives must be taken outside the wall / roof branches):
    // dUH = d(u, h) / d(screen x, y); tW = horizontal world direction of +u along this wall; nH = outward normal
    float4 dUH = float4(ddx(uv0.x), ddy(uv0.x), ddx(uv0.y), ddy(uv0.y));
    float2 nH = normalize(N.xy + float2(1e-5, 0.0));
    float2 tH = float2(-nH.y, nH.x);
    float2 tW = tH * ((dot(ddx(wpos.xy), tH) * dUH.x + dot(ddy(wpos.xy), tH) * dUH.y) < 0.0 ? -1.0 : 1.0);
    float code = floor(vc.x * 255.0 + 0.5);
    float arch = floor(code / 16.0);
    float variant = code - arch * 16.0;
    float seed = vc.y * 255.0 / 256.0 + 0.00123;
    float weather = vc.z;
    float flags = vc.w;
    float hero = step(0.97, vc.w);   // Taipei 101 tags A = 250

    float isRoof = smoothstep(0.55, 0.75, N.z);
    float isSoffit = step(N.z, -0.7);
    float3 bw = float3(0.0, 0.0, 0.0); float rw = 0.0; float mw = 0.0; float sw = 0.0; float3 ew = float3(0.0, 0.0, 0.0);
    float3 br = float3(0.0, 0.0, 0.0); float rr = 0.0; float mr = 0.0; float sr = 0.0; float3 er = float3(0.0, 0.0, 0.0);
    // Wall XOR roof: the facade grammar is not evaluated on roof pixels and the roof finish is not evaluated on
    // wall pixels (isRoof is exactly 0 / 1 on building meshes: vertical walls, flat roofs). Schools (ARCH_SCHOOL = 7)
    // use only their own wall / roof, which replace every output of the generic path.
    [branch] if (abs(arch - 7.0) < 0.5)
    {
        xc_school_wall(uv0.x, uv0.y, uv1.x, uv1.y, variant, seed, weather, flags, night, litFrac, fwu, fwh,
                       bw, rw, mw, sw, ew);
        xc_school_roof(wpos, seed, weather, fwp, br, rr, mr, sr, er);
    }
    else
    {
        [branch] if (isRoof < 1.0)
        {
            xc_wall(uv0.x, uv0.y, uv1.x, uv1.y, arch, variant, seed, weather, flags, wpos,
                    night, litFrac, fwu, fwh, dUH, tW, nH, shopTx, shopS, planTx, bw, rw, mw, sw, ew);
        }
        [branch] if (isRoof > 0.0)
        {
            xc_roof(wpos, uv1.x, arch, variant, seed, weather, flags, night, fwp, br, rr, mr, sr, er);
        }
    }
    base = lerp(bw, br, isRoof);
    rough = lerp(rw, rr, isRoof);
    metal = lerp(mw, mr, isRoof);
    spec = lerp(sw, sr, isRoof);
    emis = lerp(ew, er, isRoof);
    base = lerp(base, float3(0.2, 0.2, 0.2), isSoffit);
    // Range variation: at overview distance every block's facade averages to its palette mean and
    // the far city read as one repeated pale box. Per-building value (+-17 %) and a ~650 m
    // neighbourhood tone break that up; both are constant per building / low frequency (no shimmer)
    // and fade out where facade detail resolves (fwp in m / pixel).
    float rangeF = smoothstep(1.5, 8.0, fwp) * (1.0 - night);   // day / dusk only (see contact note)
    float bTone = 0.83 + 0.34 * frac(seed * 17.31);
    float hood = 0.86 + 0.28 * xc_fnoise(float2(wpos.x, wpos.y) + 7919.0, 0.0015, fwp);
    base *= lerp(1.0, bTone * hood, rangeF);

#ifndef XC_NO_HERO
    float3 bh; float rh; float mh; float sh; float3 eh;
    xc_taipei101(wpos, uv0, vc.xyz, vc.z, N, night, fwu, fwh, bh, rh, mh, sh, eh);
    base = lerp(base, bh, hero);
    rough = lerp(rough, rh, hero);
    metal = lerp(metal, mh, hero);
    spec = lerp(spec, sh, hero);
    emis = lerp(emis, eh, hero);
#endif

    // Per-pane reflection jitter ("oil canning"): each glass pane is tilted by
    // a fraction of a degree so sky/city reflections break up per window, the
    // strongest cue that separates real glass from a flat texture.
    float glassMask = (1.0 - smoothstep(0.10, 0.30, rough)) * (1.0 - isRoof);
    float paneW = lerp(1.5, 1.4, hero);
    float2 pane = floor(float2(uv0.x / paneW, uv0.y / max(uv1.y, 2.6)));
    float r1 = xc_hash21(pane + seed * 13.0) - 0.5;
    float r2 = xc_hash21(pane.yx + seed * 7.0) - 0.5;
    float3 T = normalize(float3(-N.y, N.x, 0.0) + float3(1e-5, 0.0, 0.0));
    float3 B = float3(0.0, 0.0, 1.0);
    float tilt = 0.045 * glassMask * xc_detail(fwu, paneW * 2.0);
    nrm = normalize(N + (T * r1 + B * r2) * tilt);
}

// ----------------------------------------------------------------------------
// Basin backdrop (distant terrain, tools/lookdev/build_backdrop.py).
// vc.x = urban basin floor weight, vc.y = forest weight (plain TEXCOORD_2).
// fc = far-city data texture sample (tools/lookdev/build_far_city.py):
//   r = real WFS building coverage, g = mean height / 100 m,
//   b = p90 height / 150 m, a = 1 where Taipei WFS data exists.
// The floor is shaded from real density; there is no procedural street grid.
// Outside WFS coverage (New Taipei) a band-limited mottled fallback is used.
// ----------------------------------------------------------------------------
void xc_backdrop(float3 wpos, float3 N, float4 vc, float4 fc, float night, float fwp,
                 out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float has = fc.w;
    // band-limited fabric noise: block (45 m), neighbourhood (160 m), district (600 m) scale
    float m1 = xc_fnoise(p + 211.0, 0.022, fwp);
    float m2 = xc_fnoise(p - 977.0, 0.00625, fwp);
    float m3 = xc_fnoise(p + 3121.0, 0.0017, fwp);
    // fc is a ~47 m bilinear texel field; a low-frequency jitter on the coverage keeps its
    // footprint from reading as soft diamonds where the city meets the hillside forest.
    float covJ = saturate(fc.x * 3.0 + (m2 - 0.5) * 0.35 + (m1 - 0.5) * 0.12);
    float urban = max(vc.x * (1.0 - has), smoothstep(-0.1, 1.0, covJ) * has);
    float forest = vc.y * (1.0 - smoothstep(-0.05, 1.0, covJ) * has);
    // forest: subtropical broadleaf, dark and humid
    float fn = xc_fnoise(p, 0.004, fwp) * 0.6 + xc_fnoise(p, 0.02, fwp) * 0.4;
    float3 forestCol = lerp(float3(0.055, 0.085, 0.045), float3(0.10, 0.14, 0.07), fn);
    float steep = smoothstep(0.35, 0.7, 1.0 - N.z);
    forestCol = lerp(forestCol, float3(0.16, 0.16, 0.13), steep * 0.4);

    // density: real coverage where known, mottled estimate elsewhere
    float fallback = 0.35 + 0.35 * xc_fnoise(p, 0.003, fwp) + 0.15 * xc_fnoise(p, 0.02, fwp);
    float dens = lerp(fallback, saturate(fc.x * 1.6), has);
    float hgt = lerp(0.12, fc.y, has);                      // /100 m
    // Urban floor. Where WFS data exists (has = 1) the real buildings are far-city meshes, so the
    // ground is only what lies between them: streets, lots, yards and street trees. It is never
    // painted with fake roofs (the old 14 m binary hash parcels read as a confetti grid next to the
    // real boxes). Outside WFS coverage (no meshes) a soft mottle stands in for the whole fabric.
    float3 pave = lerp(float3(0.165, 0.163, 0.155), float3(0.245, 0.238, 0.222), m1 * 0.55 + m2 * 0.45);
    float yards = smoothstep(0.52, 0.78, m2 * 0.6 + m3 * 0.4) * (1.0 - dens * 0.7);
    pave = lerp(pave, float3(0.085, 0.115, 0.065), yards * 0.65);
    float3 fabric = lerp(float3(0.20, 0.20, 0.19), float3(0.34, 0.33, 0.31), m1 * 0.5 + m2 * 0.3 + m3 * 0.2);
    fabric = lerp(float3(0.13, 0.13, 0.125), fabric, saturate(dens * 1.3));
    float3 cityCol = lerp(fabric, pave, has);
    // canyon / contact occlusion: dense, tall clusters sit in their own shade, which grounds the
    // far-city boxes into the floor instead of standing them on a bright uniform plane
    cityCol *= 1.0 - 0.3 * saturate(dens * 1.4) * (0.45 + 0.55 * saturate(hgt * 1.6)) * has;
    cityCol *= 1.0 - 0.3 * saturate(hgt * 1.6) * (1.0 - has);   // tall fabric = deeper canyons
    float greenPocket = smoothstep(0.72, 0.8, xc_fnoise(p + 5833.0, 0.0012, fwp)) * (1.0 - has);
    greenPocket = max(greenPocket, (1.0 - saturate(fc.x * 5.0)) * has * vc.x);   // real open space
    cityCol = lerp(cityCol, float3(0.12, 0.17, 0.09), greenPocket);

    float3 lowland = lerp(float3(0.20, 0.24, 0.15), cityCol, urban);
    base = lerp(lowland, forestCol, forest);
    rough = 0.92;
    metal = 0.0;
    spec = 0.3;

    // night light field follows real density and height
    float3 sodium = float3(1.0, 0.55, 0.20);
    float3 ledW = float3(0.85, 0.92, 1.0);
    // Street lights: a sparse set of small anti-aliased lamp points (~1.4 m inside a 6 m cell).
    // Lighting whole 6 m hash cells (up to ~64 % of them) drew a glowing confetti mat at dusk.
    float2 lc = floor(p / 6.0);
    float2 lf = frac(p / 6.0);
    float lampOn = step(1.0 - dens * 0.3, xc_hash21(lc + 3.1));
    float speck = lampOn * xc_box(lf.x, 0.38, 0.62, fwp / 6.0) * xc_box(lf.y, 0.38, 0.62, fwp / 6.0);
    float3 speckCol = lerp(ledW, lerp(sodium, float3(1.0, 0.75, 0.45), 0.5), step(0.45, xc_hash21(lc)));
    // 3.2 = energy match: mean of the near field (0.3 lit x 0.0576 point area x 3.2) equals the
    // far-field mean (0.055 x dens), so city light stays continuous across the LOD fade
    float3 nearGlow = speck * speckCol * 3.2;
    float3 farGlow = float3(1.0, 0.72, 0.45) * dens * 0.055;
    float3 glow = lerp(farGlow, nearGlow, xc_detail(fwp, 12.0));
    glow *= 0.7 + 1.2 * saturate(hgt * 2.0);
    // same light-on curve as the Taipei 101 floods: night unchanged, dusk (night 0.5, ~1.3 EV
    // brighter exposure) no longer reads brighter than night
    emis = glow * urban * (1.0 - greenPocket) * night * night;
}

// Sports-surface palette for tagged school courts / playgrounds (campus_identity.py SURF_*): restrained,
// matte acrylic / PU tones, never a track red. 1 green, 2 blue, 3 grey-green, 4 concrete, 5 playground.
float3 xc_court_surface(float k)
{
    float3 c = float3(0.16, 0.29, 0.20);
    c = lerp(c, float3(0.14, 0.22, 0.32), step(1.5, k));
    c = lerp(c, float3(0.23, 0.30, 0.26), step(2.5, k));
    c = lerp(c, float3(0.41, 0.40, 0.38), step(3.5, k));
    return lerp(c, float3(0.21, 0.28, 0.29), step(4.5, k));
}

// ----------------------------------------------------------------------------
// Xinyi ground (Landscape material). gt = ground data texture sample
// (tools/lookdev/build_ground.py): r = road SDF (0.5 kerb, +-12 m), g = green,
// b = road class, a = surface class. lamp = baked street-lamp pool texture
// (sqrt-encoded). Texture sampling stays outside so this remains portable.
// ct = campus data texture (School & Campus Identity v0A, box-filtered mips):
//   r = Grade-A campus signed distance (+-16 m, > 0 inside), g = court / playground signed distance
//   (+-8 m), b = surface palette id * 32 / 255 (nearest-surface fill), a = 0. The campus layer is a
//   [branch] override after the accepted composite; its mask is exactly 0 outside the campus polygons,
//   so every other ground pixel is the accepted result. Pass float4(0, 0, 0, 0) where no campus texture
//   exists (preview).
// ----------------------------------------------------------------------------
void xc_ground(float3 wpos, float3 N, float4 gt, float4 ct, float lamp, float night, float fwp,
               out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float sd = (gt.x - 0.5) * 24.0;           // metres, negative inside carriageway
    float fsd = max(fwidth(sd), 0.02);
    float cls = gt.z;
    float green = gt.y;
    float water = gt.w;

    float road = 1.0 - smoothstep(-fsd, fsd, sd);
    // asphalt: arterials dark and fresh, lanes grey and patched
    float patchN = xc_fnoise(p, 0.08, fwp);
    float patchC = step(0.62, xc_noise2(floor(p / 3.0) * 0.37 + 5.0));
    float3 asphalt = lerp(float3(0.13, 0.13, 0.135), float3(0.085, 0.085, 0.09), cls);
    asphalt *= 0.85 + 0.3 * patchN;
    asphalt = lerp(asphalt, asphalt * 1.35, patchC * (1.0 - cls) * xc_detail(fwp, 3.0) * 0.5);
    float gutter = (1.0 - smoothstep(-0.7, -0.1, sd)) * smoothstep(-1.2, -0.7, sd);
    asphalt *= 1.0 - gutter * 0.25;

    // road edge (Taipei Street Reality v0C): ct.w = pedestrian class of the nearest road side, from mapped
    // sidewalks / sidewalk tags / road class / arcade frontage (build_ground.py curb layer): ~1 raised sidewalk,
    // ~0.5 arcade apron (no sidewalk, old shop-house arcade behind), ~0 no formal sidewalk (lane asphalt runs on
    // to the building line). Parked scooters are instanced meshes in painted road-edge bays, not ground colour.
    float ped = ct.w;
    float isSw = smoothstep(0.70, 0.85, ped);
    float isAp = smoothstep(0.30, 0.42, ped) * (1.0 - isSw);
    float isLn = 1.0 - isSw - isAp;
    float kerb = xc_box(sd, 0.0, 0.22, fsd) * isSw;
    float walk = step(0.22, sd) * (1.0 - smoothstep(3.5, 5.0, sd)) * step(0.2, cls) * isSw;
    // municipal high-pressure concrete pavers: grey / beige-grey by stretch, value-only variation, darker repairs
    float2 pv = frac(p / 0.3);
    float paverLine = max(xc_line(pv.x, 0.12, fwp / 0.3), xc_line(pv.y, 0.12, fwp / 0.3)) * xc_detail(fwp, 0.6);
    float3 paver = lerp(float3(0.29, 0.285, 0.275), float3(0.31, 0.30, 0.28),
                        smoothstep(0.42, 0.58, xc_fnoise(p + 311.0, 0.012, fwp)));
    paver *= 0.93 + 0.14 * xc_fnoise(p - 97.0, 0.02, fwp);
    float repair = step(0.8, xc_noise2(p * 0.42 + 31.0)) * xc_detail(fwp, 2.0);
    paver = lerp(paver, paver * float3(0.80, 0.81, 0.83), repair);
    paver *= 1.0 - paverLine * 0.2;
    // arcade apron: drain-cover strip at the carriageway edge, then owner-built concrete / tile, mismatched by shop
    float apron = isAp * step(0.0, sd) * (1.0 - smoothstep(3.6, 5.0, sd));
    float3 apronC = float3(0.275, 0.266, 0.25) * (0.88 + 0.2 * xc_fnoise(p + 57.0, 0.25, fwp));
    apronC = lerp(apronC, float3(0.17, 0.17, 0.168), xc_box(sd, 0.0, 0.45, fsd));
    // no formal sidewalk: older, lighter, more patched lane asphalt continues toward the building line
    float laneEdge = isLn * step(0.0, sd) * (1.0 - smoothstep(2.6, 3.6, sd));
    float3 laneA = float3(0.135, 0.135, 0.14) * (0.88 + 0.3 * patchN);
    laneA = lerp(laneA, laneA * 1.3, step(0.55, xc_noise2(floor(p / 2.4) * 0.41 + 9.0)) * xc_detail(fwp, 2.4) * 0.5);

    // lots / plazas between buildings
    float n = xc_fnoise(p, 0.05, fwp);
    float3 plaza = lerp(float3(0.22, 0.22, 0.215), float3(0.29, 0.285, 0.27), n);

    float3 grass = lerp(float3(0.09, 0.15, 0.06), float3(0.15, 0.21, 0.08), xc_fnoise(p, 0.12, fwp));
    float hill = saturate(smoothstep(22.0, 45.0, wpos.z) + smoothstep(0.12, 0.25, 1.0 - N.z));
    float fn = xc_fnoise(p, 0.01, fwp) * 0.6 + xc_fnoise(p, 0.08, fwp) * 0.4;
    float3 forest = lerp(float3(0.05, 0.08, 0.04), float3(0.10, 0.14, 0.065), fn);
    float3 waterCol = float3(0.05, 0.08, 0.08);
    // categorical surfaces from OSM (a: 1 water, .8 track, .6 court,
    // .4 construction, .3 school yard, .2 surface parking)
    float surf = gt.w;
    float isTrack = step(0.7, surf) * (1.0 - step(0.9, surf));
    float isCourt = step(0.5, surf) * (1.0 - step(0.7, surf));
    float isBuild = step(0.35, surf) * (1.0 - step(0.5, surf));
    float isSchool = step(0.25, surf) * (1.0 - step(0.35, surf));
    float isPark = step(0.12, surf) * (1.0 - step(0.25, surf));
    float3 track = float3(0.40, 0.15, 0.11);                       // red PU school track
    float3 court = lerp(float3(0.15, 0.32, 0.24), float3(0.14, 0.24, 0.40), step(0.5, xc_hash21(floor(p / 36.0))));
    float3 dirt = lerp(float3(0.36, 0.29, 0.21), float3(0.44, 0.38, 0.30), xc_fnoise(p, 0.15, fwp));
    float3 yard = float3(0.40, 0.39, 0.36);
    float stall = max(xc_line(frac(p.x / 2.5), 0.05, fwp / 2.5), xc_line(frac(p.y / 5.5), 0.025, fwp / 5.5))
                  * xc_detail(fwp, 1.5);
    float3 lot = lerp(float3(0.15, 0.15, 0.155), float3(0.75, 0.75, 0.72), stall * 0.8);

    float3 c = plaza;
    // Building-less band: the Landscape extends past the WFS source bbox, and the far city skips
    // that bbox, so between them no layer carries buildings and the ground read as a pale empty
    // plaza strip from the air. From mid range on, shade it as low-rise roofscape (block-scale
    // value / rust / green-coat variation over darker street shade), matching the backdrop fabric.
    float2 en = float2(wpos.x, -wpos.y);
    float inSrc = smoothstep(XC_SRC_E0 - 40.0, XC_SRC_E0 + 40.0, en.x) * (1.0 - smoothstep(XC_SRC_E1 - 40.0, XC_SRC_E1 + 40.0, en.x))
                * smoothstep(XC_SRC_N0 - 40.0, XC_SRC_N0 + 40.0, en.y) * (1.0 - smoothstep(XC_SRC_N1 - 40.0, XC_SRC_N1 + 40.0, en.y));
    float b1 = xc_fnoise(p + 431.0, 0.025, fwp);
    float b2 = xc_fnoise(p - 1291.0, 0.008, fwp);
    // roof masses vs street shade (block scale), so it reads as dense fabric rather than open plaza
    float3 lowrise = lerp(float3(0.075, 0.078, 0.075), float3(0.34, 0.33, 0.30), smoothstep(0.3, 0.7, b1 * 0.7 + b2 * 0.3));
    lowrise = lerp(lowrise, lowrise * float3(1.15, 0.92, 0.80), smoothstep(0.62, 0.8, xc_fnoise(p + 77.0, 0.04, fwp)) * 0.6);
    lowrise = lerp(lowrise, lowrise * float3(0.85, 1.12, 0.95), smoothstep(0.62, 0.8, xc_fnoise(p - 53.0, 0.035, fwp)) * 0.6);
    float band = (1.0 - inSrc) * smoothstep(0.25, 1.0, fwp);
    c = lerp(c, lowrise, band);
    c = lerp(c, paver, walk);
    c = lerp(c, apronC, apron);
    c = lerp(c, laneA, laneEdge);
    c = lerp(c, grass, saturate(green * 1.2) * (1.0 - road));
    c = lerp(c, forest, hill * (1.0 - road) * (1.0 - green * 0.5));
    c = lerp(c, float3(0.55, 0.55, 0.53), kerb * step(0.2, cls));
    c = lerp(c, yard, isSchool);
    c = lerp(c, lot, isPark);
    c = lerp(c, dirt, isBuild);
    c = lerp(c, court, isCourt);
    c = lerp(c, track, isTrack);
    c = lerp(c, asphalt, road);
    water = step(0.9, surf);
    c = lerp(c, waterCol, water);

    // ---- School & Campus Identity v0A campus layer (Grade-A campuses only) -------------------------
    // Inset: bilinear overshoot at reflex corners + 8-bit steps stay < 0.35 m at mip 0 (offline leak gate);
    // a mip / anisotropic average of a 1-Lipschitz field moves by at most ~half its footprint, so the inset
    // grows with the pixel footprint once that exceeds a texel. Outside the polygons the mask is exactly 0.
    float dC = (ct.x - 0.5) * 32.0;
    float campusIn = saturate((dC - 0.5 - 0.6 * max(fwp - 1.0, 0.0)) / max(fwidth(dC), 0.02));
    float dK = (ct.y - 0.5) * 16.0;
    float fK = max(fwidth(dK), 0.01);
    [branch] if (campusIn > 0.0)
    {
        // schoolyard: neutral grey paved concrete, low-frequency patching and stains; sidewalks, greens,
        // kerbs, roads and water keep their mapped surfaces on top. No generic categorical class (and so no
        // track) is drawn inside a campus.
        float3 yardC = float3(0.30, 0.297, 0.285) * (0.965 + 0.07 * xc_fnoise(p + 913.0, 0.06, fwp));
        yardC *= 1.0 - saturate(xc_fnoise(p - 377.0, 0.21, fwp) * 1.4 - 0.75) * 0.10;
        float3 cc = lerp(yardC, paver, walk);
        cc = lerp(cc, grass, saturate(green * 1.2) * (1.0 - road));
        cc = lerp(cc, forest, hill * (1.0 - road) * (1.0 - green * 0.5));
        cc = lerp(cc, float3(0.55, 0.55, 0.53), kerb * step(0.2, cls));
        // tagged courts / playground with an analytic painted outline 0.35 m inside the real edge: a 12 cm
        // line converges to its coverage mean instead of breaking into dots at grazing angles. Past ~0.2 m
        // per pixel the outer rectangle widens inward with the footprint (max 0.8 m) so the court still reads
        // as a court at mid range; it never leaves the court polygon.
        float courtIn = saturate(dK / fK);
        float3 courtC = xc_court_surface(floor(ct.z * 255.0 / 32.0 + 0.5)) * (0.94 + 0.1 * xc_fnoise(p + 71.0, 0.25, fwp));
        cc = lerp(cc, courtC, courtIn);
        float lwK = clamp(fK * 0.85, 0.12, 0.8);
        float courtLine = saturate(lwK / fK) * (1.0 - smoothstep(lwK * 0.5 - fK * 0.5, lwK * 0.5 + fK * 0.5, abs(dK - 0.35 - lwK * 0.5))) * courtIn;
        cc = lerp(cc, float3(0.70, 0.70, 0.67), courtLine);
        cc = lerp(cc, asphalt, road);
        cc = lerp(cc, waterCol, water);
        c = lerp(c, cc, campusIn);
    }
    base = c;
    rough = lerp(0.88, 0.75, road);
    rough = lerp(rough, 0.05, water);
    metal = 0.0;
    spec = 0.4;

    float pool = lamp * lamp;                                   // decode sqrt storage
    float spill = step(3.0, sd) * (1.0 - step(12.0, sd)) * (1.0 - hill) * 0.05;   // shopfront spill near kerbs
    float3 lampCol = lerp(float3(1.0, 0.72, 0.45), float3(0.92, 0.96, 1.0), 0.7);
    emis = c * (lampCol * pool * 1.3 + float3(1.0, 0.85, 0.65) * spill + 0.02) * night;
}

// Road paint: vc = COLOR_0 (sRGB-ish paint colour). Shares the street-light fill.
void xc_paint(float3 wpos, float4 vc, float4 gt, float lamp, float night, float fwp,
              out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float3 c = vc.xyz * vc.xyz;                       // approx sRGB -> linear
    // worn paint: tyre wear breaks up lines/crossings
    float wear = xc_fnoise(p, 1.7, fwp) * 0.6 + xc_fnoise(p, 0.23, fwp) * 0.4;
    c = lerp(c, float3(0.12, 0.12, 0.12), saturate(wear - 0.55) * 1.2);
    base = c * 0.85;
    // school court markings (build_ground.py campus paint): R byte = court surface id 1..5 (road paint
    // colours all have R >= 190; small values survive the half-precision UV packing exactly). A 15 cm line
    // converges to its coverage-weighted mix with the court surface once it is sub-pixel.
    [branch] if (vc.x < 0.03)
    {
        float3 surf = xc_court_surface(floor(vc.x * 255.0 + 0.5)) * (0.94 + 0.1 * xc_fnoise(p + 71.0, 0.25, fwp));
        float3 lineC = lerp(float3(0.74, 0.74, 0.71), surf, saturate(wear - 0.6) * 0.8);
        base = lerp(surf, lineC, saturate(0.21 / max(fwp, 1e-4)));
    }
    rough = 0.6;
    metal = 0.0;
    spec = 0.5;
    float3 lampCol = lerp(float3(1.0, 0.72, 0.45), float3(0.92, 0.96, 1.0), 0.7);
    emis = base * (lampCol * lamp * lamp * 1.3 + 0.02) * night;
}

// Trees: vc.y = crown flag, vc.z = instance variant (0..1), h = height (m).
void xc_foliage(float3 wpos, float3 N, float4 vc, float h, float night,
                out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float crown = step(0.5, vc.y);
    float v = vc.z;
    // camphor / banyan dark greens, Taiwan golden-rain trees in late-September bloom
    float3 g = xc_pick4(v, float3(0.050, 0.085, 0.030), float3(0.070, 0.110, 0.035),
                        float3(0.045, 0.075, 0.035), float3(0.20, 0.16, 0.05));
    float leafN = xc_noise2(float2(wpos.x + wpos.z, wpos.y - wpos.z) * 1.3);
    g *= 0.75 + 0.5 * leafN;
    g *= lerp(0.6, 1.1, saturate((h - 3.5) / 5.0));          // self-shadowed underside
    base = lerp(float3(0.10, 0.08, 0.06), g, crown);
    rough = 0.85;
    metal = 0.0;
    spec = 0.25;
    // lit from below by street lamps at night
    emis = base * float3(1.0, 0.75, 0.45) * (1.0 - saturate((h - 3.0) / 5.0)) * 1.0 * night;
}

// ----------------------------------------------------------------------------
// Rooftop props (tools/lookdev/build_rooftops.py). vc.x*255 = prop type id,
// vc.y*255 = part id, variant = per-instance 0..1.
// types: 1 shed, 2 tank, 3 solar, 4 antenna, 5 ac, 6 cooling, 7 machine,
//        8 bmu, 9 aviation light
// ----------------------------------------------------------------------------
void xc_prop(float3 wpos, float3 N, float4 vc, float variant, float yawN, float night, float fwp,
             out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float t = floor(vc.x * 255.0 + 0.5);
    float part = floor(vc.y * 255.0 + 0.5);
    float isT1 = 1.0 - step(0.5, abs(t - 1.0));
    float isT2 = 1.0 - step(0.5, abs(t - 2.0));
    float isT3 = 1.0 - step(0.5, abs(t - 3.0));
    float isT4 = 1.0 - step(0.5, abs(t - 4.0));
    float isT5 = 1.0 - step(0.5, abs(t - 5.0));
    float isT6 = 1.0 - step(0.5, abs(t - 6.0));
    float isT7 = 1.0 - step(0.5, abs(t - 7.0));
    float isT8 = 1.0 - step(0.5, abs(t - 8.0));
    float isT9 = 1.0 - step(0.5, abs(t - 9.0));
    float isT10 = 1.0 - step(0.5, abs(t - 10.0));   // street lamp
    // rooftop identity v0: 11 gable addition room, 12 barrel-roof room, 13 open lean-to, 14 stair bulkhead
    float isT11 = 1.0 - step(0.5, abs(t - 11.0));
    float isT12 = 1.0 - step(0.5, abs(t - 12.0));
    float isT13 = 1.0 - step(0.5, abs(t - 13.0));
    float isT14 = 1.0 - step(0.5, abs(t - 14.0));
    float p1 = step(0.5, part);
    float p2 = step(1.5, part) * (1.0 - step(2.5, part));
    float p3 = step(2.5, part);

    // sheet-metal rooms (1 shed, 11-13): variant = (roof colour * 16 + wall colour + 0.5) / 256;
    // part 0 = walls (wall colour), part 1 = roof (roof colour), part 2 = steel posts
    float isSheet = isT1 + isT11 + isT12 + isT13;
    float roofIdx = floor(variant * 16.0);
    float wallIdx = floor(frac(variant * 16.0) * 16.0);
    // ridge frame (roofscape v2 step 2): yawN = per-instance custom data 1 = (ENU yaw mod 180) / 180. The unit
    // meshes run their ridge along local x, so seams / panel strips run down the slope across it. World xy is
    // UE x = east, y = -north, so the ridge direction is (cos yaw, -sin yaw).
    float ya = yawN * 3.14159265;
    float2 ru = float2(cos(ya), -sin(ya));
    float2 rq = float2(dot(wpos.xy, ru), dot(wpos.xy, float2(-ru.y, ru.x)));
    float ribs = xc_line(frac(rq.x / 0.7), 0.3, fwp / 0.7) * xc_detail(fwp, 0.7);   // broad seam rhythm, fades by ~400 m
    float3 sheet = xc_sheet16(lerp(wallIdx, roofIdx, p1));
    sheet = xc_sheet_weather(sheet, wpos.xy, rq, wpos.z, N.z, roofIdx * 0.37 + wallIdx * 0.11, fwp);
    sheet *= 1.0 - ribs * lerp(0.22, 0.16, p1);
    sheet = lerp(sheet, float3(0.16, 0.16, 0.17), p2);                    // painted steel posts
    // stair bulkhead: painted / tiled concrete (light wall palette, greyed), slab cap, dark door
    float3 bulk = lerp(xc_sheet16(wallIdx), float3(0.55, 0.54, 0.51), 0.55);
    bulk *= 1.0 - xc_fnoise(float2(wpos.x + wpos.y, wpos.z * 2.0), 0.7, fwp) * 0.22;
    bulk = lerp(bulk, float3(0.47, 0.46, 0.44), p3);
    bulk = lerp(bulk, lerp(float3(0.14, 0.20, 0.17), float3(0.30, 0.17, 0.11), step(8.0, roofIdx)), p2);
    float3 steel = xc_pick4(variant, float3(0.72, 0.73, 0.74), float3(0.70, 0.71, 0.72),
                            float3(0.78, 0.78, 0.76), float3(0.18, 0.32, 0.58));   // stainless / white PE / blue FRP
    float3 c = sheet * isSheet + bulk * isT14;
    c += lerp(steel, float3(0.20, 0.20, 0.21), p1) * isT2;
    c += lerp(float3(0.04, 0.07, 0.11), float3(0.66, 0.66, 0.64), p1) * isT3;
    c += float3(0.22, 0.22, 0.23) * isT4;
    c += lerp(float3(0.70, 0.68, 0.62), float3(0.18, 0.18, 0.18), p1) * isT5;
    c += lerp(float3(0.42, 0.48, 0.45), float3(0.14, 0.14, 0.15), p1) * isT6;
    c += lerp(xc_pick4(variant, float3(0.46, 0.46, 0.44), float3(0.55, 0.53, 0.49),
                       float3(0.36, 0.37, 0.37), float3(0.50, 0.48, 0.45)), float3(0.30, 0.30, 0.30), p1) * isT7;
    c += lerp(float3(0.70, 0.70, 0.68), float3(0.62, 0.52, 0.18), p1) * isT8;
    c += lerp(float3(0.55, 0.05, 0.03), float3(0.25, 0.25, 0.25), p1) * isT9;
    c += lerp(float3(0.30, 0.31, 0.32), float3(0.85, 0.85, 0.82), p1) * isT10;
    // soot and rain stains
    float grime = xc_fnoise(float2(wpos.x + wpos.z, wpos.y), 0.9, fwp) * 0.25;
    c *= 1.0 - grime * (1.0 - isT9) * (1.0 - isSheet * 0.6);

    base = c;
    rough = lerp(0.7, 0.62, isSheet);                    // matte, weathered sheet (no toy gloss)
    rough = lerp(rough, 0.85, isT14);
    rough = lerp(rough, 0.28, isT2 * (1.0 - p1));
    rough = lerp(rough, 0.08, isT3 * (1.0 - p1));
    metal = saturate(isSheet * lerp(0.18, 0.35, step(8.5, roofIdx) * (1.0 - step(10.5, roofIdx)))
                     + isT2 * (1.0 - p1) * step(variant, 0.49) + isT4 * 0.6 + isT8 * 0.5);
    spec = lerp(0.4, 1.0, isT3 * (1.0 - p1));
    // aviation obstruction lights: always faintly visible, bright at night
    float3 e = float3(1.0, 0.06, 0.02) * isT9 * (1.0 - p1) * lerp(0.15, 2.5, night);
    // a few lit shed windows
    e += float3(1.0, 0.78, 0.5) * (isT1 + isT11 + isT12) * step(0.85, frac(variant * 37.0)) * (1.0 - p1) * 0.12 * night;
    // street lamp heads: white LED (most of Taipei) or warm sodium
    float3 lampCol = lerp(float3(0.92, 0.96, 1.0), float3(1.0, 0.62, 0.25), step(0.5, variant));
    e += lampCol * isT10 * p1 * 3.0 * night;
    emis = e;
}

// ----------------------------------------------------------------------------
// Street identity v0B: projecting signs + rain awnings (tools/lookdev/build_street_identity.py), one opaque
// instanced material; v0C adds parked scooters on the same material. vc.x = type (15 sign / box, 16 awning,
// 17 scooter), vc.y = part. variant = (v + 0.5) / 512 for signs
// (v = atlas cell + 64 * lit + 128 * fade), (v + 0.5) / 64 for awnings (v = colour + 8 * fade + 32 * style).
// Atlas (tools/lookdev/build_sign_atlas.py, 2048^2, power-of-two aligned bins so mips never mix cells):
//   cells  0..31  128 x 512 at y 0     (16 per row)     cells 32..39  256 x 512 at y 1024
//   cells 40..55  256 x 256 at y 1536  (8 per row)
// ----------------------------------------------------------------------------
float2 xc_street_uv(float2 uv0, float variant)
{
    float v = floor(variant * 512.0);
    float cell = v - 64.0 * floor(v / 64.0);
    float isV2 = step(31.5, cell) * (1.0 - step(39.5, cell));
    float isSq = step(39.5, cell);
    float k = cell - 32.0 * isV2 - 40.0 * isSq;
    float cols = lerp(16.0, 8.0, max(isV2, isSq));
    float2 size = lerp(float2(128.0, 512.0), float2(256.0, 512.0), isV2);
    size = lerp(size, float2(256.0, 256.0), isSq);
    float row = floor(k / cols);
    float2 org = float2((k - row * cols) * size.x, lerp(0.0, lerp(1024.0, 1536.0, isSq), max(isV2, isSq)) + row * size.y);
    // inset by half a texel of the sampled mip so bilinear filtering never reaches the neighbour cell
    float2 fw = max(fwidth(uv0 * size), float2(1.0, 1.0));
    float2 inset = 0.5 * fw / size;
    float2 uv = clamp(uv0, inset, 1.0 - inset);
    return (org + uv * size) / 2048.0;
}

void xc_street(float3 wpos, float3 N, float2 uv0, float4 vc, float variant, float4 tx, float night, float fwp,
               out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float t = floor(vc.x * 255.0 + 0.5);
    float part = floor(vc.y * 255.0 + 0.5);
    // --- parked scooters (Taipei Street Reality v0C, type 17): vc.y = part (0 body, 1 seat, 2 tyre, 3 dark trim /
    // screen, 4 top box, 5 floorboard); variant = (v + 0.5) / 64, v = body colour (0..7) + 8 * grime (0..3)
    // + 32 * top-box colour (0..1). Muted fleet colours, no brands, no lights (night: a flat street-level spill only);
    // the atlas sample is unused.
    [branch] if (t > 16.5)
    {
        float sv = floor(variant * 64.0);
        float bc = sv - 8.0 * floor(sv / 8.0);
        float grime = (floor(sv / 8.0) - 4.0 * floor(sv / 32.0)) / 3.0;
        float3 body = xc_pick4(bc / 4.0, float3(0.60, 0.60, 0.58), float3(0.035, 0.035, 0.04),
                               float3(0.34, 0.35, 0.36), float3(0.10, 0.10, 0.11));
        body = lerp(body, xc_pick4((bc - 4.0) / 4.0, float3(0.05, 0.08, 0.16), float3(0.20, 0.035, 0.03),
                                   float3(0.45, 0.40, 0.31), float3(0.13, 0.17, 0.13)), step(3.5, bc));
        body = lerp(body, float3(0.21, 0.20, 0.18), grime * 0.15);
        float3 boxC = lerp(float3(0.52, 0.52, 0.50), float3(0.04, 0.04, 0.045), step(31.5, sv));
        float pBody = 1.0 - step(0.5, part);
        float3 kc = lerp(float3(0.025, 0.025, 0.027), float3(0.06, 0.06, 0.065), step(2.5, part));
        kc = lerp(kc, boxC, step(3.5, part) * (1.0 - step(4.5, part)));
        kc = lerp(kc, float3(0.07, 0.07, 0.07), step(4.5, part));
        base = lerp(kc, body, pBody);
        rough = lerp(0.72, 0.42, pBody);
        metal = 0.0;
        spec = 0.5;
        emis = base * 0.12 * night;                     // street-level spill (lamps, shopfronts): no black holes
        return;
    }
    float isAwn = step(15.5, t);
    // --- signs: atlas face, steel brackets, board rim; per-instance age and lit flag
    float v = floor(variant * 512.0);
    float lit = step(0.5, frac(floor(v / 64.0) * 0.5));
    float age = floor(v / 128.0) / 3.0;
    float3 face = tx.rgb;
    float lum = dot(face, float3(0.3, 0.59, 0.11));
    face = lerp(face, lum * float3(1.04, 1.0, 0.9), age * 0.45);              // sun-faded, yellowed acrylic
    face *= 1.0 - age * 0.2;
    float streak = xc_fnoise(float2(uv0.x * 5.0 + variant * 91.0, uv0.y * 0.7), 1.0, fwidth(uv0.x) * 5.0);
    face *= 1.0 - saturate(streak * 1.6 - 0.5) * age * 0.35 * (1.0 - uv0.y * 0.5);   // rain streaks from the top
    float isBracket = step(0.5, part) * (1.0 - step(1.5, part));
    float isRim = step(1.5, part);
    float3 sc = lerp(face, face * 0.72, isRim);
    sc = lerp(sc, float3(0.17, 0.17, 0.18), isBracket);
    // night: only lit instances glow, through the atlas emissive mask (light-box panel or letters), a little
    // under their daylight colour so streets stay restrained; unlit boards stay dark
    float3 se = face * tx.a * lit * (1.0 - isBracket) * lerp(0.75, 1.0, isRim) * 2.4 * night;
    // --- awnings: corrugated sheet or polycarbonate / canvas, sun-bleached with age, darker dirty lip
    float av = floor(variant * 64.0);
    float ac = av - 8.0 * floor(av / 8.0);
    float afade = floor(av / 8.0) - 4.0 * floor(av / 32.0);
    float astyle = step(31.5, av);
    float3 col = xc_pick4(ac / 8.0 * 2.0, float3(0.19, 0.34, 0.24), float3(0.17, 0.27, 0.40),
                          float3(0.64, 0.63, 0.58), float3(0.42, 0.43, 0.43));
    col = lerp(col, xc_pick4((ac - 4.0) / 4.0, float3(0.50, 0.56, 0.60), float3(0.44, 0.14, 0.11),
                             float3(0.54, 0.40, 0.17), float3(0.15, 0.35, 0.37)), step(3.5, ac));
    float alum = dot(col, float3(0.3, 0.59, 0.11));
    col = lerp(col, alum * 1.08 + 0.03, afade / 3.0 * 0.3);
    float3 T = normalize(cross(N, float3(0.0, 0.0, 1.0)) + float3(1e-4, 0.0, 0.0));
    float rc = dot(wpos, T) / 0.12;
    float ribs = xc_line(frac(rc), 0.35, fwp / 0.12) * xc_detail(fwp, 0.24) * (1.0 - astyle);
    col *= 1.0 - ribs * 0.22;
    float lip = step(0.5, part) * (1.0 - step(1.5, part));
    col = lerp(col, col * 0.78, lip);
    col *= 1.0 - xc_fnoise(float2(dot(wpos, T), wpos.z * 3.0), 0.8, fwp) * 0.18 * (afade / 3.0 + 0.3);
    float strut = step(2.5, part);
    col = lerp(col, float3(0.16, 0.16, 0.17), strut);                        // painted steel struts
    base = lerp(sc, col, isAwn);
    rough = lerp(lerp(0.42, 0.6, isRim + isBracket), lerp(0.62, 0.5, astyle), isAwn);
    metal = lerp(isBracket * 0.6, lerp(0.15 * (1.0 - astyle), 0.5, strut), isAwn);
    spec = 0.45;
    // awnings at night: the drip lip of ~60 % of canopies catches the light of the shop underneath
    float shopOn = step(0.4, frac(variant * 37.3));
    float3 ae = float3(1.0, 0.82, 0.58) * lip * shopOn * 0.35 * night;
    emis = lerp(se, ae, isAwn);
}
