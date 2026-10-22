"""Far-LOD research: evidence from a run_farlod_ab.ps1 run (SKYFL lines + fl_<view>_<step>_<cfg>.png screenshots).

Writes into <out>:
  stats.json             per (view, cfg): GPU p50 of both visits (order 0..N-1 and N-1..0), mean, draws, primitives, memory
  ab_<view>.jpg          control | candidate side by side (full frame, downscaled) for each candidate pair
  crop_<view>_<a>_vs_<b>.jpg  native-pixel crop of the far band (rows around the horizon, 2-8 km), A over B
  diff_<view>_<a>_vs_<b>.png  |A - B| x4 heat map (where the candidate changed the image)
    python tools/skyfront/farlod_report.py <run_dir> <out_dir> [pairs=high:high_fi,high:high_t22_fi,ultra:ultra_fi]
"""
import json
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

LINE = re.compile(r"SKYFL step=(\d+) view=(\S+) cfg=(\S+) (.*)")


def parse(log):
    rows = []
    for ln in Path(log).read_text(encoding="utf-8", errors="ignore").splitlines():
        m = LINE.search(ln)
        if m:
            kv = dict(x.split("=") for x in m.group(4).split())
            rows.append({"step": int(m.group(1)), "view": m.group(2), "cfg": m.group(3), **{k: float(v) for k, v in kv.items()}})
    return rows


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 12 + 9 * len(text), 26], fill=(0, 0, 0))
    d.text((6, 6), text, fill=(255, 255, 255))
    return img


def main(run, out, pairs="high:high_fi,high:high_t22_fi,ultra:ultra_fi"):
    run, out = Path(run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = parse(run / "farlod.log")
    stats = {}
    for r in rows:
        s = stats.setdefault(r["view"], {}).setdefault(r["cfg"], {"gpu_p50": [], "gpu_min": [], "frame_p50": [], "draws": [], "prims": [], "mem_mb": [], "steps": []})
        s["gpu_p50"].append(r["gpu_p50_ms"])
        s["gpu_min"].append(r["gpu_min_ms"])
        s["frame_p50"].append(r["frame_p50_ms"])
        s["draws"].append(r["draws_p50"])
        s["prims"].append(r["prims_p50"])
        s["mem_mb"].append(r["used_phys_mb"])
        s["steps"].append(r["step"])
    for v in stats.values():
        for s in v.values():
            s["gpu_p50_mean"] = round(statistics.mean(s["gpu_p50"]), 1)
            s["draws_mean"] = round(statistics.mean(s["draws"]))
            s["prims_mean"] = round(statistics.mean(s["prims"]))
    (out / "stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    for view, cfgs in stats.items():
        shots = {}
        for cfg, s in cfgs.items():
            f = run / ("fl_%s_%02d_%s.png" % (view, s["steps"][-1], cfg))   # second visit: warm caches
            if f.is_file():
                shots[cfg] = Image.open(f).convert("RGB")
        sheet = []
        for pr in pairs.split(","):
            a, b = pr.split(":")
            if a not in shots or b not in shots:
                continue
            A, B = shots[a], shots[b]
            w, h = A.size
            sheet.append(np.hstack([np.asarray(label(A.resize((w // 2, h // 2)), a)), np.asarray(label(B.resize((w // 2, h // 2)), b))]))
            # far band: the horizon sits a little above mid-frame for these near-level poses; native pixels, centre 60 % of the width
            y0, y1 = int(h * 0.36), int(h * 0.56)
            x0, x1 = int(w * 0.2), int(w * 0.8)
            ca, cb = A.crop((x0, y0, x1, y1)), B.crop((x0, y0, x1, y1))
            Image.fromarray(np.vstack([np.asarray(label(ca, a)), np.asarray(label(cb, b))])).save(out / ("crop_%s_%s_vs_%s.jpg" % (view, a, b)), quality=92)
            d = np.abs(np.asarray(A, np.int16) - np.asarray(B, np.int16)).mean(axis=2)
            Image.fromarray(np.clip(d * 4, 0, 255).astype(np.uint8)).resize((w // 2, h // 2)).save(out / ("diff_%s_%s_vs_%s.png" % (view, a, b)))
            cfgs[b].setdefault("mean_abs_diff_vs", {})[a] = round(float(d.mean()), 2)
        if sheet:
            Image.fromarray(np.vstack(sheet)).save(out / ("ab_%s.jpg" % view), quality=88)
    (out / "stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    for view, cfgs in stats.items():
        for cfg, s in cfgs.items():
            print("%-14s %-12s gpu_p50 %s mean %.1f | draws %d prims %d | diff %s" % (view, cfg, s["gpu_p50"], s["gpu_p50_mean"], s["draws_mean"],
                                                                                  s["prims_mean"], s.get("mean_abs_diff_vs", "")))


if __name__ == "__main__":
    main(*sys.argv[1:])
