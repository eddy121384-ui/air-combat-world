"""Cloud Prototype v0 — UE5.8 volumetric renderer adapter (editor Python).

Separation of concerns:
  cloud / weather STATE  tools/lookdev/clouds/cloud_state_v0.json -> build_clouds.py
                         (cell list + weather map; renderer-agnostic, reusable by gameplay
                         and by future card / impostor / mobile renderers)
  cloud RENDERER (this)  one VolumetricCloud actor + M_XinyiClouds_{High,Low}
                         (tools/lookdev/shaders/xinyi_clouds.hlsl reading the weather map)
                         + quality profiles. Nothing here decides where clouds are.

Quality profiles (ACW_XINYI_LOOK_CLOUDS = off | low | high | cheap; default off everywhere):
  off   cloud actor hidden, cloud shadows off: the accepted, cloud-independent city look. The saved
        look level is in this state.
  low   weak-GPU / runtime test path (UHD 770 class): 2-octave, softened density, 1 multi-scattering
        octave, 0.75x view / 0.5x shadow sampling, quarter-res trace with half-res temporal
        reconstruction and bilateral upsampling (render-target mode 0), small cloud shadow map at
        reduced strength, no sky AO. Same weather and shapes as HIGH, cheaper rendering.
  high  PC visual reference: 3-octave density, 2 multi-scattering octaves, 1.5x view / 2x shadow
        sampling, full-resolution trace, cloud shadows + sky-light cloud AO.
  cheap EXPERIMENTAL non-volumetric renderer (xinyi_look_clouds_cheap.py): volumetric actor as OFF,
        plus transient per-cell analytic lobe impostors built from the same cloud cells.
Per-time-of-day calibration (extinction, coverage bias, multi-scattering, dusk sky fill) is set on a
dynamic instance of the cloud material, not on the city MPC.
"""
import json

import unreal
from xinyi_look_common import LOOK_OUT, LOOK_PREFIX, MAT_DIR, lib

CLOUD_LABEL = LOOK_PREFIX + "Clouds"
SUN_LABEL = LOOK_PREFIX + "Sun"
SKY_LABEL = LOOK_PREFIX + "SkyLight"
REPORT = LOOK_OUT / "clouds" / "clouds.report.json"
MATERIALS = {"high": MAT_DIR + "/M_XinyiClouds_High", "low": MAT_DIR + "/M_XinyiClouds_Low"}

# Renderer calibration per time of day, applied as parameters on a dynamic instance of the cloud
# material (not weather state, not the city MPC).
EXTINCTION = {"day": 0.02, "dusk": 0.02, "night": 0.02}
COVERAGE_BIAS = 0.0
# Dusk cloud lighting. At 7 deg the atmosphere-filtered sun is deep orange, and with day-strength
# multiple scattering that orange light floods the shaded interiors too: flat orange cotton balls.
# Lower multi-scattering at dusk lets shaded volumes fall back to the cooler sky ambient (warm edges,
# neutral / cool cores), and a slightly cooler sun-on-cloud scale keeps sunlit edges amber, not ochre.
MULTI_SCATTER = {"day": 0.75, "dusk": 0.4, "night": 0.75}
SUN_ON_CLOUDS = {"dusk": (0.95, 0.88, 0.92)}
# Cool sky fill on shaded cloud volumes (emissive, x underside AO); none by day or night.
CLOUD_AMBIENT = {"dusk": (0.012, 0.012, 0.02)}

