"""Build the Xinyi ground layer: road SDF texture, road-paint mesh, tree instances.

Inputs: OSM context snapshot (data/lookdev_cache/osm_xinyi_context.json.gz),
accepted Landscape heightfield (contract), accepted building footprints (WFS).
Nothing here edits buildings or terrain. OSM is used only for surface art.

Outputs (unreal/Saved/XinyiLook/ground/):
  xinyi_ground_2048.png   RGBA8 over the accepted 2.5 km Landscape extent
                          (row 0 = north, col 0 = west; 1.2207 m/px)
                          R = road signed distance, 0.5 = kerb, +-12 m range
                              (<0.5 inside carriageway)
                          G = vegetation coverage (parks, grass, forest)
                          B = road class (0 none, .33 local, .66 collector, 1 arterial)
                          A = water coverage
  xinyi_road_paint.glb    thin opaque paint geometry draped 6 cm above terrain:
                          lane lines, double-yellow centre lines, red kerb lines,
                          zebra crossings, stop lines, scooter waiting boxes
                          (機車停等區). TEXCOORD_2 = packed RGBA8 paint colour.
  xinyi_trees.json        tree instances (street trees, median trees, parks)
  xinyi_tree.glb          one low-poly broadleaf tree (crown + trunk)
"""
from __future__ import annotations

import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import build_worldmodel, enu_origin_from_city_yaml, lonlat_to_enu  # noqa: E402

CITY = REPO / "cities/taipei/city.yaml"
OSM = REPO / "data/lookdev_cache/osm_xinyi_context.json.gz"
SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CONTRACT = REPO / "unreal/Saved/XinyiUnrealV2Contract"
OUT = REPO / "unreal/Saved/XinyiLook/ground"

E0, E1, N0, N1 = -1500.0, 1000.0, -1000.0, 1500.0
TREE_BOUNDS = None
RES = 2048
SDF_RANGE_M = 12.0
SUPER = 4

DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
            "primary_link", "secondary_link", "tertiary_link", "residential", "unclassified",
            "living_street", "service"}
CLASS = {"motorway": 1.0, "trunk": 1.0, "primary": 1.0, "secondary": 1.0, "trunk_link": 0.66,
         "primary_link": 0.66, "secondary_link": 0.66, "tertiary": 0.66, "tertiary_link": 0.66,
         "residential": 0.33, "unclassified": 0.33, "living_street": 0.33, "service": 0.2}
DEFAULT_LANES = {"trunk": 3, "primary": 3, "secondary": 3, "tertiary": 2, "residential": 2,
                 "unclassified": 2, "living_street": 1, "service": 1}
LANE_W = 3.3


class Heightfield:
    def __init__(self):
        c = json.loads((CONTRACT / "xinyi_unreal_v2_contract.json").read_text())
        ls = c["landscape"]
        n = ls["heightmap_size"][0]
        raw = np.fromfile(CONTRACT / "xinyi_moi2025_landscape_631.r16", dtype="<u2").reshape(n, n)
        self.z = (raw.astype(np.float64) - 32768.0) * ls["scale_xyz"][2] / 128.0 / 100.0
        self.step = ls["sample_spacing_m"]
        self.n = n

    def __call__(self, e, nn):
        e = np.asarray(e, dtype=np.float64)
        nn = np.asarray(nn, dtype=np.float64)
        fx = np.clip((e - E0) / self.step, 0, self.n - 1.001)
        fy = np.clip((N1 - nn) / self.step, 0, self.n - 1.001)
        x0 = np.floor(fx).astype(int)
        y0 = np.floor(fy).astype(int)
        tx, ty = fx - x0, fy - y0
        z = self.z
        return ((z[y0, x0] * (1 - tx) + z[y0, x0 + 1] * tx) * (1 - ty)
                + (z[y0 + 1, x0] * (1 - tx) + z[y0 + 1, x0 + 1] * tx) * ty)


