"""Shared pieces of the tree-budget experiment (candidates A/B/C, same-tree HISM patch). Isolated project unreal/TreeLookdev only."""
from __future__ import annotations

import random

import unreal

from tl_common import MESH_DIR, ROOT, find_actor, lib

BUDGET = ROOT + "/Budget"
PATH = {"A": MESH_DIR + "/Machilus/machilus_lod0/StaticMeshes/machilus_lod0",
        "B": BUDGET + "/B/machilus_budget_lod0/StaticMeshes/machilus_budget_lod0",
        "C": BUDGET + "/C/machilus_budget_lod0/StaticMeshes/machilus_budget_lod0",
        "D": BUDGET + "/D/machilus_balanced_lod0/StaticMeshes/machilus_balanced_lod0"}


def add_hism(actor, mesh):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams()
    params.set_editor_property("parent_handle", handles[0])
    params.set_editor_property("new_class", unreal.HierarchicalInstancedStaticMeshComponent)
    new_handle, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("add_new_subobject failed: %s" % fail)
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(unreal.SubobjectDataBlueprintFunctionLibrary.get_data(new_handle))
    comp.set_static_mesh(mesh)
    return comp


def patch_transforms():
    """10 x 10, 25 m grid with the origin on a grid point; instance 0 = identity at the origin (the look-dev tree)."""
    rng = random.Random(20261015)
    xf = [unreal.Transform(unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1))]
    for i in range(-5, 5):
        for j in range(-5, 5):
            if i == 0 and j == 0:
                continue
            x, y = 25.0 * i + rng.uniform(-4, 4), 25.0 * j + rng.uniform(-4, 4)
            s = rng.uniform(0.85, 1.15)
            xf.append(unreal.Transform(unreal.Vector(x * 100, y * 100, 0), unreal.Rotator(0, 0, rng.uniform(0, 360)), unreal.Vector(s, s, s)))
    return xf


def make_patch(actors, mesh, label):
    holder = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    holder.set_actor_label(label)
    h = add_hism(holder, mesh)
    h.add_instances(patch_transforms(), False, True)
    h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    h.set_cast_shadow(True)
    return h


def setup_tree(actors, mode, key):
    """On the loaded look-dev level: swap the tree mesh (single) or replace it with a HISM patch (patch)."""
    mesh = lib.load_asset(PATH[key])
    tree = find_actor(actors, "TL_Machilus")
    if mode == "single":
        tree.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(mesh)
        return
    actors.destroy_actor(tree)
    make_patch(actors, mesh, "TL_Machilus_Patch")
