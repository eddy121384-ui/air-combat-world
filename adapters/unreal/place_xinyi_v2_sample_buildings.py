"""Place a deterministic 50-building coordinate sample into the XinyiV2 level.

This is the first world-mutation building gate. It consumes only a
PASS_PLACEMENT_PLAN produced from exact imported UE5.8 StaticMesh bounds.

Selection is deterministic and spatially broad:
- group by the 25 validated 500 m tiles;
- per tile, select the shortest and tallest component by expected Z extent;
- expect exactly 50 distinct components.

No mesh asset is edited. Actors use identity rotation/scale and only the
prevalidated translation from the placement plan.

Reads:
  ACW_XINYI_V2_PLACEMENT_PLAN
  ACW_XINYI_V2_SAMPLE_REPORT
"""
import gzip
import json
import math
import os

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"
PREFIX = "XinyiSample_"

PLAN_PATH = os.environ.get("ACW_XINYI_V2_PLACEMENT_PLAN", "")
REPORT_PATH = os.environ.get("ACW_XINYI_V2_SAMPLE_REPORT", "")

LOCATION_TOLERANCE_CM = 0.1


def read_plan(path):
    header = None
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            obj = json.loads(line)
            if line_no == 1:
                header = obj.get("header")
            else:
                rows.append(obj)
    if not header or header.get("status") != "PASS_PLACEMENT_PLAN":
        raise RuntimeError("placement plan header is not PASS_PLACEMENT_PLAN")
    if len(rows) != int(header["planned_component_count"]):
        raise RuntimeError("placement plan row count mismatch")
    return header, rows


def label_for(row):
    a, p, r, s = row["identity"]
    return f"{PREFIX}{a}_p{p}_r{r}_s{s}"


def z_height(row):
    return float(row["expected_world_bounds_extent_cm"][2]) * 2.0


def finite3(v):
    return len(v) == 3 and all(math.isfinite(float(x)) for x in v)


def select_rows(rows):
    by_tile = {}
    for row in rows:
        by_tile.setdefault(row["tile"], []).append(row)
    if len(by_tile) != 25:
        raise RuntimeError("placement plan does not cover 25 tiles")

    selected = []
    for tile in sorted(by_tile):
        candidates = sorted(by_tile[tile], key=lambda r: (z_height(r), r["node_name"]))
        if len(candidates) < 2:
            raise RuntimeError("tile %s has fewer than two candidate buildings" % tile)
        low = candidates[0]
        high = sorted(
            candidates,
            key=lambda r: (-z_height(r), r["node_name"]),
        )[0]
        if low["identity"] == high["identity"]:
            raise RuntimeError("tile %s low/high sample collapsed to one component" % tile)
        selected.extend([low, high])

    labels = [label_for(row) for row in selected]
    if len(selected) != 50 or len(set(labels)) != 50:
        raise RuntimeError("expected 50 unique sample components")
    return selected


def current_labels():
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return [a.get_actor_label() for a in sub.get_all_level_actors()]


def main():
    if not PLAN_PATH or not os.path.isfile(PLAN_PATH):
        raise RuntimeError("ACW_XINYI_V2_PLACEMENT_PLAN is not a valid file")

    _header, rows = read_plan(PLAN_PATH)
    selected = select_rows(rows)

    unreal.EditorLevelLibrary.load_level(LEVEL)
    world_name = str(unreal.EditorLevelLibrary.get_editor_world())
    if "L_XinyiV2_Contract" not in world_name:
        raise RuntimeError("wrong current map: %s" % world_name)

    labels_before = current_labels()
    if TERRAIN_LABEL not in labels_before:
        raise RuntimeError("validated Landscape actor is missing before building sample")
    stale = [x for x in labels_before if x.startswith(PREFIX)]
    if stale:
        raise RuntimeError("refusing to duplicate existing sample actors: %d" % len(stale))

    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    lib = unreal.EditorAssetLibrary
    placed = []
    failures = []

    for row in selected:
        asset_path = row["asset_path"]
        mesh = lib.load_asset(asset_path)
        if mesh is None or mesh.get_class().get_name() != "StaticMesh":
            failures.append({"reason": "mesh_unavailable", "asset": asset_path})
            continue

        translation = [float(x) for x in row["actor_translation_cm"]]
        if not finite3(translation):
            failures.append({"reason": "translation_nonfinite", "asset": asset_path})
            continue

        actor = sub.spawn_actor_from_object(
            mesh,
            unreal.Vector(translation[0], translation[1], translation[2]),
        )
        if actor is None:
            failures.append({"reason": "spawn_failed", "asset": asset_path})
            continue

        label = label_for(row)
        actor.set_actor_label(label)
        actual = actor.get_actor_location()
        actual_location = [float(actual.x), float(actual.y), float(actual.z)]
        max_error = max(
            abs(actual_location[i] - translation[i])
            for i in range(3)
        )
        if max_error > LOCATION_TOLERANCE_CM:
            failures.append({
                "reason": "spawn_location_mismatch",
                "label": label,
                "expected_cm": translation,
                "actual_cm": actual_location,
                "max_axis_error_cm": max_error,
            })
            continue

        placed.append({
            "label": label,
            "tile": row["tile"],
            "role": "low" if row is selected[selected.index(row) // 2 * 2] else "high",
            "asset_path": asset_path,
            "translation_cm": translation,
            "expected_world_bounds_origin_cm": row["expected_world_bounds_origin_cm"],
            "expected_world_bounds_extent_cm": row["expected_world_bounds_extent_cm"],
            "height_cm": z_height(row),
        })

    if failures or len(placed) != 50:
        report = {
            "status": "FAIL_SAMPLE_PLACEMENT",
            "placed_count": len(placed),
            "failure_count": len(failures),
            "failures": failures,
        }
        if REPORT_PATH:
            os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
            with open(REPORT_PATH, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)
                fh.write("\n")
        raise RuntimeError("XinyiV2 sample placement failed: %s" % report)

    if not unreal.EditorLevelLibrary.save_current_level():
        raise RuntimeError("save_current_level returned false after sample placement")

    report = {
        "status": "PASS_SAMPLE_PLACED",
        "level": LEVEL,
        "sample_count": len(placed),
        "tile_count": len({row["tile"] for row in placed}),
        "selection": "shortest + tallest expected component per 500 m tile",
        "world_mutation": "50 StaticMeshActors only; source StaticMesh assets unchanged",
        "location_tolerance_cm": LOCATION_TOLERANCE_CM,
        "actors": placed,
        "next_gate": "fresh-process sample actor location + mesh-reference verification",
    }
    if REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    print("XINYI_V2_SAMPLE_PLACEMENT_JSON " + json.dumps(report, separators=(",", ":")))


main()
