"""Hillside forest mix v0: A (single 紅楠) vs B (two crown forms) comparison sheets from the native evidence folders.

    python tools/forest/hillside_ab_sheets.py <evidence_A> <evidence_B> <movies_dir> <rev_A> <rev_B> <out_dir> [label_A label_B]
Writes ab_still_<view>.jpg (A left / B right, each 1280x720 from the native 1920x1080 PNG), ab_crop_<view>.png (native-pixel 640x360
centre crops side by side) and ab_flight.jpg (flight frames 90 / 180 / 270 / 360, A top row, B bottom row, 640x360 each).
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

EA, EB, MOV, RA, RB, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5], Path(sys.argv[6])
OUT.mkdir(parents=True, exist_ok=True)
F = ImageFont.truetype("arial.ttf", 26)
LAB = ("A  single 紅楠 (D balanced)", "B  mix v0: 紅楠 dome 60 % + crown form B 40 %")
if len(sys.argv) > 8:  # 相思樹 lookdev v1: A = Mix T, B = two-species mix
    LAB = (sys.argv[7], sys.argv[8])
try:
    FJ = ImageFont.truetype("msjh.ttc", 26)
except OSError:
    FJ = F


def label(im, text):
    d = ImageDraw.Draw(im)
    w = int(d.textlength(text, font=FJ)) + 16
    d.rectangle((0, 0, w, 38), fill=(0, 0, 0))
    d.text((8, 4), text, fill=(255, 255, 255), font=FJ)
    return im


for v in ("agl50", "agl200", "agl500"):
    a = Image.open(EA / ("still_%s.png" % v)).convert("RGB").resize((1280, 720), Image.LANCZOS)
    b = Image.open(EB / ("still_%s.png" % v)).convert("RGB").resize((1280, 720), Image.LANCZOS)
    s = Image.new("RGB", (2560, 720))
    s.paste(label(a, LAB[0] + "  " + v), (0, 0))
    s.paste(label(b, LAB[1] + "  " + v), (1280, 0))
    s.save(OUT / ("ab_still_%s.jpg" % v), quality=90)
    ca, cb = Image.open(EA / ("crop_%s.png" % v)).convert("RGB"), Image.open(EB / ("crop_%s.png" % v)).convert("RGB")
    s = Image.new("RGB", (1290, 360), (255, 255, 255))
    s.paste(ca, (0, 0))
    s.paste(cb, (650, 0))
    s.save(OUT / ("ab_crop_%s.png" % v))
fr = (90, 180, 270, 360)
s = Image.new("RGB", (640 * len(fr), 720))
for row, rev in enumerate((RA, RB)):
    for j, f in enumerate(fr):
        mov = Path(os.environ["ACW_AB_MOV_A"]) if row == 0 and os.environ.get("ACW_AB_MOV_A") else MOV  # baseline frames read in place (other worktree)
        im = Image.open(mov / ("hf_flight_forest_%s_01" % rev) / "frames" / ("frame_%04d.png" % f)).convert("RGB").resize((640, 360), Image.LANCZOS)
        if j == 0:
            label(im, "AB"[row])
        s.paste(im, (640 * j, 360 * row))
s.save(OUT / "ab_flight.jpg", quality=88)
print("ok")
