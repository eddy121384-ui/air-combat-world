"""Taipei large wall ads v0: wall eligibility audit + deterministic placement plan.

Separate layer from the storefront signs (v0E): a few large boards on genuinely blank upper side walls,
drawn as instanced thin opaque planes with their own material (M_XinyiWallAds) and atlas
(build_wall_ad_atlas.py). Research: docs/xinyi-wall-ads-identity-research-v0.md; result:
docs/xinyi-wall-ads-v0-result.md.

Blank-wall signal (Gate 0)
--------------------------
Every procedural facade paints windows on every wall, so "the facade has windows" says nothing here. The
eligibility signal is real geometry plus the Taiwan building code: an exterior wall that sits on the lot
line may not open windows toward the neighbour (建築技術規則建築設計施工編 §45(2): no doors / windows /
balconies toward the adjacent lot unless the wall is >= 1 m from the boundary). A wall sample is a
*lot-line* sample when another building group's footprint lies within LOT_LINE_M of it; the boundary then
lies in that gap, so this wall is within 1 m of it. The usable surface is the longest contiguous lot-line
run of the wall, above the highest obstacle in front of it (the lower neighbour, rooftop props on the
neighbour's roof, and anything that hides the wall from an oblique aerial view), up to the parapet.
Walls that are not on a lot line (road flanks, open flanks, setbacks) are treated as windowed and never
receive a board. Same-group footprints (a tower's own podium / wing) never count as a neighbour.

Hosts: residential stock (low / walk-up / huaxia / res_tower) of generation legacy or huaxia only.
Never: modern / premium / unknown generation, offices, podiums, civic, schools, landmarks, Taipei 101
(suppressed hero records), rooftop-structure records. Walls whose view opens onto a park, garden or
school / campus ground within PARK_M are excluded; so are walls whose only street exposure is a service
lane / alley.

Placement (deterministic): every valid wall gets a score (road exposure, corner, area, age, district,
sha256 jitter); walls are accepted in descending score while the caps hold (one per building, spacing,
per-tile and per-core caps, aerial-only share) up to AD_RATE of the valid pool. No building id appears in
any rule; no manual exception.

Outputs (unreal/Saved/XinyiLook/wall_ads/):
  wall_ad_audit.json     Gate 0 audit: funnel, rejection reasons, distributions, every valid wall
  wall_ads.json          acw.wall_ads/0 instances for the level stage (e, n, z, yaw, sx, sy, sz, v, style)
  wall_ad_plane.glb      unit opaque plane (x = 0 facing +x, y +-0.5, z 0..1), UV0 = cell UV
  wall_ads.report.json   PASS_WALL_ADS receipt (counts, rules, hashes)
Usage: python tools/lookdev/build_wall_ads.py [--audit-only] [--max N]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
import build_ground as bg  # noqa: E402  (OSM roads / green / school polygons, same cache as the ground layer)
from gltf_writer import ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
LOOK = REPO / "unreal/Saved/XinyiLook"
OUT = LOOK / "wall_ads"
ROLES = LOOK / "urban_identity/frontage_roles.json.gz"
CAMPUSES = LOOK / "urban_identity/campuses.json"
ROOF_INST = LOOK / "rooftops/rooftop_instances.json"
ROOF_REP = LOOK / "rooftops/rooftops.report.json"
STREET_INST = LOOK / "street/street_instances.json"
ATLAS = OUT / "wall_ad_atlas.json"

ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM, ARCH_CIVIC, ARCH_SCHOOL = range(8)
ARCH_NAMES = ["low", "walkup", "huaxia", "res_tower", "office", "podium", "civic", "school"]
HOST_ARCH = {ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER}
HOST_GEN = {"legacy", "huaxia"}
FLAG_CORE, FLAG_ROOFTOP = 1, 8
TILE_M = 500.0

# ---- Gate 0 geometry rules (global; never tuned per building)
MIN_EDGE_M = 5.0           # ring edges shorter than this are not considered at all
SAMPLE_M = 1.0             # wall sample spacing
LOT_PROBES = (0.3, 0.65, 1.0)   # outward probes (m): another group's footprint here = lot-line sample
LOT_LINE_M = 1.0           # §45(2) distance
OCC_PROBES = (1.5, 2.5, 4.0, 6.0, 9.0, 13.0, 18.0, 25.0, 35.0)
VIEW_ELEV_DEG = 30.0       # oblique aerial view: an obstacle at distance d hides the wall below h - d tan(30)
CLEAR_M = 0.6              # board bottom above the highest obstacle
PARAPET_M = 1.0            # board top below the roof line
MIN_RUN_M = 5.0            # contiguous lot-line run
MIN_BAND_M = 6.0           # exposed blank band height
MIN_Z_ABOVE_GROUND_M = 6.0 # above the storefront / arcade band
PROP_STRIP_M = 2.0         # rooftop props within this strip in front of the run raise the board bottom
PARK_M = 25.0              # view onto park / garden / school ground within this distance -> excluded
ROAD_RAY_M = 40.0          # road seen over the lower neighbour
END_ROAD_M = 2.5           # a frontage edge of the same building ending this close to the wall end
LANE_W_M = 6.0             # service ways, or roads narrower than this, are lanes (frontage-role convention)

# ---- placement (profile values, research §D.3 / §K.7; design caps, not measured rates)
# OCCUPANCY is the share of *genuinely blank, street-exposed* walls (the Gate 0 valid pool) that carry a board.
# The research's 6-10 % was a share of the much larger exposed-wall pool (~1,100 walls, mostly windowed); see
# docs/xinyi-wall-ads-v0-result.md §3 for why the blank-wall share is higher and how the value was chosen.
OCCUPANCY = 0.25
MAX_BOARD_W_M = 14.0
MAX_BOARD_H_M = 24.0
MIN_BOARD_M = 4.0
FILL_W = 0.85              # board width <= this share of the lot-line run
FILL_H = 0.92              # board height <= this share of the blank band
SPACING_M = 25.0           # any two boards
CLUSTER_R_M, CLUSTER_CAP = 120.0, 2   # survey (research §K.2): never more than 2 large ads in one street window
SAME_FAMILY_SPACING_M = 40.0
SAME_CELL_SPACING_M = 400.0  # the same artwork twice inside one aerial frame reads as copy-paste
TILE_CAP, TILE_CAP_CORE = 14, 5
CORNER_GAIN = 1.5
CORE_WEIGHT = 0.15
OFFSET_CANVAS_M, OFFSET_PAINT_M = 0.15, 0.04
AGED_MIN_SHARE = 0.20
LIT_P = 0.20               # spot-lit canvas boards at night (research <= 25 %); painted / aged boards never
FAMILY_W = {"realty": 0.26, "medical": 0.26, "education": 0.15, "service": 0.12, "leasing": 0.05, "aged": 0.16}
ATTACH_TOL_M = 0.06        # QA: board plane vs the tile's wall plane (minus the offset)
VARIANTS = 512             # per-instance custom data 0 = (cell + 64 * lit + 128 * tone + 0.5) / 512


def unit(*key) -> float:
    h = hashlib.sha256("|".join(str(k) for k in key).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2.0 ** 64


# ------------------------------------------------------------------ context ---
def load_context():
    side = {}
    with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            side[r["building_id"]] = r
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    parts = []      # (building id, group, polygon, top abs m, ground abs m)
    hero = []
    for b in wm["buildings"]:
        if b["suppressed"]:
            for p in b["polygons"]:
                hero.append(Polygon(p["footprint_enu"]).buffer(0))
            continue
        if b["id"] not in side:
            continue
        g0 = float(props[b["id"]].get("ground_elev_m") or 0.0)
        top = g0 + float(b["height_m"])
        for p in b["polygons"]:
            g = Polygon(p["footprint_enu"], p.get("holes_enu") or [])
            g = g if g.is_valid else g.buffer(0)
            if g.is_empty:
                continue
            for q in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
                parts.append((b["id"], side[b["id"]]["group"], q, top, g0))
    ways, green, _water, _trees, special = bg.load_osm()
    roads = []
    for w in ways:
        geo = bg.way_geometry(w)
        if geo["skip"]:
            continue
        roads.append((LineString(w["pts"]).buffer(geo["width"] / 2.0, cap_style="flat"), w["tags"]["highway"],
                      geo["width"], geo["cls"]))
    quiet = [g for g in green if g.is_valid and not g.is_empty] + special["school"]
    for c in json.loads(CAMPUSES.read_text(encoding="utf-8"))["campuses"]:
        for part in c.get("polygon") or []:          # [{"outer": ring, "holes": [...]}] in ENU m
            q = Polygon(part["outer"], part.get("holes") or []).buffer(0)
            if not q.is_empty:
                quiet.append(q)
    roles = json.loads(gzip.decompress(ROLES.read_bytes()))
    front = defaultdict(list)
    for b in roles["buildings"]:
        for e in b["edges"]:
            front[b["building_id"]].append((np.array(e["p0"]), np.array(e["p1"]), e["role"], e["road_width"]))
    rdoc = json.loads(ROOF_INST.read_text())
    rrep = json.loads(ROOF_REP.read_text())
    roofp = []
    for t, items in rdoc["types"].items():
        ext = rrep["types"][t]["expected_ue_local_bounds"]
        ex, ey, ez = (v / 100.0 for v in ext["extent_cm"])
        for it in items:
            r = math.hypot(ex * it["sx"], ey * it["sy"]) + 0.2
            roofp.append((it["e"], it["n"], r, it["z"] + 2.0 * ez * it["sz"]))
    sdoc = json.loads(STREET_INST.read_text())
    signs = [(it["e"], it["n"], it["z"] + it["sz"]) for k in ("sign", "box") for it in sdoc["types"].get(k, [])]
    return dict(side=side, props=props, parts=parts, hero=hero, roads=roads, quiet=quiet, front=front,
                roofp=np.array(roofp, float), signs=np.array(signs, float), wm_frame=wm["local_frame"])


# -------------------------------------------------------------------- audit ---
def host_reason(rec):
    """None if the building may host a board, else the exclusion reason."""
    if rec["flags"] & FLAG_ROOFTOP:
        return "class_rooftop_structure"
    arch = rec["archetype"]
    if arch == ARCH_SCHOOL:
        return "class_school"
    if arch == ARCH_CIVIC:
        return "class_civic_or_landmark"
    if arch in (ARCH_OFFICE, ARCH_PODIUM):
        return "class_office_or_podium"
    gen = rec["facade_generation"]
    if gen in ("modern", "premium"):
        return "class_modern_or_premium"
    if gen not in HOST_GEN or arch not in HOST_ARCH:
        return "class_unknown_generation"
    return None


def longest_run(mask):
    best, cur, start, bs = 0, 0, 0, 0
    for i, m in enumerate(list(mask) + [False]):
        if m:
            if cur == 0:
                start = i
            cur += 1
            if cur > best:
                best, bs = cur, start
        else:
            cur = 0
    return bs, best


def audit(ctx):
    parts = ctx["parts"]
    polys = [p[2] for p in parts]
    tree = STRtree(polys)
    tops = np.array([p[3] for p in parts])
    groups = [p[1] for p in parts]
    road_tree = STRtree([r[0] for r in ctx["roads"]])
    quiet_u = unary_union(ctx["quiet"])
    quiet_tree = STRtree(list(quiet_u.geoms) if hasattr(quiet_u, "geoms") else [quiet_u])
    roofp = ctx["roofp"]
    roof_tree = STRtree(shapely.points(roofp[:, 0], roofp[:, 1]).tolist()) if len(roofp) else None
    funnel = Counter()
    reasons = Counter()
    by_class = defaultdict(Counter)
    walls = []
    tan_v = math.tan(math.radians(VIEW_ELEV_DEG))
    for pi, (bid, grp, poly, top, g0) in enumerate(parts):
        rec = ctx["side"][bid]
        ring = list(orient(poly, 1.0).exterior.coords)
        edges = [(np.array(a), np.array(b)) for a, b in zip(ring[:-1], ring[1:]) if math.dist(a, b) >= MIN_EDGE_M]
        if not edges:
            continue
        hr = host_reason(rec)
        gen = rec["facade_generation"]

        def rej(reason, gen=gen):
            reasons[reason] += 1
            by_class[gen][reason] += 1
        for k, (a, b) in enumerate(edges):
            funnel["raw_edges_ge_5m"] += 1
            if hr:
                rej(hr)
                continue
            L = float(np.hypot(*(b - a)))
            t = (b - a) / L
            n = np.array([t[1], -t[0]])             # outward for a CCW ring
            ns = max(1, int(L / SAMPLE_M))
            s = (np.arange(ns) + 0.5) * (L / ns)
            base = a[None, :] + s[:, None] * t[None, :]
            # lot-line probes: another group's footprint within 1 m; own-group footprints are the same building
            lot = np.zeros(ns, bool)
            own_wing = np.zeros(ns, bool)
            near_top = np.full(ns, -1e9)
            nbrs = [set() for _ in range(ns)]
            for d in LOT_PROBES:
                pts = shapely.points(base[:, 0] + n[0] * d, base[:, 1] + n[1] * d)
                si, pj = tree.query(pts, predicate="within")
                for i_, j_ in zip(si, pj):
                    if j_ == pi:
                        continue
                    if groups[j_] == grp:
                        own_wing[i_] = True
                    else:
                        lot[i_] = True
                        nbrs[i_].add(int(j_))
                    near_top[i_] = max(near_top[i_], tops[j_])
            if not lot.any():
                rej("windowed_own_wing" if own_wing.any() else "windowed_not_on_lot_line")
                continue
            i0, nrun = longest_run(lot & ~own_wing)
            run_len = nrun * (L / ns)
            if run_len < MIN_RUN_M:
                rej("lot_line_run_short")
                continue
            sl = slice(i0, i0 + nrun)
            # large institutional / commercial complexes are split into several WFS records whose shared edges
            # are joints of one structure, not lot lines: only ordinary building stock counts as a neighbour
            nb = set().union(*nbrs[sl])
            if any(ctx["side"][parts[j][0]]["archetype"] not in HOST_ARCH for j in nb):
                rej("neighbour_institutional_or_complex")
                continue
            rb = base[sl]
            zb = near_top[sl].copy()
            for d in OCC_PROBES:                       # oblique aerial occlusion
                pts = shapely.points(rb[:, 0] + n[0] * d, rb[:, 1] + n[1] * d)
                si, pj = tree.query(pts, predicate="within")
                for i_, j_ in zip(si, pj):
                    if j_ != pi:
                        zb[i_] = max(zb[i_], tops[j_] - d * tan_v)
            z_neigh = float(near_top[sl].max())
            z_bot = max(float(zb.max()), g0 + MIN_Z_ABOVE_GROUND_M - CLEAR_M) + CLEAR_M
            z_top = top - PARAPET_M
            if z_top - (z_neigh + CLEAR_M) < MIN_BAND_M:
                rej("not_exposed_above_neighbour")
                continue
            if z_top - z_bot < MIN_BAND_M:
                rej("occluded_from_air")
                continue
            r0, r1 = rb[0] - t * (L / ns) * 0.5, rb[-1] + t * (L / ns) * 0.5
            strip = Polygon([r0, r1, r1 + n * PROP_STRIP_M, r0 + n * PROP_STRIP_M])
            if roof_tree is not None:
                for j_ in roof_tree.query(strip.buffer(3.0)):
                    e_, n_, rad, ptop = roofp[j_]
                    if strip.distance(shapely.Point(e_, n_)) <= rad and ptop + CLEAR_M > z_bot:
                        z_bot = ptop + CLEAR_M
            if z_top - z_bot < MIN_BAND_M:
                rej("rooftop_prop_conflict")
                continue
            mid = (r0 + r1) / 2.0
            # existing projecting street signs in the run's air space
            if len(ctx["signs"]):
                sg = ctx["signs"]
                dd = np.hypot(sg[:, 0] - mid[0], sg[:, 1] - mid[1])
                if np.any((dd < run_len / 2 + 1.5) & (sg[:, 2] > z_bot)):
                    rej("existing_sign_conflict")
                    continue
            ray = shapely.points([mid[0] + n[0] * d for d in np.arange(1.5, PARK_M + 0.1, 1.5)],
                                 [mid[1] + n[1] * d for d in np.arange(1.5, PARK_M + 0.1, 1.5)])
            if len(quiet_tree.query(ray, predicate="within")[0]):
                rej("faces_park_or_school")
                continue
            # street exposure: a street (not a lane) seen over the lower neighbour within ROAD_RAY_M, or the
            # building's own street frontage ending at the wall (the wall is then seen along that street)
            face, any_lane = None, False
            dists = np.arange(2.0, ROAD_RAY_M + 0.1, 2.0)
            rp = shapely.points(mid[0] + n[0] * dists, mid[1] + n[1] * dists)
            si, rj = road_tree.query(rp, predicate="within")
            for o in np.lexsort((rj, si)):
                _, hw, rw, rc = ctx["roads"][rj[o]]
                if hw == "service" or rw < LANE_W_M:
                    any_lane = True
                    continue
                if face is None or (rc, rw) > (face[3], face[2]):
                    face = (float(dists[si[o]]), hw, float(rw), float(rc))
            end_role, end_w = 0, 0.0
            for p0, p1, role, rw in ctx["front"].get(bid, []):
                for q in (p0, p1):
                    if min(np.hypot(*(q - a)), np.hypot(*(q - b))) <= END_ROAD_M and role >= 2:
                        if (role, rw) > (end_role, end_w):
                            end_role, end_w = role, float(rw)
            has_face = face is not None
            has_end = end_role >= 3 and end_w >= LANE_W_M
            if not has_face and not has_end and (any_lane or end_role >= 2):
                rej("lane_or_alley_only")
                continue
            if not has_face and not has_end:
                rej("no_street_exposure")
                continue
            cond = "corner" if (has_face and has_end) else "road_face" if has_face else "street_end"
            major = (has_face and (face[3] >= 0.66 or face[2] >= 15.0)) or (has_end and (end_role in (4, 7) or end_w >= 15.0))
            rej("valid")
            walls.append({
                "wall_id": "%s/%d/%d" % (bid, pi, k), "building_id": bid, "group": grp,
                "archetype": ARCH_NAMES[rec["archetype"]], "generation": gen, "core": bool(rec["flags"] & FLAG_CORE),
                "weather": rec["weather"],
                "tile": [int(math.floor(mid[0] / TILE_M)), int(math.floor(mid[1] / TILE_M))],
                "p0": [round(float(r0[0]), 3), round(float(r0[1]), 3)], "p1": [round(float(r1[0]), 3), round(float(r1[1]), 3)],
                "normal_deg": round(math.degrees(math.atan2(n[1], n[0])), 3),
                "edge_len_m": round(L, 2), "run_len_m": round(run_len, 2),
                "ground_m": round(g0, 3), "top_m": round(top, 3), "neighbour_top_m": round(z_neigh, 3),
                "z_bottom_m": round(z_bot, 3), "z_top_m": round(z_top, 3), "band_m": round(z_top - z_bot, 2),
                "area_m2": round(run_len * (z_top - z_bot), 1),
                "condition": cond, "major_road": bool(major),
                "face_road": None if face is None else {"dist_m": face[0], "highway": face[1], "width_m": face[2]},
                "end_role": end_role,
            })
    funnel["host_class_ok"] = funnel["raw_edges_ge_5m"] - sum(v for k, v in reasons.items() if k.startswith("class_"))
    return walls, funnel, reasons, by_class


def distributions(walls):
    def hist(vals, edges):
        h = Counter()
        for v in vals:
            for lo, hi in zip(edges[:-1], edges[1:]):
                if lo <= v < hi:
                    h["%g-%g" % (lo, hi)] += 1
                    break
            else:
                h[">=%g" % edges[-1]] += 1
        return dict(h)
    return {
        "by_generation": dict(Counter(w["generation"] for w in walls)),
        "by_archetype": dict(Counter(w["archetype"] for w in walls)),
        "by_condition": dict(Counter(w["condition"] for w in walls)),
        "major_road": sum(w["major_road"] for w in walls),
        "core": sum(w["core"] for w in walls),
        "run_len_m": hist([w["run_len_m"] for w in walls], [5, 8, 12, 16, 24, 40]),
        "band_m": hist([w["band_m"] for w in walls], [6, 9, 12, 18, 30, 60]),
        "area_m2": hist([w["area_m2"] for w in walls], [30, 60, 120, 250, 500, 1000]),
        "buildings": len({w["building_id"] for w in walls}),
        "groups": len({w["group"] for w in walls}),
    }




# ---------------------------------------------------------------- placement ---
def score(w):
    road = 1.0 if w["major_road"] else 0.6
    corner = CORNER_GAIN if w["condition"] == "corner" else 1.0
    area = min(1.4, max(0.5, w["area_m2"] / 120.0))
    age = 1.0 if w["generation"] == "legacy" else 0.8
    district = CORE_WEIGHT if w["core"] else 1.0
    return road * corner * area * age * district * (0.7 + 0.6 * unit(w["wall_id"], "score"))


def board_size(w):
    """(bin, width, height) of the largest atlas aspect that fits the blank band; None if nothing >= 4 m fits."""
    wa = min(FILL_W * w["run_len_m"], MAX_BOARD_W_M)
    ha = min(FILL_H * w["band_m"], MAX_BOARD_H_M)
    best = None
    for b, a in (("T", 2.0), ("S", 1.0), ("W", 0.5)):
        bw = min(wa, ha / a)
        bh = a * bw
        if bw >= MIN_BOARD_M and bh >= MIN_BOARD_M and (best is None or bw * bh > best[1] * best[2] + 1e-6):
            best = (b, bw, bh)
    return best


def family_order(w, fams_in_bin, counts, n):
    """Families available in this board's bin, most under-represented first: deficit = host-aware target share x
    (boards so far + 1) - boards of that family so far (quota / largest-remainder style, so the totals follow
    FAMILY_W by construction instead of by luck); sha256 breaks ties."""
    wts = dict(FAMILY_W)
    if w["generation"] == "legacy":
        wts["aged"] *= 1.6
    if w["archetype"] == "res_tower":
        wts["realty"] *= 1.5            # off-site pre-sale banners on older tower flanks (survey W5)
    tot = sum(wts.values())
    fams = [f for f in sorted(wts) if f in fams_in_bin]
    return sorted(fams, key=lambda f: (-(wts[f] / tot * (n + 1) - counts[f]), unit(w["wall_id"], "family", f)))


def select(walls, atlas):
    by_bf = defaultdict(list)
    for c in atlas["cells"]:
        by_bf[(c["bin"], c["family"])].append(c)
    use = Counter()
    ranked = sorted(walls, key=lambda w: (-score(w), w["wall_id"]))
    target = int(round(OCCUPANCY * len(walls)))
    placed, used_groups, per_tile, per_core = [], set(), Counter(), Counter()
    stats = Counter()

    def near(x, y, dist, fam=None):
        return any(math.hypot(p["e"] - x, p["n"] - y) < dist and (fam is None or p["family"] == fam) for p in placed)

    def fresh_cells(b, fam, x, y, skip=None):
        """Cells of (bin, family) whose artwork is not already on a board within SAME_CELL_SPACING_M."""
        return [cc for cc in by_bf[(b, fam)] if not any(
            q is not skip and q["cell"]["id"] == cc["id"] and math.hypot(q["e"] - x, q["n"] - y) < SAME_CELL_SPACING_M
            for q in placed)]

    for w in ranked:
        if len(placed) >= target:
            break
        if w["group"] in used_groups:
            stats["skip_building_has_board"] += 1
            continue
        size = board_size(w)
        if size is None:
            stats["skip_no_board_fits"] += 1
            continue
        b, bw, bh = size
        tkey = tuple(w["tile"])
        if per_tile[tkey] >= TILE_CAP or (w["core"] and per_core[tkey] >= TILE_CAP_CORE):
            stats["skip_tile_cap"] += 1
            continue
        p0, p1 = np.array(w["p0"]), np.array(w["p1"])
        L = float(np.hypot(*(p1 - p0)))
        t = (p1 - p0) / L
        a = math.radians(w["normal_deg"])
        n = np.array([math.cos(a), math.sin(a)])
        off = (unit(w["wall_id"], "slide") - 0.5) * (L - bw) * 0.6
        c = p0 + t * (L / 2.0 + off)
        if near(c[0], c[1], SPACING_M):
            stats["skip_spacing"] += 1
            continue
        if sum(math.hypot(q["e"] - c[0], q["n"] - c[1]) < CLUSTER_R_M for q in placed) >= CLUSTER_CAP:
            stats["skip_cluster_cap"] += 1
            continue
        fam = None
        fam_n = Counter(q["family"] for q in placed)
        for f in family_order(w, {ff for (bb, ff) in by_bf if bb == b}, fam_n, len(placed)):
            if not near(c[0], c[1], SAME_FAMILY_SPACING_M, f) and fresh_cells(b, f, c[0], c[1]):
                fam = f
                break
        if fam is None:
            stats["skip_family_spacing"] += 1
            continue
        cell = sorted(fresh_cells(b, fam, c[0], c[1]), key=lambda cc: (use[cc["id"]], unit(w["wall_id"], "cell", cc["id"])))[0]
        use[cell["id"]] += 1
        slack = w["band_m"] - bh
        top = w["z_top_m"] - slack * (0.1 + 0.4 * unit(w["wall_id"], "drop"))
        placed.append({"wall": w, "e": float(c[0]), "n": float(c[1]), "t": t, "nrm": n, "bin": b, "w": bw, "h": bh,
                       "z": top - bh, "family": fam, "cell": cell})
        used_groups.add(w["group"])
        per_tile[tkey] += 1
        per_core[tkey] += w["core"]
    # aged / ghost share >= AGED_MIN_SHARE: convert the lowest-scored legacy-host boards first (deterministic)
    need = int(math.ceil(AGED_MIN_SHARE * len(placed))) - sum(p["cell"]["aged"] for p in placed)
    for p in sorted(placed, key=lambda q: (q["wall"]["generation"] != "legacy", score(q["wall"]), q["wall"]["wall_id"])):
        if need <= 0:
            break
        if p["cell"]["aged"]:
            continue
        pool = [c for c in fresh_cells(p["bin"], "aged", p["e"], p["n"], skip=p) if c["aged"]]
        others = [q for q in placed if q is not p and q["family"] == "aged"]
        if not pool or any(math.hypot(q["e"] - p["e"], q["n"] - p["n"]) < SAME_FAMILY_SPACING_M for q in others):
            continue
        use[p["cell"]["id"]] -= 1
        p["cell"] = sorted(pool, key=lambda cc: (use[cc["id"]], unit(p["wall"]["wall_id"], "cell", cc["id"])))[0]
        use[p["cell"]["id"]] += 1
        p["family"] = "aged"
        need -= 1
        stats["converted_to_aged"] += 1
    stats["target"] = target
    return placed, stats


def instances(placed, plane):
    """plane: wall id -> measured offset (m) of the tile mesh's wall plane from the footprint line; the board offset
    is applied from the mesh wall, so a 4 cm painted board can never sink into a wall digitised a few cm outward."""
    out = []
    for p in placed:
        cell, w = p["cell"], p["wall"]
        off = (OFFSET_PAINT_M if cell["painted"] else OFFSET_CANVAS_M) + plane[w["wall_id"]]
        lit = int(cell["lit_ok"] and unit(w["wall_id"], "lit") < LIT_P)
        tone = int(unit(w["wall_id"], "tone") * 4)
        e, n = p["e"] + p["nrm"][0] * off, p["n"] + p["nrm"][1] * off
        out.append({"e": round(e, 3), "n": round(n, 3), "z": round(p["z"], 3), "yaw": round(w["normal_deg"], 3),
                    "sx": 1.0, "sy": round(p["w"], 3), "sz": round(p["h"], 3),
                    "v": int(cell["id"] + 64 * lit + 128 * tone),
                    "wall_id": w["wall_id"], "cell": cell["id"], "family": p["family"], "aged": cell["aged"],
                    "painted": cell["painted"], "lit": lit, "offset_m": round(off, 4),
                    "wall_plane_m": round(plane[w["wall_id"]], 4), "condition": w["condition"],
                    "major_road": w["major_road"], "generation": w["generation"], "archetype": w["archetype"],
                    "core": w["core"], "tile": w["tile"], "score": round(score(w), 4)})
    return out


def qa_attachment(placed):
    """Every board must lie on a real wall of the accepted tile mesh: 9 sample points of the board (before the
    offset) must each fall inside a wall triangle coplanar with it (corners within ATTACH_TOL_M of the plane,
    normal within 3 deg). Fails closed: a board in mid-air, past a wall end or above the roof is an error."""
    from gltf_writer import read_glb_primitives
    rep = json.loads((LOOK / "look_tiles.report.json").read_text(encoding="utf-8"))
    tiles = {}
    for row in rep["tiles"]:
        ox, oy = row["origin_enu_m"]
        tiles[(int(ox // TILE_M), int(oy // TILE_M))] = (row["path"], ox, oy)
    cache = {}

    def tris(key):
        if key not in cache:
            cache[key] = None
            if key in tiles:
                path, ox, oy = tiles[key]
                pr = read_glb_primitives(LOOK / "tiles" / path)[0]
                pos = np.asarray(pr["position"], np.float64)
                enu = np.column_stack([pos[:, 0] + ox, -pos[:, 2] + oy, pos[:, 1]])
                tri = enu[np.asarray(pr["indices"]).reshape(-1, 3)]
                nr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                ln = np.linalg.norm(nr, axis=1)
                ok = ln > 1e-9
                tri, nr = tri[ok], nr[ok] / ln[ok, None]
                wall = np.abs(nr[:, 2]) < 0.05
                cache[key] = (tri[wall], nr[wall])
        return cache[key]

    cos_tol = math.cos(math.radians(3.0))
    fails, worst, plane = [], 0.0, {}
    for p in placed:
        n3 = np.array([p["nrm"][0], p["nrm"][1], 0.0])
        t3 = np.array([p["t"][0], p["t"][1], 0.0])
        c3 = np.array([p["e"], p["n"], 0.0])
        pts = [(u * p["w"] * 0.48, p["z"] + v * p["h"]) for u in (-1, 0, 1) for v in (0.02, 0.5, 0.98)]
        tx, ty = int(math.floor(p["e"] / TILE_M)), int(math.floor(p["n"] / TILE_M))
        cand = [r for r in (tris((tx + dx, ty + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1)) if r is not None]
        T = np.concatenate([c[0] for c in cand])
        N = np.concatenate([c[1] for c in cand])
        d = (T - c3) @ n3
        sel = (N @ n3 >= cos_tol) & (np.abs(d).max(axis=1) <= ATTACH_TOL_M)
        Ts = T[sel]
        if len(Ts):
            worst = max(worst, float(np.abs(d[sel]).max()))
            plane[p["wall"]["wall_id"]] = float(d[sel].mean())    # mesh wall plane vs footprint line (m, outward +)
        s2 = np.stack([(Ts - c3) @ t3, Ts[:, :, 2]], axis=-1)
        miss = 0
        for s, z in pts:
            hit = False
            for (x1, y1), (x2, y2), (x3, y3) in s2:
                den = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
                if abs(den) < 1e-12:
                    continue
                l1 = ((y2 - y3) * (s - x3) + (x3 - x2) * (z - y3)) / den
                l2 = ((y3 - y1) * (s - x3) + (x1 - x3) * (z - y3)) / den
                if l1 >= -1e-6 and l2 >= -1e-6 and 1 - l1 - l2 >= -1e-6:
                    hit = True
                    break
            miss += not hit
        if miss:
            fails.append({"wall_id": p["wall"]["wall_id"], "points_off_wall": miss})
    return fails, worst, plane


def write_plane(path):
    """Unit opaque plane facing +x (ENU local): y +-0.5 (width), z 0..1 (height); UV0 u left -> right as seen
    from the front, v top -> bottom (atlas convention). Two triangles, counter-clockwise from the front."""
    v = np.array([(0.0, -0.5, 0.0), (0.0, 0.5, 0.0), (0.0, 0.5, 1.0), (0.0, -0.5, 1.0)])
    uv = np.array([(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)], np.float32)
    f = np.array([(0, 1, 2), (0, 2, 3)], np.uint32)
    game = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype(np.float32)
    fn = np.cross(game[1] - game[0], game[2] - game[0])
    nrm = np.tile(fn / np.linalg.norm(fn), (4, 1)).astype(np.float32)
    write_glb(path, [{"name": "SM_XinyiWallAd", "positions": game, "normals": nrm, "uv0": uv, "indices": f,
                      "base_color": [0.8, 0.8, 0.8, 1.0]}], mesh_name="SM_XinyiWallAd")
    return ue_local_bounds_cm(game), int(len(f))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-only", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = load_context()
    walls, funnel, reasons, by_class = audit(ctx)
    walls = sorted(walls, key=lambda w: w["wall_id"])
    doc = {"schema": "acw.wall_ad_audit/0",
           "rules": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float, tuple))},
           "funnel": dict(funnel), "reasons": dict(sorted(reasons.items())),
           "reasons_by_generation": {k: dict(sorted(v.items())) for k, v in sorted(by_class.items())},
           "valid": distributions(walls),
           "capacity": {"boards_that_fit": sum(board_size(w) is not None for w in walls),
                        "target_at_occupancy": int(round(OCCUPANCY * len(walls)))},
           "walls": walls}
    (OUT / "wall_ad_audit.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("funnel", "reasons", "valid", "capacity")}, ensure_ascii=False))
    if args.audit_only:
        return
    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    placed, stats = select(walls, atlas)
    fails, worst, plane = qa_attachment(placed)
    inst = instances(placed, plane) if not fails else []
    (OUT / "wall_ads.json").write_text(json.dumps(
        {"schema": "acw.wall_ads/0", "variants": VARIANTS, "atlas_sha256": atlas["sha256"], "instances": inst},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    bounds, tri = write_plane(OUT / "wall_ad_plane.glb")
    aged = sum(i["aged"] for i in inst)
    ok = not fails and inst and aged >= AGED_MIN_SHARE * len(inst)
    report = {
        "status": "PASS_WALL_ADS" if ok else "FAIL_WALL_ADS",
        "mesh": {"mesh": "wall_ad_plane.glb", "triangles": tri, "expected_ue_local_bounds": bounds},
        "instances": len(inst), "instance_triangles": len(inst) * tri,
        "valid_walls": len(walls), "selection": dict(sorted(stats.items())),
        "by_family": dict(Counter(i["family"] for i in inst)), "by_bin": dict(Counter(p["bin"] for p in placed)),
        "by_condition": dict(Counter(i["condition"] for i in inst)),
        "by_generation": dict(Counter(i["generation"] for i in inst)),
        "by_archetype": dict(Counter(i["archetype"] for i in inst)),
        "by_tile": dict(sorted(Counter("%d_%d" % tuple(i["tile"]) for i in inst).items())),
        "major_road": sum(i["major_road"] for i in inst), "core": sum(i["core"] for i in inst),
        "aged": aged, "painted": sum(i["painted"] for i in inst), "lit": sum(i["lit"] for i in inst),
        "distinct_cells": len({i["cell"] for i in inst}),
        "board_area_m2": round(sum(p["w"] * p["h"] for p in placed), 1),
        "attachment_failures": fails, "attachment_worst_plane_err_m": round(worst, 4),
        "atlas_sha256": atlas["sha256"], "audit_sha256": sha(OUT / "wall_ad_audit.json"),
        "sha256": sha(OUT / "wall_ads.json"),
    }
    (OUT / "wall_ads.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "by_tile"}, ensure_ascii=False))
    if not ok:
        raise SystemExit("wall ads failed: %s" % json.dumps(fails)[:800])


if __name__ == "__main__":
    main()
