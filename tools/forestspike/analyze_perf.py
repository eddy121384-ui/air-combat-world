"""Summarise ForestSpike CSV-profiler runs (UE5.8 CSV, header row at the end).

  python tools/forestspike/analyze_perf.py [--dir unreal/ForestSpike/Saved/ForestSpike/perf] [--cold 120] [--out summary.json]

Per run: frames [0, cold) are the cold / boot window (level load, shader + streaming warm-up) and are reported
separately; frames >= cold are the warmed window used for the headline numbers. All times are ms of THIS host.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from perf_integrity import read_csv, sha256

REPO = Path(__file__).resolve().parents[2]
COLS = ["FrameTime", "GameThreadTime", "RenderThreadTime", "RHIThreadTime", "GPUTime"]
EXTRA = ["RHI/DrawCalls", "PhysicalUsedMB"]


def parse(path):
    data = read_csv(path)
    cols = {c: data["columns"][c] for c in COLS + EXTRA if c in data["columns"]}
    return cols, data["metadata"]


def classification(path, meta):
    receipt = Path(path).parent / "completion.json"
    if not receipt.exists():
        return "HISTORICAL_ONLY_UNVERIFIED"
    result = json.loads(receipt.read_text(encoding="utf-8-sig"))
    if (result.get("status") == "PASS_FS_PERF_CAPTURE" and result.get("csv_sha256") == sha256(path)
            and all(result.get(k) == meta.get(k) for k in ("tag", "level", "run_id"))):
        return "PASS_FS_PERF_CAPTURE"
    return "FAIL_FS_PERF_CAPTURE"


def pct(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]


def stats(v):
    v = [value for value in v if value is not None]
    if not v:
        return None
    return {"n": len(v), "median": round(statistics.median(v), 3), "p95": round(pct(v, 95), 3), "p99": round(pct(v, 99), 3),
            "max": round(max(v), 3), "min": round(min(v), 3), "mean": round(statistics.fmean(v), 3)}


def summarise(path, cold):
    cols, meta = parse(path)
    out = {"file": Path(path).name, "frames": len(cols.get("FrameTime", [])), "cold_frames": cold, "meta": {
        k: meta.get(k) for k in ("tag", "level", "cpu", "targetframerate", "vsyncenabled", "config")}}
    out["capture_status"] = classification(path, meta)
    out["host_scope"] = "Intel UHD 770 only"
    out["scope"] = "CSV timing summary; does not establish LOD or moving-path validity"
    for c, v in cols.items():
        out[c] = {"cold": stats(v[:cold]), "warm": stats(v[cold:])}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(REPO / "unreal/ForestSpike/Saved/ForestSpike/perf"))
    ap.add_argument("--cold", type=int, default=120)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = [summarise(p, a.cold) for p in sorted(Path(a.dir).rglob("*.csv"))]
    for r in res:
        w = {c: r[c]["warm"] for c in COLS if c in r}
        print("%-52s frames %4d | " % (r["file"][:52], r["frames"]) + " ".join(
            "%s med %.2f p95 %.2f max %.2f;" % (c[:-4] if c.endswith("Time") else c, w[c]["median"], w[c]["p95"], w[c]["max"])
            for c in COLS if c in w))
    if a.out:
        # Historical summaries are evidence; opt for a new path on every audit.
        with Path(a.out).open("x", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
