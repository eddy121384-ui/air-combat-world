"""Hillside forest look-dev v1, stage 1 (UnrealEditor-Cmd, TreeLookdev project): Xiangshan test terrain + 紅楠 D balanced HISM forest.

Inputs (tools/forest/hillside_{terrain,scatter,views}.py): $ACW_HF_DIR/{terrain.r16, terrain.json, instances.json, views.json}.
Needs the prebuilt editor plugin XinyiLandscapeBridge (only ALandscape::Import; see unreal/TreeLookdev/Plugins, gitignored).

Everything is new content under /Game/HillsideForest/<rev>; the PR #30/#31 assets are only referenced:
* mesh: /Game/TreeLookdev/Budget/D/... (D balanced, LOD 34,272 / 14,806 / 2,018 / 534 tris, screens 1.0 / 0.5 / 0.15 / 0.06) - unchanged;
* M_TL_LeafCards / M_TL_Bark: only the "Used with Instanced Static Meshes" usage flag is (re)asserted and SAVED (PR #31 lesson: an
  unsaved flag makes standalone -game draw HISMs with the engine default grey material);
* MI_HF_Leaf_V0..V2: material instances of M_TL_LeafCards that change only existing parameters (TintLo / TintHi / Brightness);
* M_HF_Ground: plain opaque landscape material (dark mottled understory proxy inside the 250 m block, flat placeholder outside it).
Maps: L_HF_Xiangshan (main), L_HF_Stills_<forest|empty> + L_HF_Flight_<forest|empty> (camera Level Sequence, auto-play actor; used by
MRQ and the flight perf runs), L_HFP_<view>_<forest|empty> (static camera auto-activated for player 0; still-view perf runs).
Receipt: reports/hf_build.report.json.
"""
import json
import math
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_budget_common import PATH, add_hism  # noqa: E402
from tl_common import MAT_DIR, ensure_dir, find_actor, lib, mel, tools, write_report  # noqa: E402

HF_DIR = Path(os.environ["ACW_HF_DIR"])
REV = os.environ.get("ACW_HF_REV", "r1")
HF = "/Game/HillsideForest"
DIR = HF + "/" + REV
MAIN = DIR + "/L_HF_Xiangshan"
EV = float(os.environ.get("ACW_HF_EV", "-0.4"))  # PR #31 native stage used -0.6 (its +0.8 SceneCapture value is ~2 EV too bright natively); +0.2 here for the darker forest-scale scene
SHADOW_M = float(os.environ.get("ACW_HF_SHADOW_M", "1200"))
LEAF_VARIANTS = {  # existing M_TL_LeafCards parameters only (parent defaults: TintLo 0.82/0.86/0.80, TintHi 1.18/1.12/1.0, Brightness 0.42)
    0: {},
    1: {"TintHi": (1.34, 1.26, 0.80), "TintLo": (0.90, 0.94, 0.70), "Brightness": 0.50},  # lighter, yellower (new-leaf flush / sunlit crowns)
    2: {"TintHi": (0.98, 1.04, 1.00), "TintLo": (0.66, 0.76, 0.78), "Brightness": 0.34},  # darker, bluer (older foliage / shaded crowns)
    # mix v0, crown form B only: a lighter, yellower family (light-gap / ridge crowns, new flush) so the two forms differ in tone as well
    3: {"TintHi": (1.42, 1.34, 0.72), "TintLo": (0.92, 0.96, 0.66), "Brightness": 0.52},
    4: {"TintHi": (1.30, 1.26, 0.82), "TintLo": (0.84, 0.92, 0.66), "Brightness": 0.44},
}
# instance file: instances.json = version A (single 紅楠 D); instances_mix.json = version B (mix v0: form A = D, form B = crown B)
INSTANCES = os.environ.get("ACW_HF_INSTANCES", "instances.json")
# form A LOD chain: D balanced (default, Mix D) or PR #31's aggressive C (Mix C low-precision tolerance test); form B is always crown B
A_CHAIN = os.environ.get("ACW_HF_A_CHAIN", "D")
if A_CHAIN not in ("C", "D"):
    raise RuntimeError("ACW_HF_A_CHAIN must be C or D")
