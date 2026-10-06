"""Taipei Street Reality v0C: curb-zone truth (road-edge pedestrian class + scooter stall rows).

Called by build_ground.py with the road ways / junctions / footprints it has already built. Inputs beyond those:
the locked OSM cache (mapped sidewalks, road sidewalk=* tags, crossing ways), the frontage roles baked into the
look tiles (urban_identity/frontage_roles.json.gz) and look_buildings.jsonl.gz (archetypes).

1. Road-side pedestrian class, sampled every ~5 m along each side of every drivable way:
     SIDEWALK  a mapped footway=sidewalk runs parallel within W/2 - 1.5 .. W/2 + 9 m and that road's kerb is
               the nearest one to it (a parallel arterial's sidewalk never lands on an alley), or the road
               carries sidewalk=both / left / right / separate (or sidewalk:<side>), or the road is an unmapped
               trunk / primary / secondary / tertiary (not *_link) not tagged sidewalk=no (mapped geometry
               beats the tag: sidewalk=no next to a separately mapped sidewalk is still a sidewalk).
               service ways (alleys, driveways, aisles) never get a raised sidewalk.
     ARCADE    no sidewalk, but old-stock commercial frontage (roles 5-7 on low / walk-up / huaxia: the walls the
               shader paints a 騎樓 arcade on) faces the side: owner-built apron in front of the arcade
     NONE      everything else (residential / unclassified / living_street / service, *_link, sidewalk=no):
               the lane's asphalt runs on to the building line
   Sidewalk evidence gaps <= 15 m are bridged, isolated evidence < 10 m is dropped; same for arcade frontage.
   Raster: every half-carriageway carries its class and every ground pixel takes the class of the nearest
   half-carriageway (Voronoi), so a side's class never leaks across its carriageway. Encoded 0 / 0.5 / 1 in the
   campus texture alpha (xc_ground ct.w). No per-street exceptions.

2. Scooter stall rows (機車停車格, white painted bays on the road edge), placed only from frontage:
   curb segments = frontage edges (roles 2-7; role 2 only on real lanes) projected onto their road side and
   merged; per segment a deterministic chance by role, then runs of 4-16 bays (1.2 m pitch x 2.0 m deep,
   perpendicular to the kerb) with 2.5-9 m gaps. A bay is dropped when it would be
     * within (cross-road half width + 10 m) of a real junction, (+4 m) of a lane mouth, (+2 m) of a driveway /
       parking-aisle / access way meeting the road on that side, or within 4 m of a mapped crossing;
     * overlapping another bay (inside of a tight bend, a neighbouring road's row), touching a building
       footprint (repaired, holes kept), another road's carriageway, school / campus / court / parking /
       construction ground, a street tree or lamp pole, or within 0.3 m of a mapped sidewalk line;
     * leaving less than 3.5 m (two-way) / 3.0 m (one-way) / 2.6 m (lane) of clear carriageway.
   Bay position by side class: sidewalk side - the bay ends 0.25 m short of the kerb; arcade side - up to
   0.4 m outward (stays off the apron); no-sidewalk side - shifted outward into the asphalt band toward the
   building line (keeps >= 0.7 m from the wall, <= 1.6 m past the carriageway edge).
   Per-row RNG seeded by the sha256 of the curb segment id; no global random state.

Outputs: urban_identity/curb_segments.json.gz (acw.curb_segments/0: side classes, segments, rows, bays);
the bays feed the scooter instances in build_street_identity.py.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring, unary_union
from shapely.strtree import STRtree

NONE, ARCADE, SIDEWALK = 0, 1, 2
CLASS_NAME = {NONE: "none", ARCADE: "arcade", SIDEWALK: "sidewalk"}
CLASS_ALPHA = {NONE: 0, ARCADE: 128, SIDEWALK: 255}
DEFAULT_SIDEWALK = {"trunk", "primary", "secondary", "tertiary"}
OLD_ARCH = {0, 1, 2}                 # low / walk-up / huaxia (xc_wall isOld: arcade on commercial frontage)
ARCH_CIVIC, ARCH_SCHOOL = 6, 7
SAMPLE_M = 5.0
FILL_GAP = 3                         # samples (15 m)
MIN_RUN = 2                          # samples (10 m)

PITCH = 1.2                          # bay width along the kerb (legal 1-1.5 m)
DEPTH = 2.0                          # bay depth, perpendicular to the kerb
LINE_W = 0.12
ROW_P = {7: 0.45, 6: 0.45, 5: 0.35, 4: 0.22, 3: 0.22, 2: 0.12}      # chance a curb segment hosts bay rows
RUN_BAYS = (4, 16)
RUN_GAP_M = (2.5, 9.0)
MIN_CLEAR = {"two_way": 3.5, "one_way": 3.0, "lane": 2.6}
JUNCTION_CLEAR = 10.0
LANE_MOUTH_CLEAR = 4.0
ACCESS_CLEAR = 2.0
CROSSING_CLEAR = 4.0


def seeded(*key):
    return random.Random(int.from_bytes(hashlib.sha256("|".join(map(str, key)).encode()).digest()[:8], "big"))


def is_lane(w):
    t = w["tags"]
    if t.get("highway") != "service":
        return False
    name = t.get("name:zh") or t.get("name") or ""
    return t.get("service") == "alley" or (t.get("service") is None and ("巷" in name or "弄" in name))


def tag_sides(t):
    """OSM sidewalk tags -> {+1 (left), -1 (right)}: True / False / None (untagged)."""
    out = {1: None, -1: None}
    v = t.get("sidewalk")
    yes = ("yes", "both", "separate")
    if v in yes:
        out = {1: True, -1: True}
    elif v == "left":
        out = {1: True, -1: False}
    elif v == "right":
        out = {1: False, -1: True}
    elif v in ("no", "none"):
        out = {1: False, -1: False}
    b = t.get("sidewalk:both")
    if b is not None:
        out = {1: b in yes, -1: b in yes}
    for k, s in (("sidewalk:left", 1), ("sidewalk:right", -1)):
        if t.get(k) is not None:
            out[s] = t[k] in yes
    return out


def smooth(flags, fill_gap, min_run):
    """Bridge False gaps <= fill_gap between True runs, then drop True runs shorter than min_run."""
    f = list(flags)
    n = len(f)
    i = 0
    while i < n:
        if not f[i]:
            j = i
            while j < n and not f[j]:
                j += 1
            if 0 < i and j < n and j - i <= fill_gap:
                for k in range(i, j):
                    f[k] = True
            i = j
        else:
            i += 1
    i = 0
    while i < n:
        if f[i]:
            j = i
            while j < n and f[j]:
                j += 1
            if j - i < min_run:
                for k in range(i, j):
                    f[k] = False
            i = j
        else:
            i += 1
    return f


class WayFrame:
    """Arc-length frame of a way centreline."""

    def __init__(self, pts):
        self.line = LineString(pts)
        self.L = self.line.length

    def at(self, s):
        s = min(max(s, 0.0), self.L)
        p = self.line.interpolate(s)
        a = self.line.interpolate(max(0.0, s - 0.75))
        b = self.line.interpolate(min(self.L, s + 0.75))
        t = np.array([b.x - a.x, b.y - a.y])
        t /= max(np.linalg.norm(t), 1e-9)
        return np.array([p.x, p.y]), t, np.array([-t[1], t[0]])     # point, tangent, left normal


def load_osm_lines(osm_doc, enu):
    sidewalks, crossings = [], []
    for e in osm_doc["elements"]:
        if e["type"] != "way":
            continue
        t = e.get("tags", {})
        if t.get("footway") == "sidewalk":
            pts = enu(e["geometry"])
            if len(pts) >= 2:
                sidewalks.append(LineString(pts))
        elif t.get("footway") == "crossing" or t.get("crossing") is not None and t.get("highway") == "footway":
            pts = enu(e["geometry"])
            if len(pts) >= 2:
                crossings.append(LineString(pts))
    return sidewalks, crossings


def side_classes(ways, sidewalks, arcade_marks):
    """Per (way id, side): list of (s0, s1, class) runs covering the whole centreline."""
    stree = STRtree(sidewalks) if sidewalks else None
    wlines = [LineString(w["pts"]) for w in ways]
    wtree = STRtree(wlines)

    def nearest_kerb(q, own):
        """True when way `own`'s kerb is (within 0.5 m) the nearest kerb to point q."""
        d_own = wlines[own].distance(q) - ways[own]["width"] / 2
        for i in wtree.query(q.buffer(14.0)):
            i = int(i)
            if i != own and wlines[i].distance(q) - ways[i]["width"] / 2 < d_own - 0.5:
                return False
        return True
    out = {}
    stats = Counter()
    for wi, w in enumerate(ways):
        if w["skip"]:
            continue
        fr = WayFrame(w["pts"])
        if fr.L < 0.5:
            continue
        W = w["width"]
        n = max(1, int(round(fr.L / SAMPLE_M)))
        ss = [(i + 0.5) * fr.L / n for i in range(n)]
        tags = tag_sides(w["tags"])
        for side in (1, -1):
            ev = []
            for s in ss:
                p, t, nl = fr.at(s)
                nn = nl * side
                hit = False
                if stree is not None:
                    probe = LineString([tuple(p + nn * (W / 2 - 1.5)), tuple(p + nn * (W / 2 + 9.0))])
                    for i in stree.query(probe):
                        ln = sidewalks[int(i)]
                        x = ln.intersection(probe)
                        if x.is_empty:
                            continue
                        pts = [x] if x.geom_type == "Point" else [g for g in getattr(x, "geoms", []) if g.geom_type == "Point"]
                        for q in pts:
                            pr = ln.project(q)
                            a = ln.interpolate(max(0.0, pr - 1.0))
                            b = ln.interpolate(min(ln.length, pr + 1.0))
                            v = np.array([b.x - a.x, b.y - a.y])
                            if abs(float(np.dot(v, t))) / max(np.linalg.norm(v), 1e-9) >= 0.9 and nearest_kerb(q, wi):
                                hit = True
                                break
                        if hit:
                            break
                ev.append(hit)
            ev = smooth(ev, FILL_GAP, MIN_RUN)
            arc = smooth([any(a <= s <= b for a, b in arcade_marks.get((w["id"], side), ())) for s in ss], 2, MIN_RUN)
            base = w["base"]
            default_sw = base in DEFAULT_SIDEWALK and not w["tags"]["highway"].endswith("_link")
            cls = []
            for k in range(n):
                if base == "service":
                    c = ARCADE if arc[k] else NONE
                    why = "service"
                elif ev[k]:
                    c, why = SIDEWALK, "mapped"
                elif tags[side] is False:
                    c = ARCADE if arc[k] else NONE
                    why = "tag_no"
                elif tags[side] is True:
                    c, why = SIDEWALK, "tagged"
                elif default_sw:
                    c, why = SIDEWALK, "default_major"
                else:
                    c = ARCADE if arc[k] else NONE
                    why = "arcade" if arc[k] else "none"
                cls.append(c)
                stats[f"{base}|{why}"] += fr.L / n
            runs = []
            for k, c in enumerate(cls):
                s0 = 0.0 if k == 0 else (ss[k - 1] + ss[k]) / 2
                s1 = fr.L if k == n - 1 else (ss[k] + ss[k + 1]) / 2
                if runs and runs[-1][2] == c:
                    runs[-1][1] = s1
                else:
                    runs.append([s0, s1, c])
            out[(w["id"], side)] = runs
    return out, stats


