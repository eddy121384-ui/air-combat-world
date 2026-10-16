"""Hillside forest look-dev v1, stage 2 (FRESH UnrealEditor-Cmd process): persisted-material / content gate. Fails closed.

Why a separate process: the editor sets "Used with Instanced Static Meshes" in memory the first time a HISM draws a material, so a check in
the build process can pass while the saved asset is still wrong (PR #31 q1: standalone -game then drew the engine default grey material).
This stage reads only what is on disk:

* M_TL_LeafCards / M_TL_Bark packages: used_with_instanced_static_meshes == True, leaf blend mode MASKED + two-sided + foliage shading,
  and the package is not dirty after load; after ALL maps below were loaded (HISMs registered) no material / forest package is dirty
  (a missing saved flag would be set in memory there and dirty its package);
* every map that renders the forest (main, stills, flight, perf): HF_Forest has one HISM per (form, tint) of the instance file
  ($ACW_HF_INSTANCES, default instances.json), the D mesh for form A / crown-B mesh for form B (4 LODs, screens 1/0.5/0.15/0.06),
  slot 0 resolves to M_TL_Bark and slot 1 to an MI_HF_Leaf_V* whose base material is M_TL_LeafCards (MASKED), never a default /
  WorldGrid material, total instances == instances.json, and 32 sampled instance transforms match instances.json (location <= 1 cm, scale <= 0.05 %);
* the MICs carry the intended parameter overrides; the Landscape exists with 64 components and M_HF_Ground.
The native pixel guard (tree pixels in the standalone -game MRQ frames are green, not grey) is in tools/forest/hillside_frames.py.
Receipt: reports/hf_verify.report.json (PASS_HF_VERIFY or FAIL_HF_VERIFY).
"""
import json
import math
import os
import random
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_budget_common import PATH  # noqa: E402
from tl_common import MAT_DIR, OUT, find_actor, lib, write_report  # noqa: E402

HF_DIR = Path(os.environ["ACW_HF_DIR"])
build = json.loads((OUT / "reports" / "hf_build.report.json").read_text(encoding="utf-8"))
INSTANCES = os.environ.get("ACW_HF_INSTANCES", "instances.json")
I = json.loads((HF_DIR / INSTANCES).read_text(encoding="utf-8"))["instances"]
# form A LOD chain: D balanced (default, Mix D) or PR #31's aggressive C (Mix C low-precision tolerance test); form B is always crown B
A_CHAIN = os.environ.get("ACW_HF_A_CHAIN", "D")
if A_CHAIN not in ("C", "D"):
    raise RuntimeError("ACW_HF_A_CHAIN must be C or D")
FORM_MESH = {"A": PATH[A_CHAIN], "B": "/Game/HillsideForest/Trees/CrownB/machilus_balanced_lod0/StaticMeshes/machilus_balanced_lod0"}
GROUPS = sorted({(it.get("form", "A"), it["variant"]) for it in I})
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
DEFAULTS = ("/Engine/EngineMaterials/WorldGridMaterial", "/Engine/EngineMaterials/DefaultMaterial", "/Engine/EngineMaterials/DefaultDeferredDecalMaterial")
rep = {"status": "FAIL_HF_VERIFY", "instances_file": INSTANCES, "a_chain": A_CHAIN, "checks": [], "materials": {}, "maps": {}, "error": None}


