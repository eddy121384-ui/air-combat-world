"""Moving-camera visual gate: path geometry, calculated LOD timeline and image-sequence metrics for A vs D (project venv: numpy + Pillow).

python tools/treegen/flight_analyze.py <flight_paths.json> <movies_dir> <rev> <out_dir>

Inputs: <movies_dir>/mrq_<A|D|E>_<path>_<rev>/frames/frame_NNNN.png (native Movie Render Queue frames, 1920x1080, 60 fps fixed step; E = same camera, empty ground).
Per path it computes
  * camera pose per frame (linear interpolation of the sequence keys), slant distance to the patch-centre tree and to every tree of the 10x10 patch,
  * the LOD each tree should use per frame for A (thresholds 0.5 / 0.15) and D (0.5 / 0.15 / 0.06), screen = 3.08 * 8.377 m * scale / slant [calculated, PR #30
    convention, not read from the engine], and the frames where >= 3 trees switch LOD ("events"),
  * tree masks: |luminance(frame) - luminance(E frame)| > 0.03 at 960x540 (trees + their cast shadows; the ground, sky and exposure are identical in E),
  * per-frame metrics inside the mask: footprint fraction ("cover"), mean luminance, dark fraction (< 0.12), and |second difference| of each over time
    (a jump detector that ignores the smooth camera-driven trend); A-vs-D blurred (5x5) mean absolute difference inside the union mask; a flicker proxy =
    mean |I(t+1) - 2 I(t) + I(t-1)| inside the mask.
Writes <out_dir>/flight_metrics.json and one chart per path. None of these is a verdict by itself; the frames are the evidence.
"""
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CUTS = {"A": (0.5, 0.15), "D": (0.5, 0.15, 0.06)}
THR = 0.03


def patch():
    rng = random.Random(20261015)
    tr = [(0.0, 0.0, 1.0)]
    for i in range(-5, 5):
        for j in range(-5, 5):
            if i == 0 and j == 0:
                continue
            x, y = 25.0 * i + rng.uniform(-4, 4), 25.0 * j + rng.uniform(-4, 4)
            s = rng.uniform(0.85, 1.15)
            rng.uniform(0, 360)
            tr.append((x, y, s))
    return np.array(tr)


TREES = patch()


def pose(path, n):
    ks = path["keys"]
    f = [k["frame"] for k in ks]
    return np.stack([np.interp(np.arange(n), f, [k["pos_m"][i] for k in ks]) for i in range(3)], 1)


def lod_counts(pos, cand):
    d = np.sqrt((pos[:, None, 0] - TREES[None, :, 0]) ** 2 + (pos[:, None, 1] - TREES[None, :, 1]) ** 2 + (pos[:, None, 2] - 6.0) ** 2)
    scr = 3.08 * 8.377 * TREES[None, :, 2] / d
    return sum((scr < c).astype(int) for c in CUTS[cand]), d


def _one(p):
    return np.asarray(Image.open(p).convert("L").resize((960, 540), Image.BILINEAR), np.float32) / 255.0


def load(pool, folder, n):
    ps = [os.path.join(folder, "frame_%04d.png" % f) for f in range(n)]
    return np.stack(list(pool.map(_one, ps, chunksize=8)))


def box(a, k=5):
    pad = k // 2
    p = np.pad(a, ((0, 0), (pad, pad), (pad, pad)), mode="edge")
    o = np.zeros_like(a)
    for dy in range(k):
        for dx in range(k):
            o += p[:, dy:dy + a.shape[1], dx:dx + a.shape[2]]
    return o / (k * k)


def d2(x):
    x = np.asarray(x, float)
    return np.concatenate([[0], np.abs(x[2:] - 2 * x[1:-1] + x[:-2]), [0]])


