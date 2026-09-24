"""Capture four readable deterministic QA views of the passing XinyiV2 runtime world.

The persisted geometry contract is read-only here. Capture-only presentation:
- two QA materials created under /Game/XinyiV2/QA;
- material overrides applied only to the loaded editor world;
- temporary SkyAtmosphere / SkyLight / sun / fill / camera actors;
- no level save after presentation overrides.

Expected persisted world:
- /Game/XinyiV2/L_XinyiV2_Contract
- Terrain_Xinyi_MOI2025
- exactly 25 XinyiRuntimeTile_* actors
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

# Presentation overrides are intentionally NOT saved to the level.
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
# Capture-only daylight rig
# ---------------------------------------------------------------------------

sun = actors.spawn_actor_from_class(
    unreal.DirectionalLight,
    unreal.Vector(0.0, 0.0, 60000.0),
    unreal.Rotator(-38.0, -32.0, 0.0),
)
sun.set_actor_label("XinyiCapture_Sun")
sun_comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
sun_comp.set_intensity(8.0)
sun_comp.set_editor_property("atmosphere_sun_light", True)
try:
    sun_comp.set_editor_property("light_source_angle", 1.5)
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
sky_comp.set_editor_property("real_time_capture", True)
sky_comp.set_editor_property("intensity", 1.35)

fill = actors.spawn_actor_from_class(
    unreal.DirectionalLight,
    unreal.Vector(0.0, 0.0, 40000.0),
    unreal.Rotator(-18.0, 145.0, 0.0),
)
fill.set_actor_label("XinyiCapture_Fill")
fill_comp = fill.get_component_by_class(unreal.DirectionalLightComponent)
fill_comp.set_intensity(0.8)
try:
    fill_comp.set_editor_property("cast_shadows", False)
except Exception:
    pass

camera = actors.spawn_actor_from_class(
    unreal.CameraActor,
    unreal.Vector(0.0, 0.0, 100000.0),
    unreal.Rotator(0.0, 0.0, 0.0),
)
camera.set_actor_label("XinyiCapture_Camera")
camera.camera_component.set_field_of_view(55.0)

# Stable QA rendering; stay within desktop SM5 baseline.
unreal.SystemLibrary.execute_console_command(world, "r.ScreenPercentage 100")
unreal.SystemLibrary.execute_console_command(world, "r.MotionBlurQuality 0")
unreal.SystemLibrary.execute_console_command(world, "r.RayTracing 0")
unreal.SystemLibrary.execute_console_command(world, "r.HighResScreenshotDelay 16")
unreal.SystemLibrary.execute_console_command(world, "r.EyeAdaptationQuality 2")
unreal.SystemLibrary.execute_console_command(world, "r.Tonemapper.Sharpen 0.35")

try:
    sky_comp.recapture_sky()
except Exception:
    pass

state = {
    "index": 0,
    "task": None,
    "phase": "warmup",
    "phase_started": time.monotonic(),
    "started": time.monotonic(),
    "captures": [],
}
TIMEOUT_SECONDS = 360.0


def vec(values):
    return unreal.Vector(float(values[0]), float(values[1]), float(values[2]))


def set_view(spec):
    location = vec(spec["location_cm"])
    target = vec(spec["target_cm"])
    rotation = unreal.MathLibrary.find_look_at_rotation(location, target)
    camera.set_actor_location(location, False, False)
    camera.set_actor_rotation(rotation, False)
    camera.camera_component.set_field_of_view(float(spec["fov"]))


def finish(success=True):
    try:
        unreal.unregister_slate_post_tick_callback(handle)
    except Exception:
        pass

    report = {
        "status": "PASS_CAPTURE" if success else "FAIL_CAPTURE",
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
            "sun_intensity": 8.0,
            "fill_intensity": 0.8,
        },
        "resolution": [WIDTH, HEIGHT],
        "captures": state["captures"],
        "elapsed_seconds": time.monotonic() - state["started"],
        "world_saved_after_overrides": False,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("XINYI_V2_CAPTURE_REPORT " + json.dumps(report, separators=(",", ":")))

    try:
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    except Exception:
        pass
    unreal.SystemLibrary.quit_editor()


def tick(_delta):
    try:
        now = time.monotonic()
        if now - state["started"] > TIMEOUT_SECONDS:
            raise RuntimeError("XinyiV2 screenshot sequence timed out")

        if state["phase"] == "warmup":
            # Give simple material shaders + atmosphere + skylight enough time
            # to settle before the first deterministic frame.
            if now - state["phase_started"] >= 14.0:
                try:
                    sky_comp.recapture_sky()
                except Exception:
                    pass
                state["phase"] = "position"
                state["phase_started"] = now
            return

        if state["index"] >= len(VIEWS):
            finish(True)
            return

        spec = VIEWS[state["index"]]

        if state["phase"] == "position":
            set_view(spec)
            state["phase"] = "settle"
            state["phase_started"] = now
            return

        if state["phase"] == "settle":
            if now - state["phase_started"] < 3.0:
                return
            output = OUT_DIR / (spec["name"] + ".png")
            if output.exists():
                output.unlink()
            state["task"] = unreal.AutomationLibrary.take_high_res_screenshot(
                WIDTH,
                HEIGHT,
                str(output),
                camera=camera,
                delay=1.0,
            )
            state["phase"] = "capture"
            state["phase_started"] = now
            unreal.log("XINYI_V2_CAPTURE_REQUEST " + str(output))
            return

        if state["phase"] == "capture":
            task = state["task"]
            if task is None:
                raise RuntimeError("Automation screenshot task was not created")
            if not task.is_task_done():
                return

            output = OUT_DIR / (spec["name"] + ".png")
            if not output.is_file() or output.stat().st_size < 4096:
                raise RuntimeError(
                    "screenshot task completed but PNG is missing/too small: %s" % output
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
            state["index"] += 1
            state["task"] = None
            state["phase"] = "position"
            state["phase_started"] = now
            return

    except Exception:
        ERROR_PATH.write_text(traceback.format_exc(), encoding="utf-8")
        unreal.log_error("XINYI_V2_CAPTURE_FAILED " + traceback.format_exc())
        state["captures"].append(
            {"error": traceback.format_exc(), "index": state["index"]}
        )
        finish(False)


handle = unreal.register_slate_post_tick_callback(tick)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
unreal.log("XINYI_V2_READABLE_WHITEBOX_CAPTURE_STARTED " + str(OUT_DIR))
