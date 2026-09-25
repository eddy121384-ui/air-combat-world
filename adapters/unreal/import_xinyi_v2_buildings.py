"""Import the 25 validated Full-Xinyi GLBs into an isolated UE5.8 asset path.

This is the asset-import stage only. It does not spawn actors or modify geometry.

Run inside UnrealEditor-Cmd with:
  ACW_XINYI_V2_CONTRACT=<absolute xinyi_unreal_v2_contract.json>
  ACW_XINYI_V2_BUILDING_DIR=<absolute directory containing 25 GLBs>
  ACW_XINYI_V2_IMPORT_REPORT=<absolute report path, optional>

The script:
- verifies every GLB SHA-256 against the offline contract before import;
- imports each tile into its own deterministic /Game/XinyiV2/Buildings/<tile> path;
- refuses to import over a non-empty destination;
- strips importer-default Nanite from every StaticMesh for the mobile/SM5 baseline;
- saves assets;
- records per-tile asset counts and a deterministic asset-path inventory hash.

No building placement/Z work happens here. That is the next stage after import
granularity and names are observed in the actual UE5.8 importer.
"""
import hashlib
import json
import os
import re
import time

import unreal

CONTRACT_PATH = os.environ.get("ACW_XINYI_V2_CONTRACT", "")
BUILDING_DIR = os.environ.get("ACW_XINYI_V2_BUILDING_DIR", "")
REPORT_PATH = os.environ.get("ACW_XINYI_V2_IMPORT_REPORT", "")
ROOT = "/Game/XinyiV2/Buildings"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def tile_asset_key(tile):
    # Git tile keys contain +/- signs. Use a conservative package-safe spelling.
    def repl(match):
        sign, digits = match.group(1), match.group(2)
        return ("p" if sign == "+" else "m") + digits
    parts = tile.split("_")
    return "_".join(repl(re.match(r"([+-])(\d+)$", p)) for p in parts)


def try_interchange(src, dest_dir):
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    source_data = unreal.InterchangeManager.create_source_data(src)
    params = unreal.ImportAssetParameters()
    return mgr.import_asset(dest_dir, source_data, params)


def try_asset_tools(src, dest_dir):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    task = unreal.AssetImportTask()
    task.filename = src
    task.destination_path = dest_dir
    task.automated = True
    task.save = True
    tools.import_asset_tasks([task])
    return [str(a) for a in task.imported_object_paths or []]


def static_mesh_paths(dest_dir):
    lib = unreal.EditorAssetLibrary
    out = []
    for ap in lib.list_assets(dest_dir, recursive=True):
        try:
            obj = lib.load_asset(ap)
        except Exception:  # noqa: BLE001
            continue
        if obj is not None and obj.get_class().get_name() == "StaticMesh":
            out.append(str(ap))
    return sorted(out)


def disable_nanite(dest_dir):
    lib = unreal.EditorAssetLibrary
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    fixed = 0
    failed = []
    for ap in static_mesh_paths(dest_dir):
        try:
            obj = lib.load_asset(ap)
            ns = obj.get_editor_property("nanite_settings")
            if ns.get_editor_property("enabled"):
                ns.set_editor_property("enabled", False)
                obj.set_editor_property("nanite_settings", ns)
                sub.set_nanite_settings(obj, ns, True)
                if not lib.save_asset(ap):
                    failed.append("%s: save declined" % ap)
                    continue
                fixed += 1
        except Exception as exc:  # noqa: BLE001
            failed.append("%s: %r" % (ap, exc))
    return fixed, failed


def inventory_hash(paths):
    return hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()


