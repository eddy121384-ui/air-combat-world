"""Packaged runtime gate: summarise real-time runs of the packaged game (tools/ntw/forest_world/run_packaged.ps1).

Per run, on the hero-flight window of LS_NF_Perf_P (t = 12 .. 129 s after the load frame; first 30 s of the flight skipped for
"steady" numbers and reported separately): frame / GPU / game / render thread median + p95, GPU passes, World Partition streaming
events, the game-thread / render-thread cost of streaming the forest tiles in (component registration = AddToWorld, level streaming,
async loading, render-resource init, GPU-scene instance uploads), GPU-scene instance count, and memory (process physical, LLM tags).
    python tools/ntw/forest_world/pk_analyze.py <runs_dir> <out.json> run [run ...]
"""
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

csv.field_size_limit(2**31 - 1)
STREAM_COLS = ("Exclusive/GameThread/AddToWorld", "Exclusive/GameThread/UpdateLevelStreaming", "Exclusive/GameThread/AsyncLoading",
               "Exclusive/GameThread/FlushAsyncLoading", "Exclusive/GameThread/InitRenderResource", "Exclusive/GameThread/UpdateStreamingState",
               "Exclusive/RenderThread/UpdatePrimitiveInstances", "Exclusive/RenderThread/UpdateGPUScene", "FileIO/GameThread/AsyncLoadingTime")


def load(p):
    rows = list(csv.reader(open(p, encoding="utf-8", errors="replace")))
    head = rows[0]
    end = next((i for i, r in enumerate(rows) if i > 0 and r and r[0] == "EVENTS"), len(rows))
    data = {}
    for j, h in enumerate(head):
        v = []
        for r in rows[1:end]:
            try:
                v.append(float(r[j]))
            except (ValueError, IndexError):
                v.append(np.nan)
        data[h] = np.array(v)
    return data


def st(x):
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    return {"median": round(float(np.median(x)), 2), "p95": round(float(np.percentile(x, 95)), 2), "p99": round(float(np.percentile(x, 99)), 2),
            "max": round(float(x.max()), 2)}


def main():
    root, out, runs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    res = {}
    for r in runs:
        d = load(root / r / "profile.csv")
        ft = d["FrameTime"]
        t = np.cumsum(ft) / 1000.0
        k0 = int(np.nanargmax(np.where(t < 60, ft, -1)))
        ts = (t - t[k0]) * float(__import__("os").environ.get("ACW_PK_TIMESCALE", "1"))   # slomo 1.25 run: sequence time = wall time x 1.25
        fl = (ts >= 12) & (ts < 129.3)
        steady = (ts >= 42) & (ts < 129.3)
        seg = {}
        for name, m in (("flight", fl), ("flight_steady", steady)):
            s = {k: st(d[k][m]) for k in ("FrameTime", "GPUTime", "GameThreadTime", "RenderThreadTime") if k in d}
            s["frames"] = int(m.sum())
            s["fps_median"] = round(1000.0 / s["FrameTime"]["median"], 2)
            s["passes_median"] = dict(sorted(((h[4:], round(float(np.nanmedian(d[h][m])), 1)) for h in d if h.startswith("GPU/")),
                                             key=lambda x: -(x[1] if x[1] == x[1] else 0))[:8])
            seg[name] = s
        streaming = {k.split("/")[-1]: st(d[k][fl]) for k in STREAM_COLS if k in d}
        gt_spikes = int(np.sum(d["GameThreadTime"][fl] > 50)) if "GameThreadTime" in d else None
        llm = {h[4:]: round(float(np.nanmax(d[h])), 1) for h in d if h.startswith("LLM/") and np.isfinite(d[h]).any()}
        llm_top = dict(sorted(llm.items(), key=lambda x: -x[1])[:15])
        ev = []
        for line in open(root / r / "game.log", encoding="utf-8", errors="replace"):
            m = re.search(r"\]\[\s*(\d+)\]LogWorldPartition: Streaming performance changed: (\w+) -> (\w+)", line)
            if m:
                f = min(int(m.group(1)), len(t) - 1)
                ev.append({"t_s": round(float(ts[f]), 1), "to": m.group(3)})
        load_ms = None
        for line in open(root / r / "game.log", encoding="utf-8", errors="replace"):
            m = re.search(r"Took ([\d.]+) seconds to LoadMap", line)
            if m:
                load_ms = round(float(m.group(1)) * 1000, 0)
        proc = json.loads((root / r / "process.json").read_text(encoding="utf-8-sig"))
        res[r] = {"segments": seg, "streaming_cost_ms_flight": streaming, "game_thread_frames_over_50ms_flight": gt_spikes,
                  "gpuscene_instances": st(d["GPUSceneInstanceCount"][fl]) if "GPUSceneInstanceCount" in d else None,
                  "physical_used_mb": st(d["PhysicalUsedMB"]) if "PhysicalUsedMB" in d else None, "llm_peak_mb_top": llm_top,
                  "loadmap_ms": load_ms, "streaming_events": ev, "flight_events": [e for e in ev if 12 <= e["t_s"] < 129.3], "process": proc}
        f = seg["flight"]
        print(r, "flight frame %s/%s GPU %s fps %s | steady GPU %s | events in flight %s | GT>50ms %s | phys max %s MB" % (
            f["FrameTime"]["median"], f["FrameTime"]["p95"], f["GPUTime"]["median"], f["fps_median"], seg["flight_steady"]["GPUTime"]["median"],
            len(res[r]["flight_events"]), gt_spikes, (res[r]["physical_used_mb"] or {}).get("max")))
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
