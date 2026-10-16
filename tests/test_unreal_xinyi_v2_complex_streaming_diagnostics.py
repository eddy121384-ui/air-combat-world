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

from validate_complex_candidate import STREAMING_TERMS, load_run, streaming_stall_terms  # noqa: E402


def _stall(**terms):
    stall = {"step_id": "open_area_+000_+000", "step_index": 76, "wait_seconds": 90.01,
             "wait_ticks": 170000, "source_observed_false_ticks": 0,
             "source_completed_false_ticks": 170000, "all_completed_false_ticks": 170000,
             "runtime_streaming_source_count": 1, "nearest_runtime_source_cm": 0.0}
    stall.update({t: True for t in STREAMING_TERMS})
    stall.update(terms)
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
           "step_timeout_diagnostics": _stall(subsystem_all_streaming_completed=False)}
    _write_run(tmp_path / "run", raw)
    with pytest.raises(ValueError, match=r"FAIL_STEP_TIMEOUT.*subsystem_all_streaming_completed"):
        load_run(tmp_path / "run", "ComplexAsSimple")


def test_probe_records_every_predicate_term_and_keeps_completion_unchanged():
    source = PROBE.read_text(encoding="utf-8")
    assert "step_timeout_diagnostics" in source and "XINYI_COMPLEX_WAIT" in source
    for term in STREAMING_TERMS:
        assert f'TEXT("{term}")' in source
    # Completion still requires all three terms; the change is diagnostic only.
    assert re.search(r"IsComplete\(\) const \{ return bSourceObserved && bSourceCompleted && bAllCompleted; \}", source)
    assert "IsStreamingComplete(" not in source
    assert source.count("EvaluateStreaming(") == 3  # definition, step wait, dynamic wait
