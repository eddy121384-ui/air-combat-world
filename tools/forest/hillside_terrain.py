"""Hillside forest look-dev v1: Xiangshan (象山) test terrain from the repo's MOI 2025 20 m DTM derivative mirror.

Source: data/lookdev_cache/moi_2025_dtm_xinyi_mirror.tif (EPSG:3857, z13 Terrarium decode of the official MOI 2025 bare-earth
20 m DTM, data.gov.tw/dataset/176927; see docs/xinyi-terrain-v0-dtm-result.md). LOOK-DEV ONLY: no Xinyi / North Taiwan
production terrain is read or written, and the grid here is not the Xinyi ENU / 500 m tile contract.

Method: a local EPSG:3826 grid centred on CENTER_WGS84, 2 m spacing, 505 x 505 samples (1008 m, 8 x 8 Landscape components of
63 quads), bicubic (scipy map_coordinates order 3) from the ~17 m mirror pixels. The 20 m source cannot carry sub-20 m relief
(rock outcrops, trail cuts, the 六巨石): the surface is a smooth real-terrain envelope, not a survey-grade 2 m DEM.

Writes <out>/terrain.r16 (little-endian uint16, row 0 = north), <out>/terrain.json (grid / Landscape contract + hashes),
<out>/terrain_height.npy (float32 metres, same grid) and <out>/terrain_hillshade.png.

    python tools/forest/hillside_terrain.py <out_dir>
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import map_coordinates

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "data/lookdev_cache/moi_2025_dtm_xinyi_mirror.tif"
CENTER_WGS84 = (121.5752, 25.0268)  # lon, lat: north-west flank of 象山, the peak (~183 m) sits near the south-east corner of the forest block
SPACING_M = 2.0
SIZE = 505  # 8 components x 63 quads + 1
SCALE_Z = 100.0  # UE landscape scale Z: 1 raw unit = SCALE_Z / 128 cm = 7.8 mm, range +-256 m around H_REF
SOURCE_ALIGN_M = 0.341955  # the single global vertical offset accepted in docs/xinyi-terrain-v0-dtm-result.md


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    to3826 = Transformer.from_crs(4326, 3826, always_xy=True)
    to3857 = Transformer.from_crs(3826, 3857, always_xy=True)
    cx, cy = to3826.transform(*CENTER_WGS84)
    half = (SIZE - 1) * SPACING_M / 2.0
    e = cx + np.linspace(-half, half, SIZE)
    n = cy + np.linspace(half, -half, SIZE)  # row 0 = north
    E, N = np.meshgrid(e, n)
    X, Y = to3857.transform(E, N)
    with rasterio.open(SRC) as ds:
        a = ds.read(1).astype(np.float64)
        inv = ~ds.transform
        col, row = inv * (X, Y)
    # pixel centres are at +0.5
    h = map_coordinates(a, [row - 0.5, col - 0.5], order=3, mode="nearest") + SOURCE_ALIGN_M
    h_ref = float(np.round((h.min() + h.max()) / 2.0))
    raw_f = 32768.0 + (h - h_ref) * 128.0 * (100.0 / SCALE_Z)
    if raw_f.min() < 0 or raw_f.max() > 65535:
        raise SystemExit("height range does not fit uint16 at SCALE_Z=%s" % SCALE_Z)
    raw = np.round(raw_f).astype("<u2")
    raw.tofile(out / "terrain.r16")
    # height the Landscape will actually reproduce (quantised), used by every downstream tool
    hq = ((raw.astype(np.float64) - 32768.0) / 128.0 * (SCALE_Z / 100.0) + h_ref).astype(np.float32)
    np.save(out / "terrain_height.npy", hq)
    # hillshade (sun from NW 315 deg, 45 deg) for the document
    gy, gx = np.gradient(hq.astype(np.float64), SPACING_M)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315.0), np.radians(45.0)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    Image.fromarray(np.clip(hs * 255, 0, 255).astype(np.uint8)).save(out / "terrain_hillshade.png")
    meta = {
        "role": "LOOKDEV_TEST_TERRAIN_REAL_DTM",
        "label": "Xiangshan (象山) north-west flank, MOI 2025 20 m DTM derivative mirror, bicubic to 2 m",
        "source": {"path": str(SRC.relative_to(REPO)).replace("\\", "/"), "sha256": sha256(SRC),
                   "official_dataset": "2025年版全臺灣20公尺網格數值地形模型DTM資料 (data.gov.tw/dataset/176927)",
                   "vertical_alignment_m": SOURCE_ALIGN_M},
        "crs": "EPSG:3826", "center_wgs84": list(CENTER_WGS84), "center_3826": [cx, cy],
        "spacing_m": SPACING_M, "size": [SIZE, SIZE], "extent_m": (SIZE - 1) * SPACING_M,
        "landscape": {"components": [8, 8], "num_subsections": 1, "subsection_quads": 63,
                      "scale_xyz": [SPACING_M * 100.0, SPACING_M * 100.0, SCALE_Z],
                      "location_cm": [-half * 100.0, -half * 100.0, 0.0],
                      "z_rule": "world_z_m = (raw - 32768) / 128 * scale_z / 100 + h_ref_m - h_ref_m  (Landscape at Z=0, so UE Z = height - h_ref)",
                      "h_ref_m": h_ref},
        "ue_frame": "UE X = east (m*100), UE Y = south (= -north), UE Z = height - h_ref; origin = grid centre",
        "height_m": {"min": float(hq.min()), "max": float(hq.max()), "mean": float(hq.mean())},
        "slope_deg": {"mean": float(np.degrees(slope).mean()), "p90": float(np.percentile(np.degrees(slope), 90)),
                      "max": float(np.degrees(slope).max())},
        "limitations": ["20 m source resolution: no relief below ~20 m (rocks, trail cuts, retaining walls, buildings)",
                        "bare-earth DTM: no canopy height model, so tree heights are not from data"],
        "outputs": {"terrain.r16": sha256(out / "terrain.r16"), "terrain_height.npy": sha256(out / "terrain_height.npy")},
    }
    (out / "terrain.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("height_m", "slope_deg", "center_3826")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
