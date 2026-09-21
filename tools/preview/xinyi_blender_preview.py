"""Render readable full-Xinyi whitebox previews from validated GLB tiles.

Visualization only: this does not modify or validate production geometry.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--tiles", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def look_at(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def world_bounds(objects):
    pts = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    return mins, maxs


def render(scene, camera, path):
    scene.camera = camera
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    objects = []
    for tile in sorted(args.tiles.glob("*.glb")):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(
            filepath=str(tile),
            merge_vertices=False,
            import_shading="NORMALS",
        )
        objects.extend(
            o for o in bpy.data.objects
            if o not in before and o.type == "MESH"
        )

    if not objects:
        raise RuntimeError("No mesh objects imported")

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 950
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    # Deterministic technical whitebox styling.
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "SINGLE"
    shading.single_color = (0.78, 0.82, 0.88)
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.035, 0.045, 0.065)
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "WORLD"
    shading.curvature_ridge_factor = 1.5
    shading.curvature_valley_factor = 1.2
    shading.show_specular_highlight = False

    mins, maxs = world_bounds(objects)
    center = Vector((
        (mins[0] + maxs[0]) * 0.5,
        (mins[1] + maxs[1]) * 0.5,
        (mins[2] + maxs[2]) * 0.5,
    ))
    span_x = maxs[0] - mins[0]
    span_y = maxs[1] - mins[1]
    span = max(span_x, span_y, 1.0)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam = bpy.data.objects.new("PreviewCamera", cam_data)
    scene.collection.objects.link(cam)
    cam.data.clip_start = 0.5
    cam.data.clip_end = span * 8.0 + maxs[2]

    # Full district oblique.
    cam.data.type = "PERSP"
    cam.data.lens = 58
    cam.location = (
        center.x + span * 0.88,
        center.y - span * 1.02,
        maxs[2] + span * 0.72,
    )
    look_at(cam, center)
    render(scene, cam, args.out / "01-xinyi-whitebox-full-oblique.png")

    # Higher aerial view.
    cam.data.lens = 64
    cam.location = (
        center.x - span * 0.70,
        center.y - span * 0.78,
        maxs[2] + span * 1.15,
    )
    look_at(cam, center)
    render(scene, cam, args.out / "02-xinyi-whitebox-aerial.png")

    # Top-down map-like view.
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = span * 1.08
    cam.location = (center.x, center.y, maxs[2] + span * 1.3)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    render(scene, cam, args.out / "03-xinyi-whitebox-top.png")

    print({
        "objects": len(objects),
        "bounds_min": mins,
        "bounds_max": maxs,
        "renders": [p.name for p in sorted(args.out.glob("*.png"))],
    })


if __name__ == "__main__":
    main()
