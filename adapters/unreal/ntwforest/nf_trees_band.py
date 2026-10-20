"""Forest performance: rank-banded HISM culling (UnrealEditor-Cmd, with RHI).

Measured (tools/ntw/forest_world/run_ab.ps1, fixed-step UHD 770): PR #49's cost is dominated by the 2.6 -> 4.3 km ring, although
80-90 % of the trees there have already dissolved - a HISM component can only cull at ONE distance, so every tree out to 4.3 km is
submitted and vertex-shaded (the per-tree vanish distance lives in the material).

Fix, with no change to what is drawn:
1. Every tree gets its own vanish rank r (deterministic per tile / group / index) as per-instance custom data 0. The tree materials read
   r from PerInstanceCustomData instead of PerInstanceRandom, in both the pixel keep mask and the vertex WPO (clump / vanish collapse).
2. Each tile's trees are split into rank bands; a band's HISM end cull = vanish distance of its highest rank + FadeWidth + 100 m, from
   the MPC curve T(r) = NearFull + (ThinEnd - NearFull) * r^ThinGamma. A tree is therefore only submitted where it can still be visible.
Bands (rank edges) 0-0.30 / 0.30-0.55 / 0.55-0.78 / 0.78-1: with the PR #49 curve, culls 1.46 / 2.05 / 2.99 / 4.25 km.
Receipt: reports/nf_trees_band.report.json.
"""
import array
import json
import math
import os
import random
import struct
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, FORM_BARK_SRC, FORM_LEAF_SRC, FORM_MESH, MAP, MAT, RUN, VARIANT_FORM, lib, link, mel, write_report  # noqa: E402

EDGES = [0.0, 0.30, 0.55, 0.78, 1.0]
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
rep = {"status": "FAIL_NF_TREES_BAND", "materials": {}, "error": None}


def custom_nodes(mat):
    """(keep Custom node of the opacity mask, clump Custom node of the WPO)."""
    op = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_OPACITY_MASK)
    keep = op if op.get_class().get_name() == "MaterialExpressionCustom" else \
        next(n for n in mel.get_inputs_for_material_expression(mat, op) if n is not None and n.get_class().get_name() == "MaterialExpressionCustom")
    tr = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    clump = mel.get_inputs_for_material_expression(mat, tr)[0]
    return keep, clump


def materials():
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        keep, clump = custom_nodes(mat)
        for i, node in enumerate((keep, clump)):
            cd = E(mat, unreal.MaterialExpressionPerInstanceCustomData, -1300, 2500 + 100 * i, data_index=0)
            try:
                cd.set_editor_property("const_default_value", 1.0)   # no custom data -> rank 1 (tree lives to ThinEnd)
            except Exception as exc:  # noqa: BLE001
                rep.setdefault("warnings", []).append("const_default_value: %s" % exc)
            link(cd, "", node, "R")
        mel.recompile_material(mat)
        lib.save_asset(path, only_if_is_dirty=False)
        rep["materials"][path] = "rank_from_custom_data"


def mpc():
    c = lib.load_asset(MAT + "/MPC_NF_Forest")
    return {str(p.get_editor_property("parameter_name")): p.get_editor_property("default_value") for p in c.get_editor_property("scalar_parameters")}


def read_tile(path):
    buf = open(path, "rb").read()
    (ng,), off, groups = struct.unpack_from("<I", buf, 0), 4, []
    for _ in range(ng):
        form, var, n = struct.unpack_from("<cHI", buf, off)
        off += 7
        rec = array.array("d")
        rec.frombytes(buf[off:off + n * 9 * 8])
        off += n * 9 * 8
        groups.append((form.decode(), var, n, rec))
    return groups


