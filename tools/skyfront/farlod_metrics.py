"""Far-LOD research v2: two targeted image metrics on a run_farlod_ab.ps1 run (fl_<view>_<step>_<cfg>.png).

1. Far-band structure vs PR #57 High (does the impostor layer blur the 5-7 km ridge / valley outlines?): luminance SSIM at 1/4
   resolution over the far band (rows 30-46 % of the frame, where the 5-10 km ranges sit in these poses) between each config and the
   High frame of the same pose. Low-frequency SSIM is insensitive to crown speckle but drops when ridge outlines / slope shading change.
2. Dark dots on open ground (far_range farmland, rows 50-75 %, columns 15-60 %): connected blobs of 2-80 px that are > 25 levels darker
   than the 15 px median around them. PR #57 High has (almost) none; scaled-up field-tree impostors show up as such blobs.
    python tools/skyfront/farlod_metrics.py <run_dir> [out_json]
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def lum(img):
    return np.asarray(img.convert("L"), np.float32)


def blur(x, r):
    k = 2 * r + 1
    p = np.pad(x, r, mode="edge")
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def ssim(a, b, r=3):
    ma, mb = blur(a, r), blur(b, r)
    va, vb = blur(a * a, r) - ma * ma, blur(b * b, r) - mb * mb
    cov = blur(a * b, r) - ma * mb
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return float((((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))).mean())


def dark_dots(img):
    g = img.convert("L")
    a = np.asarray(g, np.float32)
    med = np.asarray(g.filter(ImageFilter.MedianFilter(15)), np.float32)
    m = (med - a) > 25
    h, w = m.shape
    m = m[int(h * 0.50):int(h * 0.75), int(w * 0.15):int(w * 0.60)]
    seen = np.zeros_like(m, bool)
    n = 0
    for y, x in zip(*np.nonzero(m)):
        if seen[y, x]:
            continue
        stack, size = [(y, x)], 0
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            size += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < m.shape[0] and 0 <= nx < m.shape[1] and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        n += 2 <= size <= 80
    return n


def main(run, out=None):
    run = Path(run)
    shots = {}
    for f in run.glob("fl_*_*_*.png"):
        m = re.match(r"fl_(.+)_(\d\d)_(.+)\.png", f.name)
        if m:
            shots.setdefault(m.group(1), {}).setdefault(m.group(3), []).append((int(m.group(2)), f))
    res = {}
    for view, cfgs in shots.items():
        if "high" not in cfgs:
            continue
        ref = Image.open(sorted(cfgs["high"])[-1][1])
        w, h = ref.size
        box = (0, int(h * 0.30), w, int(h * 0.46))
        r4 = lum(ref.crop(box).resize((w // 4, (box[3] - box[1]) // 4), Image.BILINEAR))
        for cfg, lst in cfgs.items():
            img = Image.open(sorted(lst)[-1][1])
            c4 = lum(img.crop(box).resize((w // 4, (box[3] - box[1]) // 4), Image.BILINEAR))
            e = res.setdefault(view, {}).setdefault(cfg, {})
            e["far_band_ssim_vs_high"] = round(ssim(r4, c4), 4)
            if view == "far_range":
                e["dark_dots_farmland"] = dark_dots(img)
    text = json.dumps(res, indent=1)
    print(text)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
