"""Before / after sheets from two MRQ still renders of the same stills sequence (frame (i+1)*hold - 1 of each held pose).

    python tools/ntw/forest_world/ba_sheet.py <before_frames> <after_frames> <views.json> <out_dir> [--labels before,after] [--width 960]
Writes <out_dir>/ba_<i>_<name>.jpg (before | after, labelled) and <out_dir>/ba_all.jpg (all pairs stacked, half size).
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("views")
    ap.add_argument("out")
    ap.add_argument("--labels", default="PR #46 (before),distance layers (after)")
    ap.add_argument("--width", type=int, default=960)
    a = ap.parse_args()
    V = json.loads(Path(a.views).read_text(encoding="utf-8"))
    hold, w = V["still_hold_frames"], a.width
    h = w * 9 // 16
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    labels = a.labels.split(",")
    rows = []
    for i, s in enumerate(V["stills"]):
        f = "frame_%04d.png" % ((i + 1) * hold - 1)
        pair = Image.new("RGB", (2 * w, h))
        for k, d in enumerate((a.before, a.after)):
            im = Image.open(Path(d) / f).convert("RGB").resize((w, h), Image.LANCZOS)
            dr = ImageDraw.Draw(im)
            dr.rectangle((0, 0, w, 22), fill=(0, 0, 0))
            dr.text((6, 5), "%s | %s" % (labels[k], s["name"]), fill=(255, 255, 255))
            pair.paste(im, (k * w, 0))
        pair.save(out / ("ba_%02d_%s.jpg" % (i + 1, s["name"])), quality=90)
        rows.append(pair.resize((w, h // 2)))
    sheet = Image.new("RGB", (w, len(rows) * (h // 2)))
    for i, r in enumerate(rows):
        sheet.paste(r, (0, i * (h // 2)))
    sheet.save(out / "ba_all.jpg", quality=85)


if __name__ == "__main__":
    main()
