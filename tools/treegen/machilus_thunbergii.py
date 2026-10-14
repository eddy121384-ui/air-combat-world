"""紅楠 / 豬腳楠 Machilus thunbergii - golden-reference tree (Blender 5.2, Cycles).

blender -b --factory-startup --python tools/treegen/machilus_thunbergii.py -- <out_dir> [--views front,oblique,top,close]
        [--res 1920x1080] [--samples 96] [--no-render]

Form targets (open-grown mature tree; see docs/treegen/machilus-thunbergii.md for the references):
- 12-15 m tall, broad dome crown about as wide as tall, made of distinct billowy foliage clumps with dark gaps;
- short stout trunk (DBH ~0.55 m), buttressed base, forking low (2.5-3 m) into 3-5 ascending scaffold limbs;
- light grey-brown, fairly smooth bark with conspicuous lenticels;
- leaves leathery, glossy dark green above, paler beneath, obovate-elliptic 7-11 cm, crowded at the shoot tips
  around a large red-scaled terminal bud; a minority of shoots carry a red-bronze young flush.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import tg_leaf  # noqa: E402
import tg_materials  # noqa: E402
import tg_scene  # noqa: E402
import tg_tree  # noqa: E402

P = dict(
    seed=20261014,
    height_fork=2.7,
    trunk_lean=(0.18, 0.06),
    n_limbs=5,
    limb_len=(3.2, 4.8),
    limb_elev=(36, 60),  # degrees above horizontal
    leader=True,
    shell_c=(0.0, 0.0, 7.1),
    shell_r=(6.4, 6.1, 5.2),
    n_lobes=22,
    lobe_r=(1.9, 2.8),
    lobe_zf=0.9,
    lobe_elev=(-48, 86),
    lobe_frac=(0.7, 0.93),
    core_frac=0.82,
    # overall crown outline: broad dome, widest in the lower third, rounded top (12-15 m tall open-grown tree)
    dome=dict(c=(0.0, 0.0, 4.8), r_xy=(7.6, 7.3), rz_up=9.4, rz_dn=2.9, q_up=1.35,
              asym=dict(r1=0.1, a1=2.4, r2=0.07, a2=0.6, z1=0.1, az=2.0)),
    limb_stagger_nodes=3,
    attr_n=52000,
    attr_zmin=2.3,
    surface_bias=0.55,
    keep_floor=0.08,
    seg=0.2,
    influence=1.7,
    kill=0.32,
    tropism=(0.0, 0.0, 0.1),
    r_tip=0.006,
    pipe_exp=2.35,
    r_root=0.3,
    spray_back_prob=0.85,
    sprays_back=3,
    shell_depth=1.1,  # m below the lobe surface counted as the sun-leaf shell
    interior_keep=0.45,
    spray_scale=(0.85, 1.2),
)


def args():
    a = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = a[0] if a else os.path.join(os.getcwd(), "out", "treegen", "machilus")
    opts = dict(views=["front", "oblique", "top", "close"], res=(1920, 1080), samples=96, render=True, tag="iter")
    i = 1
    while i < len(a):
        if a[i] == "--views":
            opts["views"] = a[i + 1].split(",")
            i += 1
        elif a[i] == "--res":
            w, h = a[i + 1].split("x")
            opts["res"] = (int(w), int(h))
            i += 1
        elif a[i] == "--samples":
            opts["samples"] = int(a[i + 1])
            i += 1
        elif a[i] == "--tag":
            opts["tag"] = a[i + 1]
            i += 1
        elif a[i] == "--no-render":
            opts["render"] = False
        i += 1
    return out, opts


def build_skeleton(rng):
    sk = tg_tree.Skeleton()
    root = sk.add((0, 0, 0), -1, can_grow=False)
    # trunk: slight lean and sinuosity
    lx, ly = P["trunk_lean"]
    n = 7
    pts = []
    for k in range(1, n + 1):
        t = k / n
        z = P["height_fork"] * t
        pts.append((lx * t * t + 0.04 * math.sin(3 * t), ly * t + 0.03 * math.cos(4 * t), z))
    fork = tg_tree.add_polyline(sk, root, pts, can_grow=False)
    sk.can_grow[fork] = True
    fork_p = sk.pos[fork]
    trunk_nodes = list(range(root + 1, fork + 1))
    # scaffold limbs, origins staggered over the upper trunk (no single candelabra point)
    az0 = rng.uniform(0, 2 * math.pi)
    limbs = []
    for j in range(P["n_limbs"]):
        az = az0 + j * 2 * math.pi / P["n_limbs"] + rng.uniform(-0.35, 0.35)
        el = math.radians(rng.uniform(*P["limb_elev"]))
        L = rng.uniform(*P["limb_len"])
        attach = trunk_nodes[-1 - int(rng.integers(0, P["limb_stagger_nodes"] + 1))]
        if sk.pos[attach].z < P["height_fork"] - 0.8:
            attach = fork
        sk.can_grow[attach] = True
        d0 = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
        steps = int(L / 0.3)
        lp = []
        p = sk.pos[attach].copy()
        d = d0.copy()
        wob = Vector(rng.normal(0, 1, 3)).normalized()
        for k in range(steps):
            # ascending S-curve: starts steep, then turns outward, tip turns up again; lateral wander
            t = k / steps
            bend = Vector((d0.x, d0.y, 0)).normalized() * (0.06 if t < 0.5 else -0.03)
            wander = wob * 0.06 * math.sin(2.2 * math.pi * t + j)
            d = (d + bend + wander + Vector(rng.normal(0, 0.05, 3))).normalized()
            p = p + d * 0.3
            lp.append(tuple(p))
        limbs.append(tg_tree.add_polyline(sk, attach, lp))
    if P["leader"]:
        lp = []
        p = fork_p.copy()
        d = Vector((0.05, -0.04, 1)).normalized()
        for k in range(9):
            d = (d + Vector(rng.normal(0, 0.05, 3))).normalized()
            p = p + d * 0.35
            lp.append(tuple(p))
        tg_tree.add_polyline(sk, fork, lp)
    return sk


def build():
    rng = np.random.default_rng(P["seed"])
    t0 = time.time()
    lobes = tg_tree.make_lobes(
        rng, P["n_lobes"], np.array(P["shell_c"]), np.array(P["shell_r"]), P["lobe_elev"], P["lobe_frac"], P["lobe_r"], P["lobe_zf"]
    )
    lobes.append(tg_tree.core_lobe(P["shell_c"], P["shell_r"], P["core_frac"]))
    env = P["dome"]
    attractors = tg_tree.sample_attractors(
        rng, lobes, P["attr_n"], P["attr_zmin"], P["surface_bias"], P["keep_floor"],
        envelope=lambda p: tg_tree.dome_envelope(p, env["c"], env["r_xy"], env["rz_up"], env["rz_dn"], env.get("asym"), env.get("q_up", 2.0)),
    )
    sk = build_skeleton(rng)
    iters = tg_tree.space_colonize(sk, attractors, P["seg"], P["influence"], P["kill"], Vector(P["tropism"]), rng)
    tg_tree.smooth(sk, iters=3, w=0.5, fixed_below=P["height_fork"])
    tg_tree.pipe_radii(sk, P["r_tip"], P["pipe_exp"], P["r_root"])
    stats = dict(sc_iterations=iters, nodes=len(sk.pos), attractors=len(attractors), lobes=len(lobes))
    stats["trunk_radius_base_m"] = float(sk.radius[0])
    stats["build_skeleton_s"] = round(time.time() - t0, 1)
    print("SKELETON", stats)
    return sk, lobes, stats, rng


def flare(z, ang, phase=0.7):
    if z > 1.4:
        return 1.0
    k = math.exp(-z / 0.32)
    buttress = 1 + 0.32 * max(0.0, math.cos(5 * ang + phase)) ** 2 + 0.12 * math.cos(3 * ang + 1.9)
    return 1.0 + 0.6 * k * buttress + 0.06 * (1.4 - z) / 1.4


def make_sprays(rng, mats):
    shape = tg_leaf.LeafShape()
    coll = bpy.data.collections.new("TG_SprayPrototypes")
    coll.use_fake_user = True
    protos = []
    for k, kind in enumerate(tg_leaf.SPRAY_KINDS):
        mb = tg_leaf.build_spray(rng, shape, kind)
        me = mb.to_mesh(f"P{k}_spray", [mats["leaf"], mats["twig"], mats["bud"]])
        ob = bpy.data.objects.new(f"P{k}_spray", me)
        coll.objects.link(ob)
        leaves = sum(1 for mi in mb.mat if mi == 0) // 2  # approx, refined below
        protos.append(dict(name=ob.name, tris=mb.tris(), leaf_faces=sum(1 for mi in mb.mat if mi == 0)))
    return coll, protos


def spray_points(sk, rng, crown_c, lobes):
    tips = tg_tree.tips(sk)
    up = Vector((0, 0, 1))
    P_pos, P_rot, P_scl, P_proto, P_tint = [], [], [], [], []

    def emit(i, d):
        p = sk.pos[i]
        outward = (p - Vector(crown_c))
        outward.z *= 0.5
        outward = outward.normalized() if outward.length > 1e-6 else Vector((1, 0, 0))
        z = (d + up * 0.35 + outward * 0.35).normalized()
        y = (up - z * up.dot(z))
        y = y.normalized() if y.length > 1e-4 else z.orthogonal().normalized()
        x = y.cross(z)
        m = Matrix((x, y, z)).transposed()
        roll = Matrix.Rotation(rng.uniform(-0.45, 0.45), 3, z)
        q = (roll @ m).to_quaternion()
        P_pos.append(tuple(p))
        P_rot.append((q.w, q.x, q.y, q.z))
        P_scl.append(rng.uniform(*P["spray_scale"]))
        P_proto.append(int(rng.integers(0, len(tg_leaf.SPRAY_KINDS))))
        # per-spray hue drift: slowly varying over the crown (sectors) + noise
        P_tint.append(float(0.18 * math.sin(p.x * 0.6 + 1.3) * math.cos(p.y * 0.5) + rng.normal(0, 0.08)))

    # sun-leaf shell: tips near a lobe surface carry more foliage than tips deep inside the crown
    tip_p = np.array([tuple(sk.pos[i]) for i in tips])
    depth = tg_tree.lobe_depth(tip_p, lobes)
    for i, dep in zip(tips, depth):
        par = sk.parent[i]
        d = (sk.pos[i] - sk.pos[par]).normalized()
        shell = dep < P["shell_depth"]
        if not shell and rng.uniform() > P["interior_keep"]:
            continue
        emit(i, d)
        if shell:
            # second spray at the same tip, rolled (dense terminal clusters)
            emit(i, (d + Vector(rng.normal(0, 0.35, 3))).normalized())
        # extra lateral sprays further back on the same twig (alternating sides)
        j = i
        sgn = 1 if rng.uniform() < 0.5 else -1
        for _ in range(P["sprays_back"] if shell else 1):
            for _ in range(int(rng.integers(2, 4))):
                if sk.parent[j] < 0:
                    break
                j = sk.parent[j]
            if sk.parent[j] < 0 or sk.radius[j] > 0.025 or rng.uniform() > P["spray_back_prob"]:
                continue
            dd = (sk.pos[i] - sk.pos[j]).normalized()
            side = dd.cross(up)
            side = side.normalized() if side.length > 1e-4 else dd.orthogonal().normalized()
            sgn = -sgn
            emit(j, (dd + side * sgn * 0.9).normalized())
    return P_pos, P_rot, P_scl, P_proto, P_tint


def instancer(name, coll, pos, rot, scl, proto, tint):
    me = bpy.data.meshes.new(name + "_pts")
    me.from_pydata(pos, [], [])
    a = me.attributes.new("rot", "QUATERNION", "POINT")
    a.data.foreach_set("value", np.asarray(rot, dtype=np.float32).ravel())
    a = me.attributes.new("scl", "FLOAT", "POINT")
    a.data.foreach_set("value", np.asarray(scl, dtype=np.float32))
    a = me.attributes.new("proto", "INT", "POINT")
    a.data.foreach_set("value", np.asarray(proto, dtype=np.int32))
    a = me.attributes.new("tint", "FLOAT", "POINT")
    a.data.foreach_set("value", np.asarray(tint, dtype=np.float32))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ng = bpy.data.node_groups.new("TG_SprayInstancer", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = ng.nodes, ng.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")
    ci = nodes.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    iop = nodes.new("GeometryNodeInstanceOnPoints")
    iop.inputs["Pick Instance"].default_value = True
    na_p = nodes.new("GeometryNodeInputNamedAttribute")
    na_p.data_type = "INT"
    na_p.inputs["Name"].default_value = "proto"
    na_r = nodes.new("GeometryNodeInputNamedAttribute")
    na_r.data_type = "QUATERNION"
    na_r.inputs["Name"].default_value = "rot"
    na_s = nodes.new("GeometryNodeInputNamedAttribute")
    na_s.data_type = "FLOAT"
    na_s.inputs["Name"].default_value = "scl"
    links.new(gi.outputs[0], iop.inputs["Points"])
    links.new(ci.outputs[0], iop.inputs["Instance"])
    links.new(na_p.outputs["Attribute"], iop.inputs["Instance Index"])
    links.new(na_r.outputs["Attribute"], iop.inputs["Rotation"])
    links.new(na_s.outputs["Attribute"], iop.inputs["Scale"])
    links.new(iop.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("Sprays", "NODES")
    mod.node_group = ng
    return ob


def main():
    out_dir, opts = args()
    os.makedirs(out_dir, exist_ok=True)
    scene = tg_scene.reset_scene()
    tg_scene.setup_stage(scene, samples=opts["samples"], res=opts["res"])
    sk, lobes, stats, rng = build()

    mats = dict(
        bark=tg_materials.bark(),
        twig=tg_materials.simple("M_Twig", (0.075, 0.07, 0.035), 0.6),
        bud=tg_materials.simple("M_Bud", (0.26, 0.05, 0.025), 0.45),
        leaf=tg_materials.leaf(),
    )
    v, f, uv, a_rad, a_lvl = tg_tree.mesh_branches(sk, flare=flare)
    me = tg_tree.to_bpy_mesh("MachilusThunbergii_branches", v, f, uv, dict(radius=a_rad, branch_level=a_lvl))
    me.materials.append(mats["bark"])
    br = bpy.data.objects.new("MachilusThunbergii_branches", me)
    scene.collection.objects.link(br)
    stats["branch_tris"] = sum(len(p.vertices) - 2 for p in me.polygons)

    coll, protos = make_sprays(rng, mats)
    pts = spray_points(sk, rng, P["shell_c"], lobes)
    ins = instancer("MachilusThunbergii_sprays", coll, *pts)
    n_sprays = len(pts[0])
    proto_idx = np.array(pts[3])
    leaf_tris = sum(protos[k]["leaf_faces"] * 1 for k in proto_idx)  # faces ~ quads+tris
    tris_inst = sum(protos[k]["tris"] for k in proto_idx)
    stats.update(
        sprays=n_sprays,
        tips=len(tg_tree.tips(sk)),
        proto_tris=[p["tris"] for p in protos],
        instanced_spray_tris=int(tris_inst),
        total_tris=int(tris_inst + stats["branch_tris"]),
    )
    # leaves per prototype: each blade = 2 single-point rows + 6 three-vertex rows -> 14 faces
    stats["leaves"] = int(sum(protos[k]["leaf_faces"] for k in proto_idx) / 14)
    print("STATS", json.dumps(stats))

    # bounds
    allp = np.array([tuple(p) for p in sk.pos])
    height = float(allp[:, 2].max() + 0.4)
    spread = float(max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1])) + 0.8)
    stats.update(height_m=round(height, 2), spread_m=round(spread, 2))
    # close-up target: a front-side tip at about 55 % height
    tips_i = tg_tree.tips(sk)
    tp = np.array([tuple(sk.pos[i]) for i in tips_i])
    score = -tp[:, 1] - 2.0 * np.abs(tp[:, 2] - 0.5 * height) - 1.0 * np.abs(tp[:, 0])
    tgt = Vector(tp[int(np.argmax(score))])
    cams = tg_scene.make_cameras(scene, height, spread, close_target=tgt, close_from=tgt + Vector((0.9, -2.6, 0.5)))
    with open(os.path.join(out_dir, f"{opts['tag']}_stats.json"), "w") as fh:
        json.dump(dict(params=P, stats=stats), fh, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, f"{opts['tag']}_machilus_thunbergii.blend"))
    if opts["render"]:
        t1 = time.time()
        tg_scene.render_views(scene, cams, out_dir, opts["tag"], views=opts["views"])
        print("RENDER_S", round(time.time() - t1, 1))


if __name__ == "__main__":
    main()
