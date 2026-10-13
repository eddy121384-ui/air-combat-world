"""Write capture-job specs for adapters/unreal/forestspike/fs_capture.py.

  python tools/forestspike/make_spec.py smoke            # 3 jobs: visual + ID + top-down smoke test
  python tools/forestspike/make_spec.py gate             # B0 gate: ID passes at every pre-registered viewpoint
  python tools/forestspike/make_spec.py visual           # B0 visual set (arms A/B x S off/on at key viewpoints)
  python tools/forestspike/make_spec.py coverage         # top-down coverage curves for arms A and B
  python tools/forestspike/make_spec.py ring             # switch-ring series: visual frames across d_S along V3
Specs go to unreal/ForestSpike/Saved/ForestSpike/specs/<set>.json (git-ignored; the generator is the source).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SPECS = REPO / "unreal" / "ForestSpike" / "Saved" / "ForestSpike" / "specs"
POSES = {p["id"]: p for p in json.loads((HERE / "viewpoints.json").read_text())["poses"]}
CAL = SPECS.parent / "reports" / "calibration.json"
CAL_N = json.loads(CAL.read_text()) if CAL.is_file() else {"A": 26000, "B": 26000}
DS_DEFAULT = 500.0   # frozen by the B0 gate (see docs/forestspike-b0-preflight-result.md)
WS_DEFAULT = 100.0


def vis(name, pid, arm, s=1, ds=DS_DEFAULT, ws=WS_DEFAULT, ca=None, cb=None):
    ca, cb = ca or CAL_N["A"], cb or CAL_N["B"]
    return {"name": name, "kind": "visual", "pose": POSES[pid], "arm": arm, "s_core": s, "s_ctx": s, "und": 0,
            "ds_m": ds, "ws_m": ws, "count_a": ca, "count_b": cb}


def idp(name, pid, arm="A", ca=None, cb=None):
    ca, cb = ca or CAL_N["A"], cb or CAL_N["B"]
    return {"name": name, "kind": "id", "pose": POSES[pid], "arm": arm, "count_a": ca, "count_b": cb}


def build(which):
    jobs = []
    extra = {}
    if which == "smoke":
        jobs = [vis("smoke_v1_agl200_p10_A_s1", "v1_agl200_p10", "A"), idp("smoke_id_v1_agl200_p10_A", "v1_agl200_p10"),
                vis("smoke_v1_agl500_p35_A_s1", "v1_agl500_p35", "A"), idp("smoke_id_v1_agl500_p35_A", "v1_agl500_p35"),
                {"name": "smoke_topdown_A", "kind": "topdown", "arm": "A", "counts": [26000], "ortho_m": 1000.0}]
    elif which == "gate":
        for pid in POSES:
            jobs.append(idp("id_" + pid, pid))
        for pid in POSES:
            if POSES[pid]["group"] == "V1":
                jobs.append(idp("idB_" + pid, pid, arm="B"))
        extra = {"warmup": 6, "settle": 2}
    elif which == "visual":
        for pid in ("v1_agl50_p15", "v1_agl200_p10", "v1_agl500_p35", "v1_agl1000_p45"):
            for arm in ("A", "B"):
                for sv in (0, 1):
                    jobs.append(vis("vis_%s_%s_S%d" % (pid, arm, sv), pid, arm, s=sv))
    elif which == "ring":
        for t in (14, 18, 22, 26, 30):
            for sv in (0, 1):
                jobs.append(vis("ring_A_S%d_t%02d" % (sv, t), "v3i_t%02d" % t, "A", s=sv))
    elif which == "gate2":
        for pid in POSES:
            if pid.startswith(("v3i_", "v5i_")):
                jobs.append(idp("id_" + pid, pid))
        extra = {"warmup": 6, "settle": 2}
    elif which == "verify":
        jobs = [{"name": "ver_A", "kind": "topdown", "arm": "A", "counts": [CAL_N["A"]], "ortho_m": 1000.0},
                {"name": "ver_B", "kind": "topdown", "arm": "B", "counts": [CAL_N["B"]], "ortho_m": 1000.0}]
    elif which == "coverage":
        jobs = [{"name": "cov_A", "kind": "topdown", "arm": "A", "counts": [8000, 16000, 26000, 40000, 60000], "ortho_m": 1000.0},
                {"name": "cov_B", "kind": "topdown", "arm": "B", "counts": [8000, 16000, 26000, 40000, 60000], "ortho_m": 1000.0}]
    else:
        raise SystemExit("unknown set " + which)
    spec = {"set": which, "res": [1920, 1080], "warmup": 24, "settle": 6, "id_gamma": 0.0, "jobs": jobs}
    spec.update(extra)
    SPECS.mkdir(parents=True, exist_ok=True)
    p = SPECS / (which + ".json")
    p.write_text(json.dumps(spec, indent=1))
    print(p, len(jobs), "jobs")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "smoke")
