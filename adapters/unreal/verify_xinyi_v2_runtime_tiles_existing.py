"""Verify already-imported XinyiV2 runtime tile assets without reimporting them.

This is a resume-only gate for interrupted local runs. It consumes the same
offline contract as the importer, but inspects the 25 persisted StaticMesh assets
already under /Game/XinyiV2/RuntimeBuildings.

No source GLB import occurs here.
"""
import json
import math
import os
import re
import time

import unreal

CONTRACT_PATH = os.environ.get("ACW_XINYI_V2_CONTRACT", "")
REPORT_PATH = os.environ.get("ACW_XINYI_V2_RUNTIME_IMPORT_REPORT", "")
ROOT = "/Game/XinyiV2/RuntimeBuildings"
EXTENT_TOLERANCE_CM = 2.0


def tile_key(tile):
    def repl(match):
        sign, digits = match.group(1), match.group(2)
        return ("p" if sign == "+" else "m") + digits
    return "_".join(repl(re.match(r"([+-])(\d+)$", p)) for p in tile.split("_"))


def static_mesh_paths(dest):
    lib = unreal.EditorAssetLibrary
    out = []
    for path in lib.list_assets(dest, recursive=True):
        obj = lib.load_asset(path)
        if obj is not None and obj.get_class().get_name() == "StaticMesh":
            out.append(str(path))
    return sorted(out)


def mesh_bounds(path):
    obj = unreal.EditorAssetLibrary.load_asset(path)
    if obj is None or obj.get_class().get_name() != "StaticMesh":
        raise RuntimeError("not a StaticMesh: %s" % path)
    b = obj.get_bounds()
    return (
        [float(b.origin.x), float(b.origin.y), float(b.origin.z)],
        [float(b.box_extent.x), float(b.box_extent.y), float(b.box_extent.z)],
    )


def max_axis_error(a, b):
    return max(abs(float(a[i]) - float(b[i])) for i in range(3))


def main():
    if not CONTRACT_PATH or not os.path.isfile(CONTRACT_PATH):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT is not a valid file")

    contract = json.loads(open(CONTRACT_PATH, "r", encoding="utf-8").read())
    if contract.get("status") != "PASS_CONTRACT":
        raise RuntimeError("offline contract is not PASS_CONTRACT")

    rows = contract.get("tiles") or []
    runtime_meta = contract["outputs"].get("building_runtime_tiles") or {}
    if len(rows) != 25 or int(runtime_meta.get("count", 0)) != 25:
        raise RuntimeError("runtime contract does not contain exactly 25 tiles")

    started = time.perf_counter()
    reports = []
    failures = []
    lib = unreal.EditorAssetLibrary

    if not lib.does_directory_exist(ROOT):
        failures.append({"reason": "runtime_root_missing", "root": ROOT})

    for row in rows:
        tile = row["tile"]
        dest = ROOT + "/" + tile_key(tile)
        try:
            paths = static_mesh_paths(dest)
            if len(paths) != 1:
                raise RuntimeError(
                    "persisted runtime tile has %d StaticMesh assets, expected 1" % len(paths)
                )
            mesh_path = paths[0]
            obj = lib.load_asset(mesh_path)
            ns = obj.get_editor_property("nanite_settings")
            if ns.get_editor_property("enabled"):
                raise RuntimeError("persisted runtime tile has Nanite enabled")

            origin, extent = mesh_bounds(mesh_path)
            expected_extent = row["runtime_expected_ue_local_bounds_extent_cm"]
            extent_error = max_axis_error(extent, expected_extent)
            if not math.isfinite(extent_error) or extent_error > EXTENT_TOLERANCE_CM:
                raise RuntimeError(
                    "runtime tile extent mismatch %.6f cm > %.3f cm"
                    % (extent_error, EXTENT_TOLERANCE_CM)
                )

            reports.append({
                "tile": tile,
                "asset_path": mesh_path,
                "source_sha256": row["runtime_building_sha256"],
                "expected_triangles": int(row["runtime_triangles"]),
                "imported_bounds_origin_cm": origin,
                "imported_bounds_extent_cm": extent,
                "expected_local_bounds_origin_cm": row[
                    "runtime_expected_ue_local_bounds_origin_cm"
                ],
                "expected_local_bounds_extent_cm": expected_extent,
                "extent_max_axis_error_cm": extent_error,
                "tile_world_translation_cm": row["expected_ue_translation_cm"],
                "resume_existing_asset": True,
            })
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "tile": tile,
                "reason": "persisted_asset_validation_failed",
                "error": repr(exc),
            })

    status = (
        "PASS_RUNTIME_TILE_IMPORT"
        if not failures and len(reports) == 25
        else "FAIL_RUNTIME_TILE_IMPORT"
    )
    report = {
        "status": status,
        "root": ROOT,
        "tile_count": len(reports),
        "static_mesh_asset_count": len(reports),
        "expected_static_mesh_asset_count": 25,
        "elapsed_seconds": time.perf_counter() - started,
        "extent_tolerance_cm": EXTENT_TOLERANCE_CM,
        "resume_mode": True,
        "tiles": reports,
        "failures": failures,
    }

    if REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")

    print("XINYI_V2_RUNTIME_RESUME_JSON " + json.dumps(report, separators=(",", ":")))
    if status != "PASS_RUNTIME_TILE_IMPORT":
        raise RuntimeError("persisted XinyiV2 runtime tile validation failed")


main()
