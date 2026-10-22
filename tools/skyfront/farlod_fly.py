"""Far-LOD research: temporal check of a run_farlod_ab.ps1 -Fly run (frame-indexed 300 m/s straight flight, one PNG per frame per cfg).

Per config:
  * far-band temporal change: mean |frame(t) - frame(t-1)| over the far band (rows around the horizon), per frame
  * pops: frames whose far-band change is > 3x the median of the surrounding 15 frames (same rule as PR #49 flight_temporal_check)
  * full-frame spikes (same rule on the whole frame)
  * shimmer: median far-band change (flicker of sub-pixel cards / dither shows up here, motion parallax is identical across configs)
Outputs <out>/fly_<cfg>.mp4, fly_side_by_side_<a>_vs_<b>.mp4, fly_temporal.json, a few stills. Frames are not copied.
    python tools/skyfront/farlod_fly.py <run_dir> <out_dir> [cfg_a cfg_b]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def series(frames, band):
    prev, far, full = None, [], []
    for f in frames:
        im = np.asarray(Image.open(f).convert("L"), np.float32)
        if prev is not None:
            d = np.abs(im - prev)
            far.append(float(d[band[0]:band[1]].mean()))
            full.append(float(d.mean()))
        prev = im
    return np.array(far), np.array(full)


def spikes(x, k=7, ratio=3.0):
    out = []
    for i in range(len(x)):
        lo, hi = max(0, i - k), min(len(x), i + k + 1)
        med = float(np.median(np.r_[x[lo:i], x[i + 1:hi]])) if hi - lo > 1 else 0.0
        if med > 0 and x[i] > ratio * med:
            out.append(i)
    return out


def main(run, out, *cfgs):
    run, out = Path(run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    found = sorted({m.group(1) for f in run.glob("fly_*_*.png") for m in [re.match(r"fly_(.+)_\d{4}\.png", f.name)] if m})
    cfgs = list(cfgs) or found
    rep = {}
    for c in cfgs:
        frames = sorted(run.glob("fly_%s_[0-9][0-9][0-9][0-9].png" % c))
        h = Image.open(frames[0]).size[1]
        band = (int(h * 0.36), int(h * 0.56))
        far, full = series(frames, band)
        rep[c] = {"frames": len(frames), "far_band_rows": band, "far_change_median": round(float(np.median(far)), 3),
                  "far_change_p95": round(float(np.percentile(far, 95)), 3), "far_pops": spikes(far), "full_spikes": spikes(full)}
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", str(run / ("fly_%s_%%04d.png" % c)), "-c:v", "libx264", "-crf", "18",
                        "-pix_fmt", "yuv420p", str(out / ("fly_%s.mp4" % c))], check=True)
        for k in (0, len(frames) // 2, len(frames) - 1):
            Image.open(frames[k]).convert("RGB").save(out / ("fly_%s_f%04d.jpg" % (c, k)), quality=90)
    if len(cfgs) >= 2:
        a, b = cfgs[0], cfgs[1]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out / ("fly_%s.mp4" % a)), "-i", str(out / ("fly_%s.mp4" % b)), "-filter_complex",
                        "[0:v][1:v]hstack=inputs=2", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                        str(out / ("fly_side_by_side_%s_vs_%s.mp4" % (a, b)))], check=True)
    (out / "fly_temporal.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    for c, r in rep.items():
        print(c, {k: (len(v) if isinstance(v, list) and k != "far_band_rows" else v) for k, v in r.items()})


if __name__ == "__main__":
    main(*sys.argv[1:])
