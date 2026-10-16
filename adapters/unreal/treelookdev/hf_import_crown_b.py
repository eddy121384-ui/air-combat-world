"""Hillside forest mix v0 (UnrealEditor-Cmd): import the 紅楠 second crown form (crown B) as a 4-LOD static mesh.

Input: $ACW_HF_CROWN_B_GAME/glb/machilus_balanced_lod{0..3}.glb, made by tools/treegen/machilus_game.py (profile balanced, atlas frames
reused) from the crown-B golden (tools/treegen/params/machilus_crown_b.json). Same recipe as PR #31's tl_budget_build.py for D: Nanite
off, LOD build settings, slots Bark / LeafCards bound to the unchanged M_TL_Bark / M_TL_LeafCards, screen sizes 1.0 / 0.5 / 0.15 / 0.06.
Output: /Game/HillsideForest/Trees/CrownB/... ; receipt reports/hf_import_crown_b.report.json.
"""
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import MAT_DIR, ensure_dir, lib, write_report  # noqa: E402

GAME_B = Path(os.environ["ACW_HF_CROWN_B_GAME"])
DEST = "/Game/HillsideForest/Trees/CrownB"
SCREENS = [1.0, 0.5, 0.15, 0.06]
sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
rep = {"status": "FAIL_HF_IMPORT_CROWN_B", "error": None}


def audit(mesh):
    n = mesh.get_num_lods()
    b = mesh.get_bounds()
    return {"lods": n, "screens": [round(x, 4) for x in sub.get_lod_screen_sizes(mesh)], "triangles": [mesh.get_num_triangles(i) for i in range(n)],
            "vertices": [sub.get_number_verts(mesh, i) for i in range(n)], "sections": [mesh.get_num_sections(i) for i in range(n)],
            "sphere_radius_cm": b.sphere_radius, "bounds_origin_cm": [b.origin.x, b.origin.y, b.origin.z],
            "bounds_extent_cm": [b.box_extent.x, b.box_extent.y, b.box_extent.z]}


try:
    ensure_dir("/Game/HillsideForest")
    ensure_dir("/Game/HillsideForest/Trees")
    if lib.does_directory_exist(DEST):
        raise RuntimeError("%s exists" % DEST)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    if not mgr.import_asset(DEST, unreal.InterchangeManager.create_source_data(str(GAME_B / "glb" / "machilus_balanced_lod0.glb")), params):
        raise RuntimeError("Interchange import failed")
    found = [(str(p).split(".")[0], lib.load_asset(p)) for p in lib.list_assets(DEST, recursive=True)]
    meshes = [(p, o) for p, o in found if o is not None and o.get_class().get_name() == "StaticMesh"]
    if len(meshes) != 1:
        raise RuntimeError("%d static meshes" % len(meshes))
    path, mesh = meshes[0]
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    rep["import_lods"] = {lod: sub.import_lod(mesh, lod, str(GAME_B / "glb" / ("machilus_balanced_lod%d.glb" % lod))) for lod in (1, 2, 3)}
    for lod in range(mesh.get_num_lods()):
        bs = sub.get_lod_build_settings(mesh, lod)
        for prop, val in (("recompute_normals", False), ("recompute_tangents", True), ("use_mikk_t_space", True),
                          ("use_full_precision_u_vs", True), ("remove_degenerates", False), ("generate_lightmap_u_vs", False)):
            bs.set_editor_property(prop, val)
        sub.set_lod_build_settings(mesh, lod, bs)
    mesh.set_editor_property("static_materials", [
        unreal.StaticMaterial(material_interface=lib.load_asset(MAT_DIR + "/M_TL_Bark"), material_slot_name="Bark"),
        unreal.StaticMaterial(material_interface=lib.load_asset(MAT_DIR + "/M_TL_LeafCards"), material_slot_name="LeafCards")])
    for lod in range(mesh.get_num_lods()):
        for s in range(mesh.get_num_sections(lod)):
            sub.set_lod_material_slot(mesh, min(s, 1), lod, s)
    if not sub.set_lod_screen_sizes(mesh, SCREENS):
        raise RuntimeError("set_lod_screen_sizes")
    if not lib.save_asset(path):
        raise RuntimeError("save " + path)
    rep["asset"] = path
    rep["mesh"] = audit(mesh)
    if rep["mesh"]["lods"] != 4:
        raise RuntimeError("expected 4 LODs: %s" % rep["mesh"])
    rep["status"] = "PASS_HF_IMPORT_CROWN_B"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("hf_import_crown_b.report.json", rep)
unreal.SystemLibrary.quit_editor()
