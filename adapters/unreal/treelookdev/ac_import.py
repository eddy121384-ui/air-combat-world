"""相思樹 Acacia confusa lookdev v1 (UnrealEditor-Cmd): import the 相思樹 game version as a 4-LOD static mesh with its own materials.

Input: $ACW_AC_GAME/glb/acacia_acacia_lod{0..3}.glb + textures/T_Acacia_*.png (tools/treegen/machilus_game.py with ACW_TL_SPECIES=acacia,
ACW_TL_PROFILE=acacia; tools/treegen/machilus_game_textures.py <out> acacia). Only NEW assets are written - the 紅楠 textures /
materials / meshes are never touched:
* /Game/TreeLookdev/Textures/T_Acacia_{LeafAtlas_BC, LeafAtlas_N, Bark_BC, Bark_N}
* /Game/TreeLookdev/Materials/M_TL_Acacia_LeafCards, M_TL_Acacia_Bark: the same plain graphs as M_TL_LeafCards / M_TL_Bark
  (tl_build.py) with the acacia textures; "Used with Instanced Static Meshes" is set, compiled and SAVED here, at creation (PR #31 lesson:
  an unsaved flag makes standalone -game draw HISMs with the engine default grey material). hf_verify.py re-checks it in a fresh process.
* /Game/HillsideForest/Trees/Acacia/...: Nanite off, LOD build settings as PR #31, slots Bark / LeafCards, screens 1.0 / 0.5 / 0.15 / 0.06.
Receipt: reports/ac_import.report.json.
"""
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import MAT_DIR, TEX_DIR, ensure_dir, lib, mel, tools, write_report  # noqa: E402

GAME = Path(os.environ["ACW_AC_GAME"])
# species (柳杉 unreal v1): ACW_AC_SPECIES=cryptomeria -> T_Cryptomeria_* / M_TL_Cryptomeria_* / cryptomeria_<profile>_lod*.glb; default 相思樹
SPECIES = os.environ.get("ACW_AC_SPECIES", "acacia")
CAP = SPECIES.capitalize()
DEST = os.environ.get("ACW_AC_DEST", "/Game/HillsideForest/Trees/Acacia")
# LOD chain = machilus_game.py profile (acacia = first chain, acacia_dense = second); MESH_ONLY: reuse the saved acacia textures / materials
PROFILE = os.environ.get("ACW_AC_PROFILE", "acacia")
MESH_ONLY = os.environ.get("ACW_AC_MESH_ONLY") == "1"
# LEAF_TAG (clump chain): import <stem>_LeafAtlasW_* as T_<tag>_LeafAtlas_* and create M_TL_<tag>_LeafCards; the bark material is reused
LEAF_TAG = os.environ.get("ACW_AC_LEAF_TAG")
ATLAS_STEM = os.environ.get("ACW_AC_ATLAS_STEM", "T_%s_LeafAtlas" % CAP)
CLIP = float(os.environ.get("ACW_AC_CLIP", "0.4"))  # opacity mask clip and alpha-coverage threshold (lineup a4: 0.25 slightly fuller)
SCREENS = [1.0, 0.5, 0.15, 0.06]
# leaf defaults: the acacia atlas is already lighter / yellower than the 紅楠 one, so the tint pair is near-neutral; same stage brightness
LEAF = dict(TintLo=(0.86, 0.88, 0.80), TintHi=(1.14, 1.10, 0.96), OcclMin=0.3, Brightness=0.42, SSSColor=(0.8, 0.95, 0.3), SSS=0.45,
            NormalFlatten=0.4, Roughness=0.7, Specular=0.18)
BARK = dict(TwigColor=(0.07, 0.045, 0.025), BarkBrightness=0.5, Roughness=0.9)
sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
rep = {"status": "FAIL_AC_IMPORT", "textures": {}, "materials": {}, "error": None}


def import_texture(png, name, srgb, normal=False, alpha_coverage=None):
    path = TEX_DIR + "/" + name
    if lib.does_asset_exist(path):
        raise RuntimeError("refusing to overwrite " + path)
    task = unreal.AssetImportTask()
    for k, v in (("filename", str(png)), ("destination_path", TEX_DIR), ("destination_name", name), ("automated", True),
                 ("replace_existing", False), ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    tex = lib.load_asset(path)
    if tex is None:
        raise RuntimeError("texture import failed: %s" % png)
    tex.set_editor_property("srgb", srgb)
    if normal:
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
    if alpha_coverage is not None:
        tex.set_editor_property("do_scale_mips_for_alpha_coverage", True)
        tex.set_editor_property("alpha_coverage_thresholds", unreal.Vector4(0.0, 0.0, 0.0, alpha_coverage))
    if not lib.save_asset(path):
        raise RuntimeError("save " + path)
    rep["textures"][name] = {"path": path, "size": [tex.blueprint_get_size_x(), tex.blueprint_get_size_y()], "srgb": srgb}
    return tex


def new_material(name):
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        raise RuntimeError("refusing to overwrite " + path)
    return tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew()), path


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, out, b, pin):
    if not mel.connect_material_expressions(a, out, b, pin):
        raise RuntimeError("connect failed %s.%s -> %s" % (a.get_name(), out, pin))


