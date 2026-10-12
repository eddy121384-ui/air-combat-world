"""World bounds specification for Skyfront theaters. Map size is DATA, never a global constant.

A world is an axis-aligned rectangle in EPSG:3826 (TWD97 / TM2) metres whose corners sit on the world grid
(`cell_m`, default 8 km = the L1 cell of tools/ntw/frame.py). Everything that depends on a map size (bounds,
cell list, runtime origin, UE extents) is derived from a spec file in `worlds/*.json`, so a 160 km, 224 km or
288 km map are the same code path.

Invariants checked by `WorldSpec.validate()`:
  * size_x_m, size_y_m are positive multiples of cell_m
  * the SW corner is a multiple of cell_m in absolute EPSG:3826 (so cells of every world coincide)
  * cell_m is a multiple of the 500 m L2 tile, so L2 tiles never straddle a world cell
  * the NTW storage frame origin (frame.NTW_ORIGIN_TM2) is itself on the grid, so tile keys are
    world-independent: changing the map size never renames a tile.

Runtime (engine) origin = world centre snapped to the grid. UE axes follow the accepted Xinyi contract:
UE X = east * 100 cm, UE Y = -north * 100 cm, UE Z = up * 100 cm.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import frame

L2_TILE_M = 500.0


@dataclass(frozen=True)
class WorldSpec:
    name: str
    sw_tm2: tuple[float, float]
    size_m: tuple[float, float]
    cell_m: float = 8000.0
    notes: dict = field(default_factory=dict, compare=False, hash=False)

    # ---- construction -------------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "WorldSpec":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        s = cls(name=d["name"], sw_tm2=tuple(map(float, d["sw_corner_epsg3826"])),
                size_m=(float(d["size_km"][0]) * 1000.0, float(d["size_km"][1]) * 1000.0),
                cell_m=float(d.get("cell_km", 8)) * 1000.0, notes=d.get("notes", {}))
        s.validate()
        return s

    @classmethod
    def centred(cls, name, centre_tm2, size_km, cell_km=8.0):
        """Snap a requested centre to the grid (useful for trying other map sizes)."""
        c = cell_km * 1000.0
        sx, sy = size_km[0] * 1000.0, size_km[1] * 1000.0
        x0 = round((centre_tm2[0] - sx / 2) / c) * c
        y0 = round((centre_tm2[1] - sy / 2) / c) * c
        s = cls(name=name, sw_tm2=(x0, y0), size_m=(sx, sy), cell_m=c)
        s.validate()
        return s

    def validate(self):
        c = self.cell_m
        errs = []
        for v, lab in ((self.size_m[0], "size_x"), (self.size_m[1], "size_y")):
            if v <= 0 or abs(v / c - round(v / c)) > 1e-9:
                errs.append(f"{lab}={v} not a positive multiple of cell {c}")
        for v, lab in ((self.sw_tm2[0], "sw_x"), (self.sw_tm2[1], "sw_y")):
            if abs(v / c - round(v / c)) > 1e-9:
                errs.append(f"{lab}={v} not on the {c} m grid")
        if abs(c / L2_TILE_M - round(c / L2_TILE_M)) > 1e-9:
            errs.append(f"cell {c} not a multiple of the {L2_TILE_M} m L2 tile")
        for v in frame.NTW_ORIGIN_TM2:
            if abs(v / c - round(v / c)) > 1e-9:
                errs.append(f"NTW storage origin {frame.NTW_ORIGIN_TM2} not on the {c} m grid")
        if errs:
            raise ValueError("; ".join(errs))

    # ---- derived geometry ---------------------------------------------------------------------
    @property
    def bounds_tm2(self):
        x0, y0 = self.sw_tm2
        return (x0, y0, x0 + self.size_m[0], y0 + self.size_m[1])

    @property
    def cells_xy(self):
        return int(round(self.size_m[0] / self.cell_m)), int(round(self.size_m[1] / self.cell_m))

    @property
    def runtime_origin_tm2(self):
        x0, y0, x1, y1 = self.bounds_tm2
        c = self.cell_m
        return (math.floor((x0 + x1) / 2 / c) * c, math.floor((y0 + y1) / 2 / c) * c)

    def cell_index_abs(self, x_tm2, y_tm2):
        """Absolute grid index (EPSG:3826 / cell). World-independent."""
        return math.floor(x_tm2 / self.cell_m), math.floor(y_tm2 / self.cell_m)

    def cells(self):
        """Yield (col, row, abs_ix, abs_iy, (x0,y0,x1,y1)) for every world cell, SW -> NE, row-major."""
        nx, ny = self.cells_xy
        ax0, ay0 = self.cell_index_abs(*self.sw_tm2)
        c = self.cell_m
        for row in range(ny):
            for col in range(nx):
                x0, y0 = (ax0 + col) * c, (ay0 + row) * c
                yield col, row, ax0 + col, ay0 + row, (x0, y0, x0 + c, y0 + c)

    def cell_id(self, abs_ix, abs_iy):
        """Stable cell id from ABSOLUTE indices (same id in every world that contains the cell)."""
        return f"C{int(abs_ix):+05d}{int(abs_iy):+05d}"

    def tm2_to_ue_cm(self, x, y, z=0.0):
        ox, oy = self.runtime_origin_tm2
        return ((x - ox) * 100.0, -(y - oy) * 100.0, z * 100.0)

    def contains(self, x, y, margin_m=0.0):
        x0, y0, x1, y1 = self.bounds_tm2
        return x0 + margin_m <= x <= x1 - margin_m and y0 + margin_m <= y <= y1 - margin_m

    def summary(self):
        x0, y0, x1, y1 = self.bounds_tm2
        ox, oy = self.runtime_origin_tm2
        nx, ny = self.cells_xy
        return {
            "name": self.name, "size_km": [self.size_m[0] / 1000, self.size_m[1] / 1000], "cell_km": self.cell_m / 1000,
            "cells": [nx, ny], "cell_count": nx * ny, "l2_tiles_per_cell": int((self.cell_m / L2_TILE_M) ** 2),
            "bounds_epsg3826": [x0, y0, x1, y1], "runtime_origin_epsg3826": [ox, oy],
            "bounds_ntw_frame": [x0 - frame.NTW_ORIGIN_TM2[0], y0 - frame.NTW_ORIGIN_TM2[1],
                                 x1 - frame.NTW_ORIGIN_TM2[0], y1 - frame.NTW_ORIGIN_TM2[1]],
            "ue_extent_cm": {"x": [(x0 - ox) * 100, (x1 - ox) * 100], "y": [-(y1 - oy) * 100, -(y0 - oy) * 100]},
            "max_abs_ue_coordinate_km": max(abs(x0 - ox), abs(x1 - ox), abs(y0 - oy), abs(y1 - oy)) / 1000,
        }
