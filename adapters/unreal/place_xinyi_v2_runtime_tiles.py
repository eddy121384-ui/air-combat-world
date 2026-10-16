"""Place 25 imported XinyiV2 runtime building tiles over the validated Landscape."""
import json
import math
import os

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"
PREFIX = "XinyiRuntimeTile_"
IMPORT_REPORT = os.environ.get("ACW_XINYI_V2_RUNTIME_IMPORT_REPORT", "")
WORLD_REPORT = os.environ.get("ACW_XINYI_V2_WORLD_REPORT", "")
LOCATION_TOLERANCE_CM = 0.1


def finite3(v):
    return len(v) == 3 and all(math.isfinite(float(x)) for x in v)


def main():
    if not IMPORT_REPORT or not os.path.isfile(IMPORT_REPORT):
        raise RuntimeError("ACW_XINYI_V2_RUNTIME_IMPORT_REPORT is not a valid file")
    imported = json.loads(open(IMPORT_REPORT, "r", encoding="utf-8").read())
    if imported.get("status") != "PASS_RUNTIME_TILE_IMPORT":
        raise RuntimeError("runtime tile import report is not PASS_RUNTIME_TILE_IMPORT")

    unreal.EditorLevelLibrary.load_level(LEVEL)
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    lib = unreal.EditorAssetLibrary
    actors = list(sub.get_all_level_actors())
    labels = [a.get_actor_label() for a in actors]
    if TERRAIN_LABEL not in labels:
        raise RuntimeError("validated Landscape actor missing before runtime tile placement")

    for actor in actors:
        if actor.get_actor_label().startswith(PREFIX):
            sub.destroy_actor(actor)

    placed = []
    failures = []
    for row in imported["tiles"]:
        mesh = lib.load_asset(row["asset_path"])
        if mesh is None or mesh.get_class().get_name() != "StaticMesh":
            failures.append({"tile": row["tile"], "reason": "mesh_missing"})
            continue

        tile_world = [float(x) for x in row["tile_world_translation_cm"]]
        expected_origin = [float(x) for x in row["expected_local_bounds_origin_cm"]]
        actual_origin = [float(x) for x in row["imported_bounds_origin_cm"]]
        translation = [
            tile_world[i] + expected_origin[i] - actual_origin[i]
            for i in range(3)
        ]
        if not finite3(translation):
            failures.append({"tile": row["tile"], "reason": "translation_nonfinite"})
            continue

        actor = sub.spawn_actor_from_object(
            mesh,
            unreal.Vector(translation[0], translation[1], translation[2]),
        )
        if actor is None:
            failures.append({"tile": row["tile"], "reason": "spawn_failed"})
            continue

        label = PREFIX + row["tile"].replace("+", "p").replace("-", "m")
        actor.set_actor_label(label)
        loc = actor.get_actor_location()
        actual = [float(loc.x), float(loc.y), float(loc.z)]
        err = max(abs(actual[i] - translation[i]) for i in range(3))
        if err > LOCATION_TOLERANCE_CM:
            failures.append({
                "tile": row["tile"],
                "reason": "location_mismatch",
                "expected_cm": translation,
                "actual_cm": actual,
                "error_cm": err,
            })
            continue

        placed.append({
            "tile": row["tile"],
            "label": label,
            "asset_path": row["asset_path"],
            "translation_cm": translation,
        })

    status = "PASS_RUNTIME_WORLD" if not failures and len(placed) == 25 else "FAIL_RUNTIME_WORLD"
    if status == "PASS_RUNTIME_WORLD":
        if not unreal.EditorLevelLibrary.save_current_level():
            raise RuntimeError("save_current_level returned false")

    report = {
        "status": status,
        "level": LEVEL,
        "terrain_label": TERRAIN_LABEL,
        "building_tile_actor_count": len(placed),
        "actors": placed,
        "failures": failures,
    }
    if WORLD_REPORT:
        os.makedirs(os.path.dirname(os.path.abspath(WORLD_REPORT)), exist_ok=True)
        with open(WORLD_REPORT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    print("XINYI_V2_RUNTIME_WORLD_JSON " + json.dumps(report, separators=(",", ":")))
    if status != "PASS_RUNTIME_WORLD":
        raise RuntimeError("XinyiV2 runtime world placement failed")


main()
