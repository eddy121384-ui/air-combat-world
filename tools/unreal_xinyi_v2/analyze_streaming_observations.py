"""Offline diagnostics for a contract-derived World Partition streaming route.

Supplied JSON cannot authenticate a packaged Unreal process. Never emit runtime PASS.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from host_gate_common import SCHEMA_VERSION, sha256, write_json_new


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def identities(value, expected):
    return (isinstance(value, list)
            and all(isinstance(tile, str) and tile in expected for tile in value)
            and len(value) == len(set(value)))


def analyze(plan: dict, capture: dict) -> tuple[str, list[str]]:
    failures = []
    route = plan["streaming"]["route"]
    expected = {p["expected_tile_id"] for p in route if p["kind"] == "tile"}
    if (plan.get("schema") != "xinyi-host-route/v1" or len(route) != 27
            or len(expected) != 25 or route[0]["kind"] != "control"
            or route[-1]["kind"] != "control"):
        failures.append("incomplete_25_tile_route")
    if capture.get("mode") != "packaged_development" or capture.get("fresh_process") is not True:
        failures.append("capture_process_metadata")
    if not isinstance(capture.get("process_id"), str) or not capture["process_id"]:
        failures.append("missing_process_id")
    if capture.get("world") != plan.get("world"):
        failures.append("world_mismatch")
    points = capture.get("points")
    if not isinstance(points, list):
        points = []
    if [p.get("id") if isinstance(p, dict) else None for p in points] != [p["id"] for p in route]:
        failures.append("route_order_or_completeness")

    prior = set()
    seen, centers, loads, unloads = set(), set(), set(), set()
    for index, target in enumerate(route):
        if index >= len(points) or not isinstance(points[index], dict):
            continue
        point = points[index]
        label = target["id"]
        loc = point.get("location_cm")
        if (point.get("id") != label or not isinstance(loc, list) or len(loc) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in loc)
                or any(abs(a - b) > 1 for a, b in zip(loc, target["location_cm"]))):
            failures.append(f"source_position:{label}")
        wait = point.get("wait_ms")
        if (point.get("streaming_completed") is not True or not number(wait)
                or wait > plan["streaming"]["timeout_seconds"] * 1000):
            failures.append(f"completion_or_timeout:{label}")
        tiles = point.get("loaded_tile_ids")
        if not identities(tiles, expected):
            failures.append(f"tile_identity_or_duplicate:{label}")
            continue
        current = set(tiles)
        seen |= current
        if target["kind"] == "control" and current:
            failures.append(f"control_tile_count:{label}")
        if target["kind"] == "tile":
            tile = target["expected_tile_id"]
            if tile not in current:
                failures.append(f"target_tile_not_loaded:{label}")
            else:
                centers.add(tile)
        entered, exited = current - prior, prior - current
        if not identities(point.get("load_delta"), expected) or set(point["load_delta"]) != entered:
            failures.append(f"load_delta:{label}")
        if not identities(point.get("unload_delta"), expected) or set(point["unload_delta"]) != exited:
            failures.append(f"unload_delta:{label}")
        loads |= entered
        unloads |= exited
        prior = current
        if type(point.get("loaded_actor_count")) is not int or point["loaded_actor_count"] != len(current):
            failures.append(f"actor_count:{label}")
        terrain = point.get("terrain")
        if (not isinstance(terrain, dict) or
                any(type(terrain.get(k)) is not int or terrain[k] < 0
                    for k in ("render_component_count", "collision_component_count"))):
            failures.append(f"terrain_inventory:{label}")
        if point.get("missing_refs") != [] or point.get("errors") != []:
            failures.append(f"refs_or_errors:{label}")
        if not number(point.get("placement_max_error_cm")) or point["placement_max_error_cm"] > 0.1:
            failures.append(f"placement_drift:{label}")
        if not number(point.get("hitch_ms")):
            failures.append(f"hitch_measurement:{label}")
    if seen != expected:
        failures.append("not_all_25_tiles_observed")
    if centers != expected:
        failures.append("not_all_25_centers_loaded")
    if loads != expected or unloads != expected:
        failures.append("missing_tile_load_or_unload")
    failures = sorted(set(failures))
    return ("FAIL_PACKAGED_STREAMING" if failures else "NOT_RUN_PACKAGED_STREAMING", failures)


def compare_runs(first: dict, second: dict) -> list[str]:
    failures = []
    if first.get("process_id") == second.get("process_id"):
        failures.append("repeat_not_distinct_process")
    a, b = first.get("points"), second.get("points")
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        return failures + ["repeat_route_length"]
    for point_a, point_b in zip(a, b):
        if not isinstance(point_a, dict) or not isinstance(point_b, dict):
            failures.append("repeat_malformed_point")
            continue
        for name in ("id", "loaded_tile_ids", "load_delta", "unload_delta", "loaded_actor_count", "terrain"):
            left, right = point_a.get(name), point_b.get(name)
            if (name in ("loaded_tile_ids", "load_delta", "unload_delta")
                    and isinstance(left, list) and isinstance(right, list)
                    and all(isinstance(v, str) for v in left + right)):
                left, right = set(left), set(right)
            if left != right:
                failures.append(f"repeat_state_mismatch:{point_a.get('id')}:{name}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-plan", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--repeat-observations", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.route_plan.read_text(encoding="utf-8"))
    capture = json.loads(args.observations.read_text(encoding="utf-8"))
    repeat = json.loads(args.repeat_observations.read_text(encoding="utf-8"))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    status, failures = analyze(plan, capture)
    _, repeat_failures = analyze(plan, repeat)
    failures.extend(repeat_failures)
    failures.extend(compare_runs(capture, repeat))
    if snapshot.get("status") != "PASS_SNAPSHOT":
        failures.append("snapshot_not_passed")
    if capture.get("run_id") != snapshot.get("run_id") or repeat.get("run_id") != snapshot.get("run_id"):
        failures.append("run_id_mismatch")
    if any(c.get("route_plan_sha256") != sha256(args.route_plan) for c in (capture, repeat)):
        failures.append("route_plan_hash_mismatch")
    if any(c.get("snapshot_sha256") != sha256(args.snapshot) for c in (capture, repeat)):
        failures.append("snapshot_hash_mismatch")
    contract_hashes = {row.get("sha256") for row in snapshot.get("files", [])
                       if row.get("category") == "offline_contracts"}
    if plan.get("source_contract_sha256") not in contract_hashes:
        failures.append("contract_not_in_snapshot")
    failures = sorted(set(failures))
    if failures:
        status = "FAIL_PACKAGED_STREAMING"
    receipt = {
        "schema": SCHEMA_VERSION, "receipt_type": "streaming", "status": status,
        "runtime_validation": False, "analysis_only": True,
        "created_utc": datetime.now(UTC).isoformat(), "run_id": snapshot["run_id"],
        "world": plan["world"], "route_plan_sha256": sha256(args.route_plan),
        "snapshot_sha256": sha256(args.snapshot),
        "observations_sha256": sha256(args.observations),
        "repeat_observations_sha256": sha256(args.repeat_observations),
        "observation_count": len(capture.get("points", [])), "failures": failures,
    }
    write_json_new(args.out, receipt)
    raise SystemExit(2 if failures else 3)


if __name__ == "__main__":
    main()
