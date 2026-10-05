"""Generate Taipei rooftop clutter as instanced props on the real roof polygons.

The WFS gives every building a flat roof. From an aircraft the Taipei roofscape
is anything but: 頂樓加蓋 sheet-metal sheds, stainless water tanks on stands,
solar water heaters, TV antennas, AC condensers, and on towers machine rooms,
cooling towers, window-cleaning cranes and red aviation obstruction lights.

Placement is deterministic per building (seeded by building id), constrained to
the accepted footprint polygon (inset) at the building's surveyed top elevation,
oriented to the footprint's minimum rotated rectangle. Buildings are not edited.

Rooftop identity pass v0: the old residential stock (walk-ups, huaxia, low shop-houses) carries the
Taipei roofscape - 頂樓加蓋 sheet-metal rooms with gable / barrel / mono-pitch roofs over much of the
roof, mixed heights, stair bulkheads with tanks on top, solar heaters, AC rows along the parapet - in a
sun-faded, weighted sheet-metal palette (blue-grey, oxidised red, faded / teal green, galvanised,
off-white). Residential towers get a little, offices / podiums / civic none (machine rooms, cooling).
Schools (ARCH_SCHOOL, School & Campus Identity v0A) get tanks, an occasional stair bulkhead / solar
heater and no additions; every archetype is routed explicitly (unknown ones fail closed).
Archetype + planned-core flag + weathering (age proxy) + roof size drive the rules.

Outputs (unreal/Saved/XinyiLook/rooftops/):
  props_<type>.glb          one small mesh per prop type (TEXCOORD_2 packed data:
                            R = prop type id, G = part id)
  rooftop_instances.json    {type: [{e,n,z,yaw,sx,sy,sz,v}]}, v in 0..VARIANTS-1 (per-instance
                            custom data = (v + 0.5) / VARIANTS). Sheet-metal types: v = roof colour
                            index * 16 + wall colour index (SHEET_NAMES palette; colours in
                            xinyi_city.hlsl xc_sheet16); other types: v // 64 = their 4-way variant.
  rooftops.report.json
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
LOOK = REPO / "unreal/Saved/XinyiLook"
OUT = LOOK / "rooftops"

TYPES = ["shed", "tank", "solar", "antenna", "ac", "cooling", "machine", "bmu", "avlight",
         "addition", "barrel", "leanto", "bulkhead"]
# 10 is the street lamp (build_ground.py), which shares the props material
TYPE_ID = {"shed": 1, "tank": 2, "solar": 3, "antenna": 4, "ac": 5, "cooling": 6, "machine": 7, "bmu": 8,
           "avlight": 9, "addition": 11, "barrel": 12, "leanto": 13, "bulkhead": 14}
ID_TYPE = {v: k for k, v in TYPE_ID.items()}
VARIANTS = 256
# Taipei sheet-metal palette (index -> name; colours live in xinyi_city.hlsl xc_sheet16). Weights follow
# aerial photos of old Taipei fabric: blue-grey and galvanised dominate, then oxidised red, faded / teal
# green and off-white; saturated colours are rare. Planned-core roofs skew neutral.
SHEET_NAMES = ["bluegrey", "fadedblue", "lightbluegrey", "brickred", "rustred", "redbrown", "fadedgreen",
               "tealgreen", "greengrey", "galvanised", "galvdark", "offwhite", "beige", "cream", "fadedteal",
               "rustgalv"]
SHEET_W_OLD = [8, 10, 7, 7, 7, 4, 6, 6, 3, 8, 4, 8, 4, 4, 5, 3]
SHEET_W_CORE = [8, 4, 8, 2, 1, 1, 3, 2, 4, 16, 8, 12, 7, 8, 3, 1]
WALL_W = [4, 2, 4, 1, 1, 1, 2, 1, 2, 12, 6, 16, 10, 12, 2, 2]       # walls: mostly light / neutral
ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM, ARCH_CIVIC, ARCH_SCHOOL = range(8)
FLAG_ROOFTOP = 8
# School roofs (School & Campus Identity v0A) emit only these prop types, into the ordinary HISMs
SCHOOL_PROP_TYPES = {"tank", "bulkhead", "solar"}
SCHOOL_WALL_W = [0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 8, 2, 6, 0, 0]   # bulkheads: off-white / cream / grey only


# ------------------------------------------------------------------ meshes ---
class MB:
    def __init__(self, tid):
        self.tid = tid
        self.v, self.f, self.c = [], [], []

    def box(self, cx, cy, z0, sx, sy, sz, part=0):
        x0, x1, y0, y1, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, z0 + sz
        faces = [
            [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],  # top
            [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],  # bottom
            [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
            [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
        ]
        for q in faces:
            self.quad(q, part)

    def quad(self, q, part):
        b = len(self.v)
        self.v += q
        self.c += [(self.tid, part, 0, 255)] * 4
        self.f += [(b, b + 1, b + 2), (b, b + 2, b + 3)]

    def cyl(self, cx, cy, z0, r, h, n=10, part=0, cap=True):
        a = [2 * math.pi * i / n for i in range(n)]
        for i in range(n):
            j = (i + 1) % n
            p0 = (cx + r * math.cos(a[i]), cy + r * math.sin(a[i]))
            p1 = (cx + r * math.cos(a[j]), cy + r * math.sin(a[j]))
            self.quad([(p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z0 + h), (p0[0], p0[1], z0 + h)], part)
            if cap:
                b = len(self.v)
                self.v += [(cx, cy, z0 + h), (p0[0], p0[1], z0 + h), (p1[0], p1[1], z0 + h)]
                self.c += [(self.tid, part, 0, 255)] * 3
                self.f += [(b, b + 1, b + 2)]

    def write(self, path):
        v = np.asarray(self.v, dtype=np.float64)
        f = np.asarray(self.f, dtype=np.int64)
        game = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype(np.float32)
        fn = np.cross(game[f[:, 1]] - game[f[:, 0]], game[f[:, 2]] - game[f[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
        nrm = np.zeros_like(game)
        for k in range(3):
            nrm[f[:, k]] = fn
        write_glb(path, [{"name": "XinyiRoofProp", "positions": game, "normals": nrm,
                          "uv2": pack_rgba8(np.asarray(self.c, np.uint8)), "indices": f.astype(np.uint32),
                          "base_color": [0.6, 0.6, 0.6, 1.0]}], mesh_name="SM_XinyiRoof_" + ID_TYPE[self.tid])
        return ue_local_bounds_cm(game), len(f)


def build_meshes():
    OUT.mkdir(parents=True, exist_ok=True)
    meshes = {}
    # unit shed: 1 x 1 footprint, 1 m tall walls + shallow gable ridge; scaled per instance
    m = MB(TYPE_ID["shed"])
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    m.quad([(-0.52, -0.52, 1.0), (0.52, -0.52, 1.0), (0.52, 0.0, 1.12), (-0.52, 0.0, 1.12)], 1)
    m.quad([(0.52, 0.52, 1.0), (-0.52, 0.52, 1.0), (-0.52, 0.0, 1.12), (0.52, 0.0, 1.12)], 1)
    meshes["shed"] = m
    # stainless water tank on a steel stand (36 tris: the stand reads as one frame)
    m = MB(TYPE_ID["tank"])
    m.box(0, 0, 0, 1.1, 1.1, 1.2, part=1)
    m.cyl(0, 0, 1.2, 0.62, 1.5, n=8, part=0)
    meshes["tank"] = m
    # solar water heater: tilted collector + horizontal tank
    m = MB(TYPE_ID["solar"])
    m.quad([(-1.0, -0.9, 0.3), (1.0, -0.9, 0.3), (1.0, 0.6, 1.3), (-1.0, 0.6, 1.3)], 0)
    m.quad([(1.0, -0.9, 0.25), (-1.0, -0.9, 0.25), (-1.0, 0.6, 1.25), (1.0, 0.6, 1.25)], 1)
    m.box(0, 0.75, 1.1, 2.1, 0.45, 0.45, part=1)
    m.box(0, -0.9, 0, 2.0, 0.06, 0.3, part=1)
    meshes["solar"] = m
    # TV antenna: mast + two crossbars
    m = MB(TYPE_ID["antenna"])
    m.box(0, 0, 0, 0.06, 0.06, 4.0, part=0)
    m.box(0, 0, 3.2, 1.6, 0.04, 0.04, part=0)
    m.box(0, 0, 3.7, 1.1, 0.04, 0.04, part=0)
    meshes["antenna"] = m
    # AC condenser
    m = MB(TYPE_ID["ac"])
    m.box(0, 0, 0, 0.9, 0.35, 0.7, part=0)
    m.quad([(-0.3, -0.176, 0.12), (0.3, -0.176, 0.12), (0.3, -0.176, 0.6), (-0.3, -0.176, 0.6)], 1)
    meshes["ac"] = m
    # cooling tower (towers / podiums)
    m = MB(TYPE_ID["cooling"])
    m.cyl(0, 0, 0, 1.6, 2.8, n=12, part=0)
    m.cyl(0, 0, 2.8, 1.2, 0.5, n=12, part=1)
    meshes["cooling"] = m
    # machine room / stair core (unit box)
    m = MB(TYPE_ID["machine"])
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    m.box(0, 0, 1.0, 1.04, 1.04, 0.04, part=1)
    meshes["machine"] = m
    # window-cleaning crane (BMU) on office towers
    m = MB(TYPE_ID["bmu"])
    m.box(0, 0, 0, 1.2, 1.2, 2.2, part=0)
    m.box(3.0, 0, 2.0, 7.0, 0.35, 0.45, part=0)
    m.box(6.3, 0, 1.4, 0.2, 0.2, 0.6, part=1)
    meshes["bmu"] = m
    # aviation obstruction light (emissive red)
    m = MB(TYPE_ID["avlight"])
    m.box(0, 0, 0, 0.1, 0.1, 1.2, part=1)
    m.box(0, 0, 1.2, 0.35, 0.35, 0.35, part=0)
    meshes["avlight"] = m
    # 頂樓加蓋 room, gable sheet roof: unit 1 x 1 x 1 walls (part 0, wall colour), ridge along x with
    # 0.06 eaves overhang and 0.16 rise (part 1, roof colour); gable ends in wall colour
    tid = TYPE_ID["addition"]
    m = MB(tid)
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    o, rz = 0.56, 0.16
    m.quad([(-o, -o, 0.97), (o, -o, 0.97), (o, 0.0, 1.0 + rz), (-o, 0.0, 1.0 + rz)], 1)
    m.quad([(o, o, 0.97), (-o, o, 0.97), (-o, 0.0, 1.0 + rz), (o, 0.0, 1.0 + rz)], 1)
    for x in (-0.5, 0.5):
        b0 = len(m.v)
        m.v += [(x, -0.5, 1.0), (x, 0.5, 1.0), (x, 0.0, 1.0 + rz)]
        m.c += [(tid, 0, 0, 255)] * 3
        m.f += [(b0, b0 + 1, b0 + 2) if x > 0 else (b0, b0 + 2, b0 + 1)]
    meshes["addition"] = m
    # 頂樓加蓋 room, barrel (curved) sheet roof along x: 6-segment arc, rise 0.22
    tid = TYPE_ID["barrel"]
    m = MB(tid)
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    arc = [(-0.55 + 1.1 * k / 6, 0.98 + 0.24 * math.sin(math.pi * k / 6)) for k in range(7)]
    for k in range(6):
        (y0, z0), (y1, z1) = arc[k], arc[k + 1]
        m.quad([(-0.54, y0, z0), (-0.54, y1, z1), (0.54, y1, z1), (0.54, y0, z0)], 1)
    for x in (-0.5, 0.5):
        for k in range(6):
            (y0, z0), (y1, z1) = arc[k], arc[k + 1]
            b0 = len(m.v)
            m.v += [(x, 0.0, 1.0), (x, max(-0.5, min(0.5, y0)), max(1.0, z0)), (x, max(-0.5, min(0.5, y1)), max(1.0, z1))]
            m.c += [(tid, 0, 0, 255)] * 3
            m.f += [(b0, b0 + 2, b0 + 1) if x > 0 else (b0, b0 + 1, b0 + 2)]
    meshes["barrel"] = m
    # open mono-pitch awning on four posts (drying / roof-garden cover): sheet from 0.8 up to 1.0
    tid = TYPE_ID["leanto"]
    m = MB(tid)
    m.quad([(-0.52, -0.52, 0.80), (0.52, -0.52, 0.80), (0.52, 0.52, 1.0), (-0.52, 0.52, 1.0)], 1)
    for x in (-0.47, 0.47):
        for y in (-0.47, 0.47):
            m.box(x, y, 0.0, 0.035, 0.035, 0.8 + 0.2 * (y + 0.5), part=2)
    meshes["leanto"] = m
    # stair / tank bulkhead (樓梯間): painted concrete box, slab cap, door
    tid = TYPE_ID["bulkhead"]
    m = MB(tid)
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    m.box(0, 0, 1.0, 1.06, 1.06, 0.07, part=3)
    m.quad([(-0.18, -0.502, 0.0), (0.18, -0.502, 0.0), (0.18, -0.502, 0.72), (-0.18, -0.502, 0.72)], 2)
    meshes["bulkhead"] = m
    info = {}
    for t, mb in meshes.items():
        bounds, tris = mb.write(OUT / f"props_{t}.glb")
        info[t] = {"mesh": f"props_{t}.glb", "triangles": tris, "expected_ue_local_bounds": bounds}
    return info


# --------------------------------------------------------------- placement ---
def rng_for(bid):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(bid.encode()).digest()[:8], "little"))


def max_rect(inner, ang, origin, cell=0.5):
    """Largest axis-aligned rectangle (in the roof frame rotated by -ang about origin) inside `inner`,
    on a `cell` grid (maximal-rectangle histogram scan). Returns (u0, u1, v0, v1) roof-frame bounds."""
    import shapely
    R = affinity.rotate(inner, -ang, origin=tuple(origin))
    minx, miny, maxx, maxy = R.bounds
    xs = np.arange(minx + cell / 2, maxx, cell)
    ys = np.arange(miny + cell / 2, maxy, cell)
    if len(xs) < 2 or len(ys) < 2:
        return None
    gx, gy = np.meshgrid(xs, ys)
    ok = shapely.contains_xy(R, gx, gy)
    h = np.zeros(len(xs), np.int32)
    best = (0, None)
    for j in range(len(ys)):
        h = np.where(ok[j], h + 1, 0)
        stack = []
        for i in range(len(xs) + 1):
            hi = h[i] if i < len(xs) else 0
            start = i
            while stack and stack[-1][1] >= hi:
                s0, sh = stack.pop()
                a_ = sh * (i - s0)
                if a_ > best[0]:
                    best = (a_, (s0, i, j - sh + 1, j + 1))
                start = s0
            stack.append((start, hi))
    if best[1] is None:
        return None
    i0, i1, j0, j1 = best[1]
    return (minx + i0 * cell, minx + i1 * cell, miny + j0 * cell, miny + j1 * cell)


def pick(rng, w):
    w = np.asarray(w, np.float64)
    return int(rng.choice(len(w), p=w / w.sum()))


# 頂樓加蓋 rules by archetype: base probability (x0.45 in the planned core, x0.7 .. 1.3 with age), share
# of the roof's long axis the rooms cover, room typology weights (gable addition, barrel, flat shed,
# open lean-to)
ADD_RULES = {
    ARCH_WALKUP: {"p": 0.80, "cover": (0.55, 0.95), "w": [0.42, 0.24, 0.22, 0.12]},
    ARCH_LOW: {"p": 0.42, "cover": (0.40, 0.85), "w": [0.30, 0.15, 0.30, 0.25]},
    ARCH_HUAXIA: {"p": 0.42, "cover": (0.30, 0.65), "w": [0.40, 0.18, 0.30, 0.12]},
    ARCH_RESTOWER: {"p": 0.12, "cover": (0.15, 0.35), "w": [0.30, 0.05, 0.55, 0.10]},
}
SEG_TYPES = ["addition", "barrel", "shed", "leanto"]


def main():
    info = build_meshes()
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    look = {}
    with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            look[r["building_id"]] = r
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    inst = {t: [] for t in TYPES}
    stats = {"old_roof_parts": 0, "roof_parts_with_additions": 0, "additions_by_arch": {}, "core_additions": 0}
    sheet_use = [0] * 16

    school_roof = {"on": False}

    def add(t, x, y, z, yaw, sx=1.0, sy=1.0, sz=1.0, v=0):
        if school_roof["on"] and t not in SCHOOL_PROP_TYPES:
            raise RuntimeError("school roof emitted unrouted prop type %s" % t)
        inst[t].append({"e": round(x, 3), "n": round(y, 3), "z": round(z, 3), "yaw": round(yaw, 2),
                        "sx": round(sx, 3), "sy": round(sy, 3), "sz": round(sz, 3), "v": int(v)})

    def legacy_v(rng):            # 4-way variant of the original props in the top two bits of 0..255
        return int(rng.integers(0, 4)) * 64 + int(rng.integers(0, 64))

    for b in wm["buildings"]:
        if b["suppressed"] or b["id"] not in look:
            continue
        rec = look[b["id"]]
        arch = rec["archetype"]
        if rec["flags"] & FLAG_ROOFTOP or arch == ARCH_CIVIC:
            continue
        # one placement pass per record (kept as a loop to leave the body's indentation untouched)
        for arch, weather, rng in [(arch, rec["weather"], rng_for(b["id"]))]:
            school_roof["on"] = arch == ARCH_SCHOOL
            core = bool(rec["flags"] & 1)
            age = weather / 255.0          # weathering is an age proxy (old stock weathers hardest)
            p = props[b["id"]]
            top = float(p["ground_elev_m"]) + float(b["height_m"])
            H = float(b["height_m"])
            # building colour identity: one dominant sheet colour; walls mostly light / neutral
            sheet_w = SHEET_W_CORE if core else SHEET_W_OLD
            main_c = pick(rng, sheet_w)
            wall_c = main_c if rng.random() < 0.55 else pick(rng, WALL_W)
            for part in b["polygons"]:
                poly = Polygon(part["footprint_enu"], part.get("holes_enu") or [])
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 12.0:
                    continue
                inner = poly.buffer(-0.8)
                if inner.is_empty or inner.area < 4.0:
                    continue
                if inner.geom_type != "Polygon":
                    inner = max(inner.geoms, key=lambda g: g.area)
                ip = prep(inner)
                mrr = poly.minimum_rotated_rectangle
                c = np.asarray(mrr.exterior.coords)[:4]
                e1, e2 = c[1] - c[0], c[2] - c[1]
                if np.linalg.norm(e1) < np.linalg.norm(e2):
                    e1, e2 = e2, e1
                L, W = float(np.linalg.norm(e1)), float(np.linalg.norm(e2))
                u, vv = e1 / max(L, 1e-6), e2 / max(W, 1e-6)
                ang = math.degrees(math.atan2(u[1], u[0]))
                mc = np.asarray(mrr.centroid.coords[0])
                cx, cy = inner.representative_point().coords[0]
                placed = []        # (x, y, r) discs of small clutter
                blocks = []        # footprints of rooms / bulkheads: clutter keeps out, tanks may sit on top

                def free(x, y, r):
                    if any((x - px) ** 2 + (y - py) ** 2 < (r + pr) ** 2 for px, py, pr in placed):
                        return False
                    q = Point(x, y).buffer(r, 4)
                    return not any(bl.intersects(q) for bl in blocks)

                def scatter(t, n, r, near_edge=False, **kw):
                    minx, miny, maxx, maxy = inner.bounds
                    core_area = inner.buffer(-max(1.5, r * 2.5)) if near_edge else None
                    tries = 0
                    k = 0
                    while k < n and tries < n * 14:
                        tries += 1
                        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
                        if core_area is not None and not core_area.is_empty and core_area.contains(Point(x, y)):
                            continue        # AC condensers line the parapet
                        if ip.contains(Point(x, y)) and free(x, y, r):
                            placed.append((x, y, r))
                            add(t, x, y, top, ang + (90 if rng.random() < 0.5 else 0), v=legacy_v(rng), **kw)
                            k += 1
                    return k

                def fit(ccx, ccy, a, bb, shrink=0.85, tries=5):
                    for _ in range(tries):
                        r_ = affinity.rotate(box(ccx - a / 2, ccy - bb / 2, ccx + a / 2, ccy + bb / 2), ang, origin=(ccx, ccy))
                        if inner.contains(r_):
                            return a, bb, r_
                        a *= shrink
                        bb *= shrink
                    return None

                def tank_cluster(n, z0, x0, y0, spread):
                    for k in range(n):
                        x = x0 + (k - (n - 1) / 2) * 1.3 * u[0] + rng.normal(0, spread) * vv[0]
                        y = y0 + (k - (n - 1) / 2) * 1.3 * u[1] + rng.normal(0, spread) * vv[1]
                        add("tank", x, y, z0, ang, v=legacy_v(rng))

                area = inner.area
                if arch in (ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER):
                    if arch != ARCH_RESTOWER:
                        stats["old_roof_parts"] += 1
                    rule = ADD_RULES[arch]
                    p_add = rule["p"] * (0.45 if core else 1.0) * (0.7 + 0.6 * age)
                    covered = 0.0
                    if area > 12 and rng.random() < p_add:
                        # 頂樓加蓋: 1-3 rooms in a row inside the roof's largest inscribed rectangle (roof frame:
                        # x along the long axis), starting at one end; fits irregular footprints by construction
                        mr = max_rect(inner, ang, mc)
                        any_seg = False
                        stats.setdefault("attempts", {}).setdefault(str(arch), 0)
                        stats["attempts"][str(arch)] += 1
                        if mr is not None and (mr[1] - mr[0]) >= 2.6 and (mr[3] - mr[2]) >= 2.6:
                            ru0, ru1, rv0, rv1 = mr
                            RL, RW = ru1 - ru0, rv1 - rv0
                            along_u = RL >= RW
                            long_, short_ = (RL, RW) if along_u else (RW, RL)
                            Lc = max(2.4, long_ * rng.uniform(*rule["cover"]))
                            nseg = 1 if Lc < 9 else (1 + int(rng.random() < 0.55) + int(Lc > 20 and rng.random() < 0.5))
                            start = 0.0 if rng.random() < 0.5 else long_ - Lc
                            seg_h0 = rng.uniform(2.5, 3.0)
                            pos = start
                            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
                            for sl in rng.dirichlet([2.0] * nseg) * Lc:
                                s0 = pos
                                pos += sl
                                if sl < 2.6:
                                    continue
                                t = SEG_TYPES[pick(rng, rule["w"])]
                                wfrac = rng.uniform(0.8, 1.0) if t != "leanto" else rng.uniform(0.6, 0.95)
                                sw = max(2.6, short_ * wfrac)
                                if sw > short_ or sl * sw < 8.0:
                                    continue            # too small for a room: would read as a thin prism
                                off = rng.uniform(0.0, 1.0) * (short_ - sw)
                                # roof-frame centre -> world
                                if along_u:
                                    fu, fv, a_, b_, yaw = ru0 + s0 + sl / 2, rv0 + off + sw / 2, sl, sw, ang
                                else:
                                    fu, fv, a_, b_, yaw = ru0 + off + sw / 2, rv0 + s0 + sl / 2, sl, sw, ang + 90.0
                                ccx = mc[0] + (fu - mc[0]) * ca - (fv - mc[1]) * sa
                                ccy = mc[1] + (fu - mc[0]) * sa + (fv - mc[1]) * ca
                                r_ = affinity.rotate(box(ccx - a_ / 2, ccy - b_ / 2, ccx + a_ / 2, ccy + b_ / 2), yaw, origin=(ccx, ccy))
                                h = (seg_h0 + rng.uniform(-0.35, 0.45)) if t != "leanto" else rng.uniform(2.2, 2.6)
                                # patchwork: most rooms share the building's colour, some were re-roofed in another
                                rc = main_c if rng.random() < 0.68 else pick(rng, sheet_w)
                                wc = wall_c if t != "leanto" else rc
                                sheet_use[rc] += 1
                                add(t, ccx, ccy, top, yaw, a_ * 0.97, b_, h, v=rc * 16 + wc)
                                blocks.append(r_)
                                covered += a_ * b_
                                any_seg = True
                                # a second, smaller storey on a few walk-up rooms (mixed roof heights)
                                if arch == ARCH_WALKUP and t in ("addition", "shed") and a_ > 5 and rng.random() < 0.09:
                                    rc2 = rc if rng.random() < 0.5 else pick(rng, sheet_w)
                                    add("shed", ccx, ccy, top + h + 0.1, yaw, a_ * rng.uniform(0.35, 0.55),
                                        b_ * rng.uniform(0.5, 0.8), rng.uniform(2.2, 2.6), v=rc2 * 16 + wc)
                        else:
                            stats.setdefault("fit_fail", {}).setdefault(str(arch), 0)
                            stats["fit_fail"][str(arch)] += 1
                        if any_seg:
                            stats["roof_parts_with_additions"] += 1
                            key = ["low", "walkup", "huaxia", "res_tower"][arch]
                            stats["additions_by_arch"][key] = stats["additions_by_arch"].get(key, 0) + 1
                            stats["core_additions"] += int(core)
                    cover = covered / max(area, 1.0)
                    # stair bulkhead on walk-ups / huaxia / towers, unless the rooms already fill the roof
                    if arch != ARCH_LOW and cover < 0.7 and area > 30:
                        bw = rng.uniform(2.6, 3.4) if arch == ARCH_WALKUP else rng.uniform(3.4, 5.0)
                        bd = rng.uniform(3.4, 4.6) if arch == ARCH_WALKUP else rng.uniform(4.0, 6.0)
                        bh = rng.uniform(2.6, 3.0) if arch != ARCH_RESTOWER else rng.uniform(3.2, 4.2)
                        for _ in range(8):
                            ss, tt = rng.uniform(-0.25, 0.25), rng.uniform(-0.3, 0.3)
                            bx = mc[0] + u[0] * ss * L + vv[0] * tt * W
                            by = mc[1] + u[1] * ss * L + vv[1] * tt * W
                            f = fit(bx, by, bw, bd, 0.9, 3)
                            if f is not None and min(f[0], f[1]) < 2.2:
                                f = None            # no chimney-thin bulkheads on tiny roof parts
                            if f is not None and not any(f[2].intersects(bl) for bl in blocks):
                                a_, b_, r_ = f
                                add("bulkhead", bx, by, top, ang, a_, b_, bh, v=int(rng.integers(0, 16)) * 16 + pick(rng, WALL_W))
                                blocks.append(r_)
                                # tanks on the bulkhead roof: the classic Taipei rooftop silhouette
                                if rng.random() < (0.55 if arch == ARCH_WALKUP else 0.4):
                                    tank_cluster(1 + int(rng.random() < 0.5) + int(a_ > 4.0 and rng.random() < 0.25),
                                                 top + bh + 0.07, bx, by, 0.15)
                                break
                    # tank clusters on the roof, solar heaters, antennas, AC rows along the parapet
                    nt = (int(rng.random() < 0.75) + int(area > 180) + int(rng.random() < 0.2)) if arch != ARCH_RESTOWER else (1 + int(area > 400))
                    minx, miny, maxx, maxy = inner.bounds
                    for _ in range(nt):
                        for _t in range(10):
                            x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
                            if ip.contains(Point(x, y)) and free(x, y, 1.6):
                                n = 1 + int(rng.random() < 0.3) + int(rng.random() < 0.08)
                                tank_cluster(n, top, x, y, 0.1)
                                placed.append((x, y, 0.8 * n))
                                break
                    if arch != ARCH_RESTOWER:
                        if rng.random() < (0.35 if not core else 0.15):
                            scatter("solar", 1, 1.2)
                        if rng.random() < 0.45:
                            scatter("antenna", 1, 0.5, sz=rng.uniform(0.7, 1.2))
                        scatter("ac", int(rng.integers(0, 4)) + int(area / 120), 0.5, near_edge=True)
                    else:
                        if not blocks:
                            mw = min(12.0, math.sqrt(area) * 0.4)
                            add("machine", cx, cy, top, ang, mw, mw * rng.uniform(0.6, 1.0), rng.uniform(3.0, 5.0), v=legacy_v(rng))
                            placed.append((cx, cy, mw * 0.6))
                        scatter("cooling", int(area > 500), 1.8)
                        scatter("antenna", int(rng.integers(0, 3)), 0.5, sz=rng.uniform(1.5, 3.0))
                        scatter("ac", int(area / 150), 0.5, near_edge=True)
                elif arch == ARCH_SCHOOL:
                    # classroom-wing roofs (School & Campus Identity v0A): bare concrete / green waterproofing in
                    # the shader, elevated water tanks, an occasional stair bulkhead and solar heater. No 頂樓加蓋
                    # rooms, AC rows, antennas or podium chillers.
                    stats["school_roof_parts"] = stats.get("school_roof_parts", 0) + 1
                    if area > 120 and rng.random() < 0.5:
                        bw, bd, bh = rng.uniform(3.4, 4.6), rng.uniform(4.0, 6.0), rng.uniform(2.8, 3.3)
                        for _ in range(8):
                            ss, tt = rng.uniform(-0.35, 0.35), rng.uniform(-0.2, 0.2)
                            bx = mc[0] + u[0] * ss * L + vv[0] * tt * W
                            by = mc[1] + u[1] * ss * L + vv[1] * tt * W
                            f = fit(bx, by, bw, bd, 0.9, 3)
                            if f is not None and min(f[0], f[1]) >= 2.6:
                                a_, b_, r_ = f
                                add("bulkhead", bx, by, top, ang, a_, b_, bh, v=pick(rng, SCHOOL_WALL_W) * 16 + pick(rng, SCHOOL_WALL_W))
                                blocks.append(r_)
                                if rng.random() < 0.5:
                                    tank_cluster(1 + int(rng.random() < 0.5), top + bh + 0.07, bx, by, 0.15)
                                break
                    minx, miny, maxx, maxy = inner.bounds
                    for _ in range(int(area > 60) + int(area > 400) + int(area > 1200)):
                        for _t in range(10):
                            x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
                            if ip.contains(Point(x, y)) and free(x, y, 2.0):
                                n = 2 + int(rng.random() < 0.4)
                                tank_cluster(n, top, x, y, 0.1)
                                placed.append((x, y, 0.9 * n))
                                break
                    if area > 200 and rng.random() < 0.2:
                        scatter("solar", 1, 1.2)
                elif arch == ARCH_OFFICE:
                    # premium / modern towers stay clean: machine room, cooling, window-cleaning crane
                    mw = min(12.0, math.sqrt(area) * 0.45)
                    add("machine", cx, cy, top, ang, mw, mw * rng.uniform(0.6, 1.0), rng.uniform(3.0, 5.0), v=legacy_v(rng))
                    placed.append((cx, cy, mw * 0.6))
                    scatter("cooling", 1 + int(area > 600), 1.8)
                    if area > 300 and rng.random() < 0.6:
                        scatter("bmu", 1, 2.0)
                    scatter("antenna", int(rng.integers(0, 3)), 0.5, sz=rng.uniform(1.5, 3.0))
                    scatter("ac", int(area / 150), 0.5)
                elif arch == ARCH_PODIUM:  # department store: chillers + cooling towers
                    scatter("cooling", 1 + int(area / 900), 1.8)
                    scatter("machine", 1 + int(area / 1500), 3.0, sx=rng.uniform(4, 8), sy=rng.uniform(3, 6), sz=3.0)
                    scatter("ac", int(area / 80), 0.5)
                else:   # every archetype is routed explicitly; a new one must not inherit another's roof
                    raise RuntimeError("unrouted archetype %d for %s" % (arch, b["id"]))
                # red aviation obstruction lights on tall buildings (corners of the roof)
                if H >= 60.0 and part is b["polygons"][0]:
                    for q in np.asarray(inner.minimum_rotated_rectangle.exterior.coords)[:4]:
                        if ip.contains(Point(q[0] * 0.995 + cx * 0.005, q[1] * 0.995 + cy * 0.005)):
                            add("avlight", float(q[0]), float(q[1]), top, 0.0, v=0)

    total = sum(len(v) for v in inst.values())
    (OUT / "rooftop_instances.json").write_text(json.dumps({"count": total, "variants": VARIANTS, "types": inst}) + "\n")
    tri_total = sum(info[t]["triangles"] * len(inst[t]) for t in TYPES)
    report = {"types": {t: {**info[t], "instances": len(inst[t])} for t in TYPES}, "instances_total": total,
              "variants": VARIANTS, "instance_triangles_total": tri_total, "stats": stats,
              "sheet_colour_use": dict(zip(SHEET_NAMES, sheet_use))}
    (OUT / "rooftops.report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({t: len(inst[t]) for t in TYPES}), "total", total, "tris", tri_total)
    print(json.dumps(stats), json.dumps(dict(zip(SHEET_NAMES, sheet_use))))


if __name__ == "__main__":
    main()
