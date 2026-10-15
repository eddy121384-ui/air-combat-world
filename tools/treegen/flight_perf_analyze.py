"""GPU / frame time while flying (UE CSV profiler rows per frame; numpy).

python tools/treegen/flight_perf_analyze.py <perf_dir> <flight_paths.json> <prefix> <out.json>

Runs: <perf_dir>/<prefix>r<round>__L_TLF_<A|D|E>_<path>/profile.csv. The Level Sequence auto-plays from BeginPlay at a fixed 60 fps step, so CSV row r corresponds to
sequence frame r - R0 with a boot offset R0 that is NOT measured (rows 0-1 are boot rows with no GPU time; the first real frames are rows 2-4). R0 = 3 is assumed and
every window is shrunk by MARGIN = 15 frames on each side, which covers +-12 frames of offset error. Windows:
  hold   = sequence frames [20, flight_start - 5)   (stationary camera)
  flight = sequence frames [flight_start + MARGIN, flight_end - MARGIN)
Per run: median / p95 / p99 / max of GPUTime and FrameTime (ms) in each window; A and D also as (run - empty-level run of the same round and path).
GPU/<pass> columns are not used (they stop updating after ~209 frames on heavy levels).
"""
import csv
import json
import os
import sys

import numpy as np

csv.field_size_limit(2**31 - 1)
root, pj, prefix, out = sys.argv[1:5]
P = json.load(open(pj))["paths"]
R0, MARGIN = 3, 15


def num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def read(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    hdr = [i for i, r in enumerate(rows) if r and r[0] == "EVENTS"][-1]
    head = rows[hdr]
    return {k: np.array([float(r[head.index(k)]) if len(r) > head.index(k) and num(r[head.index(k)]) else np.nan for r in rows[1:hdr]]) for k in ("FrameTime", "GPUTime")}


def stats(v):
    v = v[~np.isnan(v)]
    return dict(median=round(float(np.median(v)), 3), p95=round(float(np.percentile(v, 95)), 3), p99=round(float(np.percentile(v, 99)), 3), max=round(float(v.max()), 3), mean=round(float(v.mean()), 3), n=int(len(v)))


runs = {}
for d in sorted(os.listdir(root)):
    if not d.startswith(prefix) or "__L_TLF_" not in d or not os.path.isfile(os.path.join(root, d, "profile.csv")):
        continue
    tag, level = d.split("__")
    _, _, cond, pid = level.split("_", 3)
    runs[(tag, cond, pid)] = read(os.path.join(root, d, "profile.csv"))

res = {}
for pid, path in P.items():
    res[pid] = {"runs": {}, "delta_vs_empty": {}}
    f0, f1 = path["flight_start"] + MARGIN, path["flight_end"] - MARGIN
    for (tag, cond, p), r in sorted(runs.items()):
        if p != pid:
            continue
        res[pid]["runs"]["%s/%s" % (tag, cond)] = dict(
            flight_gpu=stats(r["GPUTime"][R0 + f0:R0 + f1]), flight_frame=stats(r["FrameTime"][R0 + f0:R0 + f1]),
            hold_gpu=stats(r["GPUTime"][R0 + 20:R0 + path["flight_start"] - 5]), rows=int(len(r["GPUTime"])))
    for cond in ("A", "D"):
        rows = []
        for (tag, c, p), r in sorted(runs.items()):
            if p != pid or c != cond or (tag, "E", pid) not in runs:
                continue
            e = runs[(tag, "E", pid)]
            sl = slice(R0 + f0, R0 + f1)
            dg = r["GPUTime"][sl] - e["GPUTime"][sl]  # same sequence frame, same camera pose: tree - empty, frame by frame
            rows.append(dict(tag=tag, gpu_delta=stats(dg), flight_gpu=stats(r["GPUTime"][sl]), empty_gpu=stats(e["GPUTime"][sl])))
        res[pid]["delta_vs_empty"][cond] = rows
json.dump(dict(r0=R0, margin=MARGIN, window="flight = frames [flight_start+MARGIN, flight_end-MARGIN)", paths=res), open(out, "w"), indent=1)
for pid, r in res.items():
    for cond in ("A", "D"):
        for x in r["delta_vs_empty"].get(cond, []):
            print("%-7s %s %s  GPU %.2f med / %.2f p95 / %.2f max (empty %.2f med)  delta-vs-empty med %+.2f p95 %+.2f" % (pid, cond, x["tag"], x["flight_gpu"]["median"], x["flight_gpu"]["p95"],
                                                                                                        x["flight_gpu"]["max"], x["empty_gpu"]["median"], x["gpu_delta"]["median"], x["gpu_delta"]["p95"]))
