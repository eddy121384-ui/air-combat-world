"""Forest performance: coverage-preserving thinning (UnrealEditor-Cmd, with RHI).

Rewrites the "NF clump" Custom node (World Position Offset; nf_trees_dl.py + nf_trees_vanish.py) of the six M_NF_* tree materials:
  x = saturate((d - NearFull) / (ThinEnd - NearFull)),  f = 1 - x^(1/ThinGamma)   = fraction of trees still drawn at distance d
  every survivor widens by 1/sqrt(f) (capped at ClumpGain + 1), height by a third of that, around its own pivot
so the canopy cover (trees x crown area) stays constant while the number of trees - and the stacked masked-card overdraw that dominates the
GPU cost on the base / depth / shadow passes - falls with distance. Trees past their own vanish distance still collapse onto the pivot
(no raster work). The pixel keep mask (nf_assets.py) is unchanged, so near trees (< NearFull) are exactly the PR #49 trees.
Receipt: reports/nf_trees_cover.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import FORM_BARK_SRC, FORM_LEAF_SRC, MAT, lib, mel, write_report  # noqa: E402

HLSL = """float x = saturate((D - Near) / max(End - Near, 1.0));
float f = 1.0 - pow(x, 1.0 / max(Gamma, 0.05));
float g = min(rsqrt(max(f, 0.05)) - 1.0, CG);
float T = Near + (End - Near) * pow(saturate(R), Gamma);
if (D > T + Width + 3000.0) { return -LP; }
return LP * float3(g, g, 0.33 * g);"""
# ACW_NF_CLUMP_MODE=linear restores the PR #49 clump formula (g = ClumpGain * x) while keeping the vanish collapse; measured: the
# coverage-preserving variant cost MORE (fixed-step flight 368 vs 349 ms, shadow depths 23 -> 41 ms) because widened survivors bring back
# the masked-card area the thinning removed.
HLSL_LINEAR = """float g = CG * saturate((D - Near) / max(End - Near, 1.0));
float T = Near + (End - Near) * pow(saturate(R), Gamma);
if (D > T + Width + 3000.0) { return -LP; }
return LP * float3(g, g, 0.35 * g);"""
if os.environ.get("ACW_NF_CLUMP_MODE") == "linear":
    HLSL = HLSL_LINEAR
rep = {"status": "FAIL_NF_TREES_COVER", "materials": {}, "error": None, "mode": os.environ.get("ACW_NF_CLUMP_MODE", "cover")}
try:
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        tr = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
        cu = mel.get_inputs_for_material_expression(mat, tr)[0]
        names = [str(i.get_editor_property("input_name")) for i in cu.get_editor_property("inputs")]
        if "R" not in names:
            raise RuntimeError("run nf_trees_vanish.py first: " + path)
        cu.set_editor_property("code", HLSL)
        mat.set_editor_property("max_world_position_offset_displacement", float(os.environ.get("ACW_NF_MAXWPO_CM", "1200")))   # bounds growth: every extra metre lets more trees into frustum / shadow culling
        mel.recompile_material(mat)
        lib.save_asset(path, only_if_is_dirty=False)
        rep["materials"][path] = "coverage_preserving"
    rep["status"] = "PASS_NF_TREES_COVER"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_trees_cover.report.json", rep)
unreal.SystemLibrary.quit_editor()
