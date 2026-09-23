"""Fresh-process verification for XinyiV2 Landscape + 25 runtime building tiles."""
import json
import math
import os

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"
WORLD_REPORT = os.environ.get("ACW_XINYI_V2_WORLD_REPORT", "")
REOPEN_REPORT = os.environ.get("ACW_XINYI_V2_WORLD_REOPEN_REPORT", "")
TOLERANCE_CM = 0.1


def mesh_path(actor):
    comps = actor.get_components_by_class(unreal.StaticMeshComponent)
    if len(comps) != 1:
        raise RuntimeError("expected one StaticMeshComponent")
    mesh = comps[0].get_editor_property("static_mesh")
    return str(mesh.get_path_name()) if mesh else ""


def main():
    if not WORLD_REPORT or not os.path.isfile(WORLD_REPORT):
        raise RuntimeError("ACW_XINYI_V2_WORLD_REPORT is not a valid file")
    expected = json.loads(open(WORLD_REPORT, "r", encoding="utf-8").read())
    if expected.get("status") != "PASS_RUNTIME_WORLD":
        raise RuntimeError("runtime world report is not PASS_RUNTIME_WORLD")

    unreal.EditorLevelLibrary.load_level(LEVEL)
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
    failures = []

    if TERRAIN_LABEL not in actors:
        failures.append({"reason": "terrain_missing"})

    for row in expected["actors"]:
        actor = actors.get(row["label"])
        if actor is None:
            failures.append({"reason": "tile_actor_missing", "label": row["label"]})
            continue
        loc = actor.get_actor_location()
        actual = [float(loc.x), float(loc.y), float(loc.z)]
        want = [float(x) for x in row["translation_cm"]]
        if max(abs(actual[i] - want[i]) for i in range(3)) > TOLERANCE_CM:
            failures.append({
                "reason": "tile_location_changed",
                "label": row["label"],
                "expected_cm": want,
                "actual_cm": actual,
            })
        try:
            got_mesh = mesh_path(actor)
        except Exception as exc:  # noqa: BLE001
            failures.append({"reason": "mesh_reference_unreadable", "label": row["label"], "error": repr(exc)})
            continue
        if got_mesh != row["asset_path"]:
            failures.append({
                "reason": "mesh_reference_changed",
                "label": row["label"],
                "expected": row["asset_path"],
                "actual": got_mesh,
            })

    runtime_labels = [x for x in actors if x.startswith("XinyiRuntimeTile_")]
    if len(runtime_labels) != 25:
        failures.append({"reason": "runtime_tile_actor_count", "actual": len(runtime_labels), "expected": 25})

    report = {
        "status": "PASS_RUNTIME_WORLD_FRESH_REOPEN" if not failures else "FAIL_RUNTIME_WORLD_FRESH_REOPEN",
        "level": LEVEL,
        "runtime_tile_actor_count": len(runtime_labels),
        "terrain_present": TERRAIN_LABEL in actors,
        "failures": failures,
    }
    if REOPEN_REPORT:
        os.makedirs(os.path.dirname(os.path.abspath(REOPEN_REPORT)), exist_ok=True)
        with open(REOPEN_REPORT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    print("XINYI_V2_RUNTIME_WORLD_REOPEN_JSON " + json.dumps(report, separators=(",", ":")))
    if failures:
        raise RuntimeError("XinyiV2 runtime world fresh-reopen gate failed")


main()
