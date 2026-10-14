"""Shared Blender look-dev stage for single-tree review renders (Cycles, headless).

Every tree is rendered on the same stage: physical sky + sun, neutral grass ground, a 1.7 m scale
figure, fixed exposure, and four auto-framed cameras (front, oblique, top, close).
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

SUN_ELEVATION_DEG = 38.0
SUN_AZIMUTH_DEG = 215.0  # light from front-left (camera looks +Y)
EXPOSURE = 0.0


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def _sky_world(scene):
    world = bpy.data.worlds.new("TG_World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    for t in ("MULTIPLE_SCATTERING", "NISHITA", "SINGLE_SCATTERING", "HOSEK_WILKIE"):
        try:
            sky.sky_type = t
            break
        except TypeError:
            continue
    for attr, val in (
        ("sun_elevation", math.radians(SUN_ELEVATION_DEG)),
        ("sun_rotation", math.radians(SUN_AZIMUTH_DEG)),
        ("altitude", 100.0),
        ("air_density", 1.0),
        ("aerosol_density", 1.6),
        ("dust_density", 1.6),
        ("ozone_density", 1.0),
        ("sun_disc", False),
    ):
        if hasattr(sky, attr):
            setattr(sky, attr, val)
    bg.inputs["Strength"].default_value = 0.22
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])


def _sun(scene):
    data = bpy.data.lights.new("TG_Sun", "SUN")
    data.energy = 4.2
    data.angle = math.radians(0.6)
    data.color = (1.0, 0.96, 0.9)
    obj = bpy.data.objects.new("TG_Sun", data)
    scene.collection.objects.link(obj)
    el = math.radians(SUN_ELEVATION_DEG)
    az = math.radians(SUN_AZIMUTH_DEG)
    # direction the light travels (from sun toward ground)
    d = Vector((-math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), -math.sin(el)))
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def _ground_material():
    m = bpy.data.materials.new("TG_Ground")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.03, 0.04, 0.015, 1)
    ramp.color_ramp.elements[1].color = (0.07, 0.07, 0.03, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    return m


def _ground(scene, size=400.0):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "TG_Ground"
    g.data.materials.append(_ground_material())
    return g


def _scale_figure(scene, x, y):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.7, vertices=16, location=(x, y, 0.85))
    f = bpy.context.active_object
    f.name = "TG_ScaleFigure_1p7m"
    m = bpy.data.materials.new("TG_Figure")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.5, 0.5, 0.52, 1)
    f.data.materials.append(m)
    return f


def setup_stage(scene, samples=64, res=(1920, 1080), figure_xy=(4.0, -3.0)):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.cycles.transparent_max_bounces = 16
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Base Contrast"
    except TypeError:
        pass
    scene.view_settings.exposure = EXPOSURE
    _sky_world(scene)
    _sun(scene)
    _ground(scene)
    if figure_xy is not None:
        _scale_figure(scene, *figure_xy)


def _camera(scene, name, loc, target, lens=35.0, ortho_scale=None):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = 0.05
    data.clip_end = 2000
    if ortho_scale:
        data.type = "ORTHO"
        data.ortho_scale = ortho_scale
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = loc
    direction = Vector(target) - Vector(loc)
    up = "Y"
    if abs(direction.normalized().z) > 0.99:
        obj.rotation_euler = (0, 0, 0)
    else:
        obj.rotation_euler = direction.to_track_quat("-Z", up).to_euler()
    return obj


def make_cameras(scene, height, spread, close_target=None, close_from=None):
    """Frame a tree of `height` (m) and crown `spread` (m) centred on the origin."""
    cz = height * 0.5
    span = max(height, spread * 0.75) * 1.35
    dist = span / (2 * math.tan(math.radians(16.3)))  # 35 mm vertical half-fov on 16:9
    cams = {
        "front": _camera(scene, "CAM_front", (0, -dist, height * 0.36), (0, 0, cz * 0.98)),
        # 32 deg down, 50 mm from further away (a 35 mm lens this close exaggerates the near crown into a box)
        "oblique": _camera(
            scene,
            "CAM_oblique",
            (
                dist * 1.43 * math.cos(math.radians(32)) * math.sin(math.radians(40)),
                -dist * 1.43 * math.cos(math.radians(32)) * math.cos(math.radians(40)),
                height * 0.5 + dist * 1.43 * math.sin(math.radians(32)),
            ),
            (0, 0, height * 0.5),
            lens=50.0,
        ),
        "top": _camera(scene, "CAM_top", (0, 0, height + 60), (0, 0, 0), ortho_scale=spread * 1.3 * 16 / 9),
    }
    if close_target is not None:
        cams["close"] = _camera(scene, "CAM_close", close_from, close_target, lens=50.0)
    return cams


def render_views(scene, cams, out_dir, prefix, views=None, samples=None):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for view, cam in cams.items():
        if views and view not in views:
            continue
        scene.camera = cam
        if samples:
            scene.cycles.samples = samples
        path = os.path.join(out_dir, f"{prefix}_{view}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        paths.append(path)
        print("RENDERED", path)
    return paths

