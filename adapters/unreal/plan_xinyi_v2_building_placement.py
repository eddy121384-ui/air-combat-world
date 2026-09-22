"""Build a fail-closed, zero-world-mutation placement plan from imported UE5.8 meshes.

This stage intentionally does NOT spawn building actors. It joins:
- the offline per-component expected UE world-bounds contract derived from the
  validated GLBs + surveyed WFS ground elevations; and
- actual StaticMesh asset bounds produced by UE5.8 Interchange.

Only when every component maps uniquely and the imported extents match the
validated expected extents does it emit a placement translation:

    actor_translation = expected_world_bounds_origin - imported_asset_bounds_origin

This makes placement independent of whether Interchange retained tile-local
coordinates, baked node transforms, or recentered mesh assets.

Reads:
  ACW_XINYI_V2_CONTRACT
  ACW_XINYI_V2_CONTRACT_ROOT
  ACW_XINYI_V2_IMPORT_REPORT
  ACW_XINYI_V2_PLACEMENT_SUMMARY
  ACW_XINYI_V2_PLACEMENT_PLAN
"""
import gzip
import json
import math
import os
import re
import statistics

import unreal

CONTRACT_PATH = os.environ.get("ACW_XINYI_V2_CONTRACT", "")
CONTRACT_ROOT = os.environ.get("ACW_XINYI_V2_CONTRACT_ROOT", "")
IMPORT_REPORT_PATH = os.environ.get("ACW_XINYI_V2_IMPORT_REPORT", "")
SUMMARY_PATH = os.environ.get("ACW_XINYI_V2_PLACEMENT_SUMMARY", "")
PLAN_PATH = os.environ.get("ACW_XINYI_V2_PLACEMENT_PLAN", "")

EXTENT_TOLERANCE_CM = 2.0
IDENTITY_RE = re.compile(
    r"tp_building_height[._](\d+)_p(\d+)_r(\d+)_s(\d+)",
    re.IGNORECASE,
)


def component_identity(text):
    m = IDENTITY_RE.search(str(text))
    if not m:
        return None
    return tuple(int(m.group(i)) for i in range(1, 5))


def read_expected(path):
    header = None
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            obj = json.loads(line)
            if line_no == 1:
                header = obj.get("header")
                if not header:
                    raise RuntimeError("placement manifest first row lacks header")
                continue
            rows.append(obj)
    return header, rows


def mesh_bounds(asset_path):
    obj = unreal.EditorAssetLibrary.load_asset(asset_path)
    if obj is None or obj.get_class().get_name() != "StaticMesh":
        raise RuntimeError("not a StaticMesh: %s" % asset_path)
    b = obj.get_extended_bounds()
    origin = [float(b.origin.x), float(b.origin.y), float(b.origin.z)]
    extent = [float(b.box_extent.x), float(b.box_extent.y), float(b.box_extent.z)]
    return obj, origin, extent


def vsub(a, b):
    return [float(a[i]) - float(b[i]) for i in range(3)]


def max_axis_error(a, b):
    return max(abs(float(a[i]) - float(b[i])) for i in range(3))


def finite3(v):
    return len(v) == 3 and all(math.isfinite(float(x)) for x in v)


