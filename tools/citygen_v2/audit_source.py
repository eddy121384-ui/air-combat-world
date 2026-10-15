"""Audit the committed Xinyi WFS snapshot before any v2 meshing.

This measures source geometry loss separately from triangulation or extrusion.
A mature geometry library cannot recover coordinates already quantized into
a point or line.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

R_WGS84 = 6378137.0


def _iter_polygons(geom: dict):
    if geom.get("type") == "Polygon":
        yield geom["coordinates"]
    elif geom.get("type") == "MultiPolygon":
        yield from geom["coordinates"]


def _decimal_digits(value: float) -> int:
    text = format(float(value), ".15g")
    if "e" in text.lower() or "." not in text:
        return 0
    return len(text.rstrip("0").split(".", 1)[1])


def _distinct_xy_count(ring: list) -> int:
    return len({(float(p[0]), float(p[1])) for p in ring})


def audit(path: Path) -> dict:
    fc = json.loads(path.read_text(encoding="utf-8"))
    type_counts = Counter()
    decimal_counts = Counter()
    polygon_parts = 0
    multipart_features = 0
    features_with_holes = 0
    parts_with_holes = 0
    collapsed_parts = 0
    collapsed_features: set[str] = set()
    ext_vertex_counts: list[int] = []
    lats: list[float] = []

    for f in fc["features"]:
        geom = f.get("geometry") or {}
        type_counts[geom.get("type", "None")] += 1
        polys = list(_iter_polygons(geom))
        if len(polys) > 1:
            multipart_features += 1
        has_hole = False
        for poly in polys:
            polygon_parts += 1
            if len(poly) > 1:
                parts_with_holes += 1
                has_hole = True
            outer = poly[0] if poly else []
            distinct = _distinct_xy_count(outer)
            ext_vertex_counts.append(distinct)
            if distinct < 3:
                collapsed_parts += 1
                collapsed_features.add(str(f.get("id")))
            for ring in poly:
                for lon, lat in ring:
                    decimal_counts[_decimal_digits(lon)] += 1
                    decimal_counts[_decimal_digits(lat)] += 1
                    lats.append(float(lat))
        if has_hole:
            features_with_holes += 1

    max_decimals = max(decimal_counts, default=0)
    median_lat = sorted(lats)[len(lats) // 2] if lats else 25.0
    if max_decimals > 0:
        step_deg = 10.0 ** (-max_decimals)
        lat_step_m = R_WGS84 * math.radians(step_deg)
        lon_step_m = lat_step_m * math.cos(math.radians(median_lat))
    else:
        lat_step_m = lon_step_m = None

    ext_vertex_counts.sort()

    def quantile(q: float):
        if not ext_vertex_counts:
            return None
        return ext_vertex_counts[round((len(ext_vertex_counts) - 1) * q)]

    return {
        "source": str(path),
        "feature_count": len(fc["features"]),
        "geometry_type_counts": dict(type_counts),
        "polygon_parts": polygon_parts,
        "multipart_features": multipart_features,
        "features_with_holes": features_with_holes,
        "parts_with_holes": parts_with_holes,
        "collapsed_exterior_parts_lt3_distinct_xy": collapsed_parts,
        "collapsed_feature_count": len(collapsed_features),
        "exterior_distinct_vertex_count": {
            "min": min(ext_vertex_counts) if ext_vertex_counts else None,
            "p50": quantile(0.50),
            "p90": quantile(0.90),
            "p99": quantile(0.99),
            "max": max(ext_vertex_counts) if ext_vertex_counts else None,
        },
        "coordinate_decimal_digit_histogram": {
            str(k): v for k, v in sorted(decimal_counts.items())
        },
        "max_coordinate_decimals_observed": max_decimals,
        "approx_coordinate_grid_m_at_median_lat": {
            "east_west": lon_step_m,
            "north_south": lat_step_m,
            "median_lat": median_lat,
        },
        "precision_warning": (
            "EPSG:4326 coordinates are quantized coarsely enough to collapse "
            "small footprints; verify a higher-precision/native-CRS WFS route "
            "before treating this layer as production footprint truth."
            if max_decimals <= 4
            else None
        ),
    }


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=repo / "data/generated/taipei/sample_buildings.geojson",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo / "data/generated/taipei/xinyi_v2_source_audit.report.json",
    )
    args = parser.parse_args()
    report = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
