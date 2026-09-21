"""Build deterministic Xinyi terrain tiles from the MOI 2025 DTM derivative mirror.

Unlike the earlier Copernicus prototype, this source is bare-earth DTM semantics.
A single documented global vertical datum offset is estimated from surveyed WFS
building ground elevations, then the residual agreement is measured explicitly.
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
from worldmodel import R_WGS84, build_worldmodel, enu_origin_from_city_yaml  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
RASTER = REPO / "data/generated/taipei/terrain/cache/moi_2025_dtm_xinyi_mirror.tif"
SOURCE_MANIFEST = REPO / "data/generated/taipei/terrain/moi_2025_dtm_mirror_source.json"
OUT = REPO / "unreal/Saved/XinyiTerrainV0"
TILES_OUT = OUT / "tiles"
REPORT = OUT / "terrain_dtm.report.json"
BUILDING_Z = OUT / "building_z_offsets.json"

GRID_STEP_M = 20.0
GRID_COUNT = int(TILE_SIZE_M / GRID_STEP_M) + 1


def enu_to_lonlat(x, y, lon0, lat0):
    lat = lat0 + math.degrees(float(y) / R_WGS84)
    lon = lon0 + math.degrees(float(x) / (R_WGS84 * math.cos(math.radians(lat0))))
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
        col, row = self.inverse * (rx, ry)
        col = np.asarray(col, dtype=np.float64) - 0.5
        row = np.asarray(row, dtype=np.float64) - 0.5
        c0 = np.floor(col).astype(int)
        r0 = np.floor(row).astype(int)
        dc, dr = col - c0, row - r0
        if (
            np.any(c0 < 0) or np.any(r0 < 0)
            or np.any(c0 + 1 >= self.band.shape[1])
            or np.any(r0 + 1 >= self.band.shape[0])
        ):
            raise RuntimeError("requested Xinyi sample lies outside MOI DTM mirror raster")
        v00 = self.band[r0, c0]
        v10 = self.band[r0, c0 + 1]
        v01 = self.band[r0 + 1, c0]
        v11 = self.band[r0 + 1, c0 + 1]
        values = v00*(1-dc)*(1-dr) + v10*dc*(1-dr) + v01*(1-dc)*dr + v11*dc*dr
        if not np.all(np.isfinite(values)):
            raise RuntimeError("nonfinite MOI DTM sample")
        return values


def pct(values, p):
    ordered = sorted(values)
    return ordered[int((len(ordered)-1)*p)]


def sample_building_ground_deltas(fc, sampler, vertical_offset=0.0):
    to_lonlat = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    rows, deltas = [], []
    for f in fc["features"]:
        props = f.get("properties") or {}
        ground = props.get("ground_elev_m")
        if not isinstance(ground, (int, float)) or not math.isfinite(ground):
            continue
        geom = shape(f["geometry"])
        if geom.is_empty:
            continue
        p = geom.representative_point()
        lon, lat = to_lonlat.transform(p.x, p.y)
        dtm = float(sampler.sample_lonlat([lon], [lat])[0]) + vertical_offset
        delta = dtm - float(ground)
        deltas.append(delta)
        rows.append({
            "building_id": str(f.get("id", "")),
            "wfs_ground_elev_m": float(ground),
            "dtm_elev_m": dtm,
            "dtm_minus_wfs_ground_m": delta,
        })
    if not deltas:
        raise RuntimeError("no DTM/WFS ground comparison samples")
    absd = [abs(x) for x in deltas]
    return {
        "count": len(deltas),
        "min_m": min(deltas),
        "p05_m": pct(deltas, 0.05),
        "median_m": statistics.median(deltas),
        "p95_m": pct(deltas, 0.95),
        "max_m": max(deltas),
        "median_abs_m": statistics.median(absd),
        "p95_abs_m": pct(absd, 0.95),
        "gt_1m_abs": sum(abs(x) > 1 for x in deltas),
        "gt_3m_abs": sum(abs(x) > 3 for x in deltas),
        "gt_5m_abs": sum(abs(x) > 5 for x in deltas),
        "sample_preview": rows[:50],
    }


def terrain_tile(origin, sampler, lon0, lat0, vertical_offset):
    local = np.linspace(0.0, TILE_SIZE_M, GRID_COUNT, dtype=np.float64)
    gx, gy = np.meshgrid(local + origin[0], local + origin[1])
    lon = np.empty_like(gx)
    lat = np.empty_like(gy)
    for iy in range(GRID_COUNT):
        for ix in range(GRID_COUNT):
            lon[iy, ix], lat[iy, ix] = enu_to_lonlat(gx[iy, ix], gy[iy, ix], lon0, lat0)
    z = sampler.sample_lonlat(lon.ravel(), lat.ravel()).reshape(gx.shape) + vertical_offset

    lx, ly = np.meshgrid(local, local)
    vertices = np.column_stack([lx.ravel(), ly.ravel(), z.ravel()])
    faces = []
    for iy in range(GRID_COUNT - 1):
        for ix in range(GRID_COUNT - 1):
            a = iy*GRID_COUNT + ix
            b = a + 1
            d = (iy+1)*GRID_COUNT + ix
            c = d + 1
            faces.extend([(a,b,c), (a,c,d)])
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int64), process=False)
    mesh.apply_transform(GAME_FROM_ENU_ZUP)
    return mesh, z


def tile_name(origin):
    return f"{int(origin[0]//500):+04d}_{int(origin[1]//500):+04d}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    TILES_OUT.mkdir(parents=True, exist_ok=True)
    for old in TILES_OUT.glob("*.glb"):
        old.unlink()

    fc = json.loads(SOURCE.read_text(encoding="utf-8"))
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    lon0, lat0 = enu_origin_from_city_yaml(CITY)

    xs, ys = [], []
    for b in wm["buildings"]:
        for p in b["polygons"]:
            xs.extend(q[0] for q in p["footprint_enu"])
            ys.extend(q[1] for q in p["footprint_enu"])
    min_tx, max_tx = math.floor(min(xs)/TILE_SIZE_M), math.floor(max(xs)/TILE_SIZE_M)
    min_ty, max_ty = math.floor(min(ys)/TILE_SIZE_M), math.floor(max(ys)/TILE_SIZE_M)
    origins = [(tx*TILE_SIZE_M, ty*TILE_SIZE_M)
               for ty in range(min_ty, max_ty+1)
               for tx in range(min_tx, max_tx+1)]

    sampler = BilinearRaster(RASTER)
    try:
        raw = sample_building_ground_deltas(fc, sampler, 0.0)
        # DTM minus surveyed ground -> add the opposite median as one global datum shift.
        vertical_offset = -float(raw["median_m"])
        aligned = sample_building_ground_deltas(fc, sampler, vertical_offset)

        tile_rows, seam_errors, edge_cache = [], [], {}
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

            edges = {
                "west": z[:,0].astype(np.float32),
                "east": z[:,-1].astype(np.float32),
                "south": z[0,:].astype(np.float32),
                "north": z[-1,:].astype(np.float32),
            }
            tx, ty = int(origin[0]//500), int(origin[1]//500)
            for key, edge_name in [((tx-1,ty,"east"),"west"), ((tx,ty-1,"north"),"south")]:
                if key in edge_cache:
                    diff = np.abs(edge_cache[key] - edges[edge_name])
                    if float(np.max(diff)) != 0.0:
                        seam_errors.append({"tile":name,"edge":edge_name,"max_abs_m":float(np.max(diff))})
            for edge_name, arr in edges.items():
                edge_cache[(tx,ty,edge_name)] = arr

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

        offsets, missing = {}, []
        for f in fc["features"]:
            bid = str(f.get("id", ""))
            ground = (f.get("properties") or {}).get("ground_elev_m")
            if not isinstance(ground, (int,float)) or not math.isfinite(ground):
                missing.append(bid)
            else:
                offsets[bid] = float(ground)

        BUILDING_Z.write_text(json.dumps({
            "policy":"surveyed WFS ground_elev_m as building Blender-world base elevation",
            "terrain_source":"MOI 2025 bare-earth DTM derivative mirror",
            "vertical_datum_offset_applied_to_dtm_m":vertical_offset,
            "count":len(offsets),
            "missing":missing,
            "offsets_m":offsets,
        }, separators=(",",":"), allow_nan=False)+"\n", encoding="utf-8")

        terrain_hash = hashlib.sha256(
            "\n".join(f'{r["tile"]}:{r["sha256"]}' for r in tile_rows).encode()
        ).hexdigest()

        agreement_pass = aligned["median_abs_m"] <= 2.0 and aligned["p95_abs_m"] <= 8.0
        passed = (
            len(origins) == 25 and not seam_errors and not missing
            and all(math.isfinite(r["elevation_min_m"]) and math.isfinite(r["elevation_max_m"]) for r in tile_rows)
            and agreement_pass
        )

        report = {
            "gate":"Xinyi terrain v0 MOI 2025 DTM mirror",
            "status":"PASS_DTM_CANDIDATE" if passed else "FAIL_DTM_GROUND_AGREEMENT",
            "terrain_source":source_manifest,
            "vertical_alignment":{
                "method":"one global offset = -median(DTM - surveyed WFS ground_elev_m)",
                "offset_applied_m":vertical_offset,
                "raw_dtm_minus_wfs_ground":raw,
                "aligned_dtm_minus_wfs_ground":aligned,
                "acceptance":{"median_abs_m_max":2.0,"p95_abs_m_max":8.0,"pass":agreement_pass},
            },
            "building_xy_geometry":"unchanged validated Xinyi building GLBs",
            "building_z":{"source":"WFS ground_elev_m","count":len(offsets),"missing_count":len(missing)},
            "tile_policy":{"size_m":TILE_SIZE_M,"grid_step_m":GRID_STEP_M,"tile_count":len(origins)},
            "qa":{"seam_failure_count":len(seam_errors),"seam_failures":seam_errors},
            "output":{
                "terrain_tiles":tile_rows,
                "total_vertices":total_vertices,
                "total_triangles":total_triangles,
                "manifest_sha256":terrain_hash,
                "building_z_offsets":str(BUILDING_Z.relative_to(REPO)),
            },
        }
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")

        print(json.dumps({
            "pass":passed,
            "status":report["status"],
            "tiles":len(origins),
            "vertical_offset_m":vertical_offset,
            "raw_ground_agreement":raw,
            "aligned_ground_agreement":aligned,
            "seam_failures":len(seam_errors),
            "manifest_sha256":terrain_hash,
        }, ensure_ascii=False, indent=2))
        if not passed:
            raise SystemExit(2)
    finally:
        sampler.close()


if __name__ == "__main__":
    main()
