"""Battlefield (mission) bounds inside a WorldSpec: which ~100 km box covers the North Taiwan core, and how much sea is left?

Config-driven (worlds/battlefields/*.json) so other theatres reuse it. For each mission size on the 8 km grid
(and a free-placement reference size at 1 km steps) the planner evaluates every placement inside the world:
  HARD   required admin regions fully inside (main-island parts, margin), required points inside (per-point margin),
         derived required geometry inside (Taipei basin floor, Tamsui estuary, north coast, northern tip)
  SCORE  min(west core sea depth, north core sea depth)  (depth = coast -> mission edge along 1 km scan lines)
  INFO   east depth, land/sea, what is left outside (only visible as far field), production zone (mission + halo cells)
Writes data/ntw/battlefield/<name>_study.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import duckdb
import numpy as np
import shapely
from scipy import ndimage
from shapely import box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import world_cells as wc  # noqa: E402
from world_planner import load_geography, row_extents, to_tm2  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

R = "s3://overturemaps-us-west-2/release/2026-09-23.1"


def derived_geometry(world, main_island, feats):
    """Required geometry derived from real data (each rule is recorded in the output)."""
    out = {}
    # Taipei basin floor: DTM (accepted mirror) < 20 m, connected to Taipei Main Station, inside a fixed window
    win = (288000.0, 2755000.0, 318000.0, 2785000.0)
    mos, meta, _ = wc.dtm_mosaic(world)
    res = 100.0
    xs = np.arange(win[0] + res / 2, win[2], res)
    ys = np.arange(win[1] + res / 2, win[3], res)
    GX, GY = np.meshgrid(xs, ys)
    lon, lat = wc.TO_LL.transform(GX.ravel(), GY.ravel())
    z = wc.sample_dtm(mos, meta, np.asarray(lon), np.asarray(lat)).reshape(GX.shape)
    land = shapely.contains_xy(main_island, GX.ravel(), GY.ravel()).reshape(GX.shape)
    low = land & (z < 20.0)
    lab, _ = ndimage.label(low)
    tms = wc.TO_TM2.transform(121.5170, 25.0478)  # Taipei Main Station (pilot A centre)
    k = lab[int((tms[1] - win[1]) // res), int((tms[0] - win[0]) // res)]
    basin = lab == k
    pts = shapely.points(GX[basin], GY[basin])
    out["taipei_basin"] = shapely.convex_hull(shapely.multipoints(shapely.get_coordinates(pts)))
    out["taipei_basin_area_km2"] = float(basin.sum()) * res * res / 1e6
    # Tamsui estuary
    cache = REPO / "data/generated/ntw/world/tamsui_river.wkb"
    if not cache.exists():
        c = duckdb.connect()
        c.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
        w = c.execute(f"""select ST_AsWKB(geometry) from read_parquet('{R}/theme=base/type=water/*', hive_partitioning=1)
                          where bbox.xmin >= 121.30 and bbox.xmax <= 121.70 and bbox.ymin >= 24.90 and bbox.ymax <= 25.25
                            and id='ffb9db5c-e14c-3f3f-868f-2f9f695bdc6b'""").fetchone()
        cache.write_bytes(bytes(w[0]))
    river = to_tm2(shapely.from_wkb(cache.read_bytes()))
    est = shapely.intersection(river, main_island.boundary.buffer(1000.0))
    out["tamsui_estuary"] = est if not est.is_empty else river
    # northern tip and north coast
    co = shapely.get_coordinates(main_island.exterior)
    tip = co[np.argmax(co[:, 1])]
    out["north_tip"] = shapely.Point(*tip)
    kee = next(f for f in feats if f["name"] == "基隆港")
    ex0 = out["tamsui_estuary"].bounds[0]
    coast = shapely.intersection(main_island.exterior, box(ex0, 2_784_000, kee["x"], 3_000_000))
    out["north_coast"] = coast
    return out


def evaluate(bx, geo, req, derived, scan, cfg, core_union):
    main_island, islands, regions, feats = geo
    x0, y0, x1, y1 = bx
    fail = []
    rm = cfg["required"]["region_margin_km"] * 1000
    inner = box(x0 + rm, y0 + rm, x1 - rm, y1 - rm)
    for code, g in req.items():
        if not shapely.covers(inner, g):
            fail.append(f"region:{code}")
    for p in cfg["required"]["points"]:
        f = next(f for f in feats if f["name"] == p["name"])
        m = p["margin_km"] * 1000
        if not (x0 + m <= f["x"] <= x1 - m and y0 + m <= f["y"] <= y1 - m):
            fail.append(f"point:{p['name']}")
    for k, spec in cfg["required"]["derived"].items():
        m = spec["margin_km"] * 1000
        if not shapely.covers(box(x0 + m, y0 + m, x1 - m, y1 - m), derived[k]):
            fail.append(f"derived:{k}")
    ys, wlo, whi, xs, nhi, core_w, core_e, core_n = scan

    def depth(vals, edge, coords, sel, sign, lo, hi):
        m = ~np.isnan(vals) & sel & (coords >= lo) & (coords <= hi)
        if not m.any():
            return None
        return np.maximum(sign * (vals[m] - edge), 0.0)
    w = depth(wlo, x0, ys, core_w, 1, y0, y1)
    n = depth(nhi, y1, xs, core_n, -1, x0, x1)
    e = depth(whi, x1, ys, core_e, -1, y0, y1)
    km = lambda a, f: None if a is None else round(float(f(a)) / 1000, 1)  # noqa: E731
    mb = box(*bx)
    land = shapely.intersection(main_island, mb).area if not fail else 0.0
    area = (x1 - x0) * (y1 - y0)
    obj = min(v for v in (km(w, np.min), km(n, np.min)) if v is not None) if w is not None and n is not None else -1
    return {"bounds_epsg3826": [x0, y0, x1, y1], "feasible": not fail, "violations": fail,
            "depth_km": {"west_core_min": km(w, np.min), "west_core_median": km(w, np.median),
                         "north_core_min": km(n, np.min), "north_core_median": km(n, np.median),
                         "east_core_min": km(e, np.min), "east_core_median": km(e, np.median)},
            "objective_km": obj, "land_pct": round(100 * land / area, 1), "sea_pct": round(100 - 100 * land / area, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=REPO / "worlds/battlefields/north_core_v1.json")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    world = WorldSpec.load(REPO / cfg["world"])
    main_island, islands, req_all, foreign, tw_regions, feats = load_geography()
    regions = {code: shapely.intersection(g, main_island.buffer(1.0)) for code, (name, g) in tw_regions.items()}
    req = {code: regions[code] for code in cfg["required"]["regions_full"]}
    derived = derived_geometry(world, main_island, feats)
    core_codes = ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE"]
    core_union = unary_union([regions[c] for c in core_codes]).buffer(300.0)
    shapely.prepare(core_union)
    ys = np.arange(2_600_000, 2_900_001, 1000.0)
    xs = np.arange(150_000, 450_001, 1000.0)
    wlo, whi = row_extents(main_island, ys, True)
    _, nhi = row_extents(main_island, xs, False)

    def inc(xv, yv):
        ok = ~np.isnan(xv) & ~np.isnan(yv)
        o = np.zeros(len(xv), bool)
        o[ok] = shapely.contains_xy(core_union, xv[ok], yv[ok])
        return o
    scan = (ys, wlo, whi, xs, nhi, inc(wlo, ys), inc(whi, ys), inc(xs, nhi))
    geo = (main_island, islands, regions, feats)
    wx0, wy0, wx1, wy1 = world.bounds_tm2
    results = {}
    sizes = [(s, 8000.0) for s in cfg["mission_sizes_km"]] + [(cfg["reference_free_size_km"], 1000.0)]
    for size_km, step in sizes:
        s = size_km * 1000.0
        cands = []
        for x0 in np.arange(wx0, wx1 - s + 1, step):
            for y0 in np.arange(wy0, wy1 - s + 1, step):
                cands.append(evaluate((x0, y0, x0 + s, y0 + s), geo, req, derived, scan, cfg, core_union))
        feas = sorted([c for c in cands if c["feasible"]], key=lambda c: (-c["objective_km"], -(c["depth_km"]["north_core_min"] or 0), c["bounds_epsg3826"]))
        for c in feas[:5]:
            mb = box(*c["bounds_epsg3826"])
            c["regions_partly_inside_pct"] = {code: round(100 * shapely.intersection(g, mb).area / g.area, 1) for code, g in regions.items()
                                              if 0 < shapely.intersection(g, mb).area < 0.999 * g.area}
            c["regions_fully_inside"] = sorted(code for code, g in regions.items() if g.area > 0 and shapely.covers(mb, g))
        hist = {}
        for c in cands:
            for v in c["violations"]:
                hist[v] = hist.get(v, 0) + 1
        results[str(size_km)] = {"grid_step_m": step, "candidates": len(cands), "feasible": len(feas), "top": feas[:5],
                                 "infeasible_reasons": dict(sorted(hist.items(), key=lambda kv: -kv[1])[:12])}
        best = feas[0] if feas else None
        print(size_km, "feasible", len(feas), "of", len(cands), best and (best["bounds_epsg3826"], best["objective_km"], best["depth_km"], best["land_pct"]))
    rotated = rotated_study(cfg, world, main_island, islands, regions, feats, derived, req, core_codes)
    out = {"config": cfg["name"], "world": world.name, "results": results, "rotated_mission_study": rotated,
           "derived_geometry": {"taipei_basin_area_km2": round(derived["taipei_basin_area_km2"], 1),
                                "taipei_basin_bounds_epsg3826": [round(v) for v in derived["taipei_basin"].bounds],
                                "tamsui_estuary_bounds_epsg3826": [round(v) for v in derived["tamsui_estuary"].bounds],
                                "north_tip_epsg3826": [round(v, 1) for v in derived["north_tip"].coords[0]],
                                "north_coast_bounds_epsg3826": [round(v) for v in derived["north_coast"].bounds]},
           "core_landscape_span": span_report(regions, derived, feats, cfg)}
    od = REPO / "data/ntw/battlefield"
    od.mkdir(parents=True, exist_ok=True)
    (od / f"{cfg['name']}_study.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3826"}},
          "features": [{"type": "Feature", "properties": {"name": k}, "geometry": shapely.geometry.mapping(shapely.set_precision(derived[k], 1.0))}
                       for k in ("taipei_basin", "tamsui_estuary", "north_coast", "north_tip")]}
    (od / f"{cfg['name']}_derived_epsg3826.geojson").write_text(json.dumps(gj), encoding="utf-8")
    print(json.dumps(out["core_landscape_span"], ensure_ascii=False, indent=1))


def rotated_study(cfg, world, main_island, islands, regions, feats, derived, req, core_codes):
    """Same evaluation in a frame rotated clockwise by `deg` about the world runtime origin (mission boundaries are gameplay
    data; production cells stay grid-aligned). Returns, per angle and size, the best feasible box as a polygon in EPSG:3826."""
    from shapely import affinity
    piv = world.runtime_origin_tm2
    out = {}
    for deg in cfg.get("rotated_angles_deg", [30, 40, 45, 50]):
        rot = lambda g: affinity.rotate(g, -deg, origin=piv)  # noqa: E731  (clockwise)
        mi, isl = rot(main_island), rot(islands)
        regs = {k: rot(g) for k, g in regions.items()}
        rq = {k: regs[k] for k in req}
        dv = {k: rot(v) if hasattr(v, "geom_type") else v for k, v in derived.items()}
        fs = []
        for f in feats:
            if "x" in f:
                q = affinity.rotate(shapely.Point(f["x"], f["y"]), -deg, origin=piv)
                fs.append(dict(f, x=q.x, y=q.y))
        cu = unary_union([regs[c] for c in core_codes]).buffer(300.0)
        shapely.prepare(cu)
        bx_ = mi.bounds
        ys = np.arange(math.floor(bx_[1] / 1000) * 1000 - 200000, bx_[3] + 200000, 1000.0)
        xs = np.arange(math.floor(bx_[0] / 1000) * 1000 - 200000, bx_[2] + 200000, 1000.0)
        wlo, whi = row_extents(mi, ys, True)
        _, nhi = row_extents(mi, xs, False)

        def inc(xv, yv):
            ok = ~np.isnan(xv) & ~np.isnan(yv)
            o = np.zeros(len(xv), bool)
            o[ok] = shapely.contains_xy(cu, xv[ok], yv[ok])
            return o
        scan = (ys, wlo, whi, xs, nhi, inc(wlo, ys), inc(whi, ys), inc(xs, nhi))
        rb = unary_union(list(rq.values()) + [dv[k] for k in ("taipei_basin", "tamsui_estuary", "north_coast", "north_tip")]).bounds
        for size_km in cfg.get("rotated_sizes_km", [96, 104]):
            sm = size_km * 1000.0
            best = None
            for x0 in np.arange(rb[2] - sm, rb[0] + 1, 2000.0):
                for y0 in np.arange(rb[3] - sm, rb[1] + 1, 2000.0):
                    r = evaluate((x0, y0, x0 + sm, y0 + sm), (mi, isl, regs, fs), rq, dv, scan, cfg, cu)
                    if r["feasible"] and (best is None or (r["objective_km"], r["depth_km"]["north_core_min"] or 0) > (best["objective_km"], best["depth_km"]["north_core_min"] or 0)):
                        best = r
            if best:
                poly = affinity.rotate(box(*best["bounds_epsg3826"]), deg, origin=piv)
                best = dict(best, rotation_deg_clockwise=deg, polygon_epsg3826=[[round(x, 1), round(y, 1)] for x, y in poly.exterior.coords],
                            note="depth_km sides refer to the ROTATED frame (west = toward the north-west coast for ~45 deg)")
                best.pop("bounds_epsg3826")
            out[f"{deg}deg_{size_km}km"] = best
            print("rotated", deg, size_km, best and (best["objective_km"], best["depth_km"], best["land_pct"]))
    return out


def span_report(regions, derived, feats, cfg):
    """Real extent of the North-Taipei-Keelung-Taoyuan-Hsinchu landscape (what a mission must contain)."""
    geoms = [regions[c] for c in cfg["required"]["regions_full"]] + [derived[k] for k in ("taipei_basin", "tamsui_estuary", "north_coast", "north_tip")]
    pts = [shapely.Point(f["x"], f["y"]) for f in feats if f["name"] in [p["name"] for p in cfg["required"]["points"]]]
    u = unary_union(geoms + pts)
    b = u.bounds
    six = unary_union([regions[c] for c in ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE"]]).bounds
    return {"required_set_bounds_epsg3826": [round(v) for v in b],
            "required_set_extent_km": [round((b[2] - b[0]) / 1000, 1), round((b[3] - b[1]) / 1000, 1)],
            "six_core_regions_extent_km": [round((six[2] - six[0]) / 1000, 1), round((six[3] - six[1]) / 1000, 1)],
            "note": "required set = Taipei/Keelung/Hsinchu City + airports/ports/Yangmingshan + basin/estuary/north coast; "
                    "full admin areas of New Taipei, Taoyuan and Hsinchu County are NOT required (their mountain hinterland is far-field)"}


if __name__ == "__main__":
    main()
