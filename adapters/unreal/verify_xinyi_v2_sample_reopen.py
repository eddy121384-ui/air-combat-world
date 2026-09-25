"""Fresh-process verification for the deterministic 50-building XinyiV2 sample."""
import json
import math
import os

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"

SAMPLE_REPORT_PATH = os.environ.get("ACW_XINYI_V2_SAMPLE_REPORT", "")
REOPEN_REPORT_PATH = os.environ.get("ACW_XINYI_V2_SAMPLE_REOPEN_REPORT", "")
LOCATION_TOLERANCE_CM = 0.1


def close3(a, b, tol):
    return len(a) == 3 and len(b) == 3 and all(
        math.isfinite(float(a[i])) and abs(float(a[i]) - float(b[i])) <= tol
        for i in range(3)
    )


def actor_mesh_path(actor):
    try:
        comps = actor.get_components_by_class(unreal.StaticMeshComponent)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("cannot enumerate StaticMeshComponents: %r" % exc)
    if len(comps) != 1:
        raise RuntimeError("expected exactly one StaticMeshComponent, got %d" % len(comps))
    mesh = comps[0].get_editor_property("static_mesh")
    if mesh is None:
        raise RuntimeError("StaticMeshComponent has no static_mesh")
    return str(mesh.get_path_name())


def main():
    if not SAMPLE_REPORT_PATH or not os.path.isfile(SAMPLE_REPORT_PATH):
        raise RuntimeError("ACW_XINYI_V2_SAMPLE_REPORT is not a valid file")
    expected = json.loads(open(SAMPLE_REPORT_PATH, "r", encoding="utf-8").read())
    if expected.get("status") != "PASS_SAMPLE_PLACED":
        raise RuntimeError("sample placement report is not PASS_SAMPLE_PLACED")

    unreal.EditorLevelLibrary.load_level(LEVEL)
    world_name = str(unreal.EditorLevelLibrary.get_editor_world())
    if "L_XinyiV2_Contract" not in world_name:
        raise RuntimeError("fresh process loaded wrong map: %s" % world_name)

    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
    failures = []

    if TERRAIN_LABEL not in actors:
        failures.append({"reason": "terrain_missing_after_sample_reopen"})

    for row in expected["actors"]:
        label = row["label"]
        actor = actors.get(label)
        if actor is None:
            failures.append({"reason": "sample_actor_missing", "label": label})
            continue

        loc = actor.get_actor_location()
        actual_location = [float(loc.x), float(loc.y), float(loc.z)]
        if not close3(actual_location, row["translation_cm"], LOCATION_TOLERANCE_CM):
            failures.append({
                "reason": "sample_location_changed_after_reopen",
                "label": label,
                "expected_cm": row["translation_cm"],
                "actual_cm": actual_location,
            })

        try:
            actual_mesh = actor_mesh_path(actor)
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "reason": "sample_mesh_reference_unreadable",
                "label": label,
                "error": repr(exc),
            })
            continue

        expected_mesh = row["asset_path"]
        if actual_mesh != expected_mesh:
            failures.append({
                "reason": "sample_mesh_reference_changed",
                "label": label,
                "expected": expected_mesh,
                "actual": actual_mesh,
            })

    sample_labels = [x for x in actors if x.startswith("XinyiSample_")]
    if len(sample_labels) != int(expected["sample_count"]):
        failures.append({
            "reason": "sample_actor_count_changed_after_reopen",
            "expected": int(expected["sample_count"]),
            "actual": len(sample_labels),
        })

    report = {
        "status": "PASS_SAMPLE_FRESH_REOPEN" if not failures else "FAIL_SAMPLE_FRESH_REOPEN",
        "level": LEVEL,
        "expected_sample_count": int(expected["sample_count"]),
        "reopened_sample_count": len(sample_labels),
        "tile_count": int(expected["tile_count"]),
        "location_tolerance_cm": LOCATION_TOLERANCE_CM,
        "failure_count": len(failures),
        "failures": failures,
    }

    if REOPEN_REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REOPEN_REPORT_PATH)), exist_ok=True)
        with open(REOPEN_REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    print("XINYI_V2_SAMPLE_REOPEN_JSON " + json.dumps(report, separators=(",", ":")))
    if failures:
        raise RuntimeError("XinyiV2 sample fresh-reopen gate failed")


main()
