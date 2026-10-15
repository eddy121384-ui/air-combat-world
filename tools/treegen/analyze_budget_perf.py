"""Summarise the tree-budget perf runs (UE CSV profiler). python tools/treegen/analyze_budget_perf.py <perf_dir> <out.json> <tag_prefix> [first=60] [end=210]

Per run: median of FrameTime / GPUTime / GPU/<pass> over frames [first, end) (default 60..209; same window for every run). Per (view, kind, candidate): candidate - empty (same round, same
camera) for every round, then mean / min / max over rounds. Levels: L_TLB_<view>_empty and L_TLB_<view>_<single|patch>_<A|B|C|D>.
"""
import csv
import json
import os
import statistics as st
import sys
from collections import defaultdict

csv.field_size_limit(2**31 - 1)
root, out, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
cold = int(sys.argv[4]) if len(sys.argv) > 4 else 60
end = int(sys.argv[5]) if len(sys.argv) > 5 else 210  # GPU/<pass> columns stop updating after ~frame 209 on heavy (patch) levels: one common window for every run
KEYS = ("FrameTime", "GPUTime", "GameThreadTime", "RenderThreadTime")


def num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def read(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    hdr_rows = [i for i, r in enumerate(rows) if r and r[0] == "EVENTS"]
    head = rows[hdr_rows[-1]]
    ft = head.index("FrameTime")
    data = [r for r in rows[1:hdr_rows[-1]] if len(r) > ft and r[0] != "EVENTS" and num(r[ft])]
    cols = {}
    for i, h in enumerate(head):
        vals = [float(r[i]) for r in data if len(r) > i and num(r[i])]
        if len(vals) >= 0.9 * len(data):
            cols[h] = vals
    return cols


runs = {}
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d, "profile.csv")
    if not os.path.isfile(p) or "__L_TLB_" not in d or not d.startswith(prefix):
        continue
    tag, level = d.split("__")
    cols = read(p)
    m = {}
    for k, v in cols.items():
        if k in KEYS or k.startswith("GPU/"):
            w = v[cold:end]
            if len(w) > 20:
                m[k] = round(st.median(w), 3)
    runs[d] = dict(tag=tag, level=level, frames=len(cols.get("FrameTime", [])), median=m)

delta = defaultdict(list)
for d, r in runs.items():
    parts = r["level"].split("_")  # L TLB view kind cand
    if len(parts) != 5:
        continue
    view, kind, cand = parts[2], parts[3], parts[4]
    e = runs.get("%s__L_TLB_%s_empty" % (r["tag"], view))
    if not e:
        continue
    row = {k: round(r["median"][k] - e["median"][k], 3) for k in r["median"] if k in e["median"]}
    delta["%s/%s/%s" % (view, kind, cand)].append(dict(tag=r["tag"], **row))
summary = {}
for key, rows in delta.items():
    names = sorted({k for x in rows for k in x if k != "tag"})
    agg = {}
    for n in names:
        v = [x[n] for x in rows if n in x]
        agg[n] = dict(mean=round(st.mean(v), 3), min=min(v), max=max(v), n=len(v))
    summary[key] = dict(rounds=rows, agg=agg)
empties = {r["level"]: r["median"].get("GPUTime") for r in runs.values() if r["level"].endswith("_empty")}
json.dump(dict(window_frames=[cold, end], prefix=prefix, runs=runs, candidate_minus_empty=summary), open(out, "w"), indent=1)
for key in sorted(summary):
    a = summary[key]["agg"]
    print("%-22s GPU %+7.2f ms (%+.2f..%+.2f, n=%d)  Prepass %+.2f  Base %+.2f  ShadowDepths %+.2f" % (
        key, a["GPUTime"]["mean"], a["GPUTime"]["min"], a["GPUTime"]["max"], a["GPUTime"]["n"],
        a.get("GPU/Prepass", {}).get("mean", float("nan")), a.get("GPU/Basepass", {}).get("mean", float("nan")),
        a.get("GPU/ShadowDepths", {}).get("mean", float("nan"))))
