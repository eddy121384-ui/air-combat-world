"""Hillside forest - low-precision tolerance test: Mix D (form A on the D balanced chain) vs Mix C (form A on PR #31's aggressive C chain).

    python tools/forest/hillside_lod_tolerance.py <movies_dir> <rev_D> <rev_C> <rev_empty> <evidence_D> <evidence_C> <out_dir>

Inputs are the native standalone -game MRQ frames (same cameras / flight / stage; only form A's LOD chain differs) and the hillside_frames.py
evidence folders. Writes to <out_dir>:
* dc_still_<view>.jpg  D | C side by side (each 1280x720 from the native 1920x1080), dc_crop_<view>.png native-pixel 640x360 centre crops,
  dc_diff_<view>.jpg  |D - C| luminance x4 (where the two differ at all);
* fly_DvsC.mp4  D | C side by side at normal speed (2 x 1280x720, 60 fps); fly_DvsC_crop1to1.mp4  native-pixel 960x540 centre crops side by
  side (flicker is easier to judge unscaled);
* flicker.json + flicker_chart.png: per frame, inside the tree mask (|lum(forest) - lum(empty flight)| > 0.03 at 960x540, trees + their
  shadows), mean |I(t+1) - 2 I(t) + I(t-1)| (PR #31 flight_analyze.py flicker proxy) for D and C; plus the D - C luminance gap in the mask.
  The camera moves, so the proxy also contains motion; only the D vs C comparison on the identical path is meaningful.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MOV, RD, RC, RE, ED, EC, OUT = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], Path(sys.argv[5]), Path(sys.argv[6]), Path(sys.argv[7])
OUT.mkdir(parents=True, exist_ok=True)
FJ = ImageFont.truetype("msjh.ttc", 26)
LAB = {"D": "Mix D  form A on D balanced (LOD1 14.8k / LOD2 2.0k)", "C": "Mix C  form A on aggressive C (LOD1 4.9k / LOD2 1.4k)"}


def label(im, text, y=0):
    d = ImageDraw.Draw(im)
    w = int(d.textlength(text, font=FJ)) + 16
    d.rectangle((0, y, w, y + 38), fill=(0, 0, 0))
    d.text((8, y + 4), text, fill=(255, 255, 255), font=FJ)
    return im


def lum(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


for v in ("agl50", "agl200", "agl500"):
    d = Image.open(ED / ("still_%s.png" % v)).convert("RGB")
    c = Image.open(EC / ("still_%s.png" % v)).convert("RGB")
    s = Image.new("RGB", (2560, 720))
    s.paste(label(d.resize((1280, 720), Image.LANCZOS), LAB["D"] + "  " + v), (0, 0))
    s.paste(label(c.resize((1280, 720), Image.LANCZOS), LAB["C"] + "  " + v), (1280, 0))
    s.save(OUT / ("dc_still_%s.jpg" % v), quality=90)
    s = Image.new("RGB", (1290, 360), (255, 255, 255))
    s.paste(d.crop((640, 360, 1280, 720)), (0, 0))
    s.paste(c.crop((640, 360, 1280, 720)), (650, 0))
    s.save(OUT / ("dc_crop_%s.png" % v))
    dl = np.abs(lum(np.asarray(d, np.float32) / 255) - lum(np.asarray(c, np.float32) / 255))
    Image.fromarray(np.clip(dl * 4 * 255, 0, 255).astype(np.uint8)).resize((960, 540), Image.BILINEAR).save(OUT / ("dc_diff_%s.jpg" % v), quality=88)

# ----------------------------------------------------------------------------- flight
fd, fc, fe = (MOV / ("hf_flight_%s_%s_01" % (k, r)) / "frames" for k, r in (("forest", RD), ("forest", RC), ("empty", RE)))
n = len(list(fd.glob("frame_*.png")))
if n != len(list(fc.glob("frame_*.png"))) or n != len(list(fe.glob("frame_*.png"))):
    raise SystemExit("frame counts differ")


def lf(folder, f):
    return lum(np.asarray(Image.open(folder / ("frame_%04d.png" % f)).convert("RGB").resize((960, 540), Image.BILINEAR), np.float32) / 255)


L = {"D": [], "C": []}
M = []
for f in range(n):
    e = lf(fe, f)
    a, b = lf(fd, f), lf(fc, f)
    L["D"].append(a)
    L["C"].append(b)
    M.append((np.abs(a - e) > 0.03) | (np.abs(b - e) > 0.03))
rep = {"frames": n, "rule": "mean |I(t+1) - 2 I(t) + I(t-1)| inside the union tree mask (|lum - lum(empty)| > 0.03, 960x540)"}
for k in ("D", "C"):
    X = np.stack(L[k])
    t2 = np.abs(X[2:] - 2 * X[1:-1] + X[:-2])
    rep["flicker_" + k] = [0.0] + [float(t2[i][M[i + 1]].mean()) if M[i + 1].any() else 0.0 for i in range(n - 2)] + [0.0]
fD, fC = np.array(rep["flicker_D"][1:-1]), np.array(rep["flicker_C"][1:-1])
rep["lum_gap_D_minus_C_in_mask"] = [float((L["D"][i] - L["C"][i])[M[i]].mean()) if M[i].any() else 0.0 for i in range(n)]
rep["summary"] = {"flicker_D_median": float(np.median(fD)), "flicker_C_median": float(np.median(fC)),
                  "flicker_D_p95": float(np.percentile(fD, 95)), "flicker_C_p95": float(np.percentile(fC, 95)),
                  "flicker_C_over_D_median": float(np.median(fC) / np.median(fD)),
                  "frames_C_above_D_by_20pct": int((fC > 1.2 * fD).sum()),
                  "mean_lum_gap_D_minus_C": float(np.mean(rep["lum_gap_D_minus_C_in_mask"])),
                  "mask_share_median": float(np.median([m.mean() for m in M]))}
(OUT / "flicker.json").write_text(json.dumps(rep) + "\n", encoding="utf-8")
# chart
W, H = 1200, 360
im = Image.new("RGB", (W, H), (255, 255, 255))
dr = ImageDraw.Draw(im)
top = max(fD.max(), fC.max()) * 1.05
for arr, col in ((fD, (40, 90, 200)), (fC, (220, 90, 20))):
    pts = [(40 + i * (W - 60) / (len(arr) - 1), H - 30 - v / top * (H - 60)) for i, v in enumerate(arr)]
    dr.line(pts, fill=col, width=2)
F = ImageFont.truetype("arial.ttf", 16)
dr.text((45, 8), "flicker proxy per frame inside the tree mask: blue = Mix D, orange = Mix C (median D %.4f, C %.4f)" % (np.median(fD), np.median(fC)), fill=(0, 0, 0), font=F)
dr.text((45, H - 24), "frame 1 .. %d (60 fps, 7.5 s canopy pass)" % (n - 2), fill=(0, 0, 0), font=F)
im.save(OUT / "flicker_chart.png")

lab = OUT / "_dc_label.png"
st = Image.new("RGBA", (2560, 44), (0, 0, 0, 0))
d = ImageDraw.Draw(st)
for x, t in ((0, LAB["D"]), (1280, LAB["C"])):
    w = int(d.textlength(t, font=FJ)) + 16
    d.rectangle((x, 0, x + w, 44), fill=(0, 0, 0, 190))
    d.text((x + 8, 4), t, fill=(255, 255, 255, 255), font=FJ)
st.save(lab)
st.crop((0, 0, 1920, 44)).save(OUT / "_dc_label_crop.png")
ff = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "60", "-i", str(fd / "frame_%04d.png"), "-framerate", "60", "-i", str(fc / "frame_%04d.png")]
enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "slow"]
subprocess.run(ff + ["-i", str(lab), "-filter_complex", "[0:v]scale=1280:720[a];[1:v]scale=1280:720[b];[a][b]hstack[s];[s][2:v]overlay=0:0"] + enc
               + [str(OUT / "fly_DvsC.mp4")], check=True)
lab2 = Image.new("RGBA", (1920, 44), (0, 0, 0, 0))
d = ImageDraw.Draw(lab2)
for x, t in ((0, "Mix D (1:1 pixels, centre)"), (960, "Mix C (1:1 pixels, centre)")):
    w = int(d.textlength(t, font=FJ)) + 16
    d.rectangle((x, 0, x + w, 44), fill=(0, 0, 0, 190))
    d.text((x + 8, 4), t, fill=(255, 255, 255, 255), font=FJ)
lab2.save(OUT / "_dc_label_crop.png")
subprocess.run(ff + ["-i", str(OUT / "_dc_label_crop.png"), "-filter_complex",
                     "[0:v]crop=960:540:480:270[a];[1:v]crop=960:540:480:270[b];[a][b]hstack[s];[s][2:v]overlay=0:0"] + enc
               + [str(OUT / "fly_DvsC_crop1to1.mp4")], check=True)
for p in (lab, OUT / "_dc_label_crop.png"):
    p.unlink()
print(json.dumps(rep["summary"], indent=1))
