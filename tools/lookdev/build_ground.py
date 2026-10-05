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
                          A = surface class (nearest): 1.0 water, 0.8 running
                              track, 0.6 sports court, 0.4 construction,
                              0.3 school yard, 0.2 surface parking, 0 none
  xinyi_road_paint.glb    thin opaque paint geometry draped 6 cm above terrain:
                          lane lines, double-yellow centre lines, red kerb lines,
                          zebra crossings, stop lines, scooter waiting boxes
                          (機車停等區). TEXCOORD_2 = packed RGBA8 paint colour.
  xinyi_trees.json        tree instances (street trees, median trees, parks)
  xinyi_tree.glb          one low-poly broadleaf tree (crown + trunk)
  xinyi_campus_2048.png   School & Campus Identity v0A data texture over the same extent, sampled
                          bilinear without mips (exact masks at every distance):
                          R = Grade-A campus signed distance, 0.5 + d / 32 (+-16 m, > 0.5 inside)
                          G = tagged court / playground signed distance, 0.5 + d / 16 (+-8 m)
                          B = surface palette id * 32 (nearest surface; xc_court_surface)
                          A = 0. Everything outside the campus polygons decodes to "outside".
                          Box-filtered mips; the shader insets the masks by the pixel footprint.
  xinyi_campus_paint.glb  court markings as paint geometry (6 cm above terrain); TEXCOORD_2 R byte =
                          surface id 1..5 (road paint R >= 190; xc_paint court branch)
  campus_ground.json      campuses / surfaces / markings used (audit). No running track is ever
                          produced: OSM has none here and inferred tracks are not render input.
