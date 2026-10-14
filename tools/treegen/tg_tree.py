"""Tree skeleton (space colonisation inside a lobed crown envelope) and tube meshing.

The skeleton is a list of nodes with parent links. Branch radii follow the pipe model.
Meshing writes one tube per branch chain (continuation = thickest child), embedded at the parent axis.
No bpy import at module level for the skeleton part; meshing builds a bpy mesh from numpy arrays.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree


# ----------------------------------------------------------------------------- envelope


@dataclass
class Lobe:
    c: np.ndarray
    r: float
    zf: float  # vertical squash (<1 flatter)


def make_lobes(rng, n, shell_c, shell_r, elev_range, radial_frac, lobe_r, zf):
    """Lobe centres on the shell, blue-noise (dart throwing) over the allowed elevation band.

    A golden-angle spiral with ordered elevations was tried first: lobes 8 / 13 apart line up in azimuth and
    stack into vertical columns, which read as straight walls (a 'box' crown) from some azimuths."""
    lobes = []
    s0, s1 = math.sin(math.radians(elev_range[0])), math.sin(math.radians(elev_range[1]))
    band = 2 * math.pi * (s1 - s0)  # solid angle of the band
    sep = 0.8 * math.sqrt(band / n)
    dirs = []
    tries = 0
    while len(dirs) < n:
        tries += 1
        z = rng.uniform(s0, s1)  # uniform on the sphere band
        az = rng.uniform(0, 2 * math.pi)
        rxy = math.sqrt(max(0.0, 1 - z * z))
        d = np.array([rxy * math.cos(az), rxy * math.sin(az), z])
        if tries < 20000 and any(np.arccos(np.clip(d @ e, -1, 1)) < sep for e in dirs):
            continue
        dirs.append(d)
    for d in dirs:
        f = rng.uniform(*radial_frac)
        c = shell_c + d * shell_r * f
        lobes.append(Lobe(c=c, r=rng.uniform(*lobe_r), zf=zf))
    return lobes


def core_lobe(shell_c, shell_r, frac):
    """Inner crown body: turns the gaps between protruding lobes into shallow crevices instead of holes."""
    rx = 0.5 * (shell_r[0] + shell_r[1])
    return Lobe(c=np.asarray(shell_c, dtype=float), r=rx * frac, zf=shell_r[2] / rx)


def lobe_depth(p, lobes):
    """Signed depth inside the union of lobes (>0 inside), per point. p: (N,3)."""
    best = np.full(len(p), -1e9)
    for lb in lobes:
        q = p - lb.c
        q[:, 2] /= lb.zf
        best = np.maximum(best, lb.r - np.linalg.norm(q, axis=1))
    return best


def dome_envelope(p, c, r_xy, rz_up, rz_dn, asym=None, q_up=2.0):
    """Normalised radius of an egg-shaped dome (wide low, tapering top); <= 1 inside.

    asym: optional low-frequency azimuthal modulation so the crown is not a regular egg:
    dict(r1, a1, r2, a2, z1, az) -> r_xy *= 1 + r1 cos(t - a1) + r2 cos(2t - a2); rz_up *= 1 + z1 cos(t - az)."""
    q = p - np.asarray(c)
    rx = np.full(len(q), float(r_xy[0]))
    ry = np.full(len(q), float(r_xy[1]))
    ru = np.full(len(q), float(rz_up))
    if asym:
        t = np.arctan2(q[:, 1], q[:, 0])
        m = 1 + asym["r1"] * np.cos(t - asym["a1"]) + asym["r2"] * np.cos(2 * t - asym["a2"])
        rx, ry = rx * m, ry * m
        ru = ru * (1 + asym["z1"] * np.cos(t - asym["az"]))
    # q_up < 2 above the widest level: paraboloid-like taper instead of an ellipse
    # (an ellipse keeps near-vertical sides for most of the crown height, which reads as a cylinder from above)
    up = q[:, 2] >= 0
    zt = np.where(up, np.abs(q[:, 2] / ru) ** q_up, (q[:, 2] / rz_dn) ** 2)
    return np.sqrt((q[:, 0] / rx) ** 2 + (q[:, 1] / ry) ** 2 + zt)


def sample_attractors(rng, lobes, n, z_min, surface_bias=0.9, keep_floor=0.3, envelope=None, soft=0.12):
    lo = np.min([lb.c - lb.r for lb in lobes], axis=0)
    hi = np.max([lb.c + lb.r for lb in lobes], axis=0)
    out = []
    while sum(len(o) for o in out) < n:
        p = rng.uniform(lo, hi, size=(n, 3))
        p = p[p[:, 2] > z_min]
        if envelope is not None:
            e = envelope(p)
            # soft limit: lobes may bulge a little past the dome, never form square shoulders
            p = p[e < 1.0 + soft * rng.uniform(size=len(p)) ** 2]
        d = lobe_depth(p, lobes)
        p, d = p[d > 0], d[d > 0]
        keep = rng.uniform(size=len(p)) < keep_floor + (1 - keep_floor) * np.exp(-d / surface_bias)
        out.append(p[keep])
    return np.concatenate(out)[:n]


# ----------------------------------------------------------------------------- skeleton


@dataclass
class Skeleton:
    pos: list = field(default_factory=list)  # Vector
    parent: list = field(default_factory=list)  # int, -1 for root
    can_grow: list = field(default_factory=list)
    radius: np.ndarray | None = None
    children: list | None = None

    def add(self, p, parent, can_grow=True):
        self.pos.append(Vector(p))
        self.parent.append(parent)
        self.can_grow.append(can_grow)
        return len(self.pos) - 1

    def build_children(self):
        self.children = [[] for _ in self.pos]
        for i, par in enumerate(self.parent):
            if par >= 0:
                self.children[par].append(i)


def add_polyline(sk, start_idx, pts, can_grow=True):
    idx = start_idx
    for p in pts:
        idx = sk.add(p, idx, can_grow)
    return idx


def space_colonize(sk, attractors, seg, influence, kill, tropism, rng, jitter=0.08, max_iter=400):
    pts = [Vector(a) for a in attractors]
    alive = np.ones(len(pts), dtype=bool)
    for it in range(max_iter):
        kd = KDTree(len(sk.pos))
        for i, p in enumerate(sk.pos):
            kd.insert(p, i)
        kd.balance()
        pull = {}
        for j in np.flatnonzero(alive):
            p = pts[j]
            co, i, dist = kd.find(p)
            if dist < kill:
                alive[j] = False
                continue
            if dist > influence or not sk.can_grow[i]:
                continue
            v = (p - co) / dist
            acc = pull.get(i)
            pull[i] = v if acc is None else acc + v
        if not pull:
            break
        grown = 0
        for i, v in pull.items():
            if v.length < 1e-3:
                continue
            d = v.normalized() + tropism
            d += Vector(rng.normal(0, jitter, 3))
            d.normalize()
            new = sk.pos[i] + d * seg
            # avoid stacking a node on an existing child (oscillation)
            _, _, dd = kd.find(new)
            if dd < seg * 0.3:
                continue
            sk.add(new, i)
            grown += 1
        # kill attractors reached by new nodes
        kd2 = KDTree(grown + 1)
        base = len(sk.pos) - grown
        for k in range(grown):
            kd2.insert(sk.pos[base + k], k)
        kd2.balance()
        for j in np.flatnonzero(alive):
            _, _, dist = kd2.find(pts[j])
            if dist is not None and dist < kill:
                alive[j] = False
        if grown == 0 or not alive.any():
            break
    return it


def smooth(sk, iters=2, w=0.5, fixed_below=None):
    sk.build_children()
    for _ in range(iters):
        new = list(sk.pos)
        for i, par in enumerate(sk.parent):
            ch = sk.children[i]
            if par < 0 or not ch:
                continue
            if fixed_below is not None and sk.pos[i].z < fixed_below:
                continue
            nb = (sk.pos[par] + sum((sk.pos[c] for c in ch), Vector()) / len(ch)) * 0.5
            new[i] = sk.pos[i].lerp(nb, w)
        sk.pos = new


def pipe_radii(sk, r_tip, exponent, r_root=None):
    """Pipe-model radii. If r_root is given, radii are remapped geometrically
    r' = r_tip * (r / r_tip) ** g so that the root reaches r_root while tips stay r_tip
    (a skeleton has far fewer tips than a real crown has shoots, so the raw pipe model under-sizes wood)."""
    sk.build_children()
    n = len(sk.pos)
    rad = np.zeros(n)
    depth_cache.clear()
    order = sorted(range(n), key=lambda i: -_depth(sk, i))
    depth_cache.clear()
    for i in order:
        ch = sk.children[i]
        rad[i] = r_tip if not ch else sum(rad[c] ** exponent for c in ch) ** (1 / exponent)
    if r_root is not None:
        root = sk.parent.index(-1)
        g = math.log(r_root / r_tip) / math.log(rad[root] / r_tip)
        rad = r_tip * (rad / r_tip) ** g
    sk.radius = rad


depth_cache: dict = {}


def _depth(sk, i):
    if i in depth_cache:
        return depth_cache[i]
    d, j, chain = 0, i, []
    while j >= 0 and j not in depth_cache:
        chain.append(j)
        j = sk.parent[j]
    d = depth_cache.get(j, -1) if j >= 0 else -1
    for k in reversed(chain):
        d += 1
        depth_cache[k] = d
    return depth_cache[i]


def chains(sk):
    """Decompose into branch chains: list of node index lists (first item = attach node)."""
    sk.build_children()
    out = []
    root = sk.parent.index(-1)
    stack = [(root, None)]
    while stack:
        start, attach = stack.pop()
        chain = [attach] if attach is not None else []
        i = start
        while True:
            chain.append(i)
            ch = sk.children[i]
            if not ch:
                break
            ch = sorted(ch, key=lambda c: -sk.radius[c])
            for c in ch[1:]:
                stack.append((c, i))
            i = ch[0]
        out.append(chain)
    return out


def tips(sk):
    sk.build_children()
    return [i for i, c in enumerate(sk.children) if not c]


# ----------------------------------------------------------------------------- meshing


def _sides(r):
    if r > 0.16:
        return 18
    if r > 0.07:
        return 12
    if r > 0.03:
        return 8
    if r > 0.012:
        return 6
    return 4


def _catmull(pts, rads, sub):
    """Subdivide a polyline (Catmull-Rom) `sub` times per segment; radii linearly."""
    if sub <= 1 or len(pts) < 3:
        return pts, rads
    P = [pts[0]] + pts + [pts[-1]]
    op, orad = [], []
    for k in range(len(pts) - 1):
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        for s in range(sub):
            t = s / sub
            t2, t3 = t * t, t * t * t
            q = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            op.append(q)
            orad.append(rads[k] * (1 - t) + rads[k + 1] * t)
    op.append(pts[-1])
    orad.append(rads[-1])
    return op, orad


def mesh_branches(sk, min_radius=0.0, flare=None, bark_tile=0.6, rng=None, sides_fn=None, sub_fn=None):
    """Return (verts, faces, uvs, attrs) numpy arrays for all chains with radius >= min_radius.

    flare: callable(z, angle) -> radius multiplier for the trunk chain base (root flare / buttress).
    UV: u wraps the circumference (integer repeats so the seam tiles), v = length / bark_tile.
    attrs: per-vertex 'radius' (m) and 'branch_level'.
    """
    verts, faces, uvs, a_rad, a_lvl = [], [], [], [], []
    trunk_chain = None
    for ci, ch in enumerate(chains(sk)):
        pts = [sk.pos[i].copy() for i in ch]
        rads = [float(sk.radius[i]) for i in ch]
        if ch[0] is not None and len(ch) > 1 and sk.parent[ch[1]] == ch[0]:
            rads[0] = rads[1]  # attach ring uses the child's radius (sits inside the parent)
        if max(rads) < min_radius:
            continue
        if min_radius > 0:
            # game LODs: cut the thin end of a chain (foliage cards carry their own twigs)
            keep = len(rads)
            while keep > 2 and rads[keep - 1] < 0.6 * min_radius:
                keep -= 1
            pts, rads = pts[:keep], rads[:keep]
        is_trunk = sk.parent[ch[0]] == -1
        if is_trunk:
            trunk_chain = ch
        sub = sub_fn(rads[0]) if sub_fn else (3 if rads[0] > 0.05 else (2 if rads[0] > 0.015 else 1))
        pts, rads = _catmull(pts, rads, sub)
        n = sides_fn(rads[0]) if sides_fn else _sides(rads[0])
        repeats = max(1, round(2 * math.pi * rads[0] / bark_tile))
        # parallel-transport frames
        tang = []
        for k in range(len(pts)):
            a = pts[max(k - 1, 0)]
            b = pts[min(k + 1, len(pts) - 1)]
            t = (b - a)
            tang.append(t.normalized() if t.length > 1e-9 else Vector((0, 0, 1)))
        ref = Vector((1, 0, 0)) if abs(tang[0].x) < 0.9 else Vector((0, 1, 0))
        nrm = tang[0].cross(ref).normalized()
        base = len(verts)
        vacc = 0.0
        for k, (p, r, t) in enumerate(zip(pts, rads, tang)):
            if k > 0:
                vacc += (p - pts[k - 1]).length
                nrm = (nrm - t * nrm.dot(t)).normalized()
            bin_ = t.cross(nrm)
            for s in range(n + 1):
                ang = 2 * math.pi * s / n
                rr = r
                if is_trunk and flare is not None:
                    rr = r * flare(p.z, ang)
                off = nrm * math.cos(ang) + bin_ * math.sin(ang)
                verts.append(tuple(p + off * rr))
                uvs.append((repeats * s / n, vacc / bark_tile))
                a_rad.append(r)
                a_lvl.append(0.0 if is_trunk else 1.0)
        rings = len(pts)
        for k in range(rings - 1):
            r0 = base + k * (n + 1)
            r1 = r0 + n + 1
            for s in range(n):
                faces.append((r0 + s, r0 + s + 1, r1 + s + 1, r1 + s))
        # tip cap: collapse last ring by adding a centre vertex
        tip_c = len(verts)
        verts.append(tuple(pts[-1] + tang[-1] * rads[-1] * 0.5))
        uvs.append((0.5, vacc / bark_tile))
        a_rad.append(rads[-1])
        a_lvl.append(1.0)
        last = base + (rings - 1) * (n + 1)
        for s in range(n):
            faces.append((last + s, last + s + 1, tip_c))
    return verts, faces, uvs, np.array(a_rad), np.array(a_lvl)


def to_bpy_mesh(name, verts, faces, uvs, attrs=None):
    import bpy

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    vi = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vi)
    uvl.data.foreach_set("uv", np.asarray(uvs, dtype=np.float32)[vi].ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), dtype=bool))
    if attrs:
        for k, arr in attrs.items():
            at = me.attributes.new(k, "FLOAT", "POINT")
            at.data.foreach_set("value", np.asarray(arr, dtype=np.float32))
    me.update()
    return me