def load_osm():
    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    d = json.loads(gzip.decompress(OSM.read_bytes()))

    def enu(g):
        return [lonlat_to_enu(p["lon"], p["lat"], lon0, lat0) for p in g]

    ways, polys_green, polys_water, trees = [], [], [], []
    for e in d["elements"]:
        t = e.get("tags", {})
        if e["type"] == "node" and t.get("natural") == "tree":
            trees.append(lonlat_to_enu(e["lon"], e["lat"], lon0, lat0))
        elif e["type"] == "way":
            pts = enu(e["geometry"])
            if len(pts) < 2:
                continue
            closed = e["nodes"][0] == e["nodes"][-1] and len(pts) >= 4
            green = (t.get("leisure") in ("park", "garden", "pitch", "playground") or
                     t.get("landuse") in ("grass", "forest", "park", "recreation_ground", "cemetery") or
                     t.get("natural") in ("wood", "scrub"))
            if closed and green:
                polys_green.append(Polygon(pts).buffer(0))
            elif closed and (t.get("natural") == "water"):
                polys_water.append(Polygon(pts).buffer(0))
            elif t.get("highway") in DRIVABLE:
                ways.append({"id": e["id"], "nodes": e["nodes"], "pts": pts, "tags": t})
        elif e["type"] == "relation":
            green = t.get("leisure") == "park" or t.get("landuse") in ("forest", "grass")
            if green:
                outers = [Polygon(enu(m["geometry"])).buffer(0) for m in e["members"]
                          if m.get("role") == "outer" and m.get("geometry") and len(m["geometry"]) >= 4]
                polys_green += [p for p in outers if p.is_valid]
    return ways, polys_green, polys_water, trees


def way_geometry(w):
    t = w["tags"]
    hw = t["highway"]
    oneway = t.get("oneway") in ("yes", "1", "-1") or hw.endswith("_link")
    lanes = None
    try:
        lanes = int(float(t.get("lanes"))) if t.get("lanes") else None
    except ValueError:
        lanes = None
    base = hw.replace("_link", "")
    if lanes is None:
        lanes = DEFAULT_LANES.get(base, 2)
        if oneway:
            lanes = max(1, lanes - (0 if base in ("trunk", "primary", "secondary") else 1))
    width = None
    try:
        width = float(t["width"]) if "width" in t else None
    except ValueError:
        width = None
    if width is None:
        width = lanes * LANE_W + (1.0 if lanes > 1 else 0.8)
        if base in ("residential", "unclassified") and not oneway:
            width = max(6.0, min(width, 8.0))
        if base == "service":
            width = 4.5
    skip = t.get("tunnel") in ("yes", "building_passage") or t.get("bridge") == "yes" or \
        (t.get("layer") not in (None, "0") and t.get("layer", "0").lstrip("-").isdigit() and int(t.get("layer")) != 0)
    return {"width": width, "lanes": lanes, "oneway": oneway, "cls": CLASS.get(hw, 0.33), "base": base, "skip": skip}


