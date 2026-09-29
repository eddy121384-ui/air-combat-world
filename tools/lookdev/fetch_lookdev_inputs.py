"""Fetch look-dev context inputs that sit *around* the validated Xinyi geometry.

Runs on a GitHub runner (network to Hugging Face / Overpass). Nothing fetched
here replaces or edits accepted building geometry:

1. Taipei-basin backdrop DTM (same MOI 2025 20 m bare-earth mirror already used
   for Xinyi terrain), downsampled to a coarse grid. Used only for the distant
   mountain ring that encloses the basin (Yangmingshan, Four Beasts, Nangang).
2. OpenStreetMap street / park / water / rail context for the Xinyi core. Used
   only for ground-surface art (asphalt, markings, sidewalks, trees).

Outputs (under data/lookdev_cache/):
- basin_dtm_mirror.npz        float32 elevation grid + EPSG:3857 bounds
- basin_dtm_mirror.json       provenance + tile hashes
- osm_xinyi_context.json.gz   raw Overpass JSON
- osm_xinyi_context.meta.json provenance + hash
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data/lookdev_cache"

HF_REPO = "yhzkiki/taiwan-dtm-2025-terrarium-z13"
HF_BASE = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main"
ZOOM = 13
TILE = 256
# Taipei basin plus the ridges that frame it from an aircraft over Xinyi.
BASIN_BBOX = (121.36, 24.93, 121.78, 25.22)  # lon0, lat0, lon1, lat1
BASIN_DOWNSAMPLE = 4  # ~76 m cells; backdrop only

# Xinyi building bbox with a small margin for streets that frame the edge.
OSM_BBOX = (25.0195, 121.5500, 25.0480, 121.5790)  # south, west, north, east
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, data: bytes | None = None, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": "air-combat-world/xinyi-lookdev"}
    )
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # network retry only
            last = exc
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_bounds_3857(x: int, y: int, z: int):
    origin = math.pi * 6378137.0
    span = 2.0 * origin / (2 ** z)
    minx = -origin + x * span
    maxy = origin - y * span
    return minx, maxy - span, minx + span, maxy


def decode_terrarium(data: bytes) -> np.ndarray:
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


def fetch_basin_dtm():
    lon0, lat0, lon1, lat1 = BASIN_BBOX
    x0f, y1f = tile_xy(lon0, lat0, ZOOM)
    x1f, y0f = tile_xy(lon1, lat1, ZOOM)
    tx0, tx1 = math.floor(x0f), math.floor(x1f)
    ty0, ty1 = math.floor(y0f), math.floor(y1f)
    rows, cols = ty1 - ty0 + 1, tx1 - tx0 + 1
    mosaic = np.zeros((rows * TILE, cols * TILE), dtype=np.float32)
    tiles = []
    for iy, ty in enumerate(range(ty0, ty1 + 1)):
        for ix, tx in enumerate(range(tx0, tx1 + 1)):
            url = f"{HF_BASE}/terrain/{ZOOM}/{tx}/{ty}.png"
            try:
                data = fetch(url)
                z = decode_terrarium(data).astype(np.float32)
                digest = sha256_bytes(data)
            except RuntimeError:
                # Offshore / out-of-coverage tiles are absent from the mirror.
                z = np.zeros((TILE, TILE), dtype=np.float32)
                digest = None
            mosaic[iy * TILE:(iy + 1) * TILE, ix * TILE:(ix + 1) * TILE] = z
            tiles.append({"x": tx, "y": ty, "sha256": digest})
    k = BASIN_DOWNSAMPLE
    h, w = mosaic.shape
    coarse = mosaic[: h // k * k, : w // k * k].reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    west, _, _, north = tile_bounds_3857(tx0, ty0, ZOOM)
    _, south, east, _ = tile_bounds_3857(tx1, ty1, ZOOM)
    np.savez_compressed(
        OUT / "basin_dtm_mirror.npz",
        elevation_m=coarse.astype(np.float32),
        bounds_3857=np.array([west, south, east, north], dtype=np.float64),
    )
    meta = {
        "role": "LOOKDEV_BACKDROP_ONLY",
        "source": f"https://huggingface.co/datasets/{HF_REPO}",
        "official_dataset": "2025年版全臺灣20公尺網格數值地形模型DTM資料 (data.gov.tw/dataset/176927)",
        "license": "政府資料開放授權條款-第1版",
        "bbox_wgs84": BASIN_BBOX,
        "zoom": ZOOM,
        "downsample": k,
        "shape": list(coarse.shape),
        "bounds_3857": [west, south, east, north],
        "elevation_range_m": [float(coarse.min()), float(coarse.max())],
        "tiles": tiles,
        "note": "Distant backdrop terrain only. Xinyi playable terrain stays on the accepted contract.",
    }
    (OUT / "basin_dtm_mirror.json").write_text(json.dumps(meta, indent=1) + "\n")
    return meta


def fetch_osm():
    s, w, n, e = OSM_BBOX
    bbox = f"{s},{w},{n},{e}"
    query = f"""
[out:json][timeout:120];
(
  way["highway"]({bbox});
  way["railway"]({bbox});
  way["leisure"~"park|garden|pitch|playground"]({bbox});
  way["landuse"~"grass|forest|park|recreation_ground|cemetery"]({bbox});
  way["natural"~"wood|water|scrub"]({bbox});
  way["waterway"]({bbox});
  relation["leisure"="park"]({bbox});
  relation["landuse"~"forest|grass"]({bbox});
  node["natural"="tree"]({bbox});
);
out body geom;
"""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for url in OVERPASS:
        try:
            raw = fetch(url, data=body, timeout=240)
            json.loads(raw)
            break
        except Exception as exc:
            last = exc
            raw = None
    if raw is None:
        raise RuntimeError(f"all overpass endpoints failed: {last}")
    gz = gzip.compress(raw, mtime=0)
    (OUT / "osm_xinyi_context.json.gz").write_bytes(gz)
    elements = json.loads(raw)["elements"]
    meta = {
        "role": "LOOKDEV_GROUND_CONTEXT_ONLY",
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0 — © OpenStreetMap contributors",
        "bbox_swne": list(OSM_BBOX),
        "element_count": len(elements),
        "raw_sha256": sha256_bytes(raw),
        "note": "Used only for ground-surface art. Building geometry stays on the WFS contract.",
    }
    (OUT / "osm_xinyi_context.meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    basin = fetch_basin_dtm()
    osm = fetch_osm()
    print(json.dumps({"basin_shape": basin["shape"], "basin_range": basin["elevation_range_m"],
                      "osm_elements": osm["element_count"]}))


if __name__ == "__main__":
    main()
