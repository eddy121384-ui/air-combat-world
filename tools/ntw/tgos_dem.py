"""Reader for the OFFICIAL MOI 2025 20 m DEM sheet packages (TGOS, data.gov.tw dataset 176927).

Package = ZIP of 1/5000 sheets: `<no>dem.grd` (text "E N H" per node, EPSG:3826 TWD97[2020], TWVD2001 metres, 20 m nodes on
multiples of 20 m) + `<no>dem.hdr` (name, number, datums, scale, dx, dy, points, cols, rows, SW E, SW N, ..., source, sensor,
..., max, min, mean, survey date, agency, production date, producer). There is NO nodata sentinel: missing data = absent nodes.

`Dem.mosaic(bbox)` returns heights on the exact 20 m node grid (NaN = absent), a sheet-index raster for provenance, and
cross-sheet duplicate statistics (nodes present in several sheets must agree).
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/generated/ntw/tgos"
STEP = 20.0


@dataclass
class Sheet:
    package: str
    number: str
    name: str
    sw: tuple[float, float]
    cols: int
    rows: int
    points: int
    survey_date: str | None
    production_date: str | None
    source: str | None

    @property
    def bbox(self):
        return (self.sw[0], self.sw[1], self.sw[0] + (self.cols - 1) * STEP, self.sw[1] + (self.rows - 1) * STEP)


def _decode(b):
    for enc in ("utf-8-sig", "cp950", "big5"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("latin1")


class Dem:
    def __init__(self, packages=None, cache_dir=None):
        zips = sorted(Path(cache_dir or CACHE).glob("*20MDEM(2025).zip"))
        if packages:
            zips = [z for z in zips if any(p in z.name for p in packages)]
        self.zips = {z.name: zipfile.ZipFile(z) for z in zips}
        self.sheets: list[Sheet] = []
        for zn, zf in self.zips.items():
            for n in zf.namelist():
                if not n.endswith("dem.hdr"):
                    continue
                L = [s.strip() for s in _decode(zf.read(n)).splitlines()]
                try:
                    sh = Sheet(package=zn, number=L[1], name=L[0], sw=(float(L[10]), float(L[11])), cols=int(L[8]),
                               rows=int(L[9]), points=int(L[7]), source=L[13] if len(L) > 13 else None,
                               survey_date=L[19] if len(L) > 19 else None, production_date=L[21] if len(L) > 21 else None)
                except (ValueError, IndexError):
                    continue
                if float(L[5]) != STEP or float(L[6]) != STEP:
                    raise ValueError(f"unexpected spacing in {zn}:{n}")
                self.sheets.append(sh)

    def close(self):
        for zf in self.zips.values():
            zf.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def sheets_in(self, bbox):
        x0, y0, x1, y1 = bbox
        return [s for s in self.sheets if not (s.bbox[2] < x0 or s.bbox[0] > x1 or s.bbox[3] < y0 or s.bbox[1] > y1)]

    def mosaic(self, bbox):
        """Heights on nodes x = x0 + i*20 (i = 0..nx-1), y = y0 + j*20 (j = 0..ny-1), row j = south->north."""
        x0, y0, x1, y1 = bbox
        for v in bbox:
            if abs(v / STEP - round(v / STEP)) > 1e-9:
                raise ValueError("bbox must be on the 20 m node grid")
        nx, ny = int(round((x1 - x0) / STEP)) + 1, int(round((y1 - y0) / STEP)) + 1
        z = np.full((ny, nx), np.nan)
        src = np.full((ny, nx), -1, dtype=np.int32)
        sheets = self.sheets_in(bbox)
        dup_n, dup_max = 0, 0.0
        for k, s in enumerate(sheets):
            a = np.loadtxt(io.BytesIO(self.zips[s.package].read(f"{s.number}dem.grd")), ndmin=2)
            ix = np.rint((a[:, 0] - x0) / STEP).astype(np.int64)
            iy = np.rint((a[:, 1] - y0) / STEP).astype(np.int64)
            m = (ix >= 0) & (iy >= 0) & (ix < nx) & (iy < ny)
            ix, iy, h = ix[m], iy[m], a[m, 2]
            prev = z[iy, ix]
            seen = ~np.isnan(prev)
            if seen.any():
                dup_n += int(seen.sum())
                dup_max = max(dup_max, float(np.max(np.abs(prev[seen] - h[seen]))))
            z[iy, ix] = np.where(seen, prev, h)  # first sheet wins; disagreement is reported, never averaged
            src[iy, ix] = np.where(seen, src[iy, ix], k)
        return z, src, sheets, {"duplicate_nodes": dup_n, "duplicate_max_abs_diff_m": dup_max}
