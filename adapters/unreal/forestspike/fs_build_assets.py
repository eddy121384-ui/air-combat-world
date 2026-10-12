"""ForestSpike B0 stage 1: textures, meshes, materials (UE5.8, UnrealEditor-Cmd).

Creates under /Game/ForestSpike (this isolated project only):
  Textures/T_FS_FieldCore, T_FS_FieldCtx     RGBA8 linear field textures (R forest, G edge dist, B slope)
  Meshes/Terrain_Core, Terrain_Context       deterministic test terrain (imported GLB)
  Meshes/Tree_A                              28-tri Xinyi reference (PR #18 xinyi_reference_preview_lod0.glb)
  Meshes/Tree_B_<archetype>                  PR #18 archetypes (LOD0 import + authored LOD1/2 import attempt)
  Materials/M_FS_Ground, M_FS_Tree           one Custom node each running tools/forestspike/shaders/fs_forest.hlsl
  Materials/MI_FS_Ground_SOn / _SOff / _SCoreOnly ...   constant instances: the far-canopy factor S as a material parameter
  Materials/MI_FS_Tree_A / _B                ArmId = 5 / 6 (only the debug ID differs; shading is identical)

Fails closed on missing inputs, bounds drift (> 2 cm after pivot correction) and failed saves.
"""
import json
import sys
import traceback

sys.path.insert(0, __import__("os").path.dirname(__file__))
import unreal  # noqa: E402
from fs_common import (  # noqa: E402
    INPUTS, MAT_DIR, MESH_DIR, MODELS, SHADER, TEX_DIR, ensure_dir, lib, mel, mesh_bounds, read_json, tools, write_report,
)

failures = []
created = {}
F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F2 = unreal.CustomMaterialOutputType.CMOT_FLOAT2
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3
ARCHETYPES = ["dense_rounded", "horizontal_tiered", "open_vase", "tall_columnar"]


# ---------------------------------------------------------------------------- material helpers
def fresh_material(name):
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        mat = lib.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    if mat is None:
        raise RuntimeError("failed to create material " + path)
    for prop, val in (("float_precision_mode", unreal.MaterialFloatPrecisionMode.MFPM_FULL),
                      ("tangent_space_normal", False), ("two_sided", True)):
        try:
            mat.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("material %s: cannot set %s (%s)" % (name, prop, exc))
    return mat, path


