"""Summarise TreeLookdev perf runs (UE CSV profiler). python tools/treegen/analyze_tl_perf.py <perf_dir> <out.json> [cold=150]

Per run: median / p95 of FrameTime, GPUTime and every GPU/<pass> column over the warmed window (frames >= cold).
Per view: tree - empty delta of the medians for each round, and the mean / spread over rounds.
"""
import csv
import json
import os
import statistics as st
import sys
from collections import defaultdict

csv.field_size_limit(2**31 - 1)  # UE appends one very long metadata row
root, out = sys.argv[1], sys.argv[2]
cold = int(sys.argv[3]) if len(sys.argv) > 3 else 150


def read(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    # UE writes "[HasHeaderRowAtEnd]": the LAST header row is authoritative. Stats first seen mid-run are appended as
    # extra trailing columns, so early rows are shorter; values map positionally from the start of every row.
    hdr_rows = [i for i, r in enumerate(rows) if r and r[0] == "EVENTS"]
    head = rows[hdr_rows[-1]]
    ft = head.index("FrameTime")
    data = [r for r in rows[1:hdr_rows[-1]] if len(r) > ft and r[0] != "EVENTS" and _num(r[ft])]
    cols = {}
    for i, h in enumerate(head):
        vals = [float(r[i]) for r in data if len(r) > i and _num(r[i])]
        if len(vals) >= 0.9 * len(data):
            cols[h] = vals
    return cols


def _num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


runs = {}
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d, "profile.csv")
    if not os.path.isfile(p):
        continue
    tag, level = d.split("__")
    cols = read(p)
    keep = {}
    for k, v in cols.items():
        if k in ("FrameTime", "GPUTime", "GameThreadTime", "RenderThreadTime", "RHIThreadTime") or k.startswith("GPU/"):
            w = v[cold:]
            if len(w) > 20:
                keep[k] = dict(median=round(st.median(w), 3), p95=round(sorted(w)[int(0.95 * (len(w) - 1))], 3))
    runs[d] = dict(tag=tag, level=level, frames=len(cols.get("FrameTime", [])), metrics=keep)

delta = defaultdict(list)
for d, r in runs.items():
    lv = r["level"]
    if not lv.endswith("_tree"):
        continue
    e = os.path.join(root, "%s__%s" % (r["tag"], lv[:-5] + "_empty"))
    e = runs.get(os.path.basename(e))
    if not e:
        continue
    view = lv[len("L_TLP_"):-5]
    row = {}
    for k in ("GPUTime", "FrameTime") + tuple(sorted(x for x in r["metrics"] if x.startswith("GPU/"))):
        if k in r["metrics"] and k in e["metrics"]:
            row[k] = round(r["metrics"][k]["median"] - e["metrics"][k]["median"], 3)
    delta[view].append(dict(tag=r["tag"], **row))
summary = {}
for view, rows in delta.items():
    g = [x["GPUTime"] for x in rows if "GPUTime" in x]
    summary[view] = dict(rounds=rows, gpu_delta_mean_ms=round(st.mean(g), 3) if g else None,
                         gpu_delta_min_ms=min(g) if g else None, gpu_delta_max_ms=max(g) if g else None)
json.dump(dict(cold_frames=cold, runs=runs, tree_minus_empty=summary), open(out, "w"), indent=1)
for v, s in summary.items():
    print(v, "GPU tree-empty mean %.2f ms (min %.2f, max %.2f) over %d rounds" % (s["gpu_delta_mean_ms"], s["gpu_delta_min_ms"], s["gpu_delta_max_ms"], len(s["rounds"])))
