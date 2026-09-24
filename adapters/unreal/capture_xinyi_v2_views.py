"""Capture four readable deterministic QA views using SceneCapture2D.

This deliberately avoids editor-viewport / AutomationLibrary screenshot state.
The previous unattended viewport backend proved unstable and could inherit debug
view modes. This route owns its renderer explicitly:

SceneCapture2D -> TextureRenderTarget2D -> FINAL_COLOR_LDR -> PNG

The persisted XinyiV2 geometry contract remains read-only. Presentation overrides
and lighting actors are transient and the level is never saved.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import traceback

import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"
RUNTIME_PREFIX = "XinyiRuntimeTile_"

BUILDING_MATERIAL = "/Game/XinyiV2/QA/M_XinyiV2_BuildingWhitebox"
TERRAIN_MATERIAL = "/Game/XinyiV2/QA/M_XinyiV2_TerrainWhitebox"

OUT_DIR = Path(
    os.environ.get(
        "ACW_XINYI_V2_CAPTURE_DIR",
        str(Path(unreal.Paths.project_saved_dir()) / "XinyiUnrealV2" / "Captures"),
    )
).resolve()
REPORT_PATH = OUT_DIR / "capture_report.json"
ERROR_PATH = OUT_DIR / "capture_error.txt"

WIDTH = 1920
HEIGHT = 1080

VIEWS = [
    {
        "name": "01-aerial",
        "location_cm": [-25000.0, -25000.0, 270000.0],
        "target_cm": [-25000.0, -25000.0, 5000.0],
        "fov": 50.0,
    },
    {
        "name": "02-nw-to-se",
        "location_cm": [-235000.0, -235000.0, 115000.0],
        "target_cm": [-20000.0, -10000.0, 7000.0],
        "fov": 55.0,
    },
    {
        "name": "03-sw-to-ne",
        "location_cm": [-230000.0, 165000.0, 90000.0],
        "target_cm": [-10000.0, -45000.0, 7000.0],
        "fov": 55.0,
    },
    {
        "name": "04-southeast-to-core",
        "location_cm": [165000.0, 165000.0, 80000.0],
        "target_cm": [-30000.0, -35000.0, 9000.0],
        "fov": 52.0,
    },
]

OUT_DIR.mkdir(parents=True, exist_ok=True)
if ERROR_PATH.exists():
    ERROR_PATH.unlink()

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assets = unreal.EditorAssetLibrary

if not levels.load_level(LEVEL):
    raise RuntimeError("failed to load XinyiV2 runtime level: %s" % LEVEL)

all_actors = list(actors.get_all_level_actors())
labels = {a.get_actor_label(): a for a in all_actors}
terrain = labels.get(TERRAIN_LABEL)
if terrain is None:
    raise RuntimeError("validated terrain actor missing before capture")

runtime_actors = [
    a for a in all_actors if a.get_actor_label().startswith(RUNTIME_PREFIX)
]
if len(runtime_actors) != 25:
    raise RuntimeError(
        "expected 25 runtime building tile actors before capture, found %d"
        % len(runtime_actors)
    )

building_mat = assets.load_asset(BUILDING_MATERIAL)
terrain_mat = assets.load_asset(TERRAIN_MATERIAL)
if building_mat is None or terrain_mat is None:
    raise RuntimeError(
        "whitebox QA materials missing; run prepare_xinyi_v2_whitebox_materials.py first"
    )

# ---------------------------------------------------------------------------
# In-memory QA presentation only. Never save these overrides to the level.
# ---------------------------------------------------------------------------

terrain.set_editor_property("landscape_material", terrain_mat)

building_components = 0
material_slots_overridden = 0
for actor in runtime_actors:
    comps = actor.get_components_by_class(unreal.StaticMeshComponent)
    if len(comps) != 1:
        raise RuntimeError(
            "runtime tile %s has %d StaticMeshComponents, expected 1"
            % (actor.get_actor_label(), len(comps))
        )
    comp = comps[0]
    building_components += 1
    slots = max(1, int(comp.get_num_materials()))
    for slot in range(slots):
        comp.set_material(slot, building_mat)
        material_slots_overridden += 1

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

# ---------------------------------------------------------------------------
# Capture-only daylight rig.
# ---------------------------------------------------------------------------

sun = actors.spawn_actor_from_class(
    unreal.DirectionalLight,
    unreal.Vector(0.0, 0.0, 60000.0),
    unreal.Rotator(0.0, -38.0, -35.0),
)
sun.set_actor_label("XinyiCapture_Sun")
sun_comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
sun_comp.set_mobility(unreal.ComponentMobility.MOVABLE)
sun_comp.set_intensity(18.0)
sun_comp.set_editor_property("atmosphere_sun_light", True)
try:
    sun_comp.set_editor_property("light_source_angle", 1.2)
except Exception:
    pass

atmosphere = actors.spawn_actor_from_class(
    unreal.SkyAtmosphere,
    unreal.Vector(0.0, 0.0, 0.0),
    unreal.Rotator(0.0, 0.0, 0.0),
)
atmosphere.set_actor_label("XinyiCapture_SkyAtmosphere")

sky = actors.spawn_actor_from_class(
    unreal.SkyLight,
    unreal.Vector(0.0, 0.0, 50000.0),
    unreal.Rotator(0.0, 0.0, 0.0),
)
sky.set_actor_label("XinyiCapture_SkyLight")
sky_comp = sky.get_component_by_class(unreal.SkyLightComponent)
sky_comp.set_mobility(unreal.ComponentMobility.MOVABLE)
sky_comp.set_editor_property("real_time_capture", False)
sky_comp.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
sky_comp.set_editor_property("intensity", 1.25)

fog = actors.spawn_actor_from_class(
    unreal.ExponentialHeightFog,
    unreal.Vector(0.0, 0.0, 0.0),
    unreal.Rotator(0.0, 0.0, 0.0),
)
fog.set_actor_label("XinyiCapture_Fog")
fog_comp = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
fog_comp.set_fog_density(0.002)
fog_comp.set_fog_height_falloff(0.16)
fog_comp.set_fog_inscattering_color(
    unreal.LinearColor(0.58, 0.68, 0.78, 1.0)
)
try:
    fog_comp.set_editor_property("fog_max_opacity", 0.35)
except Exception:
    pass

try:
    sky_comp.recapture_sky()
except Exception:
    pass

# ---------------------------------------------------------------------------
# Independent render backend: SceneCapture2D -> RenderTarget2D.
# ---------------------------------------------------------------------------

render_target = unreal.RenderingLibrary.create_render_target2d(
    world,
    WIDTH,
    HEIGHT,
    unreal.TextureRenderTargetFormat.RTF_RGBA8,
    unreal.LinearColor(0.0, 0.0, 0.0, 1.0),
    False,
)
if render_target is None:
    raise RuntimeError("create_render_target2d returned None")

capture_actor = actors.spawn_actor_from_class(
    unreal.SceneCapture2D,
    unreal.Vector(0.0, 0.0, 100000.0),
    unreal.Rotator(0.0, -90.0, 0.0),
)
capture_actor.set_actor_label("XinyiCapture_SceneCapture2D")
capture = capture_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
if capture is None:
    raise RuntimeError("SceneCapture2D actor has no SceneCaptureComponent2D")

capture.set_editor_property("texture_target", render_target)
capture.set_editor_property(
    "capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR
)
capture.set_editor_property("capture_every_frame", False)
capture.set_editor_property("capture_on_movement", False)
capture.set_editor_property("always_persist_rendering_state", True)
capture.set_editor_property("render_in_main_renderer", False)
try:
    capture.set_editor_property("max_view_distance_override", 1000000.0)
except Exception:
    pass

pp = unreal.PostProcessSettings()
pp.set_editor_property("override_auto_exposure_method", True)
pp.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
pp.set_editor_property(
    "override_auto_exposure_apply_physical_camera_exposure", True
)
pp.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
pp.set_editor_property("override_auto_exposure_bias", True)
pp.set_editor_property("auto_exposure_bias", 0.0)
pp.set_editor_property("override_motion_blur_amount", True)
pp.set_editor_property("motion_blur_amount", 0.0)
pp.set_editor_property("override_bloom_intensity", True)
pp.set_editor_property("bloom_intensity", 0.0)
capture.set_editor_property("post_process_settings", pp)
capture.set_editor_property("post_process_blend_weight", 1.0)

# Stable renderer knobs. None of these depend on the editor viewport view mode.
unreal.SystemLibrary.execute_console_command(world, "r.ScreenPercentage 100")
unreal.SystemLibrary.execute_console_command(world, "r.MotionBlurQuality 0")
unreal.SystemLibrary.execute_console_command(world, "r.RayTracing 0")
unreal.SystemLibrary.execute_console_command(world, "r.EyeAdaptationQuality 2")
unreal.SystemLibrary.execute_console_command(world, "r.Tonemapper.Sharpen 0.25")

state = {
    "index": 0,
    "phase": "warmup",
    "warmup_count": 0,
    "started": time.monotonic(),
    "captures": [],
}
TIMEOUT_SECONDS = 360.0
WARMUP_CAPTURES = 24
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def vec(values):
    return unreal.Vector(float(values[0]), float(values[1]), float(values[2]))


def set_capture_view(spec):
    location = vec(spec["location_cm"])
    target = vec(spec["target_cm"])
    rotation = unreal.MathLibrary.find_look_at_rotation(location, target)
    capture_actor.set_actor_location_and_rotation(
        location,
        rotation,
        False,
        True,
    )
    capture.set_editor_property("fov_angle", float(spec["fov"]))


def export_current(spec):
    output = OUT_DIR / (spec["name"] + ".png")
    if output.exists():
        output.unlink()

    capture.capture_scene()
    unreal.RenderingLibrary.export_render_target(
        world,
        render_target,
        str(OUT_DIR),
        output.name,
    )

    if not output.is_file():
        raise RuntimeError("render-target export did not create: %s" % output)
    if output.stat().st_size < 4096:
        raise RuntimeError("render-target export too small: %s" % output)
    with output.open("rb") as fh:
        signature = fh.read(8)
    if signature != PNG_SIGNATURE:
        raise RuntimeError(
            "render-target export is not a PNG: %s signature=%r"
            % (output, signature)
        )

    state["captures"].append(
        {
            "name": spec["name"],
            "path": str(output),
            "bytes": output.stat().st_size,
            "location_cm": spec["location_cm"],
            "target_cm": spec["target_cm"],
            "fov": spec["fov"],
        }
    )


def finish(success=True):
    try:
        unreal.unregister_slate_post_tick_callback(handle)
    except Exception:
        pass

    report = {
        "status": "PASS_CAPTURE" if success else "FAIL_CAPTURE",
        "backend": (
            "SceneCapture2D -> TextureRenderTarget2D(RTF_RGBA8) "
            "-> SCS_FINAL_COLOR_LDR -> export_render_target"
        ),
        "editor_viewport_dependency": False,
        "level": LEVEL,
        "terrain_label": TERRAIN_LABEL,
        "runtime_tile_actor_count": len(runtime_actors),
        "runtime_building_component_count": building_components,
        "material_slots_overridden": material_slots_overridden,
        "building_material": BUILDING_MATERIAL,
        "terrain_material": TERRAIN_MATERIAL,
        "lighting": {
            "sky_atmosphere": True,
            "sky_light": True,
            "sun_lux": 18.0,
            "sky_intensity": 1.25,
            "height_fog": True,
        },
        "resolution": [WIDTH, HEIGHT],
        "warmup_captures": state["warmup_count"],
        "captures": state["captures"],
        "elapsed_seconds": time.monotonic() - state["started"],
        "world_saved_after_overrides": False,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log(
        "XINYI_V2_SCENECAPTURE_REPORT "
        + json.dumps(report, separators=(",", ":"))
    )

    try:
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    except Exception:
        pass
    unreal.SystemLibrary.quit_editor()


def tick(_delta):
    try:
        if time.monotonic() - state["started"] > TIMEOUT_SECONDS:
            raise RuntimeError("XinyiV2 SceneCapture2D sequence timed out")

        if state["phase"] == "warmup":
            # Prime shadow maps / atmosphere / sky capture through the same
            # renderer used for the final frames.
            set_capture_view(VIEWS[1])
            capture.capture_scene()
            state["warmup_count"] += 1
            if state["warmup_count"] >= WARMUP_CAPTURES:
                state["phase"] = "capture"
            return

        if state["index"] >= len(VIEWS):
            finish(True)
            return

        spec = VIEWS[state["index"]]
        set_capture_view(spec)

        # Two captures after a camera cut: first primes temporal/render state,
        # second is the exported deterministic frame.
        capture.capture_scene()
        export_current(spec)

        state["index"] += 1

    except Exception:
        ERROR_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        unreal.log_error(
            "XINYI_V2_SCENECAPTURE_FAILED " + traceback.format_exc()
        )
        state["captures"].append(
            {"error": traceback.format_exc(), "index": state["index"]}
        )
        finish(False)


handle = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
unreal.log(
    "XINYI_V2_SCENECAPTURE_STARTED "
    + json.dumps(
        {
            "out": str(OUT_DIR),
            "resolution": [WIDTH, HEIGHT],
            "backend": "SceneCapture2D",
        },
        separators=(",", ":"),
    )
)
