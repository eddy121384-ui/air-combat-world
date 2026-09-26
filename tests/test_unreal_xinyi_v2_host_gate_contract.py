import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools/unreal_xinyi_v2"
sys.path.insert(0, str(TOOLS))

import host_gate_common as common  # noqa: E402
import validate_host_receipt as validator  # noqa: E402
import analyze_streaming_observations as streaming  # noqa: E402
import prepare_streaming_route as route_builder  # noqa: E402


def accepted_contract():
    east, north = 1240.0, -1875.0  # Nonzero origin catches hardcoded world positions.
    return {
        "status": "PASS_CONTRACT",
        "upstream": {
            "building_source_sha256": route_builder.EXPECTED_SOURCE,
            "building_manifest_sha256": route_builder.EXPECTED_MANIFEST,
        },
        "landscape": {"components": [5, 5], "component_size_m": 500.0},
        "coordinate_contract": {
            "unreal_mapping": "UE X = east*100 cm; UE Y = -north*100 cm; UE Z = up*100 cm",
            "extent_enu_m": {
                "min_east_m": east, "max_east_m": east + 2500,
                "min_north_m": north, "max_north_m": north + 2500,
            },
        },
        "building_placement": {"runtime_tile_count": 25},
        "tiles": [
            {
                "tile": f"x{x}y{y}", "origin_enu_m": [east + x * 500, north + y * 500],
                "expected_ue_translation_cm": [(east + x * 500) * 100, -(north + y * 500) * 100, 0],
                "runtime_building_sha256": "a" * 64,
            }
            for x in range(5) for y in range(5)
        ],
    }


def plan():
    definitions = json.loads((TOOLS / "host_gate_definitions.json").read_text())
    return route_builder.make_plan(accepted_contract(), definitions, "b" * 64, "c" * 64)


def valid_capture(route):
    previous = set()
    points = []
    for target in route["streaming"]["route"]:
        current = {target["expected_tile_id"]} if target["kind"] == "tile" else set()
        points.append({
            "id": target["id"], "location_cm": target["location_cm"],
            "streaming_completed": True, "wait_ms": 150,
            "loaded_tile_ids": sorted(current), "loaded_actor_count": len(current),
            "load_delta": sorted(current - previous), "unload_delta": sorted(previous - current),
            "terrain": {"render_component_count": 1, "collision_component_count": 1},
            "missing_refs": [], "errors": [], "placement_max_error_cm": 0.0,
            "hitch_ms": 0.0,
        })
        previous = current
    return {"mode": "packaged_development", "fresh_process": True, "process_id": "process-A",
            "world": route["world"], "points": points}


def test_route_uses_accepted_tile_origins_and_serpentine_order():
    route = plan()
    points = route["streaming"]["route"]
    assert len(points) == 27
    assert len({p["expected_tile_id"] for p in points if p["kind"] == "tile"}) == 25
    assert points[0]["expected_tile_count"] == points[-1]["expected_tile_count"] == 0
    assert points[1]["expected_tile_id"] == "x0y4"
    assert points[5]["expected_tile_id"] == "x4y4"
    assert points[6]["expected_tile_id"] == "x4y3"
    assert points[1]["location_cm"] == [149000, -37500, 30000]
    assert points[0]["location_cm"][0] == -376000
    assert points[-1]["location_cm"][0] == 874000
    assert route["source_contract_sha256"] == "b" * 64


def test_route_rejects_grid_mapping_and_hash_drift():
    definitions = json.loads((TOOLS / "host_gate_definitions.json").read_text())
    for change in ("missing_tile", "wrong_translation", "wrong_manifest"):
        contract = accepted_contract()
        if change == "missing_tile":
            contract["tiles"].pop()
        elif change == "wrong_translation":
            contract["tiles"][0]["expected_ue_translation_cm"][1] *= -1
        else:
            contract["upstream"]["building_manifest_sha256"] = "0" * 64
        try:
            route_builder.make_plan(contract, definitions, "b" * 64, "c" * 64)
        except ValueError:
            pass
        else:
            raise AssertionError(f"contract drift accepted: {change}")


def test_streaming_diagnostics_never_certify_external_json():
    route = plan()
    status, failures = streaming.analyze(route, valid_capture(route))
    assert status == "NOT_RUN_PACKAGED_STREAMING"
    assert failures == []


def test_two_clean_runs_must_have_distinct_processes_and_matching_states():
    route = plan()
    first, second = valid_capture(route), valid_capture(route)
    assert streaming.compare_runs(first, second) == ["repeat_not_distinct_process"]
    second["process_id"] = "process-B"
    assert streaming.compare_runs(first, second) == []
    second["points"][1]["loaded_tile_ids"] = []
    assert any(x.startswith("repeat_state_mismatch") for x in streaming.compare_runs(first, second))


def test_streaming_diagnostics_catch_missing_and_permanent_tiles():
    route = plan()
    capture = valid_capture(route)
    capture["points"][3]["loaded_tile_ids"] = []
    status, failures = streaming.analyze(route, capture)
    assert status == "FAIL_PACKAGED_STREAMING"
    assert any(item.startswith("target_tile_not_loaded") for item in failures)

    capture = valid_capture(route)
    ids = [p["expected_tile_id"] for p in route["streaming"]["route"] if p["kind"] == "tile"]
    for point in capture["points"]:
        point["loaded_tile_ids"] = ids
    status, failures = streaming.analyze(route, capture)
    assert status == "FAIL_PACKAGED_STREAMING"
    assert "control_tile_count:outside-east-control" in failures


