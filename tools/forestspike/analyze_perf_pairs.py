"""Paired A/B analysis of interleaved ForestSpike perf runs (CSV profiler, UHD 770 only).

  python tools/forestspike/analyze_perf_pairs.py --prefix pst [--cold 120] [--out pairs.json]

File names: <prefix>_r<round>__L_FSP_<arm>_S<s>_<view>.csv. Pairing is per round: arm A and arm B of the same round were
run back to back (order alternates each round), so a slow host drift moves both members of a pair together. The
headline is the per-round paired delta (B - A) of the warmed-window median / p95, not the pooled means.
Warmed window = frames >= --cold; the cold window (level load, shader + streaming warm-up) is reported separately.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_perf as P  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
METRICS = ["FrameTime", "GPUTime", "RenderThreadTime", "GameThreadTime", "RHIThreadTime"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(REPO / "unreal/ForestSpike/Saved/ForestSpike/perf"))
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--cold", type=int, default=120)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    runs = {}
    for f in sorted(Path(a.dir).glob("%s_r*__L_FSP_*.csv" % a.prefix)):
        m = re.match(r"%s_r(\d+)__L_FSP_([AB])_S(\d)_(.+)\.csv" % re.escape(a.prefix), f.name)
        if not m:
            continue
        rnd, arm, s, view = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        cols, _ = P.parse(f)
        runs[(rnd, arm)] = {"file": f.name, "view": view, "s": s, "cols": cols}
    rounds = sorted({r for r, _ in runs})
    complete = [r for r in rounds if (r, "A") in runs and (r, "B") in runs]
    out = {"prefix": a.prefix, "cold_frames": a.cold, "rounds_found": rounds, "rounds_complete": complete, "runs": {}, "pairs": {}}
    for (rnd, arm), r in sorted(runs.items()):
        n = len(r["cols"]["FrameTime"])
        out["runs"]["r%d_%s" % (rnd, arm)] = {"file": r["file"], "frames": n, "warm_frames": n - a.cold,
                                              **{m: {"cold": P.stats(r["cols"][m][:a.cold]), "warm": P.stats(r["cols"][m][a.cold:])}
                                                 for m in METRICS if m in r["cols"]}}
    for m in METRICS:
        for stat in ("median", "p95"):
            deltas = []
            for rnd in complete:
                va = P.stats(runs[(rnd, "A")]["cols"][m][a.cold:])[stat]
                vb = P.stats(runs[(rnd, "B")]["cols"][m][a.cold:])[stat]
                deltas.append(round(vb - va, 3))
            if deltas:
                out["pairs"]["%s_%s_B_minus_A" % (m, stat)] = {
                    "per_round": deltas, "mean": round(statistics.fmean(deltas), 3), "min": min(deltas), "max": max(deltas),
                    "sign_consistent": all(d > 0 for d in deltas) or all(d < 0 for d in deltas)}
    # run-to-run spread of the SAME config across rounds (host drift + noise floor)
    for arm in ("A", "B"):
        meds = [P.stats(runs[(r, arm)]["cols"]["GPUTime"][a.cold:])["median"] for r in rounds if (r, arm) in runs]
        if meds:
            out["pairs"]["GPUTime_median_spread_arm_%s" % arm] = {"per_round": meds, "range": round(max(meds) - min(meds), 3)}
    print(json.dumps(out["pairs"], indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
