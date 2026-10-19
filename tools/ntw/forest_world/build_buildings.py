"""North Taiwan forest world v1 - town / city massing from Overture building records (offline, deterministic; run with the acw-ntw venv).

Why: the Esri "built" class covers ~30 % of the region's land (Beitou, Shilin, Tianmu, Tamsui, Sanzhi, Jinshan, Wanli and the hill
villages). Painted as Landscape texture it read as a tiled floor. Overture's local world bands (data/generated/ntw/world/ovt_world_band2/3
of the NTW worktree: centroid, footprint area, height / floors when known) give every building's position and size, so towns become
cheap box massing (one HISM cube per building, WP-streamed per 1 km tile) plus a roof raster for beyond the box cull distance.

NOT production city geometry: footprint shape and orientation are not used (only centroid + area): boxes are square-ish (aspect from a
seeded draw), oriented along the slope contour on hills / to a smooth neighbourhood angle on flat land; heights = Overture height,
else floors x 3.2 m, else a seeded draw by footprint size (small houses 2-4 floors, large footprints 3-8). Underground records skipped.
Taipei / Xinyi production geometry is untouched (none of it is in this region).

Outputs (into the region run dir): buildings/tile_<ix>_<iy>.bin (float64 x,y,z,yaw,sx,sy,sz per box, UE cm / deg / m-scale of the 1 m
engine cube), buildings.json (index + stats), T_NF_Roofs.png (4096^2, R = roof cover, G = height / 40 m).
    <acw-ntw python> tools/ntw/forest_world/build_buildings.py --run data/generated/ntw/forest_world/v1 --world-dir <ntw>/data/generated/ntw/world
"""
import argparse
import json
import struct
from pathlib import Path

import duckdb
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy import ndimage

