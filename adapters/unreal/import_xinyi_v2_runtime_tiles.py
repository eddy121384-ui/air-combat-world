"""Import the 25 staged XinyiV2 runtime building tiles into UE5.8.

Each source GLB is already one tile-local mesh with surveyed building ground-Z
placement baked as a downstream transform. The immutable validated source GLBs
remain unchanged.

This stage expects exactly 25 StaticMesh assets, not 11,130.
"""
import hashlib
import json
import math
import os
import re
import time

import unreal

CONTRACT_PATH = os.environ.get("ACW_XINYI_V2_CONTRACT", "")
CONTRACT_ROOT = os.environ.get("ACW_XINYI_V2_CONTRACT_ROOT", "")
REPORT_PATH = os.environ.get("ACW_XINYI_V2_RUNTIME_IMPORT_REPORT", "")
ROOT = "/Game/XinyiV2/RuntimeBuildings"
EXTENT_TOLERANCE_CM = 2.0


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


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


def disable_nanite(path):
    lib = unreal.EditorAssetLibrary
    obj = lib.load_asset(path)
    ns = obj.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        obj.set_editor_property("nanite_settings", ns)
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        sub.set_nanite_settings(obj, ns, True)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save StaticMesh after Nanite policy: %s" % path)


def import_one(src, dest):
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    source = unreal.InterchangeManager.create_source_data(src)
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    ok = mgr.import_asset(dest, source, params)
    if not ok:
        raise RuntimeError("Interchange import_asset returned false: %s" % src)


def main():
    if not CONTRACT_PATH or not os.path.isfile(CONTRACT_PATH):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT is not a valid file")
    if not CONTRACT_ROOT or not os.path.isdir(CONTRACT_ROOT):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT_ROOT is not a valid directory")

    contract = json.loads(open(CONTRACT_PATH, "r", encoding="utf-8").read())
    if contract.get("status") != "PASS_CONTRACT":
        raise RuntimeError("offline contract is not PASS_CONTRACT")
    rows = contract.get("tiles") or []
    runtime_meta = contract["outputs"].get("building_runtime_tiles") or {}
    if len(rows) != 25 or int(runtime_meta.get("count", 0)) != 25:
        raise RuntimeError("runtime contract does not contain exactly 25 tiles")

    lib = unreal.EditorAssetLibrary
    if lib.does_directory_exist(ROOT):
        if not lib.delete_directory(ROOT):
            raise RuntimeError("failed to clean previous isolated runtime building root")
    if lib.list_assets(ROOT, recursive=True):
        raise RuntimeError("runtime building root is not empty after cleanup")

    started = time.perf_counter()
    reports = []
    failures = []

    for row in rows:
        tile = row["tile"]
        src = os.path.join(
            CONTRACT_ROOT,
            runtime_meta["directory"],
            row["runtime_building_glb"],
        )
        if not os.path.isfile(src):
            failures.append({"tile": tile, "reason": "runtime_glb_missing", "path": src})
            continue
        actual_sha = sha256_file(src)
        if actual_sha != row["runtime_building_sha256"]:
            failures.append({
                "tile": tile,
                "reason": "runtime_glb_sha_mismatch",
                "expected": row["runtime_building_sha256"],
                "actual": actual_sha,
            })
            continue

        dest = ROOT + "/" + tile_key(tile)
        t0 = time.perf_counter()
        try:
            import_one(src, dest)
            paths = static_mesh_paths(dest)
            if len(paths) != 1:
                raise RuntimeError(
                    "runtime tile produced %d StaticMesh assets, expected 1" % len(paths)
                )
            mesh_path = paths[0]
            disable_nanite(mesh_path)
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
                "source_sha256": actual_sha,
                "expected_triangles": int(row["runtime_triangles"]),
                "imported_bounds_origin_cm": origin,
                "imported_bounds_extent_cm": extent,
                "expected_local_bounds_origin_cm": row[
                    "runtime_expected_ue_local_bounds_origin_cm"
                ],
                "expected_local_bounds_extent_cm": expected_extent,
                "extent_max_axis_error_cm": extent_error,
                "tile_world_translation_cm": row["expected_ue_translation_cm"],
                "import_seconds": time.perf_counter() - t0,
            })
        except Exception as exc:  # noqa: BLE001
            failures.append({"tile": tile, "reason": "import_failed", "error": repr(exc)})

    status = "PASS_RUNTIME_TILE_IMPORT" if not failures and len(reports) == 25 else "FAIL_RUNTIME_TILE_IMPORT"
    report = {
        "status": status,
        "root": ROOT,
        "tile_count": len(reports),
        "static_mesh_asset_count": len(reports),
        "expected_static_mesh_asset_count": 25,
        "elapsed_seconds": time.perf_counter() - started,
        "extent_tolerance_cm": EXTENT_TOLERANCE_CM,
        "tiles": reports,
        "failures": failures,
    }
    if REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    print("XINYI_V2_RUNTIME_IMPORT_JSON " + json.dumps(report, separators=(",", ":")))
    if status != "PASS_RUNTIME_TILE_IMPORT":
        raise RuntimeError("XinyiV2 runtime tile import failed")


main()
