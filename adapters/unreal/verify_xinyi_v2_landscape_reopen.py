"""Fresh-process persistence gate for the real XinyiV2 ALandscape."""
import json
import math
import os

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
LABEL = "Terrain_Xinyi_MOI2025"
REPORT_PATH = os.environ.get("ACW_XINYI_V2_LANDSCAPE_REOPEN_REPORT", "")


def close(a, b, tol):
    return math.isfinite(float(a)) and abs(float(a) - float(b)) <= tol


def main():
    unreal.EditorLevelLibrary.load_level(LEVEL)
    world_name = str(unreal.EditorLevelLibrary.get_editor_world())
    if "L_XinyiV2_Contract" not in world_name:
        raise RuntimeError("fresh process loaded wrong map: %s" % world_name)

    bridge = getattr(unreal, "XinyiLandscapeLibrary", None)
    if bridge is None:
        raise RuntimeError("XinyiLandscapeLibrary unavailable in fresh process")

    result = json.loads(str(bridge.inspect_landscape_by_label(LABEL)))
    failures = []

    if not result.get("pass"):
        failures.append("bridge_inspection_failed")
    if int(result.get("component_count", -1)) != 25:
        failures.append("component_count_not_25")
    if result.get("landscape_info_valid") is not True:
        failures.append("landscape_info_invalid")
    if result.get("landscape_extent_quads") != [0, 0, 630, 630]:
        failures.append("landscape_extent_not_630x630")

    expected_location = [-150000.0, -150000.0, 0.0]
    expected_scale = [396.82539682539687, 396.82539682539687, 200.0]
    for got, want in zip(result.get("location_cm", []), expected_location):
        if not close(got, want, 0.05):
            failures.append("location_mismatch")
            break
    for got, want in zip(result.get("scale_xyz", []), expected_scale):
        if not close(got, want, 1.0e-4):
            failures.append("scale_mismatch")
            break

    bounds_min = result.get("bounds_min_cm") or []
    bounds_max = result.get("bounds_max_cm") or []
    if len(bounds_min) != 3 or len(bounds_max) != 3:
        failures.append("bounds_missing")
    else:
        # One full 2.5 km Xinyi square in the validated UE horizontal frame.
        if not close(bounds_min[0], -150000.0, 500.0):
            failures.append("bounds_min_x")
        if not close(bounds_max[0], 100000.0, 500.0):
            failures.append("bounds_max_x")
        if not close(bounds_min[1], -150000.0, 500.0):
            failures.append("bounds_min_y")
        if not close(bounds_max[1], 100000.0, 500.0):
            failures.append("bounds_max_y")

    report = {
        "status": "PASS_LANDSCAPE_FRESH_REOPEN" if not failures else "FAIL_LANDSCAPE_FRESH_REOPEN",
        "level": LEVEL,
        "label": LABEL,
        "inspection": result,
        "failures": failures,
    }

    if REPORT_PATH:
        os.makedirs(os.path.dirname(os.path.abspath(REPORT_PATH)), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")

    print("XINYI_V2_LANDSCAPE_REOPEN_JSON " + json.dumps(report, separators=(",", ":")))
    if failures:
        raise RuntimeError("fresh landscape reopen gate failed: %s" % failures)


main()
