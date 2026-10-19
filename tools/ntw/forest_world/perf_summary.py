"""Summarise tools/ntw/forest_world/run_nf_perf.ps1 runs (UE CSV profiler, real-time playback of LS_NF_Perf).

Timeline: the CSV starts before the map is ready; the sequence starts on the first frame after the longest load hitch in the first
60 s (map + World Partition initial streaming). From there: still i = [8 i + 2, 8 i + 8) s (first 2 s of a still dropped: camera cut,
streaming / TSR history), flight = [48, 48 + flight_s) s. Per segment: median / p95 / p99 of FrameTime, GPUTime, game / render thread,
frames > 50 ms, and memory columns when present. Exploratory, single host (Intel UHD 770 iGPU), not a benchmark.
    python tools/ntw/forest_world/perf_summary.py <perf_dir> <out.json> [run ...]
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

csv.field_size_limit(2**31 - 1)
STILLS = ["agl300_qixing", "alt1500_overview", "agl120_plantation", "agl200_qingtiangang", "alt3000_wide", "agl400_basin_edge"]
HOLD_S, FLIGHT_S = 8.0, 3499 / 30.0
COLS = ("FrameTime", "GPUTime", "GameThreadTime", "RenderThreadTime", "RHIThreadTime")


def read(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    head = rows[0]
    end = next((i for i, r in enumerate(rows) if r and r[0] == "EVENTS"), len(rows))
    data = {}
    for j, k in enumerate(head):
        if k in COLS or "Memory" in k or k.endswith("MB"):
            v = []
            for r in rows[1:end]:
                try:
                    v.append(float(r[j]))
                except (ValueError, IndexError):
                    v.append(np.nan)
            data[k] = np.array(v)
    return data


def stats(d, m):
    out = {}
    for k in COLS:
        if k in d and m.any():
            x = d[k][m]
            out[k] = {"median": round(float(np.nanmedian(x)), 2), "p95": round(float(np.nanpercentile(x, 95)), 2),
                      "p99": round(float(np.nanpercentile(x, 99)), 2)}
    ft = d["FrameTime"][m]
    out["frames"] = int(m.sum())
    out["frames_over_50ms"] = int((ft > 50).sum())
    out["fps_median"] = round(1000.0 / float(np.nanmedian(ft)), 1) if m.any() else None
    for k in d:
        if ("Memory" in k or k.endswith("MB")) and m.any():
            out[k] = {"median": round(float(np.nanmedian(d[k][m])), 1), "max": round(float(np.nanmax(d[k][m])), 1)}
    return out


def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    runs = sys.argv[3:] or sorted(p.name for p in root.iterdir() if (p / "profile.csv").exists())
    res = {}
    for r in runs:
        d = read(root / r / "profile.csv")
        t = np.cumsum(d["FrameTime"]) / 1000.0
        early = t < 60
        k0 = int(np.nanargmax(np.where(early, d["FrameTime"], -1)))   # longest hitch in the first 60 s = map load / initial streaming
        ts = t - t[k0]
        seg = {}
        for i, name in enumerate(STILLS):
            seg["still_" + name] = stats(d, (ts >= HOLD_S * i + 2) & (ts < HOLD_S * (i + 1)))
        seg["flight"] = stats(d, (ts >= HOLD_S * len(STILLS)) & (ts < HOLD_S * len(STILLS) + FLIGHT_S))
        proc = json.loads((root / r / "process.json").read_text(encoding="utf-8-sig"))
        res[r] = {"load_hitch_ms": round(float(d["FrameTime"][k0]), 1), "sequence_start_s": round(float(t[k0]), 2),
                  "csv_rows": int(len(t)), "csv_seconds": round(float(t[-1]), 1), "process": proc, "segments": seg}
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    for r, v in res.items():
        f = v["segments"]["flight"]
        print(r, "flight frame median/p95 %s/%s ms, GPU %s, >50ms %s/%s, peakWS %s MB" % (
            f.get("FrameTime", {}).get("median"), f.get("FrameTime", {}).get("p95"), f.get("GPUTime", {}).get("median"),
            f.get("frames_over_50ms"), f.get("frames"), v["process"].get("peak_working_set_mb")))


if __name__ == "__main__":
    main()
