"""相思樹 lookdev v1 (UnrealEditor-Cmd): distance look of the thin-phyllode atlas - changes ONLY the 相思樹 leaf material / atlas.

Why: in the first native lineups (a1 / a2) the 相思樹 cards read as hard "confetti" blobs at 60 m and as a thin speckle from the air, with
either LOD chain. The atlas tiles hold thin 6-9 mm blades (4-15 % coverage); at 60 m a card is ~20 px, so the 512 px tile is sampled at
mip 4-5 and "scale mips for alpha coverage" turns the blades into a few opaque blobs. The 紅楠 atlas (broad leaves) does not have this.
Knobs (env), each recorded in the receipt:
* ACW_AC_DITHER=1|0: M_TL_Acacia_LeafCards.dither_opacity_mask (masked + TAA -> fractional coverage resolves as soft partial cover);
* ACW_AC_ALPHA_COV=<threshold>|off: T_Acacia_LeafAtlas_BC alpha-coverage mip scaling (off = true average alpha in the mips);
* ACW_AC_CLIP=<value>: opacity mask clip value.
The ISM usage flag is re-asserted and the material saved (hf_verify.py re-checks it in a fresh process). Receipt: reports/ac_tune.report.json.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import MAT_DIR, TEX_DIR, lib, mel, write_report  # noqa: E402

rep = {"status": "FAIL_AC_TUNE", "error": None}
try:
    mpath, tpath = MAT_DIR + "/M_TL_Acacia_LeafCards", TEX_DIR + "/T_Acacia_LeafAtlas_BC"
    mat, tex = lib.load_asset(mpath), lib.load_asset(tpath)
    if mat is None or tex is None:
        raise RuntimeError("acacia leaf material / atlas missing")
    before = {"dither_opacity_mask": bool(mat.get_editor_property("dither_opacity_mask")),
              "opacity_mask_clip_value": float(mat.get_editor_property("opacity_mask_clip_value")),
              "do_scale_mips_for_alpha_coverage": bool(tex.get_editor_property("do_scale_mips_for_alpha_coverage"))}
    cov = os.environ.get("ACW_AC_ALPHA_COV")
    if cov is not None:
        if cov == "off":
            tex.set_editor_property("do_scale_mips_for_alpha_coverage", False)
        else:
            tex.set_editor_property("do_scale_mips_for_alpha_coverage", True)
            tex.set_editor_property("alpha_coverage_thresholds", unreal.Vector4(0.0, 0.0, 0.0, float(cov)))
        if not lib.save_asset(tpath, only_if_is_dirty=False):
            raise RuntimeError("save " + tpath)
    if os.environ.get("ACW_AC_DITHER") is not None:
        mat.set_editor_property("dither_opacity_mask", os.environ["ACW_AC_DITHER"] == "1")
    if os.environ.get("ACW_AC_CLIP") is not None:
        mat.set_editor_property("opacity_mask_clip_value", float(os.environ["ACW_AC_CLIP"]))
    mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    mel.recompile_material(mat)
    if not lib.save_asset(mpath, only_if_is_dirty=False):
        raise RuntimeError("save " + mpath)
    rep["before"] = before
    rep["after"] = {"dither_opacity_mask": bool(mat.get_editor_property("dither_opacity_mask")),
                    "opacity_mask_clip_value": float(mat.get_editor_property("opacity_mask_clip_value")),
                    "do_scale_mips_for_alpha_coverage": bool(tex.get_editor_property("do_scale_mips_for_alpha_coverage")),
                    "alpha_coverage_threshold_a": float(tex.get_editor_property("alpha_coverage_thresholds").w),
                    "used_with_instanced_static_meshes": bool(mat.get_editor_property("used_with_instanced_static_meshes"))}
    rep["status"] = "PASS_AC_TUNE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("ac_tune.report.json", rep)
unreal.SystemLibrary.quit_editor()
