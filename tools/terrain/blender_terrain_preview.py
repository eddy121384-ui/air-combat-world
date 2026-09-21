"""Render Xinyi buildings anchored to surveyed WFS ground elevation over terrain.

Visualization only. Building vertex/face buffers are never modified; only each
building object's world-up translation is adjusted from the audited WFS
ground_elev_m manifest. Terrain is the labeled cloud prototype DSM surface.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ID_RE = re.compile(r"^(tp_building_height\.\d+)")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--")+1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--buildings", type=Path, required=True)
    p.add_argument("--terrain", type=Path, required=True)
    p.add_argument("--building-z", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def import_glbs(directory, prefix):
    objects = []
    for glb in sorted(directory.glob("*.glb")):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(
            filepath=str(glb),
            merge_vertices=False,
            import_shading="NORMALS",
        )
        added = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        for o in added:
            o["preview_layer"] = prefix
        objects.extend(added)
    return objects


def bounds(objects):
    pts = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    return mins, maxs


def look_at(camera, target):
    camera.rotation_euler = (Vector(target)-camera.location).to_track_quat("-Z","Y").to_euler()


def render(scene, camera, path):
    scene.camera = camera
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    a = parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    terrain = import_glbs(a.terrain, "terrain")
    buildings = import_glbs(a.buildings, "building")
    if not terrain or not buildings:
        raise RuntimeError(f"import failed terrain={len(terrain)} buildings={len(buildings)}")

    zdata = json.loads(a.building_z.read_text(encoding="utf-8"))
    offsets = zdata["offsets_m"]
    missing = []
    applied = 0
    for obj in buildings:
        m = ID_RE.match(obj.name)
        if not m:
            missing.append(obj.name)
            continue
        bid = m.group(1)
        if bid not in offsets:
            missing.append(obj.name)
            continue
        matrix = obj.matrix_world.copy()
        # GLB/game frame is X=east, Y=up, Z=-north. Elevation must move on Y.\n        matrix.translation.y += float(offsets[bid])
        obj.matrix_world = matrix
        applied += 1

    if missing:
        raise RuntimeError(f"missing building Z for {len(missing)} objects; first={missing[:10]}")

    # Regression guard: imported building bases must land on surveyed ground Z.
    # This catches accidental use of the internal GLB Y-up axis after Blender
    # has already converted the scene to Z-up.
    base_z_errors = []
    base_z_rows = []
    for obj in buildings:
        m = ID_RE.match(obj.name)
        bid = m.group(1)
        expected = float(offsets[bid])
        world_base_z = min((obj.matrix_world @ Vector(corner)).z for corner in obj.bound_box)
        err = abs(world_base_z - expected)
        base_z_errors.append(err)
        if len(base_z_rows) < 50:
            base_z_rows.append({
                "name": obj.name,
                "building_id": bid,
                "expected_ground_m": expected,
                "world_base_z_m": world_base_z,
                "abs_error_m": err,
            })
    max_base_z_error = max(base_z_errors, default=0.0)
    if max_base_z_error > 1.0e-3:
        raise RuntimeError(
            f"building base-Z regression: max abs error {max_base_z_error:.6g} m"
        )

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "OBJECT"
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.025, 0.035, 0.055)
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "WORLD"
    shading.curvature_ridge_factor = 1.5
    shading.curvature_valley_factor = 1.2
    shading.show_specular_highlight = False

    for o in buildings:
        o.color = (0.80, 0.84, 0.90, 1.0)
    for o in terrain:
        o.color = (0.26, 0.34, 0.29, 1.0)

    all_objects = terrain + buildings
    mins,maxs = bounds(all_objects)
    center = Vector((
        (mins[0]+maxs[0])/2,
        (mins[1]+maxs[1])/2,
        (mins[2]+maxs[2])/2,
    ))
    span = max(maxs[0]-mins[0], maxs[1]-mins[1], 1.0)

    cam_data = bpy.data.cameras.new("TerrainPreviewCamera")
    cam = bpy.data.objects.new("TerrainPreviewCamera", cam_data)
    scene.collection.objects.link(cam)
    cam.data.clip_start = 0.5
    cam.data.clip_end = span*10 + maxs[2]

    # Northwest -> southeast: puts the southeast hillside behind the urban core.
    cam.data.type = "PERSP"
    cam.data.lens = 55
    cam.location = (
        center.x - span*0.88,
        center.y + span*0.92,
        maxs[2] + span*0.56,
    )
    look_at(cam, (center.x, center.y, mins[2] + (maxs[2]-mins[2])*0.25))
    render(scene,cam,a.out/"01-xinyi-terrain-nw-to-se.png")

    # Southwest -> northeast alternative.
    cam.location = (
        center.x - span*0.92,
        center.y - span*0.82,
        maxs[2] + span*0.64,
    )
    look_at(cam, (center.x, center.y, mins[2] + (maxs[2]-mins[2])*0.24))
    render(scene,cam,a.out/"02-xinyi-terrain-sw-to-ne.png")

    # High aerial for terrain/building relationship.
    cam.location = (
        center.x - span*0.45,
        center.y + span*0.50,
        maxs[2] + span*1.18,
    )
    cam.data.lens = 62
    look_at(cam, center)
    render(scene,cam,a.out/"03-xinyi-terrain-aerial.png")

    # Top view for tile/coverage inspection.
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = span*1.08
    cam.location = (center.x,center.y,maxs[2]+span*1.3)
    cam.rotation_euler = (0,0,0)
    render(scene,cam,a.out/"04-xinyi-terrain-top.png")

    report = {
        "status":"PROTOTYPE_PREVIEW",
        "terrain_objects":len(terrain),
        "building_objects":len(buildings),
        "building_z_applied":applied,
        "missing_building_z":len(missing),
        "building_base_z_max_abs_error_m":max_base_z_error,
        "building_base_z_preview":base_z_rows,
        "bounds_min":mins,
        "bounds_max":maxs,
        "renders":[p.name for p in sorted(a.out.glob("*.png"))],
        "warning":"Terrain surface is Copernicus GLO-30 DSM prototype, not production bare-earth DTM."
    }
    (a.out/"preview.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
