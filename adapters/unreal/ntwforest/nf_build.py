"""North Taiwan forest world v1, stage 2 (UnrealEditor-Cmd, run with -nullrhi): the World Partition map.

/Game/NorthForest/Maps/L_NF_Yangmingshan, from the UE 5.8 OpenWorld template (template landscape / meshes / clouds / HLOD / minimap
removed, its sun / sky / fog kept and re-set):
* Landscape 2647 x 2647 at 10 m (21 x 21 components of 2 x 2 sections x 63 quads) from terrain.r16 via the XinyiLandscapeBridge
  plugin; all Landscape actors NOT spatially loaded (the whole 26.5 km terrain is always resident: ~14 MB heightmap).
* Sea: one opaque plane at TWVD2001 0 m, 160 km wide, not spatially loaded.
* Forest: one actor per 1 km tree tile (trees/*.bin), spatially loaded, one HISM per (form, tint variant); per-component end cull =
  MPC ThinEnd + 200 m (the material dissolves every tree before that), no collision, shadows on.
* Runtime grid: 1 km cells, 3.2 km loading range (NtwGateLibrary.configure_runtime_grid).
Receipt: reports/nf_build.report.json.
"""
import array
import json
import math
import os
import struct
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import (FORM_BARK_SRC, FORM_MESH, MAP, MAT, RUN, VARIANT_FORM, ensure_dir, find_actor, lib, terrain_meta,  # noqa: E402
                       write_report)

LEVEL = MAP + "/L_NF_Yangmingshan"
CELL_CM, RANGE_CM = 100000, 320000
END_CULL_CM = 260000
SUN = {"azimuth_deg": float(os.environ.get("ACW_NF_SUN_AZ", "222")), "elevation_deg": float(os.environ.get("ACW_NF_SUN_EL", "34"))}
ONLY_TILES = int(os.environ.get("ACW_NF_MAX_TILES", "0"))   # debugging: 0 = all
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
rep = {"status": "FAIL_NF_BUILD", "level": LEVEL, "steps": [], "error": None}


def step(name, **kw):
    rep["steps"].append(dict(name=name, t=round(time.time() - T0, 1), **kw))
    unreal.log("NF_STEP %s" % name)


def setp(obj, props, tag):
    for k, v in props.items():
        try:
            obj.set_editor_property(k, v)
        except Exception as exc:  # noqa: BLE001
            rep.setdefault("warnings", []).append("%s %s: %s" % (tag, k, exc))


def not_spatial(a):
    a.set_editor_property("is_spatially_loaded", False)


def lighting():
    out = {}
    for a in ues.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn == "DirectionalLight":
            az, el = math.radians(SUN["azimuth_deg"]), math.radians(SUN["elevation_deg"])
            to_sun = unreal.Vector(math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))
            a.set_actor_rotation(unreal.MathLibrary.make_rot_from_x(unreal.Vector(-to_sun.x, -to_sun.y, -to_sun.z)), False)
            sc = a.get_component_by_class(unreal.DirectionalLightComponent)
            sc.set_mobility(unreal.ComponentMobility.MOVABLE)
            setp(sc, {"atmosphere_sun_light": True, "light_source_angle": 0.6, "dynamic_shadow_distance_movable_light": 300000.0,
                      "dynamic_shadow_cascades": 4, "cascade_distribution_exponent": 3.0, "contact_shadow_length": 0.0}, "sun")
            sc.set_intensity(11.0)
            sc.set_light_color(unreal.LinearColor(1.0, 0.95, 0.88, 1.0))
            out["sun"] = SUN
        elif cn == "SkyLight":
            c = a.get_component_by_class(unreal.SkyLightComponent)
            c.set_mobility(unreal.ComponentMobility.MOVABLE)
            setp(c, {"real_time_capture": True, "lower_hemisphere_is_black": True}, "sky")
            c.set_intensity(4.0)
            c.set_lower_hemisphere_color(unreal.LinearColor(0.5, 0.55, 0.3, 1.0))
        elif cn == "ExponentialHeightFog":
            a.set_actor_location(unreal.Vector(0, -2800000, 2000), False, False)
            c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
            setp(c, {"fog_density": 0.006, "fog_height_falloff": 0.035, "start_distance": 1500.0,
                     "fog_inscattering_luminance": unreal.LinearColor(0.45, 0.55, 0.68, 1.0)}, "fog")
        elif cn == "SkyAtmosphere":
            c = a.get_component_by_class(unreal.SkyAtmosphereComponent)
            setp(c, {"aerial_perspective_start_depth": 0.3}, "atmosphere")
        if cn in ("DirectionalLight", "SkyLight", "ExponentialHeightFog", "SkyAtmosphere"):
            not_spatial(a)
    pp = ues.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
    pp.set_actor_label("NF_PostProcess")
    pp.set_editor_property("unbound", True)
    s = pp.get_editor_property("settings")
    setp(s, {"override_auto_exposure_method": True, "auto_exposure_method": unreal.AutoExposureMethod.AEM_MANUAL,
             "override_auto_exposure_apply_physical_camera_exposure": True, "auto_exposure_apply_physical_camera_exposure": False,
             "override_auto_exposure_bias": True, "auto_exposure_bias": -0.2, "override_bloom_intensity": True, "bloom_intensity": 0.15,
             "override_motion_blur_amount": True, "motion_blur_amount": 0.0, "override_vignette_intensity": True, "vignette_intensity": 0.15}, "pp")
    pp.set_editor_property("settings", s)
    not_spatial(pp)
    return out


