"""Hillside forest - LOD1 visual recovery v0: Mix D vs Mix C vs a new LOD1 (third column; env ACW_HF_NEW_LABEL / ACW_HF_NEW_TAG name it),
native standalone -game MRQ frames.

    python tools/forest/hillside_lod1_recovery.py <movies_dir> <evidence_D> <evidence_C> <evidence_S> <out_dir> <rev_D> <rev_C> <rev_S> <rev_empty>
        [<alt_D> <alt_C> <alt_S>]

Writes to <out_dir>:
* dcs_still_<view>.jpg  D | C | S (each 1280x720 from the native 1920x1080), views agl50 / agl200 / agl500;
* dcs_crop1to1_agl50.png  native-pixel 640x360 crops, D / C / S side by side, two regions: frame centre and the upper-right LOD1 band
  (where C read pale in the tolerance test);
* dcs_alt_<view>.jpg  the same D | C | S comparison under the alternative sun (alt revisions, stills only), agl50 / agl200;
* pixel metrics (recovery.json): inside the pixels where D and C differ (|lum D - lum C| > 0.03), mean luminance, saturation and B/G of
  D, C and S, and the share of C's offset from D that S removes; same at 200 m and for the alternative sun;
* flight: fly_DCS.mp4 (D | C | S, 3 x 960x540, 60 fps, normal speed), fly_DCS_crop1to1.mp4 (native-pixel 640x540 centre crops),
  flicker proxy (PR #31 flight_analyze.py: mean |I(t+1) - 2 I(t) + I(t-1)| in the union tree mask vs the empty flight) for all three.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

a = sys.argv[1:]
MOV, ED, EC, ES, OUT = Path(a[0]), Path(a[1]), Path(a[2]), Path(a[3]), Path(a[4])
RD, RC, RS, RE = a[5:9]
ALT = a[9:12] if len(a) >= 12 else None
OUT.mkdir(parents=True, exist_ok=True)
FJ = ImageFont.truetype("msjh.ttc", 24)
LAB = {"D": "Mix D  LOD1 14.8k (top + end cards)", "C": "Mix C  LOD1 4.9k (top-only)",
       "S": os.environ.get("ACW_HF_NEW_LABEL", "Mix S  LOD1 6.7k (C + side cards)")}
NEW = os.environ.get("ACW_HF_NEW_TAG", "S")  # short tag of the third column in labels / video captions
HOLD = {"agl50": 47, "agl200": 95, "agl500": 143}


def label(im, text):
    d = ImageDraw.Draw(im)
    w = int(d.textlength(text, font=FJ)) + 16
    d.rectangle((0, 0, w, 36), fill=(0, 0, 0))
    d.text((8, 3), text, fill=(255, 255, 255), font=FJ)
    return im


def lum(x):
    return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]


def still(rev, v):
    tag = rev if "_" in rev else rev + "_01"  # "m8_02" = an explicit MRQ revision
    return Image.open(MOV / ("hf_stills_forest_%s" % tag) / "frames" / ("frame_%04d.png" % HOLD[v])).convert("RGB")


def metrics(ims):
    D, C, S = (np.asarray(i, np.float32) / 255 for i in ims)
    m = np.abs(lum(D) - lum(C)) > 0.03
    out = {"diff_px_share": float(m.mean())}
    for k, X in (("D", D), ("C", C), ("S", S)):
        x = X[m]
        mx, mn = x.max(1), x.min(1)
        out[k] = {"lum": float(lum(x).mean()), "sat": float(((mx - mn) / np.maximum(mx, 1e-6)).mean()),
                  "b_over_g": float((x[:, 2] / np.maximum(x[:, 1], 1e-4)).mean())}
    for q in ("lum", "sat", "b_over_g"):
        off = out["C"][q] - out["D"][q]
        out["recovered_share_" + q] = float((out["C"][q] - out["S"][q]) / off) if abs(off) > 1e-6 else None
    out["mean_abs_lum_diff_to_D"] = {k: float(np.abs(lum(X) - lum(D))[m].mean()) for k, X in (("C", C), ("S", S))}
    return out


def sheet(ims, labels, path, w=1280, h=720):
    s = Image.new("RGB", (w * len(ims), h))
    for j, (im, t) in enumerate(zip(ims, labels)):
        s.paste(label(im.resize((w, h), Image.LANCZOS), t), (w * j, 0))
    s.save(path, quality=90)


rep = {"lighting_base": {}, "lighting_alt": {}}
for v in ("agl50", "agl200", "agl500"):
    ims = [still(r, v) for r in (RD, RC, RS)]
    sheet(ims, [LAB[k] + "  " + v for k in "DCS"], OUT / ("dcs_still_%s.jpg" % v))
    rep["lighting_base"][v] = metrics(ims)
    if v == "agl50":
        s = Image.new("RGB", (3 * 640 + 20, 2 * 360 + 10), (255, 255, 255))
        for row, (x0, y0) in enumerate(((640, 360), (1180, 120))):
            for j, im in enumerate(ims):
                s.paste(im.crop((x0, y0, x0 + 640, y0 + 360)), (j * 650, row * 370))
        s.save(OUT / "dcs_crop1to1_agl50.png")
if ALT:
    for v in ("agl50", "agl200"):
        ims = [still(r, v) for r in ALT]
        sheet(ims, [LAB[k] + "  " + v + "  alt sun 250/28" for k in "DCS"], OUT / ("dcs_alt_%s.jpg" % v))
        rep["lighting_alt"][v] = metrics(ims)

# ----------------------------------------------------------------------------- flight
fdir = {k: MOV / ("hf_flight_forest_%s_01" % r) / "frames" for k, r in (("D", RD), ("C", RC), ("S", RS))}
fe = MOV / ("hf_flight_empty_%s_01" % RE) / "frames"
n = len(list(fe.glob("frame_*.png")))


def lf(folder, f):
    return lum(np.asarray(Image.open(folder / ("frame_%04d.png" % f)).convert("RGB").resize((960, 540), Image.BILINEAR), np.float32) / 255)


L = {k: [] for k in "DCS"}
M = []
for f in range(n):
    e = lf(fe, f)
    cur = {k: lf(fdir[k], f) for k in "DCS"}
    for k in "DCS":
        L[k].append(cur[k])
    M.append(np.any([np.abs(cur[k] - e) > 0.03 for k in "DCS"], axis=0))
fl = {}
for k in "DCS":
    X = np.stack(L[k])
    t2 = np.abs(X[2:] - 2 * X[1:-1] + X[:-2])
    fl[k] = np.array([float(t2[i][M[i + 1]].mean()) for i in range(n - 2)])
rep["flicker"] = {"rule": "mean |I(t+1) - 2 I(t) + I(t-1)| in the union tree mask (|lum - lum(empty)| > 0.03, 960x540)",
                  **{"median_" + k: float(np.median(fl[k])) for k in "DCS"}, **{"p95_" + k: float(np.percentile(fl[k], 95)) for k in "DCS"},
                  "S_over_D_median": float(np.median(fl["S"]) / np.median(fl["D"])), "C_over_D_median": float(np.median(fl["C"]) / np.median(fl["D"])),
                  "frames_S_above_D_by_20pct": int((fl["S"] > 1.2 * fl["D"]).sum())}
(OUT / "recovery.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")

lab = Image.new("RGBA", (2880, 40), (0, 0, 0, 0))
d = ImageDraw.Draw(lab)
for j, k in enumerate("DCS"):
    t = LAB[k]
    w = int(d.textlength(t, font=FJ)) + 16
    d.rectangle((960 * j, 0, 960 * j + w, 40), fill=(0, 0, 0, 190))
    d.text((960 * j + 8, 4), t, fill=(255, 255, 255, 255), font=FJ)
lab.save(OUT / "_lab.png")
lab2 = Image.new("RGBA", (1920, 40), (0, 0, 0, 0))
d = ImageDraw.Draw(lab2)
for j, k in enumerate("DCS"):
    d.rectangle((640 * j, 0, 640 * j + 260, 40), fill=(0, 0, 0, 190))
    d.text((640 * j + 8, 4), "Mix %s  1:1 pixels" % (NEW if k == "S" else k), fill=(255, 255, 255, 255), font=FJ)
lab2.save(OUT / "_lab_c.png")
ff = ["ffmpeg", "-y", "-loglevel", "error"]
for k in "DCS":
    ff += ["-framerate", "60", "-i", str(fdir[k] / "frame_%04d.png")]
enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow"]
subprocess.run(ff + ["-i", str(OUT / "_lab.png"), "-filter_complex",
                     "[0:v]scale=960:540[a];[1:v]scale=960:540[b];[2:v]scale=960:540[c];[a][b][c]hstack=inputs=3[s];[s][3:v]overlay=0:0"] + enc
               + [str(OUT / "fly_DCS.mp4")], check=True)
subprocess.run(ff + ["-i", str(OUT / "_lab_c.png"), "-filter_complex",
                     "[0:v]crop=640:540:640:270[a];[1:v]crop=640:540:640:270[b];[2:v]crop=640:540:640:270[c];[a][b][c]hstack=inputs=3[s];[s][3:v]overlay=0:0"]
               + enc + [str(OUT / "fly_DCS_crop1to1.mp4")], check=True)
for p in ("_lab.png", "_lab_c.png"):
    (OUT / p).unlink()
fr = (90, 180, 270, 360)
s = Image.new("RGB", (640 * len(fr), 360 * 3))
for row, k in enumerate("DCS"):
    for j, f in enumerate(fr):
        im = Image.open(fdir[k] / ("frame_%04d.png" % f)).convert("RGB").resize((640, 360), Image.LANCZOS)
        if j == 0:
            label(im, "Mix " + (NEW if k == "S" else k))
        s.paste(im, (640 * j, 360 * row))
s.save(OUT / "dcs_flight.jpg", quality=88)
print(json.dumps({k: rep["lighting_base"][k] for k in ("agl50", "agl200")}, indent=1))
print(json.dumps(rep["lighting_alt"], indent=1))
print(json.dumps(rep["flicker"], indent=1))
