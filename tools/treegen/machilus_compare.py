"""Golden (Blender Cycles) vs game version (UE5.8) comparison sheets (project venv: Pillow).

python tools/treegen/machilus_compare.py <golden_dir> <golden_agl_dir> <ue_capture_dir> <prefix> <out_dir>

* cmp_<view>.jpg      front / oblique / top / close: golden | UE (automatic LOD), native pixels side by side.
* cmp_front_lods.jpg  front view: golden | UE LOD0 (auto) | forced LOD1 | forced LOD2.
* cmp_agl50.jpg / cmp_agl200.jpg: full frames golden | UE, then nearest-neighbour zoomed crops around the tree:
  golden | UE auto | UE LOD0 | LOD1 | LOD2 (zoom x4 at 50 m AGL, x8 at 200 m AGL: individual pixels stay visible).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

GOLD, GOLD_AGL, UE, PFX, OUT = sys.argv[1:6]
os.makedirs(OUT, exist_ok=True)
try:
    FONT = ImageFont.truetype("arial.ttf", 26)
except OSError:
    FONT = ImageFont.load_default()


def label(im, text):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w = int(d.textlength(text, font=FONT)) + 16
    d.rectangle((0, 0, w, 36), fill=(0, 0, 0))
    d.text((8, 4), text, fill=(255, 255, 255), font=FONT)
    return im


def load(path):
    return Image.open(path).convert("RGB")


def row(ims, labels, scale=1.0):
    ims = [label(im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS), t) for im, t in zip(ims, labels)]
    s = Image.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims)), (20, 20, 20))
    x = 0
    for im in ims:
        s.paste(im, (x, 0))
        x += im.width
    return s


def stack(rows):
    w = max(r.width for r in rows)
    s = Image.new("RGB", (w, sum(r.height for r in rows)), (20, 20, 20))
    y = 0
    for r in rows:
        s.paste(r, (0, y))
        y += r.height
    return s


def ue(name):
    return load(os.path.join(UE, "%s_%s.png" % (PFX, name)))


for view in ("front", "oblique", "top", "close"):
    g = load(os.path.join(GOLD, "v1_%s.jpg" % view))
    row([g, ue(view + "_auto")], ["Blender golden (Cycles)", "UE5.8 game version (auto LOD)"], 0.5).save(
        os.path.join(OUT, "cmp_%s.jpg" % view), quality=92)

g = load(os.path.join(GOLD, "v1_front.jpg"))
row([g, ue("front_auto"), ue("front_lod1"), ue("front_lod2")],
    ["golden", "UE LOD0 (auto here)", "UE LOD1 (forced)", "UE LOD2 (forced)"], 0.5).save(os.path.join(OUT, "cmp_front_lods.jpg"), quality=92)


def crop_box(im_ue_tree, im_ue_empty=None, cx=960, cy=535, w=240, h=135):
    return (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


for view, zoom, (w, h) in (("agl50", 4, (360, 200)), ("agl200", 8, (180, 100))):
    g = load(os.path.join(GOLD_AGL, "v1_%s.png" % view))
    a = ue(view + "_auto")
    box = crop_box(a, cx=960, cy=535, w=w, h=h)
    full = row([g, a], ["golden %s (full frame)" % view, "UE auto LOD (full frame)"], 0.5)
    crops = [im.crop(box).resize((w * zoom // 2, h * zoom // 2), Image.NEAREST) for im in
             (g, a, ue(view + "_lod0"), ue(view + "_lod1"), ue(view + "_lod2"))]
    crow = row(crops, ["golden x%d" % zoom, "UE auto", "UE LOD0", "UE LOD1", "UE LOD2"])
    stack([full, crow]).save(os.path.join(OUT, "cmp_%s.jpg" % view), quality=92)
print("COMPARE_OK", sorted(os.listdir(OUT)))
