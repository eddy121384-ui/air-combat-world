"""Blender 5.2 headless fixed-camera renders of the terrain vertical slice (read-only use of accepted Xinyi assets).

Scene (NTW frame, recentred on the pilot-cell junction (308000, 2768000) EPSG:3826):
  * new terrain chunks of both pilot cells at --lod (+ the Xinyi seam stitch strip at that LOD)
  * accepted Xinyi Landscape surface rebuilt from the ACCEPTED 631 x 631 R16 (exactly what Unreal imports), in its ENU frame
  * accepted Xinyi runtime building tiles (surveyed ground baked), in their ENU frame
  * Xinyi ENU -> NTW placement = measured affine (rotation 0.239 deg + anisotropic scale), object transform only;
    accepted files are read, never written
Cameras (EPSG:3826 + metres above TWVD2001) are fixed in CAMERAS so runs are comparable. Workbench engine (headless-safe).
usage: blender -b --python tools/ntw/blender_terrain_views.py -- --run <terrain run dir> --lod 0 --out <dir> [--debug-seam]
       [--cameras seam_150m,xinyi_300m]
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

REPO = Path(__file__).resolve().parents[2]
NTW_ORIGIN = (224000.0, 2688000.0)
CENTRE = (308000.0, 2768000.0)
CONTRACT = Path(r"D:\Users\EDDY\Documents\GitHub\air-combat-world\unreal\Saved\XinyiUnrealV2Inputs\run-35822928983\unreal\Saved\XinyiUnrealV2Contract")
CAMERAS = {  # name: (eye E, eye N, eye Z, target E, target N, target Z, ortho_scale or None)
    "seam_150m": (306600, 2767450, 165, 306850, 2768620, 20, None),
    "xinyi_300m": (304300, 2766900, 310, 306800, 2769800, 30, None),
    "hills_600m": (309800, 2761500, 640, 306300, 2770500, 30, None),
    "overview_800m": (302500, 2760300, 820, 308200, 2770200, 60, None),
    "far_3km": (308000, 2749000, 3000, 308000, 2768500, 80, None),
    "top_ortho": (308000, 2768000, 6000, 308000, 2768000, 0, 17000.0),
}


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--lod", type=int, default=0)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--debug-seam", action="store_true")
    p.add_argument("--cameras", default=",".join(CAMERAS))
    p.add_argument("--no-buildings", action="store_true")
    return p.parse_args(a)


def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    return m


def local(e, n):
    return (e - CENTRE[0], n - CENTRE[1])


def import_glb(path, parent, material):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=False, import_shading="NORMALS")
    for o in set(bpy.data.objects) - before:
        if o.parent is None:
            o.parent = parent
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(material)


def xinyi_landscape(parent, material):
    c = json.loads((CONTRACT / "xinyi_unreal_v2_contract.json").read_text(encoding="utf-8"))
    n = c["landscape"]["heightmap_size"][0]
    sz = c["landscape"]["height_encoding"]["scale_z"]
    h = (np.frombuffer((CONTRACT / c["outputs"]["heightmap_r16"]["path"]).read_bytes(), dtype="<u2").reshape(n, n).astype(np.float64) - 32768.0) * sz / 12800.0
    e0, n1 = c["coordinate_contract"]["extent_enu_m"]["min_east_m"], c["coordinate_contract"]["extent_enu_m"]["max_north_m"]
    step = 2500.0 / (n - 1)
    cols, rows = np.meshgrid(np.arange(n), np.arange(n))
    V = np.column_stack([(e0 + cols * step).ravel(), (n1 - rows * step).ravel(), h.ravel()])
    idx = np.arange(n * n).reshape(n, n)
    a, b, cc, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    F = np.concatenate([np.stack([a, cc, d, b], -1).reshape(-1, 4)])
    me = bpy.data.meshes.new("xinyi_landscape_accepted_r16")
    me.from_pydata(V.tolist(), [], F.tolist())
    me.update()
    ob = bpy.data.objects.new("xinyi_landscape_accepted_r16", me)
    bpy.context.collection.objects.link(ob)
    ob.parent = parent
    me.materials.append(material)
    for p_ in me.polygons:
        p_.use_smooth = True


def xinyi_parent():
    study = json.loads((REPO / "data/ntw/coordinate_study.json").read_text(encoding="utf-8"))["xinyi_enu_to_ntw_affine"]
    M = np.array(study["linear_part"])
    t = np.array(study["translation_m"])  # ENU -> NTW frame
    tx, ty = t[0] + NTW_ORIGIN[0] - CENTRE[0], t[1] + NTW_ORIGIN[1] - CENTRE[1]
    emp = bpy.data.objects.new("xinyi_enu_to_ntw_affine", None)
    bpy.context.collection.objects.link(emp)
    emp.matrix_world = Matrix(((M[0, 0], M[0, 1], 0, tx), (M[1, 0], M[1, 1], 0, ty), (0, 0, 1, 0), (0, 0, 0, 1)))
    return emp


def camera(name, spec):
    ex, ey, ez, tx, ty, tz, ortho = spec
    cd = bpy.data.cameras.new(name)
    cd.clip_end = 120000
    cd.clip_start = 1.0
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.sensor_fit = "VERTICAL"
        cd.angle_y = math.radians(60.0)
    co = bpy.data.objects.new(name, cd)
    bpy.context.collection.objects.link(co)
    co.location = Vector((*local(ex, ey), ez))
    if ortho:
        co.rotation_euler = (0, 0, 0)
    else:
        direction = Vector((*local(tx, ty), tz)) - co.location
        co.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return co


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_shadows = False  # Workbench shadow volumes need manifold meshes; open terrain + skirts create false dark patches
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sc.display.shadow_focus = 0.5
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.image_settings.file_format = "PNG"
    sc.world = bpy.data.worlds.new("w")
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.72, 0.80, 0.88)
    root = bpy.data.objects.new("ntw_root", None)
    bpy.context.collection.objects.link(root)
    root.location = (-(CENTRE[0] - NTW_ORIGIN[0]), -(CENTRE[1] - NTW_ORIGIN[1]), 0)
    m_terrain = mat("terrain", (0.46, 0.52, 0.40))
    m_stitch = mat("stitch", (0.85, 0.15, 0.1) if a.debug_seam else (0.46, 0.52, 0.40))
    m_xin = mat("xinyi_landscape", (0.25, 0.45, 0.85) if a.debug_seam else (0.46, 0.52, 0.40))
    m_bld = mat("buildings", (0.86, 0.86, 0.84))
    files = sorted(a.run.glob(f"chunks/*/ch??_lod{a.lod}.glb"))
    for f in files:
        import_glb(f, root, m_terrain)
    for f in sorted(a.run.glob(f"chunks/*/xinyi_stitch_lod{a.lod}.glb")):
        import_glb(f, root, m_stitch)
    xp = xinyi_parent()
    xinyi_landscape(xp, m_xin)
    if not a.no_buildings:
        for f in sorted((CONTRACT / "building_runtime_tiles").glob("*.glb")):
            key = f.stem.split("_")[-2:]
            ix, iy = int(key[0]), int(key[1])
            tile = bpy.data.objects.new(f"xinyi_tile_{ix}_{iy}", None)
            bpy.context.collection.objects.link(tile)
            tile.parent = xp
            tile.location = (ix * 500.0, iy * 500.0, 0.0)
            import_glb(f, tile, m_bld)
    a.out.mkdir(parents=True, exist_ok=True)
    tag = f"lod{a.lod}" + ("_seamdebug" if a.debug_seam else "")
    done = []
    for name in a.cameras.split(","):
        cam = camera(name, CAMERAS[name])
        sc.camera = cam
        sc.render.filepath = str(a.out / f"{name}_{tag}.png")
        bpy.ops.render.render(write_still=True)
        done.append(sc.render.filepath)
    print(json.dumps({"rendered": done, "terrain_files": len(files), "blender": bpy.app.version_string}))


main()
