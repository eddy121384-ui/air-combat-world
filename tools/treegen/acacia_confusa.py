"""相思樹 Acacia confusa - golden-reference tree (Blender 5.2, Cycles). Second Taiwan lowland species after 紅楠.

blender -b --factory-startup --python tools/treegen/acacia_confusa.py -- <out_dir> [--views front,oblique,top,close]
        [--res 1920x1080] [--samples 96] [--no-render] [--tag v1]

Form targets (mature open-to-stand-grown tree of the northern Taiwan hills; see docs/treegen/acacia-confusa.md):
- 11-13 m tall, crown about as wide as tall but IRREGULAR and flat-shouldered, built from separate, flattened foliage clouds at the
  ends of the limbs with sky and dark branches visible between them (no continuous dome, no core mass);
- trunk leaning, short, forking low (~2 m) into 2-4 long SINUOUS ascending-spreading limbs that fork again; grey-brown bark with
  shallow longitudinal fissures, thin shoots red-brown;
- foliage: slender arching twigs with narrow falcate phyllodes held near-vertical (tg_phyllode) -> fine, feathery, light-transmitting
  texture; colour a lighter yellow-olive green than the glossy dark 紅楠.
Shares the 紅楠 machinery (tg_tree space colonisation + meshing, tg_scene stage, the spray instancer); only the species parameters,
the explicit limb architecture, the phyllode sprays and the materials are new. The 紅楠 generator is untouched.
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
import tg_materials  # noqa: E402
import tg_phyllode  # noqa: E402
import tg_scene  # noqa: E402
import tg_tree  # noqa: E402
_tg_params = os.environ.pop("ACW_TG_PARAMS", None)  # the 紅楠 module applies ACW_TG_PARAMS to its own P on import: hide it
from machilus_thunbergii import args, instancer  # noqa: E402  (CLI + GN instancer are species-neutral)
if _tg_params is not None:
    os.environ["ACW_TG_PARAMS"] = _tg_params

SPECIES = "AcaciaConfusa"
P = dict(
    seed=20261016,
    height_fork=1.8,
    trunk_lean=(0.55, 0.2),
    n_limbs=3,
    limb_len=(3.4, 4.8),
    limb_elev=(36, 58),
    limb_wander=0.11,
    sub_fork=(0.45, 0.7),  # each limb forks once at this fraction of its length
    sub_elev=(20, 45),
    shell_c=(0.4, 0.1, 7.0),
    shell_r=(5.4, 5.0, 5.0),
    n_lobes=15,
    lobe_r=(1.4, 2.4),
    lobe_zf=0.55,  # flattened, flat-bottomed clouds
    lobe_elev=(-52, 85),
    lobe_frac=(0.5, 1.0),
    cap_r=2.2,
    dome=dict(c=(0.4, 0.1, 6.2), r_xy=(7.8, 7.0), rz_up=6.6, rz_dn=4.2, q_up=3.0,
              asym=dict(r1=0.22, a1=0.9, r2=0.15, a2=2.6, z1=0.2, az=1.4)),
    attr_n=60000,
    attr_zmin=2.6,
    surface_bias=0.4,
    keep_floor=0.04,
    seg=0.2,
    influence=1.5,
    kill=0.3,
    tropism=(0.0, 0.0, 0.06),
    sc_jitter=0.16,
    r_tip=0.005,
    pipe_exp=2.25,
    r_root=0.27,
    shell_depth=0.9,
    interior_keep=0.2,
    sprays_back=3,
    spray_back_prob=0.8,
    spray_scale=(1.2, 1.6),
)
if os.environ.get("ACW_TG_PARAMS"):  # same opt-in override contract as machilus_thunbergii.py
    with open(os.environ["ACW_TG_PARAMS"], encoding="utf-8") as _fh:
        for _k, _v in json.load(_fh).items():
            if _k.startswith("_"):
                continue
            if _k not in P:
                raise KeyError("ACW_TG_PARAMS: unknown parameter %s" % _k)
            P[_k] = tuple(_v) if isinstance(_v, list) else _v
SPRAY_KINDS = tg_phyllode.SPRAY_KINDS


def _sinuous(sk, attach, d0, L, rng, wander, step=0.3, phase=0.0):
    """A limb that keeps changing direction (acacia limbs zig-zag between growth flushes), returns its node list."""
    steps = max(3, int(L / step))
    p = sk.pos[attach].copy()
    d = d0.copy()
    wob = Vector(rng.normal(0, 1, 3)).normalized()
    nodes = []
    idx = attach
    for k in range(steps):
        t = k / steps
        flat = Vector((d0.x, d0.y, 0))
        flat = flat.normalized() if flat.length > 1e-6 else Vector((1, 0, 0))
        bend = flat * (0.05 if t < 0.55 else -0.02)
        zig = wob * wander * math.sin(2.6 * math.pi * t + phase) + Vector(rng.normal(0, wander * 0.6, 3))
        d = (d + bend + zig).normalized()
        if d.z < 0.15:
            d.z = 0.15
            d.normalize()
        p = p + d * step
        idx = sk.add(tuple(p), idx)
        nodes.append(idx)
    return nodes


def build_skeleton(rng):
    sk = tg_tree.Skeleton()
    root = sk.add((0, 0, 0), -1, can_grow=False)
    lx, ly = P["trunk_lean"]
    n = 7
    pts = []
    for k in range(1, n + 1):
        t = k / n
        z = P["height_fork"] * t
        pts.append((lx * t ** 1.4 + 0.06 * math.sin(4.0 * t), ly * t + 0.05 * math.sin(5.0 * t + 1.0), z))
    fork = tg_tree.add_polyline(sk, root, pts, can_grow=False)
    trunk_nodes = list(range(root + 1, fork + 1))
    lean = Vector((lx, ly, 0)).normalized()
    az_lean = math.atan2(lean.y, lean.x)
    for j in range(P["n_limbs"]):
        # limbs fan out around the lean direction (the crown overhangs the lean, as on slopes)
        az = az_lean + (j - (P["n_limbs"] - 1) / 2) * (2 * math.pi / (P["n_limbs"] + 0.6)) + rng.uniform(-0.3, 0.3)
        el = math.radians(rng.uniform(*P["limb_elev"]))
        L = rng.uniform(*P["limb_len"])
        attach = trunk_nodes[-1 - int(rng.integers(0, 3))]
        d0 = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
        nodes = _sinuous(sk, attach, d0, L, rng, P["limb_wander"], phase=j * 1.7)
        # one secondary fork per limb
        fk = nodes[int(len(nodes) * rng.uniform(*P["sub_fork"]))]
        dz = sk.pos[fk] - sk.pos[sk.parent[fk]]
        side = dz.cross(Vector((0, 0, 1)))
        side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
        sgn = 1 if rng.uniform() < 0.5 else -1
        se = math.radians(rng.uniform(*P["sub_elev"]))
        sd = (Vector((dz.x, dz.y, 0)).normalized() * math.cos(se) + Vector((0, 0, math.sin(se))) + side * sgn * 0.7).normalized()
        _sinuous(sk, fk, sd, L * rng.uniform(0.45, 0.65), rng, P["limb_wander"], phase=j * 2.3 + 1.0)
    return sk


def build():
    rng = np.random.default_rng(P["seed"])
    t0 = time.time()
    lobes = tg_tree.make_lobes(
        rng, P["n_lobes"], np.array(P["shell_c"]), np.array(P["shell_r"]), P["lobe_elev"], P["lobe_frac"], P["lobe_r"], P["lobe_zf"]
    )
    # one crown-top cloud: dart-thrown lobes can leave the apex empty, which reads as a ring / donut from above
    c = np.array(P["shell_c"]) + np.array([0.0, 0.0, P["shell_r"][2] * 0.78])
    lobes.append(tg_tree.Lobe(c=c, r=P["cap_r"], zf=P["lobe_zf"]))
    env = P["dome"]
    attractors = tg_tree.sample_attractors(
        rng, lobes, P["attr_n"], P["attr_zmin"], P["surface_bias"], P["keep_floor"],
        envelope=lambda p: tg_tree.dome_envelope(p, env["c"], env["r_xy"], env["rz_up"], env["rz_dn"], env.get("asym"), env.get("q_up", 2.0)),
    )
    sk = build_skeleton(rng)
    iters = tg_tree.space_colonize(sk, attractors, P["seg"], P["influence"], P["kill"], Vector(P["tropism"]), rng, jitter=P["sc_jitter"])
    tg_tree.smooth(sk, iters=2, w=0.45, fixed_below=P["height_fork"])
    tg_tree.pipe_radii(sk, P["r_tip"], P["pipe_exp"], P["r_root"])
    stats = dict(sc_iterations=iters, nodes=len(sk.pos), attractors=len(attractors), lobes=len(lobes))
    stats["trunk_radius_base_m"] = float(sk.radius[0])
    stats["build_skeleton_s"] = round(time.time() - t0, 1)
    print("SKELETON", stats)
    return sk, lobes, stats, rng


def flare(z, ang, phase=1.1):
    """Mild root flare, slightly fluted (no 紅楠 buttresses)."""
    if z > 0.9:
        return 1.0
    k = math.exp(-z / 0.22)
    return 1.0 + 0.32 * k * (1 + 0.15 * math.cos(4 * ang + phase))


def make_sprays(rng, mats):
    shape = tg_phyllode.PhyllodeShape()
    coll = bpy.data.collections.new("TG_SprayPrototypes")
    coll.use_fake_user = True
    protos = []
    for k, kind in enumerate(SPRAY_KINDS):
        mb = tg_phyllode.build_spray(rng, shape, kind)
        me = mb.to_mesh(f"P{k}_spray", [mats["leaf"], mats["twig"]])
        ob = bpy.data.objects.new(f"P{k}_spray", me)
        coll.objects.link(ob)
        protos.append(dict(name=ob.name, tris=mb.tris(), phyllodes=mb.n_phyllodes))
    return coll, protos


def spray_points(sk, rng, crown_c, lobes):
    tips = tg_tree.tips(sk)
    up = Vector((0, 0, 1))
    P_pos, P_rot, P_scl, P_proto, P_tint = [], [], [], [], []

    def emit(i, d):
        p = sk.pos[i]
        outward = p - Vector(crown_c)
        outward.z *= 0.35
        outward = outward.normalized() if outward.length > 1e-6 else Vector((1, 0, 0))
        # sprays reach outward and nearly horizontal from the cloud surface; the twig's own sag droops the end
        z = (d * 0.5 + outward * 0.75 + up * 0.12).normalized()
        y = up - z * up.dot(z)
        y = y.normalized() if y.length > 1e-4 else z.orthogonal().normalized()
        x = y.cross(z)
        m = Matrix((x, y, z)).transposed()
        roll = Matrix.Rotation(rng.uniform(-0.6, 0.6), 3, z)
        q = (roll @ m).to_quaternion()
        P_pos.append(tuple(p))
        P_rot.append((q.w, q.x, q.y, q.z))
        P_scl.append(rng.uniform(*P["spray_scale"]))
        P_proto.append(int(rng.integers(0, len(SPRAY_KINDS))))
        # per-spray tint: broad sector drift (one side of the crown yellower) + noise
        P_tint.append(float(0.2 * math.sin(p.x * 0.45 + 0.4) * math.cos(p.y * 0.38 + 1.1) + rng.normal(0, 0.09)))

    tip_p = np.array([tuple(sk.pos[i]) for i in tips])
    depth = tg_tree.lobe_depth(tip_p, lobes)
    for i, dep in zip(tips, depth):
        par = sk.parent[i]
        d = (sk.pos[i] - sk.pos[par]).normalized()
        if sk.pos[i].z < P["attr_zmin"] - 0.5:  # no foliage on stray low shoots below the crown base
            continue
        shell = dep < P["shell_depth"]
        if not shell and rng.uniform() > P["interior_keep"]:
            continue
        emit(i, d)
        if shell:
            emit(i, (d + Vector(rng.normal(0, 0.4, 3))).normalized())
        j = i
        sgn = 1 if rng.uniform() < 0.5 else -1
        for _ in range(P["sprays_back"] if shell else 0):
            for _ in range(int(rng.integers(2, 4))):
                if sk.parent[j] < 0:
                    break
                j = sk.parent[j]
            if sk.parent[j] < 0 or sk.radius[j] > 0.02 or rng.uniform() > P["spray_back_prob"]:
                continue
            dd = (sk.pos[i] - sk.pos[j]).normalized()
            side = dd.cross(up)
            side = side.normalized() if side.length > 1e-4 else dd.orthogonal().normalized()
            sgn = -sgn
            emit(j, (dd + side * sgn * 0.8).normalized())
    return P_pos, P_rot, P_scl, P_proto, P_tint


def make_materials():
    return dict(
        bark=tg_materials.fissured_bark(),
        twig=tg_materials.simple("M_Twig", (0.075, 0.045, 0.025), 0.6),
        leaf=tg_materials.phyllode(),
    )


def main():
    out_dir, opts = args()
    os.makedirs(out_dir, exist_ok=True)
    scene = tg_scene.reset_scene()
    tg_scene.setup_stage(scene, samples=opts["samples"], res=opts["res"])
    sk, lobes, stats, rng = build()
    mats = make_materials()
    v, f, uv, a_rad, a_lvl = tg_tree.mesh_branches(sk, flare=flare)
    me = tg_tree.to_bpy_mesh(SPECIES + "_branches", v, f, uv, dict(radius=a_rad, branch_level=a_lvl))
    me.materials.append(mats["bark"])
    br = bpy.data.objects.new(SPECIES + "_branches", me)
    scene.collection.objects.link(br)
    stats["branch_tris"] = sum(len(p.vertices) - 2 for p in me.polygons)
    coll, protos = make_sprays(rng, mats)
    pts = spray_points(sk, rng, P["shell_c"], lobes)
    instancer(SPECIES + "_sprays", coll, *pts)
    proto_idx = np.array(pts[3])
    tris_inst = sum(protos[k]["tris"] for k in proto_idx)
    stats.update(sprays=len(pts[0]), tips=len(tg_tree.tips(sk)), proto_tris=[p["tris"] for p in protos],
                 proto_phyllodes=[p["phyllodes"] for p in protos], instanced_spray_tris=int(tris_inst),
                 total_tris=int(tris_inst + stats["branch_tris"]), phyllodes=int(sum(protos[k]["phyllodes"] for k in proto_idx)))
    allp = np.array([tuple(p) for p in sk.pos])
    height = float(allp[:, 2].max() + 0.5)
    spread = float(max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1])) + 1.0)
    stats.update(height_m=round(height, 2), spread_m=round(spread, 2))
    print("STATS", json.dumps(stats))
    tips_i = tg_tree.tips(sk)
    tp = np.array([tuple(sk.pos[i]) for i in tips_i])
    score = -tp[:, 1] - 2.0 * np.abs(tp[:, 2] - 0.55 * height) - 1.0 * np.abs(tp[:, 0] - allp[:, 0].mean())
    tgt = Vector(tp[int(np.argmax(score))])
    cams = tg_scene.make_cameras(scene, height, spread, close_target=tgt, close_from=tgt + Vector((0.9, -2.4, 0.4)))
    with open(os.path.join(out_dir, f"{opts['tag']}_stats.json"), "w") as fh:
        json.dump(dict(params=P, stats=stats), fh, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, f"{opts['tag']}_acacia_confusa.blend"))
    if opts["render"]:
        t1 = time.time()
        tg_scene.render_views(scene, cams, out_dir, opts["tag"], views=opts["views"])
        print("RENDER_S", round(time.time() - t1, 1))


if __name__ == "__main__":
    main()
