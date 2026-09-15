"""Set Sun + Sky to Movable so no lighting bake is ever needed (runs in Cmd).

Context: the greybox level uses default Static lights, so the GUI demands a
lighting rebuild (red "LIGHTING NEEDS TO BE REBUILT (5 unbuilt objects)").
Skyfront is mobile-first (iPhone 13 mini): baked lightmaps cost build time +
memory and misrepresent the target. Movable (fully dynamic) lights render
without any bake and match the mobile direction.

For each of Sun (DirectionalLight) / Sky (SkyLight): set the light
component's mobility to MOVABLE, read it back, then save the level.
Prints LIGHT_OK only if both read back MOVABLE and the save succeeds.

REQUIRES the GUI editor to be closed (it locks the .umap, same file-lock
lesson as the Nanite fix).
"""
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
TARGETS = [
    ("Sun", unreal.DirectionalLightComponent),
    ("Sky", unreal.SkyLightComponent),
]


def main():
    try:
        unreal.EditorLevelLibrary.load_level(LEVEL)
        print("LIGHT_LOADED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("LIGHT_FAIL load %r" % e)
        return
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    labels = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
    ok = True
    for label, comp_class in TARGETS:
        actor = labels.get(label)
        if actor is None:
            print("LIGHT_MISSING %s" % label)
            ok = False
            continue
        try:
            comp = actor.get_component_by_class(comp_class)
            comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
            back = comp.get_editor_property("mobility")
            # ComponentMobility compares by enum value; print the name.
            print("LIGHT_SET %s -> %s" % (label, back))
            if back == unreal.ComponentMobility.MOVABLE:
                print("LIGHT_OK %s movable" % label)
            else:
                print("LIGHT_MISMATCH %s got %s" % (label, back))
                ok = False
        except Exception as e:  # noqa: BLE001
            print("LIGHT_EXC %s %r" % (label, e))
            ok = False
    if not ok:
        print("LIGHT_ABORT not saving")
        return
    try:
        unreal.EditorLevelLibrary.save_current_level()
        print("LIGHT_SAVED %s" % LEVEL)
    except Exception as e:  # noqa: BLE001
        print("LIGHT_SAVE_FAIL %r" % e)
        return
    print("LIGHT_DONE movable sun+sky, no bake needed")


main()
