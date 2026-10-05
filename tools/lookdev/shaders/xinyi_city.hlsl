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
// builder draws indices with district weights). Sun-faded, oxidised, matte: blue-greys, oxidised /
// brick reds, faded and teal greens, galvanised, off-white / beige. No saturated toy colours.
// Painted whole-roof sheet colour index (no instance data): uniform hash with half of the warm picks
// moved to blue / galvanised, so painted roofs (old roofs, surveyed rooftop records, far city) follow
// the observed mix instead of a red carpet.
float xc_sheet_paint_index(float r, float r2)
{
    float i = floor(r * 16.0);
    float warm = step(2.5, i) * (1.0 - step(5.5, i)) + step(14.5, i);
    return lerp(i, lerp(1.0, 9.0, step(0.5, frac(r2 * 3.1))), warm * step(0.5, r2));
}

float3 xc_sheet16(float i)
{
    float3 c = float3(0.18, 0.28, 0.40);                                  // 0 blue-grey
    c = lerp(c, float3(0.13, 0.27, 0.48), step(0.5, i));                  // 1 faded blue (the signature 鐵皮 blue)
    c = lerp(c, float3(0.30, 0.42, 0.54), step(1.5, i));                  // 2 light blue
    c = lerp(c, float3(0.31, 0.105, 0.065), step(2.5, i));                // 3 brick red
    c = lerp(c, float3(0.36, 0.155, 0.085), step(3.5, i));                // 4 oxidised rust red
    c = lerp(c, float3(0.27, 0.13, 0.085), step(4.5, i));                 // 5 red-brown
    c = lerp(c, float3(0.18, 0.34, 0.20), step(5.5, i));                  // 6 faded green
    c = lerp(c, float3(0.13, 0.31, 0.29), step(6.5, i));                  // 7 teal green
    c = lerp(c, float3(0.26, 0.36, 0.29), step(7.5, i));                  // 8 green-grey
    c = lerp(c, float3(0.46, 0.47, 0.47), step(8.5, i));                  // 9 galvanised
    c = lerp(c, float3(0.32, 0.33, 0.33), step(9.5, i));                  // 10 weathered galvanised
    c = lerp(c, float3(0.62, 0.62, 0.59), step(10.5, i));                 // 11 off-white
    c = lerp(c, float3(0.55, 0.49, 0.38), step(11.5, i));                 // 12 beige
    c = lerp(c, float3(0.66, 0.64, 0.58), step(12.5, i));                 // 13 cream
    c = lerp(c, float3(0.20, 0.40, 0.42), step(13.5, i));                 // 14 faded teal
    return lerp(c, float3(0.38, 0.28, 0.20), step(14.5, i));              // 15 rusting galvanised
}

