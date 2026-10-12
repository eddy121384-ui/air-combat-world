"""Terrain coverage of the theater from the MOI 2025 20 m DTM Terrarium z13 mirror tile index.

The mirror (yhzkiki/taiwan-dtm-2025-terrarium-z13) is the same transport already accepted for Xinyi.
tile-index.csv lists every tile with valid_fraction (0 = no DTM data, i.e. open sea / outside the DTM).
This reads only that index (355 KB); it does NOT download elevation tiles.
Writes data/ntw/dtm_coverage.json.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely import prepare, intersects
from shapely.geometry import box, shape

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / "data/generated/ntw/dtm/tile-index.csv"
Z = 13


def tile_bounds_lonlat(x, y, z=Z):
    n = 2.0 ** z
    lon0, lon1 = x / n * 360 - 180, (x + 1) / n * 360 - 180
    def lat(yy):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return lon0, lat(y + 1), lon1, lat(y)


def main():
    theater = json.loads((REPO / "data/ntw/theater_regions.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(INDEX.open(encoding="utf-8")))
    idx = {(int(r["x"]), int(r["y"])): r for r in rows}
    out = {"mirror": "yhzkiki/taiwan-dtm-2025-terrarium-z13", "zoom": Z, "tiles_in_index_total": len(rows),
           "tiles_with_any_valid_pixels": sum(1 for r in rows if float(r["valid_fraction"]) > 0), "regions": []}
    ground_m_per_px = 156543.03392 * math.cos(math.radians(25)) / 2 ** Z
    out["approx_pixel_m_at_25N"] = round(ground_m_per_px, 2)
    union_tiles = set()
    for r in theater["regions"]:
        g = shape(r["boundary_simplified_150m"])
        prepare(g)
        minx, miny, maxx, maxy = g.bounds
        n = 2.0 ** Z
        x0 = int((minx + 180) / 360 * n); x1 = int((maxx + 180) / 360 * n)
        def ty(lat):
            return int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        y0, y1 = ty(maxy), ty(miny)
        touched = missing = nodata = 0
        vf = []
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if not intersects(g, box(*tile_bounds_lonlat(x, y))):
                    continue
                touched += 1
                rec = idx.get((x, y))
                if rec is None:
                    missing += 1
                    continue
                v = float(rec["valid_fraction"])
                vf.append(v)
                if v == 0:
                    nodata += 1
                union_tiles.add((x, y))
        out["regions"].append({
            "key": r["key"], "tiles_intersecting_land_boundary": touched, "tiles_missing_from_index": missing,
            "tiles_all_nodata": nodata, "mean_valid_fraction": round(float(np.mean(vf)), 3) if vf else None,
            "png_tiles_to_download_for_land": touched - missing - nodata,
        })
    vfs = [float(idx[t]["valid_fraction"]) for t in union_tiles if t in idx]
    out["all_regions_unique_tiles"] = len(union_tiles)
    out["all_regions_mean_valid_fraction"] = round(float(np.mean(vfs)), 3)
    out["note"] = ("valid_fraction < 1 at the coast is expected (sea pixels are NODATA). Vertical datum: MOI DTM is "
                   "orthometric TWVD2001; Xinyi calibration offset (+0.342 m vs WFS surveyed ground) is NOT validated outside Taipei.")
    p = REPO / "data/ntw/dtm_coverage.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
