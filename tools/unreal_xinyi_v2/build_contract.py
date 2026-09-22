"""Build the engine-facing XinyiV2 contract from already-validated upstream data.

This stage does not run Unreal and does not alter building geometry. It converts
accepted MOI 2025 DTM elevations into a deterministic Unreal Landscape heightmap
and records the exact building/tile placement contract that the Unreal import
stage must satisfy.

Landscape topology is deliberately aligned to the existing city tile grid:

    5 x 5 Landscape components
    2 x 2 sections/component
    63 quads/section
    126 quads/component
    500 m/component
    631 x 631 height samples

The 20 m DTM is bilinearly oversampled only to satisfy Unreal Landscape topology.
This does not increase the semantic/source accuracy of the terrain.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import rasterio
import trimesh
from PIL import Image
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))

from worldmodel import R_WGS84, enu_origin_from_city_yaml  # noqa: E402

CITY = REPO / "cities/taipei/city.yaml"
RASTER = REPO / "data/generated/taipei/terrain/cache/moi_2025_dtm_xinyi_mirror.tif"
TERRAIN_SOURCE = REPO / "data/generated/taipei/terrain/moi_2025_dtm_mirror_source.json"
TERRAIN_REPORT = REPO / "unreal/Saved/XinyiTerrainV0/terrain_dtm.report.json"
BUILDING_Z = REPO / "unreal/Saved/XinyiTerrainV0/building_z_offsets.json"
FULL_REPORT = REPO / "unreal/Saved/XinyiV2Full/run-01/full_xinyi.report.json"
OUT = REPO / "unreal/Saved/XinyiUnrealV2Contract"
BUILDING_TILES = REPO / "unreal/Saved/XinyiV2Full/run-01/tiles"
BUILDING_ID_RE = re.compile(r"^(tp_building_height\.\d+)")

EXPECTED_BUILDING_SOURCE_SHA256 = "c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d"
EXPECTED_BUILDING_MANIFEST_SHA256 = "bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15"

TILE_SIZE_M = 500.0
COMPONENTS_PER_AXIS = 5
SECTIONS_PER_COMPONENT = 2
SECTION_QUADS = 63
COMPONENT_QUADS = SECTIONS_PER_COMPONENT * SECTION_QUADS  # 126
HEIGHTMAP_SIZE = COMPONENTS_PER_AXIS * COMPONENT_QUADS + 1  # 631
LANDSCAPE_SCALE_Z = 200.0
HEIGHT_ROUNDTRIP_TOLERANCE_M = 0.01


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def enu_to_lonlat(east_m, north_m, lon0, lat0):
    east_m = np.asarray(east_m, dtype=np.float64)
    north_m = np.asarray(north_m, dtype=np.float64)
    lat = lat0 + np.degrees(north_m / R_WGS84)
    lon = lon0 + np.degrees(
        east_m / (R_WGS84 * math.cos(math.radians(lat0)))
    )
    return lon, lat


def enu_to_ue_cm(east_m: float, north_m: float, up_m: float = 0.0):
    """Validated mapping: ENU east/north/up -> UE X/-Y/Z in centimetres."""
    return [east_m * 100.0, -north_m * 100.0, up_m * 100.0]

def game_bounds_to_ue_bounds(bounds_game_m, ground_m: float):
    """Map validated glTF/game-frame world bounds to expected UE world bounds.

    The validated importer mapping is game (X, Y, Z) -> UE (X, Z, Y), with
    metres -> centimetres. Game Z already stores -north. The building mesh base
    is authored at game Y=0, so surveyed WFS ground is added only to UE Z.
    """
    b = np.asarray(bounds_game_m, dtype=np.float64)
    if b.shape != (2, 3) or not np.all(np.isfinite(b)):
        raise RuntimeError("invalid game-frame bounds")
    lo, hi = b[0], b[1]
    ue_min = np.asarray(
        [lo[0] * 100.0, lo[2] * 100.0, (lo[1] + ground_m) * 100.0],
        dtype=np.float64,
    )
    ue_max = np.asarray(
        [hi[0] * 100.0, hi[2] * 100.0, (hi[1] + ground_m) * 100.0],
        dtype=np.float64,
    )
    return ue_min, ue_max


def canonical_component_key(name: str) -> str:
    """Package-safe comparison key for GLB node names vs Interchange asset names."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(name)).strip("_").lower()


