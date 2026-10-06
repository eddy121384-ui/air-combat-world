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
from xinyi_look_clouds import apply_clouds, spawn_clouds  # noqa: E402
from xinyi_look_tod import apply_tod, spawn_rig  # noqa: E402

LOC_TOL_CM = 0.5
TREE_CULL_START_CM = 150000.0
TREE_CULL_END_CM = 260000.0
# Street identity v0B: low-flight layer. Blades keep the street silhouette to ~0.7 km, small boxes and
# awnings fade much earlier; boxes cast no shadow (sub-metre, near only).
STREET_HISM = {"sign": ((50000.0, 70000.0), True), "box": ((22000.0, 32000.0), False),
               "awning": ((28000.0, 40000.0), True)}


def remove_previous_look_level():
    """Make the build repeatable: replace only the generated look level, nothing else.

    EditorAssetLibrary.delete_asset leaves the .umap on disk in UE5.8, and save_map then refuses with
    "Unable to overwrite existing package", so the file is removed explicitly. The guard keeps this to
    the single generated /Game/XinyiLook package; /Game/XinyiV2 and /Game/Taipei are never touched.
    """
    if not LOOK_LEVEL.startswith("/Game/XinyiLook/") or LOOK_LEVEL == SOURCE_LEVEL:
        raise RuntimeError("refusing to replace non-generated level %s" % LOOK_LEVEL)
    if lib.does_asset_exist(LOOK_LEVEL):
        if not lib.delete_asset(LOOK_LEVEL):
            raise RuntimeError("cannot replace previous look level %s" % LOOK_LEVEL)
    umap = os.path.join(unreal.Paths.project_content_dir(), LOOK_LEVEL[len("/Game/"):] + ".umap")
    if os.path.isfile(umap):
        os.remove(umap)
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/Game/XinyiLook"], True)
    if os.path.isfile(umap) or lib.does_asset_exist(LOOK_LEVEL):
        raise RuntimeError("previous look level could not be removed: %s" % umap)


def duplicate_level():
    remove_previous_look_level()
    # EditorAssetLibrary.duplicate_asset on a World only creates an unsaved in-memory world; loading the
    # on-disk path afterwards then trips the engine's "old world not cleaned up" fatal. Save-as from the
    # loaded source writes the real .umap and leaves it current. The source package is not written.
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(SOURCE_LEVEL):
        raise RuntimeError("cannot load source level %s" % SOURCE_LEVEL)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, LOOK_LEVEL):
        raise RuntimeError("save_map (save-as) failed for %s" % LOOK_LEVEL)


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


def place_hism(actors, asset_row, items, label, cull, cast_shadow, uniform_key=None, variants=4):
    """One holder actor + HISM; per-instance custom data 0 = variant (0..1) = (v + 0.5) / variants."""
    mesh = lib.load_asset(asset_row["asset_path"])
    pv = [asset_row["expected_bounds_origin_cm"][i] - asset_row["imported_bounds_origin_cm"][i] for i in range(3)]
    holder = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0.0, 0.0, 0.0))
    holder.set_actor_label(LOOK_PREFIX + label)
    h = add_hism(holder, mesh)
    try:
        h.set_num_custom_data_floats(1)
    except Exception:
        h.set_editor_property("num_custom_data_floats", 1)
    xf = []
    for it in items:
        p = enu_to_ue_cm(it["e"], it["n"], it["z"])
        if uniform_key:
            sc = (it[uniform_key],) * 3
        else:
            sc = (it["sx"], it["sy"], it["sz"])
        # ENU yaw (CCW from east) -> UE yaw (UE Y = -north flips handedness)
        xf.append(unreal.Transform(
            unreal.Vector(p.x + pv[0] * sc[0], p.y + pv[1] * sc[1], p.z + pv[2] * sc[2]),
            unreal.Rotator(0.0, 0.0, -float(it["yaw"])),
            unreal.Vector(sc[0], sc[1], sc[2])))
    h.add_instances(xf, False, True)
    for i, it in enumerate(items):
        h.set_custom_data_value(i, 0, (it["v"] + 0.5) / float(variants), False)
    h.set_cull_distances(cull[0], cull[1])
    h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    h.set_cast_shadow(cast_shadow)
    try:  # not exposed to Python on every UE5.x build; a render-refresh hint only
        h.mark_render_state_dirty()
    except AttributeError:
        pass
    return int(h.get_instance_count())


