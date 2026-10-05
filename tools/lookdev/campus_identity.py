"""School & Campus Identity v0A: Grade-A campuses, WFS building-group membership, sports surfaces.

Shared by the look-dev builders (no Unreal import, no randomness, deterministic):

  build_look_tiles.py  campus membership -> ARCH_SCHOOL (7) for accepted building groups and the
                       yard-facing corridor wall flag; writes campus/campus_membership.json (+ audit PNGs)
  build_ground.py      campus yard / court / playground data texture + court line paint
  build_rooftops.py    reads the archetype only (school roofs: no 頂樓加蓋 additions)

Inputs are locked look-dev caches only: data/lookdev_cache/osm_education_context.json.gz (ODbL, see its
.meta.json) and the accepted WFS footprints. Nothing here edits geometry.

Grade-A campus (rule, not a list): an OSM `amenity=school` multipolygon relation for an elementary /
junior-high / senior-high / vocational school whose polygon lies >= 97 % inside the WFS building-source
bbox (every building of the campus has real WFS geometry). On the locked cache this selects exactly nine
campuses; a different count fails closed (source drift must be reviewed, not silently absorbed).

Membership (per building GROUP, so a wing and its height-zone records stay consistent):
  accept  >= 97 % of the group footprint inside the campus polygon
          or >= 85 % inside and >= 60 % covered by OSM-tagged school buildings (a tagged wing whose
          footprint overhangs a loosely drawn campus line)
  reject  straddling groups below those thresholds (group override would repaint fabric outside)
          groups abutting (<= 1 m) a building group that lies mostly outside the campus, unless OSM tags
          them as school buildings: an edge terrace continuing out of the campus is shop-house fabric
Sports: only tagged leisure=pitch / playground inside a Grade-A campus; a surface more than 25 % under a
WFS footprint is an indoor court (activity hall) and is rejected. Athletics tracks are never produced
(OSM has none here; inferred candidates are not render input).
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, polygonize, unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EDU = REPO / "data/lookdev_cache/osm_education_context.json.gz"

ARCH_SCHOOL = 7
GRADE_A_LEVELS = ("elementary", "junior_high", "senior_high", "vocational")
GRADE_A_MIN_COVERAGE = 0.97
EXPECTED_GRADE_A = 9
INSIDE_MIN = 0.97
INSIDE_MIN_TAGGED = 0.85
OSM_COVER_MIN = 0.60
ATTACH_GAP_M = 1.0
OUTSIDE_NEIGHBOUR_MAX_INSIDE = 0.5
PITCH_UNDER_BUILDING_MAX = 0.25
EDU_BUILDING = ("school", "university", "college", "kindergarten")

# court surface palette ids (xinyi_city.hlsl xc_court_surface); restrained, matte, no track colours
SURF_NONE, SURF_GREEN, SURF_BLUE, SURF_GREYGREEN, SURF_CONCRETE, SURF_PLAYGROUND = 0, 1, 2, 3, 4, 5
HARD_SURFACES = ("concrete", "asphalt", "paved", "paving_stones")


def school_level(name: str) -> str:
    n = name or ""
    for key, lvl in (("國際國中小", "k12"), ("國小", "elementary"), ("國中", "junior_high"), ("高中", "senior_high"),
                     ("高工", "vocational"), ("工農", "vocational"), ("商職", "vocational"), ("工商", "vocational"),
                     ("幼兒園", "kindergarten"), ("幼稚園", "kindergarten"), ("大學", "university"), ("學院", "university")):
        if key in n:
            return lvl
    return "school"


def edu_features(lon0: float, lat0: float) -> list:
    """Closed ways and multipolygon relations of the education cache as ENU shapely geometry."""
    import sys
    sys.path.insert(0, str(REPO / "tools/compiler"))
    from worldmodel import lonlat_to_enu

    def enu(g):
        return [lonlat_to_enu(p["lon"], p["lat"], lon0, lat0) for p in g]

    doc = json.loads(gzip.decompress(EDU.read_bytes()))
    feats = []
    for e in doc["elements"]:
        t = e.get("tags", {})
        if e["type"] == "way" and e.get("geometry"):
            pts = enu(e["geometry"])
            if len(pts) >= 4 and e["nodes"][0] == e["nodes"][-1]:
                g = Polygon(pts).buffer(0)
                if g.is_valid and not g.is_empty:
                    feats.append({"type": "way", "id": e["id"], "tags": t, "geom": g})
        elif e["type"] == "relation":
            outers = [LineString(enu(m["geometry"])) for m in e.get("members", [])
                      if m.get("role") == "outer" and m.get("geometry") and len(m["geometry"]) >= 2]
            inners = [LineString(enu(m["geometry"])) for m in e.get("members", [])
                      if m.get("role") == "inner" and m.get("geometry") and len(m["geometry"]) >= 4]
            polys = list(polygonize(linemerge(outers))) if outers else []
            if not polys:
                continue
            g = unary_union([p.buffer(0) for p in polys])
            for ln in inners:
                g = g.difference(Polygon(ln).buffer(0))
            if g.is_valid and not g.is_empty:
                feats.append({"type": "relation", "id": e["id"], "tags": t, "geom": g})
    return feats


def grade_a_campuses(feats: list, src_bbox) -> list:
    out = []
    for f in sorted(feats, key=lambda x: (x["type"], x["id"])):
        t = f["tags"]
        name = t.get("name:zh") or t.get("name") or ""
        if f["type"] != "relation" or t.get("amenity") != "school":
            continue
        level = school_level(name)
        cov = f["geom"].intersection(src_bbox).area / f["geom"].area
        if level in GRADE_A_LEVELS and cov >= GRADE_A_MIN_COVERAGE:
            out.append({"id": "osm_relation_%d" % f["id"], "name": name, "level": level, "geom": f["geom"],
                        "bbox_coverage": round(cov, 4)})
    if len(out) != EXPECTED_GRADE_A:
        raise RuntimeError("Grade-A campus rule selected %d campuses, expected %d (education source drift?)"
                           % (len(out), EXPECTED_GRADE_A))
    return out


def school_building_union(feats: list):
    return unary_union([f["geom"] for f in feats if f["type"] == "way"
                        and str(f["tags"].get("building", "")) in EDU_BUILDING])


def assign_groups(campuses: list, groups: dict, osm_school) -> tuple[dict, list]:
    """groups: {group_id: footprint (Multi)Polygon}. Returns ({group_id: campus_id}, decisions)."""
    gids = sorted(groups)
    geoms = [groups[g] for g in gids]
    tree = STRtree(geoms)
    inside_of = {}          # group -> (best campus, inside fraction)
    for c in campuses:
        for i in tree.query(c["geom"], predicate="intersects"):
            g = gids[int(i)]
            a = geoms[int(i)].area
            frac = geoms[int(i)].intersection(c["geom"]).area / a if a > 0 else 0.0
            if frac > inside_of.get(g, (None, -1.0))[1]:
                inside_of[g] = (c["id"], frac)
    accepted, decisions = {}, []
    for c in campuses:
        cand = sorted(g for g, (cid, _f) in inside_of.items() if cid == c["id"])
        for g in cand:
            geom = groups[g]
            frac = inside_of[g][1]
            osm_cov = geom.intersection(osm_school).area / geom.area if geom.area > 0 else 0.0
            tagged = osm_cov >= OSM_COVER_MIN
            reason = None
            if not (frac >= INSIDE_MIN or (frac >= INSIDE_MIN_TAGGED and tagged)):
                reason = "straddles_campus_boundary"
            elif not tagged:
                for j in tree.query(geom.buffer(ATTACH_GAP_M), predicate="intersects"):
                    h = gids[int(j)]
                    if h == g:
                        continue
                    if inside_of.get(h, (None, 0.0))[1] < OUTSIDE_NEIGHBOUR_MAX_INSIDE:
                        reason = "abuts_outside_fabric"
                        break
            if reason is None:
                accepted[g] = c["id"]
            decisions.append({"campus": c["id"], "group": g, "accepted": reason is None, "reason": reason or "inside",
                              "inside_fraction": round(frac, 4), "osm_school_cover": round(osm_cov, 4),
                              "area_m2": round(geom.area, 1),
                              "outside_area_m2": round(geom.area - geom.intersection(c["geom"]).area, 2)})
    return accepted, decisions


def _rect(g):
    """Minimum rotated rectangle -> (centre, long-axis unit vector, length, width)."""
    co = np.asarray(g.minimum_rotated_rectangle.exterior.coords)[:4]
    e1, e2 = co[1] - co[0], co[2] - co[1]
    if np.hypot(*e1) < np.hypot(*e2):
        e1, e2 = e2, e1
    L, W = float(np.hypot(*e1)), float(np.hypot(*e2))
    c = co.mean(axis=0)
    return (float(c[0]), float(c[1])), (e1 / max(L, 1e-9)).tolist(), L, W


def sports_surfaces(campuses: list, feats: list, wfs_polys: list) -> tuple[list, list]:
    """Tagged pitches / playgrounds inside Grade-A campuses. Returns (surfaces, rejected)."""
    wtree = STRtree(wfs_polys)
    surfaces, rejected = [], []
    for f in sorted(feats, key=lambda x: x["id"]):
        t = f["tags"]
        lei = t.get("leisure")
        if f["type"] != "way" or lei not in ("pitch", "playground"):
            continue
        g = f["geom"]
        owner = [c for c in campuses if c["geom"].contains(g.representative_point())]
        if not owner:
            continue
        c = owner[0]
        hits = [wfs_polys[int(i)] for i in wtree.query(g, predicate="intersects")]
        cover = g.intersection(unary_union(hits)).area / g.area if hits and g.area > 0 else 0.0
        centre, axis, L, W = _rect(g)
        rec = {"id": "osm_way_%d" % f["id"], "campus": c["id"], "kind": lei, "sport": t.get("sport", ""),
               "surface": t.get("surface", ""), "length_m": round(L, 2), "width_m": round(W, 2),
               "axis_deg": round(math.degrees(math.atan2(axis[1], axis[0])) % 180.0, 2),
               "area_m2": round(g.area, 1), "under_building_fraction": round(cover, 3)}
        if cover > PITCH_UNDER_BUILDING_MAX:
            rec["reason"] = "under_building"
            rejected.append(rec)
            continue
        if lei == "playground":
            surf = SURF_PLAYGROUND
        elif rec["surface"] in HARD_SURFACES:
            surf = SURF_CONCRETE
        elif rec["sport"] in ("tennis", "badminton"):
            surf = SURF_GREEN
        else:   # basketball / volleyball / multi / untagged hard courts: one colour per campus
            surf = SURF_BLUE if int(c["id"].rsplit("_", 1)[1]) % 2 else SURF_GREEN
        rec.update({"surface_id": surf, "centre": [round(centre[0], 3), round(centre[1], 3)],
                    "axis": [round(axis[0], 6), round(axis[1], 6)], "geom": g})
        surfaces.append(rec)
    return surfaces, rejected


class YardProbe:
    """Does a wall face the open schoolyard? Probes along its outward normal must land inside the campus
    and outside every WFS footprint (corridors of Taiwanese classroom wings face the yard)."""

    def __init__(self, campus_geom, wfs_polys):
        from shapely.prepared import prep
        self.campus = prep(campus_geom)
        self.solid = prep(unary_union(wfs_polys).buffer(0.3))

    def faces_yard(self, p0, p1, normal) -> bool:
        from shapely.geometry import Point
        p0, p1, n = np.asarray(p0, float), np.asarray(p1, float), np.asarray(normal, float)
        votes = 0
        total = 0
        for s in (0.15, 0.35, 0.5, 0.65, 0.85):
            q = p0 + (p1 - p0) * s
            for d in (4.0, 9.0):
                pt = Point(*(q + n * d))
                total += 1
                votes += int(self.campus.contains(pt) and not self.solid.contains(pt))
        return votes >= 0.7 * total
