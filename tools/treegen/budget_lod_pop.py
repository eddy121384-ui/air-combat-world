"""LOD-switch difference proxy from forced-LOD captures (project venv: numpy + Pillow).

python tools/treegen/budget_lod_pop.py <ue_capture_dir> <out.json>

For each (candidate, camera) with forced-LOD captures <view>_single_<cand>_lod<N>.png, compares the tree crop of LOD n with LOD n+1 (the pair the
engine switches between) and with the candidate's own highest LOD. Metrics on the crop (same camera, same stage, same frame content):
  mean_dL     |mean luminance difference|  (crown darkens / lightens at the switch)
  blur_mad    mean absolute RGB difference after a 5x5 box blur (what survives sub-pixel noise: massing / density change)
  raw_mad     mean absolute RGB difference of the native pixels (includes leaf-level speckle)
This measures the SIZE of the visible step at a hard switch of a single frame. It does not measure a cross-fade, temporal flicker, or how the engine's
screen-size threshold places the switch (see the doc: not a popping test).
"""
import json
import os
import sys

import numpy as np
from PIL import Image

SRC, OUT = sys.argv[1:3]
CROP = {"sl150": (240, 180), "sl300": (120, 90), "sl500": (80, 60), "sl1000": (48, 36)}


def load(name, view):
    p = os.path.join(SRC, name + ".png")
    if not os.path.isfile(p):
        return None
    im = np.asarray(Image.open(p).convert("RGB"), np.float32) / 255.0
    cw, ch = CROP[view]
    x, y = im.shape[1] // 2 - cw // 2, im.shape[0] // 2 - ch // 2
    return im[y:y + ch, x:x + cw]


def box(a, k=5):
    pad = k // 2
    p = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    out = np.zeros_like(a)
    for dy in range(k):
        for dx in range(k):
            out += p[dy:dy + a.shape[0], dx:dx + a.shape[1]]
    return out / (k * k)


def lum(a):
    return a @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def cmp(a, b):
    return dict(mean_dL=round(abs(float(lum(a).mean() - lum(b).mean())), 4), blur_mad=round(float(np.abs(box(a) - box(b)).mean()), 4),
                raw_mad=round(float(np.abs(a - b).mean()), 4))


res = {}
for cand in "ABCD":
    for view in CROP:
        ims = {n: load("%s_single_%s_lod%d" % (view, cand, n), view) for n in range(4)}
        ims = {n: i for n, i in ims.items() if i is not None}
        if len(ims) < 2:
            continue
        top = min(ims)
        for n in sorted(ims):
            if n + 1 in ims:
                res["%s/%s/lod%d->lod%d" % (cand, view, n, n + 1)] = cmp(ims[n], ims[n + 1])
            if n != top:
                res["%s/%s/lod%d vs lod%d" % (cand, view, n, top)] = cmp(ims[n], ims[top])
json.dump(res, open(OUT, "w"), indent=1)
for k, v in res.items():
    print("%-26s %s" % (k, v))
