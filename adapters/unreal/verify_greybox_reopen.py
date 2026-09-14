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
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
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


main()
