"""Phase 3 — polygon triangulation + flat-roof extrusion. Stdlib only.

Triangulation: hole-bridging + ear clipping. Correct for typical building
footprints (small rings, orthogonal shapes). Holes are rare in WFS footprints;
when present they are bridged into the outer ring (standard technique).
"""
from __future__ import annotations


def _signed_area(ring: list) -> float:
    a = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _clean_ring(ring: list) -> list:
    out = []
    for p in ring:
        if not out or (abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9):
            out.append([p[0], p[1]])
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    # Drop any vertex duplicating an earlier one (e.g. triangle stored as
    # A-B-C-B, or rings with repeated vertices). O(n^2) is fine: n is small.
    deduped = []
    for p in out:
        if not any(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for q in deduped):
            deduped.append(p)
    out = deduped
    # Spike removal: WFS footprints contain out-and-back spikes (A-B-A) and
    # collinear intermediate points. Strip iteratively: drop p[j] when it
    # coincides with p[j+1] (spike tip) or lies on segment p[j-1]->p[j+1].
    changed = True
    while changed and len(out) > 3:
        changed = False
        n = len(out)
        for j in range(n):
            prev = out[(j - 1) % n]
            cur = out[j]
            nxt = out[(j + 1) % n]
            # spike tip: prev == nxt (went out and came back)
            if abs(prev[0] - nxt[0]) < 1e-9 and abs(prev[1] - nxt[1]) < 1e-9:
                del out[j]
                changed = True
                break
            # collinear: cross == 0 and cur between prev and nxt
            cross = (cur[0] - prev[0]) * (nxt[1] - prev[1]) - (cur[1] - prev[1]) * (nxt[0] - prev[0])
            dot = (cur[0] - prev[0]) * (nxt[0] - prev[0]) + (cur[1] - prev[1]) * (nxt[1] - prev[1])
            seg2 = (nxt[0] - prev[0]) ** 2 + (nxt[1] - prev[1]) ** 2
            if seg2 > 0 and abs(cross) < 1e-9 * seg2 and 0 < dot < seg2:
                del out[j]
                changed = True
                break
    return out


def _point_in_triangle(px, py, ax, ay, bx, by, cx, cy) -> bool:
    v0x, v0y = cx - ax, cy - ay
    v1x, v1y = bx - ax, by - ay
    v2x, v2y = px - ax, py - ay
    d00 = v0x * v0x + v0y * v0y
    d01 = v0x * v1x + v0y * v1y
    d02 = v0x * v2x + v0y * v2y
    d11 = v1x * v1x + v1y * v1y
    d12 = v1x * v2x + v1y * v2y
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18:
        return False
    u = (d11 * d02 - d01 * d12) / den
    v = (d00 * d12 - d01 * d02) / den
    return u >= -1e-9 and v >= -1e-9 and (u + v) <= 1 + 1e-9


def _ear_clip(ring: list) -> list:
    """Ear clipping on a single CCW ring. Returns index triples."""
    n = len(ring)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    idx = list(range(n))
    tris = []
    guard = n * n
    while len(idx) > 3 and guard > 0:
        guard -= 1
        m = len(idx)
        clipped = False
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            ax, ay = ring[i0]
            bx, by = ring[i1]
            cx, cy = ring[i2]
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if cross <= 1e-12:  # reflex (CCW) or degenerate
                continue
            ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                if _point_in_triangle(ring[j][0], ring[j][1], ax, ay, bx, by, cx, cy):
                    ok = False
                    break
            if ok:
                tris.append((i0, i1, i2))
                del idx[k]
                clipped = True
                break
        if not clipped:
            break  # degenerate input; avoid infinite loop
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _bridge_holes(outer: list, holes: list) -> list:
    """Merge holes into outer ring via leftmost-hole-vertex bridging."""
    ring = [list(p) for p in outer]
    for hole in holes:
        h = [list(p) for p in hole]
        # leftmost (then lowest) hole vertex
        hi = min(range(len(h)), key=lambda i: (h[i][0], h[i][1]))
        hx, hy = h[hi]
        # visible outer vertex: closest in x-distance to the left of hx
        best, best_i = None, -1
        for i, (ox, oy) in enumerate(ring):
            if ox <= hx + 1e-9:
                # segment (ox,oy)->(hx,hy) must not cross; cheap check: pick max ox
                score = ox
                if best is None or score > best:
                    best, best_i = score, i
        if best_i < 0:
            best_i = 0
        # splice: ring[..best_i] + hole-loop + ring[best_i..]
        loop = h[hi:] + h[:hi + 1]
        ring = ring[:best_i + 1] + loop + ring[best_i + 1:]
    return ring


