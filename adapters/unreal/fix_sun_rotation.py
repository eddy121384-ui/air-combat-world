"""Point Sun back down at the city (runs inside UnrealEditor-Cmd).

Context: the Sun actor's rotation was found at pitch +30 (shining UP into
the sky), so Lit mode was pitch black — no light hit anything. Cause was
either an in-GUI accidental drag or a Rotator axis-ordering slip in the
original build script. This script sets rotation two independent ways and
only saves when the read-back matches the intent exactly.

Intended daylight: pitch -45 (45 deg down), yaw 30, roll 0.
Prints SUN_OK + saves, or SUN_MISMATCH and aborts without saving.

REQUIRES the GUI editor to be closed (it locks the .umap).
"""
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
WANT = (-45.0, 30.0, 0.0)


def rot_of(actor):
    r = actor.get_actor_rotation()
    return (float(r.pitch), float(r.yaw), float(r.roll))


def close(a, b, tol=0.5):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def main():
    try:
        unreal.EditorLevelLibrary.load_level(LEVEL)
        print("SUNFIX_LOADED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("SUNFIX_FAIL load %r" % e)
        return
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    by_label = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
    sun = by_label.get("Sun")
    if sun is None:
        print("SUNFIX_MISSING Sun")
        return
    print("SUNFIX_BEFORE (%.1f,%.1f,%.1f)" % rot_of(sun))
    try:
        comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
        print("SUNFIX_INTENSITY %r" % comp.get_editor_property("intensity"))
    except Exception as e:  # noqa: BLE001
        print("SUNFIX_INTENSITY_EXC %r" % e)
    # Attempt 1: constructor order (pitch, yaw, roll).
    try:
        sun.set_actor_rotation(unreal.Rotator(WANT[0], WANT[1], WANT[2]), False)
        print("SUNFIX_TRY1 (%.1f,%.1f,%.1f)" % rot_of(sun))
    except Exception as e:  # noqa: BLE001
        print("SUNFIX_TRY1_EXC %r" % e)
    if not close(rot_of(sun), WANT):
        # Attempt 2: attribute assignment (order-proof).
        try:
            r = sun.get_actor_rotation()
            r.pitch, r.yaw, r.roll = WANT
            sun.set_actor_rotation(r, False)
            print("SUNFIX_TRY2 (%.1f,%.1f,%.1f)" % rot_of(sun))
        except Exception as e:  # noqa: BLE001
            print("SUNFIX_TRY2_EXC %r" % e)
    if not close(rot_of(sun), WANT):
        print("SUNFIX_MISMATCH want=%s got=(%.1f,%.1f,%.1f) NOT saving"
              % (WANT, *rot_of(sun)))
        return
    print("SUNFIX_OK sun points down at the city")
    try:
        unreal.EditorLevelLibrary.save_current_level()
        print("SUNFIX_SAVED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("SUNFIX_SAVE_FAIL %r" % e)


main()
