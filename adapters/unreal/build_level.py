"""UE 5.8 headless level build for the greybox spike (runs inside UnrealEditor-Cmd).

Creates /Game/Taipei/L_TaipeiGreybox with:
  - layerA city massing + 101 placeholder StaticMeshActors at origin
  - DirectionalLight + SkyLight + ExponentialHeightFog (+ SkyAtmosphere if available)
  - PlayerStart high above Xinyi (default pawn flies: WASD + mouse in PIE)
Saves the level. Prints LEVEL_OK + placed actors. Defensive: each step try/except.
"""
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox"
CITY = "/Game/Taipei/xinyi_tile_2km/StaticMeshes/layerA_city_massing.layerA_city_massing"
HERO = "/Game/Taipei/xinyi_tile_2km/StaticMeshes/hero_taipei101_placeholder.hero_taipei101_placeholder"


def spawn_mesh(path, label):
    sm = unreal.EditorAssetLibrary.load_asset(path)
    if sm is None:
        print("LEVEL_MISSING %s" % path)
        return None
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = sub.spawn_actor_from_object(sm, unreal.Vector(0, 0, 0))
    actor.set_actor_label(label)
    print("LEVEL_PLACED %s" % label)
    return actor


def spawn_class(cls, label, loc):
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = sub.spawn_actor_from_class(cls, loc)
        actor.set_actor_label(label)
        print("LEVEL_PLACED %s" % label)
        return actor
    except Exception as e:  # noqa: BLE001
        print("LEVEL_SKIP %s (%r)" % (label, e))
        return None


def main():
    try:
        unreal.EditorLevelLibrary.new_level(LEVEL)
        print("LEVEL_CREATED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("LEVEL_NOTE new_level: %r (loading existing?)" % e)
        try:
            unreal.EditorAssetLibrary.load_asset(LEVEL)
        except Exception as e2:  # noqa: BLE001
            print("LEVEL_FAIL %r" % e2)
            return

    spawn_mesh(CITY, "CityMassing_Xinyi")
    spawn_mesh(HERO, "Hero_Taipei101")

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
        print("LEVEL_SKIP Atmosphere (%r)" % e)
    # PlayerStart ~350 m above the 101 site (ENU -90,78 m -> UE cm x10... see note)
    # UE units are cm: 101 site ≈ (-9078, -7792) cm; start 350 m up + 900 m south.
    spawn_class(unreal.PlayerStart, "Start", unreal.Vector(-9078, -7792 + 90000, 35000))

    try:
        unreal.EditorLevelLibrary.save_current_level()
        print("LEVEL_SAVED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("LEVEL_SAVE_FAIL %r" % e)
    print("LEVEL_OK %s" % LEVEL)


main()
