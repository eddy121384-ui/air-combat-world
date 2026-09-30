"""XinyiLook time-of-day rig (UE5.8 editor Python).

Presets come from tools/lookdev/preview/shots.json ("light" block) so the
preview renderer and Unreal share one source of truth. Mapping:

  sunAz/sunEl      -> DirectionalLight rotation (azimuth clockwise from north)
  sunRad           -> sun colour * intensity (lux-like, same shading units)
  fogDen (1/m)     -> ExponentialHeightFog density factor (~ /0.025)
  fogCol           -> fog inscattering colour (includes night city glow)
  exposure         -> manual exposure compensation log2(exposure)
  night / litFrac  -> MPC_XinyiLook Night / LitFrac

Absolute Unreal calibration (fog density scale, exposure curve) still needs a
host capture; EmissiveScale in the MPC is the single emission trim knob.
"""
import json
import math

import unreal
from xinyi_look_common import LOOK_PREFIX, MPC_PATH, SHOTS, lib

RIG = {
    "sun": LOOK_PREFIX + "Sun",
    "atmo": LOOK_PREFIX + "SkyAtmosphere",
    "sky": LOOK_PREFIX + "SkyLight",
    "fog": LOOK_PREFIX + "HeightFog",
    "pp": LOOK_PREFIX + "PostProcess",
}
SKY_INTENSITY = {"day": 1.0, "dusk": 0.85, "night": 0.35}
BLOOM = {"day": 0.15, "dusk": 0.45, "night": 0.8}
FOG_SCALE = 0.025
# Host calibration (UE5.8 lit viewport, HighResShot): the preview "exposure" presets are in preview
# shading units. In UE manual exposure (EV100 0) with the same sun value the sun-lit scene sits
# ~2 stops low, and the ACES toe crushes the physically dim SkyAtmosphere to near-black. +2.0 EV
# gives a clear Taipei day sky with no clipping. Night is emissive-lit and calibrated separately.
UE_EXPOSURE_OFFSET_EV = {"day": 2.0, "dusk": 2.0, "night": 0.0}


def presets():
    return json.loads(SHOTS.read_text(encoding="utf-8"))["light"]


def sun_rotator(az_deg, el_deg):
    az, el = math.radians(az_deg), math.radians(el_deg)
    # light travels from the sun toward the scene; UE Y = -north
    fx = -math.sin(az) * math.cos(el)
    fy = math.cos(az) * math.cos(el)
    fz = -math.sin(el)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, fz))))
    yaw = math.degrees(math.atan2(fy, fx))
    return unreal.Rotator(0.0, pitch, yaw)


def find(actors, label):
    for a in actors.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def spawn_rig(actors):
    def spawn(cls, label, loc=(0.0, 0.0, 0.0)):
        a = find(actors, label)
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
        except Exception as exc:
            unreal.log_warning("sun %s: %s" % (prop, exc))
    spawn(unreal.SkyAtmosphere, RIG["atmo"])
    sky = spawn(unreal.SkyLight, RIG["sky"], (0.0, 0.0, 60000.0))
    skc = sky.get_component_by_class(unreal.SkyLightComponent)
    skc.set_mobility(unreal.ComponentMobility.MOVABLE)
    skc.set_editor_property("real_time_capture", True)
    skc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
    spawn(unreal.ExponentialHeightFog, RIG["fog"])
    pp = spawn(unreal.PostProcessVolume, RIG["pp"])
    pp.set_editor_property("unbound", True)
    pp.set_editor_property("priority", 10.0)


def apply_tod(world, actors, name, persist_mpc_defaults=False):
    L = presets()[name]
    sun = find(actors, RIG["sun"])
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    rad = L["sunRad"]
    inten = max(rad)
    if inten <= 1e-6:
        # night: faint cool moonlight keeps silhouettes readable
        sun.set_actor_rotation(sun_rotator(135.0, 55.0), False)
        sc.set_intensity(0.03)
        sc.set_light_color(unreal.LinearColor(0.55, 0.65, 1.0, 1.0))
    else:
        sun.set_actor_rotation(sun_rotator(L["sunAz"], L["sunEl"]), False)
        sc.set_intensity(float(inten))
        sc.set_light_color(unreal.LinearColor(rad[0] / inten, rad[1] / inten, rad[2] / inten, 1.0))

    skc = find(actors, RIG["sky"]).get_component_by_class(unreal.SkyLightComponent)
    skc.set_intensity(SKY_INTENSITY.get(name, 1.0))

    fc = find(actors, RIG["fog"]).get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_fog_density(float(L["fogDen"]) / FOG_SCALE)
    fc.set_fog_height_falloff(0.2)
    c = L["fogCol"]
    fc.set_fog_inscattering_color(unreal.LinearColor(c[0], c[1], c[2], 1.0))
    try:
        fc.set_editor_property("fog_max_opacity", 0.92)
    except Exception:
        pass

    pp = find(actors, RIG["pp"])
    s = pp.get_editor_property("settings")
    for prop, val in (
        ("override_auto_exposure_method", True),
        ("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL),
        ("override_auto_exposure_apply_physical_camera_exposure", True),
        ("auto_exposure_apply_physical_camera_exposure", False),
        ("override_auto_exposure_bias", True),
        ("auto_exposure_bias", math.log2(max(1e-3, float(L["exposure"]))) + UE_EXPOSURE_OFFSET_EV.get(name, 0.0)),
        ("override_bloom_intensity", True),
        ("bloom_intensity", BLOOM.get(name, 0.3)),
        ("override_motion_blur_amount", True),
        ("motion_blur_amount", 0.0),
    ):
        s.set_editor_property(prop, val)
    pp.set_editor_property("settings", s)

    mpc = lib.load_asset(MPC_PATH)
    # Python exposes UKismetMaterialLibrary without the Kismet prefix (like SystemLibrary / MathLibrary).
    unreal.MaterialLibrary.set_scalar_parameter_value(world, mpc, "Night", float(L["night"]))
    unreal.MaterialLibrary.set_scalar_parameter_value(world, mpc, "LitFrac", float(L["litFrac"]))
    if persist_mpc_defaults:
        params = mpc.get_editor_property("scalar_parameters")
        for p in params:
            n = str(p.get_editor_property("parameter_name"))
            if n == "Night":
                p.set_editor_property("default_value", float(L["night"]))
            elif n == "LitFrac":
                p.set_editor_property("default_value", float(L["litFrac"]))
        mpc.set_editor_property("scalar_parameters", params)
        lib.save_asset(MPC_PATH)
    try:
        skc.recapture_sky()
    except Exception:
        pass
    return L