FORM_MESH = {"A": PATH[A_CHAIN], "B": "/Game/HillsideForest/Trees/CrownB/machilus_balanced_lod0/StaticMeshes/machilus_balanced_lod0"}
# inside the block the floor stands in for the understory (shrubs / ferns / saplings - not modelled): two dark greens mottled by a ~6 m
# world-space noise; outside the block a flat placeholder olive-grey that is visibly NOT forest (test terrain only)
GROUND = {"inside": ((0.016, 0.024, 0.009), (0.034, 0.040, 0.017)), "outside": (0.060, 0.062, 0.040)}

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
report = {"status": "FAIL_HF_BUILD", "rev": REV, "instances_file": INSTANCES, "a_chain": A_CHAIN, "maps": {}, "materials": {}, "error": None}
T = json.loads((HF_DIR / "terrain.json").read_text(encoding="utf-8"))
I = json.loads((HF_DIR / INSTANCES).read_text(encoding="utf-8"))
V = json.loads((HF_DIR / "views.json").read_text(encoding="utf-8"))


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, out, b, pin):
    if not mel.connect_material_expressions(a, out, b, pin):
        raise RuntimeError("connect failed %s.%s -> %s" % (a.get_name(), out, pin))


def assert_ism_usage():
    out = {}
    for name in ("M_TL_LeafCards", "M_TL_Bark"):
        m = lib.load_asset(MAT_DIR + "/" + name)
        before = bool(m.get_editor_property("used_with_instanced_static_meshes"))
        if not before:
            mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
            mel.recompile_material(m)
            if not lib.save_asset(MAT_DIR + "/" + name, only_if_is_dirty=False):
                raise RuntimeError("save " + name)
        out[name] = {"flag_before": before, "flag_after": bool(m.get_editor_property("used_with_instanced_static_meshes")),
                     "blend_mode": str(m.get_editor_property("blend_mode")), "two_sided": bool(m.get_editor_property("two_sided"))}
    return out


def leaf_instances(parent):
    out = {}
    used = {it["variant"] for it in I["instances"]}
    for v, params in LEAF_VARIANTS.items():
        if v not in used:
            continue
        name = "MI_HF_Leaf_V%d" % v
        mic = tools.create_asset(name, DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mic, parent)
        for k, val in params.items():
            # UE 5.8: the set_* return value is False even when the value is applied (hf_probe_params.py), so read it back instead
            if isinstance(val, tuple):
                mel.set_material_instance_vector_parameter_value(mic, k, unreal.LinearColor(val[0], val[1], val[2], 1.0))
                c = mel.get_material_instance_vector_parameter_value(mic, k)
                ok = all(abs(a - b) < 1e-4 for a, b in zip((c.r, c.g, c.b), val))
            else:
                mel.set_material_instance_scalar_parameter_value(mic, k, float(val))
                ok = abs(mel.get_material_instance_scalar_parameter_value(mic, k) - val) < 1e-4
            if not ok:
                raise RuntimeError("%s: parameter %s did not take the value" % (name, k))
        mel.update_material_instance(mic)
        if not lib.save_asset(DIR + "/" + name):
            raise RuntimeError("save " + name)
        out[v] = mic
        report["materials"][name] = {"parent": parent.get_path_name(), "overrides": {k: list(x) if isinstance(x, tuple) else x for k, x in params.items()}}
    return out