The accepted ground outputs above are written first and are unchanged by the campus layer.
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
import campus_identity as campus_id  # noqa: E402

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
    special = {"track": [], "court": [], "construction": [], "school": [], "parking": []}
    for e in d["elements"]:
        t = e.get("tags", {})
        if e["type"] == "node" and t.get("natural") == "tree":
            trees.append(lonlat_to_enu(e["lon"], e["lat"], lon0, lat0))
        elif e["type"] == "way":
            pts = enu(e["geometry"])
            if len(pts) < 2:
                continue
            closed = e["nodes"][0] == e["nodes"][-1] and len(pts) >= 4
            grass_pitch = t.get("leisure") == "pitch" and t.get("surface") in ("grass", "artificial_turf")
            if closed and not grass_pitch:
                cls = None
                if t.get("leisure") == "track":
                    cls = "track"
                elif t.get("leisure") in ("pitch", "stadium", "sports_centre"):
                    cls = "court"
                elif t.get("landuse") in ("construction", "brownfield"):
                    cls = "construction"
                elif t.get("amenity") in ("school", "university", "college", "kindergarten"):
                    cls = "school"
                elif t.get("amenity") == "parking" and t.get("parking") in (None, "surface"):
                    cls = "parking"
                if cls:
                    q = Polygon(pts).buffer(0)
                    if q.is_valid and not q.is_empty:
                        special[cls].append(q)
                    continue
            green = (t.get("leisure") in ("park", "garden", "playground") or grass_pitch or
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
    return ways, polys_green, polys_water, trees, special


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
    ways, greens, waters, osm_trees, special = load_osm()
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
    # categorical surface classes: painted in priority order, sampled nearest
    cat = Image.new("L", (S, S), 0)
    drc = ImageDraw.Draw(cat)
    for name, val in (("school", 77), ("parking", 51), ("construction", 102), ("court", 153), ("track", 204)):
        for g in special[name]:
            g = g.intersection(extent.buffer(50))
            if not g.is_empty:
                fill(drc, g, val)
    for g in waters:
        g = g.intersection(extent.buffer(50))
        if not g.is_empty:
            fill(drc, g, 255)
    A = np.asarray(cat, dtype=np.float32)[SUPER // 2::SUPER, SUPER // 2::SUPER] / 255.0
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

    # ---- Four Beasts hill forest: 5-crown clumps on real DTM slopes ----------
    forest = []
    step = 16.0
    gx = np.arange(E0 + 8, E1 - 8, step)
    gy = np.arange(N0 + 8, N1 - 8, step)
    for yv in gy:
        for xv in gx:
            x = xv + rng.uniform(-5, 5)
            y = yv + rng.uniform(-5, 5)
            z = float(hf([x], [y])[0])
            dzx = float(hf([x + 4], [y])[0] - hf([x - 4], [y])[0]) / 8.0
            dzy = float(hf([x], [y + 4])[0] - hf([x], [y - 4])[0]) / 8.0
            slope = math.hypot(dzx, dzy)
            if z < 28.0 or (slope < 0.08 and z < 45.0):
                continue
            if bp.contains(Point(x, y)):
                continue
            forest.append({"e": round(x, 2), "n": round(y, 2), "z": round(z - 0.3, 2),
                           "yaw": round(float(rng.uniform(0, 360)), 1),
                           "s": round(float(rng.uniform(0.9, 1.35)), 3), "v": int(rng.integers(0, 3))})
    (OUT / "xinyi_forest.json").write_text(json.dumps({"count": len(forest), "instances": forest}) + "\n")
    forest_bounds = write_forest_clump(OUT / "xinyi_forest_clump.glb")

    # ---- street lamps along real roads (emissive heads, no dynamic lights) ----
    lamps = []
    for w in ways:
        if w["skip"] or w["cls"] < 0.33 or w["base"] == "service":
            continue
        ls = LineString(w["pts"])
        sides = (-1, 1) if (w["width"] >= 10.0 or not w["oneway"]) else (1,)
        spacing = 30.0 if w["cls"] >= 0.66 else 38.0
        for side in sides:
            try:
                off = ls.offset_curve(side * (w["width"] * 0.5 + 0.6))
            except Exception:
                continue
            if off.is_empty or off.geom_type != "LineString" or off.length < 5:
                continue
            pos = rng.uniform(0, spacing)
            while pos < off.length:
                a = off.interpolate(pos)
                b2 = off.interpolate(min(pos + 1.0, off.length))
                heading = math.degrees(math.atan2(b2.y - a.y, b2.x - a.x))
                if E0 + 5 < a.x < E1 - 5 and N0 + 5 < a.y < N1 - 5:
                    z = float(hf([a.x], [a.y])[0])
                    # arm points toward the carriageway centre
                    lamps.append({"e": round(a.x, 2), "n": round(a.y, 2), "z": round(z, 2),
                                  "yaw": round(heading + (90.0 if side < 0 else -90.0), 1),
                                  "s": 1.0 if w["cls"] >= 0.66 else 0.8,
                                  "v": 0 if rng.random() < 0.7 else 3})
                pos += spacing
    (OUT / "xinyi_lamps.json").write_text(json.dumps({"count": len(lamps), "instances": lamps}) + "\n")

    # baked street-lamp light pools (mobile trick: no dynamic lights at night)
    LRES = 1024
    lpx = (E1 - E0) / LRES
    light = np.zeros((LRES, LRES), np.float64)
    ker_r = 26.0
    kr = int(math.ceil(ker_r / lpx))
    ky, kx = np.mgrid[-kr:kr + 1, -kr:kr + 1]
    kd = np.hypot(kx, ky) * lpx
    for lm in lamps:
        # pool centred ~2 m over the carriageway from the pole
        yaw = math.radians(lm["yaw"])
        cx = lm["e"] + math.cos(yaw) * 2.0
        cy = lm["n"] + math.sin(yaw) * 2.0
        ix = int((cx - E0) / lpx); iy = int((N1 - cy) / lpx)
        k = lm["s"] / (1.0 + (kd / (5.0 * lm["s"])) ** 2) ** 1.5 * (kd < ker_r)
        y0, y1 = max(0, iy - kr), min(LRES, iy + kr + 1)
        x0, x1 = max(0, ix - kr), min(LRES, ix + kr + 1)
        if y0 >= y1 or x0 >= x1:
            continue
        light[y0:y1, x0:x1] += k[y0 - (iy - kr):y1 - (iy - kr), x0 - (ix - kr):x1 - (ix - kr)]
    light = np.sqrt(1.0 - np.exp(-light * 0.9))          # soft saturation; sqrt: 8-bit precision in the dark
    Image.fromarray((light * 255 + 0.5).astype(np.uint8), "L").save(OUT / "xinyi_ground_light_1024.png", optimize=True)
    lamp_bounds = write_lamp_mesh(OUT / "xinyi_lamp.glb")
    campus = build_campus_layer(hf, bpolys)
    report = {
        "texture": "xinyi_ground_2048.png", "resolution": RES, "metres_per_px": (E1 - E0) / RES,
        "extent_enu_m": [E0, E1, N0, N1], "sdf_range_m": SDF_RANGE_M,
        "road_ways": sum(1 for w in ways if not w["skip"]), "junctions": len(junctions),
        "crossings": crossings, "paint_triangles": int(len(faces)), "trees": len(inst),
        "road_area_m2": float(roads.area),
        "surface_classes": {k: len(v) for k, v in special.items()},
        "paint_mesh": "xinyi_road_paint.glb",
        "paint_expected_ue_local_bounds": ue_local_bounds_cm(game),
        "tree_mesh": "xinyi_tree.glb",
        "tree_expected_ue_local_bounds": TREE_BOUNDS,
        "tree_instances": "xinyi_trees.json",
        "forest_clumps": len(forest),
        "forest_mesh": "xinyi_forest_clump.glb",
        "forest_expected_ue_local_bounds": forest_bounds,
        "forest_instances": "xinyi_forest.json",
        "lamps": len(lamps),
        "lamp_mesh": "xinyi_lamp.glb",
        "lamp_expected_ue_local_bounds": lamp_bounds,
        "lamp_instances": "xinyi_lamps.json",
        "lamp_light_texture": "xinyi_ground_light_1024.png",
        "campus": campus,
    }
    (OUT / "ground.report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


# ------------------------------------------------------------------ campus ---
COURT_LINE_W = 0.15          # real lines are 5 cm; 15 cm keeps them readable at low-flight range (xc_paint)
# standard court markings in court-local metres (x along the long axis, y across):
# (length, width, [polylines]); lines are mirrored for both halves where the sport is symmetric
STANDARD_COURTS = {"basketball": (28.0, 15.0), "volleyball": (18.0, 9.0), "tennis": (23.77, 10.97),
                   "badminton": (13.4, 6.1)}
SPORT_ALIAS = {"multi": "basketball"}     # Taiwanese 綜合球場: basketball markings


def _arc(cx, cy, r, a0, a1, n=20):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def _rect(hl, hw):
    return [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw), (-hl, -hw)]


def court_markings(sport):
    """Polylines of a standard court of `sport` centred at the origin (court-local metres)."""
    L, W = STANDARD_COURTS[sport]
    hl, hw = L / 2, W / 2
    lines = [_rect(hl, hw), [(0.0, -hw), (0.0, hw)]]
    if sport == "basketball":
        lines.append(_arc(0, 0, 1.8, 0, 2 * math.pi, 32))
        for sgn in (-1, 1):
            bx = sgn * (hl - 1.575)
            lines.append([(sgn * hl, -2.45), (sgn * (hl - 5.8), -2.45), (sgn * (hl - 5.8), 2.45), (sgn * hl, 2.45)])
            ftx = sgn * (hl - 5.8)       # free-throw semicircle on the court side
            lines.append([(ftx - sgn * 1.8 * math.cos(t), 1.8 * math.sin(t))
                          for t in np.linspace(-math.pi / 2, math.pi / 2, 17)])
            # 3-point line: corner straights 6.6 m off the axis, arc r 6.75 m around the basket
            phi = math.acos(math.sqrt(6.75 ** 2 - 6.6 ** 2) / 6.75)
            arc = [(bx - sgn * 6.75 * math.cos(t), 6.75 * math.sin(t)) for t in np.linspace(-phi, phi, 29)]
            lines.append([(sgn * hl, -6.6)] + arc + [(sgn * hl, 6.6)])
    elif sport == "volleyball":
        lines += [[(-3.0, -hw), (-3.0, hw)], [(3.0, -hw), (3.0, hw)]]
    elif sport == "tennis":
        s_ = 4.115
        lines += [[(-hl, -s_), (hl, -s_)], [(-hl, s_), (hl, s_)], [(-6.40, -s_), (-6.40, s_)], [(6.40, -s_), (6.40, s_)],
                  [(-6.40, 0.0), (6.40, 0.0)]]
    elif sport == "badminton":
        s_ = 2.53
        lines += [[(-hl, -s_), (hl, -s_)], [(-hl, s_), (hl, s_)], [(-1.98, -hw), (-1.98, hw)], [(1.98, -hw), (1.98, hw)],
                  [(-hl + 0.76, -hw), (-hl + 0.76, hw)], [(hl - 0.76, -hw), (hl - 0.76, hw)],
                  [(-hl, 0.0), (-1.98, 0.0)], [(1.98, 0.0), (hl, 0.0)]]
    return lines


def plan_markings(rec):
    """Marking plan for one tagged surface, from its real rectangle (no inferred sport / layout).

    Standard markings only when the sport is tagged, the pitch is clearly elongated (long / short >= 1.3,
    so the long axis is unambiguous) and the standard court fits at >= 85 % scale; otherwise only the
    real pitch boundary is drawn (the outline itself is drawn analytically by the ground shader from the
    court signed distance, for every surface)."""
    sport = SPORT_ALIAS.get(rec["sport"], rec["sport"])
    L, W = rec["length_m"], rec["width_m"]
    if rec["kind"] != "pitch":
        return {"mode": "none", "reason": "playground: surface only"}
    if sport in STANDARD_COURTS and L / max(W, 1e-6) >= 1.3:
        Ls, Ws = STANDARD_COURTS[sport]
        f = min(1.0, (L - 0.4) / Ls, (W - 0.4) / Ws)
        if f >= 0.85:
            return {"mode": "standard", "sport": sport, "scale": round(f, 4)}
        return {"mode": "boundary", "reason": "standard %s court does not fit (scale %.2f)" % (sport, f)}
    if sport in STANDARD_COURTS:
        return {"mode": "boundary", "reason": "near-square pitch (%.1f x %.1f m): court axis ambiguous" % (L, W)}
    return {"mode": "boundary", "reason": "sport not tagged" if not rec["sport"] else "no standard markings for %s" % sport}


def build_campus_layer(hf, wfs_polys):
    """Grade-A campus yard / court data texture + court marking paint (see module docstring)."""
    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    edu = campus_id.edu_features(lon0, lat0)
    wm_b = unary_union(wfs_polys)
    src_bbox = box(*wm_b.bounds)
    campuses = campus_id.grade_a_campuses(edu, src_bbox)
    surfaces, rejected = campus_id.sports_surfaces(campuses, edu, wfs_polys)
    # tracks are never drawn here (only a future curated, cited override may add one); count what is ignored
    osm_tracks = sum(1 for f in edu if f["tags"].get("leisure") == "track"
                     or any(k in str(f["tags"].get("sport", "")) for k in ("athletics", "running")))
    import shapely
    px = (E1 - E0) / RES
    img = np.zeros((RES, RES, 4), np.uint8)
    for c in campuses:
        g = c["geom"]
        x0, y0, x1, y1 = g.buffer(20.0).bounds
        i0, i1 = max(0, int((x0 - E0) / px)), min(RES, int(math.ceil((x1 - E0) / px)))
        j0, j1 = max(0, int((N1 - y1) / px)), min(RES, int(math.ceil((N1 - y0) / px)))
        ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1))
        xs, ys = E0 + (ii + 0.5) * px, N1 - (jj + 0.5) * px
        inside = shapely.contains_xy(g, xs, ys)
        d = shapely.distance(g.boundary, shapely.points(xs, ys))
        d = np.where(inside, d, -d)
        val = np.clip(np.floor((0.5 + np.clip(d, -16.0, 16.0) / 32.0) * 255.0 + 0.5), 0, 255).astype(np.uint8)
        img[j0:j1, i0:i1, 0] = np.maximum(img[j0:j1, i0:i1, 0], val)
        mine = [sf for sf in surfaces if sf["campus"] == c["id"]]
        if mine:
            dd = np.full(xs.shape, -1e9)
            near = np.full(xs.shape, 1e9)
            sid = np.zeros(xs.shape, np.uint8)
            for sf in mine:
                sg = sf["geom"]
                ins = shapely.contains_xy(sg, xs, ys)
                ds = shapely.distance(sg.boundary, shapely.points(xs, ys))
                sd = np.where(ins, ds, -ds)
                dd = np.maximum(dd, sd)
                closer = np.abs(np.minimum(sd, 0.0)) < near
                sid = np.where(closer, sf["surface_id"], sid)
                near = np.minimum(near, np.abs(np.minimum(sd, 0.0)))
            gv = np.clip(np.floor((0.5 + np.clip(dd, -8.0, 8.0) / 16.0) * 255.0 + 0.5), 0, 255).astype(np.uint8)
            img[j0:j1, i0:i1, 1] = np.maximum(img[j0:j1, i0:i1, 1], np.where(inside, gv, 0))
            img[j0:j1, i0:i1, 2] = np.where(inside, sid * 32, img[j0:j1, i0:i1, 2])
    Image.fromarray(img, "RGBA").save(OUT / "xinyi_campus_2048.png", optimize=True)

    # court markings as paint geometry, laid on the real pitch rectangle
    paint = Paint(hf)
    plans = []
    for sf in surfaces:
        plan = plan_markings(sf)
        g = sf["geom"]
        cx, cy = sf["centre"]
        ax = np.array(sf["axis"])
        ay = np.array([-ax[1], ax[0]])
        color = (sf["surface_id"], 0, 0, 255)       # R = surface id (xc_paint court branch)

        def world(pts, f=1.0):
            return [(cx + ax[0] * x * f + ay[0] * y * f, cy + ax[1] * x * f + ay[1] * y * f) for x, y in pts]
        if plan["mode"] == "standard":
            for ln in court_markings(plan["sport"]):
                paint.polyline(world(ln, plan["scale"]), 0.0, COURT_LINE_W, color)
        plans.append({k: v for k, v in sf.items() if k != "geom"} | {"markings": plan})
    game, colr, faces = paint.arrays()
    write_glb(OUT / "xinyi_campus_paint.glb", [{
        "name": "XinyiRoadPaint", "positions": game,
        "normals": np.tile(np.array([[0, 1, 0]], np.float32), (len(game), 1)),
        "uv2": pack_rgba8(colr), "indices": faces, "base_color": [0.9, 0.9, 0.9, 1.0],
    }], mesh_name="SM_XinyiCampusPaint")
    doc = {"schema": "acw.campus_ground/0", "campuses": [{k: c[k] for k in ("id", "name", "level", "bbox_coverage")}
                                                         for c in campuses],
           "surfaces": plans, "rejected_surfaces": rejected, "running_tracks": 0, "osm_track_features_ignored": osm_tracks,
           "track_policy": "no leisure=track / sport=athletics in the source; inferred tracks are never drawn"}
    (OUT / "campus_ground.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"texture": "xinyi_campus_2048.png", "paint_mesh": "xinyi_campus_paint.glb",
            "paint_expected_ue_local_bounds": ue_local_bounds_cm(game), "paint_triangles": int(len(faces)),
            "campuses": len(campuses), "surfaces": len(surfaces), "rejected_surfaces": len(rejected),
            "running_tracks": 0, "audit": "campus_ground.json"}


