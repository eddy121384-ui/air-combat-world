"""North Taiwan forest world v1, town massing stage (UnrealEditor-Cmd -nullrhi): building boxes into L_NF_Yangmingshan.

One actor per 1 km tile (buildings/*.bin from build_buildings.py) with one HISM of the engine 1 m cube; NOT spatially loaded (75k
instances ~ a few MB, so towns stay visible to the horizon instead of popping at the 3.2 km World Partition range), end cull 9 km,
shadows on, no collision. M_NF_Building: per-instance wall tone (grey / beige / dark tile), floor-band windows from world height,
roofs from the vertex normal. Receipt: reports/nf_buildings.report.json.
"""
import array
import json
import os
import struct
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, MAP, MAT, RUN, find_actor, lib, link, mel, tools, write_report  # noqa: E402

LEVEL = MAP + "/L_NF_Yangmingshan"
END_CULL_CM = 900000
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rep = {"status": "FAIL_NF_BUILDINGS", "error": None}
HLSL = """float r2 = frac(R * 7.31), r3 = frac(R * 13.7), r4 = frac(R * 29.1);
float3 wall = lerp(float3(0.12, 0.12, 0.115), float3(0.21, 0.20, 0.185), R);
wall = (r2 > 0.62) ? lerp(float3(0.19, 0.16, 0.12), float3(0.25, 0.21, 0.16), r4) : wall;   // beige / brown tile
wall = (r2 > 0.90) ? float3(0.28, 0.28, 0.27) : wall;                                        // newer white tile
wall = (r2 < 0.10) ? float3(0.075, 0.075, 0.075) : wall;                                     // dark / weathered
float fl = frac(Z / 320.0);
float win = (fl > 0.38 && fl < 0.80) ? 1.0 : 0.0;
float3 c = lerp(wall, float3(0.035, 0.042, 0.05), win * 0.65);
float3 roof = lerp(float3(0.10, 0.10, 0.095), float3(0.17, 0.16, 0.15), r4);                  // concrete roof slab
roof = (r3 > 0.50 && r3 < 0.70) ? float3(0.045, 0.085, 0.14) : roof;                         // blue metal sheet (tie-pi)
roof = (r3 >= 0.70 && r3 < 0.82) ? float3(0.045, 0.105, 0.095) : roof;                       // teal metal sheet
roof = (r3 >= 0.82 && r3 < 0.93) ? float3(0.14, 0.065, 0.04) : roof;                          // rust / red
return ((NZ > 0.7) ? roof : c) * Scale;"""
MAT_NAME = "M_NF_Building_R" + os.environ.get("ACW_NF_BLD_REV", "1")
MAT_ONLY = os.environ.get("ACW_NF_BLD_MAT_ONLY") == "1"   # re-material the existing building actors only