def ground_material():
    name = "M_HF_Ground"
    mat = tools.create_asset(name, DIR, unreal.Material, unreal.MaterialFactoryNew())
    wp = E(mat, unreal.MaterialExpressionWorldPosition, -1400, 0)
    mx = E(mat, unreal.MaterialExpressionComponentMask, -1200, -60, r=True, g=False, b=False, a=False)
    my = E(mat, unreal.MaterialExpressionComponentMask, -1200, 60, r=False, g=True, b=False, a=False)
    link(wp, "", mx, "")
    link(wp, "", my, "")
    ax, ay = E(mat, unreal.MaterialExpressionAbs, -1050, -60), E(mat, unreal.MaterialExpressionAbs, -1050, 60)
    link(mx, "", ax, "")
    link(my, "", ay, "")
    mm = E(mat, unreal.MaterialExpressionMax, -900, 0)
    link(ax, "", mm, "A")
    link(ay, "", mm, "B")
    sub = E(mat, unreal.MaterialExpressionSubtract, -750, 0, const_b=12500.0 + 300.0)  # block half-width + 3 m, in cm
    link(mm, "", sub, "A")
    div = E(mat, unreal.MaterialExpressionDivide, -600, 0, const_b=1500.0)
    link(sub, "", div, "A")
    sat = E(mat, unreal.MaterialExpressionSaturate, -450, 0)
    link(div, "", sat, "")
    lp = E(mat, unreal.MaterialExpressionLinearInterpolate, -300, 0)
    (a_, b_), c_out = GROUND["inside"], GROUND["outside"]
    nz = E(mat, unreal.MaterialExpressionNoise, -900, -350, scale=1.0 / 600.0, levels=3, output_min=0.0, output_max=1.0)
    mottle = E(mat, unreal.MaterialExpressionLinearInterpolate, -500, -250)
    link(E(mat, unreal.MaterialExpressionConstant3Vector, -700, -450, constant=unreal.LinearColor(a_[0], a_[1], a_[2], 1)), "", mottle, "A")
    link(E(mat, unreal.MaterialExpressionConstant3Vector, -700, -300, constant=unreal.LinearColor(b_[0], b_[1], b_[2], 1)), "", mottle, "B")
    link(nz, "", mottle, "Alpha")
    link(mottle, "", lp, "A")
    link(E(mat, unreal.MaterialExpressionConstant3Vector, -500, 200, constant=unreal.LinearColor(c_out[0], c_out[1], c_out[2], 1)), "", lp, "B")
    link(sat, "", lp, "Alpha")
    mel.connect_material_property(lp, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(E(mat, unreal.MaterialExpressionConstant, -300, 250, r=0.95), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    lib.save_asset(DIR + "/" + name)
    report["materials"][name] = {"inside_rgb_mottle": GROUND["inside"], "noise_scale_m": 6.0, "outside_rgb": GROUND["outside"], "blend_at_m": 128.0}
    return mat


def spawn(cls, label, loc=(0.0, 0.0, 0.0), rot=None):
    a = actors.spawn_actor_from_class(cls, unreal.Vector(*loc), rot or unreal.Rotator(0, 0, 0))
    a.set_actor_label(label)
    return a


def setp(obj, props, tag):
    for k, v in props.items():
        try:
            obj.set_editor_property(k, v)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("%s %s: %s" % (tag, k, exc))
            report.setdefault("warnings", []).append("%s %s: %s" % (tag, k, exc))


def stage():
    sun_az, sun_el = math.radians(V["sun"]["azimuth_deg"]), math.radians(V["sun"]["elevation_deg"])
    to_sun = unreal.Vector(math.sin(sun_az) * math.cos(sun_el), -math.cos(sun_az) * math.cos(sun_el), math.sin(sun_el))
    sun = spawn(unreal.DirectionalLight, "HF_Sun", (0, 0, 50000))
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.set_actor_rotation(unreal.MathLibrary.make_rot_from_x(unreal.Vector(-to_sun.x, -to_sun.y, -to_sun.z)), False)
    setp(sc, {"atmosphere_sun_light": True, "light_source_angle": 0.6, "dynamic_shadow_distance_movable_light": SHADOW_M * 100.0,
              "dynamic_shadow_cascades": 4, "cascade_distribution_exponent": 2.5, "contact_shadow_length": 0.03}, "sun")
    sc.set_intensity(11.0)
    sc.set_light_color(unreal.LinearColor(1.0, 0.96, 0.9, 1.0))
    ac = spawn(unreal.SkyAtmosphere, "HF_SkyAtmosphere").get_component_by_class(unreal.SkyAtmosphereComponent)
    setp(ac, {"aerial_perspective_start_depth": 0.1}, "atmosphere")
    sky = spawn(unreal.SkyLight, "HF_SkyLight", (0, 0, 40000))
    skc = sky.get_component_by_class(unreal.SkyLightComponent)
    skc.set_mobility(unreal.ComponentMobility.MOVABLE)
    setp(skc, {"real_time_capture": True, "source_type": unreal.SkyLightSourceType.SLS_CAPTURED_SCENE, "lower_hemisphere_is_black": True}, "sky")
    skc.set_intensity(4.0)
    skc.set_lower_hemisphere_color(unreal.LinearColor(0.5, 0.55, 0.3, 1.0))
    # humid lowland haze (Taipei basin): light exponential height fog based near the basin floor (~10 m a.s.l.)
    fog = spawn(unreal.ExponentialHeightFog, "HF_HeightFog", (0, 0, (10.0 - T["landscape"]["h_ref_m"]) * 100.0))
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    setp(fc, {"fog_density": 0.012, "fog_height_falloff": 0.06, "start_distance": 0.0,
              "fog_inscattering_luminance": unreal.LinearColor(0.42, 0.5, 0.6, 1.0)}, "fog")
    pp = spawn(unreal.PostProcessVolume, "HF_PostProcess")
    pp.set_editor_property("unbound", True)
    s = pp.get_editor_property("settings")
    setp(s, {"override_auto_exposure_method": True, "auto_exposure_method": unreal.AutoExposureMethod.AEM_MANUAL,
             "override_auto_exposure_apply_physical_camera_exposure": True, "auto_exposure_apply_physical_camera_exposure": False,
             "override_auto_exposure_bias": True, "auto_exposure_bias": EV, "override_bloom_intensity": True, "bloom_intensity": 0.0,
             "override_motion_blur_amount": True, "motion_blur_amount": 0.0, "override_vignette_intensity": True, "vignette_intensity": 0.0,
             "override_color_saturation": True, "color_saturation": unreal.Vector4(0.9, 0.9, 0.9, 1.0)}, "pp")
    pp.set_editor_property("settings", s)
    return {"sun": V["sun"], "sun_lux": 11.0, "sky": 4.0, "exposure_ev": EV, "shadow_distance_m": SHADOW_M, "fog_density": 0.012}


def terrain(m_ground):
    L = T["landscape"]
    bridge = getattr(unreal, "XinyiLandscapeLibrary", None)
    if bridge is None:
        raise RuntimeError("XinyiLandscapeLibrary unavailable: copy the prebuilt XinyiLandscapeBridge plugin into unreal/TreeLookdev/Plugins")
    res = json.loads(str(bridge.create_landscape_from_raw16(str(HF_DIR / "terrain.r16"), T["size"][0], T["size"][1], L["num_subsections"],
                                                            L["subsection_quads"], unreal.Vector(*L["location_cm"]), unreal.Vector(*L["scale_xyz"]),
                                                            "HF_Terrain_Xiangshan")))
    if res.get("status") != "PASS_CREATED" or int(res.get("component_count", -1)) != L["components"][0] * L["components"][1]:
        raise RuntimeError("landscape bridge: %s" % res)
    land = find_actor(actors, "HF_Terrain_Xiangshan")
    land.set_editor_property("landscape_material", m_ground)
    return res


def forest(mics):
    bark = lib.load_asset(MAT_DIR + "/M_TL_Bark")
    holder = spawn(unreal.Actor, "HF_Forest")
    comps, counts = {}, {}
    groups = sorted({(it.get("form", "A"), it["variant"]) for it in I["instances"]})
    for form, v in groups:
        mesh = lib.load_asset(FORM_MESH[form])
        if mesh is None or mesh.get_num_lods() != 4:
            raise RuntimeError("form %s mesh missing or not 4 LODs: %s" % (form, FORM_MESH[form]))
        mic = mics[v]
        h = add_hism(holder, mesh)
        h.set_material(0, bark)
        h.set_material(1, mic)
        h.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        h.set_cast_shadow(True)
        xf = []
        for it in I["instances"]:
            if it["variant"] != v or it.get("form", "A") != form:
                continue
            z_up = unreal.Vector(math.tan(math.radians(it["lean_east_deg"])), -math.tan(math.radians(it["lean_north_deg"])), 1.0)
            yaw = math.radians(it["yaw_deg"])
            rot = unreal.MathLibrary.make_rot_from_zx(z_up, unreal.Vector(math.cos(yaw), math.sin(yaw), 0.0))
            xf.append(unreal.Transform(unreal.Vector(*it["ue_cm"]), rot, unreal.Vector(it["scale_x"], it["scale_y"], it["scale_z"])))
        h.add_instances(xf, False, True)
        comps["%s%d" % (form, v)] = h
        counts["%s%d" % (form, v)] = h.get_instance_count()
    return holder, counts


def camera(label, pose):
    cam = spawn(unreal.CameraActor, label, tuple(pose["ue_loc_cm"]), unreal.Rotator(*pose["ue_rot"]))
    cc = cam.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", V["hfov_deg"])
    cc.set_editor_property("aspect_ratio", 16.0 / 9.0)
    cc.set_editor_property("constrain_aspect_ratio", True)
    cam.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    return cam


def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def save_as(dest):
    if lib.does_asset_exist(dest):
        raise RuntimeError("refusing to overwrite map %s (use a new ACW_HF_REV)" % dest)
    if not unreal.EditorLoadingAndSavingUtils.save_map(world(), dest):
        raise RuntimeError("save_map " + dest)


def variant_of_main(dest, cond):
    if not levels.load_level(MAIN):
        raise RuntimeError("load " + MAIN)
    if cond == "empty":
        actors.destroy_actor(find_actor(actors, "HF_Forest"))
    save_as(dest)


def sequence(name, keys, interp):
    """Camera Level Sequence on the reloaded map (ForestSpike B1a / PR #31 recipe: build, save, reload, then bind)."""
    w = world()
    cam = find_actor(actors, "HF_Cam")
    seq = tools.create_asset("LS_" + name, DIR, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    end = keys[-1]["frame"]
    seq.set_display_rate(unreal.FrameRate(V["fps"], 1))
    seq.set_clock_source(unreal.UpdateClockSource.TICK)
    seq.set_playback_start(0)
    seq.set_playback_end(end + 1)
    binding = seq.add_possessable(cam)
    section = binding.add_track(unreal.MovieScene3DTransformTrack).add_section()
    section.set_range(0, end + 1)
    channels = list(section.get_all_channels())
    for k in keys:
        loc, rot = k["ue_loc_cm"], k["ue_rot"]
        for c, val in zip(channels, [loc[0], loc[1], loc[2], rot[0], rot[1], rot[2], 1, 1, 1]):
            c.add_key(unreal.FrameNumber(k["frame"]), float(val), 0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, interp)
    cut = seq.add_track(unreal.MovieSceneCameraCutTrack).add_section()
    cut.set_range(0, end + 1)
    cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding))
    if not lib.save_asset(seq.get_path_name()):
        raise RuntimeError("save sequence " + name)
    lsa = spawn(unreal.LevelSequenceActor, "HF_Sequence")
    lsa.set_editor_property("level_sequence_asset", seq)
    ps = lsa.get_editor_property("playback_settings")
    ps.set_editor_property("auto_play", True)
    ps.set_editor_property("loop_count", unreal.MovieSceneSequenceLoopCount(0))
    ps.set_editor_property("finish_completion_state_override", unreal.MovieSceneCompletionModeOverride.FORCE_KEEP_STATE)
    lsa.set_editor_property("playback_settings", ps)
    bound = [o.get_path_name() for b in seq.get_bindings() for o in unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq, b, w)]
    if cam.get_path_name() not in bound:
        raise RuntimeError("camera not bound in %s: %s" % (name, bound))
    return seq.get_path_name(), end + 1