def landscape():
    T = terrain_meta()
    L = T["landscape"]
    res = json.loads(str(unreal.XinyiLandscapeLibrary.create_landscape_from_raw16(
        str(RUN / "terrain.r16"), T["size"][0], T["size"][1], L["num_subsections"], L["subsection_quads"],
        unreal.Vector(*L["location_cm"]), unreal.Vector(*L["scale_xyz"]), "NF_Terrain")))
    if res.get("status") != "PASS_CREATED":
        raise RuntimeError("landscape bridge: %s" % res)
    mat = lib.load_asset(MAT + "/M_NF_Landscape")
    kinds = {}
    for a in ues.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn in ("Landscape", "LandscapeStreamingProxy"):
            a.set_editor_property("landscape_material", mat)
            not_spatial(a)
            kinds[cn] = kinds.get(cn, 0) + 1
    return {"bridge": res, "actors": kinds}


def sea():
    plane = lib.load_asset("/Engine/BasicShapes/Plane")
    a = ues.spawn_actor_from_object(plane, unreal.Vector(-500000.0, -2800000.0, 0.0), unreal.Rotator(0, 0, 0))
    a.set_actor_label("NF_Sea")
    a.set_actor_scale3d(unreal.Vector(1600.0, 1600.0, 1.0))
    c = a.get_component_by_class(unreal.StaticMeshComponent)
    c.set_material(0, lib.load_asset(MAT + "/M_NF_Water"))
    c.set_cast_shadow(False)
    c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    not_spatial(a)


def add_hism(actor, mesh):
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams()
    params.set_editor_property("parent_handle", handles[0])
    params.set_editor_property("new_class", unreal.HierarchicalInstancedStaticMeshComponent)
    new_handle, fail = sds.add_new_subobject(params)
    if not fail.is_empty():
        raise RuntimeError("add_new_subobject failed: %s" % fail)
    comp = unreal.SubobjectDataBlueprintFunctionLibrary.get_object(unreal.SubobjectDataBlueprintFunctionLibrary.get_data(new_handle))
    comp.set_static_mesh(mesh)
    return comp


def read_tile(path):
    with open(path, "rb") as fh:
        buf = fh.read()
    (ng,), off, groups = struct.unpack_from("<I", buf, 0), 4, []
    for _ in range(ng):
        form, var, n = struct.unpack_from("<cHI", buf, off)
        off += 7
        rec = array.array("d")
        rec.frombytes(buf[off:off + n * 9 * 8])
        off += n * 9 * 8
        groups.append((form.decode(), var, n, rec))
    return groups


