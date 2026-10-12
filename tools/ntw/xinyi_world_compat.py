"""Xinyi <-> world compatibility (Phase 2A). Read-only with respect to every accepted Xinyi artefact.

1. Sector outline: the 25 accepted ENU tiles (x -1500..1000, y -1000..1500 m) inverted EXACTLY through the
   accepted ENU formula (tools/compiler/worldmodel.py) to lon/lat, then to EPSG:3826; densified edges.
2. Placement in the world: world cells / NTW L2 tiles touched, distance to world edges, and the full Xinyi-level
   UE (cm) -> world UE (cm) 2-D affine composed from the Phase-1 measured ENU->NTW affine and the world runtime origin.
3. L3 ownership / suppression (PR #16 review item 2): NTW must not rebuild a building Xinyi already owns.
   Rule proposed: suppress by SOURCE IDENTITY (same WFS layer) = the Xinyi pinned source id set; tested here
   against today's citywide WFS: id match, geometry drift, new features in the Xinyi fetch bbox, and any
   footprint overlap between a non-Xinyi WFS feature and a Xinyi feature (double-render risk).
4. Accepted GLB integrity: sha256 of the local accepted tiles vs the accepted report (read-only).
Writes data/ntw/world/xinyi_compat.json and data/ntw/world/xinyi_l3_mask_epsg3826.geojson.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping, shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools/compiler"))
import frame  # noqa: E402
from world_spec import WorldSpec  # noqa: E402
from worldmodel import R_WGS84, lonlat_to_enu  # noqa: E402

O_LON, O_LAT = 121.5654, 25.0330
XINYI_TILES = [(ix, iy) for ix in range(-3, 2) for iy in range(-2, 3)]  # == accepted report tile keys
FETCH_BBOX_4326 = (121.5546, 25.0247, 121.5744, 25.0427)  # tools/citygen_v2/fetch_projected_sample.mjs BBOX
XINYI_SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"   # pinned, sha c7ca8da1...
WFS = REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson"
TO_TM2 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)


def enu_to_lonlat(x, y):
    """Exact inverse of worldmodel.lonlat_to_enu."""
    return O_LON + math.degrees(x / (R_WGS84 * math.cos(math.radians(O_LAT)))), O_LAT + math.degrees(y / R_WGS84)


def enu_ring_to_tm2(x0, y0, x1, y1, step=50.0):
    pts = []
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        for i in range(n):
            t = i / n
            pts.append(TO_TM2.transform(*enu_to_lonlat(ax + t * (bx - ax), ay + t * (by - ay))))
    return Polygon(pts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=Path, default=REPO / "worlds/north_taiwan_224.json")
    ap.add_argument("--accepted-run", type=Path,
                    default=Path(r"D:\Users\EDDY\Documents\GitHub\air-combat-world\unreal\Saved\XinyiV2Full\run-01"),
                    help="local accepted Xinyi run (read-only) used only to verify GLB hashes")
    a = ap.parse_args()
    spec = WorldSpec.load(a.world)
    out = {"world": spec.name}

    # 1. sector outline
    xs = [ix * 500.0 for ix, _ in XINYI_TILES]
    ys = [iy * 500.0 for _, iy in XINYI_TILES]
    sector = enu_ring_to_tm2(min(xs), min(ys), max(xs) + 500, max(ys) + 500)
    fb = FETCH_BBOX_4326
    fetch_poly = Polygon([TO_TM2.transform(x, y) for x, y in ((fb[0], fb[1]), (fb[2], fb[1]), (fb[2], fb[3]), (fb[0], fb[3]))])
    ox_tm2, oy_tm2 = TO_TM2.transform(O_LON, O_LAT)
    out["sector"] = {
        "enu_extent_m": [min(xs), min(ys), max(xs) + 500, max(ys) + 500],
        "outline_area_km2": round(sector.area / 1e6, 4), "nominal_enu_area_km2": 6.25,
        "outline_bounds_epsg3826": [round(v, 2) for v in sector.bounds],
        "enu_origin_epsg3826": [round(ox_tm2, 3), round(oy_tm2, 3)],
        "fetch_bbox_area_km2": round(fetch_poly.area / 1e6, 4),
    }
    # 2. placement in the world
    x0, y0, x1, y1 = spec.bounds_tm2
    sb = sector.bounds
    cells = sorted({spec.cell_id(*spec.cell_index_abs(x, y)) for x, y in shapely.get_coordinates(sector)})
    l2 = set()
    for gx in range(int(math.floor(sb[0] / 500)), int(math.floor(sb[2] / 500)) + 1):
        for gy in range(int(math.floor(sb[1] / 500)), int(math.floor(sb[3] / 500)) + 1):
            if box(gx * 500, gy * 500, gx * 500 + 500, gy * 500 + 500).intersects(sector):
                l2.add(frame.cell_key(gx - frame.NTW_ORIGIN_TM2[0] / 500, gy - frame.NTW_ORIGIN_TM2[1] / 500))
    study = json.loads((REPO / "data/ntw/coordinate_study.json").read_text(encoding="utf-8"))["xinyi_enu_to_ntw_affine"]
    M = np.array(study["linear_part"])
    T = np.array(study["translation_m"]) + np.array(frame.NTW_ORIGIN_TM2)  # ENU -> absolute TM2
    rox, roy = spec.runtime_origin_tm2
    # Xinyi-level UE (cm): X = 100 e, Y = -100 n  ->  world UE (cm): X = 100 (E - rox), Y = -100 (N - roy)
    F = np.diag([1.0, -1.0])
    A_ue = F @ M @ F
    t_ue = np.array([100 * (T[0] - rox), -100 * (T[1] - roy)])
    out["placement"] = {
        "inside_world": bool(shapely.covers(box(x0, y0, x1, y1), sector)),
        "distance_to_world_edges_km": {"west": round((sb[0] - x0) / 1000, 2), "east": round((x1 - sb[2]) / 1000, 2),
                                       "south": round((sb[1] - y0) / 1000, 2), "north": round((y1 - sb[3]) / 1000, 2)},
        "world_cells_8km": cells, "ntw_l2_tiles_touched": len(l2),
        "note_alignment": "Xinyi ENU tiles are rotated 0.239 deg and scaled (1.00054 E, 0.99503 N) vs the NTW/TM2 grid, so "
                          "they can never coincide with NTW L2 tiles; ownership must therefore be by source identity, not by tile.",
        "xinyi_ue_to_world_ue_affine_cm": {
            "linear": [[round(float(v), 9) for v in r] for r in A_ue], "translation_cm": [round(float(v), 2) for v in t_ue],
            "determinant": round(float(np.linalg.det(A_ue)), 9),
            "meaning": "world_UE_xy = linear @ xinyi_level_UE_xy + translation; Z unchanged (both TWVD2001 m * 100)",
            "enu_origin_in_world_ue_cm": [round(float(v), 2) for v in t_ue]},
        "max_abs_world_ue_coordinate_of_sector_km": round(max(abs(sb[0] - rox), abs(sb[2] - rox), abs(sb[1] - roy), abs(sb[3] - roy)) / 1000, 2),
    }
    # 3. identity-based suppression test
    src = json.loads(XINYI_SOURCE.read_text(encoding="utf-8"))
    src_sha = hashlib.sha256(XINYI_SOURCE.read_bytes()).hexdigest()
    xin = {str(f["id"]): shape(f["geometry"]) for f in src["features"]}
    cur, cur_inside_fetch = {}, set()
    shapely.prepare(fetch_poly)
    for line in WFS.open(encoding="utf-8"):
        r = json.loads(line)
        g = shape(r["geometry"])
        cur[r["id"]] = g
        if fetch_poly.intersects(g):
            cur_inside_fetch.add(r["id"])
    matched = [i for i in xin if i in cur]
    same_geom = sum(1 for i in matched if shapely.equals_exact(xin[i], cur[i], tolerance=1e-6))
    new_in_bbox = sorted(cur_inside_fetch - set(xin))
    gone = sorted(set(xin) - set(cur))
    # double-render risk: non-Xinyi current WFS features whose footprint overlaps a Xinyi footprint
    xin_geoms = shapely.make_valid(np.array(list(xin.values()), dtype=object))
    tree = shapely.STRtree(xin_geoms)
    others = [i for i in cur if i not in xin and cur[i].intersects(sector.buffer(200))]
    og = shapely.make_valid(np.array([cur[i] for i in others], dtype=object))
    qi, ti = tree.query(og, predicate="intersects")
    inter = shapely.area(shapely.intersection(og[qi], xin_geoms[ti])) if len(qi) else np.array([])
    ovl = inter > 0.01
    out["l3_suppression"] = {
        "rule": "NTW skips any WFS feature whose id is in the Xinyi pinned source id set; Xinyi hero suppression stays Xinyi-owned",
        "xinyi_source_sha256": src_sha, "xinyi_source_features": len(xin),
        "ids_found_in_current_wfs": len(matched), "ids_with_identical_geometry": same_geom,
        "ids_missing_from_current_wfs": len(gone), "missing_examples": gone[:10],
        "current_features_in_fetch_bbox_not_in_xinyi": len(new_in_bbox), "new_examples": new_in_bbox[:10],
        "non_xinyi_features_near_sector": len(others),
        "non_xinyi_features_overlapping_a_xinyi_footprint_gt_0p01m2": int(len(set(qi[ovl]))) if len(qi) else 0,
        "max_overlap_area_m2": round(float(inter.max()), 3) if len(inter) else 0.0,
        "current_wfs_fetch": json.loads((REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson.manifest.json").read_text())["fetched_at"],
    }
    # 4. accepted GLB integrity (read-only)
    rep = a.accepted_run / "full_xinyi.report.json"
    if rep.exists():
        r = json.loads(rep.read_text(encoding="utf-8"))
        ok = 0
        for t in r["tiles"]:
            f = a.accepted_run / "tiles" / f"xinyi_v2_{t['tile']}.glb"
            ok += int(f.exists() and hashlib.sha256(f.read_bytes()).hexdigest() == t["sha256"])
        out["accepted_glb_integrity"] = {"run": str(a.accepted_run), "tiles": len(r["tiles"]), "sha256_match": ok,
                                         "manifest_sha256": r["tile_summary"]["manifest_sha256"],
                                         "report_tile_keys_equal_constant": sorted(t["tile"] for t in r["tiles"]) ==
                                         sorted(frame.cell_key(ix, iy) for ix, iy in XINYI_TILES)}
    else:
        out["accepted_glb_integrity"] = {"status": "accepted run not present on this machine; not checked"}
    od = REPO / "data/ntw/world"
    (od / "xinyi_compat.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3826"}},
          "features": [{"type": "Feature", "properties": {"name": "xinyi_l3_sector_outline", "source": "accepted ENU tiles, exact inverse"},
                        "geometry": mapping(shapely.set_precision(sector, 0.01))},
                       {"type": "Feature", "properties": {"name": "xinyi_wfs_fetch_bbox", "source": "fetch_projected_sample.mjs"},
                        "geometry": mapping(shapely.set_precision(fetch_poly, 0.01))}]}
    (od / "xinyi_l3_mask_epsg3826.geojson").write_text(json.dumps(gj), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