def build_component_placement_manifest(tiles_dir: Path, tile_rows, z_offsets):
    rows = []
    failures = []
    seen_keys = set()

    for tile_row in tile_rows:
        glb = tiles_dir / tile_row["building_glb"]
        if not glb.is_file():
            failures.append({"tile": tile_row["tile"], "reason": "missing_glb", "path": str(glb)})
            continue

        scene = trimesh.load_scene(glb, file_type="glb", process=False)
        node_names = sorted(scene.graph.nodes_geometry)
        if len(node_names) != int(tile_row["building_nodes"]):
            failures.append({
                "tile": tile_row["tile"],
                "reason": "node_count_mismatch",
                "expected": int(tile_row["building_nodes"]),
                "actual": len(node_names),
            })
            continue

        for node_name in node_names:
            match = BUILDING_ID_RE.match(str(node_name))
            if not match:
                failures.append({
                    "tile": tile_row["tile"],
                    "node": str(node_name),
                    "reason": "building_id_unparseable",
                })
                continue
            building_id = match.group(1)
            if building_id not in z_offsets:
                failures.append({
                    "tile": tile_row["tile"],
                    "node": str(node_name),
                    "building_id": building_id,
                    "reason": "missing_surveyed_ground",
                })
                continue

            transform, geometry_name = scene.graph[node_name]
            mesh = scene.geometry[geometry_name].copy()
            mesh.apply_transform(transform)
            bounds = np.asarray(mesh.bounds, dtype=np.float64)
            ue_min, ue_max = game_bounds_to_ue_bounds(
                bounds, float(z_offsets[building_id])
            )
            ue_origin = (ue_min + ue_max) * 0.5
            ue_extent = (ue_max - ue_min) * 0.5
            key = canonical_component_key(node_name)
            if key in seen_keys:
                failures.append({
                    "tile": tile_row["tile"],
                    "node": str(node_name),
                    "reason": "canonical_component_key_collision",
                    "key": key,
                })
                continue
            seen_keys.add(key)

            rows.append({
                "tile": tile_row["tile"],
                "node_name": str(node_name),
                "canonical_key": key,
                "building_id": building_id,
                "surveyed_ground_m": float(z_offsets[building_id]),
                "expected_ue_bounds_min_cm": ue_min.tolist(),
                "expected_ue_bounds_max_cm": ue_max.tolist(),
                "expected_ue_bounds_origin_cm": ue_origin.tolist(),
                "expected_ue_bounds_extent_cm": ue_extent.tolist(),
            })

    if failures:
        raise RuntimeError(
            "component placement manifest failed: "
            + json.dumps(failures[:10], ensure_ascii=False)
        )
    return rows



def encode_landscape_height_m(height_m, scale_z=LANDSCAPE_SCALE_Z):
    """Encode metres to Unreal Landscape uint16 storage.

    Unreal Landscape height decoding is:
        height_cm = (uint16 - 32768) * ScaleZ / 128
    """
    z = np.asarray(height_m, dtype=np.float64)
    code = np.rint(32768.0 + z * 100.0 * 128.0 / float(scale_z))
    if np.any(code < 0.0) or np.any(code > 65535.0):
        raise RuntimeError(
            f"terrain exceeds Landscape ScaleZ={scale_z} representable range"
        )
    return code.astype(np.uint16)


def decode_landscape_height_m(code, scale_z=LANDSCAPE_SCALE_Z):
    code = np.asarray(code, dtype=np.float64)
    return (code - 32768.0) * float(scale_z) / 128.0 / 100.0


class BilinearRaster:
    def __init__(self, path: Path):
        self.ds = rasterio.open(path)
        self.band = self.ds.read(1, masked=False).astype(np.float64)
        self.to_raster = Transformer.from_crs(
            "EPSG:4326", self.ds.crs, always_xy=True
        )
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
        dc = col - c0
        dr = row - r0
        if (
            np.any(c0 < 0)
            or np.any(r0 < 0)
            or np.any(c0 + 1 >= self.band.shape[1])
            or np.any(r0 + 1 >= self.band.shape[0])
        ):
            raise RuntimeError("Landscape sample lies outside the accepted DTM raster")
        v00 = self.band[r0, c0]
        v10 = self.band[r0, c0 + 1]
        v01 = self.band[r0 + 1, c0]
        v11 = self.band[r0 + 1, c0 + 1]
        out = (
            v00 * (1 - dc) * (1 - dr)
            + v10 * dc * (1 - dr)
            + v01 * (1 - dc) * dr
            + v11 * dc * dr
        )
        if not np.all(np.isfinite(out)):
            raise RuntimeError("nonfinite accepted-DTM sample")
        return out


def _origin_set(rows):
    return {
        (float(row["origin_enu_m"][0]), float(row["origin_enu_m"][1]))
        for row in rows
    }


