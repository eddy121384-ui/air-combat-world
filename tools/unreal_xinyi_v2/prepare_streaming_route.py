"""Derive an observation route from the accepted offline contract, without Unreal."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from host_gate_common import sha256, write_json_new

EXPECTED_SOURCE = "c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d"
EXPECTED_MANIFEST = "bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15"
PLAN_SCHEMA = "xinyi-host-route/v1"


def finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"nonfinite/non-numeric coordinate: {value!r}")
    return float(value)


def make_plan(contract: dict, definitions: dict, contract_hash: str, definitions_hash: str) -> dict:
    if definitions.get("world") != "/Game/XinyiV2/L_XinyiV2_Contract_WP":
        raise ValueError("runtime map changed")
    if contract.get("status") != "PASS_CONTRACT":
        raise ValueError("offline contract has not passed")
    upstream = contract["upstream"]
    if (upstream.get("building_source_sha256") != EXPECTED_SOURCE
            or upstream.get("building_manifest_sha256") != EXPECTED_MANIFEST):
        raise ValueError("upstream building truth changed")
    landscape = contract["landscape"]
    size = finite_number(landscape["component_size_m"])
    if landscape["components"] != [5, 5] or size != 500.0:
        raise ValueError("landscape grid is not the accepted 5x5 x 500 m contract")
    if contract["coordinate_contract"]["unreal_mapping"] != (
            "UE X = east*100 cm; UE Y = -north*100 cm; UE Z = up*100 cm"):
        raise ValueError("ENU-to-UE mapping changed")
    if contract["building_placement"]["runtime_tile_count"] != 25:
        raise ValueError("runtime building tile count changed")
    rows = contract["tiles"]
    if len(rows) != 25 or len({row["tile"] for row in rows}) != 25:
        raise ValueError("missing/duplicate tile identities")
    by_origin = {}
    for row in rows:
        east, north = map(finite_number, row["origin_enu_m"])
        key = (east, north)
        if key in by_origin or not isinstance(row["tile"], str) or not row["tile"]:
            raise ValueError("duplicate origin or invalid tile identity")
        translation = list(map(finite_number, row["expected_ue_translation_cm"]))
        if len(translation) != 3 or any(abs(a - b) > 0.01 for a, b in zip(translation, (east * 100, -north * 100, 0))):
            raise ValueError(f"tile translation mismatch: {row['tile']}")
        if not re.fullmatch(r"[0-9a-f]{64}", row["runtime_building_sha256"]):
            raise ValueError(f"missing runtime building hash: {row['tile']}")
        by_origin[key] = row
    xs = sorted({x for x, _ in by_origin})
    ys = sorted({y for _, y in by_origin})
    if len(xs) != 5 or len(ys) != 5 or any(
            abs(axis[i + 1] - axis[i] - size) > 1e-7
            for axis in (xs, ys) for i in range(4)):
        raise ValueError("tile origins do not form a 500 m grid")
    if set(by_origin) != {(x, y) for x in xs for y in ys}:
        raise ValueError("tile grid has gaps")
    extent = contract["coordinate_contract"]["extent_enu_m"]
    bounds = (xs[0], xs[-1] + size, ys[0], ys[-1] + size)
    if any(abs(finite_number(extent[name]) - actual) > 1e-7 for name, actual in zip(
            ("min_east_m", "max_east_m", "min_north_m", "max_north_m"), bounds)):
        raise ValueError("tile grid and Landscape extent disagree")

    spec = definitions["streaming"]["route_spec"]
    if spec.get("order") != "north-to-south-serpentine" or spec.get("tile_center_count") != 25:
        raise ValueError("route policy changed")
    clearance = finite_number(spec["control_clearance_m"])
    source_z = finite_number(spec["source_z_cm"])
    if clearance <= size or source_z < 0:
        raise ValueError("invalid control clearance or streaming-source height")
    mid_y = -((bounds[2] + bounds[3]) / 2) * 100
    points = [{"id": "outside-west-control", "kind": "control",
               "location_cm": [(bounds[0] - clearance) * 100, mid_y, source_z],
               "expected_tile_count": 0}]
    for row_index, north in enumerate(reversed(ys)):
        ordered_x = xs if row_index % 2 == 0 else list(reversed(xs))
        for column_index, east in enumerate(ordered_x):
            tile = by_origin[(east, north)]
            points.append({
                "id": f"tile-{row_index:02d}-{column_index:02d}", "kind": "tile",
                "expected_tile_id": tile["tile"],
                "expected_runtime_building_sha256": tile["runtime_building_sha256"],
                "location_cm": [(east + size / 2) * 100, -(north + size / 2) * 100, source_z],
            })
    points.append({"id": "outside-east-control", "kind": "control",
                   "location_cm": [(bounds[1] + clearance) * 100, mid_y, source_z],
                   "expected_tile_count": 0})
    return {
        "schema": PLAN_SCHEMA, "status": "PLAN_ONLY", "runtime_validation": False,
        "world": definitions["world"], "source_contract_sha256": contract_hash,
        "definitions_sha256": definitions_hash, "building_manifest_sha256": EXPECTED_MANIFEST,
        "control_clearance_m": clearance,
        "control_distance_is_candidate": True,
        "streaming": {
            "timeout_seconds": finite_number(definitions["streaming"]["timeout_seconds"]),
            "dwell_seconds": finite_number(definitions["streaming"]["dwell_seconds"]),
            "require_load_and_unload_per_tile": True, "route": points,
        },
        "note": "Control distance must be checked against the measured runtime loading range; zero loaded building tiles is required at both controls.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--definitions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    definitions = json.loads(args.definitions.read_text(encoding="utf-8"))
    plan = make_plan(contract, definitions, sha256(args.contract), sha256(args.definitions))
    write_json_new(args.out, plan)
    print(f"XINYI_ROUTE_PLAN_ONLY points={len(plan['streaming']['route'])} path={args.out}")


if __name__ == "__main__":
    main()
