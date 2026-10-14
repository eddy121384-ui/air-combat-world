"""Tool evaluation: Modular Tree (MTree 5.5.2, GPL-3.0) OAK preset with its own leaves, on the shared stage.

blender -b --factory-startup --python tools/treegen/mtree_eval.py -- <out_dir>
"""
import os
import sys

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(__file__))
import tg_scene  # noqa: E402

out_dir = sys.argv[sys.argv.index("--") + 1]
scene = tg_scene.reset_scene()
addon_utils.enable("bl_ext.blender_org.modular_tree", default_set=True)
tg_scene.setup_stage(scene, samples=48, res=(1280, 720))

# MTree 5.5.2 targets Blender <= 5.1: it sets geometry-nodes modifier inputs with modifier[id] = v,
# which Blender 5.2 rejects ("id properties not supported"). Patch in memory only (addon files untouched):
# 5.2 exposes the same inputs as attributes of modifier.properties.inputs.
import importlib  # noqa: E402
import inspect  # noqa: E402
import re  # noqa: E402
import textwrap  # noqa: E402

_ng = importlib.import_module("bl_ext.blender_org.modular_tree.python_classes.resources.node_groups")
_src = textwrap.dedent(inspect.getsource(_ng.distribute_leaves))
_src = re.sub(r"modifier\[socket_id\] = (.+)", r"_mt_set(modifier, socket_id, \1)", _src)


def _mt_set(modifier, socket_id, value):
    item = getattr(modifier.properties.inputs, socket_id)
    print("MT_SET", socket_id, type(item).__name__, [a for a in dir(item) if not a.startswith("_")][:12])
    item.value = value


_ng.__dict__["_mt_set"] = _mt_set
exec(compile(_src, _ng.__file__, "exec"), _ng.__dict__)
_ops = importlib.import_module("bl_ext.blender_org.modular_tree.python_classes.operators")
_ops.distribute_leaves = _ng.distribute_leaves

bpy.ops.mtree.quick_generate(seed=17, preset="OAK", add_leaves=True)
tree = bpy.context.view_layer.objects.active
dg = bpy.context.evaluated_depsgraph_get()
ev = tree.evaluated_get(dg)
bb = [ev.matrix_world @ __import__("mathutils").Vector(c) for c in ev.bound_box]
h = max(v.z for v in bb)
spread = max(max(v.x for v in bb) - min(v.x for v in bb), max(v.y for v in bb) - min(v.y for v in bb))
tris = sum(len(p.vertices) - 2 for p in tree.data.polygons)
print(f"MTREE height={h:.2f} spread={spread:.2f} branch_tris={tris}")
m = bpy.data.materials.new("bark")
m.use_nodes = True
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.22, 0.19, 1)
tree.data.materials.append(m)
cams = tg_scene.make_cameras(scene, h, spread)
tg_scene.render_views(scene, cams, out_dir, "mtree_oak", views=["front", "oblique"])
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "mtree_oak_eval.blend"))
