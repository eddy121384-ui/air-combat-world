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

Instances (per-instance custom data 0 = (v + 0.5) / variants, decoded in xinyi_city.hlsl xc_street):
  sign / box  v = atlas cell + 64 * lit + 128 * fade(0..3)        (variants 512)
  awning      v = colour(0..7) + 8 * fade(0..3) + 32 * style(0..1) (variants 64)

Outputs (unreal/Saved/XinyiLook/street/):
  street_sign.glb     unit blade: brackets x 0..0.25, panel x 0.25..1.25 (scaled by panel width), y +-0.5
                      (thickness), z 0..1 (height); TEXCOORD_0 = panel UV (both faces read correctly),
                      TEXCOORD_2 = (type 15, part: 0 face / 1 bracket / 2 edge)
  street_awning.glb   unit sloped canopy: x 0..1 projection, y +-0.5 width, z drop; type 16
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
TYPE_SIGN, TYPE_AWNING = 15, 16
SIGN_VARIANTS, AWNING_VARIANTS = 512, 64

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

    sm, am = sign_mesh(), awning_mesh()
    sb, st = sm.write(OUT / "street_sign.glb", "SM_XinyiStreetSign")
    ab, at = am.write(OUT / "street_awning.glb", "SM_XinyiStreetAwning")
    doc = {"schema": "acw.street_instances/0", "variants": {"sign": SIGN_VARIANTS, "box": SIGN_VARIANTS,
                                                            "awning": AWNING_VARIANTS},
           "types": inst}
    (OUT / "street_instances.json").write_text(json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n")
    report = {
        "status": "PASS_STREET_IDENTITY",
        "meshes": {"sign": {"mesh": "street_sign.glb", "triangles": st, "expected_ue_local_bounds": sb,
                            "used_by": ["sign", "box"]},
                   "awning": {"mesh": "street_awning.glb", "triangles": at, "expected_ue_local_bounds": ab,
                              "used_by": ["awning"]}},
        "instances": {k: len(v) for k, v in inst.items()},
        "instance_triangles": {"sign": len(inst["sign"]) * st, "box": len(inst["box"]) * st,
                               "awning": len(inst["awning"]) * at},
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
