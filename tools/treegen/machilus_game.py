"""紅楠 Machilus thunbergii - game version (phase 2): golden reference -> engine-ready meshes + textures.

blender -b --factory-startup -noaudio --python tools/treegen/machilus_game.py -- <golden.blend> <out_dir>

The golden .blend is opened read-only (never saved). Geometry-nodes instances and Cycles procedural shaders do not
survive an engine export, so they are converted explicitly:

* each of the 8 spray prototypes is rendered orthographically (Cycles, emission-only passes) from its sky side ("top")
  and end-on along the shoot ("end") into a 2048^2 atlas: albedo (+ in-spray AO multiplied in), camera-space normal,
  alpha coverage;
* every one of the 15,456 spray instances becomes alpha-masked cards placed with the instance's exact transform;
  card vertex normals are blended toward the nearest crown-lobe surface normal (volumetric crown shading),
  vertex colour R = the golden per-spray tint, G = crown-depth occlusion;
* the branch mesh is re-meshed from the same deterministic skeleton with fewer sides and the thin twig ends cut
  (the cards carry their own shoots), vertex colour R = young-twig blend (the golden shader's radius blend);
* bark: tileable 512^2 albedo + normal generated with the golden palette (periodic noise, lenticels);
* LOD1 / LOD2 keep the sun-shell sprays and enlarge their cards (area-preserving), with coarser branches.

Outputs: <out>/glb/machilus_lod{0,1,2}.glb, <out>/textures/*.png, <out>/cards_lod{0,1,2}.npz (card corners + UVs, for
the offline overdraw analysis), <out>/game_report.json, <out>/views.json (camera specs shared with the UE harness).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import machilus_thunbergii as mt  # noqa: E402
import tg_tree  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1 :]
GOLDEN, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
GOLDEN_STATS = os.path.join(os.path.dirname(GOLDEN), "v1_stats.json")
TILE = 512
ATLAS = 4 * TILE
for d in ("glb", "textures", "bake"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)
report = dict(golden=GOLDEN, t0=time.time())

PROFILES = {
    # keep: fraction of sprays kept (shell-weighted); views: card views per spray; crown_w: weight of the crown normal
    "v1": [
        dict(name="lod0", keep=1.0, views=("top", "end"), crown_w=0.6, min_r=0.012,
             sides=lambda r: 10 if r > 0.16 else 8 if r > 0.07 else 6 if r > 0.03 else 4,
             sub=lambda r: 2 if r > 0.05 else 1),
        dict(name="lod1", keep=0.33, views=("top", "end"), crown_w=0.75, min_r=0.025,
             sides=lambda r: 8 if r > 0.12 else 6 if r > 0.05 else 4, sub=lambda r: 1),
        dict(name="lod2", keep=0.09, views=("top",), crown_w=0.9, min_r=0.07,
             sides=lambda r: 6 if r > 0.15 else 4, sub=lambda r: 1),
    ],
    # research/forest-tree-lod-budget-v1: same atlas, same card technique, lower geometry budget (see docs/research/forest-tree-triangle-budget-v1.md)
    "budget": [
        dict(name="lod0", keep=0.40, views=("top", "end"), crown_w=0.65, min_r=0.03,
             sides=lambda r: 8 if r > 0.16 else 6 if r > 0.07 else 4, sub=lambda r: 1),
        dict(name="lod1", keep=0.12, views=("top",), crown_w=0.8, min_r=0.09,
             sides=lambda r: 6 if r > 0.15 else 4, sub=lambda r: 1),
        dict(name="lod2", keep=0.04, views=("top",), crown_w=0.9, min_r=0.18,
             sides=lambda r: 5 if r > 0.3 else 4, sub=lambda r: 1),
        dict(name="lod3", keep=0.012, views=("top",), crown_w=0.95, min_r=0.18,
             sides=lambda r: 4, sub=lambda r: 1),
    ],
    # second iteration after the first "budget" LOD1 (top-only, 1,855 enlarged cards) read sparse / pale at 150 m slant
    "balanced": [
        dict(name="lod0", keep=0.40, views=("top", "end"), crown_w=0.65, min_r=0.03,
             sides=lambda r: 8 if r > 0.16 else 6 if r > 0.07 else 4, sub=lambda r: 1),
        dict(name="lod1", keep=0.20, views=("top", "end"), crown_w=0.75, min_r=0.06,
             sides=lambda r: 6 if r > 0.12 else 4, sub=lambda r: 1),
        dict(name="lod2", keep=0.06, views=("top",), crown_w=0.85, min_r=0.18,
             sides=lambda r: 5 if r > 0.3 else 4, sub=lambda r: 1),
        dict(name="lod3", keep=0.012, views=("top",), crown_w=0.95, min_r=0.18,
             sides=lambda r: 4, sub=lambda r: 1),
    ],
}
# hillside forest LOD1 visual recovery v0: "budget" (PR #31 candidate C) with side cards restored on LOD1 only. The kept LOD1 sprays are the
# same (same keep / rng draw); the half of them whose crown-surface normal is most horizontal (the crown's sides, seen edge-on by top-only
# cards from an oblique flight view) also get their "end" card. LOD0 / LOD2 / LOD3 are identical to "budget".
PROFILES["budget_side"] = [PROFILES["budget"][0], dict(PROFILES["budget"][1], views=("top", "end"), end_frac=0.5),
                           PROFILES["budget"][2], PROFILES["budget"][3]]
# second step: end cards on every kept LOD1 spray (card area back to ~D's with C's fewer, larger cards)
PROFILES["budget_side100"] = [PROFILES["budget"][0], dict(PROFILES["budget"][1], views=("top", "end")),
                              PROFILES["budget"][2], PROFILES["budget"][3]]
PROFILE = os.environ.get("ACW_TL_PROFILE", "v1")
LODS = PROFILES[PROFILE]
REUSE_BAKE = os.environ.get("ACW_TL_REUSE_BAKE") == "1"  # reuse <out>/bake/frames.json + the committed atlas (non-default profiles)


def fname(stem, name, ext):
    """v1 keeps the original file names; other profiles are written beside them with a profile tag."""
    return "%s_%s%s" % (stem, name, ext) if PROFILE == "v1" else "%s_%s_%s%s" % (stem, PROFILE, name, ext)


# ----------------------------------------------------------------------------- golden data (read-only)
bpy.ops.wm.open_mainfile(filepath=GOLDEN)
golden_stats = json.load(open(GOLDEN_STATS))["stats"]
sk, lobes, stats, _rng = mt.build()
if len(sk.pos) != golden_stats["nodes"]:
    raise RuntimeError("skeleton not reproduced: %d nodes vs golden %d" % (len(sk.pos), golden_stats["nodes"]))
pts_ob = bpy.data.objects["MachilusThunbergii_sprays"]
pme = pts_ob.data
n_inst = len(pme.vertices)
if n_inst != golden_stats["sprays"]:
    raise RuntimeError("instance count %d vs golden %d" % (n_inst, golden_stats["sprays"]))
I_pos = np.empty(n_inst * 3, np.float32)
pme.vertices.foreach_get("co", I_pos)
I_pos = I_pos.reshape(-1, 3)


def attr(name, width):
    a = np.empty(n_inst * width, np.float32 if name != "proto" else np.int32)
    pme.attributes[name].data.foreach_get("value", a)
    return a.reshape(-1, width) if width > 1 else a


I_rot, I_scl, I_proto, I_tint = attr("rot", 4), attr("scl", 1), attr("proto", 1), attr("tint", 1)
report["skeleton_nodes"] = len(sk.pos)
report["instances"] = n_inst
protos = [bpy.data.objects["P%d_spray" % k] for k in range(8)]


# ----------------------------------------------------------------------------- views shared with UE
def cam_spec(ob, name):
    m = ob.matrix_world
    fwd = -(m.to_3x3() @ Vector((0, 0, 1)))
    d = ob.data
    spec = dict(name=name, loc=list(m.translation), fwd=list(fwd.normalized()), res=[1920, 1080])
    if d.type == "ORTHO":
        spec.update(ortho_m=d.ortho_scale)
    else:
        spec.update(hfov_deg=math.degrees(2 * math.atan(d.sensor_width / 2 / d.lens)))
    return spec


def look(name, eye, tgt, hfov):
    f = (Vector(tgt) - Vector(eye)).normalized()
    return dict(name=name, loc=list(eye), fwd=list(f), hfov_deg=hfov, res=[1920, 1080])


views = [cam_spec(bpy.data.objects["CAM_" + v], v) for v in ("front", "oblique", "top", "close")]
views += [look("agl50", (40.0, -140.0, 50.0), (0.0, 0.0, 6.0), 60.0), look("agl200", (80.0, -330.0, 200.0), (0.0, 0.0, 6.0), 60.0)]
sun = bpy.data.objects["TG_Sun"]
sun_dir = list((sun.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized())
if PROFILE == "v1":
    json.dump(dict(views=views, sun_travel_dir_blender=sun_dir, sun_energy=sun.data.energy,
                   note="Blender metres, Z up; UE = (x, -y, z) * 100 cm"), open(os.path.join(OUT, "views.json"), "w"), indent=1)


# ----------------------------------------------------------------------------- spray atlas bake
VIEWS = {
    # camera forward F, up U (prototype local frame: +Z shoot, +Y sky side); right R = F x U
    "top": (Vector((0, -1, 0)), Vector((0, 0, 1))),
    "end": (Vector((0, 0, -1)), Vector((0, 1, 0))),
}


def frame(ob, view):
    F, U = VIEWS[view]
    R = F.cross(U)
    co = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    a, b, depth = co @ np.array(R), co @ np.array(U), co @ np.array(F)
    s = max(np.ptp(a), np.ptp(b)) * 1.04
    ac, bc = 0.5 * (a.min() + a.max()), 0.5 * (b.min() + b.max())
    C = R * float(ac) + U * float(bc) + F * float(np.median(depth))
    return dict(F=F, U=U, R=R, C=C, s=float(s), dmin=float(depth.min()), dmax=float(depth.max()))


def emission_copy(mat, tag):
    """Copy of a Principled-based material whose output is the base-colour chain as emission (albedo bake)."""
    m = mat.copy()
    m.name = "BK_%s_%s" % (tag, mat.name)
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    em = nt.nodes.new("ShaderNodeEmission")
    src = bsdf.inputs["Base Color"].links
    if src:
        nt.links.new(src[0].from_socket, em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def single(name, build):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    build(nt, em)
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def _normal(nt, em):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    vt = nt.nodes.new("ShaderNodeVectorTransform")
    vt.vector_type, vt.convert_from, vt.convert_to = "NORMAL", "WORLD", "CAMERA"
    ma = nt.nodes.new("ShaderNodeVectorMath")
    ma.operation = "MULTIPLY_ADD"
    ma.inputs[1].default_value = (0.5, 0.5, 0.5)
    ma.inputs[2].default_value = (0.5, 0.5, 0.5)
    nt.links.new(geo.outputs["Normal"], vt.inputs[0])
    nt.links.new(vt.outputs[0], ma.inputs[0])
    nt.links.new(ma.outputs[0], em.inputs["Color"])


def _ao(nt, em):
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 16
    ao.inputs["Distance"].default_value = 0.15
    nt.links.new(ao.outputs["AO"], em.inputs["Color"])


def bake_atlas():
    sc = bpy.data.scenes.new("TG_Bake")
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 0
    sc.cycles.transparent_max_bounces = 0
    sc.cycles.filter_width = 1.0
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = TILE
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.image_settings.color_depth = "8"
    cam = bpy.data.objects.new("BK_Cam", bpy.data.cameras.new("BK_Cam"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
    sc.camera = cam
    m_norm = single("BK_Normal", _normal)
    m_ao = single("BK_AO", _ao)
    frames = {}
    for k, ob in enumerate(protos):
        sc.collection.objects.link(ob)
        mats = list(ob.data.materials)
        alb = [emission_copy(m, "alb") for m in mats]
        for view in VIEWS:
            fr = frame(ob, view)
            frames[(k, view)] = fr
            cam.data.ortho_scale = fr["s"]
            cam.data.clip_start = 0.01
            cam.data.clip_end = fr["dmax"] - fr["dmin"] + 4.0
            loc = fr["C"] - fr["F"] * (float(np.dot(np.array(fr["C"]), np.array(fr["F"]))) - fr["dmin"] + 1.0)
            cam.matrix_world = Matrix.Translation(loc) @ Matrix((fr["R"], fr["U"], -fr["F"])).transposed().to_4x4()
            for pas, slot_mats, vt in (("alb", alb, "Standard"), ("nrm", [m_norm] * len(mats), "Raw"), ("ao", [m_ao] * len(mats), "Raw")):
                for i, m in enumerate(slot_mats):
                    ob.data.materials[i] = m
                sc.view_settings.view_transform = vt
                sc.render.filepath = os.path.join(OUT, "bake", "p%d_%s_%s.png" % (k, view, pas))
                bpy.ops.render.render(write_still=True, scene=sc.name)
            for i, m in enumerate(mats):
                ob.data.materials[i] = m
        sc.collection.objects.unlink(ob)
    return frames


def tile_rect(k, view):
    """Atlas tile in Blender UV (origin bottom-left). Rows 0-1 from the top: 'top' views, rows 2-3: 'end' views."""
    row = (k // 4) + (0 if view == "top" else 2)
    col = k % 4
    inset = 1.0 / ATLAS
    u0, u1 = col * 0.25 + inset, (col + 1) * 0.25 - inset
    v1 = 1.0 - row * 0.25 - inset
    v0 = 1.0 - (row + 1) * 0.25 + inset
    return u0, v0, u1, v1


# ----------------------------------------------------------------------------- crown normals / depth
def crown_normal_depth(p):
    """For points p (N,3): normal of the lobe that contains them most deeply, and the union depth."""
    best = np.full(len(p), -1e9)
    nrm = np.zeros_like(p)
    for lb in lobes:
        q = p - lb.c
        qs = q.copy()
        qs[:, 2] /= lb.zf
        ln = np.linalg.norm(qs, axis=1) + 1e-9
        d = lb.r - ln
        g = np.column_stack([qs[:, 0], qs[:, 1], qs[:, 2] / lb.zf]) / ln[:, None]
        upd = d > best
        best[upd] = d[upd]
        nrm[upd] = g[upd]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    return nrm, best


# ----------------------------------------------------------------------------- cards
def choose(lod, rng):
    if lod["keep"] >= 1.0:
        return np.arange(n_inst), 1.0
    _, depth = crown_normal_depth(I_pos.astype(np.float64))
    w = np.where(depth < mt.P["shell_depth"], 1.0, 0.25)
    prob = w / w.sum()
    idx = rng.choice(n_inst, size=int(round(lod["keep"] * n_inst)), replace=False, p=prob)
    return np.sort(idx), 1.0 / math.sqrt(lod["keep"])


def build_cards(lod, frames, rng):
    idx, enlarge = choose(lod, rng)
    end_ok = None
    if lod.get("end_frac") is not None:  # end cards only on the crown sides (most horizontal crown normal); deterministic, no rng
        cn_s, _ = crown_normal_depth(I_pos[idx].astype(np.float64))
        side = np.abs(cn_s[:, 2])
        end_ok = set(idx[np.argsort(side, kind="stable")[: int(round(lod["end_frac"] * len(idx)))]].tolist())
    V, N, UV, COL, Fc = [], [], [], [], []
    corners_out, uv_out = [], []
    for i in idx:
        q = Quaternion(I_rot[i])
        Rq = q.to_matrix()
        sc = float(I_scl[i])
        pos = Vector(I_pos[i])
        k = int(I_proto[i])
        for view in lod["views"]:
            if view == "end" and end_ok is not None and i not in end_ok:
                continue
            fr = frames[(k, view)]
            h = fr["s"] * 0.5 * enlarge
            # LOD1/2 enlarge each card about its centre (area-preserving for the dropped sprays); the corners are pulled
            # slightly inward along the crown normal below so the outline does not inflate
            loc = [fr["C"] + fr["R"] * (sx * h) + fr["U"] * (sy * h) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            w = [pos + Rq @ (c * sc) for c in loc]
            u0, v0, u1, v1 = tile_rect(k, view)
            base = len(V)
            V.extend(tuple(x) for x in w)
            UV.extend(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
            Fc.append((base, base + 1, base + 2, base + 3))
            face_n = (Rq @ (-fr["F"])).normalized()
            N.extend([tuple(face_n)] * 4)
            tint = float(np.clip(0.5 + I_tint[i] * 1.2, 0.0, 1.0))
            COL.extend([(tint, 1.0, 0.0, 1.0)] * 4)
            corners_out.append([tuple(x) for x in w])
            uv_out.append((u0, v0, u1, v1))
    V = np.array(V, np.float64)
    if enlarge > 1.0:
        cn, _ = crown_normal_depth(V)
        V -= cn * (0.12 * (enlarge - 1.0))
    cn, depth = crown_normal_depth(V)
    Nf = np.array(N)
    Nb = (1 - lod["crown_w"]) * Nf + lod["crown_w"] * cn
    Nb /= np.linalg.norm(Nb, axis=1, keepdims=True)
    occl = np.clip(1.0 - np.maximum(depth, 0.0) / 2.6, 0.35, 1.0)
    COL = np.array(COL)
    COL[:, 1] = occl
    return V, Nb, np.array(UV), COL, Fc, dict(cards=len(Fc), sprays=len(idx), enlarge=enlarge,
                                               corners=np.array(corners_out, np.float32), uvrect=np.array(uv_out, np.float32))


def build_branches(lod):
    v, f, uv, a_rad, _lvl = tg_tree.mesh_branches(sk, min_radius=lod["min_r"], flare=mt.flare, sides_fn=lod["sides"], sub_fn=lod["sub"])
    me = tg_tree.to_bpy_mesh("tmp_br_" + lod["name"], v, f, uv)
    me.update()
    vn = np.empty(len(me.vertices) * 3, np.float32)
    me.vertex_normals.foreach_get("vector", vn)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    bpy.data.meshes.remove(me)
    young = np.clip((0.03 - a_rad) / (0.03 - 0.009), 0.0, 1.0)
    col = np.column_stack([young, np.ones_like(young), np.zeros_like(young), np.ones_like(young)])
    return np.array(v, np.float64), vn.reshape(-1, 3), np.array(uv), col, f, tris


def make_lod_object(lod, frames, rng, m_bark, m_leaf):
    bv, bn, buv, bcol, bf, btris = build_branches(lod)
    cv, cn, cuv, ccol, cf, cinfo = build_cards(lod, frames, rng)
    off = len(bv)
    verts = np.vstack([bv, cv])
    faces = list(bf) + [tuple(i + off for i in fc) for fc in cf]
    me = bpy.data.meshes.new("Machilus_" + lod["name"])
    me.from_pydata([tuple(x) for x in verts], [], faces)
    me.materials.append(m_bark)
    me.materials.append(m_leaf)
    mi = np.array([0] * len(bf) + [1] * len(cf), np.int32)
    me.polygons.foreach_set("material_index", mi)
    me.polygons.foreach_set("use_smooth", np.ones(len(faces), bool))
    vi = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", vi)
    uvs = np.vstack([buv, cuv]).astype(np.float32)
    me.uv_layers.new(name="UVMap").data.foreach_set("uv", uvs[vi].ravel())
    ca = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    ca.data.foreach_set("color", np.vstack([bcol, ccol]).astype(np.float32).ravel())
    me.color_attributes.active_color = ca
    me.update()
    normals = np.vstack([bn, cn]).astype(np.float32)
    me.normals_split_custom_set_from_vertices([tuple(n) for n in normals])
    ob = bpy.data.objects.new("Machilus_" + lod["name"], me)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    info = dict(name=lod["name"], branch_tris=btris, card_tris=cinfo["cards"] * 2, cards=cinfo["cards"],
                sprays=cinfo["sprays"], card_enlarge=round(cinfo["enlarge"], 3), total_tris=tris, verts=len(me.vertices))
    np.savez_compressed(os.path.join(OUT, fname("cards", lod["name"], ".npz")), corners=cinfo["corners"], uvrect=cinfo["uvrect"])
    return ob, info


def export_glb(ob, path):
    sc = bpy.context.scene
    sc.collection.objects.link(ob)
    for o in sc.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_normals=True, export_texcoords=True,
              export_materials="EXPORT", export_yup=True)
    try:
        for extra in (dict(export_vertex_color="ACTIVE"), dict(export_colors=True), {}):
            try:
                bpy.ops.export_scene.gltf(**kw, **extra)
                return extra
            except TypeError:
                continue
        raise RuntimeError("glTF export failed: " + path)
    finally:
        sc.collection.objects.unlink(ob)


def main():
    t = time.time()
    if REUSE_BAKE:
        fj = json.load(open(os.path.join(OUT, "bake", "frames.json")))
        frames = {(int(k.split("_")[0]), k.split("_")[1]): dict(C=Vector(v["C"]), F=Vector(v["F"]), U=Vector(v["U"]), R=Vector(v["R"]), s=v["s"])
                  for k, v in fj.items()}
        report["bake_s"] = "reused"
    else:
        frames = bake_atlas()
        report["bake_s"] = round(time.time() - t, 1)
        json.dump({"%d_%s" % k: dict(C=list(v["C"]), F=list(v["F"]), U=list(v["U"]), R=list(v["R"]), s=v["s"]) for k, v in frames.items()},
                  open(os.path.join(OUT, "bake", "frames.json"), "w"), indent=1)
    m_bark = bpy.data.materials.new("M_TL_Bark")
    m_leaf = bpy.data.materials.new("M_TL_LeafCards")
    rng = np.random.default_rng(20261015)
    report["lods"] = []
    for lod in LODS:
        ob, info = make_lod_object(lod, frames, rng, m_bark, m_leaf)
        glb = os.path.join(OUT, "glb", fname("machilus", lod["name"], ".glb"))
        info["glb_option"] = str(export_glb(ob, glb))
        info["glb_bytes"] = os.path.getsize(glb)
        report["lods"].append(info)
        print("LOD", json.dumps(info))
    report["elapsed_s"] = round(time.time() - report.pop("t0"), 1)
    json.dump(report, open(os.path.join(OUT, "game_report.json" if PROFILE == "v1" else "game_report_%s.json" % PROFILE), "w"), indent=1)
    print("GAME_EXPORT_OK")


main()
