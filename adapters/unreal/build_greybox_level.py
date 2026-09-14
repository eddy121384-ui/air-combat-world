"""UE 5.8 headless greybox-cleanup level build, v2 (runs inside UnrealEditor-Cmd).

Creates/rebuilds /Game/Taipei/L_TaipeiGreybox_Clean deterministically.

v1 post-mortem (why v1 lied): EditorLevelLibrary.new_level() on an EXISTING map
path only logs `LevelEditorSubsystem: Error: NewLevel. Failed to validate the
destination` and does NOT raise a Python exception. v1's try/except therefore
printed GREYBOX_CREATED, spawned 12 actors into the auto-loaded STARTUP map
(L_TaipeiGreybox), and save_current_level() persisted the WRONG map — while
L_TaipeiGreybox_Clean.umap stayed at the previous 8-actor version. The fix:

  1. If the level asset exists -> load_level() it; else -> new_level().
  2. Destroy every existing actor (deterministic rebuild, no duplicates).
  3. Spawn the 12, then assert the CURRENT world really is L_TaipeiGreybox_Clean
     and that all 11 required labels are present IN-PROCESS before saving.
  4. save_current_level() -> the saved package is the one we verified.

Reads env: ACW_SRC_DIR (default /Game/Taipei/XinyiGreybox).
Prints GREYBOX_COUNT_OK only if the in-process gate passes; a separate fresh
process (verify_greybox_reopen.py) re-loads the map and re-asserts persistence.
"""
import os
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
SRC_DIR = os.environ.get("ACW_SRC_DIR", "/Game/Taipei/XinyiGreybox")

WANTS = [
    ("layera_low", "CityMassing_Low"),
    ("layera_mid", "CityMassing_Mid"),
    ("layera_high", "CityMassing_High"),
    ("ground_plane", "Ground_Xinyi"),
    ("hero_taipei101", "Hero_Taipei101"),
]
REQUIRED = ([label for _, label in WANTS]
            + ["Sun", "Sky", "Fog", "Atmosphere", "Start_City", "Start_Flight"])


def current_labels():
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return sorted(a.get_actor_label() for a in sub.get_all_level_actors())


def main():
    lib = unreal.EditorAssetLibrary
    if lib.does_asset_exist(LEVEL):
        unreal.EditorLevelLibrary.load_level(LEVEL)
        print("GREYBOX_LOADED %s" % LEVEL)
    else:
        unreal.EditorLevelLibrary.new_level(LEVEL)
        print("GREYBOX_CREATED %s" % LEVEL)

    try:
        world_name = str(unreal.EditorLevelLibrary.get_editor_world())
    except Exception as e:  # noqa: BLE001
        world_name = "unknown (%r)" % e
    print("GREYBOX_CURRENT %s" % world_name)
    if "L_TaipeiGreybox_Clean" not in world_name:
        print("GREYBOX_WRONG_MAP aborting (refusing to spawn into %s)" % world_name)
        return

    # Deterministic rebuild: wipe everything, then spawn fresh.
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    wiped = 0
    for a in list(sub.get_all_level_actors()):
        try:
            sub.destroy_actor(a)
            wiped += 1
        except Exception as e:  # noqa: BLE001
            print("GREYBOX_WIPE_FAIL %r" % e)
    print("GREYBOX_WIPED %d" % wiped)

    found = {}
    try:
        listed = lib.list_assets(SRC_DIR, recursive=True)
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_LIST_FAIL %r" % e)
        listed = []
    for ap in listed:
        try:
            obj = lib.load_asset(ap)
        except Exception:  # noqa: BLE001
            continue
        if obj is None or obj.get_class().get_name() not in ("StaticMesh", "SkeletalMesh"):
            continue
        low = ap.lower()
        for key, _label in WANTS:
            if key in low and key not in found:
                found[key] = obj
    print("GREYBOX_MESHES %d/5" % len(found))

    for key, label in WANTS:
        if key not in found:
            print("GREYBOX_MISSING mesh for key=%s" % key)
            continue
        try:
            actor = sub.spawn_actor_from_object(found[key], unreal.Vector(0, 0, 0))
            actor.set_actor_label(label)
            print("GREYBOX_PLACED %s" % label)
        except Exception as e:  # noqa: BLE001
            print("GREYBOX_SPAWN_FAIL %s (%r)" % (label, e))

    def spawn_class(cls, label, loc):
        try:
            actor = sub.spawn_actor_from_class(cls, loc)
            actor.set_actor_label(label)
            print("GREYBOX_PLACED %s" % label)
            return actor
        except Exception as e:  # noqa: BLE001
            print("GREYBOX_SKIP %s (%r)" % (label, e))
            return None

    sun = spawn_class(unreal.DirectionalLight, "Sun", unreal.Vector(0, 0, 40000))
    if sun is not None:
        try:
            sun.set_actor_rotation(unreal.Rotator(-45, 30, 0), False)
        except Exception:  # noqa: BLE001
            pass
    spawn_class(unreal.SkyLight, "Sky", unreal.Vector(0, 0, 20000))
    spawn_class(unreal.ExponentialHeightFog, "Fog", unreal.Vector(0, 0, 0))
    try:
        spawn_class(unreal.SkyAtmosphere, "Atmosphere", unreal.Vector(0, 0, 0))
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_SKIP Atmosphere (%r)" % e)
    spawn_class(unreal.PlayerStart, "Start_City",
                unreal.Vector(-9078, -7792 + 90000, 35000))
    spawn_class(unreal.PlayerStart, "Start_Flight",
                unreal.Vector(-9078 + 150000, -7792 - 60000, 40000))

    labels = current_labels()
    missing = [r for r in REQUIRED if r not in labels]
    print("GREYBOX_ACTORS %s" % ",".join(labels))
    if missing:
        print("GREYBOX_COUNT_FAIL missing=%s (NOT saving)" % ",".join(missing))
        return
    print("GREYBOX_COUNT_OK 11/11 required labels present in-process")

    try:
        unreal.EditorLevelLibrary.save_current_level()
        print("GREYBOX_SAVED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_SAVE_FAIL %r" % e)
        return
    print("GREYBOX_OK %s" % LEVEL)


main()
