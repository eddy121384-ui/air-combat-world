"""Exact Taipei City comparison: authoritative WFS footprints vs Overture footprints.

Answers: how complete is Overture where an authoritative reference exists, how many Overture rows
duplicate WFS buildings, and what the WFS height-source mix is (Buju semantics, ported verbatim).
Writes data/ntw/taipei_wfs_vs_overture.json. Inputs are ignored caches (fetch_taipei_wfs.py,
fetch_overture_footprints.py).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import duckdb
import numpy as np
import shapely
from pyproj import Transformer
from shapely import STRtree, contains_xy, prepare
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent))
from heights import derive_wfs_height  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/generated/ntw"


def main():
    theater = json.loads((REPO / "data/ntw/theater_regions.json").read_text(encoding="utf-8"))
    tpe = next(r for r in theater["regions"] if r["key"] == "taipei")
    boundary = shape(tpe["boundary_simplified_150m"])
    prepare(boundary)

    wfs_geoms, wfs_src = [], Counter()
    for line in (CACHE / "wfs_taipei_citywide.ndjson").open(encoding="utf-8"):
        r = json.loads(line)
        g = shape(r["geometry"])
        wfs_geoms.append(g)
        wfs_src[derive_wfs_height(r["p"])[1]] += 1
    wfs = shapely.make_valid(np.array(wfs_geoms, dtype=object))  # overlap math only; production geometry repair is separate
    wfs_area = shapely.area(wfs)

    con = duckdb.connect()
    rows = con.execute(f"select id, wkb, src, height, num_floors from read_parquet('{(CACHE / 'ovt_taipei_fp.parquet').as_posix()}') order by id").fetchall()
    ids = [r[0] for r in rows]
    og = shapely.from_wkb([bytes(r[1]) for r in rows])
    c = shapely.centroid(og)
    inside = contains_xy(boundary, shapely.get_x(c), shapely.get_y(c))
    to3826 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
    coords = shapely.get_coordinates(og)
    x, y = to3826.transform(coords[:, 0], coords[:, 1])
    og = shapely.set_coordinates(og.copy(), np.column_stack([x, y]))
    og_in = shapely.make_valid(og[inside])
    src_in = np.array([r[2] for r in rows])[inside]
    area_o = shapely.area(og_in)

    tree = STRtree(wfs)
    qi, ti = tree.query(og_in, predicate="intersects")
    inter = shapely.area(shapely.intersection(og_in[qi], wfs[ti]))
    cov_o = np.zeros(len(og_in))
    np.add.at(cov_o, qi, inter)       # overlaps between WFS parts are rare; ratio is clipped to 1
    frac_o = np.minimum(cov_o / area_o, 1.0)
    cov_w = np.zeros(len(wfs))
    np.add.at(cov_w, ti, inter)
    frac_w = np.minimum(cov_w / wfs_area, 1.0)

    def pct(m):
        return round(100.0 * float(m), 2)

    out = {
        "overture_release": "2026-09-23.1", "wfs_hits": len(wfs), "overture_rows_in_taipei": int(inside.sum()),
        "wfs_total_footprint_km2": round(float(wfs_area.sum() / 1e6), 3),
        "overture_total_footprint_km2": round(float(area_o.sum() / 1e6), 3),
        "overture_rows_mostly_inside_wfs_pct_ge50": pct((frac_o >= 0.5).mean()),
        "overture_rows_no_wfs_overlap_pct": pct((frac_o < 0.05).mean()),
        "overture_rows_no_wfs_overlap_count": int((frac_o < 0.05).sum()),
        "wfs_features_ge50pct_covered_by_overture_pct": pct((frac_w >= 0.5).mean()),
        "wfs_features_not_touched_by_overture_pct": pct((frac_w < 0.05).mean()),
        "wfs_area_covered_by_overture_pct": pct(cov_w.sum() / wfs_area.sum()),
        "by_overture_source": {s: {"rows": int((src_in == s).sum()),
                                   "mostly_inside_wfs_pct": pct((frac_o[src_in == s] >= 0.5).mean())} for s in sorted(set(src_in))},
        "wfs_height_source_counts": dict(wfs_src),
        "note": "Exact over all of Taipei City; overlap uses planar EPSG:3826 intersection area. 'covered' = area fraction.",
    }
    p = REPO / "data/ntw/taipei_wfs_vs_overture.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
