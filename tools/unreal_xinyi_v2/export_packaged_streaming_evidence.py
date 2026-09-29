"""Export reviewable, path-free point evidence from a passed local host gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from host_gate_common import sha256, write_json_new


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    gate = load(root / "30-packaged-streaming-gate.json")
    immutability = load(root / "90-source-immutability.json")
    route = load(root / "10-streaming-route.json")
    if (gate["status"] != "PASS_PACKAGED_STREAMING" or gate["failures"] or
            immutability["status"] != "PASS_SOURCE_IMMUTABILITY" or
            gate["run_id"] != immutability["run_id"] or
            gate["route_plan_sha256"] != sha256(root / "10-streaming-route.json")):
        raise ValueError("passing packaged and source-immutability receipts required")
    runs = []
    for number, attestation in enumerate(gate["runs"], 1):
        raw = load(root / f"20-packaged-{number}.raw.json")
        if len(raw["points"]) != 27 or raw["process_id"] != attestation["process_id"]:
            raise ValueError(f"run {number} raw receipt mismatch")
        points = []
        for point in raw["points"]:
            points.append({key: point[key] for key in (
                "id", "kind", "expected_tile_id", "location_cm", "requested_state",
                "source_enabled", "source_registered", "source_observed", "active_source_count",
                "streaming_completed", "wait_ms", "hitch_ms", "loaded_cell_count",
                "loaded_cell_names", "active_cell_names", "terrain_cell_names", "loaded_tile_ids",
                "loaded_actor_count", "load_delta", "unload_delta", "placement_max_error_cm",
                "missing_refs", "terrain", "errors"
            )})
        runs.append({
            "run_index": number, "process_id": attestation["process_id"],
            "launch_id": attestation["launch_id"],
            "executable_sha256": attestation["executable_sha256"],
            "raw_sha256": attestation["raw_sha256"], "log_sha256": attestation["log_sha256"],
            "max_loading_range_cm": attestation["max_loading_range_cm"],
            "control_counts": attestation["control_counts"],
            "max_hitch_ms": attestation["max_hitch_ms"],
            "max_wait_ms": attestation["max_wait_ms"],
            "logged_error_count": attestation["logged_error_count"],
            "logged_warning_count": attestation["logged_warning_count"],
            "streaming_performance_changes": attestation["streaming_performance_changes"],
            "points": points,
        })
    evidence = {
        "schema": "xinyi-packaged-streaming-evidence/v1", "run_id": gate["run_id"],
        "status": gate["status"], "runtime_validation": True,
        "world": gate["world"], "source_contract_sha256": route["source_contract_sha256"],
        "route_plan_sha256": gate["route_plan_sha256"],
        "snapshot_sha256": gate["snapshot_sha256"],
        "source_immutability_status": immutability["status"],
        "protected_file_rows": immutability["baseline_file_rows"],
        "control_clearance_m": route["control_clearance_m"],
        "runs": runs,
    }
    write_json_new(args.out, evidence)
    print(args.out)


if __name__ == "__main__":
    main()