def chart(path_id, rec, out, font):
    n = len(rec["slant_center_m"])
    W, H, M = 1500, 960, 50
    img = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    names = ["slant to patch-centre tree (m, black) and trees per LOD x10 (calc.; red = A, blue = D)", "tree footprint fraction (trees + shadows), A red / D blue",
             "tree-region mean luminance, A red / D blue", "|2nd difference| of footprint fraction (jump detector), A red / D blue"]
    ph = (H - 2 * M) // 4 - 10
    fl0, fl1 = rec["flight_start"], rec["flight_end"]
    xs = lambda f: M + (W - 2 * M) * f / max(1, n - 1)  # noqa: E731
    tops = [M // 2 + i * (ph + 14) for i in range(4)]

    def series(panel, ys, color, lo, hi):
        y0 = tops[panel]
        d.line([(xs(i), y0 + ph - (min(max(v, lo), hi) - lo) / (hi - lo + 1e-12) * ph) for i, v in enumerate(ys)], fill=color, width=2)

    for pi, t in enumerate(names):
        d.rectangle((M, tops[pi], W - M, tops[pi] + ph), outline=(160, 160, 160))
        d.text((M + 4, tops[pi] + 2), t, fill=(0, 0, 0), font=font)
        for f in (fl0, fl1):
            d.line([(xs(f), tops[pi]), (xs(f), tops[pi] + ph)], fill=(120, 120, 120))
    series(0, rec["slant_center_m"], (0, 0, 0), 0, 1000)
    for cand, col in (("A", (200, 0, 0)), ("D", (0, 100, 220))):
        for lod in (1, 2, 3):
            series(0, [c[lod] * 10 for c in rec["lod_counts_" + cand]], col, 0, 1000)
    for key, pi in (("cover", 1), ("lumT", 2)):
        a, b = np.array(rec[key + "_A"]), np.array(rec[key + "_D"])
        lo, hi = min(a.min(), b.min()), max(a.max(), b.max())
        series(pi, a, (200, 0, 0), lo, hi)
        series(pi, b, (0, 100, 220), lo, hi)
    a, b = np.array(rec["d2_cover_A"]), np.array(rec["d2_cover_D"])
    hi = max(a.max(), b.max()) * 1.05 + 1e-12
    series(3, a, (200, 0, 0), 0, hi)
    series(3, b, (0, 100, 220), 0, hi)
    for e in rec["events"]:
        col = (200, 0, 0) if e["cand"] == "A" else (0, 100, 220)
        for pi in range(4):
            d.line([(xs(e["frame"]), tops[pi] + ph - 8), (xs(e["frame"]), tops[pi] + ph)], fill=col, width=3)
    d.text((M, H - 24), "%s  frames 0..%d (60 fps); grey verticals = flight start / end; ticks = calculated LOD switches (>= 3 trees)" % (path_id, n - 1), fill=(0, 0, 0), font=font)
    img.save(out)


def main():
    PATHS, MOV, REV, OUT = sys.argv[1:5]
    os.makedirs(OUT, exist_ok=True)
    P = json.load(open(PATHS))
    font = ImageFont.truetype("arial.ttf", 15)
    result = {}
    with ProcessPoolExecutor(max_workers=12) as pool:
        for pid, path in P["paths"].items():
            fs = {c: os.path.join(MOV, "mrq_%s_%s_%s" % (c, pid, REV), "frames") for c in "ADE"}
            if not all(os.path.isdir(v) for v in fs.values()):
                continue
            n = min(len(os.listdir(v)) for v in fs.values())
            A, D, E = (load(pool, fs[c], n) for c in "ADE")
            pos = pose(path, n)
            rec = dict(frames=n, flight_start=path["flight_start"], flight_end=path["flight_end"], speed_mps=path["speed_mps"], mask_threshold=THR)
            lodA, dist = lod_counts(pos, "A")
            lodD, _ = lod_counts(pos, "D")
            rec["slant_center_m"] = [float(np.sqrt(((pos[i] - np.array([0, 0, 6.0])) ** 2).sum())) for i in range(n)]
            rec["slant_min_m"] = [float(dist[i].min()) for i in range(n)]
            events = []
            for cand, lod in (("A", lodA), ("D", lodD)):
                rec["lod_counts_" + cand] = [[int((lod[i] == k).sum()) for k in range(4)] for i in range(n)]
                sw = np.zeros(n, int)
                sw[1:] = (lod[1:] != lod[:-1]).sum(1)
                for f in range(n):
                    if sw[f] >= 3:
                        ch = np.flatnonzero(lod[f - 1] != lod[f])
                        events.append(dict(cand=cand, frame=f, trees=int(sw[f]), kinds=sorted({"%d->%d" % (lod[f - 1][i], lod[f][i]) for i in ch}),
                                           slant_center_m=rec["slant_center_m"][f], slant_min_m=rec["slant_min_m"][f]))
            rec["events"] = events
            mA, mD = np.abs(A - E) > THR, np.abs(D - E) > THR
            mU = mA | mD
            for c, X, m in (("A", A, mA), ("D", D, mD)):
                cnt = m.reshape(n, -1).sum(1)
                rec["cover_" + c] = [float(v) for v in cnt / m[0].size]
                lt = np.array([float(X[i][m[i]].mean()) if cnt[i] > 20 else float("nan") for i in range(n)])
                lt = np.where(np.isnan(lt), np.nanmean(lt), lt)
                rec["lumT_" + c] = [float(v) for v in lt]
                rec["dark_" + c] = [float(((X[i] < 0.12) & m[i]).sum() / max(1, cnt[i])) for i in range(n)]
                rec["d2_cover_" + c] = [float(v) for v in d2(rec["cover_" + c])]
                rec["d2_lumT_" + c] = [float(v) for v in d2(rec["lumT_" + c])]
                t2 = np.abs(X[2:] - 2 * X[1:-1] + X[:-2])
                fl = [0.0] + [float(t2[i][m[i + 1]].mean()) if m[i + 1].any() else 0.0 for i in range(n - 2)] + [0.0]
                rec["flicker_" + c] = fl
            bA, bD = box(A), box(D)
            diff = np.abs(bA - bD)
            rec["blur_mad_A_vs_D_in_mask"] = [float(diff[i][mU[i]].mean()) if mU[i].any() else 0.0 for i in range(n)]
            rec["footprint_ratio_D_over_A"] = [float(rec["cover_D"][i] / max(rec["cover_A"][i], 1e-9)) for i in range(n)]
            fs0, fe = path["flight_start"], path["flight_end"]
            win = slice(fs0 + 2, min(fe, n - 2))
            sm = {}
            for k in ("cover_A", "cover_D", "lumT_A", "lumT_D", "dark_A", "dark_D", "d2_cover_A", "d2_cover_D", "d2_lumT_A", "d2_lumT_D", "blur_mad_A_vs_D_in_mask", "flicker_A", "flicker_D",
                      "footprint_ratio_D_over_A"):
                v = np.array(rec[k])[win]
                sm[k] = dict(mean=round(float(v.mean()), 5), p95=round(float(np.percentile(v, 95)), 5), max=round(float(v.max()), 5))
            for cand in ("A", "D"):
                for key in ("d2_cover_", "d2_lumT_"):
                    med = float(np.median(np.array(rec[key + cand])[win])) + 1e-9
                    for e in events:
                        a, b = max(0, e["frame"] - 4), min(n, e["frame"] + 5)
                        e.setdefault("jump_" + key + cand, round(float(np.max(np.array(rec[key + cand])[a:b])) / med, 2))
            for cand in ("A", "D"):
                for key in ("cover", "lumT"):
                    sc = [e["jump_d2_%s_%s" % (key, cand)] for e in events if e["cand"] == cand]
                    sm["event_jump_%s_%s" % (key, cand)] = dict(n=len(sc), median=round(float(np.median(sc)), 2) if sc else None, p95=round(float(np.percentile(sc, 95)), 2) if sc else None,
                                                               max=round(float(max(sc)), 2) if sc else None)
                allv = np.array(rec["d2_cover_" + cand])[win] / (float(np.median(np.array(rec["d2_cover_" + cand])[win])) + 1e-9)
                sm["flight_jump_cover_" + cand] = dict(median=1.0, p95=round(float(np.percentile(allv, 95)), 2), max=round(float(allv.max()), 2))
            rec["summary_flight_window"] = sm
            result[pid] = rec
            chart(pid, rec, os.path.join(OUT, "flight_chart_%s.png" % pid), font)
            print(pid, n, "events A/D", sum(e["cand"] == "A" for e in events), sum(e["cand"] == "D" for e in events), "cover jump A", sm["event_jump_cover_A"], "D", sm["event_jump_cover_D"], flush=True)
    json.dump(result, open(os.path.join(OUT, "flight_metrics.json"), "w"))


if __name__ == "__main__":
    main()
