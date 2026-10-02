"""Urban-identity metadata (read-only foundation for the Taipei Urban Identity pass).

Nothing here is consumed by Unreal yet: no tile, material, ground texture or level changes. It derives
the two data contracts the future street / facade and school / campus layers need and the accepted
look does not carry (see docs/xinyi-urban-identity-engineering-plan.md):

1. FRONTAGE  per building ring edge: which edges face a drivable road, which road class / width /
             curb distance, whether the view to the road is open (not blocked by another building),
             plus building-level frontage length by class, corner flag and a commercial-frontage
             candidate flag. Deterministic, geometry only (no OSM building tags exist for the WFS
             buildings, and the WFS carries no use / name attributes).
2. CAMPUS    school / university campuses (OSM multipolygon relations + amenity ways), their tagged
             classroom buildings, the WFS buildings inside them, sports pitches / playgrounds / pools /
             stadium halls with orientation and size, and the open-yard area. Athletics tracks are NOT
             in the source (0 leisure=track, 0 sport=athletics): a conservative `track_candidate` flag
             marks campuses whose open yard could hold a 400 m track (unverified, do not render).

Inputs : data/generated/taipei/sample_buildings_epsg3826.geojson (WFS, accepted)
         unreal/Saved/XinyiLook/look_buildings.jsonl.gz (archetype / flags / seed per record)
         data/lookdev_cache/osm_xinyi_context.json.gz (roads, same model as the ground art)
         data/lookdev_cache/osm_education_context.json.gz (tools/lookdev/fetch_education_context.py)
Outputs: unreal/Saved/XinyiLook/urban_identity/
  frontage.json.gz         {schema, edge_front_class, buildings: [...]}  (frontage edges only)
  campuses.json            {schema, campuses: [...], orphan_education_buildings: [...], sports: [...]}
  urban_identity.report.json   counts, per-archetype statistics, content hashes
  urban_identity_debug.png     top-down overlay (frontage edges by class, campuses, pitches)

Frontage class (3 bits, fits spare vertex flag bits 4-6 if baked later):
  0 none / interior   1 service alley   2 local street   3 collector   4 arterial
Edge ids are (building_id, part, ring edge index in the WorldModel footprint ring order); a consumer
matches walls geometrically (wall bottom edge midpoint on the edge) because the wall u parameter in
build_look_tiles.py starts at a mesh-index-dependent ring vertex.

Deterministic (no randomness); run twice -> identical sha256 in the report.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
import build_ground as bg  # noqa: E402  (road model identical to the ground art; definitions only)
from build_rooftops import max_rect  # noqa: E402
from worldmodel import build_worldmodel, enu_origin_from_city_yaml, lonlat_to_enu  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
LOOK = REPO / "unreal/Saved/XinyiLook"
EDU = REPO / "data/lookdev_cache/osm_education_context.json.gz"
OUT = LOOK / "urban_identity"

ARCH_NAMES = ["low", "walkup", "huaxia", "res_tower", "office_glass", "commercial_podium", "civic"]
ROAD_SEARCH_M = 45.0        # candidate road search radius around an edge midpoint
MAX_SETBACK_M = 16.0        # curb distance beyond which an edge is not street frontage
MIN_EDGE_M = 1.5
FACE_COS = 0.5              # edge outward normal vs direction to the road: within 60 degrees
MIN_FRONT_M = 3.0           # frontage length that counts for building-level classes
CORNER_DEG = 45.0
CLASS_BIAS_M = 2.5
FRONT_CLASS = {1.0: 4, 0.66: 3, 0.33: 2, 0.2: 1}
COMMERCIAL_ARCH = {0, 1, 2, 5}      # low / walkup / huaxia / podium (old shop-house fabric + podiums)
EDU_BUILDING = {"school", "university", "college", "kindergarten"}
HEIGHT = {}


def rnd(v, n=2):
    return round(float(v), n)


def poly_json(g, n=1):
    """Exterior (+ holes) of a Polygon / MultiPolygon as ENU coordinate lists."""
    if g.is_empty:
        return []
    parts = [g] if g.geom_type == "Polygon" else list(g.geoms)
    return [{"outer": [[rnd(x, n), rnd(y, n)] for x, y in p.exterior.coords],
             "holes": [[[rnd(x, n), rnd(y, n)] for x, y in r.coords] for r in p.interiors]} for p in parts]


# ------------------------------------------------------------------ roads ---
def load_roads():
    ways, *_ = bg.load_osm()
    roads = []
    for w in ways:
        g = bg.way_geometry(w)
        if g["skip"] or len(w["pts"]) < 2:
            continue
        roads.append({"id": w["id"], "line": LineString(w["pts"]), "width": g["width"], "cls": g["cls"],
                      "hw": w["tags"]["highway"], "name": w["tags"].get("name:zh") or w["tags"].get("name")})
    return roads


# --------------------------------------------------------------- frontage ---
def ring_edges(ring):
    pts = [tuple(p) for p in ring]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    a = np.array(pts, float)
    area = 0.5 * float(np.sum(a[:, 0] * np.roll(a[:, 1], -1) - np.roll(a[:, 0], -1) * a[:, 1]))
    sgn = 1.0 if area > 0 else -1.0                      # CCW -> outward normal is (dy, -dx)
    out = []
    for i in range(len(a)):
        p0, p1 = a[i], a[(i + 1) % len(a)]
        d = p1 - p0
        L = float(np.hypot(*d))
        if L < 1e-6:
            continue
        out.append((i, p0, p1, L, np.array([d[1], -d[0]]) / L * sgn))
    return out


def build_frontage(wm, look, roads):
    parts = []        # (building_id, group, part_idx, polygon, part)
    for b in wm["buildings"]:
        if b["suppressed"] or b["id"] not in look:
            continue
        rec = look[b["id"]]
        HEIGHT[b["id"]] = float(b["height_m"])
        if rec["flags"] & 8:                      # rooftop structure records are not street buildings
            continue
        for pi, part in enumerate(b["polygons"]):
            poly = Polygon(part["footprint_enu"], part.get("holes_enu") or [])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 6.0:
                continue
            parts.append((b["id"], rec["group"], pi, poly, part))
    bgeoms = [p[3] for p in parts]
    btree = STRtree(bgeoms)
    rlines = [r["line"] for r in roads]
    rtree = STRtree(rlines)
    group_of = {}
    for i, (bid, grp, *_r) in enumerate(parts):
        group_of[i] = grp

    per_building = {}
    for bi, (bid, grp, pi, poly, part) in enumerate(parts):
        rec = look[bid]
        ring = part["footprint_enu"]
        fronts = []
        n_edges = 0
        for ei, p0, p1, L, nrm in ring_edges(ring):
            n_edges += 1
            if L < MIN_EDGE_M:
                continue
            m = (p0 + p1) / 2.0
            mp = Point(m)
            cand = rtree.query(mp.buffer(ROAD_SEARCH_M))
            best = None
            for ci in cand:
                r = roads[ci]
                d_line = r["line"].distance(mp)
                curb = d_line - r["width"] * 0.5
                if curb > MAX_SETBACK_M:
                    continue
                q = r["line"].interpolate(r["line"].project(mp))
                v = np.array([q.x - m[0], q.y - m[1]])
                dist = float(np.hypot(*v))
                if dist < 1e-6:
                    continue
                if float(np.dot(v / dist, nrm)) < FACE_COS:
                    continue
                # nearest curb wins, but each class step is worth CLASS_BIAS_M of extra distance so a
                # main street 8 m away beats a parking-aisle `service` way 3 m away
                key = (max(curb, 0.0) - CLASS_BIAS_M * FRONT_CLASS.get(r["cls"], 2), r["id"])
                if best is None or key < best[0]:
                    best = (key, ci, curb, q, dist)
            if best is None:
                continue
            _, ci, curb, q, dist = best
            # open view to the road: the sight line must not cross another building
            start = m + nrm * 0.25
            sight = LineString([tuple(start), (q.x, q.y)])
            blocked = False
            for hi in btree.query(sight, predicate="intersects"):
                if group_of[hi] != grp and bgeoms[hi].intersects(sight):
                    blocked = True
                    break
            if blocked:
                continue
            r = roads[ci]
            fc = FRONT_CLASS.get(r["cls"], 2)
            fronts.append({"part": pi, "edge": ei, "p0": [rnd(p0[0]), rnd(p0[1])], "p1": [rnd(p1[0]), rnd(p1[1])],
                           "len": rnd(L), "normal_deg": rnd(math.degrees(math.atan2(nrm[1], nrm[0])) % 360.0, 1),
                           "front": fc, "road_id": r["id"], "road_hw": r["hw"], "road_width": rnd(r["width"], 1),
                           "curb_m": rnd(max(curb, 0.0), 1)})
        acc = per_building.setdefault(bid, {"building_id": bid, "group": grp, "archetype": rec["archetype"],
                                            "core": bool(rec["flags"] & 1), "edges_total": 0, "edges": []})
        acc["edges_total"] += n_edges
        acc["edges"] += fronts

    out = []
    for bid in sorted(per_building):
        acc = per_building[bid]
        E = acc["edges"]
        by = defaultdict(float)
        for e in E:
            by[e["front"]] += e["len"]
        solid = [e for e in E if e["len"] >= MIN_FRONT_M]
        best_class = max([e["front"] for e in solid], default=0)
        # corner: two substantial frontage edges on different roads whose normals differ >= 45 degrees
        corner = False
        for i in range(len(solid)):
            for j in range(i + 1, len(solid)):
                a, b = solid[i], solid[j]
                dn = abs((a["normal_deg"] - b["normal_deg"] + 180.0) % 360.0 - 180.0)
                if a["road_id"] != b["road_id"] and dn >= CORNER_DEG:
                    corner = True
        front_len = sum(by.values())
        commercial = bool(acc["archetype"] in COMMERCIAL_ARCH and best_class >= 2 and front_len >= 6.0)
        acc.update({"frontage_len_m": rnd(front_len), "frontage_len_by_class": {str(k): rnd(v) for k, v in sorted(by.items())},
                    "best_front_class": best_class, "corner": corner, "commercial_candidate": commercial})
        if E:
            out.append(acc)
    return out, parts


# ----------------------------------------------------------------- campus ---
def edu_geometry(doc, lon0, lat0):
    def enu(g):
        return [lonlat_to_enu(p["lon"], p["lat"], lon0, lat0) for p in g]
    feats = []
    for e in doc["elements"]:
        t = e.get("tags", {})
        if e["type"] == "way" and e.get("geometry"):
            pts = enu(e["geometry"])
            closed = len(pts) >= 4 and e["nodes"][0] == e["nodes"][-1]
            if not closed:
                continue
            g = Polygon(pts).buffer(0)
            if g.is_valid and not g.is_empty:
                feats.append({"type": "way", "id": e["id"], "tags": t, "geom": g})
        elif e["type"] == "relation":
            outers = [LineString(enu(m["geometry"])) for m in e.get("members", [])
                      if m.get("role") == "outer" and m.get("geometry") and len(m["geometry"]) >= 2]
            inners = [LineString(enu(m["geometry"])) for m in e.get("members", [])
                      if m.get("role") == "inner" and m.get("geometry") and len(m["geometry"]) >= 4]
            if not outers:
                continue
            polys = list(polygonize(linemerge(outers)))
            if not polys:
                continue
            g = unary_union([p.buffer(0) for p in polys])
            for ln in inners:
                g = g.difference(Polygon(ln).buffer(0))
            if g.is_valid and not g.is_empty:
                feats.append({"type": "relation", "id": e["id"], "tags": t, "geom": g})
    return feats


def school_level(name):
    n = name or ""
    for key, lvl in (("國際國中小", "k12"), ("國小", "elementary"), ("國中", "junior_high"), ("高中", "senior_high"),
                     ("高工", "vocational"), ("工農", "vocational"), ("商職", "vocational"), ("工商", "vocational"),
                     ("幼兒園", "kindergarten"), ("幼稚園", "kindergarten"), ("大學", "university"), ("學院", "university")):
        if key in n:
            return lvl
    return "school"


def build_campuses(feats, parts, look, bbox_poly):
    cam_src = [f for f in feats if f["tags"].get("amenity") in ("school", "university", "college", "kindergarten")]
    rels = [f for f in cam_src if f["type"] == "relation"]
    campuses = []
    used_ways = set()
    for f in sorted(rels, key=lambda x: x["id"]):
        campuses.append({"src": f, "aliases": []})
    for f in sorted([f for f in cam_src if f["type"] == "way"], key=lambda x: x["id"]):
        inside = None
        for c in campuses:
            inter = c["src"]["geom"].intersection(f["geom"]).area
            if f["geom"].area > 0 and inter / f["geom"].area > 0.6:
                inside = c
                break
        if inside is not None:
            inside["aliases"].append(f"osm_way_{f['id']}")
            used_ways.add(f["id"])
        else:
            campuses.append({"src": f, "aliases": []})

    cgeoms = [c["src"]["geom"] for c in campuses]
    ctree = STRtree(cgeoms)
    for i, c in enumerate(campuses):
        c["idx"] = i
        c["buildings_osm"] = []
        c["osm_geoms"] = []
        c["wfs"] = []
        c["pitches"] = []
        c["playgrounds"] = []
        c["pools"] = []
        c["halls"] = []

    def owner(geom):
        pt = geom.representative_point()
        hits = [int(i) for i in ctree.query(pt, predicate="intersects")]
        if not hits:
            near = ctree.nearest(geom)
            if near is not None and cgeoms[int(near)].distance(geom) <= 6.0:
                hits = [int(near)]
        return min(hits, key=lambda i: cgeoms[i].area) if hits else None

    orphans, sports = [], []
    osm_b = []
    for f in feats:
        t = f["tags"]
        bld = str(t.get("building", ""))
        lei = t.get("leisure")
        g = f["geom"]
        if lei == "pitch":
            mrr = g.minimum_rotated_rectangle
            co = list(mrr.exterior.coords)
            e1 = np.array(co[1]) - np.array(co[0])
            e2 = np.array(co[2]) - np.array(co[1])
            if np.hypot(*e1) < np.hypot(*e2):
                e1, e2 = e2, e1
            rec = {"id": f"osm_way_{f['id']}", "kind": "pitch", "sport": t.get("sport", ""), "surface": t.get("surface", ""),
                   "name": t.get("name", ""), "length_m": rnd(np.hypot(*e1)), "width_m": rnd(np.hypot(*e2)),
                   "orientation_deg": rnd(math.degrees(math.atan2(e1[1], e1[0])) % 180.0, 1),
                   "area_m2": rnd(g.area), "center": [rnd(g.centroid.x), rnd(g.centroid.y)], "polygon": poly_json(g)}
            o = owner(g)
            rec["campus"] = campuses[o]["idx"] if o is not None else None
            (campuses[o]["pitches"] if o is not None else sports).append(rec)
        elif lei == "playground":
            rec = {"id": f"osm_way_{f['id']}", "kind": "playground", "area_m2": rnd(g.area), "center": [rnd(g.centroid.x), rnd(g.centroid.y)],
                   "polygon": poly_json(g)}
            o = owner(g)
            rec["campus"] = campuses[o]["idx"] if o is not None else None
            (campuses[o]["playgrounds"] if o is not None else sports).append(rec)
        elif lei == "swimming_pool":
            rec = {"id": f"osm_way_{f['id']}", "kind": "pool", "name": t.get("name", ""), "area_m2": rnd(g.area),
                   "center": [rnd(g.centroid.x), rnd(g.centroid.y)], "polygon": poly_json(g)}
            o = owner(g)
            rec["campus"] = campuses[o]["idx"] if o is not None else None
            (campuses[o]["pools"] if o is not None else sports).append(rec)
        elif lei in ("stadium", "sports_centre"):
            rec = {"id": f"osm_way_{f['id']}", "kind": lei, "building": bld, "name": t.get("name", ""), "area_m2": rnd(g.area),
                   "center": [rnd(g.centroid.x), rnd(g.centroid.y)], "polygon": poly_json(g)}
            o = owner(g) if bld in EDU_BUILDING else None
            rec["campus"] = campuses[o]["idx"] if o is not None else None
            (campuses[o]["halls"] if o is not None else sports).append(rec)
        if bld in EDU_BUILDING and f["type"] == "way" and lei not in ("stadium", "sports_centre", "swimming_pool"):
            osm_b.append(f)

    wtree = STRtree([p[3] for p in parts])
    wfs_owner = {}
    for f in sorted(osm_b, key=lambda x: x["id"]):
        g = f["geom"]
        o = owner(g)
        rec = {"id": f"osm_way_{f['id']}", "name": f["tags"].get("name", ""), "building": f["tags"].get("building"),
               "levels": f["tags"].get("building:levels", ""), "area_m2": rnd(g.area)}
        # WFS record with the largest overlap (IoU) is the same real building
        best, best_iou = None, 0.0
        for hi in wtree.query(g, predicate="intersects"):
            pg = parts[int(hi)][3]
            u = pg.union(g).area
            iou = pg.intersection(g).area / u if u > 0 else 0.0
            if iou > best_iou:
                best, best_iou = int(hi), iou
        if best is not None and best_iou >= 0.4:
            rec["wfs_building_id"] = parts[best][0]
            rec["wfs_iou"] = rnd(best_iou, 2)
            rec["wfs_archetype"] = ARCH_NAMES[look[parts[best][0]]["archetype"]]
        (campuses[o]["buildings_osm"] if o is not None else orphans).append(rec)
        if o is not None:
            campuses[o]["osm_geoms"].append(g)

    # WFS buildings in each campus (representative point inside the campus polygon)
    for pi, (bid, grp, part_i, poly, part) in enumerate(parts):
        hits = [int(i) for i in ctree.query(poly.representative_point(), predicate="intersects")]
        if hits:
            o = min(hits, key=lambda i: cgeoms[i].area)
            campuses[o]["wfs"].append({"building_id": bid, "part": part_i, "archetype": look[bid]["archetype"],
                                       "height_m": rnd(HEIGHT.get(bid, 0.0)), "area_m2": rnd(poly.area)})

    out = []
    for c in campuses:
        f = c["src"]
        g = f["geom"]
        name = f["tags"].get("name:zh") or f["tags"].get("name") or ""
        cov = g.intersection(bbox_poly).area / g.area if g.area > 0 else 0.0
        # open yard: campus minus buildings (WFS + OSM tagged) minus sports surfaces
        solids = list(c["osm_geoms"])
        wfs_polys = [parts[i][3] for i in [int(h) for h in wtree.query(g, predicate="intersects")]
                     if g.contains(parts[i][3].representative_point())]
        solids += wfs_polys
        solids += [Polygon(r["outer"]) for x in c["pitches"] + c["playgrounds"] + c["pools"] + c["halls"] for r in x["polygon"]]
        yard = g.difference(unary_union(solids).buffer(2.0)) if solids else g
        yard = yard.buffer(-1.0).buffer(1.0)
        rect = None
        track_candidate = False
        if not yard.is_empty and yard.area > 1500.0:
            mrr = g.minimum_rotated_rectangle
            co = list(mrr.exterior.coords)
            e1 = np.array(co[1]) - np.array(co[0])
            ang = math.degrees(math.atan2(e1[1], e1[0]))
            yp = yard if yard.geom_type == "Polygon" else max(yard.geoms, key=lambda x: x.area)
            org = (g.centroid.x, g.centroid.y)
            r = max_rect(yp, ang, org, cell=1.0)
            if r is not None:
                ln, sh = max(r[1] - r[0], r[3] - r[2]), min(r[1] - r[0], r[3] - r[2])
                rect = {"length_m": rnd(ln), "width_m": rnd(sh), "campus_axis_deg": rnd(ang % 180.0, 1)}
                track_candidate = bool(ln >= 90.0 and sh >= 45.0)
        out.append({
            "id": f"osm_{f['type']}_{f['id']}", "aliases": sorted(c["aliases"]), "name": name,
            "amenity": f["tags"].get("amenity"), "level": school_level(name),
            "operator": f["tags"].get("operator", ""), "area_m2": rnd(g.area),
            "bbox_coverage": rnd(cov, 3), "complete_in_building_source": cov > 0.97,
            "polygon": poly_json(g),
            "wfs_building_count": len(c["wfs"]), "wfs_buildings": sorted(c["wfs"], key=lambda w: (w["building_id"], w["part"])),
            "osm_buildings": c["buildings_osm"], "pitches": c["pitches"], "playgrounds": c["playgrounds"],
            "pools": c["pools"], "halls": c["halls"],
            "open_yard_area_m2": rnd(yard.area), "largest_open_rect": rect,
            "yard_basis": "wfs+osm_buildings" if cov > 0.97 else ("osm_buildings_only" if cov < 0.05 else "partial_wfs+osm_buildings"),
            "track_candidate": track_candidate,
            "track_note": "no leisure=track / sport=athletics in OSM: candidate only, unverified, never render from this flag alone",
        })
    out.sort(key=lambda c: c["id"])
    return out, orphans, sports


# ------------------------------------------------------------- debug image ---
def debug_image(parts, frontage, campuses, sports, path, scale=0.5):
    from PIL import Image, ImageDraw
    xs = np.concatenate([np.asarray(p[3].exterior.coords)[:, 0] for p in parts])
    ys = np.concatenate([np.asarray(p[3].exterior.coords)[:, 1] for p in parts])
    x0, x1, y0, y1 = xs.min() - 20, xs.max() + 20, ys.min() - 20, ys.max() + 20
    W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
    img = Image.new("RGB", (W, H), (24, 26, 30))
    dr = ImageDraw.Draw(img)

    def px(p):
        return ((p[0] - x0) * scale, (y1 - p[1]) * scale)
    for c in campuses:
        for pg in c["polygon"]:
            dr.polygon([px(p) for p in pg["outer"]], fill=(30, 66, 44) if c["bbox_coverage"] > 0.0 else None,
                       outline=(80, 200, 120))
    for (_b, _g, _pi, poly, _pt) in parts:
        dr.polygon([px(p) for p in poly.exterior.coords], fill=(64, 66, 72))
    col = {1: (0, 200, 220), 2: (240, 220, 60), 3: (255, 150, 40), 4: (240, 60, 60)}
    for b in frontage:
        for e in b["edges"]:
            dr.line([px(e["p0"]), px(e["p1"])], fill=col[e["front"]], width=2)
    for c in campuses:
        for k in ("pitches", "playgrounds", "pools", "halls"):
            for x in c[k]:
                for pg in x["polygon"]:
                    dr.polygon([px(p) for p in pg["outer"]], fill=(60, 120, 240), outline=(140, 190, 255))
    for x in sports:
        for pg in x["polygon"]:
            dr.polygon([px(p) for p in pg["outer"]], outline=(140, 190, 255))
    img.save(path, optimize=True)


# -------------------------------------------------------------------- main ---
def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    look = {}
    with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            look[r["building_id"]] = r
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    roads = load_roads()
    frontage, parts = build_frontage(wm, look, roads)
    t1 = time.time()

    xs = np.concatenate([np.asarray(p[3].exterior.coords)[:, 0] for p in parts])
    ys = np.concatenate([np.asarray(p[3].exterior.coords)[:, 1] for p in parts])
    bbox_poly = shapely.geometry.box(xs.min(), ys.min(), xs.max(), ys.max())
    edu = json.loads(gzip.decompress(EDU.read_bytes()))
    feats = edu_geometry(edu, lon0, lat0)
    campuses, orphans, sports = build_campuses(feats, parts, look, bbox_poly)

    (OUT / "frontage.json.gz").write_bytes(gzip.compress(json.dumps(
        {"schema": "acw.frontage/0", "edge_front_class": {"0": "none", "1": "service alley", "2": "local street",
                                                          "3": "collector", "4": "arterial"},
         "params": {"road_search_m": ROAD_SEARCH_M, "max_setback_m": MAX_SETBACK_M, "face_cos": FACE_COS,
                    "min_edge_m": MIN_EDGE_M, "min_front_m": MIN_FRONT_M, "corner_deg": CORNER_DEG},
         "buildings": frontage}, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode("utf-8"), 9, mtime=0))
    (OUT / "campuses.json").write_text(json.dumps(
        {"schema": "acw.campuses/0", "source": "osm_education_context (ODbL) + WFS buildings",
         "campuses": campuses, "orphan_education_buildings": orphans, "sports_outside_campuses": sports},
        ensure_ascii=False, sort_keys=True, indent=0) + "\n", encoding="utf-8")

    # ---- statistics
    n_build = len({p[0] for p in parts})
    front_by_arch = defaultdict(Counter)
    for b in frontage:
        a = ARCH_NAMES[b["archetype"]]
        front_by_arch[a]["with_frontage"] += 1
        front_by_arch[a][f"best_class_{b['best_front_class']}"] += 1
        front_by_arch[a]["corner"] += int(b["corner"])
        front_by_arch[a]["commercial_candidate"] += int(b["commercial_candidate"])
    edge_total = sum(b["edges_total"] for b in frontage)
    edge_front = sum(len(b["edges"]) for b in frontage)
    len_by_class = Counter()
    for b in frontage:
        for e in b["edges"]:
            len_by_class[e["front"]] += e["len"]
    camp_summary = [{"id": c["id"], "name": c["name"], "level": c["level"], "area_m2": c["area_m2"],
                     "bbox_coverage": c["bbox_coverage"], "wfs_buildings": c["wfs_building_count"],
                     "osm_buildings": len(c["osm_buildings"]), "pitches": len(c["pitches"]),
                     "playgrounds": len(c["playgrounds"]), "open_yard_m2": c["open_yard_area_m2"],
                     "largest_open_rect": c["largest_open_rect"], "track_candidate": c["track_candidate"]} for c in campuses]
    h = {f: hashlib.sha256((OUT / f).read_bytes()).hexdigest() for f in ("frontage.json.gz", "campuses.json")}
    rep = {
        "status": "PASS_URBAN_IDENTITY_METADATA",
        "role": "read-only metadata; nothing consumes it yet (no visual change)",
        "buildings_considered": n_build, "building_parts": len(parts),
        "roads": {"ways": len(roads), "by_class": dict(Counter(FRONT_CLASS.get(r["cls"], 2) for r in roads))},
        "frontage": {"buildings_with_frontage": len(frontage), "share": rnd(len(frontage) / max(n_build, 1), 3),
                     "ring_edges_of_those": edge_total, "frontage_edges": edge_front,
                     "frontage_len_m_by_class": {str(k): rnd(v) for k, v in sorted(len_by_class.items())},
                     "by_archetype": {k: dict(v) for k, v in sorted(front_by_arch.items())},
                     "corners": sum(1 for b in frontage if b["corner"]),
                     "commercial_candidates": sum(1 for b in frontage if b["commercial_candidate"])},
        "campuses": {"count": len(campuses), "complete_in_building_source": sum(1 for c in campuses if c["complete_in_building_source"]),
                     "wfs_buildings_in_campuses": sum(c["wfs_building_count"] for c in campuses),
                     "osm_school_buildings": sum(len(c["osm_buildings"]) for c in campuses) + len(orphans),
                     "pitches_in_campuses": sum(len(c["pitches"]) for c in campuses),
                     "pitches_outside": sum(1 for s in sports if s["kind"] == "pitch"),
                     "playgrounds_in_campuses": sum(len(c["playgrounds"]) for c in campuses),
                     "track_candidates": sum(1 for c in campuses if c["track_candidate"]),
                     "athletics_tracks_in_source": sum(1 for f in feats if f["tags"].get("leisure") == "track"
                                                       or f["tags"].get("sport") in ("athletics", "running")),
                     "summary": camp_summary},
        "sha256": h, "seconds": {"frontage": rnd(t1 - t0, 1), "total": rnd(time.time() - t0, 1)},
    }
    (OUT / "urban_identity.report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    debug_image(parts, frontage, campuses, sports, OUT / "urban_identity_debug.png")
    print(json.dumps({k: rep[k] for k in ("buildings_considered", "frontage")}, ensure_ascii=False))
    print(json.dumps({k: v for k, v in rep["campuses"].items() if k != "summary"}, ensure_ascii=False))
    print(json.dumps(h))


if __name__ == "__main__":
    main()
