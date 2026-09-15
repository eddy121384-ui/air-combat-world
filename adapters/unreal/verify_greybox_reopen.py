"""Fresh-process reopen validation for L_TaipeiGreybox_Clean (runs inside a NEW
UnrealEditor-Cmd process, AFTER the build process has fully exited).

Loads the SAVED map from disk and enumerates actor labels. This is the gate
that v1 lacked: it proves save -> close -> reopen persistence instead of
trusting same-session spawn logs.

Required (11): CityMassing_Low/Mid/High, Ground_Xinyi, Hero_Taipei101,
Sun, Sky, Fog, Atmosphere, Start_City, Start_Flight.

Prints REOPEN_OK (exit path normal) or REOPEN_FAIL + missing list.
Check the engine log for the REOPEN_ line; the Cmd exit code alone is not
the signal.
"""
import os
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
SRC_DIR = os.environ.get("ACW_SRC_DIR", "/Game/Taipei/XinyiGreybox")
REQUIRED = ["CityMassing_Low", "CityMassing_Mid", "CityMassing_High",
            "Ground_Xinyi", "Hero_Taipei101",
            "Sun", "Sky", "Fog", "Atmosphere", "Start_City", "Start_Flight"]


def main():
    try:
        unreal.EditorLevelLibrary.load_level(LEVEL)
        print("REOPEN_LOADED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("REOPEN_FAIL load error %r" % e)
        return
    try:
        world_name = str(unreal.EditorLevelLibrary.get_editor_world())
    except Exception as e:  # noqa: BLE001
        world_name = "unknown (%r)" % e
    print("REOPEN_CURRENT %s" % world_name)

    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    labels = sorted(a.get_actor_label() for a in sub.get_all_level_actors())
    print("REOPEN_ACTORS %s" % ",".join(labels))
    missing = [r for r in REQUIRED if r not in labels]
    if missing:
        print("REOPEN_FAIL missing=%s" % ",".join(missing))
        return
    print("REOPEN_OK 11/11 required labels persist after fresh reopen")

    # Mobile-first gate: no mesh under SRC_DIR may require Nanite/SM6.
    lib = unreal.EditorAssetLibrary
    try:
        listed = lib.list_assets(SRC_DIR, recursive=True)
    except Exception as e:  # noqa: BLE001
        print("REOPEN_NANITE_LIST_FAIL %r" % e)
        return
    checked, offenders = 0, []
    for ap in listed:
        try:
            obj = lib.load_asset(ap)
        except Exception:  # noqa: BLE001
            continue
        if obj is None or obj.get_class().get_name() != "StaticMesh":
            continue
        checked += 1
        try:
            if obj.get_editor_property("nanite_settings").get_editor_property("enabled"):
                offenders.append(ap)
        except Exception as e:  # noqa: BLE001
            offenders.append("%s (unreadable: %r)" % (ap, e))
    if offenders:
        print("REOPEN_NANITE_FAIL offenders=%s" % ",".join(offenders))
        return
    print("REOPEN_NANITE_OK %d meshes, all Nanite off (SM5 raster safe)" % checked)


main()
