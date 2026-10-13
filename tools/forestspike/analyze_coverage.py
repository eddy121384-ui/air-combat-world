"""Coverage curve + target solve for ForestSpike arms (reads captures/<set>/cov_<arm>_n<count>.png).

  python tools/forestspike/analyze_coverage.py [--set coverage] [--target 0.70] [--out report.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

import fs_cover as C  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CAP = REPO / "unreal" / "ForestSpike" / "Saved" / "ForestSpike" / "captures"


def curve(set_name, arm):
    rows = []
    for f in sorted((CAP / set_name).glob("cov_%s_n*.png" % arm)):
        n = int(re.search(r"_n(\d+)\.png", f.name).group(1))
        m = C.measured(f, arm, px=2048)
        rows.append({"n": n, "cover_measured": m["cover"], "cover_model_ellipse": C.model_cover(arm, n),
                     "cover_poisson": C.poisson_cover(arm, n), "instance_px_outside_forest": m["instance_px_outside_forest"],
                     "forest_px": m["forest_px"], "codes_exact": m["codes_exact"]})
    return sorted(rows, key=lambda r: r["n"])


def solve(rows, target, key="cover_measured"):
    """n reaching `target`: linear interpolation of -ln(1 - cover) vs n between the bracketing measurements."""
    x = np.array([r["n"] for r in rows], float)
    t = -np.log1p(-np.clip(np.array([r[key] for r in rows], float), 1e-6, 0.999999))
    tt = -np.log1p(-target)
    n = float(np.interp(tt, t, x))
    k = float(np.polyfit(x, t, 1)[0])
    return n, k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="coverage")
    ap.add_argument("--target", type=float, default=0.70)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rep = {"target": a.target, "arms": {}}
    for arm in ("A", "B"):
        rows = curve(a.set, arm)
        n_meas, k = solve(rows, a.target, "cover_measured")
        n_mod, km = solve(rows, a.target, "cover_model_ellipse")
        rep["arms"][arm] = {"rows": rows, "n_for_target_measured_fit": round(n_meas), "k_measured": k,
                            "n_for_target_ellipse_model_fit": round(n_mod), "k_model": km}
        print("arm", arm)
        for r in rows:
            print("  n=%6d measured %.4f  ellipse-model %.4f  poisson %.4f  (measured/model %.3f)" % (
                r["n"], r["cover_measured"], r["cover_model_ellipse"], r["cover_poisson"], r["cover_measured"] / r["cover_model_ellipse"]))
        print("  n for %.0f%%: measured-fit %d, model-fit %d" % (a.target * 100, n_meas, n_mod))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1))
        cal = {"target": a.target, "A": int(round(rep["arms"]["A"]["n_for_target_measured_fit"], -2)),
               "B": int(round(rep["arms"]["B"]["n_for_target_measured_fit"], -2)), "source": "interpolated measured curve"}
        (Path(a.out).parent / "calibration.json").write_text(json.dumps(cal, indent=1))
        print("calibration", cal)


if __name__ == "__main__":
    main()
