"""Measure UE5.8 StaticMesh bounds after XinyiV2 GLB asset import.

This is deliberately a measurement stage, not a placement stage. The first
Unreal import must tell us whether Interchange baked glTF node translations into
StaticMesh geometry, kept the 500 m tile-local frame, or recentered meshes.

Reads:
  ACW_XINYI_V2_CONTRACT
  ACW_XINYI_V2_IMPORT_REPORT
  ACW_XINYI_V2_BOUNDS_REPORT (optional)

Run in a fresh UnrealEditor-Cmd process after import persistence has passed.
"""
import json
import math
import os
import statistics

import unreal

CONTRACT_PATH = os.environ.get("ACW_XINYI_V2_CONTRACT", "")
IMPORT_REPORT_PATH = os.environ.get("ACW_XINYI_V2_IMPORT_REPORT", "")
OUT_PATH = os.environ.get("ACW_XINYI_V2_BOUNDS_REPORT", "")

TILE_HALF_CM = 25000.0
CLASSIFY_MARGIN_CM = 10000.0


def xy(v):
    return [float(v.x), float(v.y)]


def xyz(v):
    return [float(v.x), float(v.y), float(v.z)]


def distance2(a, b):
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def mesh_bounds(asset_path):
    obj = unreal.EditorAssetLibrary.load_asset(asset_path)
    if obj is None or obj.get_class().get_name() != "StaticMesh":
        raise RuntimeError("not a StaticMesh: %s" % asset_path)
    b = obj.get_bounds()
    origin = xyz(b.origin)
    extent = xyz(b.box_extent)
    return {
        "asset": str(asset_path),
        "origin_cm": origin,
        "extent_cm": extent,
        "min_cm": [origin[i] - extent[i] for i in range(3)],
        "max_cm": [origin[i] + extent[i] for i in range(3)],
    }


def classify(median_xy, expected_translation_cm):
    local_center = [TILE_HALF_CM, -TILE_HALF_CM]
    world_center = [
        float(expected_translation_cm[0]) + TILE_HALF_CM,
        float(expected_translation_cm[1]) - TILE_HALF_CM,
    ]
    zero_center = [0.0, 0.0]
    distances = {
        "baked_world": distance2(median_xy, world_center),
        "tile_local": distance2(median_xy, local_center),
        "recentered": distance2(median_xy, zero_center),
    }
    ordered = sorted(distances.items(), key=lambda kv: kv[1])
    winner, best = ordered[0]
    second = ordered[1][1]
    classification = winner if second - best >= CLASSIFY_MARGIN_CM else "ambiguous"
    return classification, distances, {
        "world_center_cm": world_center,
        "tile_local_center_cm": local_center,
        "zero_center_cm": zero_center,
    }


def main():
    if not CONTRACT_PATH or not os.path.isfile(CONTRACT_PATH):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT is not a valid file")
    if not IMPORT_REPORT_PATH or not os.path.isfile(IMPORT_REPORT_PATH):
        raise RuntimeError("ACW_XINYI_V2_IMPORT_REPORT is not a valid file")

    contract = json.loads(open(CONTRACT_PATH, "r", encoding="utf-8").read())
    imported = json.loads(open(IMPORT_REPORT_PATH, "r", encoding="utf-8").read())
    if contract.get("status") != "PASS_CONTRACT":
        raise RuntimeError("offline contract is not PASS_CONTRACT")
    if imported.get("status") != "PASS_ASSET_IMPORT":
        raise RuntimeError("building import is not PASS_ASSET_IMPORT")

    contract_tiles = {row["tile"]: row for row in contract["tiles"]}
    failures = []
    rows = []
    votes = {"baked_world": 0, "tile_local": 0, "recentered": 0, "ambiguous": 0}

    for import_row in imported["per_tile"]:
        tile = import_row["tile"]
        expected = contract_tiles.get(tile)
        if expected is None:
            failures.append({"tile": tile, "reason": "tile_missing_from_contract"})
            continue

        measured = []
        for asset_path in import_row["asset_paths"]:
            try:
                measured.append(mesh_bounds(asset_path))
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "tile": tile,
                    "asset": asset_path,
                    "reason": "bounds_unreadable",
                    "error": repr(exc),
                })

        if not measured:
            failures.append({"tile": tile, "reason": "no_measurable_static_meshes"})
            continue

        origins_x = [m["origin_cm"][0] for m in measured]
        origins_y = [m["origin_cm"][1] for m in measured]
        median_xy = [statistics.median(origins_x), statistics.median(origins_y)]
        classification, distances, centers = classify(
            median_xy, expected["expected_ue_translation_cm"]
        )
        votes[classification] += 1

        agg_min = [min(m["min_cm"][i] for m in measured) for i in range(3)]
        agg_max = [max(m["max_cm"][i] for m in measured) for i in range(3)]

        rows.append({
            "tile": tile,
            "asset_count": len(measured),
            "expected_source_nodes": int(import_row["expected_source_nodes"]),
            "median_mesh_bounds_origin_xy_cm": median_xy,
            "aggregate_min_cm": agg_min,
            "aggregate_max_cm": agg_max,
            "classification": classification,
            "distance_to_centers_cm": distances,
            "candidate_centers_cm": centers,
        })

    informative = {
        k: v for k, v in votes.items() if k != "ambiguous" and v > 0
    }
    overall = "undetermined"
    if informative:
        ordered = sorted(informative.items(), key=lambda kv: (-kv[1], kv[0]))
        if len(ordered) == 1 or ordered[0][1] > ordered[1][1]:
            overall = ordered[0][0]
        else:
            overall = "mixed"

    result = {
        "gate": "XinyiV2 UE5.8 post-import StaticMesh frame measurement",
        "status": "PASS_MEASUREMENT" if not failures and len(rows) == 25 else "FAIL_MEASUREMENT",
        "tile_count": len(rows),
        "classification_votes": votes,
        "overall_transform_behavior": overall,
        "classification_margin_cm": CLASSIFY_MARGIN_CM,
        "tiles": rows,
        "failures": failures,
        "decision_rule": (
            "Do not write actor placement until this report establishes whether "
            "UE5.8 Interchange produced baked-world, tile-local, recentered, or mixed assets."
        ),
    }

    if OUT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")

    print("XINYI_V2_BOUNDS_JSON " + json.dumps(result, separators=(",", ":")))
    if result["status"] != "PASS_MEASUREMENT":
        raise RuntimeError("XinyiV2 imported-bounds measurement failed")


main()