PROFILES = {
    "high": {
        "view_sample_count_scale": 1.5,
        "shadow_view_sample_count_scale": 2.0,
        "reflection_view_sample_count_scale": 0.5,
        "shadow_reflection_view_sample_count_scale": 0.5,
        "shadow_tracing_distance": 15.0,
        "sun_cloud_shadow_res_scale": 1.0,
        "sun_cloud_shadow_ray_scale": 1.0,
        "sky_cloud_ao": True,
        "sun_cloud_shadow_strength": 0.55,
        "material": {},          # material defaults (CloudDensityGain 2.2, CloudFineLump 0.45)
        "cvars": {
            # full-resolution trace (cinematic path). Half-res temporal reconstruction (mode 1) does not
            # converge in SceneCapture stills, which then show blotchy trace noise.
            "r.VolumetricRenderTarget.Mode": 3,
            # UHD 770: view x2 + shadow x4 / 256 at full res exceeded the 2 s Windows TDR (device removed)
            "r.VolumetricCloud.ViewRaySampleMaxCount": 512,
            "r.VolumetricCloud.Shadow.ViewRaySampleMaxCount": 128,
            "r.VolumetricCloud.ShadowMap.MaxResolution": 2048,
            "r.VolumetricCloud.ShadowMap.RaySampleMaxCount": 128,
            "r.VolumetricCloud.SkyAO": 1,
            # HighQualityAerialPerspective stays 0: in SceneCapture its intermediate is never written
            # (RDG ensure) and the cloud pass then asserted on a non-Volume fallback material.
            "r.VolumetricCloud.HighQualityAerialPerspective": 0,
        },
    },
    # LOW optimization (continuous 30 Hz flight test on the UHD 770, see the pass report):
    # - Grain was view-ray undersampling of a sharp, fine density. Mode 2 forces nearest-neighbour
    #   upsampling of its quarter-res trace, so a static camera converged to a frozen speckle.
    #   Softer density (gain 2.2 -> 1.1, 320 m lobe weight 0.45 -> 0.1) cuts the variance at the
    #   source for free; mode 0 + bilateral upsampling with 0.75x view samples reconstructs it
    #   cleanly with lower frame-to-frame flicker than HIGH.
    # - Soft density widens the fringe halo that sparkles in clear sky; coverage -0.12 trims it back
    #   to the HIGH silhouette.
    # - The whole-frame darker / cooler shift was over-strong sun cloud shadow from the coarse LOW
    #   shadow map (sunlight loss ~2x HIGH): strength 0.55 -> 0.35.
    "low": {
        "view_sample_count_scale": 0.75,
        "shadow_view_sample_count_scale": 0.5,
        "reflection_view_sample_count_scale": 0.25,
        "shadow_reflection_view_sample_count_scale": 0.25,
        "shadow_tracing_distance": 8.0,
        "sun_cloud_shadow_res_scale": 0.25,
        "sun_cloud_shadow_ray_scale": 0.5,
        "sky_cloud_ao": False,
        "sun_cloud_shadow_strength": 0.35,
        "material": {"CloudDensityGain": 1.1, "CloudFineLump": 0.1, "CloudCoverage": -0.12},
        "cvars": {
            "r.VolumetricRenderTarget.Mode": 0,
            "r.VolumetricRenderTarget.UpsamplingMode": 4,
            "r.VolumetricCloud.ViewRaySampleMaxCount": 160,
            "r.VolumetricCloud.Shadow.ViewRaySampleMaxCount": 16,
            "r.VolumetricCloud.ShadowMap.MaxResolution": 512,
            "r.VolumetricCloud.ShadowMap.RaySampleMaxCount": 24,
            "r.VolumetricCloud.SkyAO": 0,
            "r.VolumetricCloud.HighQualityAerialPerspective": 0,
        },
    },
}


def finish_shaders():
    """Block until async loading, shader compilation and rendering commands are flushed."""
    try:
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        return True
    except Exception as exc:
        unreal.log_warning("finish_loading_before_screenshot failed: %s" % exc)
        return False


def report():
    return json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.is_file() else None


def _find(actors, label):
    for a in actors.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def spawn_clouds(actors):
    """Level stage: one VolumetricCloud actor whose layer matches the state's renderer layer."""
    rep = report()
    if rep is None:
        return None
    a = _find(actors, CLOUD_LABEL)
    if a is None:
        a = actors.spawn_actor_from_class(unreal.VolumetricCloud, unreal.Vector(0.0, 0.0, 0.0))
        a.set_actor_label(CLOUD_LABEL)
    c = a.get_component_by_class(unreal.VolumetricCloudComponent)
    bottom_m, top_m = rep["renderer_layer_m"]
    c.set_layer_bottom_altitude(bottom_m / 1000.0)   # km, above the SkyAtmosphere ground (sea level)
    c.set_layer_height((top_m - bottom_m) / 1000.0)
    c.set_tracing_max_distance(45.0)
    c.set_tracing_start_max_distance(80.0)
    c.set_sky_light_cloud_bottom_occlusion(0.35)   # default 0.5 read near-black under a sunlit deck
    return a


def _set(obj, prop, val, notes):
    try:
        obj.set_editor_property(prop, val)
    except Exception as exc:
        notes.append("%s.%s: %s" % (obj.get_class().get_name(), prop, str(exc)[:80]))