def _ico():
    t = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
         [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
         [8, 6, 7], [9, 8, 1]]
    return v, f


def _write_tris(path, tris, uv2, name, mesh_name):
    P = np.concatenate(tris).astype(np.float32)
    N = []
    for tri in tris:
        n = np.cross(tri[1] - tri[0], tri[2] - tri[0]); n /= np.linalg.norm(n) + 1e-9
        N += [n] * 3
    idx = np.arange(len(P), dtype=np.uint32).reshape(-1, 3)
    write_glb(path, [{"name": name, "positions": P, "normals": np.asarray(N, np.float32),
                      "uv2": uv2(P), "indices": idx}], mesh_name=mesh_name)
    return ue_local_bounds_cm(P)


def write_forest_clump(path):
    """Five-crown canopy clump (100 tris): one instance per ~16 m of hillside."""
    v, f = _ico()
    rng = np.random.default_rng(11)
    tris = []
    for k in range(5):
        a = 2 * math.pi * k / 5 + rng.uniform(-0.3, 0.3)
        r = 0.0 if k == 0 else rng.uniform(4.0, 6.5)
        c = np.array([math.cos(a) * r, rng.uniform(5.5, 8.5), math.sin(a) * r])
        sc = np.array([rng.uniform(3.2, 4.4), rng.uniform(2.6, 3.6), rng.uniform(3.2, 4.4)])
        vv = v * (1.0 + rng.uniform(-0.15, 0.15, (len(v), 1))) * sc + c
        tris += [vv[list(t)] for t in f]
    return _write_tris(path, tris, lambda P: np.column_stack([np.clip(P[:, 1] / 10.0, 0, 1),
                                                               np.ones(len(P))]).astype(np.float32),
                       "XinyiTree", "SM_XinyiForestClump")


