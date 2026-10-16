"""Rehash a host snapshot after testing without modifying source packages."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from host_gate_common import SCHEMA_VERSION, git, sha256, write_json_new
from snapshot_host_state import INVENTORY_POLICY, inventory_rows, protected_git_status


def compare(snapshot: dict, current_rows: list[dict], head: str, branch: str,
            git_status: str) -> list[dict]:
    failures = []
    if snapshot.get("schema") != SCHEMA_VERSION or snapshot.get("status") != "PASS_SNAPSHOT":
        failures.append({"reason": "snapshot_not_passed"})
    if snapshot.get("inventory_policy") != INVENTORY_POLICY:
        failures.append({"reason": "inventory_policy_mismatch"})
    requirements = snapshot.get("requirements")
    if (not isinstance(requirements, dict)
            or not all(requirements.get(k) is True for k in (
                "source_map", "wp_map", "building_assets", "engine_version", "external_actor_packages"))):
        failures.append({"reason": "snapshot_requirements_missing_or_failed"})
    repository = snapshot.get("repository") or {}
    if repository.get("head") != head or repository.get("branch") != branch:
        failures.append({"reason": "repository_ref_changed", "expected": repository,
                         "actual": {"head": head, "branch": branch}})
    if snapshot.get("protected_git_status") != git_status:
        failures.append({"reason": "protected_git_status_changed"})

    def keyed(rows, label):
        output = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not isinstance(row.get("category"), str):
                failures.append({"reason": "malformed_inventory_row", "inventory": label})
                continue
            key = (row["category"], row["path"])
            if key in output:
                failures.append({"reason": "duplicate_inventory_row", "inventory": label,
                                 "category": key[0], "path": key[1]})
            output[key] = row
        return output

    original = keyed(snapshot.get("files", []), "snapshot")
    current = keyed(current_rows, "current")
    for category, path in sorted(original.keys() | current.keys()):
        key = (category, path)
        if key not in current:
            failures.append({"reason": "file_missing", "category": category, "path": path})
        elif key not in original:
            failures.append({"reason": "file_added", "category": category, "path": path})
        else:
            before, after = original[key], current[key]
            if before.get("size_bytes") != after.get("size_bytes") or before.get("sha256") != after.get("sha256"):
                failures.append({"reason": "file_changed", "category": category, "path": path,
                                 "before_sha256": before.get("sha256"), "after_sha256": after.get("sha256")})
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    rows = inventory_rows(repo, args.engine_root)
    failures = compare(snapshot, rows, git(repo, "rev-parse", "HEAD"),
                       git(repo, "branch", "--show-current"), protected_git_status(repo))
    receipt = {
        "schema": SCHEMA_VERSION, "receipt_type": "source_immutability",
        "status": "PASS_SOURCE_IMMUTABILITY" if not failures else "FAIL_SOURCE_IMMUTABILITY",
        "runtime_validation": False, "created_utc": datetime.now(UTC).isoformat(),
        "run_id": snapshot.get("run_id"), "snapshot_sha256": sha256(args.snapshot),
        "baseline_file_rows": len(snapshot.get("files", [])), "current_file_rows": len(rows),
        "failures": failures,
    }
    write_json_new(args.out, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out), "failure_count": len(failures)}))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
