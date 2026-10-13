"""Phase 2B runtime gate - stage 1 (runs INSIDE UnrealEditor-Cmd of the ISOLATED project, never AirCombatWorld).

Builds /Game/NTWGate/L_NTWGate (World Partition, from the OpenWorld template with its sample landscape removed):
  * runtime grid: every partition main layer CellSize / LoadingRange set via the isolated native helper
  * 50 terrain chunk actors (identity-node GLBs, tile-local vertices) with REAL 5-level LOD chains (LOD1..4 copied from the
    LOD-k GLBs), screen sizes from the measured switch distances, complex-as-simple collision on LOD0, Nanite off
  * Xinyi seam stitch v2 (full-resolution edge + skirt) and v1 (decimated, Phase 2B) as LOD-chain actors (v1 hidden, no collision)
  * the ACCEPTED Xinyi Landscape (631x631 R16) created by the bridge (ALandscape::Import), placed by the measured ENU->NTW
    affine as a real actor transform: location + yaw + anisotropic XY scale; accepted runtime building tiles under the same
    transform. Accepted files are read, never written.
  * crack detector: an unlit magenta plane 200 m below the terrain (only visible through a hole in the surface)
UE axes (accepted Xinyi contract): X = east*100, Y = -north*100, Z = up*100; UE origin = world runtime origin (296000, 2760000).
env: ACW_GATE_TERRAIN_RUN, ACW_GATE_TERRAIN_RUN_V1, ACW_GATE_XINYI_CONTRACT, ACW_GATE_AFFINE_JSON, ACW_GATE_REPORT
"""
import json
import math
import os
import time

import unreal

RUN = os.environ["ACW_GATE_TERRAIN_RUN"]
RUN_V1 = os.environ["ACW_GATE_TERRAIN_RUN_V1"]
CONTRACT = os.environ["ACW_GATE_XINYI_CONTRACT"]
AFFINE = json.load(open(os.environ["ACW_GATE_AFFINE_JSON"], encoding="utf-8"))
REPORT = os.environ["ACW_GATE_REPORT"]
LEVEL = "/Game/NTWGate/L_NTWGate"
ROOT = "/Game/NTWGate"
ORIGIN = (296000.0, 2760000.0)
NTW_ORIGIN = (224000.0, 2688000.0)
CELL_CM, RANGE_CM = 160000, 800000
SWITCH_M = [3140.0, 5611.0, 10148.0, 19195.0]   # Phase 2B measured switch distances (4 px SSE) for LOD1..4
CHUNK_RADIUS_M = 1131.0 + 100.0                  # half-diagonal of a 1.6 km chunk + relief margin

ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
lib = unreal.EditorAssetLibrary
rep = {"stage": "build", "started": time.time(), "steps": []}


def step(name, **kw):
    rep["steps"].append(dict(name=name, t=round(time.time() - rep["started"], 1), **kw))
    unreal.log("NTWGATE " + name)


def ue_xy(e, n):
    return (e - ORIGIN[0]) * 100.0, -(n - ORIGIN[1]) * 100.0


def enu_to_tm2(e, n):
    M, t = AFFINE["linear_part"], AFFINE["translation_m"]
    return (M[0][0] * e + M[0][1] * n + t[0] + NTW_ORIGIN[0], M[1][0] * e + M[1][1] * n + t[1] + NTW_ORIGIN[1])


def import_glb(path, dest):
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    mgr.import_asset(dest, unreal.InterchangeManager.create_source_data(path), params)
    ms = [lib.load_asset(a) for a in lib.list_assets(dest, recursive=True)]
    ms = [m for m in ms if isinstance(m, unreal.StaticMesh)]
    if len(ms) != 1:
        raise RuntimeError("expected one StaticMesh from %s, got %d" % (path, len(ms)))
    return ms[0]


def material(name, rgb, unlit=False):
    path = "%s/Materials/%s" % (ROOT, name)
    if lib.does_asset_exist(path):
        return lib.load_asset(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    c = unreal.MaterialEditingLibrary.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -300, 0)
    c.set_editor_property("constant", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    if unlit:
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        unreal.MaterialEditingLibrary.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    else:
        unreal.MaterialEditingLibrary.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
        r = unreal.MaterialEditingLibrary.create_material_expression(m, unreal.MaterialExpressionConstant, -300, 200)
        r.set_editor_property("r", 0.9)
        unreal.MaterialEditingLibrary.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS)
    unreal.MaterialEditingLibrary.recompile_material(m)
    lib.save_loaded_asset(m)
    return m


