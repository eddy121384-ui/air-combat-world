"""Per-pass GPU medians (UE CSV GPU/<pass> columns) of the flight segment of fixed-step A/B runs (run_ab.ps1).

    python tools/ntw/forest_world/ab_passes.py <perf_dir> <out.json> run [run ...]
Flight segment = rows [k0 + 3 stills * 60 + 10, k0 + 3 stills * 60 + 1760) at a fixed 15 fps (k0 = load hitch). Also the 3 stills.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

csv.field_size_limit(2**31 - 1)
PASSES = ("Basepass", "Prepass", "RenderVelocities", "ShadowDepths", "TAA", "SSAO", "Lights", "SkyAtmosphere", "Postprocessing")


def main():
    root, out, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    res = {}
    for run in runs:
        rows = list(csv.reader(open(root / run / "profile.csv", encoding="utf-8", errors="replace")))
        head = rows[0]
        end = next(i for i, r in enumerate(rows) if i > 0 and r and r[0] == "EVENTS")
        col = lambda k: np.array([float(r[head.index(k)]) if r[head.index(k)] else np.nan for r in rows[1:end]])  # noqa: E731
        ft = col("FrameTime")
        k0 = int(np.argmax(ft[:400]))
        segs = {"flight": slice(k0 + 190, k0 + 180 + 1760)}
        for i, n in enumerate(("dl_layers_north", "agl200_qingtiangang", "agl120_plantation")):
            segs[n] = slice(k0 + 60 * i + 30, k0 + 60 * (i + 1))
        r = {}
        for sname, sl in segs.items():
            d = {"GPUTime_median": round(float(np.nanmedian(col("GPUTime")[sl])), 1), "GPUTime_p95": round(float(np.nanpercentile(col("GPUTime")[sl], 95)), 1),
                 "FrameTime_median": round(float(np.nanmedian(ft[sl])), 1), "FrameTime_p95": round(float(np.nanpercentile(ft[sl], 95)), 1)}
            for p in PASSES:
                if "GPU/" + p in head:
                    d[p] = round(float(np.nanmedian(col("GPU/" + p)[sl])), 1)
            r[sname] = d
        res[run] = r
        f = r["flight"]
        print(run.ljust(24), "flight GPU %6.1f p95 %6.1f | base %5.1f vel %5.1f shadow %5.1f prepass %s" % (
            f["GPUTime_median"], f["GPUTime_p95"], f.get("Basepass", 0), f.get("RenderVelocities", 0), f.get("ShadowDepths", 0), f.get("Prepass")),
            "| stills", [r[s]["GPUTime_median"] for s in ("dl_layers_north", "agl200_qingtiangang", "agl120_plantation")])
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
