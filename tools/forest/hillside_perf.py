"""Hillside forest look-dev v1: summarise the exploratory perf runs of tools/forest/run_hf_perf.ps1 (UE CSV profiler; numpy).

    python tools/forest/hillside_perf.py <perf_dir> <prefix> <out.json>

Runs: <perf_dir>/<prefix>r<round>__<rev>__<view>__<forest|empty|mix>/profile.csv (mix = run_hf_perf.ps1 -MixRev, x<rev> = -ExtraRevs;
every extra condition is also reported minus empty and minus forest).
Still views: median of GPUTime / FrameTime / GPU/<pass> over frames 60-209 (GPU/<pass> columns stop updating after ~209 frames on heavy
levels, PR #31). Flight: GPUTime / FrameTime median and p95 over CSV rows 20-620 (auto-play sequence, fixed 60 fps step; boot offset not
measured, see tools/treegen/flight_perf_analyze.py). Forest cost = forest - empty of the same round and view; mean [min..max] over rounds.
"""
import csv
import json
import os
import sys
from collections import defaultdict

import numpy as np

csv.field_size_limit(2**31 - 1)
root, prefix, out = sys.argv[1:4]
PASSES = ("GPU/Prepass", "GPU/Basepass", "GPU/ShadowDepths", "GPU/Lights", "GPU/AmbientOcclusion", "GPU/Postprocessing")


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
    cols = {}
    for k in ("FrameTime", "GPUTime") + PASSES:
        if k in head:
            j = head.index(k)
            cols[k] = np.array([float(r[j]) if len(r) > j and num(r[j]) else np.nan for r in rows[1:hdr]])
    return cols


runs = {}
for d in sorted(os.listdir(root)):
    if not d.startswith(prefix) or not os.path.isfile(os.path.join(root, d, "profile.csv")):
        continue
    rnd, rev, view, cond = d.split("__")
    c = read(os.path.join(root, d, "profile.csv"))
    if view == "flight":
        w = slice(20, 620)
        m = {k: {"median": round(float(np.nanmedian(c[k][w])), 2), "p95": round(float(np.nanpercentile(c[k][w], 95)), 2)} for k in ("GPUTime", "FrameTime")}
    else:
        w = slice(60, 210)
        m = {k: {"median": round(float(np.nanmedian(v[w])), 2)} for k, v in c.items()}
    runs[d] = {"round": rnd[len(prefix):], "rev": rev, "view": view, "cond": cond, "rows": int(len(c["FrameTime"])), "stats": m}

CONDS = sorted({r["cond"] for r in runs.values()} - {"empty", "forest"})
PAIRS = (("forest", "empty"),) + tuple((c, b) for c in CONDS for b in ("empty", "forest"))  # (a, b) -> a - b of the same round and view
delta = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
absval = defaultdict(lambda: defaultdict(list))
for d, r in runs.items():
    for k, s_ in r["stats"].items():
        for stat, v in s_.items():
            absval[r["view"]]["%s %s.%s" % (r["cond"], k, stat)].append(v)
    for ca, cb in PAIRS:
        if r["cond"] != ca:
            continue
        e = runs.get(d.replace("__" + ca, "__" + cb))
        if not e:
            continue
        for k, s_ in r["stats"].items():
            for stat, v in s_.items():
                if k in e["stats"] and stat in e["stats"][k]:
                    delta[r["view"]]["%s_minus_%s" % (ca, cb)]["%s.%s" % (k, stat)].append(v - e["stats"][k][stat])
summary = {}
for view in absval:
    summary[view] = {pair: {k: {"mean": round(float(np.mean(v)), 2), "min": round(float(np.min(v)), 2), "max": round(float(np.max(v)), 2), "n": len(v)}
                            for k, v in dd.items()} for pair, dd in delta[view].items()}
    summary[view]["absolute"] = {k: round(float(np.mean(v)), 2) for k, v in absval[view].items()}
json.dump({"runs": runs, "summary": summary}, open(out, "w", encoding="utf-8"), indent=1)
for view, s_ in summary.items():
    for pair in ["forest_minus_empty"] + ["%s_minus_%s" % (c, b) for c in CONDS for b in ("empty", "forest")]:
        g = s_.get(pair, {}).get("GPUTime.median")
        if g:
            print(view, pair, "GPU median %.2f [%.2f..%.2f] ms (n=%d)" % (g["mean"], g["min"], g["max"], g["n"]))
