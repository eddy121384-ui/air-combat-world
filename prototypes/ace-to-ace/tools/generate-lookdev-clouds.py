"""Original, deterministic painted cloud atlas. Requires Pillow + NumPy; no downloads.

Run from any directory: python tools/generate-lookdev-clouds.py
The four cells have transparent gutters for mipmapping and use no source imagery.
"""
from pathlib import Path
import random
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "assets" / "lookdev" / "cloud-atlas.png"
W, H = 512, 256


def noise(seed, width, height):
    rng = np.random.default_rng(seed)
    im = Image.fromarray(rng.integers(0, 256, (height, width), dtype=np.uint8))
    return np.asarray(im.resize((W, H), Image.Resampling.BICUBIC), dtype=float) / 255 - 0.5


def cloud(seed, kind):
    rng = random.Random(seed)
    y, x = np.mgrid[0:H, 0:W]
    edge = np.full((H, W), -10.0)
    pigment = np.zeros((H, W))
    # Interlocking masses with an irregular, low base and tall cumulus crowns.
    lobes = [(W * 0.5, H * 0.73, W * 0.35, H * 0.13)]
    for i in range(11):
        cx = W * (0.13 + 0.74 * i / 10)
        crown = np.sin(np.pi * i / 10) ** 0.7
        height = (0.12 if kind == 2 else 0.30) * crown
        cy = H * (0.71 - height * rng.uniform(0.7, 1.15))
        lobes.append((cx, cy, rng.uniform(35, 65), rng.uniform(24, 43)))
    if kind in (1, 3):
        # Asymmetric vertical towers, deliberately different from the low banks.
        peak_x = W * (0.39 if kind == 1 else 0.63)
        for i in range(4):
            lobes.append((peak_x + rng.uniform(-28, 28), H * (0.61 - i * 0.12),
                          rng.uniform(48, 70) - i * 4, rng.uniform(29, 43)))
        lobes.append((peak_x + 70, H * 0.49, 63, 45))
    for cx, cy, rx, ry in lobes:
        dx, dy = (x - cx) / rx, (y - cy) / ry
        field = 1 - dx * dx - dy * dy
        edge = np.maximum(edge, field)
        # Flat paint shapes, brighter on the upper-left shoulder of each mass.
        light = np.clip(0.52 - dy * 0.38 - dx * 0.13, 0, 1)
        pigment = np.where(field > 0.02, np.maximum(pigment, light), pigment)
    broad = noise(seed + 1, 30, 15)
    brush = noise(seed + 2, 128, 64)
    grain = noise(seed + 3, W, H)
    edge += broad * 0.13 + brush * 0.028
    alpha = np.clip(edge * 15, 0, 1)
    pigment = np.clip(pigment + broad * 0.11 + brush * 0.028, 0, 1)
    # Three paint values with softened joins; cool shadow / pearl / warm cream.
    shadow = np.array([126, 145, 174.0])
    pearl = np.array([195, 200, 213.0])
    cream = np.array([251, 240, 217.0])
    mid = np.clip((pigment - 0.30) / 0.18, 0, 1)[..., None]
    lit = np.clip((pigment - 0.58) / 0.16, 0, 1)[..., None]
    rgb = shadow * (1 - mid) + pearl * mid
    rgb = rgb * (1 - lit) + cream * lit
    rgb += (brush * 3 + grain * 1.5)[..., None]
    # Extend colour into transparent texels to avoid dark mip fringes.
    rgb = np.where((alpha > 0)[..., None], rgb, pearl)
    return Image.fromarray(np.dstack([np.uint8(np.clip(rgb, 0, 255)), np.uint8(alpha * 255)]))


atlas = Image.new("RGBA", (W * 2, H * 2))
for i in range(4):
    atlas.paste(cloud(20261018 + i * 100, i), ((i % 2) * W, (i // 2) * H))
OUT.parent.mkdir(parents=True, exist_ok=True)
atlas.save(OUT, optimize=True)
print(f"{OUT.name}: {atlas.width}x{atlas.height}, {OUT.stat().st_size:,} bytes")
