"""Markdown tables for docs/research/forest-tree-triangle-budget-v1.md (project venv; stdlib only).

python tools/treegen/budget_tables.py <evidence_dir>
Reads <evidence_dir>/{budget_perf_q1.json, overdraw_*.json, mesh_audit.json, lod_pop.json} and prints the tables used in the document.
"""
import json
import os
import sys

E = sys.argv[1]
J = lambda n: json.load(open(os.path.join(E, n)))  # noqa: E731

perf = J("budget_perf_q1.json")
runs, delta = perf["runs"], perf["candidate_minus_empty"]
rounds = sorted({r["tag"] for r in runs.values()})
print("rounds:", rounds, "window frames:", perf["window_frames"])

print("\n### empty-stage GPU time (ms, median of window) per round")
for v in ("front", "sl150", "sl300", "sl500", "sl1000"):
    vals = [runs["%s__L_TLB_%s_empty" % (t, v)]["median"]["GPUTime"] for t in rounds if "%s__L_TLB_%s_empty" % (t, v) in runs]
    print("| %s | %s |" % (v, " / ".join("%.1f" % x for x in vals)))

print("\n### candidate - empty GPU ms (mean over rounds, [min..max]) and pass breakdown")
print("| view | kind | cand | GPU | Prepass | Basepass | ShadowDepths | rounds |")
print("|---|---|---|---:|---:|---:|---:|---:|")
order = [("front", "single"), ("sl150", "single"), ("sl150", "patch"), ("sl300", "patch"), ("sl500", "patch"), ("sl1000", "patch")]
for view, kind in order:
    for c in "ABCD":
        k = "%s/%s/%s" % (view, kind, c)
        if k not in delta:
            continue
        a = delta[k]["agg"]
        g = a["GPUTime"]
        f = lambda n: "%+.2f" % a[n]["mean"] if n in a else "n/a"  # noqa: E731
        print("| %s | %s | %s | **%+.2f** [%+.2f..%+.2f] | %s | %s | %s | %d |" % (
            view, kind, c, g["mean"], g["min"], g["max"], f("GPU/Prepass"), f("GPU/Basepass"), f("GPU/ShadowDepths"), g["n"]))

print("\n### mesh audit / memory")
audit = J("mesh_audit.json")
print(json.dumps(audit, indent=1)[:2500])