def main():
    if not CONTRACT_PATH or not os.path.isfile(CONTRACT_PATH):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT is not a valid file")
    if not BUILDING_DIR or not os.path.isdir(BUILDING_DIR):
        raise RuntimeError("ACW_XINYI_V2_BUILDING_DIR is not a valid directory")

    contract = json.loads(open(CONTRACT_PATH, "r", encoding="utf-8").read())
    if contract.get("status") != "PASS_CONTRACT":
        raise RuntimeError("offline Unreal contract is not PASS_CONTRACT")
    rows = contract.get("tiles") or []
    if len(rows) != 25:
        raise RuntimeError("offline contract does not contain 25 building tiles")

    lib = unreal.EditorAssetLibrary
    existing = lib.list_assets(ROOT, recursive=True)
    if existing:
        raise RuntimeError(
            "refusing to import over non-empty %s (%d assets); use a clean isolated path"
            % (ROOT, len(existing))
        )

    started = time.perf_counter()
    per_tile = []
    failures = []
    total_meshes = 0
    expected_total_nodes = sum(int(row["building_nodes"]) for row in rows)

    for row in rows:
        tile = row["tile"]
        glb = os.path.join(BUILDING_DIR, row["building_glb"])
        if not os.path.isfile(glb):
            failures.append({"tile": tile, "reason": "missing_glb", "path": glb})
            continue
        actual_sha = sha256_file(glb)
        if actual_sha != row["sha256"]:
            failures.append({
                "tile": tile,
                "reason": "sha256_mismatch",
                "expected": row["sha256"],
                "actual": actual_sha,
            })
            continue

        key = tile_asset_key(tile)
        dest = ROOT + "/" + key
        before = set(lib.list_assets(dest, recursive=True))
        if before:
            failures.append({"tile": tile, "reason": "destination_not_empty", "dest": dest})
            continue

        t0 = time.perf_counter()
        route = None
        try:
            result = try_interchange(glb, dest)
            route = "interchange"
            print("XINYI_V2_IMPORT_OK %s interchange %s" % (tile, result))
        except Exception as exc:  # noqa: BLE001
            print("XINYI_V2_IMPORT_NOTE %s interchange failed %r" % (tile, exc))
            try:
                result = try_asset_tools(glb, dest)
                route = "assettools"
                print("XINYI_V2_IMPORT_OK %s assettools %s" % (tile, result))
            except Exception as exc2:  # noqa: BLE001
                failures.append({
                    "tile": tile,
                    "reason": "import_failed",
                    "interchange_error": repr(exc),
                    "assettools_error": repr(exc2),
                })
                continue

        fixed, nanite_failures = disable_nanite(dest)
        if nanite_failures:
            failures.append({
                "tile": tile,
                "reason": "nanite_disable_failed",
                "failures": nanite_failures,
            })
            continue

        saved = lib.save_directory(dest, recursive=True)
        paths = static_mesh_paths(dest)
        total_meshes += len(paths)
        per_tile.append({
            "tile": tile,
            "dest": dest,
            "route": route,
            "expected_source_nodes": int(row["building_nodes"]),
            "expected_source_triangles": int(row["triangles"]),
            "static_mesh_assets": len(paths),
            "asset_count_matches_source_nodes": len(paths) == int(row["building_nodes"]),
            "source_node_delta": len(paths) - int(row["building_nodes"]),
            "asset_path_sha256": inventory_hash(paths),
            "asset_paths": paths,
            "nanite_disabled_now": fixed,
            "save_directory_result": bool(saved),
            "import_seconds": time.perf_counter() - t0,
        })

    report = {
        "gate": "XinyiV2 UE5.8 building asset import",
        "status": "PASS_ASSET_IMPORT" if not failures and len(per_tile) == 25 else "FAIL_ASSET_IMPORT",
        "root": ROOT,
        "tile_count": len(per_tile),
        "static_mesh_asset_count": total_meshes,
        "expected_source_node_count": expected_total_nodes,
        "asset_count_matches_source_nodes": total_meshes == expected_total_nodes,
        "source_node_delta": total_meshes - expected_total_nodes,
        "elapsed_seconds": time.perf_counter() - started,
        "per_tile": per_tile,
        "failures": failures,
        "next_gate": (
            "Fresh-process persistence + imported-bounds frame measurement; then choose actor/scene placement strategy and Landscape import."
        ),
    }

    if REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")

    print("XINYI_V2_BUILDING_IMPORT_JSON " + json.dumps(report, separators=(",", ":")))

    if report["status"] != "PASS_ASSET_IMPORT":
        raise RuntimeError("XinyiV2 building asset import failed")


main()