def rasterise_classes(ways, runs, extent, res):
    """Class per ground pixel (nearest half-carriageway), 2x supersampled -> uint8 alpha (res x res)."""
    E0, E1, N0, N1 = extent
    S = res * 2
    px = (E1 - E0) / S
    img = Image.new("L", (S, S), 0)
    dr = ImageDraw.Draw(img)

    def to_px(cs):
        return [((x - E0) / px, (N1 - y) / px) for x, y in cs]

    by_id = {w["id"]: w for w in ways}
    for c in (NONE, ARCADE, SIDEWALK):                 # sidewalk drawn last: wins in shared junction boxes
        for (wid, side), rr in runs.items():
            w = by_id[wid]
            line = LineString(w["pts"])
            for s0, s1, cc in rr:
                if cc != c or s1 - s0 < 0.05:
                    continue
                sub = substring(line, s0, s1)
                if sub.length < 0.05:
                    continue
                g = sub.buffer(side * w["width"] * 0.5, single_sided=True, cap_style="flat")
                gs = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
                for q in gs:
                    if q.geom_type == "Polygon" and not q.is_empty:
                        dr.polygon(to_px(q.exterior.coords), fill=c + 1)
    a = np.asarray(img)
    valued = a > 0
    _, (iy, ix) = ndimage.distance_transform_edt(~valued, return_indices=True)
    cls = a[iy, ix].astype(np.int16) - 1
    lut = np.array([CLASS_ALPHA[NONE], CLASS_ALPHA[ARCADE], CLASS_ALPHA[SIDEWALK]], np.float32)
    alpha = lut[np.clip(cls, 0, 2)]
    alpha = alpha.reshape(res, 2, res, 2).mean(axis=(1, 3))
    return np.clip(alpha + 0.5, 0, 255).astype(np.uint8)