def forest():
    idx = json.loads((RUN / "trees.json").read_text(encoding="utf-8"))
    meshes = {f: lib.load_asset(p) for f, p in FORM_MESH.items()}
    barks = {f: lib.load_asset(MAT + "/" + s.replace("M_TL_", "M_NF_")) for f, s in FORM_BARK_SRC.items()}
    leaves = {v: lib.load_asset(MAT + "/MI_NF_Leaf_V%d" % v) for v in VARIANT_FORM}
    if not all(meshes.values()) or not all(barks.values()) or not all(leaves.values()):
        raise RuntimeError("missing forest assets")
    total, tiles, comps = 0, 0, 0
    folder = unreal.Name("NF_Forest")
    for t in idx["tiles"][: ONLY_TILES or None]:
        cx, cy = t["center_ue_cm"]
        holder = ues.spawn_actor_from_class(unreal.Actor, unreal.Vector(cx, cy, 0.0))
        holder.set_actor_label("NF_Trees_%02d_%02d" % (t["tx"], t["ty"]))
        holder.set_folder_path(folder)
        root = holder.get_editor_property("root_component")
        if root is not None:
            root.set_mobility(unreal.ComponentMobility.STATIC)
        for form, var, n, rec in read_tile(RUN / "trees" / t["file"]):
            if VARIANT_FORM[var] != form:
                raise RuntimeError("variant %d is not form %s" % (var, form))
            h = add_hism(holder, meshes[form])
            h.set_material(0, barks[form])
            h.set_material(1, leaves[var])
            h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            h.set_cast_shadow(True)
            h.set_cull_distances(0, END_CULL_CM)
            xf = []
            for i in range(n):
                x, y, z, yaw, sx, sy, sz, le, ln = rec[i * 9:(i + 1) * 9]
                z_up = unreal.Vector(math.tan(math.radians(le)), -math.tan(math.radians(ln)), 1.0)
                yr = math.radians(yaw)
                rot = unreal.MathLibrary.make_rot_from_zx(z_up, unreal.Vector(math.cos(yr), math.sin(yr), 0.0))
                xf.append(unreal.Transform(unreal.Vector(x, y, z), rot, unreal.Vector(sx, sy, sz)))
            h.add_instances(xf, False, True)
            if h.get_instance_count() != n:
                raise RuntimeError("instance count %s tile %s" % (h.get_instance_count(), t["file"]))
            total += n
            comps += 1
        tiles += 1
        if tiles % 50 == 0:
            step("forest_progress", tiles=tiles, instances=total)
    return {"tiles": tiles, "components": comps, "instances": total, "expected": sum(t["count"] for t in idx["tiles"][: ONLY_TILES or None]),
            "end_cull_cm": END_CULL_CM}


T0 = time.time()
try:
    ensure_dir(MAP)
    if lib.does_asset_exist(LEVEL):
        raise RuntimeError(LEVEL + " exists: delete it explicitly to rebuild")
    les.new_level_from_template(LEVEL, "/Engine/Maps/Templates/OpenWorld")
    removed = []
    for a in ues.get_all_level_actors():
        cn = a.get_class().get_name()
        if cn in ("Landscape", "LandscapeStreamingProxy", "StaticMeshActor", "VolumetricCloud", "WorldPartitionHLOD", "WorldPartitionMiniMap"):
            removed.append(cn)
            ues.destroy_actor(a)
    step("template_cleaned", removed=sorted(set(removed)))
    rep["grid"] = {"before": json.loads(unreal.NtwGateLibrary.configure_runtime_grid(CELL_CM, RANGE_CM)),
                   "after": json.loads(unreal.NtwGateLibrary.describe_runtime_grid())}
    rep["lighting"] = lighting()
    step("lighting")
    rep["landscape"] = landscape()
    step("landscape", **rep["landscape"]["actors"])
    sea()
    rep["forest"] = forest()
    step("forest", **rep["forest"])
    if rep["forest"]["instances"] != rep["forest"]["expected"]:
        raise RuntimeError("instance total mismatch")
    if not les.save_current_level():
        raise RuntimeError("save " + LEVEL)
    step("saved")
    rep["status"] = "PASS_NF_BUILD"
except Exception:  # noqa: BLE001
    rep["error"] = traceback.format_exc()
    unreal.log_error(rep["error"])
write_report("nf_build.report.json", rep)
unreal.SystemLibrary.quit_editor()
