"""North Taiwan forest - MOBILE FOREST PROFILE (UnrealEditor-Cmd, with RHI): one forest, two renderer profiles.

The PC forest (PR #46-#52) is untouched; the mobile profile is selected by the RENDERER, not by a second forest:
1. MPC_NF_Forest gains mobile twins of the distance numbers (NearFullM, ThinEndM, FadeWidthM, ThinGammaM, ShellStartM, ShellEndM,
   ClumpGainM) plus RankKeepM (share of the trees a phone keeps), CrownGainM (crown growth of the kept trees near the camera) and
   NearCanopyM (baked canopy colour under the near trees, read by the Landscape material: nf_landscape_dl.py ACW_NF_DL_MOBILE=1).
2. The tree materials' two Custom nodes (pixel keep mask, vertex clump / vanish collapse) read the twins under
   `#if SHADING_PATH_MOBILE` - the ES3.1 / Vulkan / Metal mobile renderer (and the PC ES3.1 preview) compiles the mobile numbers, the
   desktop renderer the PC numbers. On mobile the rank is remapped r' = r / RankKeepM so the kept trees still spread over the whole
   thinning range (otherwise every kept tree would dissolve in the first quarter of it).
3. The tree HISMs get a component Detail Mode from their rank band (nf_trees_band.py): ranks 0-0.55 Low, 0.55-0.78 Medium, 0.78-1 High.
   A device profile with r.DetailMode=0 never creates render state for the Medium / High bands, and with
   r.CookOutUnusedDetailModeComponents=1 the cook strips them from the phone build (instance memory, registration time, GPU-scene
   instances). Same deterministic ranks as the PC distance thinning: a phone keeps exactly the trees that survive farthest on PC.
4. Bark occlusion (part "bark"): the desktop forest gets its trunk darkening under the crowns from SSAO, which the mobile renderer does
   not run; with the thinner phone forest the bare-lit trunks read as a pink stubble (first ES3.1 preview of the cryptomeria plantation).
   The three bark materials' base colour is multiplied by BarkAOM under `#if SHADING_PATH_MOBILE` - a constant baked-occlusion stand-in.
ACW_NF_MOBILE_PARTS = comma list of mpc,trees,detail,bark (default all). Receipt: reports/nf_mobile_profile.report.json.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import E, FORM_BARK_SRC, FORM_LEAF_SRC, MAP, MAT, OUT, lib, link, mel, write_report  # noqa: E402

MOBILE = {"NearFullM": 45000.0, "ThinEndM": 150000.0, "FadeWidthM": 10000.0, "ThinGammaM": 1.6, "ShellStartM": 50000.0,
          "ShellEndM": 130000.0, "ClumpGainM": 0.5, "RankKeepM": 0.55, "CrownGainM": 0.10,
          "NearCanopyM": 0.6, "BarkAOM": 0.45}
MOBILE.update({k: float(v) for k, v in (kv.split("=") for kv in os.environ.get("ACW_NF_MOBILE_MPC", "").split(",") if kv)})
PARTS = os.environ.get("ACW_NF_MOBILE_PARTS", "mpc,trees,detail,bark").split(",")
MARK = "#if SHADING_PATH_MOBILE"
KEEP_PRE = MARK + """
Near = NearM; End = EndM; Width = WidthM; Gamma = GammaM; R = saturate(R / max(KeepM, 0.01));
#endif
"""
CLUMP_PRE = MARK + """
Near = NearM; End = EndM; Width = WidthM; Gamma = GammaM; CG = CGM; R = saturate(R / max(KeepM, 0.01));
#endif
"""
CROWN = "\n" + MARK + "\ng += CrownM * (1.0 - saturate((D - Near) / max(End - Near, 1.0)));\n#endif"
BAND_DETAIL = [unreal.DetailMode.DM_LOW, unreal.DetailMode.DM_LOW, unreal.DetailMode.DM_MEDIUM, unreal.DetailMode.DM_HIGH]
rep = {"status": "FAIL_NF_MOBILE_PROFILE", "parts": PARTS, "error": None}


def mpc():
    path = MAT + "/MPC_NF_Forest"
    c = lib.load_asset(path)
    params = list(c.get_editor_property("scalar_parameters"))
    have = {str(p.get_editor_property("parameter_name")): p for p in params}
    for k, v in MOBILE.items():
        if k in have:
            have[k].set_editor_property("default_value", v)
        else:
            p = unreal.CollectionScalarParameter()
            p.set_editor_property("parameter_name", k)
            p.set_editor_property("default_value", v)
            params.append(p)
    c.set_editor_property("scalar_parameters", params)
    lib.save_asset(path, only_if_is_dirty=False)
    rep["mpc"] = {str(p.get_editor_property("parameter_name")): p.get_editor_property("default_value")
                  for p in lib.load_asset(path).get_editor_property("scalar_parameters")}


def custom_nodes(mat):
    """(keep Custom node of the opacity mask, clump Custom node of the WPO) - same lookup as nf_trees_band.py."""
    op = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_OPACITY_MASK)
    keep = op if op.get_class().get_name() == "MaterialExpressionCustom" else \
        next(n for n in mel.get_inputs_for_material_expression(mat, op) if n is not None and n.get_class().get_name() == "MaterialExpressionCustom")
    tr = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    clump = mel.get_inputs_for_material_expression(mat, tr)[0]
    return keep, clump


def add_inputs(mat, coll, node, pins, y0):
    ins = list(node.get_editor_property("inputs"))
    have = [str(i.get_editor_property("input_name")) for i in ins]
    new = [(pin, name) for pin, name in pins if pin not in have]
    for pin, _ in new:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", pin)
        ins.append(ci)
    node.set_editor_property("inputs", ins)
    for i, (pin, name) in enumerate(new):
        link(E(mat, unreal.MaterialExpressionCollectionParameter, -1600, y0 + 70 * i, collection=coll, parameter_name=name), "", node, pin)


def trees():
    coll = lib.load_asset(MAT + "/MPC_NF_Forest")
    common = [("NearM", "NearFullM"), ("EndM", "ThinEndM"), ("WidthM", "FadeWidthM"), ("GammaM", "ThinGammaM"), ("KeepM", "RankKeepM")]
    rep["materials"] = {}
    for src in sorted(set(FORM_LEAF_SRC.values()) | set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        keep, clump = custom_nodes(mat)
        kc, cc = str(keep.get_editor_property("code")), str(clump.get_editor_property("code"))
        if MARK in kc or MARK in cc:
            rep["materials"][path] = "already"
            continue
        if "float T = " not in cc or "float g = " not in cc:
            raise RuntimeError("unexpected clump code on " + path)
        add_inputs(mat, coll, keep, common, 3000)
        add_inputs(mat, coll, clump, common + [("CGM", "ClumpGainM"), ("CrownM", "CrownGainM")], 3400)
        keep.set_editor_property("code", KEEP_PRE + kc)
        cc2 = cc.replace("\nfloat T = ", CROWN + "\nfloat T = ", 1)
        clump.set_editor_property("code", CLUMP_PRE + cc2)
        mel.recompile_material(mat)
        if not lib.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("save " + path)
        rep["materials"][path] = {"keep": KEEP_PRE + kc, "clump": CLUMP_PRE + cc2}


BARK_HLSL = MARK + """
return C.rgb * K;
#else
return C.rgb;
#endif"""


