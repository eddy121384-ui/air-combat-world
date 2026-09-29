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
//         b = weathering, a = flags/255
//
// Cost discipline (iPhone 11 Pro-class lower bound): ALU only, no textures,
// no loops, every high-frequency pattern is fwidth-filtered toward its mean
// so distant facades converge to stable averages instead of shimmering.
// ============================================================================

// TEXCOORD_2 carries RGBA8 data packed as (R*256+G, B*256+A); returns 0..1.
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
// Walls
// ----------------------------------------------------------------------------
void xc_wall(float u, float h, float H, float fh, float arch, float variant, float seed,
             float weather, float flags, float3 wpos, float night, float litFrac,
             float fwu, float fwh,
             out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float isOffice = step(3.5, arch) * (1.0 - step(4.5, arch));
    float isPodium = step(4.5, arch);
    float isTower = step(2.5, arch) * (1.0 - step(3.5, arch));
    float isOld = 1.0 - step(2.5, arch);            // low / walkup / huaxia
    float core = frac(floor(flags * 255.0 + 0.5) * 0.5) * 2.0;   // bit0
    float podiumPart = step(0.5, frac(floor(flags * 255.0 / 4.0 + 0.001) * 0.5));  // bit2
    float rooftop = step(0.5, frac(floor(flags * 255.0 / 8.0 + 0.001) * 0.5));     // bit3

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

    // --- iron window cages (鐵窗) + AC units — the Taipei signature ------------
    float cageP = lerp(0.62, 0.34, step(1.5, arch));            // walkups most caged
    cageP *= lerp(1.0, 0.45, step(4.0, fi));                     // fewer high up
    cageP *= isOld * (1.0 - core * 0.7);
    float caged = step(1.0 - cageP, frac(cellR * 7.1));
    float barsV = xc_line(frac(u / 0.13), 0.22, fwu / 0.13);
    float barsH = xc_line(frac(h / 0.42), 0.12, fwh / 0.42);
    float cageBars = max(barsV, barsH) * xc_detail(fwu, 0.26);
    float cageMask = caged * xc_box(fu, wx0 - 0.04, wx1 + 0.04, fwb) * xc_box(fv, wy0 - 0.05, wy1 + 0.04, fwf);
    float3 cageCol = lerp(float3(0.62, 0.62, 0.60), float3(0.25, 0.17, 0.12), step(0.6, frac(cellR * 13.7)));
    // far away a cage reads as a lighter, busier window
    float cageCover = lerp(0.45, cageBars, xc_detail(fwu, 0.26)) * cageMask * (1.0 - tPier);

    float acP = lerp(0.55, 0.35, step(1.5, arch)) * (isOld + isTower * 0.5) * (1.0 - isOffice);
    float hasAC = step(1.0 - acP, frac(cellR * 3.7)) * step(0.5, fi);
    float acLeft = step(0.5, frac(cellR * 5.9));
    float acx0 = lerp(0.60, 0.06, acLeft);
    float ac = hasAC * xc_box(fu, acx0, acx0 + 0.24, fwb) * xc_box(fv, 0.05, 0.25, fwf) * dBay;
    float acGrille = xc_line(frac(u / 0.05), 0.3, fwu / 0.05) * xc_detail(fwu, 0.1);
    float3 acCol = lerp(float3(0.74, 0.72, 0.66), float3(0.34, 0.34, 0.33), acGrille * 0.6);

    // --- floor slabs / balcony edges / curtain-wall mullions ------------------
    float slab = xc_box(fv, 0.0, lerp(0.07, 0.10, isTower), fwf) * dFloor;
    float mull = xc_line(fu, 0.05, fwb) * isOffice * dBay;
    float spandrel = (1.0 - xc_box(fv, 0.14, 0.97, fwf)) * isOffice * dFloor;

    // --- street level: 騎樓 arcade + shopfronts + signage band ------------------
    float street = (1.0 - step(fh * 1.05, h)) * (1.0 - podiumPart * 0.0);
    float arcade = street * isOld * (1.0 - core * 0.6);
    float signBand = step(fh * 1.02, h) * (1.0 - step(fh * 1.55, h)) * isOld * (1.0 - core * 0.8);
    float signCell = floor(u / (bw * (0.8 + 0.8 * colR)));
    float signR = xc_hash21(float2(signCell, seed * 29.0));
    float hasSign = step(0.35, signR);
    float3 signCol = xc_sign_palette(frac(signR * 9.7));
    // pseudo-lettering: blocky glyph rhythm on signs (near only)
    float glyph = step(0.45, xc_hash21(floor(float2(u / 0.55, h / 0.5)) + signCell)) * xc_detail(fwu, 0.8);

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
    float shutter = step(0.7, xc_hash21(float2(signCell, 3.0)));
    float3 shop = lerp(float3(0.07, 0.065, 0.06), float3(0.42, 0.42, 0.42), shutter);
    c = lerp(c, shop, arcade * 0.92);
    float3 signFace = lerp(signCol, signCol * 0.25 + 0.6, glyph * 0.5);
    c = lerp(c, signFace, signBand * hasSign);

    // metal-sheet rooftop additions (頂樓加蓋) on small rooftop records
    float ribs = xc_line(frac(u / 0.2), 0.3, fwu / 0.2) * xc_detail(fwu, 0.4);
    float3 sheet = xc_pick4(frac(seed * 2.9 + variant * 0.13),
        float3(0.22, 0.34, 0.48), float3(0.70, 0.71, 0.70), float3(0.36, 0.22, 0.14), float3(0.60, 0.58, 0.50));
    c = lerp(c, sheet * (1.0 - ribs * 0.25), rooftop * isOld);

    // parapet cap: light concrete band at the roof line
    float parapet = step(H - 0.45, h) * (1.0 - isOffice);
    c = lerp(c, float3(0.58, 0.57, 0.54), parapet * 0.8);

    // --- humid weathering: sill streaks, top grime, splash at the base -------
    float streakN = xc_noise1(u * 1.9 + seed * 17.0);
    float underSill = (1.0 - smoothstep(0.0, wy0, fv)) * xc_box(fu, wx0, wx1, fwb) * dBay;
    float streak = saturate(streakN * 1.4 - 0.35) * (0.4 + 0.6 * underSill);
    float topGrime = smoothstep(H - 2.5 * fh, H, h) * 0.5;
    float splash = 1.0 - smoothstep(0.0, 1.2, h);
    float grime = saturate((streak * 0.7 + topGrime + splash * 0.6) * weather);
    grime *= 1.0 - isOffice * 0.8;
    c *= 1.0 - grime * 0.42;
    c = lerp(c, c * float3(0.92, 0.95, 0.92), weather * 0.5 * isOld);   // green-grey humid cast

    // --- material response ------------------------------------------------------
    float glassAmt = win * (1.0 - cageCover * 0.7) * (1.0 - arcade);
    rough = lerp(0.82, 0.10, glassAmt);
    rough = lerp(rough, 0.05, glassAmt * isOffice);
    rough = lerp(rough, 0.55, ac);
    rough = lerp(rough, 0.35, frame);
    metal = mull * 0.9 + ac * 0.1 + frame * 0.6 + glassAmt * isOffice * 0.35;
    spec = lerp(0.35, 1.0, glassAmt);

    // --- night -------------------------------------------------------------------
    float litP = litFrac * lerp(1.0, 0.8, isOffice);
    litP *= 1.0 - step(0.5, rooftop) * 0.6;
    float floorZone = lerp(xc_hash21(float2(fi, seed * 5.0)), xc_hash31(float3(floor(bi / 8.0), fi, seed * 5.0)), 0.35);   // office floors lit as bands
    float litR = lerp(cellR, floorZone, isOffice);
    float lit = step(1.0 - litP, litR);
    float curtain = lerp(0.55 + 0.45 * frac(cellR * 23.0), 0.15 + 0.85 * frac(cellR * 31.0), step(0.5, isOld + isTower));
    float3 lightCol = xc_window_light(frac(cellR * 17.3), isOffice * 0.2 + isPodium);
    float winLight = win * (1.0 - cageCover * 0.5) * (1.0 - arcade) * (1.0 - balc * 0.5);
    // far distance: average lit coverage instead of per-window noise
    float litMean = litP * winMean * lerp(0.8, 0.45, isOffice);
    float bandLit = step(1.0 - litP, xc_hash21(float2(fi, seed * 5.0))) * winMean;
    float farLit = lerp(litMean, bandLit * 0.9, isOffice * dFloor);
    float winEmis = lerp(farLit, lit * winLight * curtain, dBay * dFloor);
    float3 e = lightCol * winEmis * lerp(0.24, 0.30, isOffice);
    // shopfronts and signs carry the street at night
    float shopLit = arcade * (1.0 - shutter) * step(0.25, signR);
    e += float3(1.0, 0.85, 0.62) * shopLit * 1.2;
    float signLit = signBand * hasSign * step(0.2, signR);
    e += signFace * signLit * 1.3;
    // podium LED / logo panels (department stores)
    float led = isPodium * step(0.7, xc_hash21(float2(floor(u / 18.0), seed * 3.0))) * xc_box(fv, 0.15, 0.9, fwf)
              * step(fh * 1.5, h);
    e += xc_sign_palette(frac(seed * 4.1 + floor(u / 18.0) * 0.37)) * led * 0.9;
    // tower crowns: a lit band under the parapet on some towers
    float crown = step(H - fh * 0.9, h) * (1.0 - step(H - 0.5, h)) * step(0.78, frac(seed * 8.3)) * (isTower + isOffice);
    e += float3(0.95, 0.95, 1.0) * crown * 0.45;
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

    float3 sheet = xc_pick4(frac(seed * 2.9 + variant * 0.13),
        float3(0.22, 0.34, 0.48), float3(0.70, 0.71, 0.70), float3(0.36, 0.22, 0.14), float3(0.60, 0.58, 0.50));
    float sheetRoof = max(rooftop, step(0.72, frac(seed * 1.9)) * isOld);
    float ribs = xc_line(frac(p.x / 0.25), 0.3, fwp / 0.25) * xc_detail(fwp, 0.5);
    roofCol = lerp(roofCol, sheet * (1.0 - ribs * 0.3), sheetRoof);

    // ponding stains + soot
    float stain = xc_noise2(p * 0.35 + seed * 13.0);
    float stain2 = xc_noise2(p * 1.3 - seed * 7.0);
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

    base = roofCol;
    rough = lerp(0.9, 0.5, sheetRoof);
    metal = sheetRoof * 0.3;
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
    float3 glass = float3(0.10, 0.20, 0.19);
    // slight darkening at the foot of each module (under the ledge above)
    glass *= lerp(0.8, 1.05, tsec);
    float3 frame = float3(0.52, 0.58, 0.56);
    float3 c = lerp(glass, frame, saturate(mull + floorLine) * 0.8);
    float3 trim = float3(0.56, 0.60, 0.58);
    float3 gold = float3(0.80, 0.60, 0.26);
    c = lerp(trim, c, glassFlag);
    c = lerp(c, gold, isOrn);
    base = c;
    rough = lerp(0.45, 0.06, glassFlag * (1.0 - saturate(mull + floorLine)));
    rough = lerp(rough, 0.35, isOrn);
    metal = lerp(0.6, 0.1, glassFlag) * (1.0 - isOrn) + isOrn * 0.9;
    spec = 0.5;
    // Night: warm-white floodlit modules brightening toward each flared top,
    // lit corner notches, glowing crown; office floors partially lit inside.
    float band = smoothstep(0.35, 1.0, tsec) * isModule;
    float officeLit = step(0.6, xc_hash21(float2(floor(u / 2.8), floor(h / fh)))) * glassFlag;
    float3 flood = float3(1.0, 0.78, 0.45);
    float3 e = flood * band * band * 0.9 * glassFlag;
    e += float3(0.85, 0.93, 1.0) * officeLit * xc_box(fv, 0.2, 0.85, fwh / fh) * 0.08 * (1.0 - band) * xc_detail(fwu, 5.6);
    e += flood * isModule * 0.04 * glassFlag;
    e += flood * step(9.5, section) * (1.0 - step(10.5, section)) * 1.0;   // pinnacle
    e += gold * isOrn * 0.6;
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
    float isRoof = smoothstep(0.55, 0.75, N.z);
    float isSoffit = step(N.z, -0.7);
    base = lerp(bw, br, isRoof);
    rough = lerp(rw, rr, isRoof);
    metal = lerp(mw, mr, isRoof);
    spec = lerp(sw, sr, isRoof);
    emis = lerp(ew, er, isRoof);
    base = lerp(base, float3(0.2, 0.2, 0.2), isSoffit);

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
// vc.x = urban basin floor weight, vc.y = forest weight, vc.z = ridge.
// The urban floor is a texture-free "city carpet": block/street rhythm by day
// and a sodium/LED light field at night, so the basin reads as continuous
// Taipei out to the mountains without any extra geometry.
// ----------------------------------------------------------------------------
void xc_backdrop(float3 wpos, float3 N, float4 vc, float night, float fwp,
                 out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float urban = vc.x;
    float forest = vc.y;
    float ridge = vc.z;
    // forest: subtropical broadleaf, dark and humid, lighter on ridges
    float fn = xc_noise2(p * 0.004) * 0.6 + xc_noise2(p * 0.02) * 0.4;
    float3 forestCol = lerp(float3(0.055, 0.085, 0.045), float3(0.10, 0.14, 0.07), fn);
    forestCol = lerp(forestCol, float3(0.13, 0.15, 0.10), saturate(ridge * 1.6 - 0.8));
    float steep = smoothstep(0.35, 0.7, 1.0 - N.z);
    forestCol = lerp(forestCol, float3(0.16, 0.16, 0.13), steep * 0.4);

    // city carpet: superblocks (~90 m) split by streets, fine parcels (~14 m)
    float2 blk = p / 90.0;
    float2 bi = floor(blk);
    float2 bf = frac(blk);
    float streetW = 0.12 + 0.06 * xc_hash21(bi * 1.7);
    float street = 1.0 - xc_box(bf.x, streetW * 0.5, 1.0 - streetW * 0.5, fwp / 90.0)
                       * xc_box(bf.y, streetW * 0.5, 1.0 - streetW * 0.5, fwp / 90.0);
    float2 pc = floor(p / 14.0);
    float pr = xc_hash21(pc);
    float3 roofs = xc_pick4(pr, float3(0.26, 0.26, 0.25), float3(0.36, 0.355, 0.34),
                            float3(0.22, 0.25, 0.24), float3(0.31, 0.27, 0.24));
    float dParcel = xc_detail(fwp, 14.0);
    roofs = lerp(float3(0.28, 0.28, 0.27), roofs, dParcel);
    float3 cityCol = lerp(roofs, float3(0.10, 0.10, 0.10), street * lerp(0.5, 0.85, xc_detail(fwp, 30.0)));
    // pockets of park / riverside green in the basin
    float greenPocket = smoothstep(0.72, 0.8, xc_noise2(p * 0.0012 + 7.0));
    cityCol = lerp(cityCol, float3(0.12, 0.17, 0.09), greenPocket);

    float3 lowland = lerp(float3(0.20, 0.24, 0.15), cityCol, urban);
    base = lerp(lowland, forestCol, forest);
    rough = 0.92;
    metal = 0.0;
    spec = 0.3;

    // night light field: sodium arterials + white LED side streets + windows
    float lamps = street * lerp(0.5, 1.0, step(0.5, xc_hash21(bi)));
    float3 sodium = float3(1.0, 0.55, 0.20);
    float3 led = float3(0.85, 0.92, 1.0);
    float winSpeck = step(0.62, xc_hash21(floor(p / 5.0) + 3.1)) * (1.0 - street);
    float3 winCol = lerp(float3(0.8, 0.9, 1.0), float3(1.0, 0.75, 0.45), step(0.5, xc_hash21(floor(p / 5.0))));
    float3 near = lamps * lerp(led, sodium, step(0.4, xc_hash21(bi + 9.0))) * 0.45 + winSpeck * winCol * 0.25;
    float3 far = float3(1.0, 0.70, 0.42) * 0.035;                 // mean glow when unresolved
    float dLamp = xc_detail(fwp, 20.0);
    float3 glow = lerp(far, near, dLamp);
    // clustered density: arterial grids and neighbourhood cores, dark gaps
    float cluster = xc_noise2(p * 0.0025) * 0.65 + xc_noise2(p * 0.011) * 0.35;
    glow *= smoothstep(0.30, 0.75, cluster) * 1.8 + 0.1;
    float spark = step(0.985, xc_hash21(floor(p / 35.0))) * (1.0 - dLamp);   // bright far points
    glow += float3(1.0, 0.8, 0.55) * spark * 0.25;
    emis = glow * urban * (1.0 - greenPocket) * night;
}

// ----------------------------------------------------------------------------
// Xinyi ground (Landscape material). gt = ground data texture sample
// (tools/lookdev/build_ground.py): r = road SDF (0.5 kerb, +-12 m), g = green,
// b = road class, a = water. Texture sampling stays outside this function so it
// remains portable; everything else is ALU.
// ----------------------------------------------------------------------------
float xc_street_light(float sd, float cls, float2 p)
{
    // fake street-light pools: brighter on arterials, uneven along the road
    float pools = 0.55 + 0.45 * xc_noise1(dot(p, float2(0.061, 0.043)) + xc_noise1(p.x * 0.013));
    float onRoad = 1.0 - smoothstep(2.0, 6.0, sd);
    return onRoad * pools * lerp(0.35, 1.0, cls);
}

void xc_ground(float3 wpos, float3 N, float4 gt, float night, float fwp,
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
    float patchN = xc_noise2(p * 0.08);
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
    float n = xc_noise2(p * 0.05);
    float3 plaza = lerp(float3(0.22, 0.22, 0.215), float3(0.29, 0.285, 0.27), n);

    float3 grass = lerp(float3(0.09, 0.15, 0.06), float3(0.15, 0.21, 0.08), xc_noise2(p * 0.12));
    float hill = saturate(smoothstep(22.0, 45.0, wpos.z) + smoothstep(0.12, 0.25, 1.0 - N.z));
    float fn = xc_noise2(p * 0.01) * 0.6 + xc_noise2(p * 0.08) * 0.4;
    float3 forest = lerp(float3(0.05, 0.08, 0.04), float3(0.10, 0.14, 0.065), fn);
    float3 waterCol = float3(0.05, 0.08, 0.08);

    float3 c = plaza;
    c = lerp(c, paver, walk);
    c = lerp(c, grass, saturate(green * 1.2) * (1.0 - road));
    c = lerp(c, forest, hill * (1.0 - road) * (1.0 - green * 0.5));
    c = lerp(c, float3(0.55, 0.55, 0.53), kerb * step(0.2, cls));
    c = lerp(c, asphalt, road);
    c = lerp(c, waterCol, water);
    base = c;
    rough = lerp(0.88, 0.75, road);
    rough = lerp(rough, 0.05, water);
    metal = 0.0;
    spec = 0.4;

    float sl = xc_street_light(sd, cls, p);
    float spill = step(3.0, sd) * (1.0 - hill) * 0.25;           // shopfront spill onto lots
    float3 lampCol = lerp(float3(1.0, 0.55, 0.22), float3(0.90, 0.95, 1.0), step(0.6, cls));
    emis = c * (lampCol * sl * 1.1 + float3(1.0, 0.85, 0.65) * spill * 0.5) * night;
}

// Road paint: vc = COLOR_0 (sRGB-ish paint colour). Shares the street-light fill.
void xc_paint(float3 wpos, float4 vc, float4 gt, float night, float fwp,
              out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float2 p = float2(wpos.x, wpos.y);
    float3 c = vc.xyz * vc.xyz;                       // approx sRGB -> linear
    // worn paint: tyre wear breaks up lines/crossings
    float wear = xc_noise2(p * 1.7) * 0.6 + xc_noise2(p * 0.23) * 0.4;
    c = lerp(c, float3(0.12, 0.12, 0.12), saturate(wear - 0.55) * 1.2);
    base = c * 0.85;
    rough = 0.6;
    metal = 0.0;
    spec = 0.5;
    float sd = (gt.x - 0.5) * 24.0;
    float sl = xc_street_light(sd, gt.z, p);
    float3 lampCol = lerp(float3(1.0, 0.62, 0.30), float3(0.95, 0.97, 1.0), step(0.6, gt.z));
    emis = base * lampCol * sl * 1.1 * night;
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
