"""柳杉 Cryptomeria japonica - golden-reference tree (Blender 5.2, Cycles). Third species after 紅楠 and 相思樹.

blender -b --factory-startup --python tools/treegen/cryptomeria_japonica.py -- <out_dir> [--views front,oblique,top,close]
        [--res 1920x1080] [--samples 96] [--no-render] [--tag v1]

Form target: a mature PLANTATION 柳杉 of the Yangmingshan 頂山-石梯嶺 stands (docs/treegen/cryptomeria-japonica.md) as a representative
game mother tree - tall straight single trunk (~24 m), clear lower bole with a few dead stubs, a NARROW conical crown on the upper
~60 % that tapers to an acute but slightly irregular top; near-horizontal primary branches in a loose spiral whose tips turn up,
clothed in clumped, rope-like ("cord") foliage tufts; dark blue-green, reddish-brown stringy bark.
Not a Christmas tree (no regular tiers, no flat fir sprays) and not a pine (no long needle bundles, no flat-topped mature crown).

The skeleton is explicit (no space colonisation: a conifer is one leader + spiral laterals). It reuses tg_tree (pipe radii, tube
mesher), tg_scene, the GN spray instancer and tg_materials; `build()` also returns crown "lobes" (spheres stacked along the cone) so
the game exporter's crown normals / occlusion work unchanged.
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
import tg_needle  # noqa: E402
import tg_scene  # noqa: E402
import tg_tree  # noqa: E402

_tg_params = os.environ.pop("ACW_TG_PARAMS", None)  # the 紅楠 module applies ACW_TG_PARAMS to its own P on import: hide it
from machilus_thunbergii import args, instancer  # noqa: E402
if _tg_params is not None:
    os.environ["ACW_TG_PARAMS"] = _tg_params

SPECIES = "CryptomeriaJaponica"
P = dict(
    seed=20261017,
    height=24.0,
    crown_base=9.5,  # m: plantation tree, lower bole self-pruned
    crown_r=3.3,  # m: max primary reach at the crown base (crown width ~6.6 m = 0.27 x height: narrow)
    crown_power=0.9,  # reach ~ (1 - rel)^p: near-straight cone sides
    branch_step=(0.18, 0.32),  # m between primaries along the trunk (loose spiral, no regular whorls)
    elev_low=(-12.0, 2.0), elev_top=(30.0, 50.0),  # deg: lower branches horizontal / slightly drooping, upper ascending
    droop=14.0, upturn=30.0,  # deg along each primary: sag in the middle, tip turns up
    sec_step=(0.11, 0.18), sec_len=(0.35, 0.85), sec_angle=(45, 70),
    stubs=7,  # dead branch stubs on the bole
    r_root=0.36, r_tip=0.005, pipe_exp=2.3,
    spray_step=0.045,  # m between sprays along secondaries
    spray_scale=(1.15, 1.6),
    shell_depth=0.9,
    # v2 crown-mass knobs (PR #40 review 5557826475); the defaults reproduce v1 exactly (no extra rng draws when off)
    inner_step=0.0,  # m between pads on the inner half of every primary (0 = off)
    hang_frac=0.0,  # share of secondary pads that hang down-outward
    low_scale=1.0,  # pad size multiplier at the crown base (-> 1 at the top)
    clump_amp=0.0,  # amplitude of the along-branch bundling wave
    inner_start=0.3,  # m off the stem where the inner pads start
    leader_len=1.4,  # m of terminal tuft column below the top (9 pads per 1.4 m)
)
if os.environ.get("ACW_TG_PARAMS"):  # same opt-in override contract as the 紅楠 / 相思樹 generators
    with open(os.environ["ACW_TG_PARAMS"], encoding="utf-8-sig") as _fh:  # tolerate a BOM (files saved by PowerShell)
        for _k, _v in json.load(_fh).items():
            if _k.startswith("_"):
                continue
            if _k not in P:
                raise KeyError("ACW_TG_PARAMS: unknown parameter %s" % _k)
            P[_k] = tuple(_v) if isinstance(_v, list) else _v
SPRAY_KINDS = tg_needle.SPRAY_KINDS


def _polyline(sk, attach, pts, can_grow=False):
    return tg_tree.add_polyline(sk, attach, pts, can_grow=can_grow)


def crown_reach(z):
    rel = (z - P["crown_base"]) / (P["height"] - P["crown_base"])
    return P["crown_r"] * max(0.0, 1.0 - rel) ** P["crown_power"]


def build_skeleton(rng):
    sk = tg_tree.Skeleton()
    root = sk.add((0, 0, 0), -1, can_grow=False)
    H = P["height"]
    trunk, z, idx = [], 0.0, root
    while z < H - 0.05:
        z = min(H, z + 0.4)
        idx = sk.add((0.12 * math.sin(z / 6.5) + 0.03 * math.sin(z * 1.3), 0.08 * math.sin(z / 4.7 + 1.0), z), idx, can_grow=False)
        trunk.append(idx)
    prims, secs = [], []
    az = rng.uniform(0, 2 * math.pi)
    # dead stubs on the clear bole
    for _ in range(P["stubs"]):
        zz = rng.uniform(3.5, P["crown_base"] - 0.3)
        a = rng.uniform(0, 2 * math.pi)
        att = trunk[min(len(trunk) - 1, int(zz / 0.4))]
        L = rng.uniform(0.25, 0.8)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.25, 0.05))).normalized()
        _polyline(sk, att, [sk.pos[att] + d * (L * t) for t in (0.5, 1.0)])
    zz = P["crown_base"]
    while zz < H - 0.5:
        zz += rng.uniform(*P["branch_step"])
        az += math.radians(137.5) + rng.normal(0, 0.35)
        rel = (zz - P["crown_base"]) / (H - P["crown_base"])
        L = (crown_reach(zz) + 0.25) * rng.uniform(0.75, 1.12)
        if L < 0.3:
            continue
        att = trunk[min(len(trunk) - 1, int(zz / 0.4))]
        e0 = math.radians(np.interp(rel, [0, 1], [rng.uniform(*P["elev_low"]), rng.uniform(*P["elev_top"])]))
        hd = Vector((math.cos(az), math.sin(az), 0.0))
        n = max(3, int(L / 0.28))
        pts, p = [], sk.pos[att].copy()
        for k in range(n):
            t = (k + 1) / n
            e = e0 - math.radians(P["droop"]) * math.sin(math.pi * t) * (1 - rel) + math.radians(P["upturn"]) * t * t
            d = (hd * math.cos(e) + Vector((0, 0, math.sin(e))) + Vector(rng.normal(0, 0.04, 3))).normalized()
            p = p + d * (L / n)
            pts.append(p.copy())
        end = _polyline(sk, att, pts)
        nodes = list(range(end - n + 1, end + 1))
        prims.append((nodes, rel, L))
        # alternate secondaries in the branch's (tilted) horizontal plane, a little drooping, tips up
        s = rng.uniform(0.15, 0.3)
        sgn = 1 if rng.uniform() < 0.5 else -1
        while s < L * 0.92:
            k = min(n - 1, int(s / L * n))
            base = sk.pos[nodes[k]]
            bd = (sk.pos[nodes[min(k + 1, n - 1)]] - sk.pos[nodes[max(k - 1, 0)]]).normalized()
            side = bd.cross(Vector((0, 0, 1)))
            side = side.normalized() if side.length > 1e-4 else Vector((1, 0, 0))
            sgn = -sgn
            a = math.radians(rng.uniform(*P["sec_angle"]))
            sd = (bd * math.cos(a) + side * sgn * math.sin(a) + Vector((0, 0, rng.uniform(-0.15, 0.2)))).normalized()
            sl = rng.uniform(*P["sec_len"]) * (1.05 - 0.55 * s / L) * (0.6 + 0.4 * min(1.0, L / 2.0))
            m = max(2, int(sl / 0.15))
            sp = [base + sd * (sl * (j + 1) / m) + Vector((0, 0, 0.12 * sl * ((j + 1) / m) ** 2)) for j in range(m)]
            e2 = _polyline(sk, nodes[k], sp)
            secs.append(list(range(e2 - m + 1, e2 + 1)))
            s += rng.uniform(*P["sec_step"])
    return sk, prims, secs


def build():
    rng = np.random.default_rng(P["seed"])
    t0 = time.time()
    sk, prims, secs = build_skeleton(rng)
    tg_tree.pipe_radii(sk, P["r_tip"], P["pipe_exp"], P["r_root"])
    # crown "lobes" for the game exporter: spheres stacked along the cone (normals ~ radial, depth ~ distance below the cone surface)
    lobes = []
    z = P["crown_base"] + 0.6
    while z < P["height"] - 0.3:
        r = crown_reach(z) + 0.45
        lobes.append(tg_tree.Lobe(c=np.array([0.0, 0.0, z]), r=r, zf=0.9))
        z += max(0.5, 0.6 * r)
    stats = dict(nodes=len(sk.pos), primaries=len(prims), secondaries=len(secs), lobes=len(lobes),
                 trunk_radius_base_m=float(sk.radius[0]), build_skeleton_s=round(time.time() - t0, 1))
    print("SKELETON", stats)
    build.prims, build.secs = prims, secs
    return sk, lobes, stats, rng


def flare(z, ang, phase=0.4):
    """Plantation 柳杉: modest root swell with shallow flutes (fibrous bark ridges)."""
    if z > 1.2:
        return 1.0 + 0.015 * math.cos(9 * ang + phase)
    k = math.exp(-z / 0.35)
    return 1.0 + 0.35 * k * (1 + 0.2 * math.cos(6 * ang + phase)) + 0.015 * math.cos(9 * ang + phase)


def make_sprays(rng, mats):
    coll = bpy.data.collections.new("TG_SprayPrototypes")
    coll.use_fake_user = True
    protos = []
    for k, kind in enumerate(SPRAY_KINDS):
        mb = tg_needle.build_spray(rng, kind)
        me = mb.to_mesh(f"P{k}_spray", [mats["leaf"], mats["twig"]])
        ob = bpy.data.objects.new(f"P{k}_spray", me)
        coll.objects.link(ob)
        protos.append(dict(name=ob.name, tris=mb.tris(), needles=mb.n_needles))
    return coll, protos


def spray_points(sk, rng, secs, prims):
    up = Vector((0, 0, 1))
    out = ([], [], [], [], [])

    span = P["height"] - P["crown_base"]

    def emit(p, d, scale=1.0, hang=False):
        rad = Vector((p.x, p.y, 0.0))
        rad = rad.normalized() if rad.length > 1e-4 else Vector((1, 0, 0))
        # v2: hanging pads drape down-outward and fill the gap below their branch (breaks the "ladder" of horizontal tiers)
        z = (d * 0.4 + rad * 0.55 - up * 0.75).normalized() if hang else (d * 0.6 + rad * 0.4 + up * 0.25).normalized()
        if P["low_scale"] != 1.0:  # v2: bigger pads in the mid-lower crown, tapering to v1 size at the top
            scale *= 1.0 + (P["low_scale"] - 1.0) * max(0.0, 1.0 - (p.z - P["crown_base"]) / span)
        y = up - z * up.dot(z)
        y = y.normalized() if y.length > 1e-4 else z.orthogonal().normalized()
        m = Matrix((y.cross(z), y, z)).transposed()
        q = (Matrix.Rotation(rng.uniform(-0.7, 0.7), 3, z) @ m).to_quaternion()
        out[0].append(tuple(p))
        out[1].append((q.w, q.x, q.y, q.z))
        out[2].append(rng.uniform(*P["spray_scale"]) * scale)
        out[3].append(int(rng.integers(0, len(SPRAY_KINDS))))
        # per-spray tone: a little bronze / lighter on the sunny upper crown, darker low inside
        out[4].append(float(0.15 * (p.z - 16.0) / 8.0 + rng.normal(0, 0.1)))

    amp = P["clump_amp"]

    def clump(s, phase):
        """v2: foliage bundles along a branch - density / size follow a ~0.9 m wave instead of an even fur (1.0 when off)."""
        return 1.0 + amp * math.sin(2 * math.pi * s / 0.9 + phase) if amp else 1.0

    for nodes in secs:
        pts = [sk.pos[i] for i in nodes]
        L = sum((pts[k + 1] - pts[k]).length for k in range(len(pts) - 1))
        d_end = (pts[-1] - pts[-2]).normalized()
        emit(pts[-1], d_end, 1.1)  # tip tuft
        emit(pts[-1], (d_end + Vector(rng.normal(0, 0.5, 3))).normalized(), 0.9)
        if P["hang_frac"]:
            emit(pts[-1], d_end, 1.0, hang=True)
        ph = rng.uniform(0, 2 * math.pi) if amp else 0.0
        s = P["spray_step"] * rng.uniform(0.5, 1.0)
        sgn = 1
        while s < L - 0.05:
            f = s / L
            k = min(len(pts) - 2, int(f * (len(pts) - 1)))
            p = pts[k].lerp(pts[k + 1], f * (len(pts) - 1) - k)
            bd = (pts[k + 1] - pts[k]).normalized()
            side = bd.cross(up)
            side = side.normalized() if side.length > 1e-4 else bd.orthogonal()
            sgn = -sgn
            c = clump(s, ph)
            if not amp or rng.uniform() < min(1.0, c):
                hang = bool(P["hang_frac"]) and rng.uniform() < P["hang_frac"]
                emit(p, (bd + side * sgn * 0.8 + up * 0.2).normalized(), rng.uniform(0.75, 1.0) * max(0.6, c), hang=hang)
            s += P["spray_step"] * rng.uniform(0.8, 1.2)
    for nodes, rel, L in prims:  # leading tuft at every primary tip and along its outer half
        pts = [sk.pos[i] for i in nodes]
        emit(pts[-1], (pts[-1] - pts[-2]).normalized(), 1.2)
        for k in range(len(pts) // 2, len(pts) - 1):
            emit(pts[k], ((pts[k + 1] - pts[k]).normalized() + up * 0.3).normalized(), 1.0)
        if P["inner_step"]:  # v2: pads along the inner half too (from 0.3 m off the stem) -> the trunk is no longer exposed
            Lp = sum((pts[j + 1] - pts[j]).length for j in range(len(pts) - 1))
            s = P["inner_start"]
            while s < 0.55 * Lp:
                f = s / Lp
                k = min(len(pts) - 2, int(f * (len(pts) - 1)))
                p = pts[k].lerp(pts[k + 1], f * (len(pts) - 1) - k)
                bd = (pts[k + 1] - pts[k]).normalized()
                emit(p, (bd + Vector(rng.normal(0, 0.5, 3))).normalized(), rng.uniform(0.9, 1.2), hang=rng.uniform() < P["hang_frac"])
                s += P["inner_step"] * rng.uniform(0.8, 1.2)
    # leader: a dense terminal tuft column on the top metre(s) (v2: longer, covers the stem in the upper crown / top-view void)
    for t in np.linspace(P["height"] - P["leader_len"], P["height"] - 0.05, max(9, int(round(9 * P["leader_len"] / 1.4)))):
        emit(Vector((0.12 * math.sin(t / 6.5) + 0.03 * math.sin(t * 1.3), 0.08 * math.sin(t / 4.7 + 1.0), t)),
             Vector((rng.normal(0, 0.4), rng.normal(0, 0.4), 1.0)).normalized(), 0.9)
    return out


def make_materials():
    return dict(
        # reddish-brown, stringy bark in long vertical strips (fissure bands of tg_materials.fissured_bark, 柳杉 palette)
        bark=tg_materials.fissured_bark("M_Bark_Cryptomeria", base=(0.10, 0.048, 0.028), dark=(0.03, 0.015, 0.01),
                                        pale=(0.15, 0.10, 0.075), twig=(0.07, 0.042, 0.022), twig_radius=(0.004, 0.015)),
        twig=tg_materials.simple("M_Twig", (0.03, 0.045, 0.022), 0.6),
        # needles: dark blue-green, matte-satin, some bronze-tinged tips; isobilateral like the phyllode shader (veins unused: UV v 0.2-0.4)
        leaf=tg_materials.phyllode("M_Needle", upper=(0.012, 0.032, 0.02), upper_var=(0.03, 0.055, 0.026), young=(0.06, 0.08, 0.025),
                                   vein=(0.012, 0.032, 0.02), trans=(0.08, 0.13, 0.05), rough=0.6, trans_w=0.22),
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
    pts = spray_points(sk, rng, build.secs, build.prims)
    instancer(SPECIES + "_sprays", coll, *pts)
    proto_idx = np.array(pts[3])
    stats.update(sprays=len(pts[0]), proto_tris=[p["tris"] for p in protos], proto_needles=[p["needles"] for p in protos],
                 instanced_spray_tris=int(sum(protos[k]["tris"] for k in proto_idx)), needles=int(sum(protos[k]["needles"] for k in proto_idx)))
    stats["total_tris"] = stats["instanced_spray_tris"] + stats["branch_tris"]
    allp = np.array([tuple(p) for p in sk.pos])
    height = float(allp[:, 2].max() + 0.3)
    spread = float(max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1])) + 0.8)
    stats.update(height_m=round(height, 2), spread_m=round(spread, 2))
    print("STATS", json.dumps(stats))
    # close-up: a front branch end at ~45 % of the crown height
    tips = np.array(pts[0])
    zt = P["crown_base"] + 0.45 * (P["height"] - P["crown_base"])
    score = -tips[:, 1] - 2.0 * np.abs(tips[:, 2] - zt) - 1.0 * np.abs(tips[:, 0])
    tgt = Vector(tips[int(np.argmax(score))])
    cams = tg_scene.make_cameras(scene, height, spread, close_target=tgt, close_from=tgt + Vector((0.8, -2.2, 0.4)))
    with open(os.path.join(out_dir, f"{opts['tag']}_stats.json"), "w") as fh:
        json.dump(dict(params=P, stats=stats), fh, indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, f"{opts['tag']}_cryptomeria_japonica.blend"))
    if opts["render"]:
        t1 = time.time()
        tg_scene.render_views(scene, cams, out_dir, opts["tag"], views=opts["views"])
        print("RENDER_S", round(time.time() - t1, 1))


if __name__ == "__main__":
    main()