def main():
    for name, path in (
        ("ACW_XINYI_V2_CONTRACT", CONTRACT_PATH),
        ("ACW_XINYI_V2_IMPORT_REPORT", IMPORT_REPORT_PATH),
    ):
        if not path or not os.path.isfile(path):
            raise RuntimeError("%s is not a valid file" % name)
    if not CONTRACT_ROOT or not os.path.isdir(CONTRACT_ROOT):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT_ROOT is not a valid directory")

    contract = json.loads(open(CONTRACT_PATH, "r", encoding="utf-8").read())
    imported = json.loads(open(IMPORT_REPORT_PATH, "r", encoding="utf-8").read())
    if contract.get("status") != "PASS_CONTRACT":
        raise RuntimeError("offline contract is not PASS_CONTRACT")
    if imported.get("status") != "PASS_ASSET_IMPORT":
        raise RuntimeError("asset import is not PASS_ASSET_IMPORT")

    placement_meta = contract["outputs"].get("building_component_placement")
    if not placement_meta:
        raise RuntimeError("contract predates building component placement manifest")
    expected_path = os.path.join(CONTRACT_ROOT, placement_meta["path"])
    if not os.path.isfile(expected_path):
        raise RuntimeError("component placement manifest missing: %s" % expected_path)

    header, expected_rows = read_expected(expected_path)
    expected_count = int(placement_meta["count"])
    if len(expected_rows) != expected_count or int(header["count"]) != expected_count:
        raise RuntimeError("component placement manifest count mismatch")

    expected_by_id = {}
    failures = []
    for row in expected_rows:
        ident = component_identity(row["node_name"])
        if ident is None:
            failures.append({"reason": "expected_identity_unparseable", "node": row["node_name"]})
            continue
        if ident in expected_by_id:
            failures.append({"reason": "expected_identity_collision", "identity": list(ident)})
            continue
        expected_by_id[ident] = row

    actual_assets = []
    for tile in imported["per_tile"]:
        for asset_path in tile["asset_paths"]:
            actual_assets.append({"tile": tile["tile"], "asset_path": str(asset_path)})

    if len(actual_assets) != expected_count:
        failures.append({
            "reason": "imported_asset_count_does_not_match_component_contract",
            "expected": expected_count,
            "actual": len(actual_assets),
        })

    matched_expected = set()
    plan_rows = []
    extent_errors = []
    translations = []

    for actual in actual_assets:
        asset_path = actual["asset_path"]
        ident = component_identity(asset_path)
        if ident is None:
            failures.append({
                "reason": "actual_identity_unparseable",
                "asset": asset_path,
            })
            continue
        expected = expected_by_id.get(ident)
        if expected is None:
            failures.append({
                "reason": "actual_identity_missing_from_expected",
                "asset": asset_path,
                "identity": list(ident),
            })
            continue
        if ident in matched_expected:
            failures.append({
                "reason": "duplicate_actual_identity",
                "asset": asset_path,
                "identity": list(ident),
            })
            continue

        try:
            _, actual_origin, actual_extent = mesh_bounds(asset_path)
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "reason": "asset_bounds_unreadable",
                "asset": asset_path,
                "error": repr(exc),
            })
            continue

        expected_origin = expected["expected_ue_bounds_origin_cm"]
        expected_extent = expected["expected_ue_bounds_extent_cm"]
        if not finite3(actual_origin) or not finite3(actual_extent):
            failures.append({"reason": "actual_bounds_nonfinite", "asset": asset_path})
            continue

        extent_error = max_axis_error(actual_extent, expected_extent)
        if extent_error > EXTENT_TOLERANCE_CM:
            failures.append({
                "reason": "imported_extent_changed",
                "asset": asset_path,
                "node": expected["node_name"],
                "max_axis_error_cm": extent_error,
                "tolerance_cm": EXTENT_TOLERANCE_CM,
                "actual_extent_cm": actual_extent,
                "expected_extent_cm": expected_extent,
            })
            continue

        translation = vsub(expected_origin, actual_origin)
        if not finite3(translation):
            failures.append({"reason": "translation_nonfinite", "asset": asset_path})
            continue

        matched_expected.add(ident)
        extent_errors.append(extent_error)
        translations.append(translation)
        plan_rows.append({
            "identity": list(ident),
            "tile": expected["tile"],
            "node_name": expected["node_name"],
            "building_id": expected["building_id"],
            "asset_path": asset_path,
            "surveyed_ground_m": expected["surveyed_ground_m"],
            "imported_bounds_origin_cm": actual_origin,
            "imported_bounds_extent_cm": actual_extent,
            "expected_world_bounds_origin_cm": expected_origin,
            "expected_world_bounds_extent_cm": expected_extent,
            "actor_translation_cm": translation,
            "extent_max_axis_error_cm": extent_error,
        })

    missing_expected = sorted(set(expected_by_id) - matched_expected)
    if missing_expected:
        failures.append({
            "reason": "expected_components_unmatched",
            "count": len(missing_expected),
            "first": [list(x) for x in missing_expected[:20]],
        })

    pass_gate = not failures and len(plan_rows) == expected_count
    max_extent_error = max(extent_errors, default=0.0)

    summary = {
        "gate": "XinyiV2 zero-mutation building placement preflight",
        "status": "PASS_PLACEMENT_PLAN" if pass_gate else "FAIL_PLACEMENT_PLAN",
        "expected_component_count": expected_count,
        "imported_static_mesh_count": len(actual_assets),
        "planned_component_count": len(plan_rows),
        "extent_tolerance_cm": EXTENT_TOLERANCE_CM,
        "max_extent_axis_error_cm": max_extent_error,
        "translation_abs_cm": {
            "max_x": max((abs(v[0]) for v in translations), default=0.0),
            "max_y": max((abs(v[1]) for v in translations), default=0.0),
            "max_z": max((abs(v[2]) for v in translations), default=0.0),
            "median_z": statistics.median((v[2] for v in translations)) if translations else 0.0,
        },
        "failures": failures[:200],
        "failure_count": len(failures),
        "world_mutation": False,
        "placement_rule": (
            "after extent validation, translation = expected UE world-bounds origin "
            "- imported StaticMesh bounds origin"
        ),
        "next_gate": (
            "Choose runtime actor/merge/HLOD granularity using observed import asset count; "
            "the placement coordinates no longer depend on importer frame behavior."
        ),
    }

    if SUMMARY_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(SUMMARY_PATH)), exist_ok=True)
        with open(SUMMARY_PATH, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
            fh.write("\n")

    if PLAN_PATH and pass_gate:
        os.makedirs(os.path.dirname(os.path.abspath(PLAN_PATH)), exist_ok=True)
        lines = [json.dumps({"header": summary}, separators=(",", ":"), allow_nan=False)]
        lines.extend(
            json.dumps(row, separators=(",", ":"), allow_nan=False)
            for row in plan_rows
        )
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        packed = bytearray(gzip.compress(payload, compresslevel=9, mtime=0))
        if len(packed) < 10:
            raise RuntimeError("unexpectedly short gzip placement plan")
        packed[9] = 255
        with open(PLAN_PATH, "wb") as fh:
            fh.write(packed)

    print("XINYI_V2_PLACEMENT_PLAN_JSON " + json.dumps(summary, separators=(",", ":")))
    if not pass_gate:
        raise RuntimeError("XinyiV2 building placement preflight failed")


main()
