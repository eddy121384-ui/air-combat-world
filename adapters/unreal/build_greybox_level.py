"""UE 5.8 headless greybox-cleanup level build (runs inside UnrealEditor-Cmd).

Creates /Game/Taipei/L_TaipeiGreybox_Clean (ADDITIVE — L_TaipeiGreybox untouched):
  - layerA_low / layerA_mid / layerA_high + ground_plane + hero StaticMeshActors
  - DirectionalLight Sun (-45 deg) + SkyLight + ExponentialHeightFog (light) +
    SkyAtmosphere if available (neutral daylight, no Lumen/Nanite/VSM changes)
  - 2 PlayerStarts: Start_City (350 m alt, 900 m south of 101, as v0) and
    Start_Flight (400 m alt, 1500 m east of 101 for flight-perspective checks)
Saves the level. Prints GREYBOX_OK + placements. Defensive: each step try/except.

Reads env: ACW_SRC_DIR (default /Game/Taipei/XinyiGreybox) — assets are matched
by name substring so Interchange naming variations don't break the build.
"""
import os
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
SRC_DIR = os.environ.get("ACW_SRC_DIR", "/Game/Taipei/XinyiGreybox")

WANTS = [
    ("layerA_low", "CityMassing_Low"),
    ("layerA_mid", "CityMassing_Mid"),
    ("layerA_high", "CityMassing_High"),
    ("ground_plane", "Ground_Xinyi"),
    ("hero_taipei101", "Hero_Taipei101"),
]


def find_assets():
    lib = unreal.EditorAssetLibrary
    try:
        listed = lib.list_assets(SRC_DIR, recursive=True)
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_LIST_FAIL %r" % e)
        return []
    print("GREYBOX_LISTED %d under %s" % (len(listed), SRC_DIR))
    out = []
    for ap in listed:
        try:
            obj = lib.load_asset(ap)
        except Exception as e:  # noqa: BLE001
            print("GREYBOX_ASSET %s load fail %r" % (ap, e))
            continue
        cls = obj.get_class().get_name() if obj else "None"
        print("GREYBOX_ASSET %s class=%s" % (ap, cls))
        if obj is not None and cls in ("StaticMesh", "SkeletalMesh"):
            out.append((ap, obj))
    return out


def spawn_mesh(obj, label):
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = sub.spawn_actor_from_object(obj, unreal.Vector(0, 0, 0))
        actor.set_actor_label(label)
        print("GREYBOX_PLACED %s" % label)
        return actor
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_SPAWN_FAIL %s (%r)" % (label, e))
        return None


def spawn_class(cls, label, loc):
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = sub.spawn_actor_from_class(cls, loc)
        actor.set_actor_label(label)
        print("GREYBOX_PLACED %s" % label)
        return actor
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_SKIP %s (%r)" % (label, e))
        return None


def main():
    try:
        unreal.EditorLevelLibrary.new_level(LEVEL)
        print("GREYBOX_CREATED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_NOTE new_level: %r (loading existing?)" % e)
        try:
            unreal.EditorAssetLibrary.load_asset(LEVEL)
        except Exception as e2:  # noqa: BLE001
            print("GREYBOX_FAIL %r" % e2)
            return

    found = find_assets()
    by_key = {}
    for ap, obj in found:
        low = ap.lower()
        for key, _label in WANTS:
            if key.lower() in low and key not in by_key:
                by_key[key] = obj

    for key, label in WANTS:
        if key in by_key:
            spawn_mesh(by_key[key], label)
        else:
            print("GREYBOX_MISSING mesh for key=%s" % key)

    # Neutral daylight test environment (cheap, no Lumen/Nanite/VSM/post).
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

    # 101 site ≈ (-9078, -7792) cm. Start_City mirrors v0; Start_Flight gives
    # an east-offset 400 m-alt viewpoint for flight-perspective checks.
    spawn_class(unreal.PlayerStart, "Start_City",
                unreal.Vector(-9078, -7792 + 90000, 35000))
    spawn_class(unreal.PlayerStart, "Start_Flight",
                unreal.Vector(-9078 + 150000, -7792 - 60000, 40000))

    try:
        unreal.EditorLevelLibrary.save_current_level()
        print("GREYBOX_SAVED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("GREYBOX_SAVE_FAIL %r" % e)
    print("GREYBOX_OK %s" % LEVEL)


main()