// Weathering of a sheet-metal colour: sun fade on up-facing sheets, rust bloom / soot streaks, and
// mismatched patch panels (re-roofed strips) on roofs. p = world xy (m), up = N.z, seed per instance.
float3 xc_sheet_weather(float3 c, float2 p, float z, float up, float seed, float fwp)
{
    float lum = dot(c, float3(0.3, 0.59, 0.11));
    c = lerp(c, lum.xxx * 1.08, saturate(up) * 0.12);                     // UV-faded tops
    float rust = saturate(xc_fnoise(p * 0.9 + seed * 17.0 + z * 0.3, 1.1, fwp) * 1.6 - 0.55);
    c = lerp(c, c * float3(0.92, 0.72, 0.58) + float3(0.03, 0.01, 0.0), rust * 0.3);
    float soot = xc_fnoise(float2(p.x + p.y, z * 3.0) + seed * 5.0, 0.6, fwp);
    c *= 1.0 - soot * 0.12 * (1.0 - saturate(up));                        // streaky walls
    // patch panels: 0.9 m strips, a few replaced in galvanised or another faded colour
    float2 pc = float2(floor((p.x + p.y) / 0.9), floor((p.x - p.y) / 2.4));
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
void xc_wall(float u, float h, float H, float fh, float arch, float variant, float seed,
             float weather, float flags, float3 wpos, float night, float litFrac,
             float fwu, float fwh,
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
    float arcade = street * isOld * (1.0 - core * 0.6) * lerp(1.0, fComm, known);
    float signTop = lerp(1.55, 1.72, known * fPrim * fMajor);     // taller sign boards on major commercial roads
    float signBand = step(fh * 1.02, h) * (1.0 - step(fh * signTop, h)) * isOld * (1.0 - core * 0.8);
    float signW = bw * (0.8 + 0.8 * colR);
    float signCell = floor(u / signW);
    float signR = xc_hash21(float2(signCell, seed * 29.0));
    float signThr = 1.01;                                         // rear / side: none
    signThr = lerp(signThr, 0.92, step(1.5, front));             // service alley
    signThr = lerp(signThr, 0.85, fStreet);                       // street wall of a non-commercial building
    signThr = lerp(signThr, 0.60, fComm);                         // corner side street
    signThr = lerp(signThr, 0.35, fPrim);                         // commercial frontage
    signThr = lerp(signThr, 0.22, fPrim * fMajor);                // ... on a collector / arterial
    signThr += 0.1 * isHuaxia * fComm;
    float hasSign = step(lerp(0.35, signThr, known), signR);
    float3 signCol = xc_sign_palette(frac(signR * 9.7));
    // pseudo-lettering: blocky glyph rhythm on signs (near only)
    float glyph = step(0.45, xc_hash21(floor(float2(u / 0.55, h / 0.5)) + signCell)) * xc_detail(fwu, 0.8);
    // frontage walls: one row of character blocks (2 x 3 stroke clusters each) with word gaps and a dark board
    // edge, so a shop sign reads as a lettered board rather than noise; text contrasts with the board colour
    float bandH = max((signTop - 1.02) * fh, 0.3);
    float sv = (h - fh * 1.02) / bandH;
    float cu = u / 0.62;
    float chrBox = xc_box(frac(cu), 0.13, 0.87, fwu / 0.62) * xc_box(sv, 0.20, 0.80, fwh / bandH);
    float stroke = step(0.32, xc_hash21(floor(float2(cu * 2.0, sv * 3.0)) + signCell * 3.1 + seed));
    float word = step(0.2, xc_hash21(float2(floor(cu / 4.0), signCell + seed * 3.0)));
    float glyph2 = chrBox * lerp(0.7, stroke, xc_detail(fwu, 0.31)) * word * xc_detail(fwu, 0.8);
    float boardEdge = (1.0 - xc_box(frac(u / signW), 0.012, 0.988, fwu / signW)) * xc_detail(fwu, 0.5);
    glyph = lerp(glyph, glyph2, known);

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
    float shutter = step(lerp(0.55, lerp(0.55, 0.72, fPrim), known), xc_hash21(float2(signCell, 3.0)));
    float3 shop = lerp(lerp(float3(0.07, 0.065, 0.06), float3(0.15, 0.135, 0.11), known * fComm),
                       float3(0.42, 0.42, 0.42), shutter);
    shop = lerp(shop, wall * 0.9, (1.0 - xc_box(fu, 0.06, 0.94, fwb)) * dBay * known);
    c = lerp(c, shop, arcade * 0.92);
    float3 txt = lerp(float3(0.93, 0.93, 0.90), float3(0.10, 0.08, 0.07),
                      step(0.55, dot(signCol, float3(0.3, 0.59, 0.11))));
    float3 signFace = lerp(lerp(signCol, signCol * 0.25 + 0.6, glyph * 0.5),
                           lerp(lerp(signCol, txt, glyph * 0.85), float3(0.12, 0.12, 0.12), boardEdge * 0.8), known);
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
        sheet = xc_sheet_weather(sheet, wpos.xy, wpos.z, 0.0, seed, max(fwu, fwh));
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
    float3 e = lightCol * winEmis * lerp(0.24, 0.30, isOffice);
    // shopfronts and signs carry the street at night
    float shopLit = arcade * (1.0 - shutter) * step(0.25, signR);
    e += lerp(float3(1.0, 0.78, 0.5), float3(0.9, 0.95, 1.0), step(0.6, signR)) * shopLit * 0.38;
    float signLit = signBand * hasSign * step(0.2, signR);
    e += signFace * signLit * 1.3;
    // podium LED / logo panels (department stores)
    float led = isPodium * step(0.7, xc_hash21(float2(floor(u / 18.0), seed * 3.0))) * xc_box(fv, 0.15, 0.9, fwf)
              * step(fh * 1.5, h) * lerp(1.0, fStreet, known);           // street-facing walls only
    e += xc_sign_palette(frac(seed * 4.1 + floor(u / 18.0) * 0.37)) * led * 0.9;
    e += float3(1.0, 0.86, 0.64) * lobGlass * 0.3;                          // lit tower lobbies
    // tower crowns: a lit band under the parapet on some towers
    float crown = step(H - fh * 0.9, h) * (1.0 - step(H - 0.5, h)) * step(0.78, frac(seed * 8.3)) * (isTower + isOffice);
    e += float3(0.95, 0.95, 1.0) * crown * 0.45;
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

    emis = e * night;
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
        sheet = xc_sheet_weather(sheet, p, wpos.z, 1.0, seed, fwp);
        float ribs = xc_line(frac(p.x / 0.25), 0.3, fwp / 0.25) * xc_detail(fwp, 0.5);
        roofCol = lerp(roofCol, sheet * (1.0 - ribs * 0.3), sheetRoof);
    }

    // ponding stains + soot
    float stain = xc_fnoise(p + seed * 37.0, 0.35, fwp);
    float stain2 = xc_fnoise(p - seed * 5.4, 1.3, fwp);
    roofCol *= 1.0 - saturate(stain * 0.9 - 0.25) * 0.35 * weather - stain2 * 0.10;

    // equipment clutter read (tanks, condensers, solar heaters) on a 3 m grid,
    // with a fake sun-side shadow; resolves only when close enough
    float2 cell = floor(p / 3.0);
    float2 fp = frac(p / 3.0);
    float cr = xc_hash21(cell + seed * 3.0);
    float has = step(0.62, cr) * (1.0 - sheetRoof * 0.6);
    float2 cc = float2(0.3 + 0.4 * frac(cr * 7.0), 0.3 + 0.4 * frac(cr * 13.0));
    float box = xc_box(fp.x, cc.x - 0.16, cc.x + 0.16, fwp / 3.0) * xc_box(fp.y, cc.y - 0.12, cc.y + 0.12, fwp / 3.0);
    float2 sh = fp - float2(0.07, -0.07);
    float shadow = xc_box(sh.x, cc.x - 0.16, cc.x + 0.16, fwp / 3.0) * xc_box(sh.y, cc.y - 0.12, cc.y + 0.12, fwp / 3.0);
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
             float night, float litFrac,
             out float3 base, out float rough, out float metal, out float spec, out float3 emis,
             out float3 nrm)
{
    float fwu = fwidth(uv0.x);
    float fwh = fwidth(uv0.y);
    float fwp = max(fwidth(wpos.x), fwidth(wpos.y));
    float code = floor(vc.x * 255.0 + 0.5);
    float arch = floor(code / 16.0);
    float variant = code - arch * 16.0;
    float seed = vc.y * 255.0 / 256.0 + 0.00123;
    float weather = vc.z;
    float flags = vc.w;
    float hero = step(0.97, vc.w);   // Taipei 101 tags A = 250

    float3 bw; float rw; float mw; float sw; float3 ew;
    float3 br; float rr; float mr; float sr; float3 er;
    xc_wall(uv0.x, uv0.y, uv1.x, uv1.y, arch, variant, seed, weather, flags, wpos,
            night, litFrac, fwu, fwh, bw, rw, mw, sw, ew);
    xc_roof(wpos, uv1.x, arch, variant, seed, weather, flags, night, fwp, br, rr, mr, sr, er);
    // schools (ARCH_SCHOOL = 7): explicit route, replaces every wall / roof output (per-building constant:
    // coherent branch; non-school pixels keep the accepted results above untouched)
    [branch] if (abs(arch - 7.0) < 0.5)
    {
        xc_school_wall(uv0.x, uv0.y, uv1.x, uv1.y, variant, seed, weather, flags, night, litFrac, fwu, fwh,
                       bw, rw, mw, sw, ew);
        xc_school_roof(wpos, seed, weather, fwp, br, rr, mr, sr, er);
    }
    float isRoof = smoothstep(0.55, 0.75, N.z);
    float isSoffit = step(N.z, -0.7);
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

    // kerb + sidewalk pavers + scooter rows
    float kerb = xc_box(sd, 0.0, 0.22, fsd);
    float walk = step(0.22, sd) * (1.0 - smoothstep(3.5, 5.0, sd)) * step(0.2, cls);
    float2 pv = frac(p / 0.3);
    float paverLine = max(xc_line(pv.x, 0.12, fwp / 0.3), xc_line(pv.y, 0.12, fwp / 0.3)) * xc_detail(fwp, 0.6);
    float paverR = xc_hash21(floor(p / 60.0));
    float3 paver = lerp(float3(0.31, 0.25, 0.22), float3(0.33, 0.33, 0.31), step(0.5, paverR));
    paver *= 1.0 - paverLine * 0.2;
    // parked scooters (機車) along the kerb: coloured blobs, resolved only near
    float2 sc = float2(dot(p, float2(1.0, 0.0)), dot(p, float2(0.0, 1.0)));
    float2 cellS = floor(sc / float2(0.75, 0.75));
    float sr = xc_hash21(cellS);
    float scooterZone = step(0.45, sd) * (1.0 - step(2.3, sd)) * step(0.2, cls) * (1.0 - step(0.9, cls));
    float hasScooter = step(0.45, sr) * scooterZone;
    float3 scooterCol = xc_pick6(frac(sr * 7.3), float3(0.8, 0.8, 0.78), float3(0.05, 0.05, 0.06),
        float3(0.55, 0.56, 0.58), float3(0.6, 0.08, 0.06), float3(0.1, 0.2, 0.5), float3(0.75, 0.6, 0.1));
    float dS = xc_detail(fwp, 0.75);
    paver = lerp(paver, lerp(paver * 0.8, scooterCol, dS), hasScooter);

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
void xc_prop(float3 wpos, float3 N, float4 vc, float variant, float night, float fwp,
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
    float ribs = xc_line(frac((wpos.x + wpos.y) / 0.19), 0.3, fwp / 0.19) * xc_detail(fwp, 0.4);
    float3 sheet = xc_sheet16(lerp(wallIdx, roofIdx, p1));
    sheet = xc_sheet_weather(sheet, wpos.xy, wpos.z, N.z, roofIdx * 0.37 + wallIdx * 0.11, fwp);
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