def main():
    assets = read_json(REPORT_DIR / "look_assets.report.json")
    if assets.get("status") != "PASS_LOOK_ASSETS":
        raise RuntimeError("run xinyi_look_build_assets.py first (look_assets.report.json not PASS)")
    hero = read_json(LOOK_OUT / "hero/taipei101.anchor.json")
    ground = read_json(LOOK_OUT / "ground/ground.report.json")

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

    # instanced ground layers: street/park trees, hill forest clumps, street lamps
    tree_count = 0
    ground_counts = {}
    for key, inst_file, label, cull, shadow in (
        ("tree", ground["tree_instances"], "Trees", (TREE_CULL_START_CM, TREE_CULL_END_CM), True),
        ("forest", ground["forest_instances"], "HillForest", (160000.0, 240000.0), True),
        ("lamp", ground["lamp_instances"], "StreetLamps", (200000.0, 260000.0), False),
    ):
        items = read_json(LOOK_OUT / "ground" / inst_file)["instances"]
        n = place_hism(actors, s[key], items, label, cull, shadow, uniform_key="s")
        ground_counts[key] = n
        if n != len(items):
            failures.append({key: "instance count %d != %d" % (n, len(items))})
    tree_count = ground_counts["tree"]

    # rooftop clutter: one HISM per prop type. Rooftop rooms / bulkheads carry the aerial read (medium-
    # scale massing + sheet colour patches) and stay to 4.5 km; small clutter fades out much earlier.
    roof_doc = read_json(LOOK_OUT / "rooftops/rooftop_instances.json")
    roof_inst = roof_doc["types"]
    roof_variants = int(roof_doc.get("variants", 4))
    roof_cull = {"ac": (60000.0, 90000.0), "antenna": (60000.0, 90000.0),
                 "addition": (350000.0, 450000.0), "barrel": (350000.0, 450000.0), "shed": (350000.0, 450000.0),
                 "leanto": (200000.0, 260000.0), "bulkhead": (300000.0, 400000.0)}
    roof_counts = {}
    for t, row in assets["rooftop_props"].items():
        items = roof_inst.get(t, [])
        if not items:
            continue
        small = t in ("ac", "antenna", "avlight")
        n = place_hism(actors, row, items, "Roof_" + t, roof_cull.get(t, (120000.0, 200000.0)), not small,
                       variants=roof_variants)
        roof_counts[t] = n
        if n != len(items):
            failures.append({"rooftop": t, "count": n, "expected": len(items)})

    # Street identity v0B: projecting signs + awnings on baked commercial frontage (one HISM per type)
    street_counts = {}
    street_doc = LOOK_OUT / "street/street_instances.json"
    if assets.get("street_props") and street_doc.is_file():
        sdoc = read_json(street_doc)
        mesh_of = {u: row for row in assets["street_props"].values() for u in row["used_by"]}
        for t, (cull, shadow) in STREET_HISM.items():
            items = sdoc["types"].get(t, [])
            if not items:
                continue
            n = place_hism(actors, mesh_of[t], items, "Street_" + t, cull, shadow, variants=sdoc["variants"][t])
            street_counts[t] = n
            if n != len(items):
                failures.append({"street": t, "count": n, "expected": len(items)})

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
    # Cloud Prototype v0: actor + HIGH material saved, but OFF (hidden, no cloud shadows) so the accepted
    # city look is cloud-independent; captures opt in with ACW_XINYI_LOOK_CLOUDS=low|high.
    clouds = None
    if spawn_clouds(actors) is not None:
        clouds = apply_clouds(world, actors, "off", "day")

    # School & Campus Identity v0A court markings: low-flight detail; beyond ~0.9 km the courts read from
    # the ground colour.
    cp_mesh = lib.load_asset(s["campus_paint"]["asset_path"])
    cpaint, _ = spawn_mesh_actor(actors, cp_mesh, [0.0, 0.0, 0.0], s["campus_paint"]["expected_bounds_origin_cm"],
                                 "CampusPaint")
    cpc = cpaint.get_component_by_class(unreal.StaticMeshComponent)
    cpc.set_cast_shadow(False)
    cpc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    cpc.set_editor_property("ld_max_draw_distance", 90000.0)

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
        "ground_instances": ground_counts,
        "rooftop_instances": roof_counts,
        "street_instances": street_counts,
        "far_city_chunks": far_n,
        "clouds": clouds,
        "failures": failures,
        "contract_level_saved": False,
    }
    write_report("look_level.report.json", report)
    if status != "PASS_LOOK_LEVEL":
        raise RuntimeError("XinyiLook level stage failed: %s" % json.dumps(failures)[:2000])


main()
