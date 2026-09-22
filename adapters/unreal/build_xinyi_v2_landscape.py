"""Materialize the validated 631x631 MOI DTM contract as a real UE5.8 ALandscape.

Requires the editor-only XinyiLandscapeBridge plugin to be compiled and loaded.
The bridge only calls ALandscape::Import; all source/elevation mathematics remain
in the offline Python contract.

Reads:
  ACW_XINYI_V2_CONTRACT
  ACW_XINYI_V2_CONTRACT_ROOT  directory containing the RAW16 named by contract
  ACW_XINYI_V2_LANDSCAPE_REPORT (optional)
"""
import json
import os

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
LABEL = "Terrain_Xinyi_MOI2025"

CONTRACT_PATH = os.environ.get("ACW_XINYI_V2_CONTRACT", "")
CONTRACT_ROOT = os.environ.get("ACW_XINYI_V2_CONTRACT_ROOT", "")
REPORT_PATH = os.environ.get("ACW_XINYI_V2_LANDSCAPE_REPORT", "")


def write_report(report):
    if REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")


def current_world_name():
    try:
        return str(unreal.EditorLevelLibrary.get_editor_world())
    except Exception as exc:  # noqa: BLE001
        return "unknown (%r)" % exc


def main():
    if not CONTRACT_PATH or not os.path.isfile(CONTRACT_PATH):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT is not a valid file")
    if not CONTRACT_ROOT or not os.path.isdir(CONTRACT_ROOT):
        raise RuntimeError("ACW_XINYI_V2_CONTRACT_ROOT is not a valid directory")

    contract = json.loads(open(CONTRACT_PATH, "r", encoding="utf-8").read())
    if contract.get("status") != "PASS_CONTRACT":
        raise RuntimeError("offline contract is not PASS_CONTRACT")

    landscape = contract["landscape"]
    if landscape["heightmap_size"] != [631, 631]:
        raise RuntimeError("unexpected heightmap topology")
    if landscape["components"] != [5, 5]:
        raise RuntimeError("unexpected component topology")

    raw_name = contract["outputs"]["heightmap_r16"]["path"]
    raw_path = os.path.join(CONTRACT_ROOT, raw_name)
    if not os.path.isfile(raw_path):
        raise RuntimeError("RAW16 missing: %s" % raw_path)

    lib = unreal.EditorAssetLibrary
    if lib.does_asset_exist(LEVEL):
        unreal.EditorLevelLibrary.load_level(LEVEL)
        print("XINYI_V2_LEVEL_LOADED %s" % LEVEL)
    else:
        unreal.EditorLevelLibrary.new_level(LEVEL)
        print("XINYI_V2_LEVEL_CREATED %s" % LEVEL)

    world_name = current_world_name()
    if "L_XinyiV2_Contract" not in world_name:
        raise RuntimeError("wrong current map after load/create: %s" % world_name)

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in list(actor_sub.get_all_level_actors()):
        actor_sub.destroy_actor(actor)

    extent = contract["coordinate_contract"]["extent_enu_m"]
    # Heightmap row 0 is north/max-north; UE +Y points south.
    location = unreal.Vector(
        float(extent["min_east_m"]) * 100.0,
        -float(extent["max_north_m"]) * 100.0,
        0.0,
    )
    scale = landscape["scale_xyz"]
    scale_vec = unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2]))

    bridge = getattr(unreal, "XinyiLandscapeLibrary", None)
    if bridge is None:
        raise RuntimeError(
            "XinyiLandscapeLibrary is unavailable; compile/load XinyiLandscapeBridge first"
        )

    result_text = bridge.create_landscape_from_raw16(
        raw_path,
        631,
        631,
        int(landscape["sections_per_component"][0]),
        int(landscape["section_quads"]),
        location,
        scale_vec,
        LABEL,
    )
    result = json.loads(str(result_text))
    if not result.get("pass") or result.get("status") != "PASS_CREATED":
        write_report({"status": "FAIL_LANDSCAPE_CREATE", "bridge": result})
        raise RuntimeError("Landscape bridge failed: %s" % result)

    if int(result.get("component_count", -1)) != 25:
        raise RuntimeError("Landscape bridge did not create 25 components")

    if not unreal.EditorLevelLibrary.save_current_level():
        raise RuntimeError("save_current_level returned false")

    report = {
        "status": "PASS_LANDSCAPE_CREATED",
        "level": LEVEL,
        "label": LABEL,
        "bridge": result,
        "expected": {
            "component_count": 25,
            "location_cm": [location.x, location.y, location.z],
            "scale_xyz": [scale_vec.x, scale_vec.y, scale_vec.z],
        },
        "next_gate": "fresh-process reopen and bridge re-inspection",
    }
    write_report(report)
    print("XINYI_V2_LANDSCAPE_CREATE_JSON " + json.dumps(report, separators=(",", ":")))


main()
