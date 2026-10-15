"""TreeLookdev budget experiment, stage 1 (UnrealEditor-Cmd): import the budget LOD chains and build the perf levels.

Candidates (all use the SAME materials / atlas / bark as the PR #30 tree; only the mesh LOD chains differ):
  A  baseline  /Game/TreeLookdev/Meshes/Machilus/... (129,278 / 36,710 / 4,256 tris, screens 1.0 / 0.5 / 0.15) - not touched
  B  budget    machilus_budget_lod0..2 (34,272 / 4,868 / 1,400), same screens
  C  budget+far  machilus_budget_lod0..3 (+ 534-tri far LOD), screens 1.0 / 0.5 / 0.15 / 0.06
Perf levels /Game/TreeLookdev/Perf/L_TLB_<view>_<single|patch>_<A|B|C> and L_TLB_<view>_empty (same camera + stage, no tree).
single = the one look-dev tree; patch = 10 x 10 HISM copies of the same tree (25 m grid, seeded jitter / yaw / scale; instance 0 is the
look-dev tree at the origin) - a same-tree patch to make far-LOD costs measurable, NOT a forest system.
Env ACW_TL_BUDGET_STAGE = meshes | levels | all (default all).
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_budget_common import BUDGET, PATH, setup_tree  # noqa: E402
from tl_common import GAME, LEVEL, MAT_DIR, ROOT, b2u, b2u_dir, ensure_dir, find_actor, lib, write_report  # noqa: E402

sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
PERF = ROOT + "/Perf"
CHAIN = {"B": ("budget", [0, 1, 2], [1.0, 0.5, 0.15]), "C": ("budget", [0, 1, 2, 3], [1.0, 0.5, 0.15, 0.06]),
         "D": ("balanced", [0, 1, 2, 3], [1.0, 0.5, 0.15, 0.06])}
STAGE = os.environ.get("ACW_TL_BUDGET_STAGE", "all")
report = {"status": "FAIL_TL_BUDGET", "meshes": {}, "levels": [], "error": None}


def import_mesh(glb, dest):
    if lib.does_directory_exist(dest):
        lib.delete_directory(dest)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    if not mgr.import_asset(dest, unreal.InterchangeManager.create_source_data(str(glb)), params):
        raise RuntimeError("Interchange import failed: %s" % glb)
    found = [(str(p).split(".")[0], lib.load_asset(p)) for p in lib.list_assets(dest, recursive=True)]
    meshes = [(p, o) for p, o in found if o is not None and o.get_class().get_name() == "StaticMesh"]
    if len(meshes) != 1:
        raise RuntimeError("%s produced %d static meshes" % (glb, len(meshes)))
    return meshes[0]


def audit(mesh):
    n = mesh.get_num_lods()
    return {"lods": n, "screens": list(sub.get_lod_screen_sizes(mesh)), "triangles": [mesh.get_num_triangles(i) for i in range(n)],
            "vertices": [sub.get_number_verts(mesh, i) for i in range(n)], "sections": [mesh.get_num_sections(i) for i in range(n)],
            "sphere_radius_cm": mesh.get_bounds().sphere_radius}


def build_mesh(key):
    prof, lods, screens = CHAIN[key]
    m_bark = lib.load_asset(MAT_DIR + "/M_TL_Bark")
    m_leaf = lib.load_asset(MAT_DIR + "/M_TL_LeafCards")
    path, mesh = import_mesh(GAME / "glb" / ("machilus_%s_lod0.glb" % prof), BUDGET + "/" + key)
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    for lod in lods[1:]:
        r = sub.import_lod(mesh, lod, str(GAME / "glb" / ("machilus_%s_lod%d.glb" % (prof, lod))))
        report["meshes"].setdefault(key + "_import", {})[lod] = r
    for lod in range(mesh.get_num_lods()):
        bs = sub.get_lod_build_settings(mesh, lod)
        for prop, val in (("recompute_normals", False), ("recompute_tangents", True), ("use_mikk_t_space", True),
                          ("use_full_precision_u_vs", True), ("remove_degenerates", False), ("generate_lightmap_u_vs", False)):
            try:
                bs.set_editor_property(prop, val)
            except Exception as exc:  # noqa: BLE001
                unreal.log_warning("build settings %s: %s" % (prop, exc))
        sub.set_lod_build_settings(mesh, lod, bs)
    mesh.set_editor_property("static_materials", [unreal.StaticMaterial(material_interface=m_bark, material_slot_name="Bark"),
                                                  unreal.StaticMaterial(material_interface=m_leaf, material_slot_name="LeafCards")])
    for lod in range(mesh.get_num_lods()):
        for s in range(mesh.get_num_sections(lod)):
            sub.set_lod_material_slot(mesh, min(s, 1), lod, s)
    if not sub.set_lod_screen_sizes(mesh, screens):
        raise RuntimeError("set_lod_screen_sizes failed")
    lib.save_asset(path)
    report["meshes"][key] = dict(asset=path, **audit(mesh))
    if path != PATH[key]:
        raise RuntimeError("unexpected asset path %s != %s" % (path, PATH[key]))


def build_level(view, mode, key):
    if not levels.load_level(LEVEL):
        raise RuntimeError("load " + LEVEL)
    V = {v["name"]: v for v in json.loads((GAME / "views_budget.json").read_text(encoding="utf-8"))["views"]}[view]
    loc = b2u(V["loc"])
    d = b2u_dir(V["fwd"])
    rot = unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(loc.x + d.x * 1e5, loc.y + d.y * 1e5, loc.z + d.z * 1e5))
    cam = actors.spawn_actor_from_class(unreal.CameraActor, loc, rot)
    cam.set_actor_label("TL_PerfCamera")
    cc = cam.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", float(V["hfov_deg"]))
    cc.set_editor_property("aspect_ratio", 16.0 / 9.0)
    cc.set_editor_property("constrain_aspect_ratio", True)
    cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    if key is None:
        actors.destroy_actor(find_actor(actors, "TL_Machilus"))
        dest = PERF + "/L_TLB_%s_empty" % view
    else:
        setup_tree(actors, mode, key)
        dest = PERF + "/L_TLB_%s_%s_%s" % (view, mode, key)
    if lib.does_asset_exist(dest):
        lib.delete_asset(dest)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, dest):
        raise RuntimeError("save_map failed: " + dest)
    report["levels"].append(dest)


try:
    ensure_dir(BUDGET)
    ensure_dir(PERF)
    if STAGE in ("meshes", "all"):
        for k in (os.environ.get("ACW_TL_BUDGET_KEYS", "B,C,D")).split(","):
            build_mesh(k)
    if STAGE in ("levels", "all"):
        for view in ("front", "sl150", "sl300", "sl500", "sl1000"):
            build_level(view, None, None)
        for view, mode in (("front", "single"), ("sl150", "single"), ("sl150", "patch"), ("sl300", "patch"), ("sl500", "patch"), ("sl1000", "patch")):
            for key in ("A", "B", "C", "D"):
                build_level(view, mode, key)
    report["status"] = "PASS_TL_BUDGET"
except Exception:  # noqa: BLE001
    report["error"] = traceback.format_exc()
    unreal.log_error(report["error"])
write_report("tl_budget_build.%s.report.json" % STAGE, report)
unreal.SystemLibrary.quit_editor()
