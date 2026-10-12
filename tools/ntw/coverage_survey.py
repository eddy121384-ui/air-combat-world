"""Exact building coverage survey from the Overture extraction cache.

Reads data/generated/ntw/ovt_band*.parquet (see extract_overture_buildings.py) and
data/ntw/theater_regions.json. Writes:
  data/ntw/coverage_manifest.json  (compact, committed)
  data/ntw/coverage_map.svg        (static map, committed)
Everything reported here is an EXACT count over the pinned Overture release, not a sample.
Region membership = building centroid inside the 150 m-simplified region boundary
(border buildings may flip by < ~150 m of boundary error; quantified in Phase 2A world summary QA).

Two height views are reported (PR #16 review item 4):
  presence-based  explicit_height / floors_only / fallback_needed  (non-null values; Phase 1 numbers)
  validated       valid_height / valid_floors_only / present_but_invalid / no_usable_height, using the SAME bounds as
                  tools/ntw/heights.py (1.2-600 m; 1-150 floors with floors x 3.2 inside the height bounds)
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import duckdb
import numpy as np

import heights
from pyproj import Transformer
from shapely import contains_xy, prepare
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent))
from frame import LEVEL_CELL_M, NTW_ORIGIN_TM2, cell_index, lonlat_to_ntw  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/generated/ntw"
OUT_JSON = REPO / "data/ntw/coverage_manifest.json"
OUT_SVG = REPO / "data/ntw/coverage_map.svg"
RELEASE = "2026-09-23.1"


def _col(df, name, fill):
    a = df[name]
    return np.ma.filled(a, fill) if np.ma.isMaskedArray(a) else np.asarray(a)


def load():
    con = duckdb.connect()
    df = con.execute(
        f"select * from read_parquet('{(CACHE / 'ovt_band*.parquet').as_posix()}') order by id"
    ).fetchnumpy()
    d = {
        "id": np.asarray(df["id"]),
        "cx": np.asarray(df["cx"], float),
        "cy": np.asarray(df["cy"], float),
        "height_ok": ~np.isnan(_col(df, "height", np.nan).astype(float)),
        "floors_ok": ~np.ma.getmaskarray(df["num_floors"]) if np.ma.isMaskedArray(df["num_floors"]) else np.ones(len(df["id"]), bool),
        "underground": _col(df, "is_underground", False).astype(bool),
        "has_parts": _col(df, "has_parts", False).astype(bool),
        "src": np.array([s or "NULL" for s in _col(df, "src", None).astype(object)]),
        "cls": np.array([s or "NULL" for s in _col(df, "class", None).astype(object)]),
        "area": np.asarray(df["area_m2"], float),
        "npts": np.asarray(df["npts"], np.int64),
    }
    h = np.ma.filled(np.ma.asarray(df["height"]).astype(float), np.nan)
    f = np.ma.filled(np.ma.asarray(df["num_floors"]).astype(float), np.nan)
    d["h_valid"] = ~np.isnan(h) & (h >= heights.MIN_M) & (h <= heights.MAX_M)
    d["f_valid"] = (~np.isnan(f) & (f >= 1) & (f <= 150)
                    & (f * heights.FLOOR_M >= heights.MIN_M) & (f * heights.FLOOR_M <= heights.MAX_M))
    return d


def stats(d, mask, area_km2=None):
    k = int(mask.sum())
    if k == 0:
        return {"buildings": 0}
    h, f = d["height_ok"][mask], d["floors_ok"][mask]
    a, npt = d["area"][mask], d["npts"][mask]
    s = {
        "buildings": k,
        "underground_flagged": int(d["underground"][mask].sum()),
        "explicit_height": int(h.sum()),
        "floors_only": int((~h & f).sum()),
        "fallback_needed": int((~h & ~f).sum()),
        "explicit_height_pct": round(100 * float(h.mean()), 2),
        "height_or_floors_pct": round(100 * float((h | f).mean()), 2),
        "validated": {
            "valid_height": int(d["h_valid"][mask].sum()),
            "valid_floors_only": int((~d["h_valid"][mask] & d["f_valid"][mask]).sum()),
            "present_but_invalid": int(((h | f) & ~d["h_valid"][mask] & ~d["f_valid"][mask]).sum()),
            "no_usable_height": int((~d["h_valid"][mask] & ~d["f_valid"][mask]).sum()),
        },
        "has_parts": int(d["has_parts"][mask].sum()),
        "sources": {x: int((d["src"][mask] == x).sum()) for x in sorted(set(d["src"][mask]))},
        "median_footprint_m2": round(float(np.median(a)), 1),
        "p99_footprint_m2": round(float(np.percentile(a, 99)), 1),
        "footprint_area_km2": round(float(a.sum() / 1e6), 2),
        "mean_ring_vertices": round(float(npt.mean()), 2),
        "sum_ring_vertices": int(npt.sum()),
    }
    if area_km2:
        s["buildings_per_km2"] = round(k / area_km2, 1)
    return s


def main():
    theater = json.loads((REPO / "data/ntw/theater_regions.json").read_text(encoding="utf-8"))
    d = load()
    n = len(d["id"])
    region = np.full(n, -1, dtype=np.int8)
    for i, r in enumerate(theater["regions"]):
        g = shape(r["boundary_simplified_150m"])
        prepare(g)
        m = (region < 0) & contains_xy(g, d["cx"], d["cy"])
        region[m] = i
    X, Y = lonlat_to_ntw(d["cx"], d["cy"])

    out = {
        "overture_release": RELEASE,
        "kind": "EXACT counts over pinned Overture release (centroid-in-region); not sample-based",
        "total_rows_in_theater_bbox": int(n),
        "ntw_origin_epsg3826": NTW_ORIGIN_TM2,
        "regions": [],
    }
    for i, r in enumerate(theater["regions"]):
        s = stats(d, region == i, r["land_area_km2_mainland"])
        s.update(key=r["key"], name=r["name"], tier=r["tier"], land_area_km2=r["land_area_km2_mainland"])
        out["regions"].append(s)
    core = [i for i, r in enumerate(theater["regions"]) if r["tier"] == "core"]
    out["outside_all_regions"] = stats(d, region < 0)
    out["core_6"] = stats(d, np.isin(region, core))
    out["core_6_plus_yilan"] = stats(d, region >= 0)

    inreg = region >= 0
    grids = {}
    for lvl, size in LEVEL_CELL_M.items():
        ix, iy = cell_index(X[inreg], Y[inreg], size)
        _, cnt = np.unique(ix * 1_000_000 + iy, return_counts=True)
        grids[lvl] = {
            "cell_m": size, "nonempty_cells": int(len(cnt)),
            "buildings_per_cell": {f"p{p}": float(np.percentile(cnt, p)) for p in (50, 90, 99)} | {"max": int(cnt.max())},
        }
    out["grids_all_regions"] = grids
    ix2, iy2 = cell_index(X[inreg], Y[inreg], 2000.0)
    cells = defaultdict(lambda: [0, 0, 0])
    for a, b, h, f in zip(ix2.tolist(), iy2.tolist(), d["height_ok"][inreg].tolist(), d["floors_ok"][inreg].tolist()):
        c = cells[(a, b)]
        c[0] += 1
        c[1] += int(h)
        c[2] += int(not h and not f)
    out["cells_2km"] = {
        "note": "[ix,iy,buildings,explicit_height,fallback_needed]; cell SW corner = NTW_ORIGIN + (ix,iy)*2000 m (EPSG:3826)",
        "rows": [[k[0], k[1], *v] for k, v in sorted(cells.items())],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(OUT_JSON, OUT_JSON.stat().st_size, "bytes")
    for r in out["regions"]:
        print(r["name"], r["buildings"], f'{r["buildings_per_km2"]}/km2 h={r["explicit_height_pct"]}% h|f={r["height_or_floors_pct"]}%', r["sources"])
    print("outside", out["outside_all_regions"]["buildings"], "core6", out["core_6"]["buildings"], "all", out["core_6_plus_yilan"]["buildings"])
    print(json.dumps(grids))
    write_svg(theater, cells)


def write_svg(theater, cells):
    sz, px, gap = 2000.0, 6, 20
    xs = [k[0] for k in cells]
    ys = [k[1] for k in cells]
    x0, y0 = min(xs), min(ys)
    W, H = max(xs) + 1 - x0, max(ys) + 1 - y0
    t = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
    mx = max(v[0] for v in cells.values())

    def pt(lon, lat):
        e, n = t.transform(lon, lat)
        return ((e - NTW_ORIGIN_TM2[0]) / sz - x0) * px, (H - ((n - NTW_ORIGIN_TM2[1]) / sz - y0)) * px

    def panel(mode):
        s = []
        for (ix, iy), v in cells.items():
            if mode == "density":
                f = math.log1p(v[0]) / math.log1p(mx)
                col = f"rgb({int(255 - 215 * f)},{int(255 - 170 * f)},{int(240 - 200 * f)})"
            elif v[0] < 20:
                col = "#ddd"
            else:
                fr = v[2] / v[0]
                col = f"rgb({int(255 - 30 * (1 - fr))},{int(235 - 200 * fr)},{int(235 - 200 * fr)})"
            s.append(f'<rect x="{(ix - x0) * px}" y="{(H - (iy - y0) - 1) * px}" width="{px}" height="{px}" fill="{col}"/>')
        for r in theater["regions"]:
            g = r["boundary_simplified_150m"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for p in polys:
                d = "M" + "L".join("%.1f,%.1f" % pt(lo, la) for lo, la in p[0]) + "Z"
                s.append(f'<path d="{d}" fill="none" stroke="#222" stroke-width="0.8"/>')
        return "".join(s)

    width = W * px * 2 + gap
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{H * px + 30}" viewBox="0 0 {width} {H * px + 30}" font-family="sans-serif" font-size="11">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<g transform="translate(0,24)">{panel("density")}</g>',
        f'<g transform="translate({W * px + gap},24)">{panel("fallback")}</g>',
        f'<text x="4" y="14">Overture buildings / 2 km cell (log), release {RELEASE}</text>',
        f'<text x="{W * px + gap + 4}" y="14">Share needing 9.6 m fallback (no height, no floors); grey = fewer than 20 buildings</text></svg>',
    ]
    OUT_SVG.write_text("\n".join(svg), encoding="utf-8")
    print(OUT_SVG, OUT_SVG.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