# ------------------------------------------------------------------ paint ---
class Paint:
    WHITE = (235, 235, 228, 255)
    YELLOW = (230, 180, 40, 255)
    RED = (190, 35, 30, 255)

    def __init__(self, hf):
        self.hf = hf
        self.v, self.c, self.f = [], [], []

    def quad_strip(self, a, b, w, color):
        """Rectangle centred on segment a->b with width w."""
        a = np.asarray(a, float); b = np.asarray(b, float)
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-3:
            return
        n = np.array([-d[1], d[0]]) / L * (w * 0.5)
        pts = [a - n, b - n, b + n, a + n]
        base = len(self.v)
        z = self.hf([p[0] for p in pts], [p[1] for p in pts]) + 0.06
        for p, zz in zip(pts, z):
            self.v.append((p[0], p[1], zz))
            self.c.append(color)
        self.f += [(base, base + 1, base + 2), (base, base + 2, base + 3)]

    def polyline(self, pts, offset, w, color, dash=None, gap=None, clip=None):
        line = LineString(pts)
        if abs(offset) > 1e-6:
            try:
                line = line.offset_curve(offset, join_style="mitre", mitre_limit=2.0)
            except Exception:
                return
        if line.is_empty or line.geom_type != "LineString":
            return
        if clip is not None:
            line = line.difference(clip)
        segs = [line] if line.geom_type == "LineString" else list(getattr(line, "geoms", []))
        for s in segs:
            if s.is_empty or s.length < 0.5:
                continue
            if dash is None:
                c = list(s.coords)
                for a, b in zip(c[:-1], c[1:]):
                    self.quad_strip(a, b, w, color)
            else:
                pos = 0.0
                while pos < s.length:
                    a = s.interpolate(pos); b = s.interpolate(min(pos + dash, s.length))
                    self.quad_strip((a.x, a.y), (b.x, b.y), w, color)
                    pos += dash + gap

    def arrays(self):
        pos = np.asarray(self.v, dtype=np.float64)
        game = np.column_stack([pos[:, 0], pos[:, 2], -pos[:, 1]]).astype(np.float32)
        return game, np.asarray(self.c, np.uint8), np.asarray(self.f, np.uint32)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hf = Heightfield()
    ways, greens, waters, osm_trees = load_osm()
    extent = box(E0, N0, E1, N1)

    # buildings (for tree rejection + paint clipping)
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    bpolys = []
    for b in wm["buildings"]:
        for p in b["polygons"]:
            q = Polygon(p["footprint_enu"])
            if q.is_valid and q.area > 1:
                bpolys.append(q)
    btree = STRtree(bpolys)

    # junction detection: node ids shared by >= 2 drivable ways (not skipped)
    for w in ways:
        w.update(way_geometry(w))
    node_ways = defaultdict(list)
    node_pos = {}
    for w in ways:
        if w["skip"]:
            continue
        for i, nid in enumerate(w["nodes"]):
            node_ways[nid].append((w, i))
            node_pos[nid] = w["pts"][i]
    junctions = {nid: lst for nid, lst in node_ways.items() if len({id(x[0]) for x in lst}) >= 2}

    # road polygons by class
    road_by_cls = defaultdict(list)
    for w in ways:
        if w["skip"]:
            continue
        ls = LineString(w["pts"])
        road_by_cls[w["cls"]].append(ls.buffer(w["width"] * 0.5, cap_style="flat", join_style="round"))
        # round the ends only at junctions so carriageways meet cleanly
        for end in (0, -1):
            if w["nodes"][end] in junctions:
                road_by_cls[w["cls"]].append(Point(w["pts"][end]).buffer(w["width"] * 0.5))
    roads = unary_union([g for lst in road_by_cls.values() for g in lst]).intersection(extent.buffer(50))

    # ----------------------------------------------------------- raster -------
    S = RES * SUPER
    px = (E1 - E0) / S

    def to_px(pts):
        return [((x - E0) / px, (N1 - y) / px) for x, y in pts]

    def fill(img_draw, geom, val):
        gs = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
        for g in gs:
            if g.geom_type != "Polygon" or g.is_empty:
                continue
            img_draw.polygon(to_px(g.exterior.coords), fill=val)
            for h in g.interiors:
                img_draw.polygon(to_px(h.coords), fill=0)

    road_img = Image.new("L", (S, S), 0)
    fill(ImageDraw.Draw(road_img), roads, 255)
    road = np.asarray(road_img) > 127
    din = ndimage.distance_transform_edt(road) * px
    dout = ndimage.distance_transform_edt(~road) * px
    sd = np.where(road, -din, dout)   # negative inside carriageway
    sd_small = sd.reshape(RES, SUPER, RES, SUPER).mean(axis=(1, 3))
    R = np.clip(0.5 + sd_small / (2 * SDF_RANGE_M), 0, 1)

    def coverage(geoms):
        img = Image.new("L", (S, S), 0)
        dr = ImageDraw.Draw(img)
        for g in geoms:
            g = g.intersection(extent.buffer(50))
            if not g.is_empty:
                fill(dr, g, 255)
        a = np.asarray(img, dtype=np.float32) / 255.0
        return a.reshape(RES, SUPER, RES, SUPER).mean(axis=(1, 3))

    G = coverage(greens)
    A = coverage(waters)
    cls_img = Image.new("L", (S, S), 0)
    dr = ImageDraw.Draw(cls_img)
    for c in sorted(road_by_cls):
        fill(dr, unary_union(road_by_cls[c]).intersection(extent.buffer(50)), int(round(c * 255)))
    B = np.asarray(cls_img, dtype=np.float32).reshape(RES, SUPER, RES, SUPER).max(axis=(1, 3)) / 255.0
    # grow class outward a little so the kerb-side shader can read it
    B = ndimage.grey_dilation(B, size=(5, 5))

    rgba = np.stack([R, G, B, A], axis=-1)
    Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").save(OUT / "xinyi_ground_2048.png", optimize=True)

    # ----------------------------------------------------------- paint --------
    paint = Paint(hf)
    for w in ways:
        if w["skip"] or w["base"] in ("service",):
            continue
        pts = w["pts"]
        W, lanes = w["width"], w["lanes"]
        # keep lines out of junction boxes
        jclip = unary_union([Point(node_pos[n]).buffer(max(6.0, W * 0.9))
                             for n in (w["nodes"][0], w["nodes"][-1]) if n in junctions] or [Point(1e9, 1e9)])
        if w["oneway"]:
            for k in range(1, lanes):
                off = -W * 0.5 + 0.5 + k * ((W - 1.0) / lanes)
                paint.polyline(pts, off, 0.15, Paint.WHITE, dash=4.0, gap=6.0, clip=jclip)
            if w["cls"] >= 0.66:
                paint.polyline(pts, W * 0.5 - 0.35, 0.15, Paint.WHITE, clip=jclip)
                paint.polyline(pts, -W * 0.5 + 0.35, 0.15, Paint.YELLOW, clip=jclip)
        else:
            if w["cls"] >= 0.33 and W >= 6.0:
                paint.polyline(pts, 0.12, 0.12, Paint.YELLOW, clip=jclip)
                paint.polyline(pts, -0.12, 0.12, Paint.YELLOW, clip=jclip)
            if lanes >= 4:
                for side in (-1, 1):
                    paint.polyline(pts, side * W * 0.25, 0.15, Paint.WHITE, dash=4.0, gap=6.0, clip=jclip)
        # red kerb lines (紅線, no stopping) on most urban roads
        if w["cls"] <= 0.66 and (w["id"] % 3) != 0:
            for side in (-1, 1):
                if w["oneway"] and side < 0 and w["cls"] >= 0.66:
                    continue
                paint.polyline(pts, side * (W * 0.5 - 0.2), 0.12, Paint.RED, clip=jclip)

    # zebra crossings + stop lines + scooter waiting boxes at junctions
    crossings = 0
    for nid, lst in junctions.items():
        if len({id(w) for w, _ in lst}) < 2:
            continue
        J = np.asarray(node_pos[nid])
        widths = [w["width"] for w, _ in lst]
        for w, i in lst:
            if w["cls"] < 0.33 or w["base"] == "service":
                continue
            pts = w["pts"]
            for step in (-1, 1):
                j = i + step
                if j < 0 or j >= len(pts):
                    continue
                d = np.asarray(pts[j]) - J
                L = np.linalg.norm(d)
                if L < 8.0:
                    continue
                d /= L
                others = [ow for (ow, _), wd in zip(lst, widths) if ow is not w] or [w]
                r0 = max(o["width"] for o in others) * 0.5 + 2.5
                if r0 + 5.0 > L:
                    continue
                n = np.array([-d[1], d[0]])
                W = w["width"]
                cw_len = 4.0 if w["cls"] >= 0.66 else 3.0
                c0 = J + d * r0
                # stripes parallel to traffic, repeated across the carriageway
                k = -W * 0.5 + 0.5
                while k < W * 0.5 - 0.4:
                    a = c0 + n * (k + 0.2)
                    paint.quad_strip(a, a + d * cw_len, 0.45, Paint.WHITE)
                    k += 1.0
                crossings += 1
                # traffic approaching the junction on this side
                approaching = (not w["oneway"]) or (step == -1)
                if approaching:
                    sl = c0 + d * (cw_len + 1.5)
                    half = W * 0.5 if w["oneway"] else 0.0
                    lo = -W * 0.5 if w["oneway"] else (0.0 if step == -1 else -W * 0.5)
                    hi = W * 0.5 if w["oneway"] else (W * 0.5 if step == -1 else 0.0)
                    paint.quad_strip(sl + n * lo, sl + n * hi, 0.4, Paint.WHITE)
                    if w["cls"] >= 0.66:
                        box_far = sl + d * 3.5
                        paint.quad_strip(box_far + n * lo, box_far + n * hi, 0.15, Paint.WHITE)
                        paint.quad_strip(sl + n * lo, box_far + n * lo, 0.15, Paint.WHITE)
                        paint.quad_strip(sl + n * hi, box_far + n * hi, 0.15, Paint.WHITE)

    game, colr, faces = paint.arrays()
    write_glb(OUT / "xinyi_road_paint.glb", [{
        "name": "XinyiRoadPaint", "positions": game,
        "normals": np.tile(np.array([[0, 1, 0]], np.float32), (len(game), 1)),
        "uv2": pack_rgba8(colr), "indices": faces, "base_color": [0.9, 0.9, 0.9, 1.0],
    }], mesh_name="SM_XinyiRoadPaint")

    # ----------------------------------------------------------- trees --------
    rng = np.random.default_rng(20260929)
    trees = []
    from shapely.prepared import prep
    bp = prep(unary_union([roads, unary_union(bpolys).buffer(1.2)]))
    jpts = [Point(node_pos[n]) for n in junctions]
    jtree = STRtree(jpts)

    def ok(x, y):
        if not (E0 + 5 < x < E1 - 5 and N0 + 5 < y < N1 - 5):
            return False
        p = Point(x, y)
        if bp.contains(p):
            return False
        near = jtree.query(p.buffer(12.0))
        return len(near) == 0

    for w in ways:
        if w["skip"] or w["cls"] < 0.33:
            continue
        ls = LineString(w["pts"])
        for side in (-1, 1):
            try:
                off = ls.offset_curve(side * (w["width"] * 0.5 + 1.8))
            except Exception:
                continue
            if off.is_empty or off.geom_type != "LineString":
                continue
            spacing = 9.0 if w["cls"] >= 0.66 else 11.0
            pos = rng.uniform(0, spacing)
            while pos < off.length:
                p = off.interpolate(pos)
                if ok(p.x, p.y):
                    trees.append((p.x, p.y, 0))
                pos += spacing * rng.uniform(0.85, 1.15)
    for g in greens:
        g = g.intersection(extent)
        if g.is_empty:
            continue
        minx, miny, maxx, maxy = g.bounds
        n = int(g.area / 55.0)
        if n <= 0:
            continue
        xs = rng.uniform(minx, maxx, n * 3)
        ys = rng.uniform(miny, maxy, n * 3)
        gp = prep(g)
        placed = 0
        for x, y in zip(xs, ys):
            if placed >= n:
                break
            if gp.contains(Point(x, y)) and ok(x, y):
                trees.append((x, y, 1))
                placed += 1
    for x, y in osm_trees:
        if E0 < x < E1 and N0 < y < N1:
            trees.append((x, y, 2))
    # thin duplicates on a 3 m grid
    seen, uniq = set(), []
    for x, y, k in trees:
        key = (int(x // 3), int(y // 3))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((x, y, k))
    xs = np.array([t[0] for t in uniq]); ys = np.array([t[1] for t in uniq])
    zs = hf(xs, ys)
    inst = []
    for (x, y, k), z in zip(uniq, zs):
        inst.append({
            "e": round(float(x), 3), "n": round(float(y), 3), "z": round(float(z), 3),
            "yaw": round(float(rng.uniform(0, 360)), 1),
            "s": round(float(rng.uniform(0.8, 1.25) * (1.15 if k == 1 else 1.0)), 3),
            "v": int(rng.integers(0, 4)), "kind": k,
        })
    (OUT / "xinyi_trees.json").write_text(json.dumps({"count": len(inst), "instances": inst}) + "\n")

    global TREE_BOUNDS
    TREE_BOUNDS = write_tree_mesh(OUT / "xinyi_tree.glb")
    report = {
        "texture": "xinyi_ground_2048.png", "resolution": RES, "metres_per_px": (E1 - E0) / RES,
        "extent_enu_m": [E0, E1, N0, N1], "sdf_range_m": SDF_RANGE_M,
        "road_ways": sum(1 for w in ways if not w["skip"]), "junctions": len(junctions),
        "crossings": crossings, "paint_triangles": int(len(faces)), "trees": len(inst),
        "road_area_m2": float(roads.area),
        "paint_mesh": "xinyi_road_paint.glb",
        "paint_expected_ue_local_bounds": ue_local_bounds_cm(game),
        "tree_mesh": "xinyi_tree.glb",
        "tree_expected_ue_local_bounds": TREE_BOUNDS,
        "tree_instances": "xinyi_trees.json",
    }
    (OUT / "ground.report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


def write_tree_mesh(path):
    """~120-triangle broadleaf: flattened faceted crown on a hexagonal trunk."""
    t = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
         [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
         [8, 6, 7], [9, 8, 1]]
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    # one subdivision
    mid = {}
    verts = [tuple(x) for x in v]

    def m(a, b):
        k = tuple(sorted((a, b)))
        if k not in mid:
            p = (np.asarray(verts[a]) + np.asarray(verts[b])) / 2
            p /= np.linalg.norm(p)
            verts.append(tuple(p)); mid[k] = len(verts) - 1
        return mid[k]
    f2 = []
    for a, b, c in f:
        ab, bc, ca = m(a, b), m(b, c), m(c, a)
        f2 += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
    V = np.asarray(verts)
    rng = np.random.default_rng(7)
    V *= (1.0 + rng.uniform(-0.12, 0.12, (len(V), 1)))
    crown = V * np.array([3.2, 2.4, 3.2]) + np.array([0, 6.2, 0])   # game frame Y up
    tris = [crown[list(tri)] for tri in f2]
    cols = [(40, 255, 0, 255)] * len(tris)
    # trunk
    ang = np.linspace(0, 2 * np.pi, 7)[:-1]
    for i in range(6):
        a0, a1 = ang[i], ang[(i + 1) % 6]
        p = lambda a, y, r: np.array([np.cos(a) * r, y, np.sin(a) * r])
        q = [p(a0, 0, 0.28), p(a1, 0, 0.28), p(a1, 4.5, 0.2), p(a0, 4.5, 0.2)]
        tris += [np.array([q[0], q[2], q[1]]), np.array([q[0], q[3], q[2]])]
        cols += [(0, 0, 0, 255)] * 2
    P = np.concatenate(tris).astype(np.float32)
    fn = []
    for tri in tris:
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0]); n /= np.linalg.norm(n) + 1e-9
        # bend crown normals outward for a soft, rounded read
        fn += [n] * 3
    N = np.asarray(fn, np.float32)
    C = np.repeat(np.asarray(cols, np.uint8), 3, axis=0)
    idx = np.arange(len(P), dtype=np.uint32).reshape(-1, 3)
    C[:, 0] = np.clip(P[:, 1] / 10.0 * 255.0, 0, 255).astype(np.uint8)   # R = height / 10 m
    write_glb(path, [{"name": "XinyiTree", "positions": P, "normals": N, "uv2": pack_rgba8(C), "indices": idx,
                      "base_color": [0.2, 0.35, 0.15, 1.0]}], mesh_name="SM_XinyiTree")
    return ue_local_bounds_cm(P)


if __name__ == "__main__":
    main()