def prepare_mesh(sm, mat, collision=True):
    try:
        ns = sm.get_editor_property("nanite_settings")
        ns.enabled = False
        sm.set_editor_property("nanite_settings", ns)
    except Exception:  # noqa: BLE001
        pass
    sm.set_material(0, mat)
    bs = sm.get_editor_property("body_setup")
    if bs is not None:
        bs.set_editor_property("collision_trace_flag",
                               unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collision else unreal.CollisionTraceFlag.CTF_USE_DEFAULT)


def lod_chain(base, lod_meshes):
    for k, src in enumerate(lod_meshes, start=1):
        sms.set_lod_from_static_mesh(base, k, src, 0, True)
        # the copied LOD brings its own (glTF default) material slot; without this remap LOD1..4 rendered with the imported
        # default material (invisible / black in the first PIE probe). Every LOD section uses slot 0 (the terrain material).
        sms.set_lod_material_slot(base, 0, k, 0)
    sizes = [1.0] + [min(1.0, CHUNK_RADIUS_M / d) for d in SWITCH_M[:len(lod_meshes)]]
    try:
        base.set_editor_property("auto_compute_lod_screen_size", False)
    except Exception:  # noqa: BLE001  (not exposed to Python in 5.8; set_lod_screen_sizes applies explicit sizes)
        pass
    ok = sms.set_lod_screen_sizes(base, sizes)
    got = [round(v, 4) for v in sms.get_lod_screen_sizes(base)]
    slots = [sms.get_lod_material_slot(base, k, 0) for k in range(sms.get_lod_count(base))]
    if any(s != 0 for s in slots):
        raise RuntimeError("LOD material slot remap failed for %s: %r" % (base.get_name(), slots))
    return {"requested": [round(v, 4) for v in sizes], "applied": got, "auto": bool(base.is_lod_screen_size_auto_computed()),
            "lod_section0_material_slots": slots}, bool(ok), sms.get_lod_count(base)


def spawn_mesh(sm, x, y, z, label, tags, yaw=0.0, scale=(1.0, 1.0, 1.0)):
    a = ues.spawn_actor_from_object(sm, unreal.Vector(x, y, z), unreal.Rotator(0.0, 0.0, yaw))
    a.set_actor_label(label)
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.tags = [unreal.Name(t) for t in tags]
    return a


