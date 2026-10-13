"""Review sheets for the ForestSpike B0 report (Pillow / numpy). All frames are the harness's own renders.

  python tools/forestspike/make_sheets.py [--dst docs/evidence/forestspike-b0]
Writes (JPEG q86 unless noted):
  ring_switch_sheet.jpg      V3-inbound frames: S off / S on / pixel-origin map for d_S = 500 m, w_S = 100 m
  arms_s_sheet.jpg           4 viewpoints x {A, B} x {S off, S on}
  origin_map_v1.jpg          pixel-origin maps (core N / transition / core S / surround S) at the eight V1 stills
  baseline_hillside_native_crop.png unchanged native 640x360 crop of a ForestSpike frame (decode-ready evidence)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import fs_ids as I  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SAVED = REPO / "unreal" / "ForestSpike" / "Saved" / "ForestSpike"
CAP = SAVED / "captures"
DS, WS = 500.0, 100.0
COL = {"sky": (10, 10, 20), "open": (110, 110, 110), "N_inst": (40, 190, 70), "N_gap": (20, 100, 40),
       "TRANS": (240, 210, 40), "S_core": (225, 60, 50), "S_ctx": (60, 110, 230)}


def font(sz):
    try:
        return ImageFont.truetype("arial.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def origin_map(id_png, ds=DS, ws=WS):
    cls, rng, _, _ = I.load_id(id_png)
    out = np.zeros(cls.shape + (3,), np.uint8)
    out[:] = COL["open"]
    out[cls == 0] = COL["sky"]
    core = np.isin(cls, (2, 5, 6))
    inst = np.isin(cls, (5, 6))
    near, far = rng < ds - ws, rng >= ds
    out[core & near & ~inst] = COL["N_gap"]
    out[core & near & inst] = COL["N_inst"]
    out[core & ~near & ~far] = COL["TRANS"]
    out[core & far] = COL["S_core"]
    out[cls == 4] = COL["S_ctx"]
    return Image.fromarray(out)


def label(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 9 * len(text), 22], fill=(0, 0, 0))
    d.text((4, 3), text, fill=(255, 255, 0), font=font(15))
    return im


def thumb(path_or_im, w, h, text=None):
    im = path_or_im if isinstance(path_or_im, Image.Image) else Image.open(path_or_im).convert("RGB")
    im = im.convert("RGB").resize((w, h), Image.LANCZOS)
    return label(im, text) if text else im


def legend(w=1920, h=34):
    im = Image.new("RGB", (w, h), (20, 20, 20))
    d = ImageDraw.Draw(im)
    x = 8
    for k, t in (("N_inst", "core tree (N, range < d_S-w_S)"), ("N_gap", "core forest ground between crowns (N region)"),
                 ("TRANS", "core forest, range in [d_S-w_S, d_S): S fading in"), ("S_core", "core forest, range >= d_S: S"),
                 ("S_ctx", "surround forest: shared S"), ("open", "open ground"), ("sky", "sky")):
        d.rectangle([x, 8, x + 18, 26], fill=COL[k])
        d.text((x + 24, 9), t, fill=(235, 235, 235), font=font(14))
        x += 24 + 8 * len(t) + 18
    return im


def sheet(images, cols, w, h, caption):
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * w, rows * h + 30), (0, 0, 0))
    for i, im in enumerate(images):
        out.paste(im, ((i % cols) * w, 30 + (i // cols) * h))
    ImageDraw.Draw(out).text((8, 6), caption, fill=(255, 255, 255), font=font(16))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default=str(REPO / "docs" / "evidence" / "forestspike-b0"))
    a = ap.parse_args()
    dst = Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)

    # 1. ring sheet
    ts = (14, 18, 22, 30)
    w, h = 480, 270
    ims = []
    for t in ts:
        ims.append(thumb(CAP / "ring" / ("ring_A_S0_t%02d.png" % t), w, h, "S off  t=%ds" % t))
    for t in ts:
        ims.append(thumb(CAP / "ring" / ("ring_A_S1_t%02d.png" % t), w, h, "S on   t=%ds" % t))
    for t in ts:
        ims.append(thumb(origin_map(CAP / "gate2" / ("id_v3i_t%02d.png" % t)), w, h, "pixel origin t=%ds" % t))
    s = sheet(ims, 4, w, h, "V3 inbound dolly, 200 m AGL, 30 m/s, arm A (30,200 trees = 70 % cover), d_S = 500 m, w_S = 100 m; 1920x1080 frames reduced to 25 %")
    leg = legend()
    out = Image.new("RGB", (s.width, s.height + leg.height))
    out.paste(s, (0, 0))
    out.paste(leg, (0, s.height))
    out.save(dst / "ring_switch_sheet.jpg", quality=86, optimize=True)

    # 2. arms x S sheet
    ims = []
    w, h = 480, 270
    for pid in ("v1_agl50_p15", "v1_agl200_p10", "v1_agl500_p35", "v1_agl1000_p45"):
        for arm in ("A", "B"):
            for sv in (0, 1):
                ims.append(thumb(CAP / "visual" / ("vis_%s_%s_S%d.png" % (pid, arm, sv)), w, h,
                                 "%s arm %s S %s" % (pid[3:], arm, "on" if sv else "off")))
    sheet(ims, 4, w, h, "Arms A / B x far layer S off / on at four V1 viewpoints; d_S = 500 m, w_S = 100 m, 70 % cover; 1920x1080 reduced to 25 %"
          ).save(dst / "arms_s_sheet.jpg", quality=86, optimize=True)

    # 3. origin maps at V1
    poses = json.loads((Path(__file__).resolve().parent / "viewpoints.json").read_text())["poses"]
    v1 = [p["id"] for p in poses if p["group"] == "V1"]
    ims = []
    for pid in v1:
        ims.append(thumb(origin_map(CAP / "gate" / ("id_%s.png" % pid)), w, h, pid[3:]))
    s = sheet(ims, 4, w, h, "Where forest pixels come from at the eight V1 stills (d_S = 500 m, w_S = 100 m)")
    leg = legend()
    out = Image.new("RGB", (s.width, s.height + leg.height))
    out.paste(s, (0, 0))
    out.paste(leg, (0, s.height))
    out.save(dst / "origin_map_v1.jpg", quality=86, optimize=True)

    # 4. native crop (unchanged pixels)
    Image.open(CAP / "visual" / "vis_v1_agl200_p10_A_S1.png").convert("RGB").crop((0, 720, 640, 1080)).save(
        dst / "native_crop_agl200_A_S1.png", optimize=True)
    print("sheets ->", dst)


if __name__ == "__main__":
    main()
