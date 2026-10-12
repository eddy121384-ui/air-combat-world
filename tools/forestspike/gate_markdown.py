"""Render the B0 gate tables (markdown) from gate_table.json (V1 + legacy V3o/V5t) and gate2_table.json (V3 / V5 revised).

  python tools/forestspike/gate_markdown.py [--cand 500/100]

Shares are fractions of all forest pixels in the frame (forest = core forest ground + trees + context forest ground).
N = core trees + core forest ground with range < d_S - w_S; T = core forest in [d_S - w_S, d_S); S = core forest >= d_S;
Sctx = context forest ground (shared surround). Pre-registered rule (written before the choice) is evaluated at the end.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SAVED = Path(__file__).resolve().parents[2] / "unreal" / "ForestSpike" / "Saved" / "ForestSpike" / "reports"


def sh(v):
    f = max(v["forest_px"], 1)
    return {"N": (v["N_inst"] + v["N_gap"]) / f, "Ninst": v["N_inst"] / f, "T": v["TRANS"] / f, "S": v["S_core"] / f,
            "Sctx": v["S_ctx"] / f, "core": (v["N_inst"] + v["N_gap"] + v["TRANS"] + v["S_core"]) / f,
            "forest_screen": v["forest_px"] / v["screen_px"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="500/100")
    a = ap.parse_args()
    t1 = json.loads((SAVED / "gate_table.json").read_text())["rows"]
    t2 = json.loads((SAVED / "gate2_table.json").read_text())["rows"]
    print("### V1 stills, arm A, d_S/w_S = %s m\n" % a.cand)
    print("| viewpoint | forest % of screen | core share | N | T | S core | S surround |\n|---|---:|---:|---:|---:|---:|---:|")
    for r in sorted([r for r in t1 if r["group"] == "V1" and r["arm"] == "A"], key=lambda r: (r["agl_m"], r["pose"])):
        s = sh(r["by_candidate"][a.cand])
        print("| %s | %.0f | %.2f | %.2f | %.2f | %.2f | %.2f |" % (r["pose"][3:], 100 * s["forest_screen"], s["core"], s["N"], s["T"], s["S"], s["Sctx"]))
    print("\n### Revised V3 (inbound dolly, 200 m AGL) and V5 (inward orbit r=330 m), arm A, %s\n" % a.cand)
    print("| pass | frames | core share range | N range | T range | S core range | N>=10 %% frames |\n|---|---:|---|---|---|---|---:|")
    for name, pref, agl in (("V3 inbound", "v3i", None), ("V5 inward 200 m", "v5i_agl200", 200), ("V5 inward 500 m", "v5i_agl500", 500)):
        rows = [r for r in t2 if r["pose"].startswith(pref)]
        ss = [sh(r["by_candidate"][a.cand]) for r in rows]
        rng = lambda k: "%.2f-%.2f" % (min(s[k] for s in ss), max(s[k] for s in ss))  # noqa: E731
        print("| %s | %d | %s | %s | %s | %s | %d/%d |" % (name, len(rows), rng("core"), rng("N"), rng("T"), rng("S"),
                                                         sum(s["N"] >= 0.10 for s in ss), len(ss)))
    print("\n### Pre-registered d_S rule over the candidate set (V3 inbound frames)\n")
    print("Rule: (i) >= 8 V3 frames with T >= 5 %; (ii) V3 contains frames with N >= 40 % and frames with core-S >= 10 %; "
          "(iii) V1 agl200_p10 has N, T and S each >= 5 %. Smallest passing candidate is frozen.\n")
    print("| d_S / w_S | (i) T>=5 % frames | (ii) max N | (ii) max S | (iii) V1 200 m N/T/S | pass |\n|---|---:|---:|---:|---|---|")
    v3 = [r for r in t2 if r["pose"].startswith("v3i")]
    v1 = [r for r in t1 if r["pose"] == "v1_agl200_p10" and r["arm"] == "A"][0]
    first = None
    for key in v1["by_candidate"]:
        ss = [sh(r["by_candidate"][key]) for r in v3]
        i = sum(s["T"] >= 0.05 for s in ss)
        mn, ms = max(s["N"] for s in ss), max(s["S"] for s in ss)
        c = sh(v1["by_candidate"][key])
        ok = i >= 8 and mn >= 0.40 and ms >= 0.10 and min(c["N"], c["T"], c["S"]) >= 0.05
        first = first or (key if ok else None)
        print("| %s | %d/%d | %.2f | %.2f | %.2f / %.2f / %.2f | %s |" % (key, i, len(ss), mn, ms, c["N"], c["T"], c["S"], "PASS" if ok else "fail"))
    print("\nFrozen: **%s**" % first)


if __name__ == "__main__":
    main()
