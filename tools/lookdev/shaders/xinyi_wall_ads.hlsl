// Taipei large wall ads v0 (M_XinyiWallAds). Own material, own atlas: nothing here is compiled into
// M_XinyiCity or any other XinyiLook material (docs/xinyi-wall-ads-v0-result.md).
//
// Instances: unit plane (tools/lookdev/build_wall_ads.py), UV0 u left -> right, v top -> bottom.
// variant = per-instance custom data 0 = (v + 0.5) / 512, v = cell (0..63) + 64 * lit + 128 * tone (0..3).
// Atlas (tools/lookdev/build_wall_ad_atlas.py, 2048^2, power-of-two aligned bins so mips never mix cells):
//   cells  0..15  256 x 512 at y 0     (8 per row)     tall 1:2
//   cells 16..31  256 x 256 at y 1024  (8 per row)     square
//   cells 32..39  512 x 256 at y 1536  (4 per row)     wide 2:1
// RGB = board face (sRGB), A = night spot-light mask (printed canvas only).

float2 wa_uv(float2 uv0, float variant)
{
    float v = floor(variant * 512.0);
    float cell = v - 64.0 * floor(v / 64.0);
    float isS = step(15.5, cell) * (1.0 - step(31.5, cell));
    float isW = step(31.5, cell);
    float k = cell - 16.0 * isS - 32.0 * isW;
    float cols = lerp(8.0, 4.0, isW);
    float2 size = lerp(float2(256.0, 512.0), float2(256.0, 256.0), isS);
    size = lerp(size, float2(512.0, 256.0), isW);
    float row = floor(k / cols);
    float2 org = float2((k - row * cols) * size.x, 1024.0 * isS + 1536.0 * isW + row * size.y);
    // inset by half a texel of the sampled mip so bilinear filtering never reaches the neighbour cell
    float2 fw = max(fwidth(uv0 * size), float2(1.0, 1.0));
    float2 inset = 0.5 * fw / size;
    float2 uv = clamp(uv0, inset, 1.0 - inset);
    return (org + uv * size) / 2048.0;
}

void wa_shade(float2 uv0, float variant, float4 tx, float night,
              out float3 base, out float rough, out float metal, out float spec, out float3 emis)
{
    float v = floor(variant * 512.0);
    float lit = step(0.5, frac(floor(v / 64.0) * 0.5));
    float tone = floor(v / 128.0);                                  // 0..3: per-board print / exposure variation
    // print response: atlas whites (~0.87 linear) sit far above the city's facade albedos and read as pasted-on
    // stickers; 0.70 keeps a white board ~0.6, still a little louder than the walls and quieter than shop signs
    base = tx.rgb * 0.70 * (0.95 + 0.03 * tone);
    rough = 0.82;                                                   // matte vinyl / paint
    metal = 0.0;
    spec = 0.35;
    // night: a few canvas boards are washed by fixtures along their top edge; dim, never a light box
    float wash = lerp(1.0, 0.35, saturate(uv0.y));
    emis = base * tx.a * lit * wash * 0.55 * night;
}
