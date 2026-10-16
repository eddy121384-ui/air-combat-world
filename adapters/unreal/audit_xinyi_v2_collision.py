"""Read-only collision baseline for the 25 persisted XinyiV2 runtime tile meshes."""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import unreal


SAVED = Path(unreal.Paths.project_saved_dir()) / "XinyiUnrealV2"
IMPORT_REPORT = Path(
    os.environ.get("ACW_XINYI_V2_RUNTIME_IMPORT_REPORT", SAVED / "ue_runtime_tile_import.json")
)
REPORT = Path(
    os.environ.get("ACW_XINYI_V2_COLLISION_REPORT", SAVED / "ue_collision_baseline.json")
)
SHAPES = (
    "sphere_elems",
    "box_elems",
    "sphyl_elems",
    "tapered_capsule_elems",
    "convex_elems",
)


def main() -> None:
    source = json.loads(IMPORT_REPORT.read_text(encoding="utf-8"))
    tiles = source.get("tiles", [])
    failures = []
    rows = []

    if source.get("status") != "PASS_RUNTIME_TILE_IMPORT" or len(tiles) != 25:
        failures.append({"reason": "runtime_import_receipt_invalid"})

    for tile in tiles:
        path = tile["asset_path"]
        mesh = unreal.load_asset(path)
        if mesh is None or not isinstance(mesh, unreal.StaticMesh):
            failures.append({"reason": "static_mesh_missing", "asset_path": path})
            continue

        setup = mesh.get_editor_property("body_setup")
        if setup is None:
            failures.append({"reason": "body_setup_missing", "asset_path": path})
            continue

        aggregate = setup.get_editor_property("agg_geom")
        shape_counts = {}
        for name in SHAPES:
            try:
                shape_counts[name] = len(aggregate.get_editor_property(name))
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    {
                        "reason": "shape_count_unavailable",
                        "asset_path": path,
                        "shape": name,
                        "error": repr(exc),
                    }
                )

        rows.append(
            {
                "tile": tile["tile"],
                "asset_path": path,
                "expected_triangles": tile["expected_triangles"],
                "collision_trace_flag": str(
                    setup.get_editor_property("collision_trace_flag")
                ),
                "simple_shape_counts": shape_counts,
                "simple_shape_count": sum(shape_counts.values()),
            }
        )

    rows.sort(key=lambda row: row["tile"])
    flags = Counter(row["collision_trace_flag"] for row in rows)
    report = {
        "status": "PASS_COLLISION_BASELINE" if not failures else "FAIL_COLLISION_BASELINE",
        "audit_is_read_only": True,
        "runtime_mesh_count": len(rows),
        "expected_runtime_mesh_count": 25,
        "expected_triangle_count": sum(row["expected_triangles"] for row in rows),
        "collision_trace_flag_counts": dict(sorted(flags.items())),
        "meshes_without_simple_shapes": sum(
            row["simple_shape_count"] == 0 for row in rows
        ),
        "simple_shape_count": sum(row["simple_shape_count"] for row in rows),
        "tiles": rows,
        "failures": failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("XINYI_V2_COLLISION_BASELINE_JSON " + json.dumps(report, separators=(",", ":")))
    if failures:
        raise RuntimeError("XinyiV2 collision baseline is incomplete")


main()
