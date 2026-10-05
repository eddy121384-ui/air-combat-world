"""Decorate the accepted 25 Xinyi runtime tiles with look-dev vertex data.

Geometry contract
-----------------
This is a *representation* stage downstream of the accepted contract. For every
tile the output triangle soup is bit-identical to the accepted runtime tile
(`build_contract.build_runtime_tile_glbs`): same triangles, same order, same
float32 corner positions. The script fails closed if that is not true.

What changes is vertex *sharing* and vertex *attributes*:

- The accepted runtime GLB carries POSITION only and shares vertices between
  roofs and walls. Engines then invent smoothed normals across 90-degree eaves,
  which is a large part of why the whitebox reads as "GIS". Here every corner
  gets its planar face normal and vertices are welded only where all
  attributes agree.
- TEXCOORD_0  walls: (perimeter metres along the footprint ring, metres above
              the building's surveyed ground) -> exact per-wall window grids
              that stay continuous around corners.
              roofs/soffits: tile-local (east, north) metres.
- TEXCOORD_1  (record height_m, visual floor height m)  [real WFS data]
- TEXCOORD_2  packed RGBA8 (gltf_writer.pack_rgba8; decode xc_unpack):
              R = archetype * 16 + variant
              G = appearance seed (per building group)
              B = weathering 0..255
              A = flags (bit0 core district, bit1 group anchor, bit2 podium part,
                         bit3 rooftop structure,
                         bits 4-6 per wall:  school records: bit4 = wall facing the
                                             schoolyard (open corridor side);
                                             other records: frontage role FRONT_*
                                             (0 on roofs / rooftop-structure records),
                         >= 248 reserved for the hero tag; max baked value 127)

Building groups
---------------
The WFS models one real building as several height-zone records. Records are
grouped (union-find) so a tower and its podium / stair cores share one
archetype, palette and floor rhythm. Equal-sized row houses stay separate.

Schools
-------
Building groups accepted by the Grade-A campus membership rules
(campus_identity.py) get ARCH_SCHOOL (7): classroom-wing facade / roof grammar
instead of the shop-house / residential grammar. Wall triangles of school
buildings whose outward normal faces the open schoolyard carry flag bit4 (open
corridor side). The audit is written to campus/campus_membership.json.

Street frontage
---------------
Every wall of an ordinary (non-school, non-rooftop-structure) record carries a
frontage role in flag bits 4-6 so the facade grammar can respond to the street:

  1 rear / side / party wall (no street frontage)   2 service alley only
  3 street, local          4 street, collector / arterial   (non-commercial building)
  5 commercial corner, secondary frontage (side street)
  6 commercial primary frontage, local   7 commercial primary frontage, major road
  0 no frontage contract: roofs, rooftop-structure records, schools (bit4 = corridor),
    and every mesh outside the 25 tiles (far city, landmarks) -> accepted behaviour

Roles come from the acw.frontage/0 rules (build_urban_identity.build_frontage,
run here on the in-memory records so archetypes are never stale): per ring
edge road class, corner flag and commercial-candidate flag. A commercial
building's primary frontage is its highest-class street edge plus every street
edge within PRIMARY_DEG of it; other street edges are a secondary frontage only
on metadata corners, otherwise plain street walls. Walls are matched to ring
edges geometrically (normal, plane offset, position along the edge); the
match coverage is audited in urban_identity/frontage_bake.json and fails
closed below FRONT_MIN_COVERAGE.
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
import trimesh
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))

import build_urban_identity as urban  # noqa: E402  (acw.frontage/0 rules)
import campus_identity as campus_id  # noqa: E402
from gltf_writer import pack_rgba8, read_glb_primitives, write_glb  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
TILES = REPO / "unreal/Saved/XinyiV2Full/run-01/tiles"
Z_OFFSETS = REPO / "unreal/Saved/XinyiTerrainV0/building_z_offsets.json"
CONTRACT = REPO / "unreal/Saved/XinyiUnrealV2Contract"
OUT = REPO / "unreal/Saved/XinyiLook"

ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM, ARCH_CIVIC, ARCH_SCHOOL = range(8)
ARCH_NAMES = ["low", "walkup", "huaxia", "res_tower", "office_glass", "commercial_podium", "civic", "school"]
assert ARCH_SCHOOL == campus_id.ARCH_SCHOOL
LANDMARKS = HERE / "landmarks.json"

FLAG_CORE, FLAG_ANCHOR, FLAG_PODIUM, FLAG_ROOFTOP, FLAG_CORRIDOR = 1, 2, 4, 8, 16
CORRIDOR_MIN_WALL_M = 6.0

# street frontage role per wall, flag bits 4-6 of non-school records (see module docstring)
FRONT_SHIFT = 4
(FRONT_NONE, FRONT_REAR, FRONT_ALLEY, FRONT_STREET, FRONT_STREET_MAJOR,
 FRONT_COMM_SIDE, FRONT_COMM, FRONT_COMM_MAJOR) = range(8)
FRONT_NAMES = ["none", "rear", "alley", "street", "street_major", "commercial_side", "commercial",
               "commercial_major"]
PRIMARY_DEG = 50.0          # street edges this close in bearing to the best one share the primary frontage
FRONT_MATCH_COS = math.cos(math.radians(15.0))
FRONT_MATCH_OFFSET_M = 0.5  # wall plane vs ring edge line
FRONT_MATCH_PAD_M = 0.25    # wall midpoint may sit this far past an edge end
FRONT_MIN_COVERAGE = 0.995  # share of frontage edge length that must land on wall triangles

# Xinyi Special District (信義計畫區), from OSM boundary roads in Xinyi ENU:
# 基隆路 (W, diagonal) / 忠孝東路 (N) / 松德路 (E) / 信義路 (S).
CORE_DISTRICT = Polygon([(-590, -10), (-85, 905), (1000, 1010), (1110, 720), (930, -10)])
TAIPEI101_ENU = (-59.58, 74.40)


def sha_byte(text: str, k: int = 0) -> int:
    return hashlib.sha256(text.encode()).digest()[k]


# --------------------------------------------------------------------------
# Grouping + classification
# --------------------------------------------------------------------------

class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, child, parent):
        a, b = self.find(child), self.find(parent)
        if a != b:
            self.p[a] = b


def classify(wm, props):
    feats = [b for b in wm["buildings"] if not b["suppressed"]]
    polys = []
    for b in feats:
        parts = [Polygon(p["footprint_enu"], p.get("holes_enu") or []) for p in b["polygons"]]
        parts = [q if q.is_valid else q.buffer(0) for q in parts]
        polys.append(parts[0] if len(parts) == 1 else _union(parts))
    areas = np.array([p.area for p in polys])
    tree = STRtree(polys)
    uf = UF(len(feats))
    order = np.argsort(areas, kind="stable")
    for i in order:
        pi = polys[i]
        if pi.is_empty:
            continue
        cand = tree.query(pi.buffer(0.3))
        best, best_area = None, -1.0
        per = max(pi.length, 1e-6)
        for j in cand:
            if j == i or areas[j] <= areas[i]:
                continue
            shared = pi.buffer(0.3).intersection(polys[j].boundary).length
            small = areas[i] < 40.0
            nested = areas[i] < 0.6 * areas[j] and shared >= 0.45 * per
            if (small and shared > 0.5) or nested:
                if areas[j] > best_area:
                    best, best_area = j, areas[j]
        if best is not None:
            uf.join(i, best)

    groups = defaultdict(list)
    for i in range(len(feats)):
        groups[uf.find(i)].append(i)

    lon0, lat0 = wm["local_frame"]["origin_lonlat"]
    # Grade-A campus membership (group level; rules in campus_identity.py)
    bb = np.array([q.bounds for q in polys if not q.is_empty])
    src_bbox = Polygon.from_bounds(bb[:, 0].min(), bb[:, 1].min(), bb[:, 2].max(), bb[:, 3].max())
    edu = campus_id.edu_features(lon0, lat0)
    campuses = campus_id.grade_a_campuses(edu, src_bbox)
    group_geom = {min(feats[m]["id"] for m in members): _union([polys[m] for m in members])
                  for members in groups.values()}
    school_of, decisions = campus_id.assign_groups(campuses, group_geom, campus_id.school_building_union(edu))
    from worldmodel import lonlat_to_enu
    marks = []
    for lm in json.loads(LANDMARKS.read_text(encoding="utf-8"))["landmarks"]:
        ex, ey = lonlat_to_enu(lm["lonlat"][0], lm["lonlat"][1], lon0, lat0)
        marks.append((ex, ey, lm))

    records = {}
    stats = Counter()
    landmark_hits = Counter()
    for root, members in groups.items():
        heights = [feats[m]["height_m"] for m in members]
        anchor = members[int(np.argmax([heights[k] * 1e6 + areas[m] for k, m in enumerate(members)]))]
        ap = props[feats[anchor]["id"]]
        floors = int(ap.get("floors") or max(1, round(feats[anchor]["height_m"] / 3.2)))
        height = float(feats[anchor]["height_m"])
        fh = height / max(floors, 1)
        if not (2.6 <= fh <= 6.0):
            floors = max(1, round(height / 3.3))
            fh = min(6.0, max(2.6, height / floors))
        total_area = float(sum(areas[m] for m in members))
        c = polys[anchor].representative_point()
        core = CORE_DISTRICT.contains(c)
        d101 = math.dist((c.x, c.y), TAIPEI101_ENU)
        gid = min(feats[m]["id"] for m in members)
        seed = sha_byte(gid)

        if floors <= 3:
            arch = ARCH_LOW
            if total_area >= 2500 and fh >= 4.5:
                arch = ARCH_PODIUM
        elif floors <= 5:
            arch = ARCH_WALKUP
            if core or (total_area >= 1500 and fh >= 4.2):
                arch = ARCH_PODIUM if fh >= 4.2 else ARCH_HUAXIA
        elif floors <= 12:
            arch = ARCH_HUAXIA
            if total_area >= 2500 and fh >= 4.2:
                arch = ARCH_PODIUM
        elif floors <= 24:
            arch = ARCH_RESTOWER
            if core and (fh >= 3.7 or total_area >= 1500):
                arch = ARCH_OFFICE
        else:
            arch = ARCH_OFFICE if (fh >= 3.55 or (core and total_area >= 700)) else ARCH_RESTOWER

        campus = school_of.get(gid)
        if campus is not None:
            arch = ARCH_SCHOOL

        # Landmark art direction (location registry, look-only)
        lm_variant = None
        gc = polys[anchor].centroid          # true centroid: rings / domes match at their centre
        for ex, ey, lm in marks:
            if math.dist((gc.x, gc.y), (ex, ey)) <= lm["radius_m"] and total_area >= lm["min_area_m2"]:
                arch = ARCH_NAMES.index(lm["archetype"])
                lm_variant = int(lm["variant"])
                landmark_hits[lm["name"]] += 1
                if campus is not None:      # a registry landmark keeps its art direction
                    landmark_hits["school_overridden_by_landmark"] += 1
                    campus = None
                break

        # Weathering: old stock outside the planned district weathers hardest.
        base_w = {ARCH_LOW: 170, ARCH_WALKUP: 190, ARCH_HUAXIA: 150, ARCH_RESTOWER: 80,
                  ARCH_OFFICE: 30, ARCH_PODIUM: 70, ARCH_CIVIC: 60, ARCH_SCHOOL: 120}[arch]
        if core:
            base_w = int(base_w * 0.55)
        weather = int(max(0, min(255, base_w + (seed % 64) - 32)))
        stats[ARCH_NAMES[arch]] += 1

        for m in members:
            b = feats[m]
            flags = (FLAG_CORE if core else 0)
            if m == anchor:
                flags |= FLAG_ANCHOR
            elif b["height_m"] < 0.8 * height:
                flags |= FLAG_PODIUM
            elif areas[m] < 40.0 and b["height_m"] > height - 8.0:
                flags |= FLAG_ROOFTOP
            records[b["id"]] = {
                "group": gid,
                "archetype": arch,
                # schools: one palette per campus (all wings of a campus share tile / accent colours)
                "variant": (lm_variant if lm_variant is not None else
                            sha_byte(campus) & 15 if campus is not None else sha_byte(b["id"], 1) & 15),
                "seed": seed,
                "weather": weather,
                "flags": flags,
                "height_m": float(b["height_m"]),
                "floor_h": float(fh),
                "core": bool(core),
                "d101_m": float(d101),
            }
            if campus is not None:
                records[b["id"]]["campus"] = campus
    print("landmark groups:", dict(landmark_hits))
    membership = {"campuses": [{k: c[k] for k in ("id", "name", "level", "bbox_coverage")} for c in campuses],
                  "decisions": decisions, "landmark_conflicts": landmark_hits.get("school_overridden_by_landmark", 0)}
    return records, stats, len(groups), membership, campuses


def _union(parts):
    from shapely.ops import unary_union
    return unary_union(parts)


# --------------------------------------------------------------------------
# Per-component attribute computation
# --------------------------------------------------------------------------

def ring_params(mesh_v: np.ndarray, faces: np.ndarray, up: np.ndarray):
    """Map (x,z) float32 keys of the top-cap boundary loops to perimeter params."""
    top = faces[up]
    edges = np.concatenate([top[:, [0, 1]], top[:, [1, 2]], top[:, [2, 0]]])
    key = np.sort(edges, axis=1)
    uniq, inv, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    boundary = edges[counts[inv.reshape(-1)] == 1]
    nxt = {}
    for a, b in boundary:
        nxt.setdefault(int(a), []).append(int(b))
    params = {}  # xz key -> list of (param, loop_len)
    visited = set()
    for start in sorted(nxt):
        if start in visited:
            continue
        loop = [start]
        visited.add(start)
        cur = start
        while True:
            outs = [n for n in nxt.get(cur, []) if n not in visited or n == start]
            if not outs:
                break
            n = outs[0]
            if n == start:
                break
            loop.append(n)
            visited.add(n)
            cur = n
        pts = mesh_v[loop][:, [0, 2]].astype(np.float64)
        seg = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
        total = float(seg.sum())
        for vi, u in zip(loop, cum):
            k = mesh_v[vi][[0, 2]].astype(np.float32).tobytes()
            params.setdefault(k, []).append((float(u), total))
    return params


def corridor_walls(p, fn, wall, tile_origin, probe):
    """Wall triangles of one school component that face the schoolyard (open corridor side).

    Triangles are grouped per wall plane so both halves of a wall quad agree; the plane's horizontal
    extent is probed along its outward normal (campus_identity.YardProbe)."""
    out = np.zeros(len(p), dtype=bool)
    ox, oy = float(tile_origin[0]), float(tile_origin[1])
    planes = defaultdict(list)
    for t in np.nonzero(wall)[0]:
        n2 = np.array([fn[t, 0], -fn[t, 2]])
        ln = float(np.hypot(*n2))
        if ln < 0.9:
            continue
        n2 /= ln
        q = np.column_stack([p[t, :, 0] + ox, -p[t, :, 2] + oy])
        d = float(np.mean(q @ n2))
        planes[(int(round(n2[0] * 200)), int(round(n2[1] * 200)), int(round(d * 4)))].append((t, n2, q))
    for tris in planes.values():
        n2 = tris[0][1]
        tg = np.array([-n2[1], n2[0]])
        pts = np.concatenate([q for _t, _n, q in tris])
        s = pts @ tg
        if s.max() - s.min() < CORRIDOR_MIN_WALL_M:
            continue
        base = pts[0] - tg * s[0]
        if probe.faces_yard(base + tg * s.min(), base + tg * s.max(), n2):
            for t, _n, _q in tris:
                out[t] = True
    return out


def _bearing_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def frontage_roles(wm, records):
    """Frontage edges per building id as (p0, p1, outward unit normal, role, edge key) in ENU m.

    Runs the acw.frontage/0 generator on the in-memory records (schools and rooftop-structure records
    are handled by its own rules: never commercial / skipped)."""
    look = {bid: {"group": r["group"], "archetype": r["archetype"], "flags": r["flags"]} for bid, r in records.items()}
    frontage, _parts = urban.build_frontage(wm, look, urban.load_roads())
    roles = {}
    summary = Counter()
    school_edges = 0
    for b in frontage:
        edges = b["edges"]
        if records[b["building_id"]]["archetype"] == ARCH_SCHOOL:     # schools keep their own grammar (bit4)
            school_edges += len(edges)
            continue
        street = [e for e in edges if e["front"] >= 2]
        best = max(street, key=lambda e: (e["front"], e["len"]), default=None)
        out = []
        for e in edges:
            major = e["front"] >= 3
            if e["front"] == 1:
                role = FRONT_ALLEY
            elif not b["commercial_candidate"]:
                role = FRONT_STREET_MAJOR if major else FRONT_STREET
            elif _bearing_diff(e["normal_deg"], best["normal_deg"]) <= PRIMARY_DEG:
                role = FRONT_COMM_MAJOR if major else FRONT_COMM
            elif b["corner"]:
                role = FRONT_COMM_SIDE
            else:
                role = FRONT_STREET_MAJOR if major else FRONT_STREET
            a = math.radians(e["normal_deg"])
            out.append((np.array(e["p0"], float), np.array(e["p1"], float), np.array([math.cos(a), math.sin(a)]),
                        role, (b["building_id"], e["part"], e["edge"])))
            summary[FRONT_NAMES[role]] += 1
        roles[b["building_id"]] = out
    stats = {"buildings_with_frontage": len(roles), "school_frontage_edges_not_baked": school_edges,
             "commercial_candidates": sum(1 for b in frontage if b["commercial_candidate"]),
             "corners": sum(1 for b in frontage if b["corner"] and b["building_id"] in roles),
             "frontage_edges_by_role": dict(sorted(summary.items()))}
    return roles, stats


def wall_roles(p, fn, wall, tile_origin, fronts, coverage):
    """Frontage role per triangle: FRONT_REAR for every wall, raised to the role of the frontage ring edge the
    wall lies on (normal within 15 degrees, plane within FRONT_MATCH_OFFSET_M, midpoint on the edge).
    `coverage[edge key]` collects the matched (t0, t1) intervals along each edge for the audit."""
    role = np.zeros(len(p), dtype=np.uint8)
    role[wall] = FRONT_REAR
    if not fronts:
        return role
    idx = np.nonzero(wall)[0]
    ox, oy = float(tile_origin[0]), float(tile_origin[1])
    n2 = np.column_stack([fn[idx, 0], -fn[idx, 2]])
    ln = np.hypot(n2[:, 0], n2[:, 1])
    ok = ln > 0.9
    n2 = n2 / np.maximum(ln, 1e-9)[:, None]
    q = np.stack([p[idx, :, 0] + ox, -p[idx, :, 2] + oy], axis=-1)            # (k, 3, 2) ENU
    tg = np.column_stack([-n2[:, 1], n2[:, 0]])
    s = np.einsum("kcj,kj->kc", q, tg)
    d = np.einsum("kcj,kj->kc", q, n2).mean(axis=1)
    mid = n2 * d[:, None] + tg * ((s.min(axis=1) + s.max(axis=1)) * 0.5)[:, None]
    half = (s.max(axis=1) - s.min(axis=1)) * 0.5
    for p0, p1, ne, r, key in fronts:
        L = float(np.hypot(*(p1 - p0)))
        ue = (p1 - p0) / L
        rel = mid - p0
        t = rel @ ue
        m = (ok & (n2 @ ne >= FRONT_MATCH_COS) & (np.abs(rel @ ne) <= FRONT_MATCH_OFFSET_M)
             & (t >= -FRONT_MATCH_PAD_M) & (t <= L + FRONT_MATCH_PAD_M))
        if not m.any():
            continue
        role[idx[m]] = np.maximum(role[idx[m]], r)
        coverage[key].extend(zip(np.clip(t[m] - half[m], 0.0, L), np.clip(t[m] + half[m], 0.0, L)))
    return role


def component_attributes(mesh: trimesh.Trimesh, ground_offset: float, rec: dict, tile_origin, probe=None,
                         fronts=None, coverage=None):
    """Return per-corner arrays (T*3 rows) for one validated component mesh."""
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    p = v[f]  # (T,3,3) game frame, before ground translation
    fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    up = fn[:, 1] > 0.7
    down = fn[:, 1] < -0.7
    wall = ~(up | down)

    T = len(f)
    uv0 = np.zeros((T, 3, 2), dtype=np.float64)
    # roofs + soffits: tile-local east/north metres
    uv0[:, :, 0] = p[:, :, 0]
    uv0[:, :, 1] = -p[:, :, 2]

    params = ring_params(v, f, up)
    for t in np.nonzero(wall)[0]:
        us, lens = [], []
        for c in range(3):
            k = v[f[t, c]][[0, 2]].astype(np.float32).tobytes()
            cands = params.get(k)
            if not cands:
                us.append(None)
                lens.append(None)
                continue
            us.append(cands)
            lens.append(cands[0][1])
        # resolve ambiguous keys against the other corners
        chosen = []
        ref = next((c[0][0] for c in us if c), 0.0)
        for c in us:
            if not c:
                chosen.append((ref, 0.0))
                continue
            best = min(c, key=lambda pl: abs(pl[0] - ref))
            chosen.append(best)
        u = np.array([c[0] for c in chosen])
        L = max((c[1] for c in chosen), default=0.0)
        if L > 0 and u.max() - u.min() > 0.5 * L:
            u = np.where(u < 0.5 * L, u + L, u)
        uv0[t, :, 0] = u
        uv0[t, :, 1] = p[t, :, 1]  # metres above surveyed ground (pre-offset)

    uv1 = np.empty((T, 3, 2), dtype=np.float64)
    uv1[:, :, 0] = rec["height_m"]
    uv1[:, :, 1] = rec["floor_h"]
    col = np.empty((T, 3, 4), dtype=np.uint8)
    col[:, :] = (rec["archetype"] * 16 + rec["variant"], rec["seed"], rec["weather"], rec["flags"])
    if probe is not None and rec["archetype"] == ARCH_SCHOOL:
        col[corridor_walls(p, fn, wall, tile_origin, probe), :, 3] |= FLAG_CORRIDOR
    role = None
    if rec["archetype"] != ARCH_SCHOOL and not rec["flags"] & FLAG_ROOFTOP:
        role = wall_roles(p, fn, wall, tile_origin, fronts, coverage)
        col[:, :, 3] |= (role << FRONT_SHIFT)[:, None]
    normals = np.repeat(fn[:, None, :], 3, axis=1)
    return normals, uv0, uv1, col, role


def weld(pos, nrm, uv0, uv1, col):
    """Weld corners whose full attribute rows are bit-identical (deterministic)."""
    rows = np.concatenate([
        pos.astype(np.float32).view(np.uint32),
        nrm.astype(np.float32).view(np.uint32),
        uv0.astype(np.float32).view(np.uint32),
        uv1.astype(np.float32).view(np.uint32),
        col.astype(np.uint32),
    ], axis=1)
    uniq, first, inv = np.unique(rows, axis=0, return_index=True, return_inverse=True)
    # keep first-appearance order for stable, cache-friendly output
    order = np.argsort(first, kind="stable")
    remap = np.empty_like(order)
    remap[order] = np.arange(len(order))
    idx = remap[inv.reshape(-1)].reshape(-1, 3).astype(np.uint32)
    sel = first[order]
    return pos[sel], nrm[sel], uv0[sel], uv1[sel], col[sel], idx


# --------------------------------------------------------------------------

def build(out_dir: Path):
    contract = json.loads((CONTRACT / "xinyi_unreal_v2_contract.json").read_text())
    z_offsets = json.loads(Z_OFFSETS.read_text())
    z_offsets = z_offsets["offsets_m"]
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    records, arch_stats, group_count, membership, campuses = classify(wm, props)
    all_polys = [Polygon(pt["footprint_enu"], pt.get("holes_enu") or []).buffer(0)
                 for b in wm["buildings"] if not b["suppressed"] for pt in b["polygons"]]
    probes = {c["id"]: campus_id.YardProbe(c["geom"], all_polys) for c in campuses}
    corridor_tris = 0
    fronts, front_stats = frontage_roles(wm, records)
    coverage = defaultdict(list)
    role_area = defaultdict(Counter)        # archetype name -> role name -> wall m2

    tiles_out = out_dir / "tiles"
    tiles_out.mkdir(parents=True, exist_ok=True)
    manifest = []
    sidecar = []
    import re
    bid_re = re.compile(r"^(tp_building_height\.\d+)")

    for row in contract["tiles"]:
        tile = row["tile"]
        scene = trimesh.load_scene(TILES / row["building_glb"], file_type="glb", process=False)
        P, N, U0, U1, C = [], [], [], [], []
        comp = 0
        for node in sorted(scene.graph.nodes_geometry):
            bid = bid_re.match(str(node)).group(1)
            _, gname = scene.graph[node]
            mesh = scene.geometry[gname]
            rec = records[bid]
            nrm, uv0, uv1, col, role = component_attributes(mesh, float(z_offsets[bid]), rec, row["origin_enu_m"],
                                                            probes.get(rec.get("campus")), fronts.get(bid), coverage)
            if rec["archetype"] == ARCH_SCHOOL:
                corridor_tris += int(np.count_nonzero(col[:, 0, 3] & FLAG_CORRIDOR))
            if role is not None:
                tri = np.asarray(mesh.vertices, dtype=np.float64)[np.asarray(mesh.faces)]
                area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
                for r in np.unique(role[role > 0]):
                    role_area[ARCH_NAMES[rec["archetype"]]][FRONT_NAMES[r]] += float(area[role == r].sum())
            m2 = mesh.copy()
            m2.apply_translation([0.0, float(z_offsets[bid]), 0.0])
            corners = np.asarray(m2.vertices, dtype=np.float64)[np.asarray(m2.faces)]
            P.append(corners.reshape(-1, 3))
            N.append(nrm.reshape(-1, 3))
            U0.append(uv0.reshape(-1, 2))
            U1.append(uv1.reshape(-1, 2))
            C.append(col.reshape(-1, 4))
            comp += 1
        # float32 exactly as the accepted runtime GLB serialises it
        pos = np.concatenate(P).astype(np.float32)
        nrm = np.concatenate(N).astype(np.float32)
        uv0 = np.concatenate(U0).astype(np.float32)
        uv1 = np.concatenate(U1).astype(np.float32)
        col = np.concatenate(C).astype(np.uint8)
        wpos, wnrm, wuv0, wuv1, wcol, idx = weld(pos, nrm, uv0, uv1, col)

        # ---- fail-closed geometry equivalence against the accepted runtime tile
        ref = read_glb_primitives(CONTRACT / "building_runtime_tiles" / row["runtime_building_glb"])[0]
        ref_soup = ref["position"][ref["indices"].reshape(-1)]
        look_soup = wpos[idx.reshape(-1)]
        if ref_soup.shape != look_soup.shape or not np.array_equal(
            ref_soup.view(np.uint32), look_soup.view(np.uint32)
        ):
            raise RuntimeError(f"look tile triangle soup differs from accepted runtime tile {tile}")

        name = f"xinyi_look_{tile}.glb"
        write_glb(tiles_out / name, [{
            "name": "XinyiCity",
            "positions": wpos, "normals": wnrm, "uv0": wuv0, "uv1": wuv1, "uv2": pack_rgba8(wcol),
            "indices": idx, "base_color": [0.7, 0.7, 0.7, 1.0],
        }], mesh_name=f"SM_XinyiLook_{tile}")
        manifest.append({
            "tile": tile,
            "path": name,
            "sha256": hashlib.sha256((tiles_out / name).read_bytes()).hexdigest(),
            "components": comp,
            "triangles": int(len(idx)),
            "vertices_accepted": int(len(ref["position"])),
            "vertices_look": int(len(wpos)),
            "accepted_runtime_sha256": row["runtime_building_sha256"],
            "triangle_soup_bit_identical": True,
            "origin_enu_m": row["origin_enu_m"],
            "expected_ue_translation_cm": row["expected_ue_translation_cm"],
        })
        print(f"{tile}: {len(idx)} tris, verts {len(ref['position'])} -> {len(wpos)}", flush=True)

    # ---- frontage bake audit (fail closed on poor wall <-> ring-edge matching)
    total_len = matched_len = 0.0
    unmatched = []
    for bid, rows in fronts.items():
        for p0, p1, _ne, r, key in rows:
            L = float(np.hypot(*(p1 - p0)))
            iv = sorted(coverage.get(key, []))
            got, end = 0.0, 0.0
            for a, b in iv:
                a = max(a, end)
                if b > a:
                    got += b - a
                    end = b
            total_len += L
            matched_len += min(got, L)
            if got < 0.5 * L:
                unmatched.append({"edge": list(key), "len": round(L, 2), "matched": round(got, 2),
                                  "role": FRONT_NAMES[r]})
    share = matched_len / max(total_len, 1e-9)
    bake = {"schema": "acw.frontage_bake/0",
            "encoding": "flags bits 4-6 of non-school, non-rooftop-structure walls; 0 = no frontage contract",
            "roles": {str(i): n for i, n in enumerate(FRONT_NAMES)},
            "rules": {"primary_deg": PRIMARY_DEG, "match_normal_deg": 15.0, "match_offset_m": FRONT_MATCH_OFFSET_M,
                      "match_pad_m": FRONT_MATCH_PAD_M, "min_coverage": FRONT_MIN_COVERAGE},
            **front_stats,
            "frontage_edge_length_m": round(total_len, 1), "matched_length_m": round(matched_len, 1),
            "matched_share": round(share, 4), "edges_mostly_unmatched": len(unmatched),
            "unmatched_sample": unmatched[:40],
            "wall_area_m2_by_archetype_role": {a: {k: round(v) for k, v in sorted(c.items())}
                                               for a, c in sorted(role_area.items())}}
    (out_dir / "urban_identity").mkdir(parents=True, exist_ok=True)
    (out_dir / "urban_identity/frontage_bake.json").write_text(json.dumps(bake, indent=1) + "\n", encoding="utf-8")
    print(f"frontage bake: {share:.4f} of {total_len:.0f} m frontage matched to walls, "
          f"{len(unmatched)} edges mostly unmatched", flush=True)
    if share < FRONT_MIN_COVERAGE:
        raise RuntimeError(f"frontage wall matching covers {share:.4f} < {FRONT_MIN_COVERAGE} of frontage length")

    for bid, rec in sorted(records.items()):
        sidecar.append({"building_id": bid, **{k: rec[k] for k in ("group", "archetype", "variant", "seed",
                                                                   "weather", "flags", "floor_h")},
                        "archetype_name": ARCH_NAMES[rec["archetype"]],
                        **({"campus": rec["campus"]} if "campus" in rec else {})})
    with gzip.open(out_dir / "look_buildings.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as fh:
        for r in sidecar:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    report = {
        "status": "PASS_LOOK_TILES",
        "tiles": manifest,
        "building_groups": group_count,
        "archetype_group_counts": dict(sorted(arch_stats.items())),
        "totals": {
            "triangles": int(sum(t["triangles"] for t in manifest)),
            "vertices_accepted": int(sum(t["vertices_accepted"] for t in manifest)),
            "vertices_look": int(sum(t["vertices_look"] for t in manifest)),
        },
        "contract": "triangle soup bit-identical to accepted runtime tiles; attributes are look-dev only",
        "frontage": {k: bake[k] for k in ("buildings_with_frontage", "commercial_candidates", "corners",
                                          "frontage_edges_by_role", "matched_share")},
    }
    (out_dir / "look_tiles.report.json").write_text(json.dumps(report, indent=2) + "\n")
    school_groups = sorted({r["group"] for r in records.values() if r["archetype"] == ARCH_SCHOOL})
    membership.update({"schema": "acw.campus_membership/0", "rules": {
        "inside_min": campus_id.INSIDE_MIN, "inside_min_tagged": campus_id.INSIDE_MIN_TAGGED,
        "osm_cover_min": campus_id.OSM_COVER_MIN, "attach_gap_m": campus_id.ATTACH_GAP_M,
        "grade_a_levels": list(campus_id.GRADE_A_LEVELS), "grade_a_min_coverage": campus_id.GRADE_A_MIN_COVERAGE},
        "school_groups": len(school_groups),
        "school_records": sum(1 for r in records.values() if r["archetype"] == ARCH_SCHOOL),
        "corridor_wall_triangles": corridor_tris})
    (out_dir / "campus").mkdir(parents=True, exist_ok=True)
    (out_dir / "campus/campus_membership.json").write_text(json.dumps(membership, indent=1, ensure_ascii=False) + "\n",
                                                           encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("building_groups", "archetype_group_counts", "totals")}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