def frontage_contribs(roles, look, ways_by_id):
    """Frontage edges -> (road id, side) intervals: [(s0, s1, role, curb_m, building_id, arcade)]."""
    out = defaultdict(list)
    for b in sorted(roles["buildings"], key=lambda x: x["building_id"]):
        rec = look.get(b["building_id"])
        if rec is None:
            continue
        arch = rec["archetype"]
        civic = arch in (ARCH_CIVIC, ARCH_SCHOOL) or bool(rec["flags"] & 8)
        for e in b["edges"]:
            w = ways_by_id.get(e["road_id"])
            if w is None or w["skip"]:
                continue
            role = e["role"]
            if role < 2:
                continue
            line = LineString(w["pts"])
            p0, p1 = np.array(e["p0"], float), np.array(e["p1"], float)
            m = (p0 + p1) / 2
            sm = line.project(Point(m))
            q = line.interpolate(sm)
            a = line.interpolate(max(0.0, sm - 0.75))
            bb = line.interpolate(min(line.length, sm + 0.75))
            t = np.array([bb.x - a.x, bb.y - a.y])
            side = 1 if (t[0] * (m[1] - q.y) - t[1] * (m[0] - q.x)) > 0 else -1
            s0, s1 = sorted((line.project(Point(p0)), line.project(Point(p1))))
            if s1 - s0 < 0.5:
                continue
            out[(w["id"], side)].append({"s0": s0, "s1": s1, "role": role, "curb_m": float(e["curb_m"]),
                                         "bid": b["building_id"], "civic": civic,
                                         "arcade": role >= 5 and arch in OLD_ARCH and not civic,
                                         "lane_ok": role != 2 or is_lane(w)})
    return out


