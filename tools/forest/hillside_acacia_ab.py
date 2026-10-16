"""相思樹 lookdev v1: native-pixel A (Mix T) vs B (+ 相思樹) numbers and the side-by-side flyover video.

    python tools/forest/hillside_acacia_ab.py <evidence_A> <evidence_B> <movies_A> <movies_B> <rev_A> <rev_B> <out_dir>
Per still view (agl50 / agl200 / agl500), on the tree mask of each version (forest vs empty frame of the same pose, hillside_frames.py rule):
* canopy share in frame and tree-pixel median brightness / saturation / hue;
* colour diversity: std of the mean hue / brightness over 32 x 32 px blocks of canopy (stand-scale colour variation - the "species
  colour blocks" question), and the share of canopy blocks whose mean hue is > 6 deg yellower than the A median (yellow-olive patches);
* changed pixels: share of the frame where B differs from A (> 6/255) - where the 相思樹 actually show.
Video: fly_AB_<revA>_<revB>.mp4 = A | B flyover (2 x 960x540, 60 fps, H.264 crf 24), ffmpeg on PATH.
Writes <out_dir>/acacia_ab_report.json.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

EA, EB, MA, MB, RA, RB, OUT = sys.argv[1:8]
EA, EB, MA, MB, OUT = Path(EA), Path(EB), Path(MA), Path(MB), Path(OUT)
OUT.mkdir(parents=True, exist_ok=True)


def hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    c = mx - mn
    s = np.where(mx > 1e-6, c / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    nz = c > 1e-6
    i = nz & (mx == r)
    h[i] = (60 * ((g[i] - b[i]) / c[i]) + 360) % 360
    i = nz & (mx == g) & ~(mx == r)
    h[i] = 60 * ((b[i] - r[i]) / c[i]) + 120
    i = nz & (mx == b) & ~(mx == r) & ~(mx == g)
    h[i] = 60 * ((r[i] - g[i]) / c[i]) + 240
    return h, s, mx


def frame(movies, tag, f):
    return np.asarray(Image.open(movies / tag / "frames" / ("frame_%04d.png" % f)).convert("RGB"), np.float32) / 255.0


def stats(img, mask, hue_ref=None):
    h, s, v = hsv(img)
    B = 32
    H, W = mask.shape[0] // B, mask.shape[1] // B
    m = mask[:H * B, :W * B].reshape(H, B, W, B).mean(axis=(1, 3))
    hb = (h * mask)[:H * B, :W * B].reshape(H, B, W, B).sum(axis=(1, 3)) / np.maximum(m * B * B, 1)
    vb = (v * mask)[:H * B, :W * B].reshape(H, B, W, B).sum(axis=(1, 3)) / np.maximum(m * B * B, 1)
    ok = m > 0.6  # blocks that are mostly canopy
    out = {"canopy_share": round(float(mask.mean()), 4), "median_value": round(float(np.median(v[mask])), 4),
           "median_saturation": round(float(np.median(s[mask])), 4), "median_hue_deg": round(float(np.median(h[mask])), 2),
           "block_hue_std_deg": round(float(hb[ok].std()), 3), "block_value_std": round(float(vb[ok].std()), 4), "blocks": int(ok.sum())}
    if hue_ref is not None:
        out["share_blocks_yellower_6deg_than_A_median"] = round(float((hb[ok] < hue_ref - 6).mean()), 4)
    return out


V = json.loads((EA / "frames_report.json").read_text(encoding="utf-8"))["stills"]
rep = {"rev_A": RA, "rev_B": RB, "stills": {}}
for i, name in enumerate(V):
    f = V[name]["frame"]
    a, ae = frame(MA, "hf_stills_forest_%s_01" % RA, f), frame(MA, "hf_stills_empty_%s_01" % RA, f)
    b, be = frame(MB, "hf_stills_forest_%s_01" % RB, f), frame(MB, "hf_stills_empty_%s_01" % RB, f)
    ma, mb = np.abs(a - ae).max(-1) > 6 / 255, np.abs(b - be).max(-1) > 6 / 255
    sa = stats(a, ma)
    sb = stats(b, mb, hue_ref=sa["median_hue_deg"])
    sa["share_blocks_yellower_6deg_than_A_median"] = stats(a, ma, hue_ref=sa["median_hue_deg"])["share_blocks_yellower_6deg_than_A_median"]
    rep["stills"][name] = {"A": sa, "B": sb, "changed_pixel_share": round(float((np.abs(a - b).max(-1) > 6 / 255).mean()), 4)}
fa, fb = MA / ("hf_flight_forest_%s_01" % RA) / "frames" / "frame_%04d.png", MB / ("hf_flight_forest_%s_01" % RB) / "frames" / "frame_%04d.png"
vid = OUT / ("fly_AB_%s_%s.mp4" % (RA, RB))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "60", "-i", str(fa), "-framerate", "60", "-i", str(fb), "-filter_complex",
                "[0:v]scale=960:540[a];[1:v]scale=960:540[b];[a][b]hstack=inputs=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24",
                "-preset", "slow", str(vid)], check=True)
rep["video"] = vid.name
(OUT / "acacia_ab_report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
print(json.dumps(rep, indent=1))
