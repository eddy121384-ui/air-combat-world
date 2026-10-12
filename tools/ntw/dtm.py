"""MOI 2025 20 m DTM (Terrarium z13 mirror) bilinear sampler for NTW survey/pilot work.

Same transport and decode as tools/terrain/fetch_moi_2025_dtm_mirror.py (accepted for Xinyi):
R*256 + G + B/256 - 32768, Web-Mercator XYZ z13. Tiles are cached under data/generated/ntw/dtm/tiles.
Heights are TWVD2001 orthometric metres. NODATA (sea) decodes to < -1000 and is returned as NaN.
"""
from __future__ import annotations

import hashlib
import io
import math
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/generated/ntw/dtm/tiles"
BASE = "https://huggingface.co/datasets/yhzkiki/taiwan-dtm-2025-terrarium-z13/resolve/main/terrain/13"
Z = 13


class Dtm:
    def __init__(self):
        self._tiles: dict[tuple[int, int], np.ndarray] = {}
        self.tile_sha256: dict[str, str] = {}

    def _tile(self, x, y):
        key = (x, y)
        if key in self._tiles:
            return self._tiles[key]
        f = CACHE / f"{x}_{y}.png"
        if not f.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(f"{BASE}/{x}/{y}.png", headers={"User-Agent": "air-combat-world/ntw"})
            with urllib.request.urlopen(req, timeout=120) as r:
                f.write_bytes(r.read())
        raw = f.read_bytes()
        self.tile_sha256[f"{x}/{y}"] = hashlib.sha256(raw).hexdigest()
        rgb = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.float64)
        z = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0
        z[z < -1000] = np.nan
        self._tiles[key] = z
        return z

    @staticmethod
    def _pixel(lon, lat):
        n = 2.0 ** Z * 256.0
        px = (lon + 180.0) / 360.0 * n
        py = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
        return px, py

    def _at(self, ix, iy):
        return self._tile(ix // 256, iy // 256)[iy % 256, ix % 256]

    def sample(self, lon, lat):
        """Bilinear sample (pixel centres at +0.5). Returns NaN if any neighbour is NODATA."""
        px, py = self._pixel(lon, lat)
        fx, fy = px - 0.5, py - 0.5
        x0, y0 = math.floor(fx), math.floor(fy)
        tx, ty = fx - x0, fy - y0
        v00, v10 = self._at(x0, y0), self._at(x0 + 1, y0)
        v01, v11 = self._at(x0, y0 + 1), self._at(x0 + 1, y0 + 1)
        return (v00 * (1 - tx) * (1 - ty) + v10 * tx * (1 - ty) + v01 * (1 - tx) * ty + v11 * tx * ty)
