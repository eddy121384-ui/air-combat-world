"""Non-geometric viewport setup for visual review of imported gate evidence."""
import math
import bpy
from mathutils import Vector, Quaternion


def prepare_view(scene, names=None, top=False, wire=False):
    meshes = [o for o in scene.objects if o.type == 'MESH']
    selected = [o for o in meshes if names is None or o.name in names]
    assert selected and (names is None or len(selected) == len(names))
    for o in meshes:
        o.hide_set(o not in selected)
        o.select_set(o in selected)
        o.show_wire = wire
        o.show_all_edges = wire
    bpy.context.view_layer.objects.active = selected[0]
    points = [o.matrix_world @ Vector(c) for o in selected for c in o.bound_box]
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    for area in bpy.context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        space = area.spaces.active
        space.shading.type = 'SOLID'
        space.shading.color_type = 'SINGLE'
        space.shading.single_color = (.72,.75,.79)
        space.shading.show_cavity = True
        space.shading.cavity_type = 'BOTH'
        space.shading.show_shadows = True
        space.overlay.show_floor = False
        space.overlay.show_axis_x = False
        space.overlay.show_axis_y = False
        space.overlay.show_extras = False
        space.region_3d.view_perspective = 'ORTHO'
        space.region_3d.view_rotation = Quaternion((1,0,0,0)) if top else Vector((1,-1,1.5)).to_track_quat('Z','Y')
        space.region_3d.view_location = (lo+hi)/2
        space.region_3d.view_distance = max(2., (hi-lo).length*1.65)
        space.clip_end = 10000
        area.tag_redraw()
    bpy.context.view_layer.update()
    return {'nodes':[o.name for o in selected], 'top':top,'wire':wire,
            'bounds_enu':[list(lo),list(hi)]}
