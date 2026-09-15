"""Task 1 — read-only collision capability probe (runs inside UnrealEditor-Cmd).

Loads /Game/Taipei/L_TaipeiGreybox_Clean and reports the collision state of
the 5 city meshes (CityMassing_Low/Mid/High, Ground_Xinyi, Hero_Taipei101).

READ-ONLY: loads the level, inspects properties, prints COLL_* lines.
Saves NOTHING, spawns NOTHING, destroys NOTHING, modifies NO assets.

Usage (from repo root):
  UnrealEditor-Cmd.exe unreal/AirCombatWorld.uproject \
    -ExecutePythonScript=adapters/unreal/probe_collision.py \
    -unattended -nopause -nosound
Then grep stdout / unreal/Saved/Logs/AirCombatWorld.log for COLL_.
"""

import traceback
import unreal

LEVEL = "/Game/Taipei/L_TaipeiGreybox_Clean"
LABELS = [
    "CityMassing_Low",
    "CityMassing_Mid",
    "CityMassing_High",
    "Ground_Xinyi",
    "Hero_Taipei101",
]
GEOM_ARRAYS = (
    "box_elems",
    "sphere_elems",
    "sphyl_elems",
    "convex_elems",
    "tapered_capsule_elems",
)


def safe_get(obj, prop, tag):
    try:
        return obj.get_editor_property(prop)
    except Exception as e:  # noqa: BLE001
        print("COLL_UNREADABLE %s.%s %r" % (tag, prop, e))
        return None


def report_component(actor, label):
    try:
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    except Exception as e:  # noqa: BLE001
        print("COLL_COMP %s no_staticmeshcomponent %r" % (label, e))
        return
    if comp is None:
        print("COLL_COMP %s component=None" % label)
        return
    bi = safe_get(comp, "body_instance", label + ".comp")
    if bi is None:
        print("COLL_COMP %s body_instance=None" % label)
    else:
        coll_en = safe_get(bi, "collision_enabled", label + ".bodyinst")
        print("COLL_COMP %s collision_enabled=%s" % (label, coll_en))
        cpx = safe_get(bi, "b_use_complex_as_simple_collision",
                       label + ".bodyinst")
        print("COLL_COMP %s use_complex_as_simple=%s" % (label, cpx))
    mesh = safe_get(comp, "static_mesh", label + ".comp")
    if mesh is None:
        print("COLL_MESH %s mesh=None" % label)
        return
    print("COLL_MESH %s asset=%s" % (label, mesh.get_path_name()))
    try:
        print("COLL_MESH %s verts=%s tris=%s" % (
            label, mesh.get_num_vertices(0), mesh.get_num_triangles(0)))
    except Exception as e:  # noqa: BLE001
        print("COLL_UNREADABLE %s.mesh_counts %r" % (label, e))
    bs = safe_get(mesh, "body_setup", label + ".mesh")
    if bs is None:
        print("COLL_BODY %s body_setup=None (NO collision data at all)" % label)
        return
    flag = safe_get(bs, "collision_trace_flag", label + ".body")
    print("COLL_BODY %s trace_flag=%s" % (label, flag))
    dbl = safe_get(bs, "b_double_sided_geometry", label + ".body")
    if dbl is None:
        dbl = safe_get(bs, "bDoubleSidedGeometry", label + ".body")
    print("COLL_BODY %s double_sided=%s" % (label, dbl))
    aggr = None
    for _cand in ("agg_geom", "aggr_geom"):
        aggr = safe_get(bs, _cand, label + ".body")
        if aggr is not None:
            print("COLL_BODY %s geom_prop=%s" % (label, _cand))
            break
    if aggr is None:
        print("COLL_SIMPLE %s aggr_geom=None" % label)
        return
    total = 0
    for arr in GEOM_ARRAYS:
        try:
            elems = aggr.get_editor_property(arr)
            n = len(elems) if elems is not None else 0
        except Exception as e:  # noqa: BLE001
            print("COLL_UNREADABLE %s.aggr.%s %r" % (label, arr, e))
            continue
        total += n
        print("COLL_SIMPLE %s %s=%d" % (label, arr, n))
    print("COLL_SIMPLE %s total_simple_shapes=%d" % (label, total))


def main():
    try:
        unreal.EditorLevelLibrary.load_level(LEVEL)
        print("COLL_LOADED %s" % LEVEL)
    except Exception:  # noqa: BLE001
        print("COLL_LOAD_FAIL %s" % LEVEL)
        traceback.print_exc()
        return
    try:
        sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actors = {a.get_actor_label(): a for a in sub.get_all_level_actors()}
    except Exception:  # noqa: BLE001
        print("COLL_ACTOR_ENUM_FAIL")
        traceback.print_exc()
        return
    print("COLL_ACTORS %s" % ",".join(sorted(actors.keys())))
    for label in LABELS:
        if label not in actors:
            print("COLL_MISSING actor %s" % label)
            continue
        try:
            report_component(actors[label], label)
        except Exception:  # noqa: BLE001
            print("COLL_REPORT_FAIL %s" % label)
            traceback.print_exc()
    print("COLL_DONE (no saves performed)")


main()