E0, N0, EXT, SP = 289_540.0, 2_773_540.0, 26_460.0, 10.0
N1 = N0 + EXT
ORIGIN = (296_000.0, 2_760_000.0)
TILE_M = 1000.0
ROOF_PX = 4096
SEED = 20261019


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--world-dir", required=True)
    a = ap.parse_args()
    run, wd = Path(a.run), Path(a.world_dir)
    rows = []
    for b in (2, 3):
        f = (wd / f"ovt_world_band{b}.parquet").as_posix()
        rows += duckdb.sql(f"select cx, cy, area_m2, height, num_floors, coalesce(is_underground, false) from read_parquet('{f}') "
                           f"where cx between 121.38 and 121.74 and cy between 25.04 and 25.32").fetchall()
    arr = np.array([(r[0], r[1], r[2] or 0.0, r[3] if r[3] is not None else np.nan, r[4] if r[4] is not None else np.nan, float(r[5])) for r in rows])
    e, n = Transformer.from_crs(4326, 3826, always_xy=True).transform(arr[:, 0], arr[:, 1])
    keep = (e > E0 + 5) & (e < N1 - N0 + E0 - 5) & (n > N0 + 5) & (n < N1 - 5) & (arr[:, 5] == 0) & (arr[:, 2] >= 12)
    e, n, area, hgt, flo = e[keep], n[keep], arr[keep, 2], arr[keep, 3], arr[keep, 4]
    rng = np.random.default_rng(SEED)
    h = np.load(run / "height_q.npy").astype(np.float64)
    col, row = (e - E0) / SP, (N1 - n) / SP
    z = ndimage.map_coordinates(h, [row, col], order=1, mode="nearest")
    sea = z < 0.3
    e, n, area, hgt, flo, col, row, z = e[~sea], n[~sea], area[~sea], hgt[~sea], flo[~sea], col[~sea], row[~sea], z[~sea]
    cnt = len(e)
    # footprint: square-ish box with the record's area
    asp = np.exp(rng.normal(0, 0.28, cnt))
    side = np.sqrt(np.minimum(area, 6000.0))
    sx, sy = side * np.sqrt(asp), side / np.sqrt(asp)
    # height
    floors = np.where(np.isfinite(flo), flo, np.where(area < 90, rng.integers(2, 5, cnt), np.where(area < 400, rng.integers(3, 7, cnt), rng.integers(3, 9, cnt))))
    height = np.where(np.isfinite(hgt) & (hgt > 2), hgt, floors * 3.2 + rng.uniform(0.0, 1.5, cnt))
    height = np.clip(height, 3.0, 120.0)
    # orientation: slope contour on hills, a smooth neighbourhood angle elsewhere
    gy, gx = np.gradient(ndimage.gaussian_filter(h, 3.0), SP)
    slope = np.hypot(gx, gy)
    aspect = np.degrees(np.arctan2(gy, gx))   # in image (col, row) space; row axis = south = UE +Y, col = east = UE +X
    ang_field = ndimage.zoom(rng.uniform(0, 90, (12, 12)), h.shape[0] / 12.0, order=1)[: h.shape[0], : h.shape[1]]
    s_at = ndimage.map_coordinates(slope, [row, col], order=1)
    yaw = np.where(s_at > 0.08, ndimage.map_coordinates(aspect, [row, col], order=1) + 90.0,
                   ndimage.map_coordinates(ang_field, [row, col], order=1)) + rng.normal(0, 6, cnt)
    # ground: lowest Landscape height under the box corners, base sunk 3 m (slopes)
    r = side / 2.0 / SP
    zc = np.min([ndimage.map_coordinates(h, [row + dy * r, col + dx * r], order=1, mode="nearest") for dx in (-1, 1) for dy in (-1, 1)], axis=0)
    zb = np.minimum(zc, z) - 3.0
    top = z + height
    rec = np.stack([(e - ORIGIN[0]) * 100.0, -(n - ORIGIN[1]) * 100.0, (zb + top) / 2.0 * 100.0, yaw, sx, sy, top - zb], 1)
    bd = run / "buildings"
    bd.mkdir(exist_ok=True)
    tx, ty = ((e - E0) // TILE_M).astype(int), ((N1 - n) // TILE_M).astype(int)
    index = []
    for key in np.unique(ty * 100 + tx):
        m = (ty * 100 + tx) == key
        name = "tile_%02d_%02d.bin" % (key % 100, key // 100)
        with open(bd / name, "wb") as fh:
            fh.write(struct.pack("<I", int(m.sum())))
            fh.write(rec[m].astype("<f8").tobytes())
        cx, cy = E0 + (key % 100 + 0.5) * TILE_M, N1 - (key // 100 + 0.5) * TILE_M
        index.append({"file": name, "tx": int(key % 100), "ty": int(key // 100), "count": int(m.sum()),
                      "center_ue_cm": [(cx - ORIGIN[0]) * 100.0, -(cy - ORIGIN[1]) * 100.0]})
    # roof raster for far views
    k = ROOF_PX / EXT
    cover = np.zeros((ROOF_PX, ROOF_PX), np.float32)
    hmax = np.zeros((ROOF_PX, ROOF_PX), np.float32)
    px, py = ((e - E0) * k).astype(int).clip(0, ROOF_PX - 1), ((N1 - n) * k).astype(int).clip(0, ROOF_PX - 1)
    np.add.at(cover, (py, px), area * k * k)
    np.maximum.at(hmax, (py, px), height)
    cover = np.clip(ndimage.gaussian_filter(cover, 0.7) * 1.6, 0, 1)
    hmax = ndimage.grey_dilation(hmax, size=3)
    Image.fromarray(np.dstack([np.round(cover * 255), np.round(np.clip(hmax / 40.0, 0, 1) * 255), np.zeros_like(cover)]).astype(np.uint8), "RGB").save(run / "T_NF_Roofs.png")
    stats = {"source": "Overture world bands 2/3 (centroid, area_m2, height, num_floors); release per NTW worktree manifests",
             "license": "Overture buildings: ODbL (OSM-derived) / CC-BY-4.0 (zenodo.8174931)", "records_in_window": int(len(rows)), "boxes": int(cnt),
             "with_height": int(np.isfinite(hgt).sum()), "with_floors": int(np.isfinite(flo).sum()),
             "height_m": {"p50": float(np.median(height)), "p90": float(np.percentile(height, 90)), "max": float(height.max())}, "tiles": len(index)}
    (run / "buildings.json").write_text(json.dumps({"stats": stats, "record": "x_cm,y_cm,z_cm(centre),yaw_deg,sx_m,sy_m,sz_m (float64)", "tiles": index}, indent=0) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
