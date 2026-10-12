"""ForestSpike instance pool + HISM placement helpers (UE5.8 editor Python), shared by the level and capture stages."""
import array

import unreal
from fs_common import INPUTS, enu_to_ue_cm, read_json

ARCHETYPES = ["dense_rounded", "horizontal_tiered", "open_vase", "tall_columnar"]


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


def load_pool():
    meta = read_json(INPUTS / "pool.json")
    a = array.array("f")
    with open(str(INPUTS / "pool.f32"), "rb") as fh:
        a.frombytes(fh.read())
    cols = len(meta["columns"])
    if len(a) != meta["count"] * cols:
        raise RuntimeError("pool size mismatch")
    return a, meta["count"], cols


def pivot_shift(row):
    """expected - imported local bounds origin (cm), from the assets report (same rule as the accepted adapters)."""
    return [row["expected_bounds_origin_cm"][i] - row["imported_bounds_origin_cm"][i] for i in range(3)]


def place(h, pool, cols, idx, shift):
    """Replace all instances of HISM h with pool entries idx (first-n-by-rank placement keeps runs nested)."""
    xf = []
    cd = []
    for i in idx:
        o = i * cols
        e, n, z, yaw, sc, var, col, u = pool[o:o + 8]
        p = enu_to_ue_cm(e, n, z - 0.15)     # sink the trunk base 0.15 m: the terrain mesh is piecewise linear
        xf.append(unreal.Transform(
            unreal.Vector(p.x + shift[0] * sc, p.y + shift[1] * sc, p.z + shift[2] * sc),
            unreal.Rotator(0.0, 0.0, -float(yaw)), unreal.Vector(sc, sc, sc)))
        cd.append(((col + 0.5) / 4.0, u))
    h.clear_instances()
    h.set_num_custom_data_floats(2)
    if xf:
        h.add_instances(xf, False, True)
        for k, (c0, c1) in enumerate(cd):
            h.set_custom_data_value(k, 0, c0, False)
            h.set_custom_data_value(k, 1, c1, False)
    return len(xf)
