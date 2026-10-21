"""Mobile forest profile: compare editor fixed-step runs (tools/ntw/forest_world/run_nf_perf.ps1 -FixedFps 15) of LS_NF_Perf_P.

Same timeline as perf_summary.py (sequence start = longest hitch in the first 60 s; 3 held stills of 4 s, first 2 s of each dropped;
then the 117 s flight; sequence time = frames / 15). Per segment: GPU time, the heaviest GPU passes, RHI draw calls and primitives
(triangles) drawn, GPU-scene instance count; per run: peak physical memory and the largest LLM tags (runs started with -llm).
Exploratory, single host (Intel UHD 770 iGPU, PC ES3.1 preview of the mobile renderer): relative evidence, NOT phone performance.
    python tools/ntw/forest_world/mobile_compare.py <perf_dir> <out.json> run [run ...]
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

csv.field_size_limit(2**31 - 1)
STILLS = ["dl_layers_north", "agl200_qingtiangang", "agl120_plantation"]
HOLD_S, FLIGHT_S, FPS = 4.0, 3519 / 30.0, 15.0
KEYS = ("GPUTime", "FrameTime", "RHI/DrawCalls", "RHI/PrimitivesDrawn", "GPUSceneInstanceCount")


def load(p):
    rows = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    head = rows[0]
    end = next((i for i, r in enumerate(rows) if i > 0 and r and r[0] == "EVENTS"), len(rows))
    data = {}
    for j, h in enumerate(head):
        if h in KEYS or h.startswith("GPU/") or h.startswith("LLM/") or h == "PhysicalUsedMB":
            v = []
            for r in rows[1:end]:
                try:
                    v.append(float(r[j]))
                except (ValueError, IndexError):
                    v.append(np.nan)
            data[h] = np.array(v)
    return data


def med(x):
    x = x[np.isfinite(x)]
    return round(float(np.median(x)), 2) if len(x) else None


def seg_stats(d, m):
    s = {k: med(d[k][m]) for k in KEYS if k in d}
    g = d["GPUTime"][m]
    s["GPUTime_p95"] = round(float(np.nanpercentile(g, 95)), 2)
    s["frames"] = int(m.sum())
    s["passes"] = dict(sorted(((h[4:], med(d[h][m])) for h in d if h.startswith("GPU/") and med(d[h][m])), key=lambda x: -x[1])[:8])
    return s


def main():
    root, out, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    res = {}
    for r in runs:
        d = load(root / r / "profile.csv")
        ft = d["FrameTime"]
        t = np.cumsum(ft) / 1000.0
        k0 = int(np.nanargmax(np.where(t < 60, ft, -1)))
        ts = (np.arange(len(t)) - k0) / FPS
        segs = {name: seg_stats(d, (ts >= HOLD_S * i + 2) & (ts < HOLD_S * (i + 1))) for i, name in enumerate(STILLS)}
        segs["flight"] = seg_stats(d, (ts >= HOLD_S * len(STILLS)) & (ts < HOLD_S * len(STILLS) + FLIGHT_S))
        llm = {h[4:]: round(float(np.nanmax(d[h])), 1) for h in d if h.startswith("LLM/") and np.isfinite(d[h]).any()}
        res[r] = {"segments": segs, "physical_used_mb_max": round(float(np.nanmax(d["PhysicalUsedMB"])), 0) if "PhysicalUsedMB" in d else None,
                  "llm_peak_mb": dict(sorted(llm.items(), key=lambda x: -x[1])[:14]),
                  "gpuscene_instances_max": round(float(np.nanmax(d["GPUSceneInstanceCount"])), 0) if "GPUSceneInstanceCount" in d else None}
        f = segs["flight"]
        print("%-22s flight GPU %7s ms (p95 %7s) | draws %6s | prims %9s | instances %8s (max %s) | phys max %s MB" % (
            r, f.get("GPUTime"), f["GPUTime_p95"], f.get("RHI/DrawCalls"), f.get("RHI/PrimitivesDrawn"), f.get("GPUSceneInstanceCount"),
            res[r]["gpuscene_instances_max"], res[r]["physical_used_mb_max"]))
        for name in STILLS:
            s = segs[name]
            print("%-22s   %-20s GPU %7s ms | draws %6s | prims %9s" % ("", name, s.get("GPUTime"), s.get("RHI/DrawCalls"), s.get("RHI/PrimitivesDrawn")))
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