def apply_clouds(world, actors, quality, tod):
    """Apply a renderer quality profile. Returns a small dict for capture receipts."""
    if quality == "cheap":
        # EXPERIMENTAL third renderer (xinyi_look_clouds_cheap.py): the volumetric actor is exactly as
        # OFF (hidden, no cloud shadows), then transient analytic impostors over the same cloud state.
        from xinyi_look_clouds_cheap import apply_cheap
        off = apply_clouds(world, actors, "off", tod)
        r = apply_cheap(world, actors, tod)
        r["volumetric"] = off
        return r
    notes = []
    a = _find(actors, CLOUD_LABEL)
    if a is None:
        return {"quality": "absent"}
    c = a.get_component_by_class(unreal.VolumetricCloudComponent)
    sun = _find(actors, SUN_LABEL).get_component_by_class(unreal.DirectionalLightComponent)
    sky = _find(actors, SKY_LABEL).get_component_by_class(unreal.SkyLightComponent)
    if quality == "off":
        # hidden, but keep the HIGH material referenced so the saved level carries the prototype
        c.set_visibility(False)
        mat = lib.load_asset(MATERIALS["high"])
        if mat is not None:
            c.set_material(mat)
        _set(sun, "cast_cloud_shadows", False, notes)
        _set(sky, "cloud_ambient_occlusion", False, notes)
        return {"quality": "off", "notes": notes}
    p = PROFILES[quality]
    mat = lib.load_asset(MATERIALS[quality])
    if mat is None:
        raise RuntimeError("cloud material missing: %s" % MATERIALS[quality])
    # The cloud renderer asserts (VolumetricCloudRendering.cpp: domain == MD_Volume) if it draws while
    # the cloud material's shader map is still compiling (fallback = default surface material). Keep
    # the cloud hidden until every pending shader compile has finished.
    c.set_visibility(False)
    c.set_material(mat)
    finish_shaders()
    c.set_visibility(True)
    c.set_view_sample_count_scale(p["view_sample_count_scale"])
    c.set_shadow_view_sample_count_scale(p["shadow_view_sample_count_scale"])
    c.set_reflection_view_sample_count_scale(p["reflection_view_sample_count_scale"])
    c.set_shadow_reflection_view_sample_count_scale(p["shadow_reflection_view_sample_count_scale"])
    c.set_shadow_tracing_distance(p["shadow_tracing_distance"])
    sc = SUN_ON_CLOUDS.get(tod, (1.0, 1.0, 1.0))
    for prop, val in (("cloud_scattered_luminance_scale", unreal.LinearColor(sc[0], sc[1], sc[2], 1.0)),
                      ("cast_cloud_shadows", True), ("cloud_shadow_strength", p["sun_cloud_shadow_strength"]),
                      ("cloud_shadow_on_surface_strength", 1.0), ("cloud_shadow_on_atmosphere_strength", 0.1),
                      ("cloud_shadow_extent", 120.0),
                      ("cloud_shadow_map_resolution_scale", p["sun_cloud_shadow_res_scale"]),
                      ("cloud_shadow_ray_sample_count_scale", p["sun_cloud_shadow_ray_scale"])):
        _set(sun, prop, val, notes)
    for prop, val in (("cloud_ambient_occlusion", p["sky_cloud_ao"]), ("cloud_ambient_occlusion_strength", 0.8),
                      ("cloud_ambient_occlusion_extent", 120.0)):
        _set(sky, prop, val, notes)
    for k, v in p["cvars"].items():
        unreal.SystemLibrary.execute_console_command(world, "%s %s" % (k, v))
    mid = unreal.MaterialLibrary.create_dynamic_material_instance(world, mat)
    a = CLOUD_AMBIENT.get(tod, (0.0, 0.0, 0.0))
    params = {"CloudExtinction": EXTINCTION.get(tod, 0.02), "CloudCoverage": COVERAGE_BIAS,
              "CloudMultiScatter": MULTI_SCATTER.get(tod, 0.75)}
    # profile material values (LOW density softening); coverage adds to the per-ToD bias
    for n, v in p["material"].items():
        params[n] = params.get(n, 0.0) + v if n == "CloudCoverage" else v
    for n, v in params.items():
        mid.set_scalar_parameter_value(n, v)
    mid.set_vector_parameter_value("CloudAmbient", unreal.LinearColor(a[0], a[1], a[2], 0.0))
    c.set_material(mid)
    params["CloudAmbient"] = list(a)
    return {"quality": quality, "material": MATERIALS[quality], "cvars": p["cvars"], "notes": notes,
            "params": params, "visible": bool(c.is_visible())}