def check(name, ok, detail=None):
    rep["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        unreal.log_error("HF_VERIFY FAIL %s %s" % (name, detail))
    return ok


def dirty_packages():
    return sorted(p.get_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())


def pkg_dirty(obj):
    return obj.get_path_name().split(".")[0] in dirty_packages()


def base_path(m):
    b = m.get_base_material() if hasattr(m, "get_base_material") else m
    return b.get_path_name().split(".")[0], b


def material_gate():
    for name in ("M_TL_LeafCards", "M_TL_Bark"):
        m = lib.load_asset(MAT_DIR + "/" + name)
        d = {"used_with_instanced_static_meshes": bool(m.get_editor_property("used_with_instanced_static_meshes")),
             "blend_mode": str(m.get_editor_property("blend_mode")), "two_sided": bool(m.get_editor_property("two_sided")),
             "shading_model": str(m.get_editor_property("shading_model")), "package_dirty_after_load": pkg_dirty(m)}
        rep["materials"][name] = d
        check(name + " saved with ISM usage", d["used_with_instanced_static_meshes"], d)
        check(name + " package clean after load", d["package_dirty_after_load"] is False, d)
        if name == "M_TL_LeafCards":
            check("leaf MASKED", "MASKED" in d["blend_mode"].upper(), d["blend_mode"])
            check("leaf two-sided", d["two_sided"], d)
            check("leaf foliage shading", "FOLIAGE" in d["shading_model"].upper(), d["shading_model"])
    for name, want in build["materials"].items():
        if not name.startswith("MI_HF_Leaf_"):
            continue
        mic = lib.load_asset(build["maps"]["main"]["map"].rsplit("/", 1)[0] + "/" + name)
        got = {}
        for k, v in want["overrides"].items():
            if isinstance(v, list):
                c = unreal.MaterialEditingLibrary.get_material_instance_vector_parameter_value(mic, k)
                got[k] = [round(c.r, 4), round(c.g, 4), round(c.b, 4)]
                ok = all(abs(a - b) < 1e-3 for a, b in zip(got[k], v))
            else:
                got[k] = round(unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(mic, k), 4)
                ok = abs(got[k] - v) < 1e-3
            check("%s %s" % (name, k), ok, {"want": v, "got": got[k]})
        bp, _ = base_path(mic)
        check(name + " base is M_TL_LeafCards", bp == MAT_DIR + "/M_TL_LeafCards", bp)
        rep["materials"][name] = {"base": bp, "overrides": got, "package_dirty_after_load": pkg_dirty(mic)}


def forest_gate(key, path, expect_forest):
    if not levels.load_level(path):
        return check(key + " load", False, path)
    m = {"map": path}
    land = find_actor(actors, "HF_Terrain_Xiangshan")
    check(key + " landscape present", land is not None)
    if land is not None:
        lm = land.get_editor_property("landscape_material")
        n_comp = len(land.get_components_by_class(unreal.LandscapeComponent))
        m["landscape"] = {"material": lm.get_path_name() if lm else None, "components": n_comp}
        check(key + " landscape 64 components", n_comp == 64, n_comp)
        check(key + " landscape material", lm is not None and lm.get_name() == "M_HF_Ground", m["landscape"]["material"])
    holder = find_actor(actors, "HF_Forest")
    if not expect_forest:
        check(key + " empty map has no forest", holder is None)
        rep["maps"][key] = m
        return
    if not check(key + " forest present", holder is not None):
        return
    hisms = holder.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    check(key + " one HISM per (form, tint)", len(hisms) == len(GROUPS), {"hisms": len(hisms), "groups": GROUPS})
    per_mesh = {}
    total, comps = 0, []
    world_xf = []
    for h in hisms:
        mesh = h.get_editor_property("static_mesh")
        mp = mesh.get_path_name().split(".")[0] if mesh else None
        screens = [round(x, 3) for x in sms.get_lod_screen_sizes(mesh)] if mesh else None
        mats = []
        for slot in range(h.get_num_materials()):
            mi = h.get_material(slot)
            bp, b = base_path(mi)
            mats.append({"slot": slot, "material": mi.get_path_name().split(".")[0], "base": bp, "base_blend": str(b.get_editor_property("blend_mode")),
                         "base_ism_usage": bool(b.get_editor_property("used_with_instanced_static_meshes"))})
        n = h.get_instance_count()
        total += n
        comps.append({"name": h.get_name(), "mesh": mp, "lods": mesh.get_num_lods() if mesh else None, "screens": screens,
                      "triangles": [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())] if mesh else None,
                      "instances": n, "materials": mats, "cast_shadow": bool(h.get_editor_property("cast_shadow"))})
        check("%s %s mesh = form-A chain (D or C) or crown B" % (key, h.get_name()), mp in FORM_MESH.values(), mp)
        per_mesh[mp] = per_mesh.get(mp, 0) + n
        check("%s %s 4 LODs 1/0.5/0.15/0.06" % (key, h.get_name()), screens == [1.0, 0.5, 0.15, 0.06], screens)
        check("%s %s slot0 bark" % (key, h.get_name()), mats[0]["base"] == MAT_DIR + "/M_TL_Bark" and mats[0]["base_ism_usage"], mats[0])
        check("%s %s slot1 masked leaf MIC" % (key, h.get_name()),
              mats[1]["material"].split("/")[-1].startswith("MI_HF_Leaf_V") and mats[1]["base"] == MAT_DIR + "/M_TL_LeafCards"
              and "MASKED" in mats[1]["base_blend"].upper() and mats[1]["base_ism_usage"], mats[1])
        check("%s %s no default material" % (key, h.get_name()), not any(x["material"] in DEFAULTS or x["base"] in DEFAULTS for x in mats), mats)
        for i in range(n):
            world_xf.append(h.get_instance_transform(i, True))
    m["hisms"] = comps
    m["instances_total"] = total
    m["instances_per_mesh"] = per_mesh
    want = {FORM_MESH[f]: sum(1 for it in I if it.get("form", "A") == f) for f in {it.get("form", "A") for it in I}}
    check(key + " instances per form", per_mesh == want, {"got": per_mesh, "want": want})
    check(key + " instance total", total == len(I), {"got": total, "want": len(I)})
    # transform spot check against instances.json (match by nearest location)
    rng = random.Random(7)
    worst_cm, worst_scale = 0.0, 0.0
    locs = [(t.translation.x, t.translation.y, t.translation.z, t) for t in world_xf]
    for it in rng.sample(I, 32):
        x, y, z = it["ue_cm"]
        best = min(locs, key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2 + (q[2] - z) ** 2)
        worst_cm = max(worst_cm, math.dist(best[:3], (x, y, z)))
        sc = best[3].scale3d
        worst_scale = max(worst_scale, abs(sc.x - it["scale_x"]) / it["scale_x"] * 100, abs(sc.y - it["scale_y"]) / it["scale_y"] * 100, abs(sc.z - it["scale_z"]) / it["scale_z"] * 100)  # scale error in %
    m["spot_check"] = {"worst_location_cm": round(worst_cm, 3), "worst_scale_err_pct": round(worst_scale, 4)}
    check(key + " transforms match instances.json", worst_cm <= 1.0 and worst_scale <= 0.05, m["spot_check"])
    rep["maps"][key] = m


try:
    material_gate()
    for key, row in build["maps"].items():
        forest_gate(key, row["map"], not key.endswith("_empty"))
    # had a material lacked the saved flag, registering the HISMs of the maps above would have set it in memory and dirtied the package
    dirty = [p for p in dirty_packages() if "/Materials/" in p or "/HillsideForest/" in p]
    check("no material / forest package dirtied by loading every map", not dirty, dirty)
    rep["n_checks"] = len(rep["checks"])
    rep["n_failed"] = sum(1 for c in rep["checks"] if not c["ok"])
    rep["status"] = "PASS_HF_VERIFY" if rep["n_failed"] == 0 and build["status"] == "PASS_HF_BUILD" else "FAIL_HF_VERIFY"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("hf_verify.report.json", rep)
unreal.SystemLibrary.quit_editor()
