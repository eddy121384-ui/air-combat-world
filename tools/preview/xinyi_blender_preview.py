"""Render human-readable full-Xinyi whitebox previews from validated GLB tiles.

This is visualization only. It does not modify or validate production geometry.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--tiles", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def look_at(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def bounds(objects):
    pts = [obj.matrix_world @ Vector(c) for obj in objects for c in obj.bound_box]
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    return mins, maxs


def main():
    a = args()
    a.out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    objects = []
    for tile in sorted(a.tiles.glob("*.glb")):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(
            filepath=str(tile),
            merge_vertices=False,
            import_shading="NORMALS",
        )
        objects += [o for o in bpy.data.objects if o not in before and o.type == "MESH"]

    if not objects:
        raise RuntimeError("No mesh objects imported")

    # Neutral whitebox material.
    mat = bpy.data.materials.new("Whitebox")
    mat.diffuse_color = (0.72, 0.76, 0.82, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.72, 0.76, 0.82, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.88
        bsdf.inputs["Metallic"].default_value = 0.0
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    # Keep tone mapping simple and bright enough for technical review.
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.8

    world = bpy.data.worlds.new("WhiteboxWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.055, 0.065, 0.085, 1.0)
    bg.inputs["Strength"].default_value = 0.45
    scene.world = world

    # Sun + broad area light.
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = 0.12
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (0.75, -0.55, -0.65)

    area_data = bpy.data.lights.new("Fill", "AREA")
    area_data.energy = 2500.0
    area_data.shape = "DISK"
    area_data.size = 2000.0
    area = bpy.data.objects.new("Fill", area_data)
    scene.collection.objects.link(area)

    mins, maxs = bounds(objects)
    center = Vector(((mins[0]+maxs[0])*0.5, (mins[1]+maxs[1])*0.5, (mins[2]+maxs[2])*0.5))
    span_x, span_y = maxs[0]-mins[0], maxs[1]-mins[1]
    span = max(span_x, span_y, 1.0)
    area.location = (center.x - span*0.25, center.y - span*0.2, maxs[2] + span*0.85)
    area.rotation_euler = (0.0, 0.0, 0.0)

    # Ground plane only for visual readability; not part of geometry.
    bpy.ops.mesh.primitive_plane_add(size=span*1.35, location=(center.x, center.y, mins[2]-0.02))
    ground = bpy.context.object
    ground.name = "PreviewGround"
    gmat = bpy.data.materials.new("Ground")
    gmat.diffuse_color = (0.08, 0.095, 0.12, 1.0)
    gmat.use_nodes = True
    gbsdf = gmat.node_tree.nodes.get("Principled BSDF")
    if gbsdf:
        gbsdf.inputs["Base Color"].default_value = (0.08, 0.095, 0.12, 1.0)
        gbsdf.inputs["Roughness"].default_value = 1.0
    ground.data.materials.append(gmat)

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam = bpy.data.objects.new("PreviewCamera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.clip_start = 0.5
    cam.data.clip_end = span * 8.0 + maxs[2]

    # 1) Isometric-ish full district.
    cam.data.type = "PERSP"
    cam.data.lens = 58
    cam.location = (center.x + span*0.88, center.y - span*1.02, maxs[2] + span*0.72)
    look_at(cam, center)
    scene.render.filepath = str(a.out / "01-xinyi-whitebox-full-oblique.png")
    bpy.ops.render.render(write_still=True)

    # 2) Higher aerial oblique.
    cam.data.lens = 64
    cam.location = (center.x - span*0.70, center.y - span*0.78, maxs[2] + span*1.15)
    look_at(cam, center)
    scene.render.filepath = str(a.out / "02-xinyi-whitebox-aerial.png")
    bpy.ops.render.render(write_still=True)

    # 3) Top-down map-like view.
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = span * 1.08
    cam.location = (center.x, center.y, maxs[2] + span*1.3)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    scene.render.filepath = str(a.out / "03-xinyi-whitebox-top.png")
    bpy.ops.render.render(write_still=True)

    print({
        "objects": len(objects),
        "bounds_min": mins,
        "bounds_max": maxs,
        "renders": [p.name for p in sorted(a.out.glob("*.png"))],
    })


if __name__ == "__main__":
    main()