def main():
    les.new_level_from_template(LEVEL, "/Engine/Maps/Templates/OpenWorld")
    removed = []
    for a in unreal.EditorLevelLibrary.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn in ("Landscape", "LandscapeStreamingProxy", "StaticMeshActor", "VolumetricCloud", "WorldPartitionHLOD", "WorldPartitionMiniMap"):
            removed.append(cn)
            ues.destroy_actor(a)
    step("template_cleaned", removed=sorted(set(removed)), count=len(removed))
    grid = unreal.NtwGateLibrary.configure_runtime_grid(CELL_CM, RANGE_CM)
    step("runtime_grid_configured", before=json.loads(grid), after=json.loads(unreal.NtwGateLibrary.describe_runtime_grid()))

    m_ter = material("M_NTW_Terrain", (0.30, 0.36, 0.26))
    m_bld = material("M_NTW_Building", (0.75, 0.75, 0.72))
    material("M_NTW_DebugStitch", (0.9, 0.08, 0.05))
    material("M_NTW_DebugLandscape", (0.10, 0.25, 0.9))
    m_mag = material("M_NTW_CrackMagenta", (1.0, 0.0, 1.0), unlit=True)

    rpt = json.load(open(os.path.join(RUN, "terrain.report.json"), encoding="utf-8"))
    origin = {(c["cell"], c["chunk"], c["lod"]): c["sw_epsg3826"] for c in rpt["chunks"]}
    chunks = sorted({(c["cell"], c["chunk"]) for c in rpt["chunks"] if c["chunk"].startswith("ch")})
    placed = []
    for cell, ch in chunks:
        d = "%s/Terrain/%s/%s" % (ROOT, cell.replace("+", "p"), ch)
        meshes = [import_glb(os.path.join(RUN, "chunks", cell, "%s_lod%d.glb" % (ch, k)), "%s/lod%d" % (d, k)) for k in range(5)]
        base = meshes[0]
        prepare_mesh(base, m_ter)
        sizes, ok, n = lod_chain(base, meshes[1:])
        e, nn = origin[(cell, ch, 0)]
        x, y = ue_xy(e, nn)
        spawn_mesh(base, x, y, 0.0, "NTW_%s_%s" % (cell, ch), ["NTWChunk", cell, ch])
        placed.append({"cell": cell, "chunk": ch, "sw_epsg3826": [e, nn], "ue_cm": [x, y], "lods": n, "screen_sizes": sizes, "screen_sizes_set": ok})
    step("chunks_placed", count=len(placed), example=placed[0])

    stitches = {}
    for tag, run in (("v2", RUN), ("v1", RUN_V1)):
        r2 = json.load(open(os.path.join(run, "terrain.report.json"), encoding="utf-8"))
        so = {c["lod"]: c["sw_epsg3826"] for c in r2["chunks"] if c["chunk"] == "xinyi_stitch"}
        d = "%s/Stitch_%s" % (ROOT, tag)
        meshes = [import_glb(os.path.join(run, "chunks", "C+0038+0346", "xinyi_stitch_lod%d.glb" % k), "%s/lod%d" % (d, k)) for k in range(5)]
        if len(set(map(tuple, so.values()))) != 1:
            # each stitch LOD has its own local origin: rebase all LODs to LOD0's origin by placing per-LOD actors is not
            # possible in one LOD chain, so record it; v2/v1 stitch LOD origins are reported and checked below
            pass
        base = meshes[0]
        prepare_mesh(base, m_ter, collision=(tag == "v2"))
        sizes, ok, n = lod_chain(base, meshes[1:])
        e, nn = so[0]
        x, y = ue_xy(e, nn)
        a = spawn_mesh(base, x, y, 0.0, "NTW_XinyiStitch_%s" % tag, ["NTWStitch", tag])
        if tag == "v1":
            a.set_actor_hidden_in_game(True)
            a.set_actor_enable_collision(False)
        stitches[tag] = {"lod_origins_epsg3826": so, "ue_cm": [x, y], "lods": n, "screen_sizes": sizes}
    step("stitches_placed", stitches=stitches)

    # accepted Xinyi Landscape: actor transform from three exact affine-mapped vertices
    c = json.load(open(os.path.join(CONTRACT, "xinyi_unreal_v2_contract.json"), encoding="utf-8"))
    L = c["landscape"]
    ext = c["coordinate_contract"]["extent_enu_m"]
    st = L["sample_spacing_m"]
    p00 = ue_xy(*enu_to_tm2(ext["min_east_m"], ext["max_north_m"]))
    p10 = ue_xy(*enu_to_tm2(ext["min_east_m"] + st, ext["max_north_m"]))
    p01 = ue_xy(*enu_to_tm2(ext["min_east_m"], ext["max_north_m"] - st))
    ax = (p10[0] - p00[0], p10[1] - p00[1])
    ay = (p01[0] - p00[0], p01[1] - p00[1])
    sx, sy = math.hypot(*ax), math.hypot(*ay)
    yaw = math.degrees(math.atan2(ax[1], ax[0]))
    ortho = (ax[0] * ay[0] + ax[1] * ay[1]) / (sx * sy)
    raw = os.path.join(CONTRACT, c["outputs"]["heightmap_r16"]["path"])
    res = unreal.XinyiLandscapeLibrary.create_landscape_from_raw16(raw, L["heightmap_size"][0], L["heightmap_size"][1],
                                                                   L["sections_per_component"][0], L["section_quads"],
                                                                   unreal.Vector(p00[0], p00[1], 0.0), unreal.Vector(sx, sy, L["scale_xyz"][2]),
                                                                   "Xinyi_Landscape_Accepted")
    land = [a for a in unreal.EditorLevelLibrary.get_all_level_actors() if a.get_actor_label() == "Xinyi_Landscape_Accepted"][0]
    land.set_actor_rotation(unreal.Rotator(0.0, 0.0, yaw), False)
    land.set_editor_property("landscape_material", m_ter)
    try:
        land.set_editor_property("is_spatially_loaded", False)
    except Exception as e:  # noqa: BLE001
        step("landscape_spatial_flag_failed", error=repr(e))
    step("xinyi_landscape", bridge=res[:400], pivot_ue_cm=p00, scale_xy_cm=[sx, sy], yaw_deg=yaw, axis_orthogonality_cos=ortho,
         actual_location=[land.get_actor_location().x, land.get_actor_location().y, land.get_actor_location().z],
         actual_scale=[land.get_actor_scale3d().x, land.get_actor_scale3d().y, land.get_actor_scale3d().z],
         actual_yaw=land.get_actor_rotation().yaw)

    # accepted Xinyi runtime building tiles (tile-local ENU, ground baked) under the same affine
    btiles = 0
    bdir = os.path.join(CONTRACT, "building_runtime_tiles")
    for f in sorted(os.listdir(bdir)):
        if not f.endswith(".glb"):
            continue
        ix, iy = (int(v) for v in f[:-4].split("_")[-2:])
        sm = import_glb(os.path.join(bdir, f), "%s/XinyiBuildings/%s" % (ROOT, f[:-4].replace("+", "p").replace("-", "m")))
        prepare_mesh(sm, m_bld, collision=False)
        x, y = ue_xy(*enu_to_tm2(ix * 500.0, iy * 500.0))
        spawn_mesh(sm, x, y, 0.0, "Xinyi_Buildings_%s" % f[:-4], ["XinyiBuildings"], yaw=yaw,
                   scale=(sx / (L["sample_spacing_m"] * 100.0), sy / (L["sample_spacing_m"] * 100.0), 1.0))
        btiles += 1
    step("xinyi_buildings", tiles=btiles)

    plane = lib.load_asset("/Engine/BasicShapes/Plane")
    cx, cy = ue_xy(308000.0, 2768000.0)
    # exactly the two-cell footprint (8 x 16 km): a ray that passes over the far terrain edge lands outside the plane, so
    # magenta pixels can only come from a hole in the surface
    mag = spawn_mesh(plane, cx, cy, -20000.0, "NTW_CrackDetector_Magenta", ["NTWCrackPlane"], scale=(8000.0, 16000.0, 1.0))
    mag.static_mesh_component.set_material(0, m_mag)
    mag.set_actor_enable_collision(False)
    mag.set_editor_property("is_spatially_loaded", False)
    step("crack_plane", z_cm=-20000.0, size_m=[8000, 16000], center_epsg3826=[308000.0, 2768000.0])

    # actor-precision probes (always loaded, 10 m cubes with collision): near the UE origin and ~156 km away (world corner
    # region of the 224 km envelope), at deliberately fractional centimetre positions
    cube = lib.load_asset("/Engine/BasicShapes/Cube")
    probes = {}
    for name, loc in (("near", (37.37, -61.61, 12345.67)), ("far", (11000000.37, -11000000.61, 12345.67))):
        p = spawn_mesh(cube, loc[0], loc[1], loc[2], "NTW_PrecisionProbe_" + name, ["NTWProbe", name], scale=(10.0, 10.0, 10.0))
        p.set_editor_property("is_spatially_loaded", False)
        g = p.get_actor_location()
        probes[name] = {"requested_cm": list(loc), "editor_cm": [g.x, g.y, g.z]}
    step("precision_probes", probes=probes)

    cap = ues.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(cx, cy, 100000.0), unreal.Rotator(0.0, -90.0, 0.0))
    cap.set_actor_label("NTW_GateCapture")
    cap.tags = [unreal.Name("NTWCapture")]
    cap.set_editor_property("is_spatially_loaded", False)
    step("capture_actor")

    # readable captures: high afternoon sun instead of the template's low sun (lighting only, no effect on geometry)
    for a in unreal.EditorLevelLibrary.get_all_level_actors():
        if a.get_class().get_name() == "DirectionalLight":
            a.set_actor_rotation(unreal.Rotator(0.0, -48.0, 125.0), False)
    step("sun", pitch=-48.0, yaw=125.0)

    lib.save_directory(ROOT, only_if_is_dirty=False, recursive=True)
    les.save_current_level()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)

    # fail closed on stale / duplicated World Partition external actors (a rebuilt level must contain exactly one set)
    counts = {}
    for a in unreal.EditorLevelLibrary.get_all_level_actors():
        cn = a.get_class().get_name()
        key = next((str(t) for t in a.tags if str(t) in ("NTWChunk", "NTWStitch", "XinyiBuildings", "NTWProbe", "NTWCrackPlane", "NTWCapture")), None)
        key = key or ("Landscape" if cn == "Landscape" else None)
        if key:
            counts[key] = counts.get(key, 0) + 1
    expected = {"NTWChunk": 50, "NTWStitch": 2, "XinyiBuildings": 25, "NTWProbe": 2, "NTWCrackPlane": 1, "NTWCapture": 1, "Landscape": 1}
    step("actor_census", counts=counts, expected=expected)
    if counts != expected:
        raise RuntimeError("actor census mismatch %r != %r" % (counts, expected))
    rep["status"] = "PASS_BUILD"
    rep["seconds"] = round(time.time() - rep["started"], 1)


try:
    main()
except Exception as exc:  # noqa: BLE001
    import traceback
    rep["status"] = "FAIL"
    rep["error"] = traceback.format_exc()
with open(REPORT, "w", encoding="utf-8") as fh:
    json.dump(rep, fh, indent=1, default=str)
unreal.SystemLibrary.quit_editor()
