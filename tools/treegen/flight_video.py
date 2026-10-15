"""Side-by-side A | D videos and LOD-switch frame strips from the native MRQ frames (project venv: numpy + Pillow; needs ffmpeg on PATH).

python tools/treegen/flight_video.py <flight_metrics.json> <movies_dir> <rev> <out_dir> [path_ids,...]

For each path: <out>/flight_<path>_AvsD.mp4 (each panel 1280x720, 60 fps, real time) and <out>/flight_<path>_AvsD_slow4x.mp4 (same frames at 15 fps),
overlay = condition names + triangle budgets, time, slant distance to the patch-centre tree and the CALCULATED LOD mix (A: LOD1/LOD2; D: LOD1/LOD2/LOD3);
a red bar appears for 4 frames at every calculated LOD switch of >= 3 trees. Also <out>/strip_<path>_<cand>_f<frame>.jpg: A (top) and D (bottom), frames
event-4, -2, 0, +2, +4 at 640x360 (native frames, only scaled).
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

MET, MOV, REV, OUT = sys.argv[1:5]
ONLY = sys.argv[5].split(",") if len(sys.argv) > 5 else None
os.makedirs(OUT, exist_ok=True)
M = json.load(open(MET))
F = ImageFont.truetype("arial.ttf", 22)
FS = ImageFont.truetype("arial.ttf", 18)


def frame(c, pid, f):
    return Image.open(os.path.join(MOV, "mrq_%s_%s_%s" % (c, pid, REV), "frames", "frame_%04d.png" % f)).convert("RGB")


def bar(im, text, y, font=F, fill=(0, 0, 0), col=(255, 255, 255)):
    d = ImageDraw.Draw(im)
    w = int(d.textlength(text, font=font)) + 14
    d.rectangle((0, y, w, y + 30), fill=fill)
    d.text((7, y + 3), text, fill=col, font=font)


for pid, r in M.items():
    if ONLY and pid not in ONLY:
        continue
    n = r["frames"]
    tmp = os.path.join(OUT, "_tmp_" + pid)
    os.makedirs(tmp, exist_ok=True)
    ev_frames = {e["frame"]: e for e in r["events"]}
    for f in range(n):
        a, d = frame("A", pid, f).resize((1280, 720), Image.LANCZOS), frame("D", pid, f).resize((1280, 720), Image.LANCZOS)
        bar(a, "A baseline  LOD1 36.7k / LOD2 4.3k tris", 0)
        bar(d, "D balanced  LOD1 14.8k / LOD2 2.0k / LOD3 0.5k tris", 0)
        la, ld = r["lod_counts_A"][f], r["lod_counts_D"][f]
        t = (f - r["flight_start"]) / 60.0
        bar(a, "%s %.0f m/s  t=%+.2fs  frame %d  slant %.0f m  trees LOD0/1/2: %d/%d/%d (calc.)" % (pid, r["speed_mps"], t, f, r["slant_center_m"][f], la[0], la[1], la[2]), 690, FS)
        bar(d, "LOD0/1/2/3: %d/%d/%d/%d (calc.)" % (ld[0], ld[1], ld[2], ld[3]), 690, FS)
        hit = [e for k, e in ev_frames.items() if 0 <= f - k < 4]
        if hit:
            for im, c in ((a, "A"), (d, "D")):
                ee = [e for e in hit if e["cand"] == c]
                if ee:
                    ImageDraw.Draw(im).rectangle((0, 36, 1279, 44), fill=(220, 0, 0))
                    bar(im, "LOD switch: %d trees %s" % (ee[0]["trees"], ",".join(ee[0]["kinds"])), 48, FS, (160, 0, 0))
        s = Image.new("RGB", (2560, 720))
        s.paste(a, (0, 0))
        s.paste(d, (1280, 0))
        s.save(os.path.join(tmp, "f_%04d.png" % f))
    for tag, fps in (("", 60), ("_slow4x", 15)):
        out = os.path.join(OUT, "flight_%s_AvsD%s.mp4" % (pid, tag))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", os.path.join(tmp, "f_%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "20", "-preset", "slow", "-r", "60" if fps == 60 else "30", out], check=True)
        print(out, os.path.getsize(out))
    # strips around the biggest events
    evs = sorted(r["events"], key=lambda e: -e["trees"])
    chosen, used = [], []
    for e in evs:
        if any(abs(e["frame"] - u) < 12 and e["cand"] == c for u, c in used):
            continue
        chosen.append(e)
        used.append((e["frame"], e["cand"]))
        if len(chosen) >= 4:
            break
    for e in chosen:
        cols = [max(0, min(n - 1, e["frame"] + k)) for k in (-4, -2, 0, 2, 4)]
        s = Image.new("RGB", (3200, 720))
        for ci, f in enumerate(cols):
            for ri, c in enumerate("AD"):
                im = frame(c, pid, f).resize((640, 360), Image.LANCZOS)
                bar(im, "%s f%d%s" % (c, f, "  <- switch" if f == e["frame"] else ""), 0, FS)
                s.paste(im, (ci * 640, ri * 360))
        out = os.path.join(OUT, "strip_%s_%s_f%d.jpg" % (pid, e["cand"], e["frame"]))
        s.save(out, quality=90)
        print(out, "event", e)
    for fn in os.listdir(tmp):
        os.remove(os.path.join(tmp, fn))
    os.rmdir(tmp)
