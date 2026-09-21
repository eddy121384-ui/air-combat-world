"""Fetch Xinyi coverage from a cloud-readable mirror of the official 2025 MOI 20 m DTM.

The mirror is yhzkiki/taiwan-dtm-2025-terrarium-z13 on Hugging Face. It is a
format conversion of the official MOI 2025 20 m bare-earth DTM, not an alternate
terrain product. We keep the mirror provenance + downloaded file hashes and do
not pretend the mirror is the original TGOS transport.
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_bounds
from shapely.geometry import shape

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
OUT = REPO / "data/generated/taipei/terrain"
CACHE = OUT / "cache"
RASTER = CACHE / "moi_2025_dtm_xinyi_mirror.tif"
MANIFEST = OUT / "moi_2025_dtm_mirror_source.json"

HF_REPO = "yhzkiki/taiwan-dtm-2025-terrarium-z13"
HF_BASE = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main"
ZOOM = 13
TILE_SIZE = 256


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_bytes(url: str) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "air-combat-world/xinyi-terrain-v0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
        headers = {k.lower(): v for k, v in r.headers.items()}
        return data, headers


def tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_bounds_3857(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    origin = math.pi * 6378137.0
    span = 2.0 * origin / (2 ** z)
    minx = -origin + x * span
    maxx = minx + span
    maxy = origin - y * span
    miny = maxy - span
    return minx, miny, maxx, maxy


def decode_terrarium(data: bytes) -> np.ndarray:
    import io
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

fc = json.loads(SOURCE.read_text(encoding="utf-8"))
to4326 = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)

xs, ys = [], []
for feature in fc["features"]:
    geom = shape(feature["geometry"])
    if geom.is_empty:
        continue
    minx, miny, maxx, maxy = geom.bounds
    xs += [minx, maxx]
    ys += [miny, maxy]

lon0, lat0 = to4326.transform(min(xs), min(ys))
lon1, lat1 = to4326.transform(max(xs), max(ys))
min_lon, max_lon = sorted([lon0, lon1])
min_lat, max_lat = sorted([lat0, lat1])

# One source-pixel/tile safety pad is excessive but cheap at z13 and guarantees
# bilinear samples near our requested world edge have neighbours.
tx0f, ty1f = tile_xy(min_lon, min_lat, ZOOM)
tx1f, ty0f = tile_xy(max_lon, max_lat, ZOOM)
tx0 = math.floor(min(tx0f, tx1f)) - 1
tx1 = math.floor(max(tx0f, tx1f)) + 1
ty0 = math.floor(min(ty0f, ty1f)) - 1
ty1 = math.floor(max(ty0f, ty1f)) + 1

source_meta = {}
for name in ("source-manifest.json", "build-summary.json", "validation-samples.csv"):
    try:
        data, headers = fetch_bytes(f"{HF_BASE}/{name}")
        source_meta[name] = {
            "url": f"{HF_BASE}/{name}",
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "content_type": headers.get("content-type"),
            "x_repo_commit": headers.get("x-repo-commit"),
        }
        (CACHE / f"moi2025_mirror_{name.replace('/', '_')}").write_bytes(data)
    except Exception as exc:
        source_meta[name] = {"error": f"{type(exc).__name__}: {exc}"}

rows = ty1 - ty0 + 1
cols = tx1 - tx0 + 1
mosaic = np.empty((rows * TILE_SIZE, cols * TILE_SIZE), dtype=np.float32)
tiles = []

for iy, ty in enumerate(range(ty0, ty1 + 1)):
    for ix, tx in enumerate(range(tx0, tx1 + 1)):
        url = f"{HF_BASE}/terrain/{ZOOM}/{tx}/{ty}.png"
        data, headers = fetch_bytes(url)
        z = decode_terrarium(data).astype(np.float32)
        if z.shape != (TILE_SIZE, TILE_SIZE):
            raise RuntimeError(f"unexpected tile shape {tx}/{ty}: {z.shape}")
        mosaic[iy*TILE_SIZE:(iy+1)*TILE_SIZE, ix*TILE_SIZE:(ix+1)*TILE_SIZE] = z
        tiles.append({
            "z": ZOOM,
            "x": tx,
            "y": ty,
            "url": url,
            "bytes": len(data),
            "sha256": sha256_bytes(data),
            "elevation_min_m": float(np.min(z)),
            "elevation_max_m": float(np.max(z)),
            "x_repo_commit": headers.get("x-repo-commit"),
        })

west, south0, _, north = tile_bounds_3857(tx0, ty0, ZOOM)
_, south, east, _ = tile_bounds_3857(tx1, ty1, ZOOM)
transform = from_bounds(west, south, east, north, mosaic.shape[1], mosaic.shape[0])

with rasterio.open(
    RASTER,
    "w",
    driver="GTiff",
    width=mosaic.shape[1],
    height=mosaic.shape[0],
    count=1,
    dtype="float32",
    crs="EPSG:3857",
    transform=transform,
    nodata=None,
    compress="deflate",
) as ds:
    ds.write(mosaic, 1)

h = hashlib.sha256()
with RASTER.open("rb") as fh:
    for block in iter(lambda: fh.read(1024 * 1024), b""):
        h.update(block)

repo_commits = sorted({t["x_repo_commit"] for t in tiles if t.get("x_repo_commit")})
manifest = {
    "role": "OFFICIAL_MOI_2025_DTM_DERIVATIVE_MIRROR_CANDIDATE",
    "official_dataset": {
        "title": "2025年版全臺灣20公尺網格數值地形模型DTM資料",
        "data_gov_url": "https://data.gov.tw/dataset/176927",
        "semantics": "bare-earth 20 m DTM",
        "license": "政府資料開放授權條款-第1版",
        "mainland_source_crs": "EPSG:3826",
    },
    "mirror": {
        "repository": HF_REPO,
        "dataset_card": f"https://huggingface.co/datasets/{HF_REPO}",
        "format": "Terrarium RGB XYZ z13",
        "decode": "R*256 + G + B/256 - 32768",
        "repo_commits_from_headers": repo_commits,
        "metadata_files": source_meta,
    },
    "xinyi_source_bbox_wgs84": [min_lon, min_lat, max_lon, max_lat],
    "tile_range": {"z": ZOOM, "x": [tx0, tx1], "y": [ty0, ty1]},
    "tiles": tiles,
    "output_raster": {
        "path": str(RASTER.relative_to(REPO)),
        "crs": "EPSG:3857",
        "width": mosaic.shape[1],
        "height": mosaic.shape[0],
        "elevation_min_m": float(np.min(mosaic)),
        "elevation_max_m": float(np.max(mosaic)),
        "sha256": h.hexdigest(),
    },
    "acceptance_note": (
        "This is a cloud-readable derivative of the official MOI 2025 bare-earth DTM. "
        "Production acceptance still requires cross-checking against WFS surveyed ground "
        "elevations and preserving the mirror source manifest / hashes."
    ),
}
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({
    "pass": True,
    "role": manifest["role"],
    "tile_range": manifest["tile_range"],
    "tile_count": len(tiles),
    "repo_commits": repo_commits,
    "raster": manifest["output_raster"],
    "metadata": source_meta,
}, ensure_ascii=False, indent=2))