def add_hism(actor, mesh):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    params = unreal.AddNewSubobjectParams()
    params.set_editor_property("parent_handle", sds.k2_gather_subobject_data_for_instance(actor)[0])
    params.set_editor_property("new_class", unreal.HierarchicalInstancedStaticMeshComponent)
    h, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("add_new_subobject failed")
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(unreal.SubobjectDataBlueprintFunctionLibrary.get_data(h))
    comp.set_static_mesh(mesh)
    return comp


def rebuild(m):
    near, end, gam, fw = m["NearFull"], m["ThinEnd"], m["ThinGamma"], m["FadeWidth"]
    culls = [int(near + (end - near) * EDGES[b + 1] ** gam + fw + 10000) for b in range(len(EDGES) - 1)]
    rep["band_culls_cm"] = culls
    wpl = unreal.WorldPartitionBlueprintLibrary
    wpl.load_actors([d.get_editor_property("guid") for d in wpl.get_actor_descs() if str(d.get_editor_property("label")).startswith("NF_Trees_")])
    idx = json.loads((RUN / "trees.json").read_text(encoding="utf-8"))
    by_label = {a.get_actor_label(): a for a in ues.get_all_level_actors() if a.get_actor_label().startswith("NF_Trees_")}
    meshes = {f: lib.load_asset(p) for f, p in FORM_MESH.items()}
    barks = {f: lib.load_asset(MAT + "/" + s.replace("M_TL_", "M_NF_")) for f, s in FORM_BARK_SRC.items()}
    leaves = {v: lib.load_asset(MAT + "/MI_NF_Leaf_V%d" % v) for v in VARIANT_FORM}
    total, comps = 0, 0
    per_band = [0] * (len(EDGES) - 1)
    for t in idx["tiles"]:
        a = by_label["NF_Trees_%02d_%02d" % (t["tx"], t["ty"])]
        a.modify()
        old = list(a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent))
        for gi, (form, var, n, rec) in enumerate(read_tile(RUN / "trees" / t["file"])):
            rng = random.Random("%s/%d/%s%d" % (t["file"], gi, form, var))
            ranks = [rng.random() for _ in range(n)]
            for b in range(len(EDGES) - 1):
                sel = [i for i in range(n) if EDGES[b] <= ranks[i] < EDGES[b + 1] or (b == len(EDGES) - 2 and ranks[i] == 1.0)]
                if not sel:
                    continue
                h = old.pop() if old else add_hism(a, meshes[form])
                h.modify()
                h.clear_instances()
                h.set_static_mesh(meshes[form])
                h.set_material(0, barks[form])
                h.set_material(1, leaves[var])
                h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
                h.set_cast_shadow(True)
                h.set_cull_distances(0, culls[b])
                h.set_num_custom_data_floats(1)
                xf = []
                for i in sel:
                    x, y, z, yaw, sx, sy, sz, le, ln = rec[i * 9:(i + 1) * 9]
                    z_up = unreal.Vector(math.tan(math.radians(le)), -math.tan(math.radians(ln)), 1.0)
                    yr = math.radians(yaw)
                    rot = unreal.MathLibrary.make_rot_from_zx(z_up, unreal.Vector(math.cos(yr), math.sin(yr), 0.0))
                    xf.append(unreal.Transform(unreal.Vector(x, y, z), rot, unreal.Vector(sx, sy, sz)))
                h.add_instances(xf, False, True)
                for k, i in enumerate(sel):
                    h.set_custom_data_value(k, 0, ranks[i], False)
                total += len(sel)
                per_band[b] += len(sel)
                comps += 1
        for h in old:   # leftover components (should not happen: every tile has >= as many band groups as before)
            h.modify()
            h.clear_instances()
    rep.update(instances=total, components=comps, per_band=per_band)
    if total != 3859205:
        raise RuntimeError("instance total %d" % total)
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save")


try:
    materials()
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    rep["mpc"] = mpc()
    rebuild(rep["mpc"])
    rep["status"] = "PASS_NF_TREES_BAND"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_trees_band.report.json", rep)
unreal.SystemLibrary.quit_editor()
