"""Validate packaged Landscape/building trace observations without changing collision."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from host_gate_common import SCHEMA_VERSION, write_json_new


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("landscape", "building"), required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.observations.read_text())
    snapshot = json.loads(args.snapshot.read_text())
    failures = []
    for row in rows:
        if row.get("actual_hit") != row.get("expected_hit"):
            failures.append({"id": row.get("id"), "reason": "hit_mismatch"})
        if row.get("expected_channel") and row.get("actual_channel") != row["expected_channel"]:
            failures.append({"id": row.get("id"), "reason": "channel_mismatch"})
        if row.get("max_error_cm") is not None and row.get("error_cm", 0) > row["max_error_cm"]:
            failures.append({"id": row.get("id"), "reason": "position_error"})
    status_name = "LANDSCAPE_TRACES" if args.kind == "landscape" else "BUILDING_COLLISION"
    receipt = {"schema": SCHEMA_VERSION, "receipt_type": f"{args.kind}_traces", "status": f"PASS_{status_name}" if not failures and rows else f"FAIL_{status_name}", "runtime_validation": True, "created_utc": datetime.now(UTC).isoformat(), "run_id": snapshot["run_id"], "observation_count": len(rows), "failures": failures}
    write_json_new(args.out, receipt)
    if receipt["status"].startswith("FAIL_"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
