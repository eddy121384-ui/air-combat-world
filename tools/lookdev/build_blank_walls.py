"""Blank side-wall v0B: mark high-confidence exposed party-wall faces so the facade shader draws them windowless.

Root cause: `xc_wall` (xinyi_city.hlsl) synthesises windows, balconies, cages, AC units and night window light on every
wall face. Exposed party walls above a lower neighbour - including the 27 wall-ad hosts - are windowless in the real
fabric far more often than not, but rendered with a full window grid (and lit windows at night).

Method (no geometry change, no new vertex channel): the look tiles already carry a per-building facade generation code
in TEXCOORD_2.x bits 15-17 (docs/xinyi-facade-metadata-payload-v0.md); codes 5-7 were reserved. A selected wall face
gets code + 5 on its own vertices (unknown 0 -> 5, legacy 1 -> 6, huaxia 2 -> 7); `xc_wall` decodes `blank = gen > 4.5`,
restores `gen`, and renders the face as a plain lived-in wall in one coherent per-face branch. Only the vertices of the
selected wall triangles change; a vertex shared with an unselected triangle is duplicated first, so the triangle soup
(positions per triangle corner, triangle order) stays bit-identical. Patched tiles go to a separate folder
(`tiles_blank/`); the asset stage imports them only when `ACW_XINYI_BLANK_WALLS` is not `off`.

Selection (deterministic, global rules, no building ids). A face qualifies only if ALL hold:
  * it is a Gate 0 valid wall of build_wall_ads.py (lot line, exposure, class, street exposure, no own wing ...);
  * along its FULL ring edge (0.5 m samples): another building group's footprint touches it (<= TOUCH_M) on
    >= TOUCH_FRAC of the edge, lies within the 1 m lot-line distance on >= LOT_FRAC, and no sample faces the
    building's own wing - otherwise part of the face may be an open, windowed flank -> keep the facade;
  * the face is <= MAX_FACE_M long (a lot depth) and no neighbour shares much more than this edge with the host
    (a low block wrapping a tower is usually its own podium / complex split into WFS records);
  * the matched tile triangles are rear / side walls (baked frontage role 1), cover >= COVER_FRAC of the edge length
    and reach the roof line; the generation code is 0-2 and agrees with the look sidecar.
Primary scope: the faces hosting the 27 wall ads. Secondary: at most SECONDARY_MAX further faces, best-exposed first,
>= SECONDARY_SPACING_M apart and away from boards. Everything else (incl. ambiguous hosts) keeps its facade.

Outputs (unreal/Saved/XinyiLook/blank_walls/): blank_walls.json (faces + rejections), blank_walls.report.json
(PASS_BLANK_WALLS), tiles_blank/<tile glb> for the tiles that contain a selected face.
Usage: python tools/lookdev/build_blank_walls.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_wall_ads as wa  # noqa: E402  (Gate 0 context, rules and outputs)
import facade_generation as fg  # noqa: E402
from gltf_writer import read_glb_primitives, write_glb  # noqa: E402

LOOK = REPO / "unreal/Saved/XinyiLook"
OUT = LOOK / "blank_walls"
TILES = LOOK / "tiles"

BLANK_OFFSET = fg.BLANK_FACE_OFFSET   # facade code + 5 = blank face (codes 5..7, reserved by the payload v0 contract)
SAMPLE_M = 0.5
TOUCH_M = 0.3               # footprints this close share the wall (party wall)
TOUCH_FRAC = 0.80
LOT_FRAC = 0.95             # within the 1 m lot-line distance along nearly the whole face
COVER_FRAC = 0.98           # matched wall triangles cover the edge
MAX_FACE_M = 25.0           # longer than a typical Taipei lot depth: more likely one complex than a party wall
WRAP_FACTOR = 1.25          # a neighbour sharing more than ~this edge wraps the host (podium / complex)
PLANE_TOL_M = 0.08
NORMAL_COS = math.cos(math.radians(3.0))
FRONT_REAR = 1
SECONDARY_MAX = 12
SECONDARY_MIN_EDGE_M = 8.0     # narrower slivers add nothing at 300-600 m
SECONDARY_SPACING_M = 80.0
SECONDARY_AWAY_FROM_BOARDS_M = 40.0
TILE_M = 500.0


def edge_of(ctx, wall_id):
    """Full ring edge (a, b) of a Gate 0 wall id `building/part/k` (k = index among the part's edges >= 5 m)."""
    bid, pi, k = wall_id.rsplit("/", 2)
    poly = ctx["parts"][int(pi)][2]
    if ctx["parts"][int(pi)][0] != bid:
        raise RuntimeError("part index mismatch for %s" % wall_id)
    ring = list(orient(poly, 1.0).exterior.coords)
    edges = [(np.array(a), np.array(b)) for a, b in zip(ring[:-1], ring[1:]) if math.dist(a, b) >= wa.MIN_EDGE_M]
    return edges[int(k)], int(pi)


def probe(ctx, tree, groups, a, b, pi):
    """Fractions of the full edge: touching another group, within the lot-line distance, facing the own wing."""
    L = float(np.hypot(*(b - a)))
    t = (b - a) / L
    n = np.array([t[1], -t[0]])
    ns = max(2, int(L / SAMPLE_M))
    s = (np.arange(ns) + 0.5) * (L / ns)
    base = a[None, :] + s[:, None] * t[None, :]
    grp = groups[pi]
    touch, lot, own = np.zeros(ns, bool), np.zeros(ns, bool), np.zeros(ns, bool)
    nbrs = set()
    for d in (0.1, TOUCH_M, 0.65, wa.LOT_LINE_M):
        pts = shapely.points(base[:, 0] + n[0] * d, base[:, 1] + n[1] * d)
        si, pj = tree.query(pts, predicate="within")
        for i_, j_ in zip(si, pj):
            if j_ == pi:
                continue
            if groups[j_] == grp:
                own[i_] = True
            else:
                lot[i_] = True
                nbrs.add(int(j_))
                if d <= TOUCH_M:
                    touch[i_] = True
    return float(touch.mean()), float(lot.mean()), float(own.mean()), n, nbrs


def wrap_len(ctx, pi, nbrs):
    """Longest boundary any lot-line neighbour shares with the host part (m). A neighbour sharing much more than this
    one edge wraps the host (a podium / complex around a tower): its \"party wall\" is a joint of one structure."""
    host = ctx["parts"][pi][2].buffer(0.35)
    return max((host.intersection(ctx["parts"][j][2].boundary).length for j in nbrs), default=0.0)


class TileSet:
    def __init__(self):
        rep = json.loads((LOOK / "look_tiles.report.json").read_text(encoding="utf-8"))
        self.rows = {}
        for row in rep["tiles"]:
            ox, oy = row["origin_enu_m"]
            self.rows[(int(ox // TILE_M), int(oy // TILE_M))] = row
        self.cache = {}

    def get(self, key):
        if key not in self.cache:
            row = self.rows.get(key)
            if row is None:
                self.cache[key] = None
            else:
                pr = read_glb_primitives(TILES / row["path"])
                if len(pr) != 1:
                    raise RuntimeError("tile %s: expected one primitive" % row["tile"])
                p = {k: np.array(v) for k, v in pr[0].items() if k != "material"}
                ox, oy = row["origin_enu_m"]
                pos = p["position"].astype(np.float64)
                tri = p["indices"].astype(np.int64)
                corners = np.stack([pos[tri[:, k]] for k in range(3)], axis=1)
                enu = np.stack([corners[..., 0] + ox, -corners[..., 2] + oy, corners[..., 1]], axis=-1)
                nr = np.cross(enu[:, 1] - enu[:, 0], enu[:, 2] - enu[:, 0])
                ln = np.linalg.norm(nr, axis=1)
                nr = nr / np.maximum(ln, 1e-12)[:, None]
                self.cache[key] = {"row": row, "prim": p, "enu": enu, "nrm": nr, "ok": ln > 1e-9, "sel": set()}
        return self.cache[key]


def match_face(tiles, a, b, n):
    """Wall triangles of the accepted tiles lying on this edge's wall plane, facing outward, within the edge span."""
    L = float(np.hypot(*(b - a)))
    t = (b - a) / L
    n3, t3, a3 = np.array([n[0], n[1], 0.0]), np.array([t[0], t[1], 0.0]), np.array([a[0], a[1], 0.0])
    mid = (a + b) / 2.0
    tx, ty = int(math.floor(mid[0] / TILE_M)), int(math.floor(mid[1] / TILE_M))
    hits = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            T = tiles.get((tx + dx, ty + dy))
            if T is None:
                continue
            e = T["enu"]
            d = (e - a3) @ n3
            s = (e - a3) @ t3
            sel = (T["ok"] & (T["nrm"] @ n3 >= NORMAL_COS) & (np.abs(d).max(axis=1) <= PLANE_TOL_M)
                   & (s.min(axis=1) >= -0.3) & (s.max(axis=1) <= L + 0.3))
            for i in np.nonzero(sel)[0]:
                hits.append((T, int(i), float(s[i].min()), float(s[i].max()), float(e[i, :, 2].min()),
                             float(e[i, :, 2].max())))
    return hits


def coverage(hits, L):
    iv = sorted((max(0.0, h[2]), min(L, h[3])) for h in hits)
    cov, cur0, cur1 = 0.0, None, None
    for s0, s1 in iv:
        if cur1 is None or s0 > cur1:
            if cur1 is not None:
                cov += cur1 - cur0
            cur0, cur1 = s0, s1
        else:
            cur1 = max(cur1, s1)
    if cur1 is not None:
        cov += cur1 - cur0
    return cov / L


def role_of(T, i):
    """Baked frontage role (flag bits 4-6) of triangle i, from its first corner's TEXCOORD_2.y."""
    vi = int(T["prim"]["indices"][i, 0])
    y = float(T["prim"]["texcoord_2"][vi, 1])
    a = int(round(y - 256 * math.floor(y / 256.0 + 1e-4)))
    return (a >> 4) & 7


def gen_of(T, i):
    vi = int(T["prim"]["indices"][i, 0])
    return fg.decode_x(float(T["prim"]["texcoord_2"][vi, 0]))[1]


def evaluate(ctx, tree, groups, tiles, side, w):
    """-> (ok, info dict, hits)."""
    (a, b), pi = edge_of(ctx, w["wall_id"])
    touch, lot, own, n, nbrs = probe(ctx, tree, groups, a, b, pi)
    L = float(np.hypot(*(b - a)))
    info = {"wall_id": w["wall_id"], "building_id": w["building_id"], "edge_len_m": round(L, 2),
            "touch_frac": round(touch, 3), "lot_frac": round(lot, 3), "own_frac": round(own, 3)}
    if own > 0.0:
        return False, {**info, "reject": "faces_own_wing"}, []
    if L > MAX_FACE_M:
        return False, {**info, "reject": "face_longer_than_a_lot"}, []
    info["neighbour_shared_m"] = round(wrap_len(ctx, pi, nbrs), 2)
    if info["neighbour_shared_m"] > WRAP_FACTOR * L + 1.0:
        return False, {**info, "reject": "neighbour_wraps_host"}, []
    if lot < LOT_FRAC:
        return False, {**info, "reject": "lot_line_not_whole_face"}, []
    if touch < TOUCH_FRAC:
        return False, {**info, "reject": "gap_not_touching"}, []
    hits = match_face(tiles, a, b, n)
    if not hits:
        return False, {**info, "reject": "no_mesh_face"}, []
    cov = coverage(hits, L)
    info["mesh_cover"] = round(cov, 3)
    ztop = max(h[5] for h in hits)
    info["mesh_triangles"] = len(hits)
    if cov < COVER_FRAC:
        return False, {**info, "reject": "mesh_face_partial"}, []
    if abs(ztop - w["top_m"]) > 0.3:
        return False, {**info, "reject": "mesh_face_not_to_roof"}, []
    roles = {role_of(T, i) for T, i, *_ in hits}
    gens = {gen_of(T, i) for T, i, *_ in hits}
    info["roles"], info["gen_codes"] = sorted(roles), sorted(gens)
    if roles != {FRONT_REAR}:
        return False, {**info, "reject": "not_rear_side_wall"}, []
    want = {"unknown": 0, "legacy": 1, "huaxia": 2}.get(side[w["building_id"]]["facade_generation"])
    if gens != {want}:
        return False, {**info, "reject": "generation_mismatch"}, []
    return True, info, hits


def patch_tiles(selected):
    """Write tiles_blank/<glb> for every tile with a selected triangle; returns per-tile rows."""
    out_dir = OUT / "tiles_blank"
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.glb"):
        p.unlink()
    rows = []
    by_tile = {}
    for T, i in selected:
        by_tile.setdefault(T["row"]["tile"], (T, set()))[1].add(i)
    for tile in sorted(by_tile):
        T, tri_sel = by_tile[tile]
        p = T["prim"]
        idx = p["indices"].astype(np.int64).copy()
        pos, nrm, uv0, uv1, uv2 = (p["position"].copy(), p["normal"].copy(), p["texcoord_0"].copy(),
                                   p["texcoord_1"].copy(), p["texcoord_2"].astype(np.float32).copy())
        sel = np.zeros(len(idx), bool)
        sel[sorted(tri_sel)] = True
        used_sel = np.unique(idx[sel])
        used_other = np.unique(idx[~sel])
        shared = np.intersect1d(used_sel, used_other)
        remap = {}
        if len(shared):                                 # duplicate shared vertices for the selected triangles
            base = len(pos)
            remap = {int(v): base + k for k, v in enumerate(shared)}
            pos, nrm, uv0, uv1, uv2 = (np.concatenate([arr, arr[shared]]) for arr in (pos, nrm, uv0, uv1, uv2))
            for r in np.nonzero(sel)[0]:
                idx[r] = [remap.get(int(v), int(v)) for v in idx[r]]
        verts = np.unique(idx[sel])
        for v in verts:
            b0, code = fg.decode_x(float(uv2[v, 0]))
            if code > fg.GEN_HUAXIA:
                raise RuntimeError("tile %s vertex %d: code %d cannot carry the blank flag" % (tile, v, code))
            uv2[v, 0] = np.float32((code + BLANK_OFFSET) * fg.PAYLOAD_UNIT + b0)
        name = T["row"]["path"]
        write_glb(out_dir / name, [{
            "name": "XinyiCity", "positions": pos, "normals": nrm, "uv0": uv0, "uv1": uv1, "uv2": uv2,
            "indices": idx.astype(np.uint32), "base_color": [0.7, 0.7, 0.7, 1.0],
        }], mesh_name=f"SM_XinyiLook_{tile}")
        # fail closed: the triangle soup (corner positions, order) must equal the accepted look tile
        chk = read_glb_primitives(out_dir / name)[0]
        soup_new = np.asarray(chk["position"])[np.asarray(chk["indices"]).reshape(-1, 3)]
        soup_old = np.asarray(p["position"])[np.asarray(p["indices"]).reshape(-1, 3)]
        if soup_new.shape != soup_old.shape or not np.array_equal(soup_new, soup_old):
            raise RuntimeError("tile %s: triangle soup changed" % tile)
        rows.append({"tile": tile, "path": name, "triangles_marked": int(sel.sum()), "vertices_marked": int(len(verts)),
                     "vertices_duplicated": len(remap), "vertices": int(len(pos)),
                     "sha256": hashlib.sha256((out_dir / name).read_bytes()).hexdigest(),
                     "source_sha256": T["row"]["sha256"]})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    audit = json.loads((wa.OUT / "wall_ad_audit.json").read_text(encoding="utf-8"))
    plan = json.loads((wa.OUT / "wall_ads.json").read_text(encoding="utf-8"))
    ctx = wa.load_context()
    tree = STRtree([p[2] for p in ctx["parts"]])
    groups = [p[1] for p in ctx["parts"]]
    tiles = TileSet()
    side = ctx["side"]
    valid = {w["wall_id"]: w for w in audit["walls"]}
    hosts = [i["wall_id"] for i in plan["instances"]]
    faces, rejected, sel_tris = [], [], []
    reasons = Counter()
    for wid in hosts:
        ok, info, hits = evaluate(ctx, tree, groups, tiles, side, valid[wid])
        info["scope"] = "ad_host"
        if ok:
            faces.append(info)
            sel_tris += [(T, i) for T, i, *_ in hits]
        else:
            rejected.append(info)
            reasons["host_" + info["reject"]] += 1
    boards = [(i["e"], i["n"]) for i in plan["instances"]]
    rank = sorted((w for wid, w in valid.items() if wid not in set(hosts)),
                  key=lambda w: (-(w["major_road"] + (w["condition"] == "corner")), -w["area_m2"], w["wall_id"]))
    chosen = []
    for w in rank:
        if len(chosen) >= SECONDARY_MAX:
            break
        mid = ((w["p0"][0] + w["p1"][0]) / 2, (w["p0"][1] + w["p1"][1]) / 2)
        if any(math.dist(mid, b) < SECONDARY_AWAY_FROM_BOARDS_M for b in boards):
            reasons["secondary_skip_near_board"] += 1
            continue
        if any(math.dist(mid, c) < SECONDARY_SPACING_M for c in chosen):
            reasons["secondary_skip_spacing"] += 1
            continue
        if w["band_m"] < 9.0 or w["edge_len_m"] < SECONDARY_MIN_EDGE_M:
            reasons["secondary_skip_small_band"] += 1
            continue
        ok, info, hits = evaluate(ctx, tree, groups, tiles, side, w)
        info["scope"] = "secondary"
        if ok:
            faces.append(info)
            chosen.append(mid)
            sel_tris += [(T, i) for T, i, *_ in hits]
        else:
            rejected.append(info)
            reasons["secondary_" + info["reject"]] += 1
    rows = patch_tiles(sel_tris)
    doc = {"schema": "acw.blank_walls/0", "blank_code_offset": BLANK_OFFSET,
           "rules": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float))},
           "faces": faces, "rejected": rejected}
    (OUT / "blank_walls.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_host = sum(f["scope"] == "ad_host" for f in faces)
    report = {
        "status": "PASS_BLANK_WALLS" if rows else "FAIL_BLANK_WALLS",
        "faces": len(faces), "ad_host_faces": n_host, "ad_hosts": len(hosts),
        "secondary_faces": len(faces) - n_host, "rejected": dict(sorted(reasons.items())),
        "triangles_marked": sum(r["triangles_marked"] for r in rows),
        "vertices_marked": sum(r["vertices_marked"] for r in rows),
        "vertices_duplicated": sum(r["vertices_duplicated"] for r in rows),
        "tiles": rows, "wall_ads_sha256": hashlib.sha256((wa.OUT / "wall_ads.json").read_bytes()).hexdigest(),
        "sha256": hashlib.sha256((OUT / "blank_walls.json").read_bytes()).hexdigest(),
    }
    (OUT / "blank_walls.report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "tiles"}))
    if report["status"] != "PASS_BLANK_WALLS":
        raise SystemExit("blank walls: nothing selected")


if __name__ == "__main__":
    main()
