"""Contact sheets for review: iteration history and the final view set (PIL, run with the project venv).

python tools/treegen/make_sheets.py <machilus_out_dir> <evidence_dir> [sheet_stem=machilus]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

src, dst = sys.argv[1], sys.argv[2]
stem = sys.argv[3] if len(sys.argv) > 3 else "machilus"
os.makedirs(dst, exist_ok=True)
try:
    font = ImageFont.truetype("arial.ttf", 22)
except OSError:
    font = ImageFont.load_default()


def label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 12 + 12 * len(text), 32), fill=(0, 0, 0))
    d.text((6, 4), text, fill=(255, 255, 255), font=font)
    return im


its = sorted(
    (d for d in os.listdir(src) if d.startswith("it") and d[2:].isdigit()), key=lambda d: int(d[2:])
)
views = ["front", "oblique", "top"]
its = [it for it in its if any(os.path.exists(os.path.join(src, it, f"{it}_{v}.png")) for v in views)]
W, H = 480, 270
sheet = Image.new("RGB", (W * len(views), H * len(its)), (20, 20, 20))
for r, it in enumerate(its):
    for c, v in enumerate(views):
        p = os.path.join(src, it, f"{it}_{v}.png")
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
        sheet.paste(label(im, f"{it} {v}"), (c * W, r * H))
sheet.save(os.path.join(dst, f"{stem}_iterations_sheet.jpg"), quality=88)
print("iterations:", its)

# final set: native-resolution JPEGs + turntable sheet
final = os.path.join(src, "v1")
for v in ("front", "oblique", "top", "close"):
    p = os.path.join(final, f"v1_{v}.png")
    if os.path.exists(p):
        Image.open(p).convert("RGB").save(os.path.join(dst, f"v1_{v}.jpg"), quality=93)
tts = sorted(f for f in os.listdir(final) if f.startswith("tt_az")) if os.path.isdir(final) else []
if tts:
    ims = [Image.open(os.path.join(final, f)).convert("RGB") for f in tts]
    w, h = ims[0].size
    tt = Image.new("RGB", (w * 3, h * 2))
    for i, (f, im) in enumerate(zip(tts, ims)):
        tt.paste(label(im, f[3:8]), ((i % 3) * w, (i // 3) * h))
    tt.save(os.path.join(dst, "v1_turntable.jpg"), quality=90)
    print("turntable:", tts)