def test_streaming_diagnostics_reject_timeout_and_unknown_tile():
    route = plan()
    capture = valid_capture(route)
    capture["points"][1]["wait_ms"] = 121000
    capture["points"][2]["loaded_tile_ids"] = ["not-an-accepted-tile"]
    status, failures = streaming.analyze(route, capture)
    assert status == "FAIL_PACKAGED_STREAMING"
    assert any(item.startswith("completion_or_timeout") for item in failures)
    assert any(item.startswith("tile_identity_or_duplicate") for item in failures)


def test_route_and_observation_cli_bind_to_snapshot_without_runtime_pass(tmp_path):
    contract_file = tmp_path / "xinyi_unreal_v2_contract.json"
    contract_file.write_text(json.dumps(accepted_contract()))
    definitions_file = TOOLS / "host_gate_definitions.json"
    route_file = tmp_path / "10-streaming-route.json"
    subprocess.run([sys.executable, str(TOOLS / "prepare_streaming_route.py"),
                    "--contract", str(contract_file), "--definitions", str(definitions_file),
                    "--out", str(route_file)], check=True, capture_output=True)
    route = json.loads(route_file.read_text())
    assert route["source_contract_sha256"] == common.sha256(contract_file)
    snapshot_file = tmp_path / "00-snapshot.json"
    snapshot = {"status": "PASS_SNAPSHOT", "run_id": "20260926T000001Z-abcdef12",
                "files": [{"category": "offline_contracts", "sha256": common.sha256(contract_file)}]}
    snapshot_file.write_text(json.dumps(snapshot))
    observations_file = tmp_path / "observations.json"
    capture = valid_capture(route)
    capture.update({"run_id": snapshot["run_id"],
                    "route_plan_sha256": common.sha256(route_file),
                    "snapshot_sha256": common.sha256(snapshot_file)})
    observations_file.write_text(json.dumps(capture))
    repeat_file = tmp_path / "repeat-observations.json"
    repeat = valid_capture(route)
    repeat.update({"run_id": snapshot["run_id"], "process_id": "process-B",
                   "route_plan_sha256": common.sha256(route_file),
                   "snapshot_sha256": common.sha256(snapshot_file)})
    repeat_file.write_text(json.dumps(repeat))
    receipt_file = tmp_path / "30-streaming-diagnostic.json"
    result = subprocess.run([sys.executable, str(TOOLS / "analyze_streaming_observations.py"),
                             "--route-plan", str(route_file), "--snapshot", str(snapshot_file),
                             "--observations", str(observations_file),
                             "--repeat-observations", str(repeat_file), "--out", str(receipt_file)],
                            capture_output=True)
    assert result.returncode == 3  # valid data, runtime provenance still unverified
    receipt = json.loads(receipt_file.read_text())
    assert receipt["status"] == "NOT_RUN_PACKAGED_STREAMING"
    assert receipt["runtime_validation"] is False
    assert receipt["failures"] == []


def test_definitions_retain_collision_and_cook_guardrails():
    data = json.loads((TOOLS / "host_gate_definitions.json").read_text())
    assert data["streaming"]["route_spec"]["tile_center_count"] == 25
    assert data["building_collision"]["require_separate_terrain_and_building_channels"] is True
    assert data["cook"]["commandlet_success_is_runtime_success"] is False


def test_receipt_validator_never_promotes_static_or_incomplete_results():
    for status, runtime_validation in (
        ("PASS_PACKAGED_STREAMING", False), ("NOT_RUN_PACKAGED_STREAMING", True)
    ):
        value = {
            "schema": common.SCHEMA_VERSION, "receipt_type": "streaming",
            "status": status, "run_id": "20260926T000001Z-abcdef12",
            "runtime_validation": runtime_validation,
            "created_utc": "2026-09-26T00:00:01+00:00",
        }
        try:
            validator.validate(value)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"invalid runtime claim accepted: {status}")


def test_receipt_json_schema_requires_runtime_discriminator():
    schema = json.loads((TOOLS / "schemas/host-gate-receipt.schema.json").read_text())
    assert "runtime_validation" in schema["required"]
    assert schema["allOf"][0]["then"]["properties"]["runtime_validation"]["const"] is True


def test_run_id_is_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "git", lambda *_: "abcdef12")
    value = common.new_run_id(tmp_path, datetime(2026, 9, 26, 0, 0, 1, tzinfo=UTC))
    assert value == "20260926T000001Z-abcdef12"
    assert common.RUN_ID_RE.fullmatch(value)


def test_powershell_never_deletes_or_mutates_originals():
    for name in ("snapshot_host_state.ps1", "prepare_streaming_route.ps1", "run_host_gates.ps1", "cook_xinyi_wp.ps1"):
        text = (TOOLS / name).read_text()
        for forbidden in ("Remove-Item", "save_current_level", "WorldPartitionConvert"):
            assert forbidden not in text
