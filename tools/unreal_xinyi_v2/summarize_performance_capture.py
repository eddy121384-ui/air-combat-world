"""Summarize raw packaged samples; capture completeness is not a budget PASS."""
import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from host_gate_common import SCHEMA_VERSION, write_json_new


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((p / 100) * (len(ordered) - 1))))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    capture = json.loads(args.samples.read_text())
    snapshot = json.loads(args.snapshot.read_text())
    frames = capture.get("frame_time_ms", [])
    required = ("run_label", "startup_to_world_ready_ms", "worst_streaming_hitch_ms", "actor_count", "component_count")
    missing = [key for key in required if key not in capture]
    if capture.get("run_label") not in ("cold", "warm"):
        missing.append("valid_run_label")
    if not frames:
        missing.append("frame_time_ms")
    summary = {"sample_count": len(frames)}
    if frames:
        summary.update({"mean_ms": statistics.fmean(frames), "p50_ms": percentile(frames, 50), "p95_ms": percentile(frames, 95), "p99_ms": percentile(frames, 99), "max_ms": max(frames)})
    receipt = {"schema": SCHEMA_VERSION, "receipt_type": "performance", "status": "PASS_PERFORMANCE_CAPTURE" if not missing else "FAIL_PERFORMANCE_CAPTURE", "runtime_validation": True, "budget_evaluated": False, "created_utc": datetime.now(UTC).isoformat(), "run_id": snapshot["run_id"], "label": capture.get("run_label"), "summary": summary, "raw_metrics": {k: v for k, v in capture.items() if k != "frame_time_ms"}, "missing": missing}
    write_json_new(args.out, receipt)
    if missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