def _seg_intersection(p1, p2, p3, p4):
    """Proper segment intersection point (None if parallel or only touching at ends)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-18:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    if 1e-9 < t < 1 - 1e-9 and 1e-9 < u < 1 - 1e-9:
        return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)]
    return None


def _ccw(tri: list) -> list:
    if _signed_area(tri) < 0:
        return tri[::-1]
    return tri


def _split_bowtie_quad(ring: list):
    """Split a self-intersecting quad (bowtie) into its two lobe triangles.

    Returns [(lobe1, [(0,1,2)]), (lobe2, [(0,1,2)])] or None.
    Exact split — no fabricated area (unlike convex-hull fallback).
    """
    if len(ring) != 4:
        return None
    a, b, c, d = ring
    x = _seg_intersection(a, b, c, d)
    if x is not None:
        return [(_ccw([a, d, x]), [(0, 1, 2)]), (_ccw([b, c, x]), [(0, 1, 2)])]
    x = _seg_intersection(b, c, d, a)
    if x is not None:
        return [(_ccw([a, b, x]), [(0, 1, 2)]), (_ccw([c, d, x]), [(0, 1, 2)])]
    return None


def triangulate(polygon_lonlat_or_enu: list) -> list:
    """Triangulate a GeoJSON polygon (outer + optional holes).

    Returns a list of (ring, tris) parts — normally exactly one part.
    A bowtie quad that ear clipping cannot handle is split into its two
    exact lobe triangles (two parts). Larger self-intersecting rings that
    still fail return a single part with empty tris (caller skips + logs).
    Input ring orientation is normalized (outer CCW).
    """
    outer = _clean_ring(polygon_lonlat_or_enu[0])
    holes = [_clean_ring(h) for h in polygon_lonlat_or_enu[1:]]
    holes = [h for h in holes if len(h) >= 3]
    ring = _bridge_holes(outer, holes) if holes else outer
    if _signed_area(ring) < 0:
        ring = ring[::-1]
    tris = _ear_clip(ring)
    if tris or len(ring) != 4:
        return [(ring, tris)]
    split = _split_bowtie_quad(ring)
    if split is not None:
        return split
    return [(ring, [])]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    import math
    l = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-12 else (0.0, 0.0, 1.0)


def _tri_area2(p1, p2, p3) -> float:
    return abs((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0]))


def extrude(ring: list, tris: list, height: float) -> tuple[list, list, list]:
    """Extrude a triangulated CCW ring to a flat-roof prism.

    Returns (positions, normals, indices) with flat shading (duplicated verts).
    Y-up game frame: (x=enu_x, y=height, z=-enu_y) so north = -Z.
    Degenerate caps (zero area) and zero-length wall edges are skipped:
    strict engines (UE MeshDescription) reject them.
    """
    pos, nrm, idx = [], [], []

    def add_tri(p1, p2, p3):
        base = len(pos) // 3  # pos is a flat float list: 3 floats per vertex
        n = _norm(_cross(_sub(p2, p1), _sub(p3, p1)))
        for p in (p1, p2, p3):
            pos.extend(p)
            nrm.extend(n)
        idx.extend([base, base + 1, base + 2])

    # roof (ENU CCW maps to +Y in the game frame (x, height, -y))
    rp = [(x, height, -y) for x, y in ring]
    for a, b, c in tris:
        if _tri_area2(ring[a], ring[b], ring[c]) < 1e-12:
            continue  # degenerate cap: strict importers reject it
        add_tri(rp[a], rp[b], rp[c])
    # walls (skip zero-length edges)
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (x2 - x1) ** 2 + (y2 - y1) ** 2 < 1e-18:
            continue
        p1 = (x1, 0.0, -y1)
        p2 = (x2, 0.0, -y2)
        p3 = (x2, height, -y2)
        p4 = (x1, height, -y1)
        add_tri(p1, p2, p3)
        add_tri(p1, p3, p4)
    # base skirt (faces down, closes the solid)
    bp = [(x, 0.0, -y) for x, y in ring]
    for a, b, c in tris:
        if _tri_area2(ring[a], ring[b], ring[c]) < 1e-12:
            continue
        add_tri(bp[a], bp[c], bp[b])
    return pos, nrm, idx
