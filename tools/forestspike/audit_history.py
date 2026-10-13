"""Append-only inventory and trajectory audit of original B0 measurements."""
import argparse
import csv
import json
import math
import re
from pathlib import Path

from perf_integrity import read_csv, sha256

ap = argparse.ArgumentParser()
ap.add_argument("--repo", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
saved = a.repo / "unreal/ForestSpike/Saved/ForestSpike"
spec = json.loads((saved / "specs/perf_pilot.json").read_text())
configs = {"L_FSP_" + c["name"]: c for c in spec["configs"]}
inventory = []
paths = list((saved / "perf").glob("*")) + list((saved / "logs").glob("perf_*.log"))
paths += list((a.repo / "unreal/ForestSpike/Content").rglob("*"))
paths += list((a.repo / "docs/evidence/forestspike-b0").rglob("*"))
paths += list((saved / "reports").glob("*"))
for p in sorted(set(paths)):
    if p.is_file():
        inventory.append({"file": p.relative_to(a.repo).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)})
inventory_path = a.out / "preserved_inventory.json"
inventory_data = {"base_head": "7d94d6e0f96ecbd0f6e9572c7a5b32b4f7cc1bbc", "files": inventory}
if inventory_path.exists():
    for row in json.loads(inventory_path.read_text())["files"]:
        original = a.repo / row["file"]
        if sha256(original) != row["sha256"]:
            raise RuntimeError("preserved file changed since first audit: " + row["file"])
else:
    with inventory_path.open("x", encoding="utf-8") as fh:
        json.dump(inventory_data, fh, indent=1)

results, trace = [], []
for p in sorted((saved / "perf").glob("*.csv")):
    data = read_csv(p)
    meta, cols = data["metadata"], data["columns"]
    side = json.loads(p.with_suffix(".json").read_text(encoding="utf-8-sig"))
    cfg = configs[meta["level"]]
    log_path = saved / "logs" / ("perf_%s__%s.log" % (meta["tag"], meta["level"]))
    log = log_path.read_text(encoding="utf-8-sig", errors="replace")
    row = {"file": p.name, "sha256": sha256(p), "frames": data["frames"], "cold_frames": 120,
           "warm_frames": data["frames"] - 120, "tag": meta["tag"], "level": meta["level"],
           "legacy_metadata": data["legacy_metadata"], "raw_tag": data["raw_metadata"].get("tag"),
           "sidecar_match": all(side[k] == meta[k] for k in ("tag", "level")) and side["frames"] == data["frames"],
           "log": log_path.relative_to(a.repo).as_posix(), "log_sha256": sha256(log_path),
           "engine_world_match": bool(re.search(r"Bringing World /Game/ForestSpike/Perf/" + re.escape(meta["level"]) + r"\." + re.escape(meta["level"]) + r" up for play", log)),
           "engine_completed_frames": re.findall(r"LogCsvProfiler: Display:\s+Frames\s*:\s*(\d+)", log),
           "engine_capture_id_match": "Capture started. CSV ID: " + meta["csvid"] in log,
           "engine_finalize_logged": "CSV finalize time" in log,
           "view_columns": [k for k in cols if k.startswith("View/")], "status": "HISTORICAL_ONLY_NOT_NEW_PASS"}
    if "path" in cfg:
        path = cfg["path"]
        poses = path["poses"]
        expected = [[v * s * 100 for v, s in zip(pose["eye_enu"], (1, -1, 1))] for pose in poses]
        samples = []
        for frame, xyz in enumerate(zip(*(cols[k] for k in ("View/PosX", "View/PosY", "View/PosZ")))):
            candidates = []
            for i, (start, end) in enumerate(zip(expected, expected[1:])):
                delta = [y - x for x, y in zip(start, end)]
                denom = sum(v * v for v in delta)
                u = max(0, min(1, sum((v - x) * d for v, x, d in zip(xyz, start, delta)) / denom))
                err = math.sqrt(sum((v - x - u * d) ** 2 for v, x, d in zip(xyz, start, delta))) / 100
                candidates.append((err, (i + u) * path["frames_per_pose"], i, u))
            err, seq_frame, i, u = min(candidates)
            sample = {"csv": p.name, "csv_frame": frame, "warm": frame >= 120, "sequence_frame": round(seq_frame, 4),
                      "path_t_s": round(14 + seq_frame / path["fps"], 6), "pose_from": poses[i]["id"],
                      "pose_to": poses[i + 1]["id"], "alpha": round(u, 6), "position_error_m": round(err, 6),
                      "x_cm": xyz[0], "y_cm": xyz[1], "z_cm": xyz[2]}
            samples.append(sample)
            trace.append(sample)
        valid = [s for s in samples if s["position_error_m"] < 0.02]
        warm = [s for s in valid if s["warm"]]
        row["sequence"] = {"declared_frames": (len(poses) - 1) * path["frames_per_pose"] + 1,
                           "intended_key_interval_s": [14, 32], "nominal_csv_s": data["frames"] / 60,
                           "nominal_warm_s": (data["frames"] - 120) / 60,
                           "trajectory_matching_frames": len(valid), "warm_matching_frames": len(warm),
                           "observed_path_t_s": [min(s["path_t_s"] for s in valid), max(s["path_t_s"] for s in valid)],
                           "observed_warm_path_t_s": [min(s["path_t_s"] for s in warm), max(s["path_t_s"] for s in warm)],
                           "nonmatching_frames": [s["csv_frame"] for s in samples if s["position_error_m"] >= 0.02],
                           "full_18_seconds_measured": False, "warmup_consumed_path": None,
                           "motion_status": "FAIL_STATIONARY_CAMERA" if max(s["sequence_frame"] for s in valid) - min(s["sequence_frame"] for s in valid) < 1 else "SUBSET_ONLY",
                           "warmup_note": "Autoplay without a lead-in would consume motion; these historical views are stationary"}
    results.append(row)
with (a.out / "historical_csv_audit.json").open("x", encoding="utf-8") as fh:
    json.dump(results, fh, indent=1)
with (a.out / "historical_camera_trace.csv").open("x", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=list(trace[0]))
    writer.writeheader()
    writer.writerows(trace)
for row in results:
    print(row["file"], row["frames"], row.get("sequence", {}).get("observed_warm_path_t_s"))