def write_lamp_mesh(path):
    """Street lamp: pole + arm + emissive head (32 tris). TEXCOORD_2 packed (type 10, part)."""
    boxes = [((0, 4.5, 0), (0.18, 9.0, 0.18), 0), ((1.1, 8.9, 0), (2.2, 0.12, 0.12), 0),
             ((2.1, 8.75, 0), (0.7, 0.18, 0.32), 1)]
    tris, parts = [], []
    for (cx, cy, cz), (sx, sy, sz), part in boxes:
        x0, x1, y0, y1, z0, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, cz - sz / 2, cz + sz / 2
        quads = [[(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)],
                 [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
                 [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],
                 [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                 [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
                 [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]]
        for q in quads:
            q = np.asarray(q, float)
            tris += [q[[0, 1, 2]], q[[0, 2, 3]]]
            parts += [part, part]
    part_per_vertex = np.repeat(np.asarray(parts), 3)

    def uv2(P):
        rgba = np.column_stack([np.full(len(P), 10), part_per_vertex, np.zeros(len(P)), np.full(len(P), 255)])
        return pack_rgba8(rgba.astype(np.uint8))
    return _write_tris(path, tris, uv2, "XinyiRoofProp", "SM_XinyiStreetLamp")


def write_tree_mesh(path):
    """28-triangle broadleaf: jittered icosahedron crown on a 4-sided trunk."""
    t = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
         [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10],
         [8, 6, 7], [9, 8, 1]]
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    # no subdivision: 20-face crown keeps 20k street trees affordable on
    # iPhone-class GPUs; jitter + shading carry the leafy read
    verts = [tuple(x) for x in v]
    f2 = f
    V = np.asarray(verts)
    rng = np.random.default_rng(7)
    V *= (1.0 + rng.uniform(-0.12, 0.12, (len(V), 1)))
    crown = V * np.array([3.2, 2.4, 3.2]) + np.array([0, 6.2, 0])   # game frame Y up
    tris = [crown[list(tri)] for tri in f2]
    cols = [(40, 255, 0, 255)] * len(tris)
    # trunk
    ang = np.linspace(0, 2 * np.pi, 5)[:-1]
    for i in range(4):
        a0, a1 = ang[i], ang[(i + 1) % 4]
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
    # plain floats (height varies per vertex): x = height / 10 m, y = crown flag
    uv2 = np.column_stack([np.clip(P[:, 1] / 10.0, 0, 1), C[:, 1] / 255.0]).astype(np.float32)
    write_glb(path, [{"name": "XinyiTree", "positions": P, "normals": N, "uv2": uv2, "indices": idx,
                      "base_color": [0.2, 0.35, 0.15, 1.0]}], mesh_name="SM_XinyiTree")
    return ue_local_bounds_cm(P)


if __name__ == "__main__":
    main()