def sequence_map(kind, cond):
    name = "HF_%s_%s" % (kind, cond)
    dest = DIR + "/L_" + name
    variant_of_main(dest, cond)
    if not levels.load_level(dest):
        raise RuntimeError("reload " + dest)
    if world().get_path_name().split(".")[0] != dest:
        raise RuntimeError("wrong world after reload: " + world().get_path_name())
    if kind == "Stills":
        hold = V["still_hold_frames"]
        keys = [dict(frame=i * hold, ue_loc_cm=s["ue_loc_cm"], ue_rot=s["ue_rot"]) for i, s in enumerate(V["stills"])]
        keys.append(dict(frame=len(V["stills"]) * hold - 1, ue_loc_cm=V["stills"][-1]["ue_loc_cm"], ue_rot=V["stills"][-1]["ue_rot"]))
        seq, frames = sequence(name, keys, unreal.MovieSceneKeyInterpolation.CONSTANT)
        grab = [(i + 1) * hold - 1 for i in range(len(V["stills"]))]
    else:
        seq, frames = sequence(name, V["flight"]["keys"], unreal.MovieSceneKeyInterpolation.LINEAR)
        grab = None
    if not levels.save_current_level():
        raise RuntimeError("save " + dest)
    report["maps"]["%s_%s" % (kind.lower(), cond)] = {"map": dest, "sequence": seq, "frames": frames, "still_frames": grab}


