"""Create a read-only, content-addressed inventory of the local XinyiV2 world."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from host_gate_common import SCHEMA_VERSION, file_rows, git, machine, new_run_id, write_json_new


def files(directory: Path, patterns: tuple[str, ...] = ("*",)) -> list[Path]:
    if not directory.exists():
        return []
    return [p for pattern in patterns for p in directory.rglob(pattern) if p.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    repo = args.repo.resolve()
    unreal = repo / "unreal"
    run_id = args.run_id or new_run_id(repo)
    run_root = (args.run_root or unreal / "Saved/XinyiHostGates" / run_id).resolve()
    groups = {
        "source_map": [unreal / "Content/XinyiV2/L_XinyiV2_Contract.umap"],
        "wp_map": [unreal / "Content/XinyiV2/L_XinyiV2_Contract_WP.umap"],
        "external_actors": files(unreal / "Content/__ExternalActors__/XinyiV2"),
        "external_objects": files(unreal / "Content/__ExternalObjects__/XinyiV2"),
        "building_assets": files(unreal / "Content/XinyiV2/RuntimeBuildings", ("*.uasset",)),
        "landscape_packages": files(unreal / "Content/XinyiV2", ("*Landscape*.uasset", "*Terrain*.uasset")),
        "plugin": files(unreal / "Plugins/XinyiLandscapeBridge"),
        "project_config": files(unreal / "Config", ("*.ini",)) + [unreal / "AirCombatWorld.uproject"],
        "engine_version": [args.engine_root / "Engine/Build/Build.version"],
    }
    rows = [row for name, paths in groups.items() for row in file_rows(repo, paths, name)]
    counts = {name: sum(row["category"] == name for row in rows) for name in groups}
    required = {"source_map": counts["source_map"] == 1, "wp_map": counts["wp_map"] == 1, "building_assets": counts["building_assets"] == 25, "engine_version": counts["engine_version"] == 1, "external_actor_packages": counts["external_actors"] > 0}
    receipt = {
        "schema": SCHEMA_VERSION, "receipt_type": "snapshot",
        "status": "PASS_SNAPSHOT" if all(required.values()) else "FAIL_SNAPSHOT",
        "runtime_validation": False, "created_utc": datetime.now(UTC).isoformat(), "run_id": run_id,
        "repository": {"head": git(repo, "rev-parse", "HEAD"), "branch": git(repo, "branch", "--show-current")},
        "machine": machine(), "counts": counts, "requirements": required, "files": rows,
        "mutation": {"source_files_written": 0, "receipt_created_exclusively": True},
    }
    write_json_new(run_root / "00-snapshot.json", receipt)
    print(json.dumps({"status": receipt["status"], "run_id": run_id, "receipt": str(run_root / "00-snapshot.json")}))
    if receipt["status"] != "PASS_SNAPSHOT":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
