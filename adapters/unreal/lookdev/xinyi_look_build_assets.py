"""XinyiLook stage 1: materials + asset import (UE5.8, UnrealEditor-Cmd).

Creates, under /Game/XinyiLook:
  Materials/MPC_XinyiLook      Night / LitFrac / EmissiveScale (time of day)
  Materials/M_XinyiCity         ordinary buildings (shared HLSL, hero path off)
  Materials/M_Taipei101         hero tower (shared HLSL, hero path on)
  Materials/M_XinyiGround       Landscape (ground data texture + shared HLSL)
  Materials/M_XinyiRoadPaint    road paint geometry
  Materials/M_XinyiBackdrop     basin mountain ring
  Materials/M_XinyiFoliage      instanced street / park trees
  Textures/T_XinyiGround        2048^2 road SDF / green / class / water (linear)
  Meshes/Tiles/<tile>/...       25 look tiles (triangle soup = accepted tiles)
  Meshes/Hero, Backdrop, Paint, Tree

Every surface material is one Custom node running
tools/lookdev/shaders/xinyi_city.hlsl — the exact source the look-dev preview
renders — wrapped in a struct (no engine plugin / shader directory needed).
Per-vertex data travels in UV channels only (no vertex-colour import policy).

Fails closed on: missing inputs, UV-channel loss, tile bounds drift vs the
accepted contract (> 2 cm), missing assets after save.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.environ.get("ACW_REPO_ROOT", ""), "adapters", "unreal", "lookdev"))
sys.path.insert(0, os.path.join(os.environ.get("ACW_REPO_ROOT", ""), "tools", "lookdev"))
import unreal  # noqa: E402
from ue_custom_code import MATERIALS, custom_code, ground_uv_code  # noqa: E402
from xinyi_look_common import (  # noqa: E402
    CONTRACT_DIR, LOOK_OUT, MAT_DIR, MESH_DIR, MPC_PATH, SHADER, TEX_DIR, E0, E1, N0, N1,  # noqa: F401
    ensure_dir, lib, max_err, mel, mesh_bounds, read_json, tile_key, tools, write_report,
)

EXTENT_TOLERANCE_CM = 2.0
failures = []
created = {}


# ---------------------------------------------------------------------------
# Material construction helpers
# ---------------------------------------------------------------------------

def fresh_material(name):
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        lib.delete_asset(path)
    mat = tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError("failed to create material %s" % path)
    # iPhone-class discipline: opaque, full precision for world-space hashing,
    # no tessellation / refraction / translucency anywhere in this layer.
    for prop, val in (
        ("float_precision_mode", unreal.MaterialFloatPrecisionMode.MFPM_FULL),
        ("tangent_space_normal", False),
    ):
        try:
            mat.set_editor_property(prop, val)
        except Exception as exc:  # property names drift between engine versions
            unreal.log_warning("material %s: cannot set %s (%s)" % (name, prop, exc))
    return mat, path


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def mpc_param(mat, mpc, name, x, y):
    e = expr(mat, unreal.MaterialExpressionCollectionParameter, x, y)
    e.set_editor_property("collection", mpc)
    e.set_editor_property("parameter_name", name)
    return e


def texcoord(mat, index, x, y):
    return expr(mat, unreal.MaterialExpressionTextureCoordinate, x, y, coordinate_index=index)


def world_pos_m(mat, x, y):
    wp = expr(mat, unreal.MaterialExpressionWorldPosition, x, y)
    div = expr(mat, unreal.MaterialExpressionDivide, x + 180, y, const_b=100.0)
    mel.connect_material_expressions(wp, "", div, "A")
    return div


def custom(mat, x, y, code, inputs, outputs, desc, out_type=None):
    c = expr(mat, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("code", code)
    c.set_editor_property("description", desc)
    c.set_editor_property("output_type", out_type or unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ins = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    outs = []
    for n, t in outputs:
        co = unreal.CustomOutput()
        co.set_editor_property("output_name", n)
        co.set_editor_property("output_type", t)
        outs.append(co)
    c.set_editor_property("additional_outputs", outs)
    return c


F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3

SURFACE_OUTPUTS = [("Rough", F1), ("Metal", F1), ("Spec", F1), ("Emis", F3), ("NrmWS", F3)]


def finish_surface(mat, node, emis_scale, x, y, normal=True):
    mel.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(node, "Rough", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(node, "Metal", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(node, "Spec", unreal.MaterialProperty.MP_SPECULAR)
    mul = expr(mat, unreal.MaterialExpressionMultiply, x, y)
    mel.connect_material_expressions(node, "Emis", mul, "A")
    mel.connect_material_expressions(emis_scale, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if normal:
        mel.connect_material_property(node, "NrmWS", unreal.MaterialProperty.MP_NORMAL)


def save_material(mat, path):
    mel.recompile_material(mat)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    created[path] = "Material"


def build_mpc():
    if lib.does_asset_exist(MPC_PATH):
        lib.delete_asset(MPC_PATH)
    mpc = tools.create_asset("MPC_XinyiLook", MAT_DIR, unreal.MaterialParameterCollection,
                             unreal.MaterialParameterCollectionFactoryNew())
    params = []
    for name, default in (("Night", 0.0), ("LitFrac", 0.08), ("EmissiveScale", 1.0)):
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", name)
        p.set_editor_property("default_value", default)
        params.append(p)
    mpc.set_editor_property("scalar_parameters", params)
    if not lib.save_asset(MPC_PATH):
        raise RuntimeError("failed to save MPC")
    created[MPC_PATH] = "MaterialParameterCollection"
    return mpc


def build_city_material(mpc, name, hero):
    mat, path = fresh_material(name)
    wp = world_pos_m(mat, -1200, -300)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -150)
    uv0, uv1, uv2 = texcoord(mat, 0, -1200, 0), texcoord(mat, 1, -1200, 120), texcoord(mat, 2, -1200, 240)
    night = mpc_param(mat, mpc, "Night", -1200, 360)
    lit = mpc_param(mat, mpc, "LitFrac", -1200, 480)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -700, 0, custom_code(name), [n for n, _ in MATERIALS[name][0]], SURFACE_OUTPUTS, name)
    for src, pin in ((wp, "WP"), (n, "N"), (uv0, "UV0"), (uv1, "UV1"), (uv2, "UV2"),
                     (night, "Night"), (lit, "LitFrac")):
        mel.connect_material_expressions(src, "", node, pin)
    finish_surface(mat, node, es, -300, 300)
    save_material(mat, path)
    return mat


def ground_uv(mat, wp, x, y):
    c = custom(mat, x, y, ground_uv_code(E0, E1, N0, N1), ["WP"], [], "XinyiGroundUV", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    mel.connect_material_expressions(wp, "", c, "WP")
    return c


def ground_sample(mat, tex, uv, x, y):
    s = expr(mat, unreal.MaterialExpressionTextureSample, x, y)
    s.set_editor_property("texture", tex)
    s.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    mel.connect_material_expressions(uv, "", s, "UVs")
    return s


def build_ground_material(mpc, tex):
    mat, path = fresh_material("M_XinyiGround")
    wp = world_pos_m(mat, -1400, -200)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -60)
    uv = ground_uv(mat, wp, -1100, 100)
    gt = ground_sample(mat, tex, uv, -900, 100)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code("M_XinyiGround"), [n for n, _ in MATERIALS["M_XinyiGround"][0]], SURFACE_OUTPUTS, "M_XinyiGround")
    for src, pin in ((wp, "WP"), (n, "N"), (gt, "GT"), (night, "Night")):
        mel.connect_material_expressions(src, "", node, pin)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


def build_paint_material(mpc, tex):
    mat, path = fresh_material("M_XinyiRoadPaint")
    wp = world_pos_m(mat, -1400, -200)
    uv2 = texcoord(mat, 2, -1200, -40)
    uv = ground_uv(mat, wp, -1100, 100)
    gt = ground_sample(mat, tex, uv, -900, 100)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code("M_XinyiRoadPaint"), [n for n, _ in MATERIALS["M_XinyiRoadPaint"][0]], SURFACE_OUTPUTS, "M_XinyiRoadPaint")
    for src, pin in ((wp, "WP"), (uv2, "UV2"), (gt, "GT"), (night, "Night")):
        mel.connect_material_expressions(src, "", node, pin)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


def build_backdrop_material(mpc):
    mat, path = fresh_material("M_XinyiBackdrop")
    wp = world_pos_m(mat, -1400, -200)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -60)
    uv2 = texcoord(mat, 2, -1200, 60)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code("M_XinyiBackdrop"), [n for n, _ in MATERIALS["M_XinyiBackdrop"][0]], SURFACE_OUTPUTS, "M_XinyiBackdrop")
    for src, pin in ((wp, "WP"), (n, "N"), (uv2, "UV2"), (night, "Night")):
        mel.connect_material_expressions(src, "", node, pin)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


def build_foliage_material(mpc):
    mat, path = fresh_material("M_XinyiFoliage")
    for prop, val in (("two_sided", True), ("used_with_instanced_static_meshes", True)):
        try:
            mat.set_editor_property(prop, val)
        except Exception as exc:
            unreal.log_warning("foliage material: cannot set %s (%s)" % (prop, exc))
    wp = world_pos_m(mat, -1400, -200)
    n = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1200, -60)
    uv2 = texcoord(mat, 2, -1200, 60)
    var = expr(mat, unreal.MaterialExpressionPerInstanceCustomData, -1200, 180, data_index=0)
    night = mpc_param(mat, mpc, "Night", -1200, 300)
    es = mpc_param(mat, mpc, "EmissiveScale", -600, 500)
    node = custom(mat, -600, 0, custom_code("M_XinyiFoliage"), [n for n, _ in MATERIALS["M_XinyiFoliage"][0]], SURFACE_OUTPUTS, "M_XinyiFoliage")
    for src, pin in ((wp, "WP"), (n, "N"), (uv2, "UV2"), (var, "Variant"), (night, "Night")):
        mel.connect_material_expressions(src, "", node, pin)
    finish_surface(mat, node, es, -300, 300, normal=False)
    save_material(mat, path)
    return mat


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def import_texture(png, name):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(png))
    task.set_editor_property("destination_path", TEX_DIR)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    tools.import_asset_tasks([task])
    path = TEX_DIR + "/" + name
    tex = lib.load_asset(path)
    if tex is None:
        raise RuntimeError("texture import failed: %s" % png)
    # data texture: linear, lossless (SDF edges + class ids must not be BC-crushed)
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    created[path] = "Texture2D"
    return tex


def import_mesh(glb, dest, material, min_uv_channels):
    if lib.does_directory_exist(dest):
        lib.delete_directory(dest)
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    source = unreal.InterchangeManager.create_source_data(str(glb))
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    if not mgr.import_asset(dest, source, params):
        raise RuntimeError("Interchange import_asset returned false: %s" % glb)
    meshes = []
    for p in lib.list_assets(dest, recursive=True):
        obj = lib.load_asset(p)
        if obj is not None and obj.get_class().get_name() == "StaticMesh":
            meshes.append((str(p).split(".")[0], obj))
    if len(meshes) != 1:
        raise RuntimeError("%s produced %d StaticMesh assets, expected 1" % (glb, len(meshes)))
    path, mesh = meshes[0]
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    # Mobile-first: no Nanite; keep authored normals; full-precision UVs carry
    # metre-scale facade coordinates + packed data; never drop triangles.
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    bs = sub.get_lod_build_settings(mesh, 0)
    for prop, val in (("recompute_normals", False), ("recompute_tangents", True),
                      ("use_full_precision_u_vs", True), ("remove_degenerates", False),
                      ("generate_lightmap_u_vs", False)):
        try:
            bs.set_editor_property(prop, val)
        except Exception as exc:
            unreal.log_warning("build settings %s: %s" % (prop, exc))
    sub.set_lod_build_settings(mesh, 0, bs)
    uvs = int(sub.get_num_uv_channels(mesh, 0))
    if uvs < min_uv_channels:
        raise RuntimeError("%s imported with %d UV channels, expected >= %d" % (glb, uvs, min_uv_channels))
    for i in range(max(1, len(mesh.static_materials))):
        mesh.set_material(i, material)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save %s" % path)
    created[path] = "StaticMesh"
    return path, mesh


def main():
    t0 = time.perf_counter()
    for d in (MAT_DIR, TEX_DIR, MESH_DIR):
        ensure_dir(d)

    look = read_json(LOOK_OUT / "look_tiles.report.json")
    hero = read_json(LOOK_OUT / "hero/taipei101.anchor.json")
    backdrop = read_json(LOOK_OUT / "backdrop/taipei_basin_backdrop.json")
    ground = read_json(LOOK_OUT / "ground/ground.report.json")
    contract = read_json(CONTRACT_DIR / "xinyi_unreal_v2_contract.json")
    if look.get("status") != "PASS_LOOK_TILES" or len(look["tiles"]) != 25:
        raise RuntimeError("look tiles report is not PASS_LOOK_TILES with 25 tiles")
    crow = {r["tile"]: r for r in contract["tiles"]}

    mpc = build_mpc()
    tex = import_texture(LOOK_OUT / "ground/xinyi_ground_2048.png", "T_XinyiGround")
    m_city = build_city_material(mpc, "M_XinyiCity", hero=False)
    m_hero = build_city_material(mpc, "M_Taipei101", hero=True)
    m_ground = build_ground_material(mpc, tex)
    m_paint = build_paint_material(mpc, tex)
    m_back = build_backdrop_material(mpc)
    m_tree = build_foliage_material(mpc)

    tiles = []
    for row in look["tiles"]:
        tile = row["tile"]
        try:
            path, mesh = import_mesh(LOOK_OUT / "tiles" / row["path"], MESH_DIR + "/Tiles/" + tile_key(tile), m_city, 3)
            origin, extent = mesh_bounds(mesh)
            exp_extent = crow[tile]["runtime_expected_ue_local_bounds_extent_cm"]
            err = max_err(extent, exp_extent)
            if err > EXTENT_TOLERANCE_CM:
                raise RuntimeError("extent drift %.3f cm vs accepted runtime tile" % err)
            tiles.append({
                "tile": tile, "asset_path": path, "triangles": row["triangles"],
                "imported_bounds_origin_cm": origin, "imported_bounds_extent_cm": extent,
                "expected_local_bounds_origin_cm": crow[tile]["runtime_expected_ue_local_bounds_origin_cm"],
                "tile_world_translation_cm": crow[tile]["expected_ue_translation_cm"],
                "extent_error_cm": err,
            })
        except Exception as exc:
            failures.append({"tile": tile, "error": str(exc)})

    singles = {}
    for key, glb, dest, mat, uvn, exp in (
        ("hero", LOOK_OUT / "hero/taipei101.glb", MESH_DIR + "/Hero", m_hero, 3, hero["expected_ue_local_bounds"]),
        ("backdrop", LOOK_OUT / "backdrop/taipei_basin_backdrop.glb", MESH_DIR + "/Backdrop", m_back, 3,
         backdrop["expected_ue_local_bounds"]),
        ("paint", LOOK_OUT / "ground/xinyi_road_paint.glb", MESH_DIR + "/RoadPaint", m_paint, 3,
         ground["paint_expected_ue_local_bounds"]),
        ("tree", LOOK_OUT / "ground/xinyi_tree.glb", MESH_DIR + "/Tree", m_tree, 3,
         ground["tree_expected_ue_local_bounds"]),
    ):
        try:
            path, mesh = import_mesh(glb, dest, mat, uvn)
            origin, extent = mesh_bounds(mesh)
            err = max_err(extent, exp["extent_cm"])
            if err > EXTENT_TOLERANCE_CM:
                raise RuntimeError("extent drift %.3f cm" % err)
            singles[key] = {"asset_path": path, "imported_bounds_origin_cm": origin,
                            "expected_bounds_origin_cm": exp["origin_cm"], "extent_error_cm": err}
        except Exception as exc:
            failures.append({"asset": key, "error": str(exc)})

    status = "PASS_LOOK_ASSETS" if not failures and len(tiles) == 25 and len(singles) == 4 else "FAIL_LOOK_ASSETS"
    report = {
        "status": status,
        "materials": {"city": "M_XinyiCity", "hero": "M_Taipei101", "ground": "M_XinyiGround",
                      "paint": "M_XinyiRoadPaint", "backdrop": "M_XinyiBackdrop", "foliage": "M_XinyiFoliage",
                      "mpc": MPC_PATH},
        "shader_source": str(SHADER),
        "tiles": tiles,
        "singles": singles,
        "created": created,
        "failures": failures,
        "elapsed_seconds": time.perf_counter() - t0,
        "scope": "visual layer under /Game/XinyiLook only; /Game/XinyiV2 untouched",
    }
    write_report("look_assets.report.json", report)
    if status != "PASS_LOOK_ASSETS":
        raise RuntimeError("XinyiLook asset stage failed: %s" % json.dumps(failures)[:2000])


main()
