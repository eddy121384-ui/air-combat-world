"""Validate two engine-authored, host-attested Development game captures.

This script never creates an observation. It checks actual child-process metadata,
immutable file hashes, Unreal log markers, and every route state/delta.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from analyze_streaming_observations import analyze, compare_runs
from host_gate_common import sha256, write_json_new

ERROR = re.compile(
    r"(?:Log(?:WorldPartition|Streaming|Linker|UObjectGlobals|PackageName).*?(?:Error|Failed to load|Can't find file)"
    r"|Fatal error|Failed to resolve actor)", re.IGNORECASE
)
WARNING = re.compile(r"\bWarning:\s")
MOVE = re.compile(r"XINYI_HOST_MOVE ([a-z0-9-]+) ")
POINT = re.compile(r"XINYI_HOST_POINT ([a-z0-9-]+) ")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_one(root: Path, index: int, plan: dict, snapshot: dict,
                 route_path: Path, snapshot_path: Path) -> tuple[dict, dict, list[str]]:
    raw_path = root / f"20-packaged-{index}.raw.json"
    log_path = root / f"20-packaged-{index}.log"
    host_path = root / f"21-packaged-{index}-host.json"
    raw, host = load(raw_path), load(host_path)
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    failures: list[str] = []
    prefix = f"run_{index}:"
    if host.get("schema") != "xinyi-packaged-launch/v1" or host.get("run_index") != index:
        failures.append(prefix + "host_receipt_schema")
    if host.get("run_id") != snapshot.get("run_id") or raw.get("run_id") != snapshot.get("run_id"):
        failures.append(prefix + "run_id")
    if host.get("process_id") != raw.get("process_id"):
        failures.append(prefix + "process_id_not_child")
    if host.get("exit_code") != 0 or host.get("timed_out") is not False:
        failures.append(prefix + "process_exit")
    if host.get("route_sha256") != sha256(route_path) or host.get("snapshot_sha256") != sha256(snapshot_path):
        failures.append(prefix + "route_or_snapshot_hash")
    if host.get("raw_sha256") != sha256(raw_path) or host.get("log_sha256") != sha256(log_path):
        failures.append(prefix + "raw_or_log_hash")
    exe = Path(host.get("executable", ""))
    archive = (root / "packaged-development").resolve()
    expected_exe = archive / "Windows" / "AirCombatWorld" / "Binaries" / "Win64" / "AirCombatWorld.exe"
    if (not exe.is_file() or exe.resolve() != expected_exe or
            host.get("executable_sha256") != sha256(exe)):
        failures.append(prefix + "packaged_executable_identity")
    if raw.get("schema") != "xinyi-runtime-engine-observation/v1" or raw.get("world_type") != "Game":
        failures.append(prefix + "engine_game_world")
    if raw.get("status") != "ENGINE_ROUTE_COMPLETE":
        failures.append(prefix + "engine_route_incomplete")
    max_range = raw.get("max_loading_range_cm")
    if (type(max_range) not in (int, float) or max_range <= 0 or
            max_range >= plan["control_clearance_m"] * 100 or
            raw.get("far_control_distance_certified") is not True or
            not raw.get("runtime_loading_ranges")):
        failures.append(prefix + "control_distance_not_certified")
    route_ids = [p["id"] for p in plan["streaming"]["route"]]
    if [m.group(1) for line in lines if (m := MOVE.search(line))] != route_ids:
        failures.append(prefix + "log_move_sequence")
    if [m.group(1) for line in lines if (m := POINT.search(line))] != route_ids:
        failures.append(prefix + "log_point_sequence")
    if not any("XINYI_HOST_FINISH ENGINE_ROUTE_COMPLETE" in line for line in lines):
        failures.append(prefix + "log_finish_marker")
    errors = [line for line in lines if ERROR.search(line)]
    warnings = [line for line in lines if WARNING.search(line)]
    performance_changes = [line for line in lines if "LogWorldPartition: Streaming performance changed:" in line]
    if errors:
        failures.append(prefix + "logged_streaming_or_reference_errors")
    capture = dict(raw)
    capture.update(mode="packaged_development", fresh_process=True,
                   route_plan_sha256=sha256(route_path), snapshot_sha256=sha256(snapshot_path))
    status, semantic = analyze(plan, capture)
    failures.extend(prefix + item for item in semantic)
    points = capture.get("points", [])
    for point in points:
        label = point.get("id", "unknown")
        if (point.get("source_registered") is not True or
                point.get("source_observed") is not True or
                point.get("source_enabled") is not True or
                point.get("active_source_count") != 1):
            failures.append(prefix + "source_ownership:" + label)
        terrain = point.get("terrain", {})
        if terrain.get("root_actor_count") != 1:
            failures.append(prefix + "terrain_root:" + label)
        if point.get("kind") == "tile" and (terrain.get("proxy_actor_count", 0) < 1 or
                terrain.get("render_component_count", 0) < 1):
            failures.append(prefix + "terrain_unavailable_near_tile:" + label)
        if point.get("kind") == "control" and (terrain.get("proxy_actor_count") != 0 or
                terrain.get("render_component_count") != 0):
            failures.append(prefix + "terrain_still_streamed_at_control:" + label)
    info = {
        "run_index": index, "launch_id": host.get("launch_id"),
        "process_id": host.get("process_id"), "started_utc": host.get("started_utc"),
        "finished_utc": host.get("finished_utc"), "exit_code": host.get("exit_code"),
        "executable": str(exe), "executable_sha256": host.get("executable_sha256"),
        "raw_sha256": sha256(raw_path), "log_sha256": sha256(log_path),
        "point_count": len(points), "max_loading_range_cm": max_range,
        "loaded_tile_union": sorted({t for p in points for t in p.get("loaded_tile_ids", [])}),
        "load_union": sorted({t for p in points for t in p.get("load_delta", [])}),
        "unload_union": sorted({t for p in points for t in p.get("unload_delta", [])}),
        "control_counts": [p.get("loaded_actor_count") for p in points if p.get("kind") == "control"],
        "max_hitch_ms": max((p.get("hitch_ms", 0) for p in points), default=0),
        "max_wait_ms": max((p.get("wait_ms", 0) for p in points), default=0),
        "logged_error_count": len(errors), "logged_warning_count": len(warnings),
        "logged_errors": errors[:20], "logged_warnings": warnings[:20],
        "streaming_performance_changes": performance_changes,
    }
    return capture, info, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    route_path, snapshot_path = root / "10-streaming-route.json", root / "00-snapshot.json"
    plan, snapshot = load(route_path), load(snapshot_path)
    runs = [validate_one(root, i, plan, snapshot, route_path, snapshot_path) for i in (1, 2)]
    first, second = runs[0][0], runs[1][0]
    failures = runs[0][2] + runs[1][2] + compare_runs(first, second)
    if runs[0][1]["launch_id"] == runs[1][1]["launch_id"] or first.get("process_id") == second.get("process_id"):
        failures.append("not_distinct_fresh_processes")
    if runs[0][1]["executable_sha256"] != runs[1][1]["executable_sha256"]:
        failures.append("different_executable_between_runs")
    receipt = {
        "schema": "xinyi-packaged-runtime-gate/v1", "run_id": snapshot.get("run_id"),
        "status": "PASS_PACKAGED_STREAMING" if not failures else "FAIL_PACKAGED_STREAMING",
        "runtime_validation": not failures, "created_utc": datetime.now(UTC).isoformat(),
        "route_plan_sha256": sha256(route_path), "snapshot_sha256": sha256(snapshot_path),
        "world": plan.get("world"), "runs": [run[1] for run in runs],
        "failures": sorted(set(failures)),
    }
    if args.out.exists():
        existing = load(args.out)
        receipt["created_utc"] = existing.get("created_utc")
        if existing != receipt:
            raise ValueError("existing gate receipt differs from revalidated inputs; refusing overwrite")
    else:
        write_json_new(args.out, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out),
                      "failures": receipt["failures"]}))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