def scalar(mat, name, x, y, table):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=float(table[name]))


def vec(mat, name, x, y, table):
    c = table[name]
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(c[0], c[1], c[2], 1.0))


def tex_param(mat, name, tex, x, y, normal=False):
    t = E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=tex)
    t.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if normal else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    return t


def finish(mat, path):
    """ISM usage flag set + compiled + saved at creation; then read back from the asset."""
    mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    mel.recompile_material(mat)
    if not lib.save_asset(path, only_if_is_dirty=False):
        raise RuntimeError("save " + path)
    rep["materials"][path] = {"used_with_instanced_static_meshes": bool(mat.get_editor_property("used_with_instanced_static_meshes")),
                              "blend_mode": str(mat.get_editor_property("blend_mode")), "two_sided": bool(mat.get_editor_property("two_sided"))}
    if not rep["materials"][path]["used_with_instanced_static_meshes"]:
        raise RuntimeError("ISM usage flag did not stick on " + path)


def leaf_material(bc, nm, name="M_TL_%s_LeafCards" % CAP):
    """Same graph as tl_build.leaf_material (M_TL_LeafCards), acacia textures / defaults."""
    mat, path = new_material(name)
    foliage = next(getattr(unreal.MaterialShadingModel, n) for n in dir(unreal.MaterialShadingModel) if "FOLIAGE" in n.upper())
    for prop, val in (("blend_mode", unreal.BlendMode.BLEND_MASKED), ("two_sided", True), ("shading_model", foliage), ("opacity_mask_clip_value", CLIP)):
        mat.set_editor_property(prop, val)
    t = tex_param(mat, "LeafBC", bc, -1400, 0)
    n = tex_param(mat, "LeafN", nm, -1400, 500, normal=True)
    vc = E(mat, unreal.MaterialExpressionVertexColor, -1400, -400)
    tint = E(mat, unreal.MaterialExpressionLinearInterpolate, -850, -400)
    link(vec(mat, "TintLo", -1100, -500, LEAF), "", tint, "A")
    link(vec(mat, "TintHi", -1100, -350, LEAF), "", tint, "B")
    link(vc, "R", tint, "Alpha")
    occ = E(mat, unreal.MaterialExpressionLinearInterpolate, -850, -200, const_b=1.0)
    link(scalar(mat, "OcclMin", -1100, -200, LEAF), "", occ, "A")
    link(vc, "G", occ, "Alpha")
    m1 = E(mat, unreal.MaterialExpressionMultiply, -650, -100)
    link(t, "RGB", m1, "A")
    link(tint, "", m1, "B")
    m2 = E(mat, unreal.MaterialExpressionMultiply, -450, -100)
    link(m1, "", m2, "A")
    link(occ, "", m2, "B")
    m3 = E(mat, unreal.MaterialExpressionMultiply, -250, -100)
    link(m2, "", m3, "A")
    link(scalar(mat, "Brightness", -450, 50, LEAF), "", m3, "B")
    mel.connect_material_property(m3, "", unreal.MaterialProperty.MP_BASE_COLOR)
    sss = E(mat, unreal.MaterialExpressionMultiply, -250, 150)
    link(m3, "", sss, "A")
    link(vec(mat, "SSSColor", -450, 200, LEAF), "", sss, "B")
    sss2 = E(mat, unreal.MaterialExpressionMultiply, -50, 150)
    link(sss, "", sss2, "A")
    link(scalar(mat, "SSS", -250, 300, LEAF), "", sss2, "B")
    mel.connect_material_property(sss2, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
    flat = E(mat, unreal.MaterialExpressionLinearInterpolate, -650, 500)
    link(n, "RGB", flat, "A")
    link(E(mat, unreal.MaterialExpressionConstant3Vector, -900, 650, constant=unreal.LinearColor(0, 0, 1, 1)), "", flat, "B")
    link(scalar(mat, "NormalFlatten", -900, 750, LEAF), "", flat, "Alpha")
    mel.connect_material_property(flat, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(scalar(mat, "Roughness", -250, 400, LEAF), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(mat, "Specular", -250, 480, LEAF), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(t, "A", unreal.MaterialProperty.MP_OPACITY_MASK)
    finish(mat, path)
    return mat


def bark_material(bc, nm):
    """Same graph as tl_build.bark_material (M_TL_Bark), acacia textures / twig colour."""
    mat, path = new_material("M_TL_%s_Bark" % CAP)
    t = tex_param(mat, "BarkBC", bc, -900, 0)
    n = tex_param(mat, "BarkN", nm, -900, 400, normal=True)
    vc = E(mat, unreal.MaterialExpressionVertexColor, -900, -300)
    lp = E(mat, unreal.MaterialExpressionLinearInterpolate, -500, 0)
    link(t, "RGB", lp, "A")
    link(vec(mat, "TwigColor", -700, -150, BARK), "", lp, "B")
    link(vc, "R", lp, "Alpha")
    bb = E(mat, unreal.MaterialExpressionMultiply, -300, 0)
    link(lp, "", bb, "A")
    link(scalar(mat, "BarkBrightness", -500, 150, BARK), "", bb, "B")
    mel.connect_material_property(bb, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(n, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(scalar(mat, "Roughness", -500, 300, BARK), "", unreal.MaterialProperty.MP_ROUGHNESS)
    finish(mat, path)
    return mat


def audit(mesh):
    n = mesh.get_num_lods()
    b = mesh.get_bounds()
    return {"lods": n, "screens": [round(x, 4) for x in sub.get_lod_screen_sizes(mesh)], "triangles": [mesh.get_num_triangles(i) for i in range(n)],
            "vertices": [sub.get_number_verts(mesh, i) for i in range(n)], "sections": [mesh.get_num_sections(i) for i in range(n)],
            "section_slots": [[sub.get_lod_material_slot(mesh, i, s) for s in range(mesh.get_num_sections(i))] for i in range(n)],
            "slots": [str(m.get_editor_property("material_slot_name")) + "=" + m.material_interface.get_path_name().split(".")[0] for m in mesh.static_materials],
            "sphere_radius_cm": b.sphere_radius, "bounds_origin_cm": [b.origin.x, b.origin.y, b.origin.z],
            "bounds_extent_cm": [b.box_extent.x, b.box_extent.y, b.box_extent.z]}


def import_mesh(m_bark, m_leaf):
    if lib.does_directory_exist(DEST):
        raise RuntimeError("%s exists" % DEST)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    glb = lambda k: str(GAME / "glb" / ("%s_%s_lod%d.glb" % (SPECIES, PROFILE, k)))  # noqa: E731
    if not mgr.import_asset(DEST, unreal.InterchangeManager.create_source_data(glb(0)), params):
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
    rep["import_lods"] = {k: sub.import_lod(mesh, k, glb(k)) for k in (1, 2, 3)}
    for lod in range(mesh.get_num_lods()):
        bs = sub.get_lod_build_settings(mesh, lod)
        for prop, val in (("recompute_normals", False), ("recompute_tangents", True), ("use_mikk_t_space", True),
                          ("use_full_precision_u_vs", True), ("remove_degenerates", False), ("generate_lightmap_u_vs", False)):
            bs.set_editor_property(prop, val)
        sub.set_lod_build_settings(mesh, lod, bs)
    mesh.set_editor_property("static_materials", [unreal.StaticMaterial(material_interface=m_bark, material_slot_name="Bark"),
                                                  unreal.StaticMaterial(material_interface=m_leaf, material_slot_name="LeafCards")])
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


try:
    for d in ("/Game/HillsideForest", "/Game/HillsideForest/Trees"):
        ensure_dir(d)
    if LEAF_TAG and not MESH_ONLY:
        T = GAME / "textures"
        bc = import_texture(T / (ATLAS_STEM + "_BC.png"), "T_%s_LeafAtlas_BC" % LEAF_TAG, True, alpha_coverage=CLIP)
        nm = import_texture(T / (ATLAS_STEM + "_N.png"), "T_%s_LeafAtlas_N" % LEAF_TAG, False, normal=True)
        m_leaf = leaf_material(bc, nm, "M_TL_%s_LeafCards" % LEAF_TAG)
        m_bark = lib.load_asset(MAT_DIR + "/M_TL_%s_Bark" % CAP)
        if m_bark is None:
            raise RuntimeError("M_TL_%s_Bark missing" % CAP)
    elif MESH_ONLY:
        m_leaf = lib.load_asset(MAT_DIR + "/" + os.environ.get("ACW_AC_LEAF_MAT", "M_TL_%s_LeafCards" % CAP))
        m_bark = lib.load_asset(MAT_DIR + "/M_TL_%s_Bark" % CAP)
        if m_leaf is None or m_bark is None:
            raise RuntimeError("ACW_AC_MESH_ONLY: acacia materials missing")
    else:
        T = GAME / "textures"
        bc = import_texture(T / (ATLAS_STEM + "_BC.png"), "T_%s_LeafAtlas_BC" % CAP, True, alpha_coverage=CLIP)
        nm = import_texture(T / (ATLAS_STEM + "_N.png"), "T_%s_LeafAtlas_N" % CAP, False, normal=True)
        bbc = import_texture(T / ("T_%s_Bark_BC.png" % CAP), "T_%s_Bark_BC" % CAP, True)
        bnm = import_texture(T / ("T_%s_Bark_N.png" % CAP), "T_%s_Bark_N" % CAP, False, normal=True)
        m_leaf = leaf_material(bc, nm)
        m_bark = bark_material(bbc, bnm)
    import_mesh(m_bark, m_leaf)
    rep["leaf_defaults"], rep["bark_defaults"] = LEAF, BARK
    rep["status"] = "PASS_AC_IMPORT"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
rep["dest"], rep["profile"], rep["mesh_only"], rep["leaf_tag"], rep["clip"], rep["species"] = DEST, PROFILE, MESH_ONLY, LEAF_TAG, CLIP, SPECIES
write_report("ac_import.report.json", rep)
unreal.SystemLibrary.quit_editor()
