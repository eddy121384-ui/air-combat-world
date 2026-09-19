"""Phase 2 — WorldModel v0: renderer-independent normalized buildings.

GIS in (EPSG:4326) -> WorldModel JSON (lon/lat preserved + theater-local ENU meters).
Coordinate rule: local tangent plane around theater origin (NOT lon*const hack):
    x = R * dlon_rad * cos(lat0)
    y = R * dlat_rad            (x=east, y=north, meters, WGS84 R=6378137)
Stdlib only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

R_WGS84 = 6378137.0
# Taipei 101 tower (used by the deterministic hero matcher).
TAIPEI_101_LONLAT = (121.5645, 25.0337)
# Hero-complex rule (v0): the WFS models 101 as a STACK of records sharing
# near-identical centroids (tower 512 m + shaft/crown records ~390-470 m, some
# with degenerate point footprints). Suppress every feature whose nearest
# polygon centroid is within radius AND whose surveyed height marks it as part
# of the tower stack. Neighbors (<300 m) are left standing.
HERO_SUPPRESS_RADIUS_M = 60.0
HERO_SUPPRESS_MIN_HEIGHT_M = 300.0


def enu_origin_from_city_yaml(path: Path) -> tuple[float, float]:
    """Minimal YAML reader for the one line we need (avoids a dep)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("enu_origin:"):
            lon = float(line.split("lon:")[1].split(",")[0])
            lat = float(line.split("lat:")[1].split(",")[0].rstrip(" }"))
            return lon, lat
    raise ValueError(f"enu_origin not found in {path}")


def lonlat_to_enu(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """WGS84 lon/lat -> local ENU meters around (lon0, lat0)."""
    dlon = math.radians(lon - lon0)
    dlat = math.radians(lat - lat0)
    x = R_WGS84 * dlon * math.cos(math.radians(lat0))
    y = R_WGS84 * dlat
    return x, y


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Independent reference for the meter-scale test."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def ring_centroid_lonlat(ring: list) -> tuple[float, float]:
    sx = sy = 0.0
    for p in ring:
        sx += p[0]
        sy += p[1]
    return sx / len(ring), sy / len(ring)


def ring_area_m2_enu(ring_enu: list) -> float:
    a = 0.0
    n = len(ring_enu)
    for i in range(n):
        x1, y1 = ring_enu[i]
        x2, y2 = ring_enu[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _iter_polygons(geom: dict):
    t = geom["type"]
    if t == "Polygon":
        yield geom["coordinates"]
    elif t == "MultiPolygon":
        yield from geom["coordinates"]


def build_worldmodel(sample_geojson: Path, city_yaml: Path) -> dict:
    """Normalize sample buildings to WorldModel v0 records."""
    lon0, lat0 = enu_origin_from_city_yaml(city_yaml)
    fc = json.loads(sample_geojson.read_text(encoding="utf-8"))
    buildings: list[dict] = []
    for f in fc["features"]:
        props = f.get("properties", {}) or {}
        height = props.get("height_m")
        if not isinstance(height, (int, float)) or not math.isfinite(height) or height <= 0:
            continue  # invalid heights never enter the WorldModel
        fid = str(f.get("id", f"noid-{len(buildings)}"))
        polys = []
        for polygon_index, poly in enumerate(_iter_polygons(f["geometry"])):
            outer = poly[0]
            holes = poly[1:]
            enu = [lonlat_to_enu(x, y, lon0, lat0) for x, y in outer]
            holes_enu = [
                [lonlat_to_enu(x, y, lon0, lat0) for x, y in hole]
                for hole in holes
            ]
            if any(not math.isfinite(v) for pt in enu for v in pt):
                continue  # NaN guard: drop bad rings, never propagate
            if any(not math.isfinite(v) for ring in holes_enu for pt in ring for v in pt):
                continue
            if len(enu) < 3:
                continue
            cx, cy = ring_centroid_lonlat(outer)
            polys.append({
                # Backward-compatible v0 fields: footprint_* remains the outer
                # ring so the baseline compiler keeps identical behavior.
                "footprint_lonlat": outer,
                "footprint_enu": enu,
                # v2 preserves source holes + part identity instead of silently
                # flattening them away before GEOS sees the polygon.
                "holes_lonlat": holes,
                "holes_enu": holes_enu,
                "source_geometry_type": f["geometry"]["type"],
                "source_polygon_index": polygon_index,
                "area_m2": ring_area_m2_enu(enu),
                "centroid_lonlat": [cx, cy],
                "centroid_enu": list(lonlat_to_enu(cx, cy, lon0, lat0)),
            })
        if not polys:
            continue
        buildings.append({
            "id": fid,
            "height_m": float(height),
            "height_source": props.get("height_source"),
            "source": "taipei_wfs_tp_building_height",
            "origin_lonlat": [lon0, lat0],
            "polygons": polys,
            "suppressed": False,
            "suppress_reason": None,
        })

    # --- Deterministic hero matcher: Taipei 101 complex ---
    # Rule: suppress ALL features with min centroid distance <= radius AND
    # height >= min-height (the tower stack). See constant comment above.
    matched_ids: list[str] = []
    for b in buildings:
        nearest = min(
            haversine_m(p["centroid_lonlat"][0], p["centroid_lonlat"][1],
                        TAIPEI_101_LONLAT[0], TAIPEI_101_LONLAT[1])
            for p in b["polygons"]
        )
        if nearest <= HERO_SUPPRESS_RADIUS_M and b["height_m"] >= HERO_SUPPRESS_MIN_HEIGHT_M:
            b["suppressed"] = True
            b["suppress_reason"] = (
                f"hero:taipei_101 complex member (nearest centroid {nearest:.1f}m, "
                f"height {b['height_m']}m)"
            )
            matched_ids.append(b["id"])
    matched_heights = [b["height_m"] for b in buildings if b["id"] in set(matched_ids)]

    return {
        "format": "air-combat-worldmodel",
        "version": "0",
        "crs_in": "EPSG:4326",
        "local_frame": {"type": "enu_meters", "origin_lonlat": [lon0, lat0]},
        "hero_match": {
            "rule": (f"suppress all features with min centroid distance to "
                     f"{TAIPEI_101_LONLAT} <= {HERO_SUPPRESS_RADIUS_M}m "
                     f"AND height_m >= {HERO_SUPPRESS_MIN_HEIGHT_M}"),
            "hero_point_lonlat": list(TAIPEI_101_LONLAT),
            "matched_building_ids": sorted(matched_ids),
            "matched_count": len(matched_ids),
            "matched_max_height_m": max(matched_heights) if matched_heights else None,
        },
        "buildings": buildings,
    }


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    wm = build_worldmodel(
        repo / "data/generated/taipei/sample_buildings.geojson",
        repo / "cities/taipei/city.yaml",
    )
    out = repo / "data/generated/taipei/worldmodel_sample.json"
    out.write_text(json.dumps(wm), encoding="utf-8")
    n = len(wm["buildings"])
    nsup = sum(1 for b in wm["buildings"] if b["suppressed"])
    print(f"WROTE {out} ({n} buildings, {nsup} suppressed, "
          f"hero_count={wm['hero_match']['matched_count']} "
          f"max_h={wm['hero_match']['matched_max_height_m']})")


if __name__ == "__main__":
    main()
