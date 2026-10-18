"""Assemble the game textures for the 紅楠 game version (run with the project venv: numpy + Pillow).

python tools/treegen/machilus_game_textures.py <game_out_dir>

* T_Machilus_LeafAtlas_BC.png  (2048^2 RGBA, sRGB): albedo x (0.55 + 0.45 AO), alpha = coverage; colour dilated into
  transparent texels so mips do not pull in a dark/grey halo.
* T_Machilus_LeafAtlas_N.png   (2048^2 RGB, linear): tangent-space normal, DirectX convention (UE: green = -Y).
  Bake input is Cycles camera space (x right, y up, z INTO the scene) -> tangent (x, y, -z) -> DirectX (x, -y, z).
* T_Machilus_Bark_BC.png / T_Machilus_Bark_N.png (512^2, tileable): periodic noise with the golden bark palette
  (mottling ramp dark/base/lichen, lenticel dots, fine bump). 1 tile = 1 UV unit = 0.6 m on the branch mesh.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

OUT = sys.argv[1]
# optional 2nd argument "acacia" (相思樹 lookdev v1): T_Acacia_* names + fissured bark; default = 紅楠, unchanged
SPECIES = sys.argv[2] if len(sys.argv) > 2 else "machilus"
TEX_STEM = {"acacia": "T_Acacia", "cryptomeria": "T_Cryptomeria"}.get(SPECIES, "T_Machilus")  # cryptomeria: 柳杉 unreal v1
# optional 3rd argument "wide": 2:1 atlas with the clump tiles of a machilus_game.py clump profile in columns 4-7 -> <stem>_LeafAtlasW_*
WIDE = len(sys.argv) > 3 and sys.argv[3] == "wide"
BAKE = os.path.join(OUT, "bake")
TEX = os.path.join(OUT, "textures")
os.makedirs(TEX, exist_ok=True)
TILE, ATLAS = 512, 2048


def load(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255.0


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def dilate(rgb, alpha, iters=24):
    """Push colour outward into alpha==0 texels (average of filled neighbours), so mip-mapping keeps leaf colour."""
    rgb = rgb.copy()
    filled = alpha > 0.02
    for _ in range(iters):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(filled.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            f = np.roll(np.roll(filled, dy, 0), dx, 1)
            acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * f[..., None]
            cnt += f
        grow = (~filled) & (cnt > 0)
        rgb[grow] = acc[grow] / cnt[grow][:, None]
        filled = filled | grow
        if filled.all():
            break
    return rgb


def atlas():
    W = ATLAS * (2 if WIDE else 1)
    bc = np.zeros((ATLAS, W, 4), np.float32)
    nm = np.zeros((ATLAS, W, 3), np.float32)
    cover = []
    tiles = [("p", k, v) for k in range(8) for v in ("top", "end")]
    if WIDE:
        tiles += [("c", k, v) for k in range(8) for v in ("ctop", "cside")]
    for pre, k, view in tiles:
        if True:  # (indent kept from the single-atlas loop)
            alb = load(os.path.join(BAKE, "%s%d_%s_alb.png" % (pre, k, view)))
            nrm = load(os.path.join(BAKE, "%s%d_%s_nrm.png" % (pre, k, view)))
            ao = load(os.path.join(BAKE, "%s%d_%s_ao.png" % (pre, k, view)))[..., 0]
            a = alb[..., 3]
            # albedo pass was rendered with the Standard view transform (sRGB); AO / normal with Raw (linear)
            col = srgb_to_lin(alb[..., :3]) * (0.55 + 0.45 * ao[..., None])
            col = dilate(col, a)
            n = nrm[..., :3] * 2 - 1
            n = np.stack([n[..., 0], n[..., 1], -n[..., 2]], -1)  # Cycles camera (z into scene) -> tangent (z out)
            n[n[..., 2] < 0.05] *= np.array([1, 1, -1])  # guard: anything pointing away is mirrored to face out
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
            n = np.where(a[..., None] > 0.02, n, np.array([0.0, 0.0, 1.0]))
            n = dilate(n, a)
            n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-6
            dx = np.stack([n[..., 0], -n[..., 1], n[..., 2]], -1)  # OpenGL -> DirectX (UE)
            row = (k // 4) + (0 if view in ("top", "ctop") else 2)
            col_i = k % 4 + (4 if pre == "c" else 0)
            ys, xs = row * TILE, col_i * TILE
            bc[ys:ys + TILE, xs:xs + TILE, :3] = lin_to_srgb(col)
            bc[ys:ys + TILE, xs:xs + TILE, 3] = a
            nm[ys:ys + TILE, xs:xs + TILE] = dx * 0.5 + 0.5
            cover.append(dict(proto=("clump%d" % k) if pre == "c" else k, view=view, coverage=float((a > 0.4).mean())))
    stem = TEX_STEM + ("_LeafAtlasW" if WIDE else "_LeafAtlas")
    Image.fromarray((bc * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(TEX, stem + "_BC.png"))
    Image.fromarray((nm * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(TEX, stem + "_N.png"))
    return cover


def periodic_noise(rng, size, beta, f_lo=1.0, f_hi=None, aspect=(1.0, 1.0)):
    w = rng.normal(size=(size, size))
    fy = np.fft.fftfreq(size)[:, None] * size / aspect[1]
    fx = np.fft.fftfreq(size)[None, :] * size / aspect[0]
    f = np.sqrt(fx * fx + fy * fy)
    amp = np.where(f >= f_lo, (np.maximum(f, 1e-6)) ** (-beta / 2), 0.0)
    if f_hi:
        amp *= np.exp(-((f / f_hi) ** 2))
    n = np.real(np.fft.ifft2(np.fft.fft2(w) * amp))
    return (n - n.mean()) / (n.std() + 1e-9)


def ramp(x, stops):
    xs = np.array([s[0] for s in stops])
    out = np.zeros(x.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(x, xs, [s[1][c] for s in stops])
    return out


def bark(size=512, seed=7):
    rng = np.random.default_rng(seed)
    base, dark, lichen = (0.1, 0.08, 0.06), (0.045, 0.036, 0.028), (0.13, 0.125, 0.1)
    lent = (0.14, 0.12, 0.095)
    mott = 0.52 + 0.055 * periodic_noise(rng, size, beta=2.2, f_lo=1.0, f_hi=14.0)
    col = ramp(mott, [(0.38, dark), (0.52, base), (0.66, lichen)])
    # lenticels: jittered torus grid, 38 x 84 cells per tile (golden voronoi scale 38, v stretched 2.2), dots < 0.09
    cu, cv = 38, 84
    jit = rng.uniform(size=(cv, cu, 2))
    yy, xx = np.mgrid[0:size, 0:size]
    pu, pv = (xx + 0.5) / size * cu, (yy + 0.5) / size * cv
    iu, iv = np.floor(pu).astype(int), np.floor(pv).astype(int)
    dmin = np.full((size, size), 9.0)
    for du in (-1, 0, 1):
        for dv in (-1, 0, 1):
            cu_i, cv_i = (iu + du) % cu, (iv + dv) % cv
            px = iu + du + jit[cv_i, cu_i, 0]
            py = iv + dv + jit[cv_i, cu_i, 1]
            dmin = np.minimum(dmin, np.hypot(pu - px, pv - py))
    dots = np.clip(0.45 * (1 - dmin / 0.09), 0, 0.45)
    col = col * (1 - dots[..., None]) + np.array(lent) * dots[..., None]
    fine = 0.5 + 0.18 * periodic_noise(rng, size, beta=1.0, f_lo=6.0, f_hi=120.0)
    h = fine + dots
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    strength = 2.2
    n = np.stack([-gx * strength, gy * strength, np.ones_like(h)], -1)  # DirectX: +green = down the image
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    Image.fromarray((lin_to_srgb(col) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(TEX, "T_Machilus_Bark_BC.png"))
    Image.fromarray(((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(TEX, "T_Machilus_Bark_N.png"))


def bark_fissured(size=512, seed=11, palette=None):
    """相思樹 bark tile (golden tg_materials.fissured_bark palette): grey-brown with pale patches and wandering longitudinal
    fissures (dark grooves along v = along the branch), tileable."""
    rng = np.random.default_rng(seed)
    base, pale, dark = palette or ((0.07, 0.056, 0.044), (0.12, 0.112, 0.098), (0.022, 0.018, 0.015))
    mott = 0.5 + 0.08 * periodic_noise(rng, size, beta=2.2, f_lo=1.0, f_hi=12.0)
    col = ramp(mott, [(0.4, base), (0.62, pale)])
    # fissures: 9 periodic grooves around the circumference, displaced by a smooth noise that varies mostly along v
    warp = periodic_noise(rng, size, beta=2.6, f_lo=1.0, f_hi=10.0, aspect=(4.0, 1.0))
    yy, xx = np.mgrid[0:size, 0:size]
    ph = (xx + 0.5) / size * 9.0 + 0.55 * warp
    saw = ph - np.floor(ph)
    groove = np.clip(1.0 - saw / 0.14, 0.0, 1.0) ** 1.5
    col = col * (1 - groove[..., None]) + np.array(dark) * groove[..., None]
    fine = 0.5 + 0.15 * periodic_noise(rng, size, beta=1.0, f_lo=6.0, f_hi=120.0)
    h = fine - 0.9 * groove
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5
    n = np.stack([-gx * 2.4, gy * 2.4, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    Image.fromarray((lin_to_srgb(col) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(TEX, TEX_STEM + "_Bark_BC.png"))
    Image.fromarray(((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8), "RGB").save(os.path.join(TEX, TEX_STEM + "_Bark_N.png"))


cover = atlas()
if SPECIES == "acacia":
    bark_fissured()
elif SPECIES == "cryptomeria":  # 柳杉 reddish-brown stringy bark (golden fissured_bark palette)
    bark_fissured(seed=13, palette=((0.10, 0.048, 0.028), (0.15, 0.10, 0.075), (0.03, 0.015, 0.01)))
else:
    bark()
json.dump(dict(atlas_coverage=cover), open(os.path.join(TEX, "textures_report.json"), "w"), indent=1)
print("TEXTURES_OK", os.listdir(TEX))
