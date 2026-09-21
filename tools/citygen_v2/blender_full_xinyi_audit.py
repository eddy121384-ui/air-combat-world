"""Independent Blender headless audit for the full Xinyi v2 tile set.

Run only after the full numerical/GLB gate passes. This script imports every
published tile GLB into a clean Blender scene, validates imported mesh buffers
without mutating geometry, and writes machine-readable evidence plus simple
overview renders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import sys
import time
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector


def _args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--tiles", type=Path, required=True)
    p.add_argument("--numerical", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--screenshots", type=Path, required=True)
    p.add_argument("--blend", type=Path)
    return p.parse_args(argv)


def _rss_mb():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def _finite(v):
    return all(math.isfinite(float(x)) for x in v)


def _tri_area(a, b, c):
    return ((b - a).cross(c - a)).length * 0.5


def _signed_volume(vertices, faces):
    """Translation-invariant signed volume with a local reference origin.

    Blender mathutils stores mesh coordinates at float32 precision. Summing
    scalar triple products against the world/local origin can catastrophically
    cancel for very small footprints located tens or hundreds of metres from
    (0,0,0). A closed mesh has translation-invariant volume, so recenter before
    accumulation instead of weakening the volume gate.
    """
    if not vertices:
        return 0.0
    origin = sum(vertices, Vector((0.0, 0.0, 0.0))) / len(vertices)
    total = 0.0
    for i, j, k in faces:
        a = vertices[i] - origin
        b = vertices[j] - origin
        c = vertices[k] - origin
        total += a.dot(b.cross(c)) / 6.0
    return total


def _mesh_audit(obj):
    mesh = obj.data
    vertices = [Vector(v.co) for v in mesh.vertices]
    faces = [tuple(p.vertices) for p in mesh.polygons]
    failures = []
    counts = Counter()

    if not vertices or not faces:
        failures.append("empty_mesh")
        return {"pass": False, "failures": failures, "counts": dict(counts)}

    counts["nonfinite_vertices"] = sum(not _finite(v) for v in vertices)
    counts["nontri_faces"] = sum(len(f) != 3 for f in faces)

    z_values = [v.z for v in vertices]
    zmin, zmax = min(z_values), max(z_values)
    ztol = max(1e-6, abs(zmax - zmin) * 1e-8)

    edges = Counter()
    balance = Counter()
    zero_area = wrong_roof = wrong_base = wrong_walls = 0

    for face in faces:
        if len(face) != 3:
            continue
        a, b, c = (vertices[i] for i in face)
        cross = (b - a).cross(c - a)
        area = cross.length * 0.5
        if not math.isfinite(area) or area <= 1e-8:
            zero_area += 1
            continue
        normal = cross.normalized()
        zs = (a.z, b.z, c.z)
        is_base = all(abs(z - zmin) <= ztol for z in zs)
        is_roof = all(abs(z - zmax) <= ztol for z in zs)
        if is_roof and normal.z <= 0:
            wrong_roof += 1
        elif is_base and normal.z >= 0:
            wrong_base += 1
        elif not is_roof and not is_base and abs(normal.z) > 1e-5:
            wrong_walls += 1

        coords = [tuple(float(x) for x in vertices[i]) for i in face]
        for u, v in zip(coords, coords[1:] + coords[:1]):
            key = tuple(sorted((u, v)))
            edges[key] += 1
            balance[key] += 1 if u < v else -1

    counts["zero_area_triangles"] = zero_area
    counts["wrong_roof_triangles"] = wrong_roof
    counts["wrong_base_triangles"] = wrong_base
    counts["nonvertical_wall_triangles"] = wrong_walls
    counts["nonmanifold_edges"] = sum(n != 2 for n in edges.values())
    counts["inconsistent_edges"] = sum(n != 0 for n in balance.values())

    volume = _signed_volume(vertices, [f for f in faces if len(f) == 3])
    counts["nonpositive_volume"] = int(not math.isfinite(volume) or volume <= 0)

    matrix = obj.matrix_world
    tx, ty, tz = float(matrix.translation.x), float(matrix.translation.y), float(matrix.translation.z)
    grid_ok = (
        abs(tx / 500.0 - round(tx / 500.0)) <= 1e-7
        and abs(ty / 500.0 - round(ty / 500.0)) <= 1e-7
        and abs(tz) <= 1e-7
    )
    counts["wrong_tile_transform"] = int(not grid_ok)

    for key, value in counts.items():
        if value:
            failures.append(f"{key}:{value}")

    return {
        "pass": not failures,
        "failures": failures,
        "counts": dict(counts),
        "vertices": len(vertices),
        "triangles": len(faces),
        "z_min": zmin,
        "z_max": zmax,
        "signed_volume_m3": volume,
        "matrix_translation": [tx, ty, tz],
    }


def _look_at(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _world_bounds(objects):
    pts = []
    for obj in objects:
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    return mins, maxs


def _render_views(objects, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    try:
        scene.render.engine = "BLENDER_WORKBENCH"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE_NEXT"

    if hasattr(scene, "display"):
        try:
            scene.display.shading.light = "STUDIO"
            scene.display.shading.show_shadows = True
            scene.display.shading.show_cavity = True
        except Exception:
            pass

    camera_data = bpy.data.cameras.new("XinyiAuditCamera")
    camera = bpy.data.objects.new("XinyiAuditCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    mins, maxs = _world_bounds(objects)
    center = [(mins[i] + maxs[i]) * 0.5 for i in range(3)]
    span_x, span_y = maxs[0] - mins[0], maxs[1] - mins[1]
    span = max(span_x, span_y, 1.0)

    # Whole-district top view.
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = span * 1.08
    camera.location = (center[0], center[1], maxs[2] + span)
    camera.rotation_euler = (0.0, 0.0, 0.0)
    scene.render.filepath = str(out_dir / "01-full-xinyi-top.png")
    bpy.ops.render.render(write_still=True)

    # Whole-district oblique.
    camera.data.type = "PERSP"
    camera.data.lens = 55
    camera.location = (
        center[0] + span * 0.70,
        center[1] - span * 0.70,
        maxs[2] + span * 0.60,
    )
    _look_at(camera, center)
    scene.render.filepath = str(out_dir / "02-full-xinyi-oblique.png")
    bpy.ops.render.render(write_still=True)

    # Central / origin neighborhood, useful for detecting tile seams and hero suppression area.
    central = [
        o for o in objects
        if abs(o.matrix_world.translation.x) <= 500.0
        and abs(o.matrix_world.translation.y) <= 500.0
    ]
    if central:
        cmins, cmaxs = _world_bounds(central)
        ccenter = [(cmins[i] + cmaxs[i]) * 0.5 for i in range(3)]
        cspan = max(cmaxs[0] - cmins[0], cmaxs[1] - cmins[1], 1.0)
        for obj in objects:
            obj.hide_render = obj not in central
        camera.data.type = "PERSP"
        camera.location = (
            ccenter[0] + cspan * 0.75,
            ccenter[1] - cspan * 0.75,
            cmaxs[2] + cspan * 0.65,
        )
        _look_at(camera, ccenter)
        scene.render.filepath = str(out_dir / "03-central-tiles-oblique.png")
        bpy.ops.render.render(write_still=True)
        for obj in objects:
            obj.hide_render = False

    return {
        "bounds_min": mins,
        "bounds_max": maxs,
        "center": center,
        "central_objects": len(central),
        "renders": sorted(p.name for p in out_dir.glob("*.png")),
    }


def main():
    args = _args()
    started = time.perf_counter()
    numerical = json.loads(args.numerical.read_text(encoding="utf-8"))
    expected_meshes = int(numerical["accounting"]["emitted_serialization_components"])
    expected_tiles = int(numerical["tile_summary"]["count"])
    expected_triangles = int(numerical["tile_summary"]["total_triangles"])

    tile_paths = sorted(args.tiles.glob("*.glb"))
    if len(tile_paths) != expected_tiles:
        raise RuntimeError(f"Expected {expected_tiles} tile GLBs, found {len(tile_paths)}")

    bpy.ops.wm.read_factory_settings(use_empty=True)

    imported = []
    tile_hashes = {}
    for tile in tile_paths:
        tile_hashes[tile.name] = hashlib.sha256(tile.read_bytes()).hexdigest()
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(
            filepath=str(tile),
            merge_vertices=False,
            import_shading="NORMALS",
        )
        after = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        imported.extend(after)

    rows = []
    totals = Counter()
    for obj in imported:
        result = _mesh_audit(obj)
        for key, value in result["counts"].items():
            totals[key] += int(value)
        rows.append({"object": obj.name, **result})

    imported_triangles = sum(r["triangles"] for r in rows)
    global_failures = []
    if len(imported) != expected_meshes:
        global_failures.append(f"mesh_count:{len(imported)}!={expected_meshes}")
    if imported_triangles != expected_triangles:
        global_failures.append(f"triangle_count:{imported_triangles}!={expected_triangles}")
    failed_meshes = sum(not r["pass"] for r in rows)
    if failed_meshes:
        global_failures.append(f"failed_meshes:{failed_meshes}")

    report = {
        "gate": "Full Xinyi Blender 5.2 headless imported-buffer gate",
        "blender_version": bpy.app.version_string,
        "numerical_manifest_sha256": numerical["tile_summary"]["manifest_sha256"],
        "expected_tiles": expected_tiles,
        "imported_tiles": len(tile_paths),
        "expected_mesh_components": expected_meshes,
        "imported_mesh_components": len(imported),
        "expected_triangles": expected_triangles,
        "imported_triangles": imported_triangles,
        "failed_meshes": failed_meshes,
        "totals": dict(totals),
        "tile_glb_sha256": tile_hashes,
        "geometry_pass": not global_failures,
        "render": {"status": "pending"},
        "render_failure": None,
        "runtime_seconds": time.perf_counter() - started,
        "max_rss_mb": _rss_mb(),
        "failures": list(global_failures),
        "pass": False,
        "objects": rows,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Persist imported-buffer evidence before invoking any graphics backend.
    # A native EGL/driver abort must not erase the geometry diagnosis.
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    render_info = {}
    render_failure = None
    try:
        render_info = _render_views(imported, args.screenshots)
    except Exception as exc:
        render_failure = f"{type(exc).__name__}:{exc}"
        global_failures.append(f"render_failed:{render_failure}")

    report = {
        "gate": "Full Xinyi Blender 5.2 headless imported-buffer gate",
        "blender_version": bpy.app.version_string,
        "numerical_manifest_sha256": numerical["tile_summary"]["manifest_sha256"],
        "expected_tiles": expected_tiles,
        "imported_tiles": len(tile_paths),
        "expected_mesh_components": expected_meshes,
        "imported_mesh_components": len(imported),
        "expected_triangles": expected_triangles,
        "imported_triangles": imported_triangles,
        "failed_meshes": failed_meshes,
        "totals": dict(totals),
        "tile_glb_sha256": tile_hashes,
        "render": render_info,
        "render_failure": render_failure,
        "runtime_seconds": time.perf_counter() - started,
        "max_rss_mb": _rss_mb(),
        "failures": global_failures,
        "pass": not global_failures,
        "objects": rows,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    if args.blend:
        args.blend.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.blend))

    print(json.dumps({
        "pass": report["pass"],
        "blender_version": report["blender_version"],
        "tiles": report["imported_tiles"],
        "meshes": report["imported_mesh_components"],
        "triangles": report["imported_triangles"],
        "failed_meshes": failed_meshes,
        "totals": report["totals"],
        "renders": report["render"].get("renders", []),
        "runtime_seconds": report["runtime_seconds"],
        "max_rss_mb": report["max_rss_mb"],
        "failures": global_failures,
    }, indent=2))

    if not report["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
