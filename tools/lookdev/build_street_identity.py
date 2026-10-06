"""Taipei street identity v0B: projecting vertical signs + rain awnings on commercial frontage.

Placement reads the frontage roles baked into the look tiles (urban_identity/frontage_roles.json.gz,
acw.frontage_roles/0 - the same contract the wall shader uses) and never re-derives frontage:

  role 7 commercial frontage, major road    densest vertical signs + awnings
  role 6 commercial frontage, local road    vertical signs + awnings
  role 5 corner side street                 occasional sign / awning
  role 3/4 residential street               no large sign; rare small box sign (old stock, towers);
                                            offices very rare; civic none
  role 2 service way                        only a *lane* (service=alley, or an untagged way named 巷 / 弄)
                                            of old stock gets a sparse small box sign; driveway /
                                            parking_aisle / unnamed service access gets nothing
  role 1 rear / side, role 0                nothing (rear walls are not in the table at all)
Schools are not in the role table; civic records are skipped explicitly; rooftop records have no frontage.

Archetype weights: walk-up / low 1.0, huaxia 0.7, podium 0.3 (signs only), planned core x0.45.
Every prop footprint is tested against all building footprints (no sign / awning pierces a
neighbour or the building's own wing) and against already placed props (min spacing). Deterministic:
per-edge seeded RNG (sha256 of the edge id), no global random state.

Taipei Street Reality v0C adds parked scooters: one per occupied painted bay of the curb layer
(urban_identity/curb_segments.json.gz, build_ground.py / curb_zone.py), never anywhere else. Row fill 55-98 %
(per row, so some rows are packed and some sparse), nose toward the carriageway 70 %, yaw +-8 deg, +-0.15 m along
the kerb; a scooter whose footprint would touch a building is dropped. Four silhouettes (step-through, maxi,
step-through with delivery top box, compact e-scooter), 40-50 triangles each, one HISM per silhouette.

Instances (per-instance custom data 0 = (v + 0.5) / variants, decoded in xinyi_city.hlsl xc_street):
  sign / box  v = atlas cell + 64 * lit + 128 * fade(0..3)        (variants 512)
  awning      v = colour(0..7) + 8 * fade(0..3) + 32 * style(0..1) (variants 64)
  scooter_*   v = body colour(0..7) + 8 * grime(0..3) + 32 * top-box colour(0..1) (variants 64)

Outputs (unreal/Saved/XinyiLook/street/):
  street_sign.glb     unit blade: brackets x 0..0.25, panel x 0.25..1.25 (scaled by panel width), y +-0.5
                      (thickness), z 0..1 (height); TEXCOORD_0 = panel UV (both faces read correctly),
                      TEXCOORD_2 = (type 15, part: 0 face / 1 bracket / 2 edge)
  street_awning.glb   unit sloped canopy: x 0..1 projection, y +-0.5 width, z drop; type 16
  street_scooter_{a,b,c,d}.glb  parked scooters at true size, x = nose direction, origin on the ground at the
                      wheelbase centre; type 17, parts 0 body / 1 seat / 2 tyre / 3 trim / 4 top box / 5 floor
  street_instances.json, street.report.json
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
import build_ground as bg  # noqa: E402  (OSM road cache, same as the frontage rules)
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
LOOK = REPO / "unreal/Saved/XinyiLook"
OUT = LOOK / "street"
ROLES = LOOK / "urban_identity/frontage_roles.json.gz"
ATLAS = OUT / "sign_atlas.json"

ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM, ARCH_CIVIC, ARCH_SCHOOL = range(8)
OLD = {ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA}
TYPE_SIGN, TYPE_AWNING, TYPE_SCOOTER = 15, 16, 17
SIGN_VARIANTS, AWNING_VARIANTS, SCOOTER_VARIANTS = 512, 64, 64
CURB = LOOK / "urban_identity/curb_segments.json.gz"
SCOOTER_KINDS = ("scooter_a", "scooter_b", "scooter_c", "scooter_d")
SCOOTER_KIND_W = (0.45, 0.15, 0.25, 0.15)      # step-through, maxi, with delivery top box, compact e-scooter
SCOOTER_COLOUR_W = (25, 20, 20, 10, 7, 6, 6, 6)  # white, black, silver, dark grey, dark blue, dark red, beige, green
ROLE_FILL = {7: 1.0, 6: 1.0, 5: 0.95, 4: 0.9, 3: 0.9, 2: 0.9}
NOSE_OUT_P = 0.7                                # nose toward the carriageway

# vertical blades: mean spacing (m) along the frontage per role; awnings: probability per shop unit
BLADE_SPACING = {7: 6.5, 6: 10.0, 5: 22.0}
BOX_SPACING = {7: 22.0, 6: 26.0, 5: 40.0}
AWNING_P = {7: 0.52, 6: 0.46, 5: 0.25}
ARCH_W = {ARCH_LOW: 1.0, ARCH_WALKUP: 1.0, ARCH_HUAXIA: 0.7, ARCH_PODIUM: 0.3}
CORE_W = 0.45
LIT_P = {7: 0.60, 6: 0.50, 5: 0.35, 3: 0.30, 4: 0.35, 2: 0.25}
LANE_BOX_SPACING = 34.0
END_CLEAR_M = 0.9           # keep props this far from wall ends (corners / party walls)
STANDOFF = 0.25             # bracket length as a fraction of the panel width (mesh contract)
MIN_GAP_M = 1.4             # sign-to-sign spacing (centres, same height band)
AWNING_COLOURS = [6, 5, 3, 3, 2, 1, 1, 1]   # weights: green, blue, off-white, grey, white-blue, red, ochre, teal


def edge_rng(*key):
    return random.Random(int.from_bytes(hashlib.sha256("|".join(map(str, key)).encode()).digest()[:8], "big"))


# ------------------------------------------------------------------ meshes ---
class Mesh:
    def __init__(self, tid):
        self.tid = tid
        self.v, self.uv, self.c, self.f = [], [], [], []

    def quad(self, q, uv, part):
        b = len(self.v)
        self.v += q
        self.uv += uv
        self.c += [(self.tid, part, 0, 255)] * 4
        self.f += [(b, b + 1, b + 2), (b, b + 2, b + 3)]

    def tri(self, t, uv, part):
        b = len(self.v)
        self.v += t
        self.uv += uv
        self.c += [(self.tid, part, 0, 255)] * 3
        self.f += [(b, b + 1, b + 2)]

    def box(self, x0, x1, y0, y1, z0, z1, part, uv=(0.03, 0.5)):
        u = [uv] * 4
        for q in ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                  [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],
                  [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
                  [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
                  [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
                  [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)]):
            self.quad(q, u, part)

    def write(self, path, name):
        v = np.asarray(self.v, np.float64)
        f = np.asarray(self.f, np.int64)
        game = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype(np.float32)
        fn = np.cross(game[f[:, 1]] - game[f[:, 0]], game[f[:, 2]] - game[f[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
        nrm = np.zeros_like(game)
        for k in range(3):
            nrm[f[:, k]] = fn
        write_glb(path, [{"name": name, "positions": game, "normals": nrm,
                          "uv0": np.asarray(self.uv, np.float32),
                          "uv2": pack_rgba8(np.asarray(self.c, np.uint8)), "indices": f.astype(np.uint32),
                          "base_color": [0.6, 0.6, 0.6, 1.0]}], mesh_name=name)
        return ue_local_bounds_cm(game), len(f)


def sign_mesh():
    """Blade light box: panel x 0.25..1.25, y +-0.5, z 0..1. UV u reads left-to-right from both faces."""
    m = Mesh(TYPE_SIGN)
    xa, xb = STANDOFF, 1.0 + STANDOFF
    # +y face: viewer's right is -x -> u = 1 at the wall side;  -y face: right is +x
    m.quad([(xa, 0.5, 0.0), (xa, 0.5, 1.0), (xb, 0.5, 1.0), (xb, 0.5, 0.0)],
           [(1.0, 1.0), (1.0, 0.0), (0.0, 0.0), (0.0, 1.0)], 0)
    m.quad([(xb, -0.5, 0.0), (xb, -0.5, 1.0), (xa, -0.5, 1.0), (xa, -0.5, 0.0)],
           [(1.0, 1.0), (1.0, 0.0), (0.0, 0.0), (0.0, 1.0)], 0)
    # rim (top, bottom, outer edge, wall side): board frame colour
    e = [(0.02, 0.5)] * 4
    m.quad([(xa, -0.5, 1.0), (xa, 0.5, 1.0), (xb, 0.5, 1.0), (xb, -0.5, 1.0)], e, 2)
    m.quad([(xa, 0.5, 0.0), (xa, -0.5, 0.0), (xb, -0.5, 0.0), (xb, 0.5, 0.0)], e, 2)
    m.quad([(xb, 0.5, 0.0), (xb, -0.5, 0.0), (xb, -0.5, 1.0), (xb, 0.5, 1.0)], e, 2)
    m.quad([(xa, -0.5, 0.0), (xa, 0.5, 0.0), (xa, 0.5, 1.0), (xa, -0.5, 1.0)], e, 2)
    # steel brackets to the wall, near top and bottom
    for z0 in (0.06, 0.88):
        m.box(0.0, xa, -0.22, 0.22, z0, z0 + 0.05, 1)
    return m


def awning_mesh():
    """Practical rain canopy (雨遮): a thin sheet fixed to the wall at z 0, falling 0.36 to the front, a 0.1 drip
    lip, side cheeks and two diagonal steel struts back to the wall (so it reads as fixed to the facade, not a
    floating slab). x = projection (scaled), y = width (scaled), z drop (scaled). Two-sided material."""
    m = Mesh(TYPE_AWNING)
    d, lip = 0.36, 0.10
    uv = [(0.0, 0.0)] * 4
    m.quad([(0.0, -0.5, 0.0), (0.0, 0.5, 0.0), (1.0, 0.5, -d), (1.0, -0.5, -d)], uv, 0)          # canopy
    m.quad([(1.0, -0.5, -d), (1.0, 0.5, -d), (1.0, 0.5, -d - lip), (1.0, -0.5, -d - lip)], uv, 1)  # drip lip
    m.tri([(0.0, -0.5, 0.0), (1.0, -0.5, -d), (1.0, -0.5, -d - lip)], [(0.0, 0.0)] * 3, 2)       # side cheeks
    m.tri([(0.0, 0.5, 0.0), (1.0, 0.5, -d - lip), (1.0, 0.5, -d)], [(0.0, 0.0)] * 3, 2)
    for y in (-0.42, 0.42):                                                                       # struts
        w = 0.012
        a0, a1 = (0.0, -0.75), (0.82, -d * 0.82 - 0.02)
        m.quad([(a0[0], y - w, a0[1]), (a1[0], y - w, a1[1]), (a1[0], y + w, a1[1]), (a0[0], y + w, a0[1])], uv, 3)
        m.quad([(a0[0], y, a0[1] - 0.02), (a1[0], y, a1[1] - 0.02), (a1[0], y, a1[1] + 0.02), (a0[0], y, a0[1] + 0.02)], uv, 3)
    return m


def prism(m, bot, top, part_side, part_top, faces=("top", "front", "back", "left", "right")):
    """Tapered box without a bottom: bot / top = (x0, x1, half width, z). Faces wound outward."""
    (x0, x1, hb, z0), (u0, u1, ht, z1) = bot, top
    B = [(x0, -hb, z0), (x1, -hb, z0), (x1, hb, z0), (x0, hb, z0)]
    T = [(u0, -ht, z1), (u1, -ht, z1), (u1, ht, z1), (u0, ht, z1)]
    c = np.mean(np.array(B + T, float), axis=0)
    quads = {"top": (T[0], T[1], T[2], T[3]), "front": (B[1], B[2], T[2], T[1]), "back": (B[3], B[0], T[0], T[3]),
             "right": (B[0], B[1], T[1], T[0]), "left": (B[2], B[3], T[3], T[2])}
    for f in faces:
        q = [np.array(v, float) for v in quads[f]]
        nrm = np.cross(q[1] - q[0], q[2] - q[0])
        if float(np.dot(nrm, np.mean(q, axis=0) - c)) < 0:
            q = q[::-1]
        m.quad([tuple(v) for v in q], [(0.0, 0.0)] * 4, part_top if f == "top" else part_side)


def wheel(m, cx, r):
    """Hexagonal tyre card in the x-z plane (two-sided material), 4 triangles."""
    v = [(cx + r * math.cos(a), 0.0, r + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 7)[:-1]]
    for k in range(1, 5):
        m.tri([v[0], v[k], v[k + 1]], [(0.0, 0.0)] * 3, 2)


def scooter_mesh(kind):
    """Parked scooter at true size (m): x = nose direction, y lateral, z up, origin on the ground at the wheelbase
    centre. Silhouette only: body + seat, floorboard, leg shield / steering column, handlebar, two tyre cards."""
    m = Mesh(TYPE_SCOOTER)
    if kind == "scooter_b":            # maxi scooter: longer, wider, taller screen
        wheel(m, -0.66, 0.23)
        wheel(m, 0.68, 0.23)
        prism(m, (-0.98, 0.0, 0.21, 0.28), (-0.92, -0.04, 0.18, 0.84), 0, 1)
        prism(m, (0.0, 0.42, 0.20, 0.24), (0.0, 0.42, 0.20, 0.36), 0, 5, ("top", "left", "right"))
        prism(m, (0.38, 0.66, 0.24, 0.28), (0.54, 0.78, 0.17, 1.0), 0, 0)
        prism(m, (0.62, 0.74, 0.36, 0.98), (0.62, 0.74, 0.36, 1.06), 3, 3, ("top", "front", "back"))
        m.quad([(0.70, -0.16, 1.0), (0.70, 0.16, 1.0), (0.58, 0.14, 1.30), (0.58, -0.14, 1.30)], [(0.0, 0.0)] * 4, 3)
    elif kind == "scooter_d":          # compact e-scooter: short, flat, tall narrow shield
        wheel(m, -0.50, 0.20)
        wheel(m, 0.54, 0.20)
        prism(m, (-0.78, 0.0, 0.16, 0.26), (-0.74, -0.04, 0.15, 0.76), 0, 1)
        prism(m, (0.0, 0.36, 0.16, 0.22), (0.0, 0.36, 0.16, 0.33), 0, 5, ("top", "left", "right"))
        prism(m, (0.33, 0.55, 0.18, 0.26), (0.46, 0.62, 0.13, 1.0), 0, 0)
        prism(m, (0.52, 0.62, 0.32, 0.98), (0.52, 0.62, 0.32, 1.05), 3, 3, ("top", "front", "back"))
    else:                              # 125 cc step-through (a); the same with a delivery top box (c)
        wheel(m, -0.56, 0.21)
        wheel(m, 0.60, 0.21)
        prism(m, (-0.86, 0.02, 0.17, 0.26), (-0.80, -0.02, 0.15, 0.80), 0, 1)
        prism(m, (0.0, 0.40, 0.17, 0.22), (0.0, 0.40, 0.17, 0.34), 0, 5, ("top", "left", "right"))
        prism(m, (0.36, 0.60, 0.21, 0.26), (0.50, 0.70, 0.15, 0.98), 0, 0)
        prism(m, (0.58, 0.70, 0.34, 0.96), (0.58, 0.70, 0.34, 1.04), 3, 3, ("top", "front", "back"))
        if kind == "scooter_c":
            prism(m, (-0.88, -0.48, 0.19, 0.80), (-0.86, -0.50, 0.18, 1.12), 4, 4)
    return m


# --------------------------------------------------------------- placement ---
def lane_ways():
    """OSM way id -> True for service ways that are plausible shop lanes (Taipei 巷 / 弄)."""
    ways, *_ = bg.load_osm()
    out = {}
    for w in ways:
        t = w["tags"]
        if t.get("highway") != "service":
            continue
        s = t.get("service")
        name = t.get("name:zh") or t.get("name") or ""
        out[w["id"]] = s == "alley" or (s is None and ("巷" in name or "弄" in name))
    return out


def rect(origin, n, t, x0, x1, half):
    """Footprint (ENU) of a prop that projects from x0 to x1 along n, +-half along t."""
    a, b = origin + n * x0, origin + n * x1
    return Polygon([a - t * half, b - t * half, b + t * half, a + t * half])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    roles = json.loads(gzip.decompress(ROLES.read_bytes()))
    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    cells = {b: [c["id"] for c in atlas["cells"] if c["bin"] == b] for b in ("v4", "v2", "sq")}
    look = {}
    with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            look[r["building_id"]] = r
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    height = {b["id"]: float(b["height_m"]) for b in wm["buildings"]}
    polys = []
    for b in wm["buildings"]:
        if b["suppressed"]:
            continue
        for p in b["polygons"]:
            g = Polygon(p["footprint_enu"], p.get("holes_enu") or [])
            g = g if g.is_valid else g.buffer(0)
            if not g.is_empty:
                polys.append(g)
    tree = STRtree(polys)
    lanes = lane_ways()

    inst = {"sign": [], "box": [], "awning": []}
    placed = defaultdict(list)          # 4 m grid cell -> [(x, y, z0, z1)] sign volumes
    stats = Counter()
    reject = Counter()

    def clear(poly):
        return not any(polys[i].intersects(poly) for i in tree.query(poly))

    def spaced(x, y, z0, z1):
        k = (int(math.floor(x / 4.0)), int(math.floor(y / 4.0)))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (px, py, a, b) in placed[(k[0] + dx, k[1] + dy)]:
                    if math.hypot(px - x, py - y) < MIN_GAP_M and a < z1 and z0 < b:
                        return False
        return True

    def put_sign(kind, cell, base, n, t, z0, height_m, width, thick, lit_p, rng, rec, role):
        yaw = math.degrees(math.atan2(n[1], n[0]))
        fp = rect(base, n, t, 0.03, width * (1.0 + STANDOFF), thick / 2 + 0.02)
        if not clear(fp):
            reject[kind + "_collides_building"] += 1
            return False
        cx, cy = base + n * width * (0.5 + STANDOFF)
        if not spaced(cx, cy, z0, z0 + height_m):
            reject[kind + "_too_close"] += 1
            return False
        k = (int(math.floor(cx / 4.0)), int(math.floor(cy / 4.0)))
        placed[k].append((cx, cy, z0, z0 + height_m))
        lit = 1 if rng.random() < lit_p else 0
        fade = min(3, int(rec["weather"] / 255.0 * 2.6 + rng.random() * 1.4))
        inst[kind].append({"e": round(float(base[0]), 3), "n": round(float(base[1]), 3), "z": round(z0, 3),
                           "yaw": round(yaw, 2), "sx": round(width, 3), "sy": round(thick, 3),
                           "sz": round(height_m, 3), "v": int(cell + 64 * lit + 128 * fade)})
        stats[f"{kind}_role{role}"] += 1
        stats[f"{kind}_lit"] += lit
        return True

    for b in sorted(roles["buildings"], key=lambda x: x["building_id"]):
        bid = b["building_id"]
        rec = look[bid]
        arch = rec["archetype"]
        if arch in (ARCH_CIVIC, ARCH_SCHOOL) or rec["flags"] & 8:
            continue
        fh = float(rec["floor_h"])
        H = height[bid]
        g0 = float(props[bid].get("ground_elev_m") or 0.0)
        core = bool(rec["flags"] & 1)
        used_cells = set()
        for e in b["edges"]:
            role = e["role"]
            p0, p1 = np.array(e["p0"], float), np.array(e["p1"], float)
            L = float(np.hypot(*(p1 - p0)))
            if L < 2.0 * END_CLEAR_M + 0.8:
                continue
            tdir = (p1 - p0) / L
            a = math.radians(e["normal_deg"])
            n = np.array([math.cos(a), math.sin(a)])
            rng = edge_rng(bid, e["part"], e["edge"])
            w_arch = ARCH_W.get(arch, 0.0) * (CORE_W if core else 1.0)

            def pick(binname):
                pool = [c for c in cells[binname] if c not in used_cells] or cells[binname]
                c = rng.choice(pool)
                used_cells.add(c)
                return c

            if role >= 5 and arch in ARCH_W:
                # ---- awnings: practical canopies over shop units (old stock only)
                if arch in OLD:
                    t = END_CLEAR_M
                    zrun = fh * rng.uniform(0.96, 1.04)          # one canopy line per frontage, stepped per shop
                    while t < L - END_CLEAR_M - 1.5:
                        unit = rng.uniform(3.0, 5.5)
                        w = min(unit - rng.uniform(0.08, 0.35), L - END_CLEAR_M - t)
                        if w >= 1.5 and rng.random() < AWNING_P[role] * (1.0 if arch != ARCH_HUAXIA else 0.8) \
                                * (0.5 if core else 1.0):
                            proj = rng.uniform(0.5, 0.9)
                            ztop = g0 + max(2.7, zrun + rng.choice((0.0, 0.0, -0.15, 0.15)))
                            mid = p0 + tdir * (t + w / 2)
                            fp = rect(mid, n, tdir, 0.03, proj, w / 2)
                            if clear(fp):
                                colour = rng.choices(range(8), AWNING_COLOURS)[0]
                                fade = min(3, int(rec["weather"] / 255.0 * 2.4 + rng.random() * 1.6))
                                style = 1 if rng.random() < 0.3 else 0          # 0 corrugated sheet, 1 polycarbonate / fabric
                                inst["awning"].append({"e": round(float(mid[0]), 3), "n": round(float(mid[1]), 3),
                                                       "z": round(ztop, 3), "yaw": round(math.degrees(a), 2),
                                                       "sx": round(proj, 3), "sy": round(w, 3),
                                                       "sz": round(rng.uniform(0.8, 1.2), 3),
                                                       "v": colour + 8 * fade + 32 * style})
                                stats[f"awning_role{role}"] += 1
                            else:
                                reject["awning_collides_building"] += 1
                        t += unit
                # ---- vertical blades
                spacing = BLADE_SPACING[role] / max(w_arch, 1e-3)
                t = END_CLEAR_M + rng.uniform(0.0, spacing)
                while t < L - END_CLEAR_M:
                    base = p0 + tdir * t
                    wide = rng.random() < 0.22
                    hs = rng.uniform(2.0, 2.8) if wide else rng.uniform(2.6, 5.2)
                    z0 = fh * rng.uniform(1.12, 1.45)
                    if z0 + hs > H - 0.6:
                        hs = H - 0.6 - z0
                    if hs >= (1.9 if wide else 2.2):
                        width = hs / (2.0 if wide else 4.0)
                        put_sign("sign", pick("v2" if wide else "v4"), base, n, tdir, g0 + z0, hs, width, 0.16,
                                 LIT_P[role], rng, rec, role)
                    else:
                        reject["sign_building_too_low"] += 1
                    t += spacing * rng.uniform(0.6, 1.4)
                # ---- small projecting boxes, hung lower (above the awning line)
                spacing = BOX_SPACING[role] / max(w_arch, 1e-3)
                t = END_CLEAR_M + rng.uniform(0.0, spacing)
                while t < L - END_CLEAR_M:
                    s = rng.uniform(0.65, 0.95)
                    z0 = fh * rng.uniform(1.0, 1.5)
                    if z0 + s < H - 0.4:
                        put_sign("box", pick("sq"), p0 + tdir * t, n, tdir, g0 + z0, s, s, 0.28, LIT_P[role], rng,
                                 rec, role)
                    t += spacing * rng.uniform(0.6, 1.4)
            elif role in (3, 4):
                # residential street walls: never a large sign; rare small box on old stock / towers
                p = {ARCH_LOW: 0.10, ARCH_WALKUP: 0.10, ARCH_HUAXIA: 0.08, ARCH_RESTOWER: 0.12,
                     ARCH_OFFICE: 0.03}.get(arch, 0.0) * (CORE_W if core else 1.0) * min(1.0, L / 12.0)
                if rng.random() < p:
                    s = rng.uniform(0.65, 0.9)
                    z0 = fh * rng.uniform(0.75, 1.1) if arch in (ARCH_RESTOWER, ARCH_OFFICE) else fh * rng.uniform(1.0, 1.4)
                    if z0 + s < H - 0.4:
                        put_sign("box", pick("sq"), p0 + tdir * rng.uniform(END_CLEAR_M, L - END_CLEAR_M), n, tdir,
                                 g0 + z0, s, s, 0.28, LIT_P[role], rng, rec, role)
            elif role == 2:
                # service ways: only real lanes (巷 / 弄 alleys) of old stock, sparse small boxes; access ways none
                if not lanes.get(e["road_id"], False):
                    stats["service_access_edges_skipped"] += 1
                    continue
                stats["lane_edges"] += 1
                if arch not in OLD:
                    continue
                t = END_CLEAR_M + rng.uniform(0.0, LANE_BOX_SPACING)
                while t < L - END_CLEAR_M:
                    if rng.random() < 0.5 * (CORE_W if core else 1.0):
                        s = rng.uniform(0.6, 0.85)
                        z0 = fh * rng.uniform(1.0, 1.4)
                        if z0 + s < H - 0.4:
                            put_sign("box", pick("sq"), p0 + tdir * t, n, tdir, g0 + z0, s, s, 0.26, LIT_P[2], rng,
                                     rec, 2)
                    t += LANE_BOX_SPACING * rng.uniform(0.7, 1.3)

    # ---- parked scooters: only in the painted bays of the curb layer (Taipei Street Reality v0C)
    curb = json.loads(gzip.decompress(CURB.read_bytes()))
    hf = bg.Heightfield()
    from PIL import Image
    gtex = np.asarray(Image.open(LOOK / "ground/xinyi_ground_2048.png")).astype(np.float32) / 255.0
    ctex = np.asarray(Image.open(LOOK / "ground/xinyi_campus_2048.png")).astype(np.float32) / 255.0

    def on_sidewalk(pts):
        """Any point on raised-sidewalk ground as the ground shader sees it (sd > 0.1 m on a sidewalk side)."""
        res = gtex.shape[0]
        for e, n in pts:
            fx = (e - bg.E0) / (bg.E1 - bg.E0) * res - 0.5
            fy = (bg.N1 - n) / (bg.N1 - bg.N0) * res - 0.5
            x0, y0 = int(math.floor(fx)), int(math.floor(fy))
            tx, ty = fx - x0, fy - y0
            w = ((y0, x0, (1 - tx) * (1 - ty)), (y0, x0 + 1, tx * (1 - ty)), (y0 + 1, x0, (1 - tx) * ty),
                 (y0 + 1, x0 + 1, tx * ty))
            sd = (sum(gtex[y, x, 0] * k for y, x, k in w) - 0.5) * 24.0
            if sd > 0.1 and sum(ctex[y, x, 3] * k for y, x, k in w) > 0.85:
                return True
        return False
    for k in SCOOTER_KINDS:
        inst[k] = []
    rows = curb["rows"]
    for bay in curb["bays"]:
        row = rows[bay["row"]]
        rng = edge_rng("scooter", row["id"], bay["k"])
        if rng.random() >= row["fill"] * ROLE_FILL.get(row["role"], 0.9):
            stats["scooter_bay_empty"] += 1
            continue
        kind = rng.choices(SCOOTER_KINDS, SCOOTER_KIND_W)[0]
        ax = math.radians(bay["yaw"])
        a_dir = np.array([math.cos(ax), math.sin(ax)])        # bay axis, kerb -> carriageway
        t_dir = np.array([-a_dir[1], a_dir[0]])
        c = np.array([bay["e"], bay["n"]]) + t_dir * rng.uniform(-0.15, 0.15) + a_dir * rng.uniform(-0.08, 0.08)
        yaw = bay["yaw"] + (0.0 if rng.random() < NOSE_OUT_P else 180.0) + rng.uniform(-8.0, 8.0)
        sc = rng.uniform(0.97, 1.0)
        half_len, half_w = (1.0 if kind == "scooter_b" else 0.9) * sc, 0.36 * sc
        yr = math.radians(yaw)
        fx, fy = np.array([math.cos(yr), math.sin(yr)]), np.array([-math.sin(yr), math.cos(yr)])
        corners = lambda c: [tuple(c + fx * dx * half_len + fy * dy * half_w) for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        if on_sidewalk(corners(c)):
            c = c + a_dir * 0.1                                # nudge toward the carriageway
            if on_sidewalk(corners(c)):
                reject["scooter_on_raised_sidewalk"] += 1
                continue
        fp = Polygon(corners(c))
        if not clear(fp):
            reject["scooter_collides_building"] += 1
            continue
        colour = rng.choices(range(8), SCOOTER_COLOUR_W)[0]
        v = colour + 8 * rng.randint(0, 3) + 32 * (1 if rng.random() < 0.6 else 0)
        inst[kind].append({"e": round(float(c[0]), 3), "n": round(float(c[1]), 3),
                           "z": round(float(hf([c[0]], [c[1]])[0]), 3), "yaw": round(yaw, 2),
                           "sx": round(sc, 3), "sy": round(sc, 3), "sz": round(sc, 3), "v": int(v)})
        stats[f"scooter_role{row['role']}"] += 1
        stats[f"scooter_class_{row['class']}"] += 1

    sm, am = sign_mesh(), awning_mesh()
    sb, st = sm.write(OUT / "street_sign.glb", "SM_XinyiStreetSign")
    ab, at = am.write(OUT / "street_awning.glb", "SM_XinyiStreetAwning")
    scooter_meshes = {}
    for k in SCOOTER_KINDS:
        bnd, tri = scooter_mesh(k).write(OUT / ("street_%s.glb" % k), "SM_XinyiStreet" + k.title().replace("_", ""))
        scooter_meshes[k] = {"mesh": "street_%s.glb" % k, "triangles": tri, "expected_ue_local_bounds": bnd,
                             "used_by": [k]}
    doc = {"schema": "acw.street_instances/0", "variants": {"sign": SIGN_VARIANTS, "box": SIGN_VARIANTS,
                                                            "awning": AWNING_VARIANTS,
                                                            **{k: SCOOTER_VARIANTS for k in SCOOTER_KINDS}},
           "types": inst}
    (OUT / "street_instances.json").write_text(json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n")
    report = {
        "status": "PASS_STREET_IDENTITY",
        "meshes": {"sign": {"mesh": "street_sign.glb", "triangles": st, "expected_ue_local_bounds": sb,
                            "used_by": ["sign", "box"]},
                   "awning": {"mesh": "street_awning.glb", "triangles": at, "expected_ue_local_bounds": ab,
                              "used_by": ["awning"]},
                   **scooter_meshes},
        "instances": {k: len(v) for k, v in inst.items()},
        "instance_triangles": {"sign": len(inst["sign"]) * st, "box": len(inst["box"]) * st,
                               "awning": len(inst["awning"]) * at,
                               **{k: len(inst[k]) * scooter_meshes[k]["triangles"] for k in SCOOTER_KINDS}},
        "curb_segments_sha256": hashlib.sha256(gzip.decompress(CURB.read_bytes())).hexdigest(),
        "stats": dict(sorted(stats.items())), "rejected": dict(sorted(reject.items())),
        "rules": {"blade_spacing_m": BLADE_SPACING, "box_spacing_m": BOX_SPACING, "awning_p": AWNING_P,
                  "arch_weight": {str(k): v for k, v in ARCH_W.items()}, "core_weight": CORE_W, "lit_p": LIT_P,
                  "lane_box_spacing_m": LANE_BOX_SPACING, "end_clear_m": END_CLEAR_M, "min_gap_m": MIN_GAP_M},
        "atlas_sha256": atlas["sha256"],
        "sha256": hashlib.sha256((OUT / "street_instances.json").read_bytes()).hexdigest(),
    }
    (OUT / "street.report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("instances", "instance_triangles", "rejected")}))
    print(json.dumps(report["stats"]))


if __name__ == "__main__":
    main()
