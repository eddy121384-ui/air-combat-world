"""Forest performance: collapse vanished trees in the vertex shader (UnrealEditor-Cmd, with RHI).

Each tree i dissolves at its own distance T_i = Near + (End - Near) * rand_i^Gamma (pixel keep mask, nf_assets.py). Past
T_i + FadeWidth every pixel of that tree is discarded - but its triangles were still rasterised and its pixel shader still ran (base pass,
depth pre-pass and every shadow cascade), for every instance out to the HISM end cull. With the PR #49 4 km tail ~90 % of the trees
at 3 km are invisible but paid for.

This stage rewrites the existing "NF clump" Custom node (World Position Offset, nf_trees_dl.py) of the six M_NF_* tree materials so the
same expression also returns -LocalPosition for a vanished tree: every vertex collapses onto the pivot, the triangles are degenerate and
never reach the rasteriser. Visible trees are untouched (same keep threshold + a 30 m margin), so the image does not change.
Receipt: reports/nf_trees_vanish.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, FORM_BARK_SRC, FORM_LEAF_SRC, MAT, lib, link, mel, write_report  # noqa: E402

HLSL = """float g = CG * saturate((D - Near) / max(End - Near, 1.0));
float T = Near + (End - Near) * pow(saturate(R), Gamma);
if (D > T + Width + 3000.0) { return -LP; }
return LP * float3(g, g, 0.35 * g);"""
rep = {"status": "FAIL_NF_TREES_VANISH", "materials": {}, "error": None}
try:
    coll = lib.load_asset(MAT + "/MPC_NF_Forest")
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        tr = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
        if tr is None:
            raise RuntimeError("no WPO on " + path + " (run nf_trees_dl.py first)")
        cu = mel.get_inputs_for_material_expression(mat, tr)[0]
        if cu is None or cu.get_class().get_name() != "MaterialExpressionCustom":
            raise RuntimeError("WPO input is not the NF clump Custom node on " + path)
        names = [str(i.get_editor_property("input_name")) for i in cu.get_editor_property("inputs")]
        if "R" not in names:
            ins = list(cu.get_editor_property("inputs"))
            for n in ("R", "Gamma", "Width"):
                ci = unreal.CustomInput()
                ci.set_editor_property("input_name", n)
                ins.append(ci)
            cu.set_editor_property("inputs", ins)
            cu.set_editor_property("code", HLSL)
            link(E(mat, unreal.MaterialExpressionPerInstanceRandom, -1000, 2200), "", cu, "R")
            link(E(mat, unreal.MaterialExpressionCollectionParameter, -1000, 2270, collection=coll, parameter_name="ThinGamma"), "", cu, "Gamma")
            link(E(mat, unreal.MaterialExpressionCollectionParameter, -1000, 2340, collection=coll, parameter_name="FadeWidth"), "", cu, "Width")
            mel.recompile_material(mat)
            lib.save_asset(path, only_if_is_dirty=False)
            rep["materials"][path] = "vanish_collapse_added"
        else:
            rep["materials"][path] = "already"
    rep["status"] = "PASS_NF_TREES_VANISH"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_trees_vanish.report.json", rep)
unreal.SystemLibrary.quit_editor()
