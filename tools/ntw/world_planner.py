"""World placement study: where should an N x N km, 8 km-aligned world sit on real north-Taiwan geography?

For every candidate SW corner on the 8 km grid (EPSG:3826) the planner evaluates
  HARD   all required admin regions (main-island parts) + required features inside with a margin
         no foreign (CN / JP) land inside the world
  SCORE  sea/air depth: distance from the Taiwan main-island coast to the west / north / east world edge,
         measured per 1 km row/column; the objective uses the CORE coast span (rows/columns of the six core
         regions + Yilan), the full-span minimum is reported too
  INFO   land / sea / foreign ratios, coastline length, optional features, high-mountain coverage,
         share of the world west of the commonly cited (approximate) Strait median line.
Size is a parameter (--size-km), so 192 / 224 / 256 / 288 km worlds use the same code.

usage: world_planner.py --size-km 224 [--margin-km 8] [--out data/ntw/world/placement_224.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import duckdb
import numpy as np
import shapely
from pyproj import Transformer
from shapely import box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from world_spec import WorldSpec  # noqa: E402

CELL = 8000.0
REQUIRED_REGIONS = ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE", "TW-ILA"]
TO_TM2 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
# Commonly cited endpoints of the Taiwan Strait median ("Davis") line. APPROXIMATE, not an official boundary;
# used only to inform game/political sensitivity of the western world edge.
MEDIAN_LINE_LONLAT = [(122.0, 27.0), (118.0, 23.0)]


def to_tm2(g):
    co = shapely.get_coordinates(g)
    x, y = TO_TM2.transform(co[:, 0], co[:, 1])
    return shapely.set_coordinates(g, np.column_stack([x, y]))


def load_geography():
    rows = duckdb.connect().execute(
        f"select country, region, name, wkb from read_parquet('{(REPO / 'data/generated/ntw/world/land.parquet').as_posix()}') order by region").fetchall()
    tw_regions, foreign = {}, []
    for country, region, name, wkb in rows:
        g = shapely.make_valid(to_tm2(shapely.from_wkb(bytes(wkb))))
        if country == "TW":
            tw_regions[region] = (name, g)
        else:
            foreign.append((country, region, name, g))
    tw = unary_union([g for _, g in tw_regions.values()])
    parts = sorted(shapely.get_parts(tw), key=lambda p: -p.area)
    main_island = parts[0]
    islands = shapely.union_all(parts[1:]) if len(parts) > 1 else shapely.Polygon()
    req = {}
    for code in REQUIRED_REGIONS:
        name, g = tw_regions[code]
        req[code] = (name, shapely.intersection(g, main_island.buffer(1.0)))
    feats = json.loads((REPO / "data/ntw/world/features.json").read_text(encoding="utf-8"))["features"]
    for f in feats:
        if "lon" in f:
            f["x"], f["y"] = TO_TM2.transform(f["lon"], f["lat"])
    return main_island, islands, req, foreign, tw_regions, feats


def row_extents(poly, y_values, horizontal=True):
    """Global min/max of polygon along each scan line (NaN where no land)."""
    xmin, ymin, xmax, ymax = poly.bounds
    lo, hi = np.full(len(y_values), np.nan), np.full(len(y_values), np.nan)
    for i, v in enumerate(y_values):
        line = shapely.LineString([(xmin - 1, v), (xmax + 1, v)]) if horizontal else shapely.LineString([(v, ymin - 1), (v, ymax + 1)])
        seg = shapely.intersection(poly, line)
        if seg.is_empty:
            continue
        co = shapely.get_coordinates(seg)
        k = 0 if horizontal else 1
        lo[i], hi[i] = co[:, k].min(), co[:, k].max()
    return lo, hi


def mountain_tiles():
    """z13 DTM tiles with max >= 2500 m north of 24.0 N (coarse high-mountain proxy) as TM2 centre points."""
    pts = []
    n = 2.0 ** 13
    for r in csv.DictReader((REPO / "data/generated/ntw/dtm/tile-index.csv").open(encoding="utf-8")):
        if not r["max_m"] or float(r["max_m"]) < 2500:
            continue
        x, y = int(r["x"]) + 0.5, int(r["y"]) + 0.5
        lon = x / n * 360 - 180
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        if lat >= 24.0:
            pts.append(TO_TM2.transform(lon, lat))
    return np.array(pts)


def evaluate(spec, geo, scan, margin_m, mtiles, median_line):
    main_island, islands, req, foreign, _, feats = geo
    x0, y0, x1, y1 = spec.bounds_tm2
    wb = box(x0, y0, x1, y1)
    inner = box(x0 + margin_m, y0 + margin_m, x1 - margin_m, y1 - margin_m)
    fail = []
    for code, (name, g) in req.items():
        if not shapely.covers(inner, g):
            fail.append(f"region:{code}")
    for f in feats:
        if f.get("tier") == "required" and "x" in f and not spec.contains(f["x"], f["y"], margin_m):
            fail.append(f"feature:{f['name']}")
    foreign_in = sum(shapely.intersection(g, wb).area for *_, g in foreign)
    if foreign_in > 0:
        fail.append(f"foreign_land_km2:{foreign_in / 1e6:.2f}")
    ys, (wlo, whi), xs, (nlo, nhi), core_rows, core_cols = scan

    def depths(lo_or_hi, edge, coords, sel, sign, lim_lo, lim_hi):
        m = ~np.isnan(lo_or_hi) & (coords >= lim_lo) & (coords <= lim_hi) & sel
        if not m.any():
            return None
        d = sign * (lo_or_hi[m] - edge)
        return np.maximum(d, 0.0)
    w_all = depths(wlo, x0, ys, np.ones_like(ys, bool), 1, y0, y1)
    e_all = depths(whi, x1, ys, np.ones_like(ys, bool), -1, y0, y1)
    n_all = depths(nhi, y1, xs, np.ones_like(xs, bool), -1, x0, x1)
    w_core = depths(wlo, x0, ys, core_rows[0], 1, y0, y1)
    e_core = depths(whi, x1, ys, core_rows[1], -1, y0, y1)
    n_core = depths(nhi, y1, xs, core_cols, -1, x0, x1)

    def km(a, fn):
        return None if a is None else round(float(fn(a)) / 1000, 1)
    land_tw = shapely.intersection(shapely.union(main_island, islands), wb).area
    coast = shapely.intersection(shapely.union(main_island, islands).boundary, wb).length
    area = spec.size_m[0] * spec.size_m[1]
    opt = [f["name"] for f in feats if f.get("tier") == "optional" and "x" in f and spec.contains(f["x"], f["y"])]
    mt_in = int(sum(spec.contains(p[0], p[1]) for p in mtiles))
    west_of_median = shapely.intersection(wb, median_line).area / area
    nearest_foreign = min(shapely.distance(wb, g) for *_, g in foreign)
    core = [v for v in (km(w_core, np.min), km(n_core, np.min), km(e_core, np.min)) if v is not None]
    return {
        "sw_corner_epsg3826": [x0, y0], "bounds_epsg3826": [x0, y0, x1, y1], "feasible": not fail, "violations": fail,
        "depth_km": {
            "west_core_min": km(w_core, np.min), "west_core_median": km(w_core, np.median), "west_all_min": km(w_all, np.min),
            "north_core_min": km(n_core, np.min), "north_core_median": km(n_core, np.median),
            "east_core_min": km(e_core, np.min), "east_core_median": km(e_core, np.median), "east_all_min": km(e_all, np.min)},
        "objective_min_core_depth_km": min(core) if len(core) == 3 else -1,
        "land_tw_pct": round(100 * land_tw / area, 2), "foreign_land_km2": round(foreign_in / 1e6, 2),
        "sea_pct": round(100 * (area - land_tw - foreign_in) / area, 2),
        "coastline_km_in_world": round(coast / 1000, 1),
        "optional_features_inside": opt, "high_mountain_tiles_inside": mt_in, "high_mountain_tiles_total": int(len(mtiles)),
        "share_west_of_approx_median_line_pct": round(100 * west_of_median, 1),
        "nearest_foreign_land_km": round(nearest_foreign / 1000, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size-km", type=float, default=224)
    ap.add_argument("--margin-km", type=float, default=8)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    size = a.size_km * 1000
    geo = load_geography()
    main_island, islands, req, foreign, tw_regions, feats = geo
    core_union = unary_union([g for _, g in req.values()])
    cb = core_union.bounds
    # scan lines every 1 km over the whole search area
    ys = np.arange(2_500_000, 3_000_001, 1000.0)
    xs = np.arange(50_000, 520_001, 1000.0)
    wlo, whi = row_extents(main_island, ys, True)
    nlo, nhi = row_extents(main_island, xs, False)
    # a scan line is "core" for a side only if its outermost main-island coast point lies in a core region
    core_buf = core_union.buffer(300.0)
    shapely.prepare(core_buf)
    def in_core(xv, yv):
        ok = ~np.isnan(xv) & ~np.isnan(yv)
        out = np.zeros(len(xv), bool)
        out[ok] = shapely.contains_xy(core_buf, xv[ok], yv[ok])
        return out
    core_rows_w = in_core(wlo, ys)
    core_rows_e = in_core(whi, ys)
    core_cols_n = in_core(xs, nhi)
    scan = (ys, (wlo, whi), xs, (nlo, nhi), (core_rows_w, core_rows_e), core_cols_n)
    ml = shapely.LineString([TO_TM2.transform(*p) for p in MEDIAN_LINE_LONLAT])
    # polygon of everything west/north-west of the line (large half-plane clipped to the search area)
    (ax, ay), (bx, by) = ml.coords
    median_west = shapely.Polygon([(ax, ay), (bx, by), (bx - 600_000, by), (ax - 600_000, ay)])
    mtiles = mountain_tiles()
    margin = a.margin_km * 1000
    cands = []
    for x0 in np.arange(64_000, 288_001, CELL):
        for y0 in np.arange(2_544_000, 2_736_001, CELL):
            spec = WorldSpec(name="cand", sw_tm2=(float(x0), float(y0)), size_m=(size, size))
            cands.append(evaluate(spec, geo, scan, margin, mtiles, median_west))
    feas = [c for c in cands if c["feasible"]]
    feas.sort(key=lambda c: (-c["objective_min_core_depth_km"], -len(c["optional_features_inside"]),
                             -(c["depth_km"]["north_core_min"] or 0), c["sw_corner_epsg3826"][0], c["sw_corner_epsg3826"][1]))
    out = {
        "size_km": a.size_km, "margin_km": a.margin_km, "grid_km": CELL / 1000, "candidates_evaluated": len(cands),
        "feasible": len(feas), "core_region_bounds_epsg3826": [round(v, 1) for v in cb],
        "required_regions": {k: v[0] for k, v in req.items()},
        "required_features": [f["name"] for f in feats if f.get("tier") == "required"],
        "ranking": "max min(core W,N,E sea depth) -> max optional features -> max north depth -> west-most, south-most",
        "core_scanlines": {"west_rows": int(core_rows_w.sum()), "east_rows": int(core_rows_e.sum()), "north_cols": int(core_cols_n.sum()),
                           "definition": "1 km scan line counts as core when its outermost main-island coast point lies within 300 m of a required region"},
        "top": feas[:15],
        "infeasible_reasons_histogram": _hist(cands),
        "median_line_note": "Approximate commonly cited endpoints (27N,122E)-(23N,118E); NOT an official boundary.",
    }
    p = a.out or REPO / f"data/ntw/world/placement_{int(a.size_km)}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(p, "feasible", len(feas), "of", len(cands))
    for c in feas[:8]:
        print(c["sw_corner_epsg3826"], c["objective_min_core_depth_km"], c["depth_km"], c["land_tw_pct"], c["sea_pct"],
              c["optional_features_inside"], c["share_west_of_approx_median_line_pct"], c["nearest_foreign_land_km"])


def _hist(cands):
    h = {}
    for c in cands:
        for v in c["violations"]:
            k = v.split(":")[0] + ":" + v.split(":")[1] if not v.startswith("foreign") else "foreign_land"
            h[k] = h.get(k, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    main()
