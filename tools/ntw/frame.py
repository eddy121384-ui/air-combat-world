"""NTW world frame: EPSG:3826 (TWD97 / TM2 zone 121) minus a fixed, grid-aligned origin.

x = east (m), y = north-grid (m), z = up (m, TWVD2001 orthometric, same as MOI DTM / WFS).
The origin is a multiple of the coarsest (32 km) hierarchy cell so every level nests exactly.
Xinyi's accepted ENU frame is NOT redefined here; see docs for the Xinyi<->NTW rigid transform.
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer

NTW_ORIGIN_TM2 = (224000.0, 2688000.0)  # 224000 = 7*32000, 2688000 = 84*32000
LEVEL_CELL_M = {"L0": 32000.0, "L1": 8000.0, "L2": 500.0}  # L2 == existing Xinyi tile size
_to_tm2 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
_to_ll = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)


def lonlat_to_ntw(lon, lat):
    e, n = _to_tm2.transform(lon, lat)
    return np.asarray(e) - NTW_ORIGIN_TM2[0], np.asarray(n) - NTW_ORIGIN_TM2[1]


def ntw_to_lonlat(x, y):
    return _to_ll.transform(np.asarray(x) + NTW_ORIGIN_TM2[0], np.asarray(y) + NTW_ORIGIN_TM2[1])


def tm2_to_ntw(e, n):
    return np.asarray(e) - NTW_ORIGIN_TM2[0], np.asarray(n) - NTW_ORIGIN_TM2[1]


def cell_index(x, y, size_m):
    """Deterministic owner cell: floor of the source-part centroid (same rule as Xinyi tile_origin)."""
    return np.floor(np.asarray(x) / size_m).astype(np.int64), np.floor(np.asarray(y) / size_m).astype(np.int64)


def cell_key(ix, iy):
    return f"{int(ix):+04d}_{int(iy):+04d}"