def material():
    path = MAT + "/" + MAT_NAME
    if lib.does_asset_exist(path):
        return lib.load_asset(path)
    mat = tools.create_asset(MAT_NAME, MAT, unreal.Material, unreal.MaterialFactoryNew())
    ins = []
    for n in ("R", "Z", "NZ", "Scale"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c = E(mat, unreal.MaterialExpressionCustom, -500, 0, code=HLSL, inputs=ins, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    link(E(mat, unreal.MaterialExpressionPerInstanceRandom, -900, -100), "", c, "R")
    wp = E(mat, unreal.MaterialExpressionWorldPosition, -1100, 50)
    z = E(mat, unreal.MaterialExpressionComponentMask, -900, 50, r=False, g=False, b=True, a=False)
    link(wp, "", z, "")
    link(z, "", c, "Z")
    vn = E(mat, unreal.MaterialExpressionVertexNormalWS, -1100, 200)
    nz = E(mat, unreal.MaterialExpressionComponentMask, -900, 200, r=False, g=False, b=True, a=False)
    link(vn, "", nz, "")
    link(nz, "", c, "NZ")
    # albedo scale: the scene's albedo calibration is set by the game-tree materials (leaf base colour ~1/3 of a real canopy), so
    # building / paving albedos are scaled by the same factor or towns blow out against the forest
    link(E(mat, unreal.MaterialExpressionScalarParameter, -900, 320, parameter_name="AlbedoScale",
           default_value=float(os.environ.get("ACW_NF_BLD_ALBEDO", "0.5"))), "", c, "Scale")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant, -500, 200, r=0.75), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mat.set_editor_property("used_with_instanced_static_meshes", True)
    mel.recompile_material(mat)
    lib.save_asset(path, only_if_is_dirty=False)
    rep["material_ism_flag"] = bool(lib.load_asset(path).get_editor_property("used_with_instanced_static_meshes"))
    if not rep["material_ism_flag"]:
        raise RuntimeError("ISM usage flag did not stick on " + path)
    return mat


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


try:
    idx = json.loads((RUN / "buildings.json").read_text(encoding="utf-8"))
    mat = material()
    if not les.load_level(LEVEL):
        raise RuntimeError("load")
    if MAT_ONLY:
        n = 0
        for a in ues.get_all_level_actors():
            if a.get_actor_label().startswith("NF_Bld_"):
                a.modify()   # World Partition external actor package must be dirtied, or the change is never saved
                for h in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
                    h.modify()
                    h.set_material(0, mat)
                    n += 1
        dirty = [p.get_name() for p in list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()) + list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())]
        rep["dirty_packages"] = len(dirty)
        if n != len(idx["tiles"]) or len(dirty) < n or not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
            raise RuntimeError("re-material %d / %d, dirty %d" % (n, len(idx["tiles"]), len(dirty)))
        rep.update(status="PASS_NF_BUILDINGS", material=MAT_NAME, rematerialed=n)
        write_report("nf_buildings_mat.report.json", rep)
        unreal.SystemLibrary.quit_editor()
        raise SystemExit
    if find_actor("NF_Bld_%02d_%02d" % (idx["tiles"][0]["tx"], idx["tiles"][0]["ty"])) is not None:
        raise RuntimeError("buildings already in the map")
    cube = lib.load_asset("/Engine/BasicShapes/Cube")
    total = 0
    for t in idx["tiles"]:
        cx, cy = t["center_ue_cm"]
        a = ues.spawn_actor_from_class(unreal.Actor, unreal.Vector(cx, cy, 0.0))
        a.set_actor_label("NF_Bld_%02d_%02d" % (t["tx"], t["ty"]))
        a.set_folder_path(unreal.Name("NF_Buildings"))
        a.set_editor_property("is_spatially_loaded", False)
        h = add_hism(a, cube)
        h.set_material(0, mat)
        h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        h.set_cull_distances(0, END_CULL_CM)
        buf = (RUN / "buildings" / t["file"]).read_bytes()
        (n,) = struct.unpack_from("<I", buf, 0)
        rec = array.array("d")
        rec.frombytes(buf[4:4 + n * 7 * 8])
        xf = [unreal.Transform(unreal.Vector(rec[i * 7], rec[i * 7 + 1], rec[i * 7 + 2]), unreal.Rotator(0, 0, rec[i * 7 + 3]),
                               unreal.Vector(rec[i * 7 + 4], rec[i * 7 + 5], rec[i * 7 + 6])) for i in range(n)]
        h.add_instances(xf, False, True)
        total += h.get_instance_count()
    rep["boxes"], rep["expected"], rep["tiles"] = total, idx["stats"]["boxes"], len(idx["tiles"])
    if total != idx["stats"]["boxes"]:
        raise RuntimeError("count mismatch")
    if not les.save_current_level():
        raise RuntimeError("save")
    rep["status"] = "PASS_NF_BUILDINGS"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_buildings.report.json", rep)
unreal.SystemLibrary.quit_editor()
