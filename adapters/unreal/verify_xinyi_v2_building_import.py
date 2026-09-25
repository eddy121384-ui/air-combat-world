"""Fresh-process persistence gate for imported XinyiV2 building assets.

Reads:
  ACW_XINYI_V2_IMPORT_REPORT=<report from import_xinyi_v2_buildings.py>

The import process must have fully exited before running this script in a new
UnrealEditor-Cmd process.
"""
import hashlib
import json
import os

import unreal

REPORT_PATH = os.environ.get("ACW_XINYI_V2_IMPORT_REPORT", "")
ROOT = "/Game/XinyiV2/Buildings"


def inventory_hash(paths):
    return hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()


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


def main():
    if not REPORT_PATH or not os.path.isfile(REPORT_PATH):
        raise RuntimeError("ACW_XINYI_V2_IMPORT_REPORT is not a valid file")
    old = json.loads(open(REPORT_PATH, "r", encoding="utf-8").read())
    if old.get("status") != "PASS_ASSET_IMPORT":
        raise RuntimeError("prior import report is not PASS_ASSET_IMPORT")

    lib = unreal.EditorAssetLibrary
    failures = []
    total = 0

    for row in old["per_tile"]:
        dest = row["dest"]
        paths = static_mesh_paths(dest)
        total += len(paths)
        if len(paths) != int(row["static_mesh_assets"]):
            failures.append({
                "tile": row["tile"],
                "reason": "static_mesh_count_changed_after_reopen",
                "before": row["static_mesh_assets"],
                "after": len(paths),
            })
        digest = inventory_hash(paths)
        if digest != row["asset_path_sha256"]:
            failures.append({
                "tile": row["tile"],
                "reason": "asset_inventory_hash_changed_after_reopen",
                "before": row["asset_path_sha256"],
                "after": digest,
            })

        for ap in paths:
            try:
                obj = lib.load_asset(ap)
                enabled = obj.get_editor_property("nanite_settings").get_editor_property("enabled")
                if enabled:
                    failures.append({
                        "tile": row["tile"],
                        "reason": "nanite_reenabled_after_reopen",
                        "asset": ap,
                    })
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "tile": row["tile"],
                    "reason": "nanite_state_unreadable",
                    "asset": ap,
                    "error": repr(exc),
                })

    result = {
        "status": "PASS_FRESH_REOPEN" if not failures else "FAIL_FRESH_REOPEN",
        "root": ROOT,
        "tile_count": len(old["per_tile"]),
        "static_mesh_asset_count": total,
        "failures": failures,
    }
    print("XINYI_V2_BUILDING_REOPEN_JSON " + json.dumps(result, separators=(",", ":")))
    if failures:
        raise RuntimeError("XinyiV2 fresh-process building asset gate failed")


main()
