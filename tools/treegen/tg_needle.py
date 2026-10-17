"""柳杉 Cryptomeria japonica foliage sprays (same contract as tg_leaf / tg_phyllode: +Z = spray growth direction, +Y = sky side,
slots 0 = foliage, 1 = twig, per-point leaf_rand / leaf_age, UV x along the needle).

What makes it 柳杉 and not a fir / pine: no flat needle sprays and no long needle bundles. Short (6-14 mm), stiff, awl-shaped needles
curve forward and clothe every branchlet all round, so each branchlet reads as a thick green CORD; the cords branch into loose,
upturned tufts ("rope-like" foliage) that clump at the branch ends.
"""
from __future__ import annotations

import math

from mathutils import Matrix, Vector

from tg_leaf import MeshBuilder, add_tube


def _cord(mb, rng, pts, spacing, length=(0.010, 0.018), angle=(40, 65), age_tip=0.0):
    """Needles spirally (137.5 deg) all round a cord polyline, each one triangle curving forward toward the cord tip."""
    seg = [(pts[k + 1] - pts[k]).length for k in range(len(pts) - 1)]
    total = sum(seg)
    s, phi, n = 0.0, rng.uniform(0, 2 * math.pi), 0
    while s < total:
        acc, k = 0.0, 0
        while k < len(seg) - 1 and acc + seg[k] < s:
            acc += seg[k]
            k += 1
        p = pts[k].lerp(pts[k + 1], (s - acc) / max(seg[k], 1e-9))
        d = (pts[k + 1] - pts[k]).normalized()
        phi += math.radians(137.5)
        radial = Matrix.Rotation(phi, 3, d) @ d.orthogonal().normalized()
        frac = s / total
        L = rng.uniform(*length) * (0.6 + 0.4 * min(1.0, (1 - frac) / 0.3 + 0.2))  # shorter toward the growing tip
        a_ = math.radians(rng.uniform(*angle))
        ax = (d * math.cos(a_) + radial * math.sin(a_)).normalized()
        w = 0.0010 + 0.0004 * rng.uniform()  # half-width at the base: 2-2.8 mm awl
        side = ax.cross(radial).normalized()
        tipp = p + ax * L + d * (0.25 * L)  # awl tip curved forward
        age = age_tip * max(0.0, (frac - 0.8) / 0.2)
        rand = float(rng.uniform())
        a = mb.add_vert(p - side * w, (0.0, 0.2), rand, age)
        b = mb.add_vert(p + side * w, (0.0, 0.4), rand, age)
        c = mb.add_vert(tipp, (1.0, 0.3), rand, age)
        mb.add_face((a, b, c), 0)
        n += 1
        s += spacing * rng.uniform(0.8, 1.2)
    return n


def _curve(rng, base, d, L, up, curl, segs=5):
    """Cord polyline: starts along d, bends toward `up` (tips turn up) with a little random wander."""
    pts, p = [base], base.copy()
    for k in range(segs):
        t = (k + 1) / segs
        dd = (d + up * curl * t * t + Vector(rng.normal(0, 0.08, 3))).normalized()
        p = p + dd * (L / segs)
        pts.append(p)
    return pts


def build_spray(rng, kind):
    """kind: dict(main_len, n_side, side_len, curl, spacing, age_tip)."""
    mb = MeshBuilder()
    sky = Vector((0, 1, 0))
    fwd = Vector((0, 0, 1))
    L = kind["main_len"]
    main = _curve(rng, Vector((0, 0, 0)), fwd, L, sky, kind["curl"], segs=6)
    add_tube(mb, main, [0.0025 * (1 - 0.6 * k / 6) for k in range(7)], sides=4)
    n = _cord(mb, rng, main, kind["spacing"], age_tip=kind["age_tip"])
    for j in range(kind["n_side"]):
        t = 0.2 + 0.7 * (j + rng.uniform(0, 0.8)) / kind["n_side"]
        k = min(int(t * 6), 5)
        base = main[k].lerp(main[k + 1], t * 6 - k)
        md = (main[k + 1] - main[k]).normalized()
        ang = math.radians(rng.uniform(35, 60))
        # side cords fan out in all directions round the axis (a 3-D tuft, not a flat fir spray), biased sideways
        roll = rng.uniform(-1.0, 1.0) + (0 if j % 2 else math.pi)
        lat = Matrix.Rotation(roll, 3, md) @ Vector((1, 0, 0))
        sd = (md * math.cos(ang) + lat * math.sin(ang)).normalized()
        sl = kind["side_len"] * rng.uniform(0.7, 1.2) * (1.15 - 0.6 * t)
        pts = _curve(rng, base, sd, sl, sky, kind["curl"] * 1.2, segs=4)
        add_tube(mb, pts, [0.0013, 0.0011, 0.001, 0.0009, 0.0008], sides=3)
        n += _cord(mb, rng, pts, kind["spacing"], age_tip=kind["age_tip"])
        # second-order cords: short upturned tufts off each side cord -> the clumped, rope-like pad
        for q in range(kind.get("n_sub", 0)):
            u = 0.3 + 0.6 * (q + rng.uniform(0, 0.7)) / kind["n_sub"]
            kq = min(int(u * 4), 3)
            b2 = pts[kq].lerp(pts[kq + 1], u * 4 - kq)
            d2 = (pts[kq + 1] - pts[kq]).normalized()
            lat2 = Matrix.Rotation(rng.uniform(0, 2 * math.pi), 3, d2) @ d2.orthogonal().normalized()
            a2 = math.radians(rng.uniform(35, 60))
            p2 = _curve(rng, b2, (d2 * math.cos(a2) + lat2 * math.sin(a2)).normalized(), sl * rng.uniform(0.3, 0.5), sky, kind["curl"] * 1.5, segs=3)
            n += _cord(mb, rng, p2, kind["spacing"], age_tip=kind["age_tip"])
    mb.n_needles = n
    return mb


# branchlet systems ("pads"): one axis, many side cords, each with short second-order tufts (it1/it2 single cords were far too sparse)
SPRAY_KINDS = [
    dict(main_len=0.70, n_side=14, side_len=0.26, n_sub=3, curl=0.5, spacing=0.0036, age_tip=0.0),
    dict(main_len=0.55, n_side=10, side_len=0.22, n_sub=2, curl=0.7, spacing=0.0036, age_tip=0.6),
    dict(main_len=0.85, n_side=16, side_len=0.30, n_sub=3, curl=0.45, spacing=0.0038, age_tip=0.0),
    dict(main_len=0.45, n_side=9, side_len=0.20, n_sub=2, curl=0.8, spacing=0.0034, age_tip=0.0),
    dict(main_len=0.65, n_side=12, side_len=0.26, n_sub=3, curl=0.6, spacing=0.0036, age_tip=0.4),
    dict(main_len=0.75, n_side=14, side_len=0.28, n_sub=2, curl=0.35, spacing=0.0038, age_tip=0.0),
    dict(main_len=0.50, n_side=10, side_len=0.22, n_sub=3, curl=0.9, spacing=0.0034, age_tip=0.0),
    dict(main_len=0.80, n_side=15, side_len=0.30, n_sub=3, curl=0.5, spacing=0.0040, age_tip=0.3),
]
