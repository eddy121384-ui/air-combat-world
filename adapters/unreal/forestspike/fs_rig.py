"""ForestSpike fixed lighting / exposure rig (UE5.8 editor Python). One preset: a clear day.

Constants are copied from the accepted XinyiLook "day" calibration (host-calibrated manual exposure, same
SkyAtmosphere / SkyLight / fog scheme) so ForestSpike frames are directly comparable with Xinyi frames in
tone. Everything is fixed in code: no eye adaptation, no per-arm differences.
"""
import math

import unreal
from fs_common import find_actor

RIG = {"sun": "FS_Sun", "atmo": "FS_SkyAtmosphere", "sky": "FS_SkyLight", "fog": "FS_HeightFog", "pp": "FS_PostProcess"}
SUN_AZ_DEG = 135.0       # azimuth clockwise from north: sun in the south-east, side-lighting NE-looking cameras
SUN_EL_DEG = 40.0
SUN_INTENSITY = 3.7
SUN_COLOR = (1.0, 0.92, 0.81)
SKY_INTENSITY = 2.2
EXPOSURE_BIAS_EV = math.log2(0.64) + 2.0
FOG_DENSITY = 0.00011 / 0.025
FOG_FALLOFF = 0.2
FOG_START_CM = 50000.0
FOG_INSCATTER = (0.40, 0.44, 0.46)
AERIAL_SCALE = 2.4
AERIAL_START_KM = 2.5
LOWER_HEMISPHERE = (0.09, 0.087, 0.08)


def sun_rotator(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    fx = -math.sin(az) * math.cos(el)
    fy = math.cos(az) * math.cos(el)
    fz = -math.sin(el)
    return unreal.Rotator(0.0, math.degrees(math.asin(max(-1.0, min(1.0, fz)))), math.degrees(math.atan2(fy, fx)))


def spawn_rig(actors):
    def spawn(cls, label, loc=(0.0, 0.0, 0.0)):
        a = find_actor(actors, label)
        if a is None:
            a = actors.spawn_actor_from_class(cls, unreal.Vector(*loc))
            a.set_actor_label(label)
        return a

    sun = spawn(unreal.DirectionalLight, RIG["sun"], (0.0, 0.0, 80000.0))
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    for prop, val in (("atmosphere_sun_light", True), ("light_source_angle", 0.53),
                      ("dynamic_shadow_distance_movable_light", 250000.0),
                      ("dynamic_shadow_cascades", 4), ("cascade_distribution_exponent", 3.0)):
        try:
            sc.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("sun %s: %s" % (prop, exc))
    sun.set_actor_rotation(sun_rotator(SUN_AZ_DEG, SUN_EL_DEG), False)
    sc.set_intensity(SUN_INTENSITY)
    sc.set_light_color(unreal.LinearColor(SUN_COLOR[0], SUN_COLOR[1], SUN_COLOR[2], 1.0))

    ac = spawn(unreal.SkyAtmosphere, RIG["atmo"]).get_component_by_class(unreal.SkyAtmosphereComponent)
    ac.set_aerial_pespective_view_distance_scale(AERIAL_SCALE)
    ac.set_editor_property("aerial_perspective_start_depth", AERIAL_START_KM)

    sky = spawn(unreal.SkyLight, RIG["sky"], (0.0, 0.0, 60000.0))
    skc = sky.get_component_by_class(unreal.SkyLightComponent)
    skc.set_mobility(unreal.ComponentMobility.MOVABLE)
    skc.set_editor_property("real_time_capture", True)
    skc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
    skc.set_intensity(SKY_INTENSITY)
    skc.set_editor_property("lower_hemisphere_is_black", True)
    skc.set_lower_hemisphere_color(unreal.LinearColor(LOWER_HEMISPHERE[0], LOWER_HEMISPHERE[1], LOWER_HEMISPHERE[2], 1.0))

    fc = spawn(unreal.ExponentialHeightFog, RIG["fog"]).get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_fog_density(FOG_DENSITY)
    fc.set_fog_height_falloff(FOG_FALLOFF)
    fc.set_start_distance(FOG_START_CM)
    fc.set_fog_inscattering_color(unreal.LinearColor(FOG_INSCATTER[0], FOG_INSCATTER[1], FOG_INSCATTER[2], 1.0))
    try:
        fc.set_editor_property("fog_max_opacity", 0.92)
    except Exception:  # noqa: BLE001
        pass

    pp = spawn(unreal.PostProcessVolume, RIG["pp"])
    pp.set_editor_property("unbound", True)
    pp.set_editor_property("priority", 10.0)
    s = pp.get_editor_property("settings")
    for prop, val in (
        ("override_auto_exposure_method", True), ("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL),
        ("override_auto_exposure_apply_physical_camera_exposure", True),
        ("auto_exposure_apply_physical_camera_exposure", False),
        ("override_auto_exposure_bias", True), ("auto_exposure_bias", EXPOSURE_BIAS_EV),
        ("override_bloom_intensity", True), ("bloom_intensity", 0.0),
        ("override_motion_blur_amount", True), ("motion_blur_amount", 0.0),
        ("override_ambient_occlusion_intensity", True), ("ambient_occlusion_intensity", 0.0),
        ("override_vignette_intensity", True), ("vignette_intensity", 0.0),
    ):
        try:
            s.set_editor_property(prop, val)
        except Exception as exc:  # noqa: BLE001
            unreal.log_warning("pp %s: %s" % (prop, exc))
    pp.set_editor_property("settings", s)