def perf_map(still, cond):
    dest = DIR + "/L_HFP_%s_%s" % (still["name"], cond)
    if not levels.load_level(MAIN):
        raise RuntimeError("load " + MAIN)
    if cond == "empty":
        actors.destroy_actor(find_actor(actors, "HF_Forest"))
    cam = find_actor(actors, "HF_Cam")
    cam.set_actor_location_and_rotation(unreal.Vector(*still["ue_loc_cm"]), unreal.Rotator(*still["ue_rot"]), False, True)
    save_as(dest)
    report["maps"]["perf_%s_%s" % (still["name"], cond)] = {"map": dest}


try:
    if lib.does_directory_exist(DIR):
        raise RuntimeError("%s exists: use a new ACW_HF_REV" % DIR)
    ensure_dir(HF)
    ensure_dir(DIR)
    report["ism_usage"] = assert_ism_usage()
    mics = leaf_instances(lib.load_asset(MAT_DIR + "/M_TL_LeafCards"))
    m_ground = ground_material()
    if not levels.new_level(MAIN):
        raise RuntimeError("new_level " + MAIN)
    report["lighting"] = stage()
    report["landscape"] = terrain(m_ground)
    _, counts = forest(mics)
    report["instances"] = {"per_variant": counts, "total": sum(counts.values()), "expected": len(I["instances"])}
    if sum(counts.values()) != len(I["instances"]):
        raise RuntimeError("instance count mismatch %s vs %d" % (counts, len(I["instances"])))
    camera("HF_Cam", V["stills"][0])
    if not levels.save_current_level():
        raise RuntimeError("save " + MAIN)
    report["maps"]["main"] = {"map": MAIN}
    for cond in ("forest", "empty"):
        sequence_map("Stills", cond)
        sequence_map("Flight", cond)
        for s in V["stills"]:
            perf_map(s, cond)
    report["status"] = "PASS_HF_BUILD"
except Exception:  # noqa: BLE001
    report["error"] = traceback.format_exc()
    unreal.log_error(report["error"])
write_report("hf_build.report.json", report)
unreal.SystemLibrary.quit_editor()
