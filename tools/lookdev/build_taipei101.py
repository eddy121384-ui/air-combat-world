"""Build the Taipei 101 hero asset for the XinyiLook visual layer.

The ordinary WFS pipeline deliberately suppresses the 101 record stack (8 parts)
and leaves a hole in the skyline. This script fills that hole with a dedicated
hero mesh. It does not touch ordinary-building geometry or the suppression
rule; it only *reads* the suppressed records to anchor the hero:

- plan centre + orientation: minimum rotated rectangle of the widest suppressed
  record (the ~54 m double-notched outline);
- ground: surveyed WFS ground_elev_m of the tower records;
- total height: the 508 m architectural reference (AGENTS.md hero rule).

Vertical massing (verified public figures + WFS stack):
  base        floors 1-26, 25-storey truncated pyramid          0.0 - 120.6 m
  modules     8 x 8-storey outward-flaring modules (~7 deg)   120.6 - 391.0 m
  top tower   floors 91-101 (101F at 438 m, roof 449.2 m)    391.0 - 449.2 m
  pinnacle    stepped housing + spire to 508 m               449.2 - 508.0 m

Output (game frame, same as the building tiles: X=east, Y=up, Z=-north;
local origin = plan centre at surveyed ground):
  unreal/Saved/XinyiLook/hero/taipei101.glb
  unreal/Saved/XinyiLook/hero/taipei101.anchor.json

Vertex data contract (read by the city shader, HERO path):
  TEXCOORD_0  (perimeter metres, height metres) — facade coordinates
  TEXCOORD_1  (WFS height 508 m, floor height 4.225 m) — the ordinary city contract
  TEXCOORD_2  packed RGBA8 (see gltf_writer.pack_rgba8):
              R = section id (0 base, 1..8 modules, 9 top, 10 pinnacle, 20 ornament)
              G = height fraction within section (0..255)
              B = 255 for glass, 0 for solid trim
              A = 250 (hero archetype tag)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/compiler"))
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
OUT = REPO / "unreal/Saved/XinyiLook/hero"

HERO_TOTAL_HEIGHT_M = 508.0
BASE_TOP_M = 120.6
MODULE_H_M = 33.8
ROOF_M = 449.2
HERO_TAG = 250

# ENU (x=east, y=north, z=up) -> game (X=east, Y=up, Z=-north)
GAME_FROM_ENU = np.array(
    [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=np.float64
)


def notched_square(half: float, notch: float, steps: int = 2) -> np.ndarray:
    """Square plan with stepped ("double-notched") corners, CCW, starting east."""
    pts = []
    # Build one corner (NE) as a staircase, then rotate for the others.
    corner = []
    s = notch / steps
    x, y = half, half - notch
    corner.append((x, y))
    for i in range(steps):
        x -= s
        corner.append((x, y))
        y += s
        corner.append((x, y))
    # last point sits on the north edge at x = half - notch
    for q in range(4):
        c, sn = math.cos(q * math.pi / 2), math.sin(q * math.pi / 2)
        for px, py in corner:
            pts.append((px * c - py * sn, px * sn + py * c))
    return np.asarray(pts, dtype=np.float64)


class MeshBuilder:
    def __init__(self):
        self.v, self.f, self.uv, self.col = [], [], [], []

    def quad(self, a, b, c, d, uva, uvb, uvc, uvd, col):
        base = len(self.v)
        self.v += [a, b, c, d]
        self.uv += [uva, uvb, uvc, uvd]
        self.col += [col] * 4
        self.f += [[base, base + 1, base + 2], [base, base + 2, base + 3]]

    def tri(self, a, b, c, col, uvs=((0, 0), (0, 0), (0, 0))):
        base = len(self.v)
        self.v += [a, b, c]
        self.uv += list(uvs)
        self.col += [col] * 3
        self.f += [[base, base + 1, base + 2]]

    def loft(self, ring0, z0, ring1, z1, col0, col1):
        """Side walls between two rings with identical vertex counts (flat shaded)."""
        n = len(ring0)
        per = 0.0
        for i in range(n):
            j = (i + 1) % n
            seg = float(np.linalg.norm(ring0[j] - ring0[i]))
            a = (*ring0[i], z0)
            b = (*ring0[j], z0)
            c = (*ring1[j], z1)
            d = (*ring1[i], z1)
            self.quad(a, b, c, d,
                      (per, z0), (per + seg, z0), (per + seg, z1), (per, z1),
                      col0)
            # top-row vertices carry the section-top gradient value
            for k in (2, 3):
                self.col[-4 + k] = col1
            per += seg

    def cap(self, ring, z, col, up=True):
        # Rings here are star-shaped around the centre: fan from centroid.
        cx, cy = ring.mean(axis=0)
        n = len(ring)
        for i in range(n):
            j = (i + 1) % n
            a, b = ring[i], ring[j]
            if up:
                self.tri((cx, cy, z), (*a, z), (*b, z), col)
            else:
                self.tri((cx, cy, z), (*b, z), (*a, z), col)

    def ledge(self, outer, inner, z, col):
        """Horizontal ring between an outer and inner ring (same count), facing up."""
        n = len(outer)
        for i in range(n):
            j = (i + 1) % n
            self.quad((*inner[i], z), (*inner[j], z), (*outer[j], z), (*outer[i], z),
                      (0, 0), (0, 0), (0, 0), (0, 0), col)



def col(section: int, t: float, glass: bool) -> tuple:
    return (section, int(round(max(0.0, min(1.0, t)) * 255)), 255 if glass else 0, HERO_TAG)


def build_tower():
    glass = MeshBuilder()
    trim = MeshBuilder()
    orn = MeshBuilder()

    notch_ratio = 3.4 / 27.0

    def ring(h):
        return notched_square(h, h * notch_ratio)

    # --- base: truncated pyramid, 26 floors ---
    base_h0, base_h1 = 27.0, 23.2
    glass.loft(ring(base_h0), 0.0, ring(base_h1), BASE_TOP_M, col(0, 0, True), col(0, 1, True))
    # plinth trim at street level (stone), 0-9 m
    trim.loft(ring(base_h0 + 0.35), 0.0, ring(base_h0 + 0.3), 9.0, col(0, 0, False), col(0, 0, False))
    trim.ledge(ring(base_h0 + 0.3), ring(base_h0 - 0.1), 9.0, col(0, 0, False))

    # --- eight flaring modules ---
    mod_h0, mod_h1 = 19.6, 24.4
    prev_outer = ring(base_h1)
    for k in range(8):
        z0 = BASE_TOP_M + MODULE_H_M * k
        z1 = z0 + MODULE_H_M
        r0, r1 = ring(mod_h0), ring(mod_h1)
        # ledge where the previous section ends: a thin solid band + setback
        trim.ledge(prev_outer, r0, z0, col(k + 1, 0, False))
        # 1.4 m solid "lintel" band at the module foot (mechanical floor read)
        band_top = z0 + 1.4
        rb = ring(mod_h0 + (mod_h1 - mod_h0) * (1.4 / MODULE_H_M))
        trim.loft(r0, z0, rb, band_top, col(k + 1, 0, False), col(k + 1, 0.04, False))
        glass.loft(rb, band_top, r1, z1, col(k + 1, 0.04, True), col(k + 1, 1, True))
        prev_outer = r1

    # --- top tower: floors 91-101 ---
    z = BASE_TOP_M + MODULE_H_M * 8  # 391.0
    top_steps = [
        (15.0, 15.8, z, 406.0),
        (10.6, 10.6, 406.0, 409.0),
        (7.3, 7.8, 409.0, ROOF_M),
    ]
    for i, (h0, h1, za, zb) in enumerate(top_steps):
        r0, r1 = ring(h0), ring(h1)
        trim.ledge(prev_outer, r0, za, col(9, 0, False))
        glass.loft(r0, za, r1, zb, col(9, (za - z) / (ROOF_M - z), True), col(9, (zb - z) / (ROOF_M - z), True))
        prev_outer = r1
    # roof cap + pinnacle housing (stepped)
    housing = [(6.2, ROOF_M, 455.0), (4.6, 455.0, 462.0), (3.2, 462.0, 467.0)]
    for h, za, zb in housing:
        r = ring(h)
        trim.ledge(prev_outer, r, za, col(10, 0, False))
        trim.loft(r, za, r, zb, col(10, 0, False), col(10, 1, False))
        prev_outer = r
    trim.cap(prev_outer, 467.0, col(10, 1, False))

    # --- spire: 12-sided taper with rings to 508 m ---
    def circle(r, n=12):
        a = np.linspace(0, 2 * math.pi, n, endpoint=False) + math.pi / n
        return np.stack([np.cos(a) * r, np.sin(a) * r], axis=1)

    spire = [(1.9, 467.0), (1.6, 480.0), (1.1, 492.0), (0.6, 502.0), (0.12, HERO_TOTAL_HEIGHT_M)]
    for (ra, za), (rb, zb) in zip(spire[:-1], spire[1:]):
        trim.loft(circle(ra), za, circle(rb), zb, col(10, 0.5, False), col(10, 1, False))
        # ring collar
        if zb < HERO_TOTAL_HEIGHT_M:
            trim.loft(circle(rb + 0.45), zb - 0.6, circle(rb + 0.45), zb, col(10, 1, False), col(10, 1, False))
            trim.ledge(circle(rb + 0.45), circle(rb), zb, col(10, 1, False))

    # --- ancient-coin ornaments on each face at the base/tower junction (26F) ---
    coin_r, hole = 6.0, 1.7
    coin_z = BASE_TOP_M - 9.0
    face_dist = base_h1 + (base_h0 - base_h1) * (9.0 / BASE_TOP_M) + 1.0
    for q in range(4):
        ang = q * math.pi / 2
        nx, ny = math.cos(ang), math.sin(ang)
        tx, ty = -ny, nx
        segs = 24
        outer_pts, inner_pts = [], []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            outer_pts.append((math.cos(a) * coin_r, math.sin(a) * coin_r))
            # square hole sampled on the same angular parametrisation
            c, s = math.cos(a), math.sin(a)
            m = max(abs(c), abs(s))
            inner_pts.append((c / m * hole, s / m * hole))
        for depth, sgn in ((face_dist + 1.2, 1), (face_dist, -1)):
            for i in range(segs):
                j = (i + 1) % segs

                def P(p, d=depth):
                    return (nx * d + tx * p[0], ny * d + ty * p[0], coin_z + p[1])
                oc = col(20, 0, False)
                if sgn > 0:
                    orn.quad(P(inner_pts[i]), P(inner_pts[j]), P(outer_pts[j]), P(outer_pts[i]),
                             (0, 0), (0, 0), (0, 0), (0, 0), oc)
                else:
                    orn.quad(P(outer_pts[i]), P(outer_pts[j]), P(inner_pts[j]), P(inner_pts[i]),
                             (0, 0), (0, 0), (0, 0), (0, 0), oc)
        # rim
        for i in range(segs):
            j = (i + 1) % segs
            a = outer_pts[i]
            b = outer_pts[j]

            def Q(p, d):
                return (nx * d + tx * p[0], ny * d + ty * p[0], coin_z + p[1])
            orn.quad(Q(a, face_dist), Q(b, face_dist), Q(b, face_dist + 1.2), Q(a, face_dist + 1.2),
                     (0, 0), (0, 0), (0, 0), (0, 0), col(20, 0, False))
        # ruyi scroll above the coin: a simple cloud-curl slab, ~8 m tall
        curl = []
        for i in range(17):
            t = i / 16
            a = math.pi * (1.0 - t)
            curl.append((math.cos(a) * 4.2, 3.6 + math.sin(a) * 2.0 + 1.4 * math.sin(t * math.pi * 2)))
        for i in range(len(curl) - 1):
            p0, p1 = curl[i], curl[i + 1]
            for d0, d1 in ((face_dist, face_dist + 0.9),):
                def R(p, d, dz=0.0):
                    return (nx * d + tx * p[0], ny * d + ty * p[0], coin_z + coin_r + p[1] + dz)
                orn.quad(R(p0, d1), R(p1, d1), R(p1, d1, 1.3), R(p0, d1, 1.3),
                         (0, 0), (0, 0), (0, 0), (0, 0), col(20, 0, False))
    return glass, trim, orn


def anchor_from_wfs():
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    hero = [b for b in wm["buildings"] if b["suppressed"]]
    if len(hero) != 8:
        raise RuntimeError(f"expected 8 hero-suppressed records, got {len(hero)}")
    widest = max(hero, key=lambda b: b["polygons"][0]["area_m2"])
    poly = Polygon(widest["polygons"][0]["footprint_enu"])
    mrr = poly.minimum_rotated_rectangle
    c = np.asarray(mrr.exterior.coords)[:4]
    centre = c.mean(axis=0)
    # orientation: edge angle folded into [-45, 45)
    e = c[1] - c[0]
    ang = math.degrees(math.atan2(e[1], e[0]))
    ang = ((ang + 45.0) % 90.0) - 45.0
    grounds = sorted({round(float(props[b["id"]]["ground_elev_m"]), 3) for b in hero})
    if len(grounds) != 1:
        raise RuntimeError(f"hero ground elevations disagree: {grounds}")
    return {
        "centre_enu_m": [float(centre[0]), float(centre[1])],
        "rotation_deg_ccw": float(ang),
        "ground_elev_m": grounds[0],
        "widest_record": widest["id"],
        "widest_record_area_m2": float(poly.area),
        "suppressed_ids": sorted(b["id"] for b in hero),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    anchor = anchor_from_wfs()
    glass, trim, orn = build_tower()
    parts = {
        "T101_Glass": (glass, [0.28, 0.42, 0.40, 1.0]),
        "T101_Trim": (trim, [0.62, 0.66, 0.64, 1.0]),
        "T101_Ornament": (orn, [0.78, 0.62, 0.30, 1.0]),
    }
    from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # local helper

    prims = []
    tri_total = 0
    for name, (mb, rgba) in parts.items():
        v = np.asarray(mb.v, dtype=np.float64)
        r = math.radians(anchor["rotation_deg_ccw"])
        c, s = math.cos(r), math.sin(r)
        x = v[:, 0] * c - v[:, 1] * s
        y = v[:, 0] * s + v[:, 1] * c
        game = np.column_stack([x, v[:, 2], -y]).astype(np.float32)
        faces = np.asarray(mb.f, dtype=np.int64)
        fn = np.cross(game[faces[:, 1]] - game[faces[:, 0]], game[faces[:, 2]] - game[faces[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        normals = np.zeros_like(game)
        normals[faces.reshape(-1)] = np.repeat(fn, 3, axis=0)  # vertices are unshared per face
        prims.append({
            "name": name,
            "positions": game,
            "indices": faces.astype(np.uint32),
            "normals": normals.astype(np.float32),
            "uv0": np.asarray(mb.uv, dtype=np.float32),
            # M_Taipei101 still evaluates the ordinary city wall branch before blending to the hero
            # branch, and that branch divides by TEXCOORD_1.y (floor height). Without real UV1 data
            # the padded zeros produce NaN, which blacks out the hero's night emissive.
            "uv1": np.tile(np.float32([HERO_TOTAL_HEIGHT_M, MODULE_H_M / 8.0]), (len(game), 1)),
            "uv2": pack_rgba8(np.asarray(mb.col, dtype=np.uint8)),
            "base_color": rgba,
        })
        tri_total += len(mb.f)
    glb = OUT / "taipei101.glb"
    write_glb(glb, prims, mesh_name="SM_Taipei101")
    top = max(float(p["positions"][:, 1].max()) for p in prims)
    if abs(top - HERO_TOTAL_HEIGHT_M) > 1e-3:
        raise RuntimeError(f"hero height drifted: {top}")
    record = {
        "asset": "taipei101.glb",
        "sha256": hashlib.sha256(glb.read_bytes()).hexdigest(),
        "triangles": tri_total,
        "height_m": HERO_TOTAL_HEIGHT_M,
        "anchor": anchor,
        "ue_actor_location_cm": [
            anchor["centre_enu_m"][0] * 100.0,
            -anchor["centre_enu_m"][1] * 100.0,
            anchor["ground_elev_m"] * 100.0,
        ],
        "expected_ue_local_bounds": ue_local_bounds_cm(np.concatenate([p["positions"] for p in prims])),
        "frame": "game (X=east, Y=up, Z=-north); local origin = plan centre at surveyed ground",
        "note": "Rotation is baked into the mesh; place the actor with zero rotation.",
    }
    (OUT / "taipei101.anchor.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: record[k] for k in ("triangles", "height_m", "ue_actor_location_cm")}))
    print(json.dumps(anchor))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
