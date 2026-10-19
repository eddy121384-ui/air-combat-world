"""Distance-layer tree tiering (UnrealEditor-Cmd, with RHI): "0-1.5 km = trees, 1.5-4 km = trees becoming crown clusters".

1. MPC_NF_Forest: preset "dl" (full density to 1.0 km, per-tree vanish distances out to 4.0 km with a long sparse tail, gamma 2.2;
   canopy shell / canopy colour 1.2 -> 3.0 km) + new scalar ClumpGain.
2. The six M_NF_* tree materials (duplicates of the accepted species materials; the M_TL_* originals stay untouched) get a World
   Position Offset that widens each surviving tree around its own pivot as it recedes: local position * (g, g, 0.35 g),
   g = ClumpGain * saturate((d - NearFull) / (ThinEnd - NearFull)); the thinned-out mid distance therefore keeps canopy cover as
   fewer, broader crown clusters instead of a sprinkle of single trees. max_world_position_offset_displacement grows the bounds.
3. Every tree tile HISM: end cull 2.6 -> 4.3 km (actors loaded through WorldPartitionBlueprintLibrary, modified, dirty map packages
   saved); runtime grid loading range 3.2 -> 4.6 km so tiles exist where the trees are still drawn.
Receipt: reports/nf_trees_dl.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import json  # noqa: E402

import unreal  # noqa: E402
from nf_common import E, FORM_BARK_SRC, FORM_LEAF_SRC, MAP, MAT, find_actor, lib, link, mel, write_report  # noqa: E402

PRESET = {"NearFull": 100000.0, "ThinEnd": 400000.0, "FadeWidth": 15000.0, "ThinGamma": 2.2, "ShellStart": 120000.0, "ShellEnd": 300000.0,
          "ShellScale": 0.8, "ClumpGain": float(os.environ.get("ACW_NF_CLUMP_GAIN", "0.7"))}
END_CULL_CM = 430000
RANGE_CM = 460000
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rep = {"status": "FAIL_NF_TREES_DL", "preset": PRESET, "error": None}
CLUMP_HLSL = """float g = CG * saturate((D - Near) / max(End - Near, 1.0));
return LP * float3(g, g, 0.35 * g);"""


def mpc():
    c = lib.load_asset(MAT + "/MPC_NF_Forest")
    params = list(c.get_editor_property("scalar_parameters"))
    have = {str(p.get_editor_property("parameter_name")) for p in params}
    if "ClumpGain" not in have:
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", "ClumpGain")
        params.append(p)
    for p in params:
        nm = str(p.get_editor_property("parameter_name"))
        if nm in PRESET:
            p.set_editor_property("default_value", PRESET[nm])
    c.set_editor_property("scalar_parameters", params)
    lib.save_asset(MAT + "/MPC_NF_Forest", only_if_is_dirty=False)
    return lib.load_asset(MAT + "/MPC_NF_Forest")


def clump_wpo(coll):
    out = {}
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        if mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET) is not None:
            out[path] = "already"
            continue
        ins = []
        for n in ("LP", "D", "Near", "End", "CG"):
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", n)
            ins.append(ci)
        cu = E(mat, unreal.MaterialExpressionCustom, -700, 1800, code=CLUMP_HLSL, inputs=ins,
               output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="NF clump")
        link(E(mat, unreal.MaterialExpressionLocalPosition, -1000, 1700), "", cu, "LP")
        d = E(mat, unreal.MaterialExpressionDistance, -1000, 1800)
        link(E(mat, unreal.MaterialExpressionWorldPosition, -1250, 1780), "", d, "A")
        link(E(mat, unreal.MaterialExpressionCameraPositionWS, -1250, 1860), "", d, "B")
        link(d, "", cu, "D")
        for i, (pin, nm) in enumerate((("Near", "NearFull"), ("End", "ThinEnd"), ("CG", "ClumpGain"))):
            link(E(mat, unreal.MaterialExpressionCollectionParameter, -1000, 1950 + 70 * i, collection=coll, parameter_name=nm), "", cu, pin)
        tr = E(mat, unreal.MaterialExpressionTransform, -400, 1800)
        tr.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL)
        tr.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
        link(cu, "", tr, "")
        mel.connect_material_property(tr, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
        try:
            mat.set_editor_property("max_world_position_offset_displacement", 900.0)
        except Exception as exc:  # noqa: BLE001
            rep.setdefault("warnings", []).append("max WPO displacement: %s" % exc)
        mel.recompile_material(mat)
        lib.save_asset(path, only_if_is_dirty=False)
        out[path] = "wpo_added"
    return out


def tiles():
    wpl = unreal.WorldPartitionBlueprintLibrary
    descs = wpl.get_actor_descs()
    guids = [d.get_editor_property("guid") for d in descs if str(d.get_editor_property("label")).startswith("NF_Trees_")]
    rep["tree_actor_descs"] = len(guids)
    rep["load_actors_returned"] = bool(wpl.load_actors(guids))   # returns False in UE 5.8 even when actors load; count below
    n = 0
    for a in ues.get_all_level_actors():
        if a.get_actor_label().startswith("NF_Trees_"):
            a.modify()
            for h in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
                h.modify()
                h.set_cull_distances(0, END_CULL_CM)
                n += 1
    rep["hism_recull"] = n
    rep["grid"] = json.loads(unreal.NtwGateLibrary.configure_runtime_grid(100000, RANGE_CM))
    dirty = list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()) + list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    rep["dirty_packages"] = len(dirty)
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save dirty packages")


try:
    coll = mpc()
    rep["mpc"] = {str(p.get_editor_property("parameter_name")): p.get_editor_property("default_value") for p in coll.get_editor_property("scalar_parameters")}
    rep["materials"] = clump_wpo(coll)
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    tiles()
    rep["status"] = "PASS_NF_TREES_DL" if rep["hism_recull"] == 4454 else "FAIL_NF_TREES_DL"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_trees_dl.report.json", rep)
unreal.SystemLibrary.quit_editor()
