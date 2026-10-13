"""B0 gate: where do forest pixels come from at each pre-registered viewpoint, as a function of d_S.

  python tools/forestspike/analyze_ids.py [--set gate] [--out reports/gate_table.json]

Input: ID passes (arm A or B, all instances rendered, no cull). Classification for a candidate (d_S, w_S) with the
far canopy layer S ON:
  N_inst   core forest pixel that is a tree instance  with range <  d_S - w_S   (arm-specific geometry)
  N_gap    core forest pixel that is forest ground    with range <  d_S - w_S   (understory seen between crowns)
  TRANS    core forest pixel (instance or ground)     with range in [d_S - w_S, d_S)   (S fading in, instances still drawn)
  S_core   core forest pixel                          with range >= d_S          (instances culled, S canopy)
  S_ctx    context forest ground pixel (always S when S is on; "bare context" when S is off)
Forest pixels = classes 2, 4, 5, 6.  Shares are fractions of all forest pixels in the frame unless stated.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

import fs_ids as I  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SAVED = REPO / "unreal" / "ForestSpike" / "Saved" / "ForestSpike"
POSES = {p["id"]: p for p in json.loads((Path(__file__).resolve().parent / "viewpoints.json").read_text())["poses"]}
CANDIDATES = [(200, 40), (300, 60), (400, 80), (500, 100), (600, 120), (800, 160), (1000, 200), (1200, 240)]


def classify(cls, rng, ds, ws):
    forest = np.isin(cls, (2, 4, 5, 6))
    core = np.isin(cls, (2, 5, 6))
    inst = np.isin(cls, (5, 6))
    near = rng < ds - ws
    far = rng >= ds
    trans = ~near & ~far
    out = {
        "N_inst": int((core & inst & near).sum()),
        "N_gap": int((core & ~inst & near).sum()),
        "TRANS": int((core & trans).sum()),
        "S_core": int((core & far).sum()),
        "S_ctx": int((cls == 4).sum()),
    }
    out["forest_px"] = int(forest.sum())
    out["screen_px"] = int(cls.size)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="gate")
    ap.add_argument("--out", default=str(SAVED / "reports" / "gate_table.json"))
    a = ap.parse_args()
    d = SAVED / "captures" / a.set
    rows = []
    for f in sorted(d.glob("id*_*.png")):
        name = f.stem
        arm = "B" if name.startswith("idB_") else "A"
        pid = name.split("_", 1)[1]
        if pid not in POSES:
            continue
        cls, rng, exact, _ = I.load_id(f)
        rec = {"pose": pid, "arm": arm, "group": POSES[pid]["group"], "agl_m": POSES[pid]["agl_m"],
               "codes_exact": float(exact.mean()), "sky_share": float((cls == 0).mean()),
               "core_forest_range_pct": np.percentile(rng[np.isin(cls, (2, 5, 6))], [5, 50, 95]).round(1).tolist()
               if np.isin(cls, (2, 5, 6)).any() else None,
               "by_candidate": {}}
        for ds, ws in CANDIDATES:
            rec["by_candidate"]["%d/%d" % (ds, ws)] = classify(cls, rng, ds, ws)
        rows.append(rec)
    Path(a.out).write_text(json.dumps({"candidates": CANDIDATES, "rows": rows}, indent=1))
    print(len(rows), "rows ->", a.out)


if __name__ == "__main__":
    main()