def bark():
    coll = lib.load_asset(MAT + "/MPC_NF_Forest")
    rep["bark"] = {}
    for src in sorted(set(FORM_BARK_SRC.values())):
        path = MAT + "/" + src.replace("M_TL_", "M_NF_")
        mat = lib.load_asset(path)
        node = mel.get_material_property_input_node(mat, unreal.MaterialProperty.MP_BASE_COLOR)
        if node.get_class().get_name() == "MaterialExpressionCustom" and MARK in str(node.get_editor_property("code")):
            rep["bark"][path] = "already"
            continue
        out = mel.get_material_property_input_node_output_name(mat, unreal.MaterialProperty.MP_BASE_COLOR)
        ins = []
        for n in ("C", "K"):
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", n)
            ins.append(ci)
        cu = E(mat, unreal.MaterialExpressionCustom, -250, -300, code=BARK_HLSL, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3,
               description="NF mobile bark occlusion", inputs=ins)
        link(node, out, cu, "C")
        link(E(mat, unreal.MaterialExpressionCollectionParameter, -550, -200, collection=coll, parameter_name="BarkAOM"), "", cu, "K")
        mel.connect_material_property(cu, "", unreal.MaterialProperty.MP_BASE_COLOR)
        mel.recompile_material(mat)
        if not lib.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("save " + path)
        rep["bark"][path] = "base colour x BarkAOM on mobile (was %s.%s)" % (node.get_name(), out)


def detail():
    band = json.loads((OUT / "reports" / "nf_trees_band.report.json").read_text(encoding="utf-8"))
    culls = [float(c) for c in band["band_culls_cm"]]
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not les.load_level(MAP + "/L_NF_Yangmingshan"):
        raise RuntimeError("load level")
    wpl = unreal.WorldPartitionBlueprintLibrary
    wpl.load_actors([d.get_editor_property("guid") for d in wpl.get_actor_descs() if str(d.get_editor_property("label")).startswith("NF_Trees_")])
    comps, inst = [0] * len(culls), [0] * len(culls)
    for a in ues.get_all_level_actors():
        if not a.get_actor_label().startswith("NF_Trees_"):
            continue
        a.modify()
        for h in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            end = float(h.get_editor_property("instance_end_cull_distance"))
            b = min(range(len(culls)), key=lambda i: abs(culls[i] - end))
            if abs(culls[b] - end) > 1.0:
                raise RuntimeError("HISM end cull %s is not a band cull %s" % (end, culls))
            h.modify()
            h.set_editor_property("detail_mode", BAND_DETAIL[b])
            comps[b] += 1
            inst[b] += h.get_instance_count()
    rep["detail"] = {"band_culls_cm": culls, "components_per_band": comps, "instances_per_band": inst,
                     "band_detail_mode": [str(d) for d in BAND_DETAIL]}
    if sum(comps) != 17351 or sum(inst) != 3859205:
        raise RuntimeError("tree HISM census %d / %d" % (sum(comps), sum(inst)))
    les.save_current_level()
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("save dirty packages")


try:
    if "mpc" in PARTS:
        mpc()
    if "trees" in PARTS:
        trees()
    if "bark" in PARTS:
        bark()
    if "detail" in PARTS:
        detail()
    rep["status"] = "PASS_NF_MOBILE_PROFILE"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_mobile_profile.report.json", rep)
unreal.SystemLibrary.quit_editor()
