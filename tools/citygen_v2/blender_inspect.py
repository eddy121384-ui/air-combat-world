"""Execute via blender_official.execute_blender_code, never as a modeler.

Creates new inspection scenes, imports GLBs unchanged, and measures raw faces.
Call view(scene, target, eye) then screenshot(path) in a subsequent MCP call.
"""
from pathlib import Path
import json
import math
from collections import Counter
import bpy
from mathutils import Vector


def import_scene(name, paths):
    scene = bpy.data.scenes.new(name)
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    for path in paths:
        bpy.ops.import_scene.gltf(filepath=str(path), import_shading='NORMALS')
    bpy.context.view_layer.update()
    return scene


def measure(scene):
    output = []
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        # Work only on numbers; do not weld/repair the scene's mesh.
        verts = [obj.matrix_world @ v.co for v in mesh.vertices]
        faces = Counter()
        for tri in mesh.loop_triangles:
            a, b, c = [verts[i] for i in tri.vertices]
            n = (b-a).cross(c-a)
            if n.length <= 2e-10:
                faces['zero_area'] += 1
            elif max(a.z, b.z, c.z)-min(a.z, b.z, c.z) < 1e-4:
                is_base = max(abs(a.z), abs(b.z), abs(c.z)) < 1e-4
                faces[('base_down' if n.z < 0 else 'base_wrong') if is_base else
                      ('roof_up' if n.z > 0 else 'roof_wrong')] += 1
            else:
                faces['walls'] += 1
        output.append({'name':obj.name, 'vertices':len(verts),
                       'triangles':len(mesh.loop_triangles), 'faces':dict(faces),
                       'nonfinite_vertices':sum(not all(math.isfinite(x) for x in v) for v in verts),
                       'bounds_m':[[min(v[i] for v in verts) for i in range(3)],
                                   [max(v[i] for v in verts) for i in range(3)]]})
    return output


def view(scene, target, eye):
    bpy.context.window.scene = scene
    target, eye = Vector(target), Vector(eye)
    for area in bpy.context.window.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            space.shading.type = 'SOLID'
            space.shading.light = 'STUDIO'
            space.shading.color_type = 'SINGLE'
            space.shading.single_color = (.7,.7,.7)
            space.shading.show_backface_culling = True
            space.overlay.show_overlays = False
            space.clip_end = 20000
            rv = space.region_3d
            rv.view_rotation = (target-eye).to_track_quat('-Z','Y')
            rv.view_location = target
            rv.view_distance = (eye-target).length
            rv.view_perspective = 'ORTHO'
            area.tag_redraw()
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)


def screenshot(path):
    bpy.ops.screen.screenshot(filepath=str(path), check_existing=False)
    return str(path)


def inspect(root, output):
    root, output = Path(root), Path(output)
    sample = json.loads((output/'sample.json').read_text())
    accepted = import_scene('Xinyi_V2_Accepted_Sample', [output/'sample'/t['file'] for t in sample['tiles']])
    failed = import_scene('Xinyi_V2_FAILED_Diagnostics', [output/'sample'/sample['diagnostic_file']])
    old = import_scene('Xinyi_V2_Compare_Old_PR3', [root/'data/generated/taipei/xinyi_tile_2km.glb'])
    evidence = root/'docs/evidence/citygen-v2'
    evidence.mkdir(parents=True, exist_ok=True)
    report = {'blender_version':bpy.app.version_string, 'coordinate_frame':'ENU Z-up meters',
              'source_sha256':sample['source_sha256'],
              'accepted':measure(accepted), 'failed_diagnostics':measure(failed), 'old':measure(old),
              'scenes':{'accepted':accepted.name,'failed':failed.name,'old':old.name}}
    (evidence/'blender-inspection.json').write_text(json.dumps(report, indent=2)+'\n')
    view(accepted, (-890,-880,10), (-770,-1090,180))
    return report
