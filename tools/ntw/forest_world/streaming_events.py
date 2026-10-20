"""World Partition streaming-performance transitions of a real-time perf run, placed on the perf-sequence timeline.

    python tools/ntw/forest_world/streaming_events.py <perf_run_dir> <n_stills> <hold_s> [out.json]
Engine frame numbers of 'Streaming performance changed' log lines are mapped to time via the CSV FrameTime; t = 0 at the load hitch.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perf_summary as ps  # noqa: E402


def main():
    run, n, hold = Path(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
    d = ps.read(run / "profile.csv")
    t = np.cumsum(d["FrameTime"]) / 1000.0
    k0 = int(np.nanargmax(np.where(t < 60, d["FrameTime"], -1)))
    ev = []
    for line in open(run / "engine.log", encoding="utf-8", errors="replace"):
        m = re.search(r"\]\[\s*(\d+)\]LogWorldPartition: Streaming performance changed: (\w+) -> (\w+)", line)
        if m:
            ts = float(t[min(int(m.group(1)), len(t) - 1)] - t[k0])
            seg = "still%d" % int(ts // hold) if ts < n * hold else ("flight" if ts < n * hold + 3519 / 30.0 else "after")
            ev.append({"t_s": round(ts, 1), "from": m.group(2), "to": m.group(3), "segment": seg})
    fl = [e for e in ev if e["segment"] == "flight"]
    res = {"run": run.name, "events": ev, "flight_events": fl, "flight_degraded": any(e["to"] in ("Slow", "Critical") for e in fl),
           "flight_fps_median": round(1000.0 / float(np.nanmedian(d["FrameTime"][(t - t[k0] >= n * hold) & (t - t[k0] < n * hold + 117.3)])), 2)}
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("flight_events", "flight_degraded", "flight_fps_median")}, indent=1))


if __name__ == "__main__":
    main()
