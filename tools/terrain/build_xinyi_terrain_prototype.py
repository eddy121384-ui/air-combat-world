"""Build deterministic 500 m Xinyi terrain prototype tiles from GLO-30 DSM.

PROTOTYPE ONLY. The final production surface target remains official MOI/TGOS
bare-earth 20 m DTM. This script validates the shared coordinate/tile/building-Z
contract without changing validated building mesh geometry.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np
import rasterio
import trimesh
from pyproj import Transformer
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))

from geometry import GAME_FROM_ENU_ZUP  # noqa: E402
from serialization_space import TILE_SIZE_M, tile_transform  # noqa: E402
from worldmodel import (R_WGS84, build_worldmodel,  # noqa: E402
                        enu_origin_from_city_yaml)

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
RASTER = REPO / "data/generated/taipei/terrain/cache/copernicus_glo30_xinyi_prototype.tif"
SOURCE_MANIFEST = REPO / "data/generated/taipei/terrain/copernicus_glo30_prototype_source.json"
OUT = REPO / "unreal/Saved/XinyiTerrainV0"
TILES_OUT = OUT / "tiles"
REPORT = OUT / "terrain_prototype.report.json"
BUILDING_Z = OUT / "building_z_offsets.json"

GRID_STEP_M = 20.0
GRID_COUNT = int(TILE_SIZE_M / GRID_STEP_M) + 1


def enu_to_lonlat(x, y, lon0, lat0):
    lat = lat0 + math.degrees(float(y) / R_WGS84)
    lon = lon0 + math.degrees(
        float(x) / (R_WGS84 * math.cos(math.radians(lat0)))
    )
    return lon, lat


class BilinearRaster:
    def __init__(self, path):
        self.ds = rasterio.open(path)
        self.band = self.ds.read(1, masked=False).astype(np.float64)
        self.nodata = self.ds.nodata
        self.to_raster = Transformer.from_crs("EPSG:4326", self.ds.crs, always_xy=True)
        self.inverse = ~self.ds.transform

    def close(self):
        self.ds.close()

    def sample_lonlat(self, lon, lat):
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.asarray(lat, dtype=np.float64)
        rx, ry = self.to_raster.transform(lon, lat)
        # Inverse affine returns pixel-corner coordinates. Convert to
        # pixel-center fractional indices for bilinear interpolation.
        col, row = self.inverse * (rx, ry)
        col = np.asarray(col, dtype=np.float64) - 0.5
        row = np.asarray(row, dtype=np.float64) - 0.5

        c0 = np.floor(col).astype(int)
        r0 = np.floor(row).astype(int)
        dc = col - c0
        dr = row - r0

        if (
            np.any(c0 < 0) or np.any(r0 < 0)
            or np.any(c0 + 1 >= self.band.shape[1])
            or np.any(r0 + 1 >= self.band.shape[0])
        ):
            raise RuntimeError("requested Xinyi terrain sample lies outside prototype raster")

        v00 = self.band[r0, c0]
        v10 = self.band[r0, c0 + 1]
        v01 = self.band[r0 + 1, c0]
        v11 = self.band[r0 + 1, c0 + 1]
        values = (
            v00 * (1-dc) * (1-dr)
            + v10 * dc * (1-dr)
            + v01 * (1-dc) * dr
            + v11 * dc * dr
        )
        if self.nodata is not None and np.any(
            np.isclose(np.stack([v00, v10, v01, v11]), self.nodata)
        ):
            raise RuntimeError("nodata encountered in Xinyi prototype terrain")
        if not np.all(np.isfinite(values)):
            raise RuntimeError("nonfinite terrain sample")
        return values


def robust_vertical_alignment(fc, sampler):
    """Estimate one global WFS-vs-DSM vertical offset using large roofs.

    GLO-30 is a DSM, so surveyed WFS roof elevations are a better prototype
    datum comparator than building ground elevations. Only large footprints are
    used; this is not the future official-DTM building anchoring policy.
    """
    to_lonlat = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    diffs = []
    rows = []

    for feature in fc["features"]:
        props = feature.get("properties") or {}
        top = props.get("top_elev_m")
        height = props.get("height_m")
        if not isinstance(top, (int, float)) or not math.isfinite(top):
            continue
        if not isinstance(height, (int, float)) or height < 8:
            continue

        geom = shape(feature["geometry"])
        if geom.is_empty or geom.area < 900.0:
            continue
        p = geom.representative_point()
        # Small 3x3 search helps a 30 m DSM cell actually hit a large roof.
        offsets = (-15.0, 0.0, 15.0)
        xy = [(p.x+dx, p.y+dy) for dx in offsets for dy in offsets]
        lonlat = [to_lonlat.transform(x, y) for x, y in xy]
        vals = sampler.sample_lonlat(
            np.asarray([q[0] for q in lonlat]),
            np.asarray([q[1] for q in lonlat]),
        )
        dsm_roof = float(np.max(vals))
        diff = float(top) - dsm_roof
        if math.isfinite(diff) and abs(diff) < 100:
            diffs.append(diff)
            rows.append({
                "building_id": str(feature.get("id", "")),
                "footprint_area_m2": float(geom.area),
                "surveyed_top_elev_m": float(top),
                "dsm_local_max_m": dsm_roof,
                "survey_minus_dsm_m": diff,
            })

    if len(diffs) < 100:
        raise RuntimeError(f"insufficient vertical alignment candidates: {len(diffs)}")

    ordered = sorted(diffs)
    offset = float(statistics.median(diffs))
    residual = [d-offset for d in diffs]
    abs_residual = [abs(x) for x in residual]
    return offset, {
        "candidate_count": len(diffs),
        "global_offset_m": offset,
        "diff_min_m": min(diffs),
        "diff_p05_m": ordered[int((len(ordered)-1)*0.05)],
        "diff_median_m": statistics.median(diffs),
        "diff_p95_m": ordered[int((len(ordered)-1)*0.95)],
        "diff_max_m": max(diffs),
        "median_abs_residual_m": statistics.median(abs_residual),
        "method": (
            "median(surveyed WFS top_elev_m - local 3x3 max Copernicus DSM) "
            "for footprints >=900m2 and height>=8m"
        ),
        "role": "prototype vertical-datum alignment only",
        "sample_preview": rows[:50],
    }


def building_surface_mismatch(fc, sampler, vertical_offset):
    """Quantify how much prototype DSM sits above surveyed building ground.

    This is diagnostic only. Positive values mean the rendered terrain surface
    would intersect/swallow the building base if the DSM is used directly.
    """
    to_lonlat = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    deltas = []
    rows = []
    for feature in fc["features"]:
        props = feature.get("properties") or {}
        ground = props.get("ground_elev_m")
        if not isinstance(ground, (int, float)) or not math.isfinite(ground):
            continue
        geom = shape(feature["geometry"])
        if geom.is_empty:
            continue
        p = geom.representative_point()
        offsets = (-15.0, 0.0, 15.0)
        xy = [(p.x+dx, p.y+dy) for dx in offsets for dy in offsets]
        lonlat = [to_lonlat.transform(x, y) for x, y in xy]
        vals = sampler.sample_lonlat(
            np.asarray([q[0] for q in lonlat]),
            np.asarray([q[1] for q in lonlat]),
        )
        terrain_surface = float(np.median(vals) + vertical_offset)
        delta = terrain_surface - float(ground)
        if math.isfinite(delta):
            deltas.append(delta)
            rows.append({
                "building_id": str(feature.get("id", "")),
                "surveyed_ground_elev_m": float(ground),
                "prototype_terrain_surface_m": terrain_surface,
                "terrain_minus_ground_m": delta,
            })
    if not deltas:
        raise RuntimeError("no building/terrain vertical mismatch samples")
    ordered = sorted(deltas)
    def pct(p):
        return ordered[int((len(ordered)-1)*p)]
    return {
        "count": len(deltas),
        "min_m": min(deltas),
        "p05_m": pct(0.05),
        "median_m": statistics.median(deltas),
        "p95_m": pct(0.95),
        "max_m": max(deltas),
        "terrain_above_ground_gt_1m": sum(d > 1.0 for d in deltas),
        "terrain_above_ground_gt_3m": sum(d > 3.0 for d in deltas),
        "terrain_above_ground_gt_5m": sum(d > 5.0 for d in deltas),
        "terrain_above_ground_gt_10m": sum(d > 10.0 for d in deltas),
        "method": (
            "median aligned Copernicus DSM over 3x3 samples spaced 15m around "
            "building representative point minus surveyed WFS ground_elev_m"
        ),
        "meaning": (
            "positive values indicate DSM surface is above the surveyed building "
            "base; this is expected over roofs/vegetation and explains visual burial"
        ),
        "sample_preview": rows[:50],
    }


def terrain_tile(origin, sampler, lon0, lat0, vertical_offset):
    local = np.linspace(0.0, TILE_SIZE_M, GRID_COUNT, dtype=np.float64)
    gx, gy = np.meshgrid(local + origin[0], local + origin[1])
    lon = np.empty_like(gx)
    lat = np.empty_like(gy)
    for iy in range(GRID_COUNT):
        for ix in range(GRID_COUNT):
            lon[iy, ix], lat[iy, ix] = enu_to_lonlat(
                gx[iy, ix], gy[iy, ix], lon0, lat0
            )
    z = sampler.sample_lonlat(lon.ravel(), lat.ravel()).reshape(gx.shape)
    z = z + vertical_offset

    # Local ENU Z-up geometry.
    lx, ly = np.meshgrid(local, local)
    vertices = np.column_stack([lx.ravel(), ly.ravel(), z.ravel()])
    faces = []
    for iy in range(GRID_COUNT-1):
        for ix in range(GRID_COUNT-1):
            a = iy*GRID_COUNT + ix
            b = a + 1
            d = (iy+1)*GRID_COUNT + ix
            c = d + 1
            faces.append((a,b,c))
            faces.append((a,c,d))
    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
    )
    mesh.apply_transform(GAME_FROM_ENU_ZUP)
    return mesh, z


def tile_name(origin):
    return f"{int(origin[0]//500):+04d}_{int(origin[1]//500):+04d}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    TILES_OUT.mkdir(parents=True, exist_ok=True)
    fc = json.loads(SOURCE.read_text(encoding="utf-8"))
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    lon0, lat0 = enu_origin_from_city_yaml(CITY)

    # Derive the exact 500m tile coverage from validated building ENU geometry.
    xs, ys = [], []
    for b in wm["buildings"]:
        for p in b["polygons"]:
            xs.extend(q[0] for q in p["footprint_enu"])
            ys.extend(q[1] for q in p["footprint_enu"])
    min_tx = math.floor(min(xs)/TILE_SIZE_M)
    max_tx = math.floor(max(xs)/TILE_SIZE_M)
    min_ty = math.floor(min(ys)/TILE_SIZE_M)
    max_ty = math.floor(max(ys)/TILE_SIZE_M)
    origins = [
        (tx*TILE_SIZE_M, ty*TILE_SIZE_M)
        for ty in range(min_ty, max_ty+1)
        for tx in range(min_tx, max_tx+1)
    ]

    sampler = BilinearRaster(RASTER)
    try:
        vertical_offset, alignment = robust_vertical_alignment(fc, sampler)
        surface_mismatch = building_surface_mismatch(fc, sampler, vertical_offset)

        tile_rows = []
        edge_cache = {}
        seam_errors = []
        total_vertices = total_triangles = 0

        for origin in origins:
            mesh, z = terrain_tile(origin, sampler, lon0, lat0, vertical_offset)
            name = tile_name(origin)
            scene = trimesh.Scene()
            scene.add_geometry(
                mesh, geom_name=f"terrain_{name}", node_name=f"terrain_{name}",
                transform=tile_transform(origin),
            )
            blob = scene.export(file_type="glb")
            out = TILES_OUT / f"xinyi_terrain_{name}.glb"
            out.write_bytes(blob)
            digest = hashlib.sha256(blob).hexdigest()

            # Store shared boundaries keyed by global grid endpoints.
            edges = {
                "west": z[:,0].astype(np.float32),
                "east": z[:,-1].astype(np.float32),
                "south": z[0,:].astype(np.float32),
                "north": z[-1,:].astype(np.float32),
            }
            tx, ty = int(origin[0]//500), int(origin[1]//500)
            checks = [
                ((tx-1,ty,"east"), "west"),
                ((tx,ty-1,"north"), "south"),
            ]
            for key, edge_name in checks:
                if key in edge_cache:
                    other = edge_cache[key]
                    diff = np.abs(other - edges[edge_name])
                    if float(np.max(diff)) != 0.0:
                        seam_errors.append({
                            "tile": name,
                            "edge": edge_name,
                            "max_abs_m": float(np.max(diff)),
                        })
            edge_cache[(tx,ty,"west")] = edges["west"]
            edge_cache[(tx,ty,"east")] = edges["east"]
            edge_cache[(tx,ty,"south")] = edges["south"]
            edge_cache[(tx,ty,"north")] = edges["north"]

            total_vertices += len(mesh.vertices)
            total_triangles += len(mesh.faces)
            tile_rows.append({
                "tile": name,
                "origin_enu_m": [origin[0], origin[1]],
                "grid": [GRID_COUNT, GRID_COUNT],
                "step_m": GRID_STEP_M,
                "elevation_min_m": float(np.min(z)),
                "elevation_max_m": float(np.max(z)),
                "vertices": len(mesh.vertices),
                "triangles": len(mesh.faces),
                "bytes": len(blob),
                "sha256": digest,
            })

        # Surveyed building base elevations are authoritative candidate anchors,
        # independent of prototype terrain surface.
        offsets = {}
        missing = []
        for f in fc["features"]:
            bid = str(f.get("id", ""))
            ground = (f.get("properties") or {}).get("ground_elev_m")
            if not isinstance(ground, (int,float)) or not math.isfinite(ground):
                missing.append(bid)
            else:
                offsets[bid] = float(ground)

        z_manifest = {
            "policy": "surveyed WFS ground_elev_m as building world-up offset",
            "status": "CANDIDATE_ANCHOR_PENDING_OFFICIAL_DTM_DATUM_CROSSCHECK",
            "count": len(offsets),
            "missing": missing,
            "offsets_m": offsets,
        }
        BUILDING_Z.write_text(
            json.dumps(z_manifest, separators=(",",":"), allow_nan=False)+"\n",
            encoding="utf-8",
        )

        terrain_hash = hashlib.sha256(
            "\n".join(f'{r["tile"]}:{r["sha256"]}' for r in tile_rows).encode()
        ).hexdigest()

        report = {
            "gate": "Xinyi terrain v0 cloud prototype",
            "status": "PASS_PROTOTYPE_NOT_PRODUCTION_TERRAIN",
            "terrain_source": source_manifest,
            "building_xy_geometry": "unchanged validated Xinyi building GLBs",
            "tile_policy": {
                "size_m": TILE_SIZE_M,
                "grid_step_m": GRID_STEP_M,
                "grid_vertices_per_axis": GRID_COUNT,
                "tile_count": len(origins),
                "tile_index_range": {
                    "x": [min_tx,max_tx],
                    "y": [min_ty,max_ty],
                },
            },
            "vertical_alignment": alignment,
            "building_surface_mismatch": surface_mismatch,
            "building_z": {
                "source": "WFS ground_elev_m",
                "count": len(offsets),
                "missing_count": len(missing),
                "status": z_manifest["status"],
            },
            "qa": {
                "all_finite": all(
                    math.isfinite(r["elevation_min_m"]) and math.isfinite(r["elevation_max_m"])
                    for r in tile_rows
                ),
                "seam_failure_count": len(seam_errors),
                "seam_failures": seam_errors,
            },
            "output": {
                "terrain_tiles": tile_rows,
                "total_vertices": total_vertices,
                "total_triangles": total_triangles,
                "manifest_sha256": terrain_hash,
                "building_z_offsets": str(BUILDING_Z.relative_to(REPO)),
            },
            "limitations": [
                "Copernicus GLO-30 is DSM, not bare-earth DTM.",
                "Urban raster surface can contain building/vegetation elevations.",
                "Global vertical alignment is prototype-only.",
                "Production terrain awaits official MOI/TGOS DTM file access and datum cross-check.",
            ],
        }
        REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
            encoding="utf-8",
        )

        passed = (
            len(origins) > 0
            and not seam_errors
            and len(missing) == 0
            and report["qa"]["all_finite"]
        )
        print(json.dumps({
            "pass": passed,
            "terrain_status": report["status"],
            "tiles": len(origins),
            "total_vertices": total_vertices,
            "total_triangles": total_triangles,
            "terrain_elevation_min_m": min(r["elevation_min_m"] for r in tile_rows),
            "terrain_elevation_max_m": max(r["elevation_max_m"] for r in tile_rows),
            "vertical_alignment": alignment,
            "building_surface_mismatch": surface_mismatch,
            "building_z_count": len(offsets),
            "seam_failures": len(seam_errors),
            "manifest_sha256": terrain_hash,
        }, ensure_ascii=False, indent=2))
        if not passed:
            raise SystemExit(2)
    finally:
        sampler.close()


if __name__ == "__main__":
    main()
