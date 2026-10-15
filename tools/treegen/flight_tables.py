"""Markdown tables for the moving-camera gate (stdlib + numpy).
python tools/treegen/flight_tables.py <evidence_dir>/flight
Reads flight_perf.json, flight_metrics.json, flight_pop_local.json.
"""
import json
import os
import sys

import numpy as np

E = sys.argv[1]
J = lambda n: json.load(open(os.path.join(E, n)))  # noqa: E731
perf, met, pop = J("flight_perf.json"), J("flight_metrics.json"), J("flight_pop_local.json")

print("### GPU time while flying (ms; mean of 3 rounds of each round's window median / p95 / max; delta = same-frame tree - empty)")
print("| path | cand | GPU median | GPU p95 | GPU max | delta median | delta p95 | rounds' p95 range |")
print("|---|---|---:|---:|---:|---:|---:|---|")
for pid, r in perf["paths"].items():
    e = [x["empty_gpu"]["median"] for x in r["delta_vs_empty"]["A"]]
    print("| %s | empty | %.1f | %.1f | - | - | - | |" % (pid, np.mean(e), np.mean([x["empty_gpu"]["p95"] for x in r["delta_vs_empty"]["A"]])))
    for c in "AD":
        rows = r["delta_vs_empty"][c]
        f = lambda k, s: np.mean([x[s][k] for x in rows])  # noqa: E731
        p95s = [x["flight_gpu"]["p95"] for x in rows]
        print("| %s | %s | %.1f | %.1f | %.1f | %+.1f | %+.1f | %.1f..%.1f |" % (pid, c, f("median", "flight_gpu"), f("p95", "flight_gpu"), f("max", "flight_gpu"), f("median", "gpu_delta"), f("p95", "gpu_delta"), min(p95s), max(p95s)))

print("\n### image metrics, flight window (A vs D; footprint = tree + shadow pixels differing from the empty stage)")
print("| path | footprint D/A | tree lum A | tree lum D | blur-MAD A-vs-D | flicker A | flicker D | D/A flicker |")
print("|---|---:|---:|---:|---:|---:|---:|---:|")
for pid, r in met.items():
    s = r["summary_flight_window"]
    cA, cD = s["cover_A"]["mean"], s["cover_D"]["mean"]
    print("| %s | %.3f | %.4f | %.4f | %.4f | %.4f | %.4f | %.2f |" % (pid, cD / cA, s["lumT_A"]["mean"], s["lumT_D"]["mean"], s["blur_mad_A_vs_D_in_mask"]["mean"], s["flicker_A"]["mean"], s["flicker_D"]["mean"],
                                                                      s["flicker_D"]["mean"] / s["flicker_A"]["mean"]))

print("\n### calculated LOD switch events (>= 3 trees in one frame) and footprint-jump score (max |2nd diff of footprint| within +-4 frames / flight median)")
print("| path | cand | events | kinds | jump median | jump p95 | whole-flight p95 |")
print("|---|---|---:|---|---:|---:|---:|")
for pid, r in met.items():
    s = r["summary_flight_window"]
    for c in "AD":
        ev = [e for e in r["events"] if e["cand"] == c]
        kinds = sorted({k for e in ev for k in e["kinds"]})
        a = s["event_jump_cover_" + c]
        print("| %s | %s | %d | %s | %s | %s | %s |" % (pid, c, len(ev), ",".join(kinds), a["median"], a["p95"], s["flight_jump_cover_" + c]["p95"]))

print("\n### per-tree switch step ratio (step at the switch frame / median step at the neighbouring frames in the same tree window; control = non-switch pairs)")
print("| path | cand | transition | n | median | p90 | p99 | max |")
print("|---|---|---|---:|---:|---:|---:|---:|")
for pid, r in pop.items():
    for c, v in r.items():
        for k, t in v["transitions"].items():
            print("| %s | %s | LOD%s | %d | %.3f | %.3f | %.3f | %.3f |" % (pid, c, k.replace("->", "->LOD"), t["n"], t["median"], t["p90"], t["p99"], t["max"]))
        t = v["control"]
        print("| %s | %s | control | %d | %.3f | %.3f | %.3f | %.3f |" % (pid, c, t["n"], t["median"], t["p90"], t["p99"], t["max"]))
