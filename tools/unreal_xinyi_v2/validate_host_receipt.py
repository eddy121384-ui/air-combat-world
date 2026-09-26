"""Fail-closed structural validator for host-gate JSON receipts."""
import argparse
import json
from pathlib import Path
from host_gate_common import RUN_ID_RE, SCHEMA_VERSION


def validate(value: dict) -> None:
    assert value.get("schema") == SCHEMA_VERSION
    assert isinstance(value.get("receipt_type"), str) and value["receipt_type"]
    assert isinstance(value.get("status"), str) and value["status"]
    assert RUN_ID_RE.fullmatch(value.get("run_id", ""))
    assert isinstance(value.get("runtime_validation"), bool)
    assert isinstance(value.get("created_utc"), str)
    static_receipts = {"snapshot", "landscape_ownership", "cook_commandlet"}
    if value["status"].startswith("PASS_") and value["receipt_type"] not in static_receipts:
        assert value["runtime_validation"] is True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipts", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.receipts:
        validate(json.loads(path.read_text(encoding="utf-8")))
        print(f"HOST_RECEIPT_SCHEMA_OK {path}")


if __name__ == "__main__":
    main()
