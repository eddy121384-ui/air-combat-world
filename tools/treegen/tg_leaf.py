"""Leaf blades and leafy twig-spray prototypes (instanced on the skeleton tips).

Local spray frame: +Z = growth direction of the spray, +Y = the side that faces the sky.
Each prototype is one mesh with material slots 0 = leaf, 1 = twig; per-point attributes
`leaf_rand` (0..1 per leaf, colour variation), `leaf_age` (0 mature .. 1 red flush), `leaf_uv`
(blade UV: x along the blade 0 base .. 1 apex, y across 0..1, midrib at 0.5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from mathutils import Matrix, Vector

LEAF_ROWS = (0.0, 0.1, 0.25, 0.42, 0.6, 0.76, 0.9, 1.0)


@dataclass
class LeafShape:
    length: tuple = (0.075, 0.11)  # m (Taiwan: blade 4.5-13 cm; mature open-grown typical 7-11)
    aspect: tuple = (0.37, 0.46)  # width / length
    widest: float = 0.63  # obovate: widest above the middle
    apex: float = 0.7  # <1 = acute / shortly acuminate apex
    petiole: tuple = (0.015, 0.03)
    fold: float = 0.14  # V fold along the midrib (rise per unit half-width)
    droop: tuple = (0.05, 0.22)  # longitudinal curvature (tip down) as fraction of length


def half_width(t, shape):
    pw = shape.widest
    if t <= pw:
        x = t / pw
        return math.sin(0.5 * math.pi * x) ** 1.1
    x = (1 - t) / (1 - pw)
    return math.sin(0.5 * math.pi * x) ** shape.apex


class MeshBuilder:
    def __init__(self):
        self.v, self.f, self.mat, self.uv, self.rand, self.age = [], [], [], [], [], []

    def add_vert(self, p, uv=(0, 0), rand=0.0, age=0.0):
        self.v.append(tuple(p))
        self.uv.append(uv)
        self.rand.append(rand)
        self.age.append(age)
        return len(self.v) - 1

    def add_face(self, idx, mat):
        self.f.append(tuple(idx))
        self.mat.append(mat)

    def tris(self):
        return sum(len(f) - 2 for f in self.f)

    def to_mesh(self, name, materials):
        import bpy

        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        for m in materials:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", np.array(self.mat, dtype=np.int32))
        me.polygons.foreach_set("use_smooth", np.ones(len(self.f), dtype=bool))
        vi = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", vi)
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.asarray(self.uv, dtype=np.float32)[vi].ravel())
        for key, arr in (("leaf_rand", self.rand), ("leaf_age", self.age)):
            at = me.attributes.new(key, "FLOAT", "POINT")
            at.data.foreach_set("value", np.asarray(arr, dtype=np.float32))
        me.update()
        return me


def add_tube(mb, pts, rads, sides=4, mat=1):
    """Thin twig tube along pts (list of Vector)."""
    base = len(mb.v)
    n = len(pts)
    t0 = (pts[1] - pts[0]).normalized()
    ref = Vector((1, 0, 0)) if abs(t0.x) < 0.9 else Vector((0, 1, 0))
    nrm = t0.cross(ref).normalized()
    for k, (p, r) in enumerate(zip(pts, rads)):
        t = (pts[min(k + 1, n - 1)] - pts[max(k - 1, 0)]).normalized()
        nrm = (nrm - t * nrm.dot(t)).normalized()
        b = t.cross(nrm)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            mb.add_vert(p + (nrm * math.cos(a) + b * math.sin(a)) * r, (s / sides, k / n))
    for k in range(n - 1):
        for s in range(sides):
            a0 = base + k * sides + s
            a1 = base + k * sides + (s + 1) % sides
            mb.add_face((a0, a1, a1 + sides, a0 + sides), mat)


def add_leaf(mb, rng, origin, axis, up, shape, age=0.0, scale=1.0):
    """One blade. axis: unit direction from petiole base toward apex; up: approximate blade normal."""
    L = rng.uniform(*shape.length) * scale
    W = L * rng.uniform(*shape.aspect)
    pet = rng.uniform(*shape.petiole) * scale
    droop = rng.uniform(*shape.droop)
    side = up.cross(axis).normalized()
    nrm = axis.cross(side).normalized()
    rand = float(rng.uniform())
    # petiole: thin 3-sided stalk
    p_end = origin + axis * pet
    add_tube(mb, [origin, p_end], [0.0014 * scale, 0.0012 * scale], sides=3, mat=1)
    twist = rng.uniform(-0.25, 0.25)
    rows = []
    for t in LEAF_ROWS:
        hw = 0.5 * W * half_width(t, shape)
        x = t * L
        z_drop = -droop * L * t * t
        tw = twist * t
        s_dir = (side * math.cos(tw) + nrm * math.sin(tw))
        mid = p_end + axis * x + nrm * z_drop
        if t in (0.0, 1.0):
            rows.append([mb.add_vert(mid, (t, 0.5), rand, age)])
            continue
        lift = nrm * (shape.fold * hw)
        lv = mb.add_vert(mid - s_dir * hw + lift, (t, 0.0), rand, age)
        cv = mb.add_vert(mid, (t, 0.5), rand, age)
        rv = mb.add_vert(mid + s_dir * hw + lift, (t, 1.0), rand, age)
        rows.append([lv, cv, rv])
    # winding chosen so the face normal points along nrm (upper / adaxial side = front face)
    for a, b in zip(rows[:-1], rows[1:]):
        if len(a) == 1:
            mb.add_face((b[0], b[1], a[0]), 0)
            mb.add_face((b[1], b[2], a[0]), 0)
        elif len(b) == 1:
            mb.add_face((b[0], a[1], a[0]), 0)
            mb.add_face((b[0], a[2], a[1]), 0)
        else:
            mb.add_face((b[0], b[1], a[1], a[0]), 0)
            mb.add_face((b[1], b[2], a[2], a[1]), 0)
    return L


def _rot(axis, ang):
    return Matrix.Rotation(ang, 3, axis)


def add_rosette(mb, rng, tip, shoot_dir, sky, shape, n_leaves, young=False, bud=True, spread=(40, 82)):
    """Leaves crowded at a shoot tip (pseudo-whorl), spiral phyllotaxis."""
    golden = math.radians(137.5)
    ref = sky - shoot_dir * sky.dot(shoot_dir)
    ref = ref.normalized() if ref.length > 1e-4 else shoot_dir.orthogonal().normalized()
    phi0 = rng.uniform(0, 2 * math.pi)
    for k in range(n_leaves):
        frac = k / max(1, n_leaves - 1)
        # older (outer, lower) leaves first: more open; inner leaves more erect
        el = math.radians(spread[1] - (spread[1] - spread[0]) * frac + rng.uniform(-8, 8))
        az = phi0 + k * golden
        radial = _rot(shoot_dir, az) @ ref
        ax = (shoot_dir * math.cos(el) + radial * math.sin(el)).normalized()
        # gravity: open leaves tip slightly downward
        ax = (ax - sky * 0.18 * math.sin(el)).normalized()
        # star-like whorl: blades face along the shoot axis, tilted toward the sky side
        up = sky * 0.45 + shoot_dir * 0.55
        up = (up - ax * up.dot(ax)).normalized()
        origin = tip - shoot_dir * (0.035 * (1 - frac) + rng.uniform(0, 0.012))
        add_leaf(mb, rng, origin, ax, up, shape, age=0.0)
    if young:
        for k in range(rng.integers(3, 6)):
            az = phi0 + k * golden + 0.6
            radial = _rot(shoot_dir, az) @ ref
            ax = (shoot_dir * 0.88 + radial * 0.47).normalized()
            up = (radial - ax * radial.dot(ax)).normalized()
            add_leaf(mb, rng, tip, ax, up, shape, age=1.0, scale=rng.uniform(0.45, 0.7))
    elif bud:
        # terminal bud: elongated ovoid, imbricate red-brown scales (approximated as a 4-sided spindle)
        L = rng.uniform(0.016, 0.026)
        add_tube(mb, [tip, tip + shoot_dir * L * 0.5, tip + shoot_dir * L], [0.0045, 0.0055, 0.0008], sides=5, mat=2)


def build_spray(rng, shape, kind):
    """kind: dict with main_len, n_side, young, scattered."""
    mb = MeshBuilder()
    sky = Vector((0, 1, 0))
    L = kind["main_len"]
    # main shoot: gentle upward (toward +Y) curve
    n = 6
    bend = rng.uniform(0.15, 0.35)
    pts = []
    for k in range(n + 1):
        t = k / n
        pts.append(Vector((rng.normal(0, 0.006), bend * L * t * t, L * t)))
    rads = [0.0075 * (1 - 0.5 * k / n) for k in range(n + 1)]
    add_tube(mb, pts, rads, sides=4)
    tip_dir = (pts[-1] - pts[-2]).normalized()
    add_rosette(mb, rng, pts[-1], tip_dir, sky, shape, int(rng.integers(10, 15)), young=kind["young"])
    # side shoots (plagiotropic: spread mostly in the local X-Z plane, slightly up)
    for j in range(kind["n_side"]):
        t = rng.uniform(0.3, 0.78)
        k = t * n
        k0 = int(k)
        base = pts[k0].lerp(pts[min(k0 + 1, n)], k - k0)
        mdir = (pts[min(k0 + 1, n)] - pts[k0]).normalized()
        sgn = 1 if j % 2 == 0 else -1
        ang = math.radians(rng.uniform(32, 55))
        sdir = (mdir * math.cos(ang) + Vector((sgn, 0, 0)) * math.sin(ang) + sky * rng.uniform(0.0, 0.3)).normalized()
        sl = rng.uniform(0.1, 0.2) * (1.1 - 0.4 * t)
        sp = [base, base + sdir * sl * 0.5 + sky * 0.01, base + sdir * sl + sky * 0.03]
        add_tube(mb, sp, [0.0048, 0.0042, 0.0034], sides=4)
        sd = (sp[-1] - sp[-2]).normalized()
        add_rosette(mb, rng, sp[-1], sd, sky, shape, int(rng.integers(8, 12)), young=kind["young"] and rng.uniform() < 0.5)
    # scattered older leaves along the main shoot (previous season)
    for j in range(kind["scattered"]):
        t = rng.uniform(0.15, 0.7)
        k = t * n
        k0 = int(k)
        p = pts[k0].lerp(pts[min(k0 + 1, n)], k - k0)
        mdir = (pts[min(k0 + 1, n)] - pts[k0]).normalized()
        az = rng.uniform(0, 2 * math.pi)
        radial = Vector((math.cos(az), 0.35 * math.sin(az), 0)).normalized()
        radial = (radial - mdir * radial.dot(mdir)).normalized()
        ax = (mdir * 0.45 + radial * 0.9 - sky * 0.15).normalized()
        up = (sky - ax * sky.dot(ax)).normalized()
        add_leaf(mb, rng, p, ax, up, shape, scale=rng.uniform(0.9, 1.1))
    return mb


SPRAY_KINDS = [
    dict(main_len=0.341, n_side=3, young=False, scattered=3),
    dict(main_len=0.279, n_side=2, young=False, scattered=2),
    dict(main_len=0.403, n_side=4, young=False, scattered=4),
    dict(main_len=0.217, n_side=1, young=False, scattered=1),
    dict(main_len=0.31, n_side=3, young=True, scattered=2),
    dict(main_len=0.372, n_side=3, young=False, scattered=3),
    dict(main_len=0.186, n_side=0, young=False, scattered=1),
    dict(main_len=0.31, n_side=2, young=True, scattered=2),
]