def merge_segments(contribs, gap=4.0):
    segs = []
    for c in sorted(contribs, key=lambda x: (x["s0"], x["s1"])):
        if c["civic"] or not c["lane_ok"]:
            continue
        if segs and c["s0"] - segs[-1]["s1"] <= gap:
            g = segs[-1]
            g["s1"] = max(g["s1"], c["s1"])
            g["parts"].append(c)
        else:
            segs.append({"s0": c["s0"], "s1": c["s1"], "parts": [c]})
    for g in segs:
        lens = Counter()
        for c in g["parts"]:
            lens[c["role"]] += c["s1"] - c["s0"]
        g["role"] = max(lens.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return segs


def build(ways, junctions, node_pos, bpolys, osm_doc, enu, roles, look, special, campus_polys, trees, lamps,
          extent, res, paint, paint_colours):
    """Compute the curb layer; adds stall paint to `paint`; returns (alpha, doc, row_clip, report)."""
    ways_ok = [w for w in ways if not w["skip"]]
    by_id = {w["id"]: w for w in ways_ok}
    sidewalks, crossings = load_osm_lines(osm_doc, enu)
    contribs = frontage_contribs(roles, look, by_id)
    arcade_marks = {k: [(c["s0"] - 1.0, c["s1"] + 1.0) for c in v if c["arcade"]] for k, v in contribs.items()}
    runs, class_stats = side_classes(ways_ok, sidewalks, arcade_marks)
    alpha = rasterise_classes(ways_ok, runs, extent, res)

    # ---------------------------------------------------------------- exclusions -------------------------
    road_polys = [LineString(w["pts"]).buffer(w["width"] * 0.5, cap_style="flat") for w in ways_ok]
    road_idx = {w["id"]: i for i, w in enumerate(ways_ok)}
    rtree = STRtree(road_polys)
    btree = STRtree(bpolys)
    sp_list = [g for k in ("school", "court", "track", "construction", "parking") for g in special.get(k, [])]
    sp_list += [g.buffer(1.0) for g in campus_polys]
    sptree = STRtree(sp_list) if sp_list else None
    swtree = STRtree(sidewalks) if sidewalks else None
    pole_pts = [Point(x, y).buffer(0.5) for x, y, _k in trees] + [Point(l["e"], l["n"]).buffer(0.35) for l in lamps]
    poletree = STRtree(pole_pts) if pole_pts else None
    ctree = STRtree(crossings) if crossings else None

    def forbidden(w, side):
        """Arc-length intervals of a way side where no bay may start / end, + real junction nodes (on a curved
        road the straight-line distance to the junction is shorter than the arc length, so both are checked)."""
        line = LineString(w["pts"])
        iv = []
        majors = []
        cum = [0.0]
        for a, b in zip(w["pts"][:-1], w["pts"][1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        for i, nid in enumerate(w["nodes"]):
            if nid not in junctions:
                continue
            s_node = cum[i]
            for ow, oi in junctions[nid]:
                if ow is w:
                    continue
                if ow["base"] != "service" and ow["cls"] >= 0.33:
                    c, both = ow["width"] / 2 + JUNCTION_CLEAR, True
                    majors.append((Point(node_pos[nid]), c))
                elif is_lane(ow):
                    c, both = ow["width"] / 2 + LANE_MOUTH_CLEAR, True
                else:
                    c, both = ow["width"] / 2 + ACCESS_CLEAR, False
                if not both:
                    # which side of this way does the access way leave on?
                    j = oi + 1 if oi + 1 < len(ow["pts"]) else oi - 1
                    q = np.array(ow["pts"][j], float)
                    p = np.array(node_pos[nid], float)
                    _, t, nl = WayFrame(w["pts"]).at(s_node)
                    if float(np.dot(q - p, nl)) * side < 0:
                        continue
                iv.append((s_node - c, s_node + c))
        if ctree is not None:
            for i in ctree.query(line.buffer(w["width"])):
                x = crossings[int(i)].intersection(line)
                pts = [x] if x.geom_type == "Point" else [g for g in getattr(x, "geoms", []) if g.geom_type == "Point"]
                for q in pts:
                    s = line.project(q)
                    iv.append((s - CROSSING_CLEAR, s + CROSSING_CLEAR))
        return iv, majors

    def clear_of(poly, own):
        if any(bpolys[int(i)].intersects(poly) for i in btree.query(poly)):
            return "building"
        for i in rtree.query(poly):
            i = int(i)
            if i != own and road_polys[i].intersection(poly).area > 0.05:
                return "other_road"
        if sptree is not None and any(sp_list[int(i)].intersects(poly) for i in sptree.query(poly)):
            return "special_ground"
        if poletree is not None and any(pole_pts[int(i)].intersects(poly) for i in poletree.query(poly)):
            return "tree_or_lamp"
        if swtree is not None and any(sidewalks[int(i)].distance(poly) < 0.3 for i in swtree.query(poly.buffer(0.3))):
            return "mapped_sidewalk"
        return None

    # ---------------------------------------------------------------- bays ------------------------------
    segs_all = []
    for (wid, side), cs in contribs.items():
        w = by_id[wid]
        for k, g in enumerate(merge_segments(cs)):
            g.update({"road_id": wid, "side": side, "id": "%d|%+d|%.1f" % (wid, side, g["s0"])})
            segs_all.append(g)
    # commercial curbs claim the carriageway first; ties broken by the segment-id hash
    segs_all.sort(key=lambda g: (-g["role"], hashlib.sha256(g["id"].encode()).hexdigest()))
    intrusion = defaultdict(lambda: defaultdict(float))      # (way, side) -> 1 m bin -> carriageway intrusion
    rows, bays, reject = [], [], Counter()
    seg_doc = []
    row_polys = defaultdict(list)                            # (way, side) -> bay polygons (red-line clip)
    bay_grid = defaultdict(list)                             # 5 m cell -> placed bay polygons (any row)

    def overlaps_bay(poly):
        x0, y0, x1, y1 = poly.bounds
        for gx in range(int(math.floor(x0 / 5.0)), int(math.floor(x1 / 5.0)) + 1):
            for gy in range(int(math.floor(y0 / 5.0)), int(math.floor(y1 / 5.0)) + 1):
                if any(q.intersection(poly).area > 0.005 for q in bay_grid[(gx, gy)]):
                    return True
        return False

    def add_bay(poly):
        x0, y0, x1, y1 = poly.bounds
        for gx in range(int(math.floor(x0 / 5.0)), int(math.floor(x1 / 5.0)) + 1):
            for gy in range(int(math.floor(y0 / 5.0)), int(math.floor(y1 / 5.0)) + 1):
                bay_grid[(gx, gy)].append(poly)
    for g in segs_all:
        w = by_id[g["road_id"]]
        side = g["side"]
        rng = seeded("curb", g["id"])
        hosts = rng.random() < ROW_P.get(g["role"], 0.0)
        seg_doc.append({"id": g["id"], "road_id": g["road_id"], "side": side, "s0": round(g["s0"], 2),
                        "s1": round(g["s1"], 2), "role": g["role"], "hosts_rows": hosts})
        if not hosts:
            continue
        fr = WayFrame(w["pts"])
        W = w["width"]
        lane = w["base"] == "service"
        clear_min = MIN_CLEAR["lane"] if lane else MIN_CLEAR["one_way" if w["oneway"] else "two_way"]
        sruns = runs[(w["id"], side)]
        fb, majors = forbidden(w, side)

        def side_class(s):
            for a, b, c in sruns:
                if a <= s <= b:
                    return c
            return NONE

        def curb_at(s):
            best = min(g["parts"], key=lambda c: 0.0 if c["s0"] <= s <= c["s1"] else min(abs(s - c["s0"]), abs(s - c["s1"])))
            return best["curb_m"]

        s = g["s0"] + rng.uniform(0.0, 4.0)
        while s + PITCH * RUN_BAYS[0] <= g["s1"]:
            nb = rng.randint(*RUN_BAYS)
            fill = rng.uniform(0.55, 0.98)
            row_id = "%s#%d" % (g["id"], len(rows))
            placed = []
            k = 0
            while k < nb and s + PITCH <= g["s1"]:
                sc = s + PITCH / 2
                why = None
                if any(a <= s + PITCH and s <= b for a, b in fb):
                    why = "junction_driveway_crossing"
                if why is None and (s < 2.0 or s + PITCH > fr.L - 2.0):
                    why = "way_end"
                if why is None:
                    pc = fr.line.interpolate(sc)
                    if any(q.distance(pc) < c + PITCH for q, c in majors):
                        why = "junction_driveway_crossing"
                if why is None:
                    c = side_class(sc)
                    cm = curb_at(sc)
                    if c == SIDEWALK:
                        shift = -0.25                       # gutter: bay ends 0.25 m short of the kerb
                    elif c == ARCADE:
                        shift = min(0.4, max(0.0, cm - 0.8))
                    else:
                        shift = min(1.6, max(0.0, cm - 0.7))
                    o_out = W / 2 + shift
                    o_in = o_out - DEPTH
                    intr = max(0.0, W / 2 - o_in)
                    bins = range(int(math.floor(s)), int(math.ceil(s + PITCH)))
                    opp = max((intrusion[(w["id"], -side)][b] for b in bins), default=0.0)
                    if W - intr - opp < clear_min:
                        why = "carriageway_clearance"
                if why is None:
                    p, t, nl = fr.at(sc)
                    nn = nl * side
                    corners = [p + t * dx + nn * o for dx, o in ((-PITCH / 2, o_in), (PITCH / 2, o_in),
                                                                 (PITCH / 2, o_out), (-PITCH / 2, o_out))]
                    poly = Polygon([tuple(q) for q in corners])
                    why = clear_of(poly, road_idx[w["id"]])
                    if why is None and (overlaps_bay(poly) or any(q[6].intersection(poly).area > 0.005 for q in placed)):
                        why = "overlaps_bay"            # inside of a tight bend, or another road's row
                if why is not None:
                    reject[why] += 1
                    if placed:
                        break                        # a blocked bay ends the row; the next row starts after it
                    s += PITCH
                    continue
                for b in bins:
                    intrusion[(w["id"], side)][b] = max(intrusion[(w["id"], side)][b], intr)
                placed.append((sc, p, t, nn, o_in, o_out, poly, c))
                s += PITCH
                k += 1
            if len(placed) >= 3:
                rows.append({"id": row_id, "road_id": w["id"], "side": side, "role": g["role"], "bays": len(placed),
                             "fill": round(fill, 3), "class": CLASS_NAME[placed[0][7]]})
                for j, (sc, p, t, nn, o_in, o_out, poly, c) in enumerate(placed):
                    ctr = p + nn * (o_in + o_out) / 2
                    yaw = math.degrees(math.atan2(-nn[1], -nn[0]))           # bay axis: kerb -> carriageway
                    bays.append({"e": round(float(ctr[0]), 3), "n": round(float(ctr[1]), 3),
                                 "yaw": round(yaw, 2), "row": len(rows) - 1, "k": j})
                    row_polys[(w["id"], side)].append(poly)
                    add_bay(poly)
                draw_row(paint, placed, paint_colours)
            elif placed:
                reject["row_too_short"] += len(placed)
                for sc, *_r in placed:
                    for b in range(int(math.floor(sc - PITCH / 2)), int(math.ceil(sc + PITCH / 2))):
                        intrusion[(w["id"], side)][b] = 0.0
            s += rng.uniform(*RUN_GAP_M)

    row_clip = {k: unary_union(v).buffer(0.3) for k, v in row_polys.items()}
    side_doc = [{"road_id": wid, "side": side, "runs": [[round(a, 2), round(b, 2), CLASS_NAME[c]] for a, b, c in rr]}
                for (wid, side), rr in sorted(runs.items())]
    km = Counter()
    for w in ways_ok:
        for side in (1, -1):
            for a, b, c in runs.get((w["id"], side), ()):
                km[(w["base"] if not is_lane(w) else "service_lane") + "|" + CLASS_NAME[c]] += (b - a) / 1000.0
    doc = {"schema": "acw.curb_segments/0",
           "rules": {"pitch_m": PITCH, "depth_m": DEPTH, "row_p": ROW_P, "run_bays": RUN_BAYS, "run_gap_m": RUN_GAP_M,
                     "min_clear_m": MIN_CLEAR, "junction_clear_m": JUNCTION_CLEAR,
                     "lane_mouth_clear_m": LANE_MOUTH_CLEAR, "access_clear_m": ACCESS_CLEAR,
                     "crossing_clear_m": CROSSING_CLEAR, "sample_m": SAMPLE_M},
           "sides": side_doc, "segments": seg_doc, "rows": rows, "bays": bays}
    report = {"side_class_km": {k: round(v, 2) for k, v in sorted(km.items())},
              "side_class_reason_km": {k: round(v / 1000.0, 2) for k, v in sorted(class_stats.items())},
              "mapped_sidewalk_km": round(sum(l.length for l in sidewalks) / 1000.0, 2),
              "crossing_ways": len(crossings), "curb_segments": len(seg_doc),
              "segments_hosting_rows": sum(1 for s in seg_doc if s["hosts_rows"]),
              "rows": len(rows), "bays": len(bays), "bays_by_role": dict(Counter(str(r["role"]) for r in rows for _ in range(r["bays"]))),
              "bays_by_class": dict(Counter(r["class"] for r in rows for _ in range(r["bays"]))),
              "rejected_bays": dict(sorted(reject.items()))}
    return alpha, doc, row_clip, report


def draw_row(paint, placed, colours):
    """White bay outlines + a slightly darker oil-stained fill (fill 1 cm under the lines)."""
    white, fill = colours
    for sc, p, t, nn, o_in, o_out, poly, c in placed:
        a, b = p + nn * o_in, p + nn * o_out
        paint.quad_strip(a, b, PITCH, fill, lift=0.05)
    for j, (sc, p, t, nn, o_in, o_out, poly, c) in enumerate(placed):
        for dx in ((-PITCH / 2, PITCH / 2) if j == len(placed) - 1 else (-PITCH / 2,)):
            paint.quad_strip(p + t * dx + nn * o_in, p + t * dx + nn * o_out, LINE_W, white)
        for o in (o_in, o_out):
            paint.quad_strip(p + t * (-PITCH / 2) + nn * o, p + t * (PITCH / 2) + nn * o, LINE_W, white)


def write_doc(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    path.write_bytes(gzip.compress(raw, mtime=0))
    return hashlib.sha256(raw).hexdigest()
