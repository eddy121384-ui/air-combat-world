"""相思樹 Acacia confusa phyllode sprays (instanced on the skeleton tips, same contract as tg_leaf).

Local spray frame: +Z = growth direction of the spray, +Y = the side that faces the sky. One mesh per prototype, material slots
0 = phyllode, 1 = twig; per-point attributes `leaf_rand` (0..1 per phyllode), `leaf_age` (0 mature .. 1 young, paler), UV per blade
(x along the blade 0 base .. 1 apex, y across 0..1, midline at 0.5).

What makes it Acacia and not 紅楠 (tg_leaf): no broad leaves crowded in tip rosettes, no bud. Long slender arching twigs carry
alternate, NARROW (6.5-10 cm x 5-9 mm), falcate phyllodes with a hooked tip, spread 30-60 deg from the twig, and - like most
phyllodinous acacias - held with the blade roughly VERTICAL (edge-on to the overhead sun). That is what makes the crown read
fine-grained, feathery and light-transmitting instead of a dense dark dome.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from mathutils import Matrix, Vector

from tg_leaf import MeshBuilder, add_tube

ROWS = (0.0, 0.08, 0.22, 0.4, 0.58, 0.76, 0.9, 1.0)


@dataclass
class PhyllodeShape:
    length: tuple = (0.065, 0.10)  # m (PROSEA: 6.5-10 cm)
    width: tuple = (0.0055, 0.0085)  # m (5-9 mm)
    widest: float = 0.42  # narrowed at both ends, widest a little below the middle
    falcate: tuple = (0.06, 0.14)  # sideways (in-blade) bow of the midline, fraction of the length
    hook: float = 0.025  # extra curl of the last 10 % (hooked apex)
    droop: tuple = (0.0, 0.08)


def half_width(t, shape):
    pw = shape.widest
    if t <= pw:
        return math.sin(0.5 * math.pi * t / pw) ** 0.8
    return math.sin(0.5 * math.pi * (1 - t) / (1 - pw)) ** 0.9


def add_phyllode(mb, rng, origin, axis, normal, shape, age=0.0, scale=1.0):
    """One falcate phyllode. axis: base -> apex; normal: blade normal (perpendicular to axis)."""
    L = rng.uniform(*shape.length) * scale
    W = rng.uniform(*shape.width) * scale
    bow = rng.uniform(*shape.falcate) * L * (1 if rng.uniform() < 0.5 else -1)
    droop = rng.uniform(*shape.droop) * L
    side = normal.cross(axis).normalized()
    rand = float(rng.uniform())
    rows = []
    for t in ROWS:
        # falcate: midline bows sideways inside the blade plane (parabola), apex hooks a little further
        lat = bow * 4 * t * (1 - t) + (shape.hook * L * (1 if bow > 0 else -1) * max(0.0, (t - 0.88) / 0.12) ** 2)
        mid = origin + axis * (t * L) + side * lat - normal * (droop * t * t)
        if t in (0.0, 1.0):
            rows.append([mb.add_vert(mid, (t, 0.5), rand, age)])
            continue
        hw = 0.5 * W * half_width(t, shape)
        rows.append([mb.add_vert(mid - side * hw, (t, 0.0), rand, age), mb.add_vert(mid + side * hw, (t, 1.0), rand, age)])
    for a, b in zip(rows[:-1], rows[1:]):
        if len(a) == 1:
            mb.add_face((b[0], b[1], a[0]), 0)
        elif len(b) == 1:
            mb.add_face((b[0], a[1], a[0]), 0)
        else:
            mb.add_face((b[0], b[1], a[1], a[0]), 0)
    return L


def _twig(rng, L, bend, sag, sky):
    """Arching twig in the local frame: leaves the parent along +Z with a little lift, arches over and sags at the end."""
    n = 8
    pts = []
    lat = rng.normal(0, 0.02)
    for k in range(n + 1):
        t = k / n
        pts.append(Vector((lat * L * t * t + rng.normal(0, 0.003), (bend * t - sag * t * t) * L, L * t)))
    return pts


def _phyllodes_along(mb, rng, pts, shape, sky, t0, spacing, angle=(30, 60), young_tip=0, scale=1.0):
    """Alternate (spiral 2/5) phyllodes along a twig polyline from fraction t0 to the tip; blades held near-vertical."""
    seg = [(pts[k + 1] - pts[k]).length for k in range(len(pts) - 1)]
    total = sum(seg)
    s = t0 * total
    phi = rng.uniform(0, 2 * math.pi)
    count = 0
    idx = []
    while s < total - 0.004:
        idx.append(s)
        s += spacing * rng.uniform(0.75, 1.25)
    for j, s in enumerate(idx):
        # locate s on the polyline
        acc, k = 0.0, 0
        while k < len(seg) - 1 and acc + seg[k] < s:
            acc += seg[k]
            k += 1
        f = (s - acc) / max(seg[k], 1e-9)
        p = pts[k].lerp(pts[k + 1], f)
        d = (pts[k + 1] - pts[k]).normalized()
        phi += math.radians(144.0)  # 2/5 phyllotaxis
        ref = sky - d * sky.dot(d)
        ref = ref.normalized() if ref.length > 1e-4 else d.orthogonal().normalized()
        radial = Matrix.Rotation(phi, 3, d) @ ref
        # gravity flattens the spiral toward the twig's horizontal plane (phyllodes spread sideways and downward, few straight up)
        radial = (radial - sky * 0.35 * max(0.0, radial.dot(sky))).normalized()
        frac = s / total
        ang = math.radians(rng.uniform(*angle) * (0.75 + 0.35 * frac))
        ax = (d * math.cos(ang) + radial * math.sin(ang)).normalized()
        ax = (ax - sky * rng.uniform(0.0, 0.18)).normalized()
        # blade plane leans toward vertical (normal horizontal, perpendicular to the blade axis) but with a wide random tilt: A. confusa
        # phyllodes are far less strictly vertical than e.g. eucalypt leaves (Hong Kong crown photo), and a strictly vertical set reads
        # as bare twigs from above (atlas top-view coverage 3-5 % in the first export)
        nrm = ax.cross(sky)
        nrm = nrm.normalized() if nrm.length > 1e-3 else ax.orthogonal().normalized()
        tilt = rng.uniform(-1.05, 1.05)
        nrm = (nrm * math.cos(tilt) + sky * math.sin(tilt))
        nrm = (nrm - ax * nrm.dot(ax)).normalized()
        young = 1.0 if j >= len(idx) - young_tip else 0.0
        sc = scale * (0.55 + 0.45 * min(1.0, frac / 0.25)) * (0.7 if young else 1.0)
        add_phyllode(mb, rng, p, ax, nrm, shape, age=young, scale=sc)
        count += 1
    return count


def build_spray(rng, shape, kind):
    """kind: dict(main_len, n_side, sag, young_tip)."""
    mb = MeshBuilder()
    sky = Vector((0, 1, 0))
    L = kind["main_len"]
    pts = _twig(rng, L, rng.uniform(0.18, 0.32), kind["sag"] * rng.uniform(0.8, 1.2), sky)
    add_tube(mb, pts, [0.0035 * (1 - 0.65 * k / (len(pts) - 1)) for k in range(len(pts))], sides=4)
    n = _phyllodes_along(mb, rng, pts, shape, sky, 0.12, rng.uniform(0.008, 0.012), young_tip=kind["young_tip"])
    for j in range(kind["n_side"]):
        t = rng.uniform(0.18, 0.62)
        k = int(t * (len(pts) - 1))
        base = pts[k]
        mdir = (pts[k + 1] - pts[k]).normalized()
        sgn = 1 if j % 2 == 0 else -1
        ang = math.radians(rng.uniform(28, 50))
        sdir = (mdir * math.cos(ang) + Vector((sgn, 0, 0)) * math.sin(ang) + sky * rng.uniform(-0.05, 0.15)).normalized()
        sl = L * rng.uniform(0.35, 0.6) * (1.1 - 0.5 * t)
        # side twig in the spray frame: rotate a local twig so its +Z follows sdir
        loc = _twig(rng, sl, rng.uniform(0.1, 0.25), kind["sag"] * rng.uniform(0.6, 1.1), sky)
        zf = sdir
        xf = sky.cross(zf).normalized()
        yf = zf.cross(xf).normalized()
        R = Matrix((xf, yf, zf)).transposed()
        sp = [base + R @ q for q in loc]
        add_tube(mb, sp, [0.0022 * (1 - 0.6 * q / (len(sp) - 1)) for q in range(len(sp))], sides=3)
        n += _phyllodes_along(mb, rng, sp, shape, sky, 0.1, rng.uniform(0.008, 0.012), young_tip=max(0, kind["young_tip"] - 1), scale=0.92)
    mb.n_phyllodes = n
    return mb


SPRAY_KINDS = [
    dict(main_len=0.46, n_side=2, sag=0.32, young_tip=0),
    dict(main_len=0.38, n_side=1, sag=0.22, young_tip=2),
    dict(main_len=0.55, n_side=3, sag=0.42, young_tip=0),
    dict(main_len=0.30, n_side=0, sag=0.18, young_tip=0),
    dict(main_len=0.50, n_side=2, sag=0.5, young_tip=3),
    dict(main_len=0.42, n_side=2, sag=0.3, young_tip=0),
    dict(main_len=0.26, n_side=1, sag=0.12, young_tip=0),
    dict(main_len=0.60, n_side=3, sag=0.55, young_tip=2),
]
