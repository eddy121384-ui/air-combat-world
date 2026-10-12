"""Phase 1D prototype: deterministic coarser massing levels derived from the L2 building whitebox, measured on pilots.

L2  individual building parts (the accepted whitebox; counts taken from the pilot reports)
L1  block massing: parts bucketed by 50 m NTW cell (centroid ownership), unioned (+1 m / -1 m), simplified 2 m,
    extruded to the area-weighted mean child height. Child identity kept in a map (building_id -> L1 id).
L0  settlement silhouette: L1 polygons per 500 m owner tile, unioned (+25 m / -25 m), simplified 15 m,
    extruded to the area-weighted p75 height.
Triangle counts use the SAME extruder as the accepted pipeline (GEOS CDT + trimesh) without per-part QA gates;
this is a sizing prototype, not an accepted LOD asset. Determinism: all iteration is over sorted keys.
Writes data/ntw/lod_prototype.json.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/citygen_v2"))
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
import build_pilot as bp  # noqa: E402
from geometry import _polygonal_parts, extrude_geos_polygon  # noqa: E402

L1_CELL, L0_TILE = 50.0, 500.0


def parts_of(pid):
    cfg = bp.pilot_cfg(pid)
    ix0, iy0 = bp.block_of(cfg)
    bx0, by0, bx1, by1 = ix0 * 500.0, iy0 * 500.0, (ix0 + 5) * 500.0, (iy0 + 5) * 500.0
    feats = (bp.load_wfs if cfg["provider"] == "taipei_wfs" else bp.load_overture)(cfg, bx0, by0, bx1, by1)
    out = []
    for f in feats:
        if f["excluded"]:
            continue
        for si, rings in f["polys"]:
            try:
                p = Polygon(rings[0], rings[1:])
            except Exception:  # noqa: BLE001
                continue
            if not p.is_valid:
                p = shapely.make_valid(p)
            for q in _polygonal_parts(p):
                if q.area > 1e-6:
                    out.append((f["id"], si, q, f["height_m"], bp.vmean(rings[0])))
    return out, (bx0, by0, bx1, by1)


def tris(poly, h):
    try:
        m = extrude_geos_polygon(poly, float(h))
        return int(len(m.faces)), int(len(m.vertices))
    except Exception:  # noqa: BLE001
        return 0, 0


def merge(polys_h, buf, simp, min_area):
    """-> list of (polygon, area-weighted heights array) after union; heights per merged polygon via area weighting."""
    u = unary_union([p.buffer(buf, join_style=2) for p, _ in polys_h]).buffer(-buf, join_style=2).simplify(simp)
    res = []
    for g in _polygonal_parts(u):
        if g.area >= min_area:
            res.append(g)
    return res


def level_stats(pid):
    parts, ext = parts_of(pid)
    area_km2 = (ext[2] - ext[0]) * (ext[3] - ext[1]) / 1e6
    l2_t = l2_v = 0
    for _, _, p, h, _ in parts:
        t, v = tris(p, h)
        l2_t += t
        l2_v += v
    # L1
    cells = defaultdict(list)
    for bid, si, p, h, c in parts:
        cells[(math.floor(c[0] / L1_CELL), math.floor(c[1] / L1_CELL))].append((bid, p, h))
    l1, idmap = [], {}
    for k in sorted(cells):
        items = cells[k]
        merged = merge([(p, h) for _, p, h in items], 1.0, 2.0, 20.0)
        for gi, g in enumerate(merged):
            ws = [(p.intersection(g).area, h) for _, p, h in items if p.intersects(g)]
            wsum = sum(w for w, _ in ws)
            hm = sum(w * h for w, h in ws) / wsum if wsum > 0 else 9.6
            cid = f"L1:{k[0]:+05d}_{k[1]:+05d}:{gi}"
            l1.append((cid, g, max(hm, 3.0)))
            for bid, p, _ in items:
                if p.intersects(g):
                    idmap[bid] = cid
    l1_t = l1_v = 0
    for _, g, h in l1:
        t, v = tris(g, h)
        l1_t += t
        l1_v += v
    # L0
    tiles = defaultdict(list)
    for cid, g, h in l1:
        c = g.centroid
        tiles[(math.floor(c.x / L0_TILE), math.floor(c.y / L0_TILE))].append((g, h))
    l0_t = l0_v = l0_n = 0
    for k in sorted(tiles):
        items = tiles[k]
        merged = merge(items, 25.0, 15.0, 400.0)
        hs = np.array([h for _, h in items])
        w = np.array([g.area for g, _ in items])
        order = np.argsort(hs)
        cw = np.cumsum(w[order]) / w.sum()
        h75 = float(hs[order][np.searchsorted(cw, 0.75)])
        for g in merged:
            t, v = tris(g, h75)
            l0_t += t
            l0_v += v
            l0_n += 1
    return {
        "pilot": pid, "block_area_km2": round(area_km2, 2), "source_parts": len(parts),
        "L2": {"objects": len(parts), "triangles": l2_t, "vertices": l2_v, "tri_per_km2": round(l2_t / area_km2)},
        "L1": {"objects": len(l1), "triangles": l1_t, "vertices": l1_v, "tri_per_km2": round(l1_t / area_km2),
               "reduction_vs_L2_triangles_x": round(l2_t / max(l1_t, 1), 1), "identity_map_entries": len(idmap)},
        "L0": {"objects": l0_n, "triangles": l0_t, "vertices": l0_v, "tri_per_km2": round(l0_t / area_km2),
               "reduction_vs_L2_triangles_x": round(l2_t / max(l0_t, 1), 1)},
    }


def main():
    out = {"method": __doc__.split("\n")[0], "pilots": [level_stats(p["id"]) for p in json.loads((HERE / "pilots.json").read_text())["pilots"]]}
    (REPO / "data/ntw/lod_prototype.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
