"""Write perf-level configs for adapters/unreal/forestspike/fs_build_perf_levels.py.

  python tools/forestspike/make_perf.py pilot    # B0 workflow validation: static pose + moving path, arms A/B, S on
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPECS = HERE.parent.parent / "unreal" / "ForestSpike" / "Saved" / "ForestSpike" / "specs"
POSES = {p["id"]: p for p in json.loads((HERE / "viewpoints.json").read_text())["poses"]}
CAL = json.loads((SPECS.parent / "reports" / "calibration.json").read_text())


def cfg(arm, s, tag, **extra):
    d = {"name": "%s_S%d_%s" % (arm, s, tag), "arm": arm, "s": s, "und": 0, "ds_m": 500.0, "ws_m": 100.0,
         "count_a": CAL["A"], "count_b": CAL["B"]}
    d.update(extra)
    return d


def build(which):
    configs = []
    if which == "pilot":
        for arm in ("A", "B"):
            configs.append(cfg(arm, 1, "v1_agl200_p10", pose=POSES["v1_agl200_p10"]))
            path = [POSES["v3i_t%02d" % t] for t in range(14, 34, 2)]          # 20 s of the inbound dolly, 10 poses
            configs.append(cfg(arm, 1, "v3i_t14_t32", path={"poses": path, "fps": 60, "frames_per_pose": 120}))
    else:
        raise SystemExit("unknown set " + which)
    SPECS.mkdir(parents=True, exist_ok=True)
    p = SPECS / ("perf_%s.json" % which)
    p.write_text(json.dumps({"set": which, "configs": configs}, indent=1))
    print(p, len(configs), "configs")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "pilot")
