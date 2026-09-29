"""XinyiLook stage 2: assemble the hero look level (UE5.8, UnrealEditor-Cmd).

/Game/XinyiV2/L_XinyiV2_Contract is duplicated to /Game/XinyiLook/L_XinyiLook_Hero.
The contract level and its assets are never modified or saved by this script.

In the look level:
- the 25 runtime tile actors keep their validated transforms; their mesh is
  swapped for the look mesh (bit-identical triangle soup). Location is
  re-derived from bounds so it cannot silently drift (fail closed > 0.5 cm);
- Landscape gets M_XinyiGround;
- Taipei 101 hero, basin backdrop, road paint and an instanced tree HISM are
  spawned (pivot corrected from measured vs expected bounds);
- a movable sun / SkyAtmosphere / SkyLight / height fog / unbound post volume
  rig is added with the "day" preset (dusk/night are applied transiently by
  the capture stage or via MPC_XinyiLook at runtime).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("ACW_REPO_ROOT", ""), "adapters", "unreal", "lookdev"))
import unreal  # noqa: E402
from xinyi_look_common import (  # noqa: E402
    LOOK_LEVEL, LOOK_OUT, LOOK_PREFIX, MPC_PATH, REPORT_DIR, RUNTIME_PREFIX, SOURCE_LEVEL, TERRAIN_LABEL,
    enu_to_ue_cm, finite3, lib, max_err, mesh_bounds, read_json, write_report,
)
from xinyi_look_tod import apply_tod, spawn_rig  # noqa: E402

LOC_TOL_CM = 0.5
TREE_CULL_START_CM = 150000.0
TREE_CULL_END_CM = 260000.0


def duplicate_level():
    if lib.does_asset_exist(LOOK_LEVEL):
        if not lib.delete_asset(LOOK_LEVEL):
            raise RuntimeError("cannot replace previous look level %s" % LOOK_LEVEL)
    dup = lib.duplicate_asset(SOURCE_LEVEL, LOOK_LEVEL)
    if dup is None:
        raise RuntimeError("duplicate_asset failed for %s" % SOURCE_LEVEL)


def spawn_mesh_actor(actors, mesh, world_origin_cm, expected_origin, label):
    imported_origin, _ = mesh_bounds(mesh)
    loc = [world_origin_cm[i] + expected_origin[i] - imported_origin[i] for i in range(3)]
    if not finite3(loc):
        raise RuntimeError("non-finite location for %s" % label)
    a = actors.spawn_actor_from_object(mesh, unreal.Vector(*loc))
    if a is None:
        raise RuntimeError("spawn failed for %s" % label)
    a.set_actor_label(LOOK_PREFIX + label)
    return a, loc


def add_hism(actor, mesh):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams()
    params.set_editor_property("parent_handle", handles[0])
    params.set_editor_property("new_class", unreal.HierarchicalInstancedStaticMeshComponent)
    new_handle, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("add_new_subobject failed: %s" % fail)
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(
        unreal.SubobjectDataBlueprintFunctionLibrary.get_data(new_handle))
    comp.set_static_mesh(mesh)
    return comp


def main():
    assets = read_json(REPORT_DIR / "look_assets.report.json")
    if assets.get("status") != "PASS_LOOK_ASSETS":
        raise RuntimeError("run xinyi_look_build_assets.py first (look_assets.report.json not PASS)")
    hero = read_json(LOOK_OUT / "hero/taipei101.anchor.json")
    ground = read_json(LOOK_OUT / "ground/ground.report.json")
    trees = read_json(LOOK_OUT / "ground" / ground["tree_instances"])["instances"]

    duplicate_level()
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not levels.load_level(LOOK_LEVEL):
        raise RuntimeError("failed to load %s" % LOOK_LEVEL)

    all_actors = list(actors.get_all_level_actors())
    by_label = {a.get_actor_label(): a for a in all_actors}
    terrain = by_label.get(TERRAIN_LABEL)
    if terrain is None:
        raise RuntimeError("validated Landscape missing from duplicated level")
    for a in all_actors:
        if a.get_actor_label().startswith(LOOK_PREFIX):
            actors.destroy_actor(a)

    failures, swapped = [], []
    tiles = {r["tile"]: r for r in assets["tiles"]}
    runtime = [a for a in all_actors if a.get_actor_label().startswith(RUNTIME_PREFIX)]
    if len(runtime) != 25:
        raise RuntimeError("expected 25 runtime tile actors, found %d" % len(runtime))
    for actor in runtime:
        tile = actor.get_actor_label()[len(RUNTIME_PREFIX):].replace("p", "+").replace("m", "-")
        row = tiles.get(tile)
        if row is None:
            failures.append({"actor": actor.get_actor_label(), "reason": "no look tile"})
            continue
        comp = actor.get_component_by_class(unreal.StaticMeshComponent)
        old = comp.get_editor_property("static_mesh")
        old_origin, old_extent = mesh_bounds(old)
        new = lib.load_asset(row["asset_path"])
        new_origin, new_extent = mesh_bounds(new)
        if max_err(old_extent, new_extent) > 2.0:
            failures.append({"tile": tile, "reason": "extent differs from accepted mesh"})
            continue
        loc = actor.get_actor_location()
        before = [float(loc.x), float(loc.y), float(loc.z)]
        target = [before[i] + old_origin[i] - new_origin[i] for i in range(3)]
        # independent check against the contract-derived translation
        contract_loc = [row["tile_world_translation_cm"][i] + row["expected_local_bounds_origin_cm"][i]
                        - new_origin[i] for i in range(3)]
        if max_err(target, contract_loc) > LOC_TOL_CM:
            failures.append({"tile": tile, "reason": "placement disagrees with contract",
                             "target": target, "contract": contract_loc})
            continue
        comp.set_static_mesh(new)
        actor.set_actor_location(unreal.Vector(*target), False, False)
        swapped.append({"tile": tile, "asset": row["asset_path"], "location_cm": target})

    terrain.set_editor_property("landscape_material", lib.load_asset("/Game/XinyiLook/Materials/M_XinyiGround"))

    s = assets["singles"]
    hero_mesh = lib.load_asset(s["hero"]["asset_path"])
    _, hero_loc = spawn_mesh_actor(actors, hero_mesh, hero["ue_actor_location_cm"],
                                   s["hero"]["expected_bounds_origin_cm"], "Taipei101")
    lm_mesh = lib.load_asset(s["landmarks"]["asset_path"])
    spawn_mesh_actor(actors, lm_mesh, [0.0, 0.0, 0.0], s["landmarks"]["expected_bounds_origin_cm"], "LandmarkRoofs")
    back_mesh = lib.load_asset(s["backdrop"]["asset_path"])
    back, _ = spawn_mesh_actor(actors, back_mesh, [0.0, 0.0, 0.0], s["backdrop"]["expected_bounds_origin_cm"],
                               "BasinBackdrop")
    back.get_component_by_class(unreal.StaticMeshComponent).set_cast_shadow(False)
    paint_mesh = lib.load_asset(s["paint"]["asset_path"])
    paint, _ = spawn_mesh_actor(actors, paint_mesh, [0.0, 0.0, 0.0], s["paint"]["expected_bounds_origin_cm"],
                                "RoadPaint")
    pc = paint.get_component_by_class(unreal.StaticMeshComponent)
    pc.set_cast_shadow(False)
    pc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    pc.set_editor_property("ld_max_draw_distance", 180000.0)

    # trees: one HISM, per-instance custom data = variant
    tree_mesh = lib.load_asset(s["tree"]["asset_path"])
    pivot = [s["tree"]["expected_bounds_origin_cm"][i] - s["tree"]["imported_bounds_origin_cm"][i] for i in range(3)]
    holder = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0.0, 0.0, 0.0))
    holder.set_actor_label(LOOK_PREFIX + "Trees")
    hism = add_hism(holder, tree_mesh)
    try:
        hism.set_num_custom_data_floats(1)
    except Exception:
        hism.set_editor_property("num_custom_data_floats", 1)
    xforms = []
    for t in trees:
        p = enu_to_ue_cm(t["e"], t["n"], t["z"])
        xforms.append(unreal.Transform(
            unreal.Vector(p.x + pivot[0] * t["s"], p.y + pivot[1] * t["s"], p.z + pivot[2] * t["s"]),
            unreal.Rotator(0.0, 0.0, float(t["yaw"])),
            unreal.Vector(t["s"], t["s"], t["s"])))
    hism.add_instances(xforms, False, True)
    for i, t in enumerate(trees):
        hism.set_custom_data_value(i, 0, (t["v"] + 0.5) / 4.0, False)
    hism.set_cull_distances(TREE_CULL_START_CM, TREE_CULL_END_CM)
    hism.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    hism.mark_render_state_dirty()
    tree_count = int(hism.get_instance_count())
    if tree_count != len(trees):
        failures.append({"trees": "instance count %d != %d" % (tree_count, len(trees))})

    # rooftop clutter: one holder actor, one HISM per prop type
    roof_inst = read_json(LOOK_OUT / "rooftops/rooftop_instances.json")["types"]
    roof_holder = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0.0, 0.0, 0.0))
    roof_holder.set_actor_label(LOOK_PREFIX + "RooftopProps")
    roof_counts = {}
    for t, row in assets["rooftop_props"].items():
        items = roof_inst.get(t, [])
        if not items:
            continue
        mesh = lib.load_asset(row["asset_path"])
        pv = [row["expected_bounds_origin_cm"][i] - row["imported_bounds_origin_cm"][i] for i in range(3)]
        h = add_hism(roof_holder, mesh)
        try:
            h.set_num_custom_data_floats(1)
        except Exception:
            h.set_editor_property("num_custom_data_floats", 1)
        xf = []
        for it in items:
            p = enu_to_ue_cm(it["e"], it["n"], it["z"])
            sc = (it["sx"], it["sy"], it["sz"])
            # ENU yaw (CCW from east) -> UE yaw (Y = -north flips handedness)
            xf.append(unreal.Transform(
                unreal.Vector(p.x + pv[0] * sc[0], p.y + pv[1] * sc[1], p.z + pv[2] * sc[2]),
                unreal.Rotator(0.0, 0.0, -float(it["yaw"])),
                unreal.Vector(sc[0], sc[1], sc[2])))
        h.add_instances(xf, False, True)
        for i, it in enumerate(items):
            h.set_custom_data_value(i, 0, (it["v"] + 0.5) / 4.0, False)
        h.set_cull_distances(60000.0 if t in ("ac", "antenna") else 120000.0,
                             90000.0 if t in ("ac", "antenna") else 200000.0)
        h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        h.set_cast_shadow(t not in ("ac", "avlight", "antenna"))
        h.mark_render_state_dirty()
        roof_counts[t] = int(h.get_instance_count())
        if roof_counts[t] != len(items):
            failures.append({"rooftop": t, "count": roof_counts[t], "expected": len(items)})

    # far-LOD Taipei basin massing (real WFS statistics), no shadows / collision
    far_n = 0
    for row in assets.get("far_city_chunks", []):
        mesh = lib.load_asset(row["asset_path"])
        a, _ = spawn_mesh_actor(actors, mesh, row["ue_actor_location_cm"], row["expected_bounds_origin_cm"],
                                "FarCity_%d_%d" % tuple(row["chunk"]))
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        c.set_cast_shadow(False)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        far_n += 1

    spawn_rig(actors)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    apply_tod(world, actors, "day", persist_mpc_defaults=True)

    status = "PASS_LOOK_LEVEL" if not failures and len(swapped) == 25 else "FAIL_LOOK_LEVEL"
    if status == "PASS_LOOK_LEVEL":
        if not levels.save_current_level():
            raise RuntimeError("save_current_level returned false")
    report = {
        "status": status,
        "source_level": SOURCE_LEVEL,
        "look_level": LOOK_LEVEL,
        "tiles_swapped": swapped,
        "hero_location_cm": hero_loc,
        "tree_instances": tree_count,
        "rooftop_instances": roof_counts,
        "far_city_chunks": far_n,
        "failures": failures,
        "contract_level_saved": False,
    }
    write_report("look_level.report.json", report)
    if status != "PASS_LOOK_LEVEL":
        raise RuntimeError("XinyiLook level stage failed: %s" % json.dumps(failures)[:2000])


main()
