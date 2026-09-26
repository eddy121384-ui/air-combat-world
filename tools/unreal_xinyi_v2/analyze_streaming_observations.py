"""Turn packaged-runtime JSON observations into a fail-closed streaming receipt."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from host_gate_common import SCHEMA_VERSION, write_json_new


def analyze(definitions: dict, observations: list[dict]) -> tuple[str, list[str]]:
    failures = []
    expected_points = [point["id"] for point in definitions["streaming"]["route"]]
    actual_points = [point.get("id") for point in observations]
    if actual_points != expected_points:
        failures.append("route_order_or_completeness")
    if any(point.get("timed_out") for point in observations):
        failures.append("streaming_timeout")
    controls = {p["id"]: p["expected_tile_count"] for p in definitions["streaming"]["route"] if "expected_tile_count" in p}
    for point in observations:
        if point.get("id") in controls and len(point.get("loaded_tile_ids", [])) != controls[point["id"]]:
            failures.append(f"control_tile_count:{point.get('id')}")
    loaded_sets = [set(point.get("loaded_tile_ids", [])) for point in observations]
    universe = set().union(*loaded_sets) if loaded_sets else set()
    if len(universe) != 25:
        failures.append("not_all_25_tiles_observed")
    if loaded_sets and all(len(loaded) == 25 for loaded in loaded_sets):
        failures.append("all_25_tiles_permanently_loaded")
    transitions = {tile: {"load": False, "unload": False} for tile in universe}
    for before, after in zip(loaded_sets, loaded_sets[1:]):
        for tile in after - before:
            transitions[tile]["load"] = True
        for tile in before - after:
            transitions[tile]["unload"] = True
    if definitions["streaming"]["require_load_and_unload_per_tile"]:
        for tile, states in transitions.items():
            if not all(states.values()):
                failures.append(f"missing_transition:{tile}")
    return ("PASS_PACKAGED_STREAMING" if not failures else "FAIL_PACKAGED_STREAMING", sorted(set(failures)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--definitions", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    definitions = json.loads(args.definitions.read_text())
    observations = json.loads(args.observations.read_text())
    snapshot = json.loads(args.snapshot.read_text())
    status, failures = analyze(definitions, observations)
    receipt = {"schema": SCHEMA_VERSION, "receipt_type": "streaming", "status": status, "runtime_validation": True, "created_utc": datetime.now(UTC).isoformat(), "run_id": snapshot["run_id"], "world": definitions["world"], "observations": observations, "failures": failures}
    write_json_new(args.out, receipt)
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
