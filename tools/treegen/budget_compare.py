"""Comparison sheets for the tree-budget experiment (project venv: Pillow).

python tools/treegen/budget_compare.py <ue_capture_dir> <out_dir> [ref_capture_dir ref_prefix]

UE captures are named <view>_<single|patch>_<A|B|C>[_lodN].png (tl_budget_capture.py). Writes
  cmp_single_<view>.jpg  full frames A | B | C (top) and nearest-neighbour crops around the tree (bottom)
  cmp_patch_<view>.jpg   same for the 100-tree same-tree patch
  cmp_lods_<view>_<cand>.jpg  forced-LOD ladders
Crops are cut from the native 1920x1080 frames around the image centre (the cameras aim at the tree) and magnified with
nearest-neighbour so individual pixels stay visible. A label bar (not part of the render) names each panel.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SRC, OUT = sys.argv[1:3]
os.makedirs(OUT, exist_ok=True)
try:
    FONT = ImageFont.truetype("arial.ttf", 24)
except OSError:
    FONT = ImageFont.load_default()
# (crop w, crop h, zoom) so every crop panel is 640x480 or so; the tree is ~188 / 94 / 56 / 28 px wide at 150 / 300 / 500 / 1000 m
CROP = {"close": (480, 360, 1), "front": (480, 360, 1), "sl150": (240, 180, 2), "sl300": (120, 90, 4), "sl500": (80, 60, 6), "sl1000": (48, 36, 10)}
PATCH_CROP = {"sl150": (480, 360, 1), "sl300": (480, 360, 1), "sl500": (480, 360, 1), "sl1000": (480, 360, 1)}
NAMES = {"A": "A baseline", "B": "B aggressive 3-LOD", "C": "C aggressive+far", "D": "D balanced+far"}


def label(im, text):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w = int(d.textlength(text, font=FONT)) + 14
    d.rectangle((0, 0, w, 32), fill=(0, 0, 0))
    d.text((7, 3), text, fill=(255, 255, 255), font=FONT)
    return im


def load(name):
    p = os.path.join(SRC, name + ".png")
    return Image.open(p).convert("RGB") if os.path.isfile(p) else None


def crop(im, cw, ch, zoom):
    x, y = im.width // 2 - cw // 2, im.height // 2 - ch // 2
    return im.crop((x, y, x + cw, y + ch)).resize((cw * zoom, ch * zoom), Image.NEAREST)


def sheet(rows, path):
    h = sum(max(i.height for i in r) for r in rows)
    w = max(sum(i.width for i in r) for r in rows)
    s = Image.new("RGB", (w, h), (20, 20, 20))
    y = 0
    for r in rows:
        x = 0
        for im in r:
            s.paste(im, (x, y))
            x += im.width
        y += max(i.height for i in r)
    s.save(path, quality=90)
    print(path, s.size)


for mode in ("single", "patch"):
    for view in ("close", "front", "sl150", "sl300", "sl500", "sl1000"):
        ims = {c: load("%s_%s_%s" % (view, mode, c)) for c in "ABCD"}
        if any(v is None for v in ims.values()):
            continue
        cw, ch, z = (CROP if mode == "single" else PATCH_CROP).get(view, (None,) * 3)
        if cw is None:
            continue
        full = [label(ims[c].resize((480, 270), Image.LANCZOS), "%s (frame /4)" % NAMES[c]) for c in "ABCD"]
        cr = [label(crop(ims[c], cw, ch, z), "%s  crop x%d" % (NAMES[c], z)) for c in "ABCD"]
        sheet([full, cr], os.path.join(OUT, "cmp_%s_%s.jpg" % (mode, view)))

for cand, view, lods in (("A", "sl150", (0, 1, 2)), ("B", "sl150", (0, 1, 2)), ("D", "sl150", (0, 1, 2)), ("A", "sl300", (0, 1, 2)), ("C", "sl300", (0, 1, 2, 3)), ("D", "sl300", (0, 1, 2, 3)), ("C", "sl1000", (2, 3)), ("D", "sl1000", (2, 3))):
    ims = [load("%s_single_%s_lod%d" % (view, cand, l)) for l in lods]
    if any(i is None for i in ims):
        continue
    cw, ch, z = CROP[view]
    auto = load("%s_single_%s" % (view, cand))
    row = [label(crop(i, cw, ch, z), "%s forced LOD%d  x%d" % (cand, l, z)) for i, l in zip(ims, lods)]
    sheet([row], os.path.join(OUT, "cmp_lods_%s_%s.jpg" % (view, cand)))