def validate_tile_grid(building_tiles, terrain_tiles):
    b = _origin_set(building_tiles)
    t = _origin_set(terrain_tiles)
    if b != t:
        raise RuntimeError(
            f"building/terrain tile-origin mismatch: buildings={len(b)} terrain={len(t)}"
        )
    if len(b) != 25:
        raise RuntimeError(f"expected 25 shared tile origins, found {len(b)}")

    xs = sorted({x for x, _ in b})
    ys = sorted({y for _, y in b})
    if len(xs) != COMPONENTS_PER_AXIS or len(ys) != COMPONENTS_PER_AXIS:
        raise RuntimeError(f"expected 5x5 tile grid, got {len(xs)}x{len(ys)}")
    if any(not math.isclose(xs[i + 1] - xs[i], TILE_SIZE_M, abs_tol=1e-9)
           for i in range(len(xs) - 1)):
        raise RuntimeError("building/terrain X origins are not on the 500 m grid")
    if any(not math.isclose(ys[i + 1] - ys[i], TILE_SIZE_M, abs_tol=1e-9)
           for i in range(len(ys) - 1)):
        raise RuntimeError("building/terrain Y origins are not on the 500 m grid")

    expected = {(x, y) for x in xs for y in ys}
    if b != expected:
        raise RuntimeError("shared 500 m tile grid is not a complete Cartesian 5x5 set")

    return {
        "min_east_m": xs[0],
        "max_east_m": xs[-1] + TILE_SIZE_M,
        "min_north_m": ys[0],
        "max_north_m": ys[-1] + TILE_SIZE_M,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--terrain-report", type=Path, default=TERRAIN_REPORT)
    p.add_argument("--building-z", type=Path, default=BUILDING_Z)
    p.add_argument("--full-report", type=Path, default=FULL_REPORT)
    p.add_argument("--raster", type=Path, default=RASTER)
    p.add_argument("--terrain-source", type=Path, default=TERRAIN_SOURCE)
    p.add_argument("--building-tiles-dir", type=Path, default=BUILDING_TILES)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()

    terrain = json.loads(args.terrain_report.read_text(encoding="utf-8"))
    building_z = json.loads(args.building_z.read_text(encoding="utf-8"))
    full = json.loads(args.full_report.read_text(encoding="utf-8"))
    source = json.loads(args.terrain_source.read_text(encoding="utf-8"))

    if terrain.get("status") != "PASS_DTM_CANDIDATE":
        raise RuntimeError(f"terrain upstream is not accepted: {terrain.get('status')}")
    if full["source"]["sha256"] != EXPECTED_BUILDING_SOURCE_SHA256:
        raise RuntimeError("validated building source SHA-256 drifted")
    if full["tile_summary"]["manifest_sha256"] != EXPECTED_BUILDING_MANIFEST_SHA256:
        raise RuntimeError("validated building tile manifest SHA-256 drifted")
    if not full["gate_result"]["pass"]:
        raise RuntimeError("full-Xinyi building gate is not PASS")
    if building_z.get("missing"):
        raise RuntimeError(f"missing building Z anchors: {len(building_z['missing'])}")

    terrain_tiles = terrain["output"]["terrain_tiles"]
    building_tiles = full["tiles"]
    extent = validate_tile_grid(building_tiles, terrain_tiles)

    width_m = extent["max_east_m"] - extent["min_east_m"]
    height_m = extent["max_north_m"] - extent["min_north_m"]
    expected_world = COMPONENTS_PER_AXIS * TILE_SIZE_M
    if not math.isclose(width_m, expected_world, abs_tol=1e-9):
        raise RuntimeError(f"unexpected Xinyi east-west extent: {width_m}")
    if not math.isclose(height_m, expected_world, abs_tol=1e-9):
        raise RuntimeError(f"unexpected Xinyi north-south extent: {height_m}")

    # Image columns increase eastward. Image rows increase southward so their
    # direction matches Unreal +Y under the validated UE Y = -north mapping.
    east = np.linspace(
        extent["min_east_m"], extent["max_east_m"], HEIGHTMAP_SIZE,
        dtype=np.float64,
    )
    north = np.linspace(
        extent["max_north_m"], extent["min_north_m"], HEIGHTMAP_SIZE,
        dtype=np.float64,
    )
    ee, nn = np.meshgrid(east, north)

    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    lon, lat = enu_to_lonlat(ee.ravel(), nn.ravel(), lon0, lat0)

    vertical_offset = float(terrain["vertical_alignment"]["offset_applied_m"])
    sampler = BilinearRaster(args.raster)
    try:
        heights = (
            sampler.sample_lonlat(lon, lat).reshape((HEIGHTMAP_SIZE, HEIGHTMAP_SIZE))
            + vertical_offset
        )
    finally:
        sampler.close()

    if not np.all(np.isfinite(heights)):
        raise RuntimeError("nonfinite heights in Unreal Landscape contract")

    encoded = encode_landscape_height_m(heights)
    decoded = decode_landscape_height_m(encoded)
    roundtrip_error = np.abs(decoded - heights)
    max_roundtrip_error = float(np.max(roundtrip_error))
    if max_roundtrip_error > HEIGHT_ROUNDTRIP_TOLERANCE_M:
        raise RuntimeError(
            f"Landscape uint16 roundtrip error {max_roundtrip_error:.6g} m exceeds "
            f"{HEIGHT_ROUNDTRIP_TOLERANCE_M} m"
        )

    args.out.mkdir(parents=True, exist_ok=True)
    png = args.out / "xinyi_moi2025_landscape_631.png"
    raw = args.out / "xinyi_moi2025_landscape_631.r16"
    report_path = args.out / "xinyi_unreal_v2_contract.json"
    building_path = args.out / "building_ground_ue_cm.json"
    component_path = args.out / "building_component_placement.jsonl.gz"

    Image.fromarray(encoded).save(png)
    # RAW16 fallback/import evidence; Unreal RAW16 convention is little-endian.
    raw.write_bytes(encoded.astype("<u2", copy=False).tobytes(order="C"))

    reopened = np.asarray(Image.open(png), dtype=np.uint16)
    if reopened.shape != encoded.shape or not np.array_equal(reopened, encoded):
        raise RuntimeError("16-bit PNG roundtrip changed Landscape height samples")

    tile_rows = []
    by_origin = {
        (float(x["origin_enu_m"][0]), float(x["origin_enu_m"][1])): x
        for x in building_tiles
    }
    for tx, ty in sorted(by_origin):
        row = by_origin[(tx, ty)]
        tile_rows.append({
            "tile": row["tile"],
            "building_glb": f"xinyi_v2_{row['tile']}.glb",
            "origin_enu_m": [tx, ty],
            "expected_ue_translation_cm": enu_to_ue_cm(tx, ty, 0.0),
            "building_nodes": int(row["nodes"]),
            "triangles": int(row["triangles"]),
            "sha256": row["sha256"],
        })

    ue_z = {
        bid: float(z_m) * 100.0
        for bid, z_m in sorted(building_z["offsets_m"].items())
    }
    building_payload = {
        "policy": (
            "surveyed WFS ground_elev_m mapped to Unreal world Z centimetres; "
            "apply uniformly after measuring imported mesh base"
        ),
        "mapping": "UE_Z_cm = WFS_ground_elev_m * 100",
        "count": len(ue_z),
        "missing": building_z.get("missing", []),
        "offsets_cm": ue_z,
    }
    building_path.write_text(
        json.dumps(building_payload, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )

    component_rows = build_component_placement_manifest(
        args.building_tiles_dir, tile_rows, building_z["offsets_m"]
    )
    expected_components = int(full["accounting"]["emitted_serialization_components"])
    if len(component_rows) != expected_components:
        raise RuntimeError(
            f"component placement count {len(component_rows)} != validated emitted "
            f"component count {expected_components}"
        )
    with gzip.open(component_path, "wt", encoding="utf-8", newline="\n") as fh:
        header = {
            "schema": "xinyi_unreal_v2_building_component_placement_v1",
            "count": len(component_rows),
            "coordinate_contract": (
                "expected bounds are UE world centimetres after surveyed WFS ground Z"
            ),
            "placement_rule": (
                "after validating imported StaticMesh extents, actor translation = "
                "expected UE bounds origin - imported asset bounds origin"
            ),
        }
        fh.write(json.dumps({"header": header}, separators=(",", ":"), allow_nan=False) + "\n")
        for row in component_rows:
            fh.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")

    spacing_m = TILE_SIZE_M / COMPONENT_QUADS
    scale_xy_cm = spacing_m * 100.0
    expected_min_ue = enu_to_ue_cm(
        extent["min_east_m"], extent["max_north_m"], float(np.min(decoded))
    )
    expected_max_ue = enu_to_ue_cm(
        extent["max_east_m"], extent["min_north_m"], float(np.max(decoded))
    )

    report = {
        "gate": "Unreal XinyiV2 offline input contract",
        "status": "PASS_CONTRACT",
        "upstream": {
            "building_source_sha256": full["source"]["sha256"],
            "building_manifest_sha256": full["tile_summary"]["manifest_sha256"],
            "building_tile_count": len(building_tiles),
            "terrain_status": terrain["status"],
            "terrain_tile_count": len(terrain_tiles),
            "terrain_vertical_offset_m": vertical_offset,
            "terrain_source_role": source.get("role"),
            "terrain_raster_sha256": source["output_raster"]["sha256"],
        },
        "coordinate_contract": {
            "source_world": "Xinyi ENU metres",
            "unreal_mapping": "UE X = east*100 cm; UE Y = -north*100 cm; UE Z = up*100 cm",
            "extent_enu_m": extent,
            "expected_bounds_ue_cm": {
                "min_x": expected_min_ue[0],
                "max_x": expected_max_ue[0],
                "min_y": expected_min_ue[1],
                "max_y": expected_max_ue[1],
                "terrain_min_z": expected_min_ue[2],
                "terrain_max_z": expected_max_ue[2],
            },
        },
        "landscape": {
            "heightmap_size": [HEIGHTMAP_SIZE, HEIGHTMAP_SIZE],
            "components": [COMPONENTS_PER_AXIS, COMPONENTS_PER_AXIS],
            "sections_per_component": [SECTIONS_PER_COMPONENT, SECTIONS_PER_COMPONENT],
            "section_quads": SECTION_QUADS,
            "component_quads": COMPONENT_QUADS,
            "component_size_m": TILE_SIZE_M,
            "world_size_m": [width_m, height_m],
            "sample_spacing_m": spacing_m,
            "scale_xyz": [scale_xy_cm, scale_xy_cm, LANDSCAPE_SCALE_Z],
            "topology_reason": (
                "5 components * 126 quads/component + 1 = 631 samples; "
                "each Landscape component is exactly one existing 500 m city tile"
            ),
            "source_resolution_note": (
                "MOI source is 20 m DTM. 631x631 is bilinear representation "
                "oversampling for Unreal component alignment, not increased terrain accuracy."
            ),
            "image_orientation": (
                "column 0 = west/min-east; row 0 = north/max-north; rows advance south, "
                "matching increasing Unreal +Y because UE Y = -north"
            ),
            "height_encoding": {
                "formula_encode": "uint16 = round(32768 + elevation_m*100*128/ScaleZ)",
                "formula_decode": "elevation_m = (uint16-32768)*ScaleZ/128/100",
                "scale_z": LANDSCAPE_SCALE_Z,
                "encoded_min": int(np.min(encoded)),
                "encoded_max": int(np.max(encoded)),
                "height_min_m": float(np.min(heights)),
                "height_max_m": float(np.max(heights)),
                "max_roundtrip_error_m": max_roundtrip_error,
                "tolerance_m": HEIGHT_ROUNDTRIP_TOLERANCE_M,
            },
        },
        "building_placement": {
            "policy": building_payload["policy"],
            "surveyed_z_count": len(ue_z),
            "missing": len(building_payload["missing"]),
            "manifest": building_path.name,
            "component_placement_manifest": component_path.name,
            "component_placement_count": len(component_rows),
            "component_placement_rule": (
                "validate imported extents, then translate each imported mesh actor by "
                "expected world-bounds origin minus imported asset-bounds origin"
            ),
        },
        "tiles": tile_rows,
        "outputs": {
            "heightmap_png": {
                "path": png.name,
                "sha256": sha256_file(png),
            },
            "heightmap_r16": {
                "path": raw.name,
                "sha256": sha256_file(raw),
                "byte_order": "little-endian uint16 row-major",
            },
            "building_ground_ue_cm": {
                "path": building_path.name,
                "sha256": sha256_file(building_path),
            },
            "building_component_placement": {
                "path": component_path.name,
                "sha256": sha256_file(component_path),
                "count": len(component_rows),
            },
        },
        "next_gate": (
            "Run UnrealEditor-Cmd import/build scripts; measure imported bounds and "
            "snap the Landscape/building actors to this contract; then fresh-reopen verify."
        ),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "pass": True,
        "status": report["status"],
        "heightmap": report["landscape"]["heightmap_size"],
        "components": report["landscape"]["components"],
        "component_size_m": TILE_SIZE_M,
        "scale_xyz": report["landscape"]["scale_xyz"],
        "height_min_m": report["landscape"]["height_encoding"]["height_min_m"],
        "height_max_m": report["landscape"]["height_encoding"]["height_max_m"],
        "height_roundtrip_max_error_m": max_roundtrip_error,
        "building_tiles": len(tile_rows),
        "building_z_count": len(ue_z),
        "building_component_placement_count": len(component_rows),
        "out": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
