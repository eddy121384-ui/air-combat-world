"""Regression: a Complex candidate step timeout must name the false streaming predicate term."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "unreal_xinyi_v2"
PROBE = ROOT / "unreal/Plugins/XinyiHostStreamingProbe/Source/XinyiHostStreamingProbe/Private/XinyiComplexCandidateProbe.cpp"
sys.path.insert(0, str(TOOLS))

from validate_complex_candidate import (  # noqa: E402
    STREAMING_TERMS,
    load_run,
    streaming_stall_readback,
    streaming_stall_terms,
)


def _readback(**fields):
    back = {"set_actor_location_returned": True, "actor_location_cm": [25000.0, -20000.0, 1000.0],
            "actor_distance_to_target_cm": 0.0, "component_streaming_source_returned": True,
            "component_source_location_cm": [25000.0, -20000.0, 1000.0],
            "component_source_distance_to_target_cm": 0.0, "source_enabled": True, "provider_registered": True}
    back.update(fields)
    return back


def _stall(readback=None, **terms):
    stall = {"step_id": "open_area_+000_+000", "step_index": 76, "wait_seconds": 90.01,
             "wait_ticks": 170000, "source_observed_false_ticks": 0,
             "source_completed_false_ticks": 170000, "all_completed_false_ticks": 170000,
             "runtime_streaming_source_count": 1, "nearest_runtime_source_cm": 0.0}
    stall.update({t: True for t in STREAMING_TERMS})
    stall.update(terms)
    if readback is not None:
        stall["source_readback"] = readback
    return stall


def _write_run(run, raw):
    run.mkdir()
    raw_path = run / "30-complex-complexassimple.raw.json"
    log_path = run / "30-complex-complexassimple.log"
    raw_path.write_text(json.dumps(raw))
    log_path.write_text("XINYI_COMPLEX_FINISH FAIL_STEP_TIMEOUT mode=ComplexAsSimple\n")
    host = {"mode": "ComplexAsSimple", "process_id": "4242", "timed_out": False, "exit_code": 0,
            "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest()}
    (run / "31-complex-complexassimple-host.json").write_text(json.dumps(host))


def test_stall_terms_name_each_false_term():
    raw = {"step_timeout_diagnostics": _stall(source_streaming_completed=False,
                                              subsystem_all_streaming_completed=False)}
    assert streaming_stall_terms(raw) == ["source_streaming_completed", "subsystem_all_streaming_completed"]
    assert streaming_stall_terms({"step_timeout_diagnostics": _stall(source_observed_at_target=False)}) == [
        "source_observed_at_target"]


def test_stall_terms_report_missing_or_malformed_diagnostics():
    # September/October-1 packages predate the diagnostics: never guess a cause.
    assert streaming_stall_terms({}) == ["unrecorded"]
    assert streaming_stall_terms({"step_timeout_diagnostics": {"source_observed_at_target": 1}}) == ["unrecorded"]


def test_timed_out_candidate_is_refused_with_named_terms(tmp_path):
    raw = {"mode": "ComplexAsSimple", "process_id": 4242, "status": "FAIL_STEP_TIMEOUT",
           "step_timeout_diagnostics": _stall(_readback(), subsystem_all_streaming_completed=False)}
    _write_run(tmp_path / "run", raw)
    with pytest.raises(ValueError, match=r"FAIL_STEP_TIMEOUT.*subsystem_all_streaming_completed"
                                         r".*world_partition_source_list_stale"):
        load_run(tmp_path / "run", "ComplexAsSimple")


@pytest.mark.parametrize("fields, expected", [
    # The 2026-10-16 stalls left WP's only source 45,069.391 cm away at the previous step.
    ({}, "world_partition_source_list_stale"),
    ({"set_actor_location_returned": False}, "source_actor_not_at_target"),
    ({"actor_distance_to_target_cm": 45069.391}, "source_actor_not_at_target"),
    ({"component_source_distance_to_target_cm": 45069.391}, "component_source_not_at_target"),
    ({"component_streaming_source_returned": False, "component_source_distance_to_target_cm": -1.0},
     "component_source_not_at_target"),
    ({"source_enabled": False}, "component_source_not_at_target"),
    ({"provider_registered": False}, "provider_unregistered"),
    ({"actor_distance_to_target_cm": 1.0}, "world_partition_source_list_stale"),  # probe's 1 cm rule
])
def test_readback_names_the_first_broken_link(fields, expected):
    raw = {"step_timeout_diagnostics": _stall(_readback(**fields), source_observed_at_target=False)}
    assert streaming_stall_readback(raw) == expected


def test_readback_absent_in_older_packages_is_unrecorded():
    assert streaming_stall_readback({}) == "unrecorded"
    assert streaming_stall_readback({"step_timeout_diagnostics": _stall()}) == "unrecorded"


def test_probe_records_every_predicate_term_and_keeps_completion_unchanged():
    source = PROBE.read_text(encoding="utf-8")
    assert "step_timeout_diagnostics" in source and "XINYI_COMPLEX_WAIT" in source
    for term in STREAMING_TERMS:
        assert f'TEXT("{term}")' in source
    # Completion still requires all three terms; the change is diagnostic only.
    assert re.search(r"IsComplete\(\) const \{ return bSourceObserved && bSourceCompleted && bAllCompleted; \}", source)
    assert "IsStreamingComplete(" not in source
    assert source.count("EvaluateStreaming(") == 3  # definition, step wait, dynamic wait


def test_probe_reads_back_every_link_the_classifier_needs():
    source = PROBE.read_text(encoding="utf-8")
    assert "bMoveAccepted = SourceActor->SetActorLocation(Step.Source);" in source
    assert 'Stall->SetObjectField(TEXT("source_readback"), SourceReadback(Step.Source));' in source
    for field in _readback():
        assert f'TEXT("{field}")' in source
