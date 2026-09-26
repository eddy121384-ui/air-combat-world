import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools/unreal_xinyi_v2"
sys.path.insert(0, str(TOOLS))

import host_gate_common as common  # noqa: E402
import validate_host_receipt as validator  # noqa: E402
import analyze_streaming_observations as streaming  # noqa: E402


def test_definitions_have_fail_closed_controls():
    data = json.loads((TOOLS / "host_gate_definitions.json").read_text())
    stream = data["streaming"]
    assert stream["fail_if_all_tiles_permanently_loaded"] is True
    assert stream["require_load_and_unload_per_tile"] is True
    controls = [p for p in stream["route"] if "control" in p["id"]]
    assert len(controls) == 2
    assert all(p["expected_tile_count"] == 0 for p in controls)
    collision = data["building_collision"]
    assert "street-negative" in collision["required_sets"]
    assert "courtyard-negative" in collision["required_sets"]
    assert collision["require_separate_terrain_and_building_channels"] is True
    assert data["cook"]["commandlet_success_is_runtime_success"] is False


def test_receipt_json_schema_requires_runtime_discriminator():
    schema = json.loads((TOOLS / "schemas/host-gate-receipt.schema.json").read_text())
    assert "runtime_validation" in schema["required"]
    assert schema["properties"]["schema"]["const"] == common.SCHEMA_VERSION
    assert schema["allOf"][0]["then"]["properties"]["runtime_validation"]["const"] is True


def test_run_id_is_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "git", lambda *_: "abcdef12")
    value = common.new_run_id(tmp_path, datetime(2026, 9, 26, 0, 0, 1, tzinfo=UTC))
    assert value == "20260926T000001Z-abcdef12"
    assert common.RUN_ID_RE.fullmatch(value)


def test_receipt_validator_rejects_static_runtime_pass():
    value = {
        "schema": common.SCHEMA_VERSION,
        "receipt_type": "streaming",
        "status": "PASS_PACKAGED_STREAMING",
        "run_id": "20260926T000001Z-abcdef12",
        "runtime_validation": False,
        "created_utc": "2026-09-26T00:00:01+00:00",
    }
    try:
        validator.validate(value)
    except AssertionError:
        pass
    else:
        raise AssertionError("static receipt must not claim runtime PASS")


def test_streaming_analyzer_rejects_permanent_residency():
    definitions = json.loads((TOOLS / "host_gate_definitions.json").read_text())
    tile_ids = [f"tile-{index:02d}" for index in range(25)]
    observations = [{"id": point["id"], "loaded_tile_ids": tile_ids} for point in definitions["streaming"]["route"]]
    status, failures = streaming.analyze(definitions, observations)
    assert status == "FAIL_PACKAGED_STREAMING"
    assert "all_25_tiles_permanently_loaded" in failures


def test_powershell_never_deletes_or_mutates_originals():
    for name in ("snapshot_host_state.ps1", "run_host_gates.ps1", "cook_xinyi_wp.ps1"):
        text = (TOOLS / name).read_text()
        for forbidden in ("Remove-Item", "save_current_level", "WorldPartitionConvert"):
            assert forbidden not in text