def expr(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar_param(mat, name, default, x, y):
    e = expr(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", default)
    return e


def world_pos_m(mat, x, y):
    wp = expr(mat, unreal.MaterialExpressionWorldPosition, x, y)
    div = expr(mat, unreal.MaterialExpressionDivide, x + 180, y, const_b=100.0)
    mel.connect_material_expressions(wp, "", div, "A")
    return div


def camera_pos_m(mat, x, y):
    cp = expr(mat, unreal.MaterialExpressionCameraPositionWS, x, y)
    div = expr(mat, unreal.MaterialExpressionDivide, x + 180, y, const_b=100.0)
    mel.connect_material_expressions(cp, "", div, "A")
    return div


def custom(mat, x, y, code, inputs, outputs, desc, out_type=F3):
    c = expr(mat, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("code", code)
    c.set_editor_property("description", desc)
    c.set_editor_property("output_type", out_type)
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


def wire(pairs, node):
    for item in pairs:
        src, pin = item[0], item[1]
        out = item[2] if len(item) > 2 else ""
        if not mel.connect_material_expressions(src, out, node, pin):
            raise RuntimeError("failed to connect %s -> %s" % (out or "default", pin))


def finish_surface(node):
    mel.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(node, "Rough", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(node, "Spec", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(node, "Emis", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(node, "NrmWS", unreal.MaterialProperty.MP_NORMAL)


def save_material(mat, path):
    mel.recompile_material(mat)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save " + path)
    created[path] = "Material"


SURFACE_OUT = [("Rough", F1), ("Spec", F1), ("Emis", F3), ("NrmWS", F3)]


def wrap(call):
    return ("struct FSFns {\n" + SHADER.read_text(encoding="utf-8") + "\n};\nFSFns f;\n"
            "float3 b; float r; float s; float3 e; float3 n;\n" + call + "\n"
            "Rough = r; Spec = s; Emis = e; NrmWS = n;\nreturn b;\n")


UV_CODE = ("float2 en = float2(WP.x, -WP.y);\nUVX = (en + 3000.0) / 6000.0;\nreturn (en + 500.0) / 1000.0;\n")


def build_ground(tex_core, tex_ctx):
    mat, path = fresh_material("M_FS_Ground")
    wp = world_pos_m(mat, -1500, -200)
    nrm = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1500, -60)
    cam = camera_pos_m(mat, -1500, 80)
    uv = custom(mat, -1250, 200, UV_CODE, ["WP"], [("UVX", F2)], "FS_FieldUV", F2)
    wire([(wp, "WP")], uv)
    samples = []
    for tex, pin, y in ((tex_core, "", 120), (tex_ctx, "UVX", 300)):
        s = expr(mat, unreal.MaterialExpressionTextureSample, -1000, y)
        s.set_editor_property("texture", tex)
        s.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
        mel.connect_material_expressions(uv, pin, s, "UVs")
        samples.append(s)
    params = {}
    for i, (name, default) in enumerate((("SCore", 1.0), ("SCtx", 1.0), ("dS", 600.0), ("wS", 120.0),
                                          ("Und", 1.0), ("Dbg", 0.0), ("IdGamma", 1.0))):
        params[name] = scalar_param(mat, name, default, -1500, 420 + 70 * i)
    code = wrap("f.fs_ground(WP, N, Cam, FC, FX, SCore, SCtx, dS, wS, Und, Dbg, IdGamma, b, r, s, e, n);")
    names = ["WP", "N", "Cam", "FC", "FX", "SCore", "SCtx", "dS", "wS", "Und", "Dbg", "IdGamma"]
    node = custom(mat, -600, 0, code, names, SURFACE_OUT, "M_FS_Ground")
    pairs = [(wp, "WP"), (nrm, "N"), (cam, "Cam"), (samples[0], "FC", "RGBA"), (samples[1], "FX", "RGBA")]
    pairs += [(params[k], k) for k in ("SCore", "SCtx", "dS", "wS", "Und", "Dbg", "IdGamma")]
    wire(pairs, node)
    finish_surface(node)
    save_material(mat, path)
    return mat


def build_tree():
    mat, path = fresh_material("M_FS_Tree")
    for prop, val in (("used_with_instanced_static_meshes", True),):
        try:
            mat.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("M_FS_Tree: cannot set %s (%s)" % (prop, exc))
    wp = world_pos_m(mat, -1500, -200)
    nrm = expr(mat, unreal.MaterialExpressionVertexNormalWS, -1500, -60)
    cam = camera_pos_m(mat, -1500, 80)
    vc = expr(mat, unreal.MaterialExpressionVertexColor, -1500, 220)
    var = expr(mat, unreal.MaterialExpressionPerInstanceCustomData, -1500, 320, data_index=0)
    u = expr(mat, unreal.MaterialExpressionPerInstanceCustomData, -1500, 400, data_index=1)
    dbg = scalar_param(mat, "Dbg", 0.0, -1500, 480)
    arm = scalar_param(mat, "ArmId", 5.0, -1500, 550)
    gam = scalar_param(mat, "IdGamma", 1.0, -1500, 620)
    code = wrap("f.fs_tree(WP, N, Cam, VC, Var, U, Dbg, ArmId, IdGamma, b, r, s, e, n);")
    node = custom(mat, -600, 0, code, ["WP", "N", "Cam", "VC", "Var", "U", "Dbg", "ArmId", "IdGamma"], SURFACE_OUT, "M_FS_Tree")
    wire([(wp, "WP"), (nrm, "N"), (cam, "Cam"), (vc, "VC"), (var, "Var"), (u, "U"), (dbg, "Dbg"), (arm, "ArmId"),
          (gam, "IdGamma")], node)
    finish_surface(node)
    save_material(mat, path)
    return mat


def make_mic(name, parent, scalars):
    path = MAT_DIR + "/" + name
    if lib.does_asset_exist(path):
        mic = lib.load_asset(path)
    else:
        mic = tools.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mic.set_editor_property("parent", parent)
    for k, v in scalars.items():
        mel.set_material_instance_scalar_parameter_value(mic, k, float(v))
    mel.update_material_instance(mic)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save " + path)
    created[path] = "MaterialInstanceConstant"
    return mic


# ---------------------------------------------------------------------------- textures / meshes
def import_field(png, name):
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
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save " + path)
    created[path] = "Texture2D"
    return tex


def import_mesh(glb, dest_dir, asset_name, material):
    dest = MESH_DIR + "/" + dest_dir
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
    ns = mesh.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled"):
        ns.set_editor_property("enabled", False)
        sub.set_nanite_settings(mesh, ns, True)
    bs = sub.get_lod_build_settings(mesh, 0)
    for prop, val in (("recompute_normals", False), ("recompute_tangents", True), ("use_full_precision_u_vs", True),
                      ("remove_degenerates", False), ("generate_lightmap_u_vs", False)):
        try:
            bs.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("build settings %s: %s" % (prop, exc))
    sub.set_lod_build_settings(mesh, 0, bs)
    for i in range(max(1, len(mesh.static_materials))):
        mesh.set_material(i, material)
    if not lib.save_asset(path):
        raise RuntimeError("failed to save " + path)
    created[path] = "StaticMesh"
    return path, mesh


def auto_lods(mesh):
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    opts = unreal.EditorScriptingMeshReductionOptions()
    settings = []
    for pct, screen in ((1.0, 1.0), (0.5, 0.12), (0.25, 0.04)):
        r = unreal.EditorScriptingMeshReductionSettings()
        r.set_editor_property("percent_triangles", pct)
        r.set_editor_property("screen_size", screen)
        settings.append(r)
    opts.set_editor_property("reduction_settings", settings)
    opts.set_editor_property("auto_compute_lod_screen_size", False)
    return int(sub.set_lods(mesh, opts))


def info(mesh, path, expected):
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    o, ext = mesh_bounds(mesh)
    eo, ee = expected["origin_cm"], expected["extent_cm"]
    return {
        "asset": path,
        "lods": int(sub.get_lod_count(mesh)),
        "triangles_lod0": int(mesh.get_num_triangles(0)) if hasattr(mesh, "get_num_triangles") else None,
        "has_vertex_colors": bool(mesh.get_editor_property("has_vertex_colors")) if "has_vertex_colors" in dir(mesh) else None,
        "imported_bounds_origin_cm": o,
        "imported_bounds_extent_cm": ext,
        "expected_bounds_origin_cm": eo,
        "expected_bounds_extent_cm": ee,
        "extent_err_cm": max(abs(ext[i] - ee[i]) for i in range(3)),
        "pivot_shift_cm": [eo[i] - o[i] for i in range(3)],
    }


def main():
    manifest = read_json(INPUTS / "inputs.manifest.json")
    bounds = read_json(INPUTS / "bounds.json")
    for d in (MAT_DIR, TEX_DIR, MESH_DIR):
        ensure_dir(d)
    tex_core = import_field(INPUTS / "field_core.png", "T_FS_FieldCore")
    tex_ctx = import_field(INPUTS / "field_ctx.png", "T_FS_FieldCtx")
    ground = build_ground(tex_core, tex_ctx)
    tree = build_tree()
    mics = {
        "MI_FS_Ground_SOn": {"SCore": 1, "SCtx": 1, "Und": 1},
        "MI_FS_Ground_SOff": {"SCore": 0, "SCtx": 0, "Und": 1},
        "MI_FS_Ground_SCtxOnly": {"SCore": 0, "SCtx": 1, "Und": 1},
    }
    for name, sc in mics.items():
        make_mic(name, ground, sc)
    mic_a = make_mic("MI_FS_Tree_A", tree, {"ArmId": 5})
    mic_b = make_mic("MI_FS_Tree_B", tree, {"ArmId": 6})

    meshes = {}
    # terrain: core / context
    for key, glb in (("Terrain_Core", "terrain_core.glb"), ("Terrain_Context", "terrain_context.glb")):
        gmat = lib.load_asset(MAT_DIR + "/MI_FS_Ground_SOn")
        path, mesh = import_mesh(INPUTS / glb, key, key, gmat)
        meshes[key] = info(mesh, path, bounds[glb])
    # arm A: 28-tri Xinyi reference (shared-material counterpart) + engine auto LODs as in the Xinyi tree layer
    path, mesh = import_mesh(MODELS / "xinyi_reference_preview_lod0.glb", "Tree_A", "Tree_A", mic_a)
    meshes["Tree_A"] = info(mesh, path, bounds["xinyi_reference_preview_lod0.glb"])
    meshes["Tree_A"]["auto_lods_set"] = auto_lods(mesh)
    lib.save_asset(path)
    meshes["Tree_A"]["lods"] = int(unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).get_lod_count(mesh))
    # arm B: PR #18 archetypes; try authored LOD1 / LOD2 via import_lod
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for arch in ARCHETYPES:
        path, mesh = import_mesh(MODELS / (arch + "_lod0.glb"), "Tree_B_" + arch, "Tree_B_" + arch, mic_b)
        rec = info(mesh, path, bounds[arch + "_lod0.glb"])
        rec["authored_lod_import"] = {}
        for lod in (1, 2):
            try:
                r = sub.import_lod(mesh, lod, str(MODELS / ("%s_lod%d.glb" % (arch, lod))))
                rec["authored_lod_import"][str(lod)] = int(r)
            except Exception as exc:  # noqa: BLE001
                rec["authored_lod_import"][str(lod)] = "ERR %s" % exc
        rec["lods_after_import_lod"] = int(sub.get_lod_count(mesh))
        lib.save_asset(path)
        meshes["Tree_B_" + arch] = rec
    for k, rec in meshes.items():
        if rec["extent_err_cm"] > 2.0:
            failures.append({"mesh": k, "extent_err_cm": rec["extent_err_cm"]})
    return meshes, manifest


try:
    meshes, manifest = main()
    status = "PASS_FS_ASSETS" if not failures else "FAIL_FS_ASSETS"
    err = None
except Exception:  # noqa: BLE001
    meshes, manifest, status, err = {}, {}, "FAIL_FS_ASSETS", traceback.format_exc()
    unreal.log_error(err)
write_report("fs_assets.report.json", {"status": status, "failures": failures, "created": created, "meshes": meshes,
                                       "inputs_manifest_world": manifest.get("world"), "error": err})
unreal.SystemLibrary.quit_editor()
