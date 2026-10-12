"""Reviewable GIS planning maps for a WorldSpec (PNG, drawn from the real DTM / coastline / Overture features).

Outputs (docs/evidence/ntw/world/):
  <name>_plan.png    terrain hillshade, coastline, world box, 8 km + 32 km grid, core regions, Xinyi, airports,
                     ports, peaks, approximate Strait median line, alternative placements, runtime origin
  <name>_tiers.png   detail tier per 8 km cell + building density
  size_options.png   best placement for each studied map size (192 / 224 / 256 / 288 km)
usage: render_world_maps.py --world worlds/north_taiwan_224.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import world_cells as wc  # noqa: E402
from world_planner import MEDIAN_LINE_LONLAT  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

OUT = REPO / "docs/evidence/ntw/world"
FONT = Path("C:/Windows/Fonts/msjh.ttc")
TIER_COL = {"T1_high": (200, 40, 40), "T2_medium": (240, 150, 40), "T2_periphery_urban": (170, 120, 200),
            "T3_low_rural_coastal": (150, 190, 110), "T3_low_mountain": (120, 140, 110), "T4_sea": None}


def font(sz):
    try:
        return ImageFont.truetype(str(FONT), sz)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


class Canvas:
    def __init__(self, ext, res):
        self.ext, self.res = ext, res
        self.w = int((ext[2] - ext[0]) / res)
        self.h = int((ext[3] - ext[1]) / res)

    def px(self, x, y):
        return ((x - self.ext[0]) / self.res, (self.ext[3] - y) / self.res)

    def grid(self):
        xs = self.ext[0] + (np.arange(self.w) + 0.5) * self.res
        ys = self.ext[3] - (np.arange(self.h) + 0.5) * self.res
        return np.meshgrid(xs, ys)


def base_map(cv, land, foreign, mos, meta):
    GX, GY = cv.grid()
    lon, lat = wc.TO_LL.transform(GX.ravel(), GY.ravel())
    e = wc.sample_dtm(mos, meta, np.asarray(lon), np.asarray(lat)).reshape(GX.shape)
    on = shapely.contains_xy(land, GX.ravel(), GY.ravel()).reshape(GX.shape)
    fon = np.zeros_like(on)
    for g in foreign:
        fon |= shapely.contains_xy(g, GX.ravel(), GY.ravel()).reshape(GX.shape)
    z = np.where(on, np.nan_to_num(e, nan=0.0), 0.0)
    gy_, gx_ = np.gradient(z, cv.res)
    slope = np.pi / 2 - np.arctan(np.hypot(gx_, gy_) * 2.0)
    aspect = np.arctan2(-gx_, gy_)
    az, alt = np.radians(315), np.radians(45)
    hs = np.clip(np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect), 0, 1)
    t = np.clip(z / 3500.0, 0, 1)
    tint = np.stack([150 + 80 * t, 185 - 40 * t + 30 * (t > 0.6), 130 + 60 * t], -1)
    rgb = tint * (0.55 + 0.45 * hs[..., None])
    sea = np.array([200, 222, 238])
    img = np.where(on[..., None], rgb, np.where(fon[..., None], np.array([215, 210, 200]), sea))
    hole, _ = wc.inland_holes(GX.ravel(), GY.ravel(), e.ravel(), land, GX.shape, (cv.res / 1000) ** 2)
    hole = hole.reshape(GX.shape) & cv.inside_world
    img[hole] = np.array([235, 0, 200])  # DTM data hole (magenta), never shown as flat terrain
    return Image.fromarray(img.astype(np.uint8)), on


def draw_poly(d, cv, g, outline, width=1, fill=None):
    for p in shapely.get_parts(g):
        if p.geom_type != "Polygon":
            continue
        d.polygon([cv.px(*c) for c in p.exterior.coords], outline=outline, fill=fill, width=width)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=Path, default=REPO / "worlds/north_taiwan_224.json")
    ap.add_argument("--res", type=float, default=200.0)
    a = ap.parse_args()
    spec = WorldSpec.load(a.world)
    raw = json.loads(a.world.read_text(encoding="utf-8"))
    x0, y0, x1, y1 = spec.bounds_tm2
    m = 48000.0
    ext = (x0 - m, y0 - m, x1 + m, y1 + m)
    cv = Canvas(ext, a.res)
    GXc, GYc = cv.grid()
    cv.inside_world = (GXc >= x0) & (GXc < x1) & (GYc >= y0) & (GYc < y1)  # DTM fetched only inside the world
    tw, foreign, main_island, islands = wc.load_land()
    land = shapely.union(main_island, islands)
    shapely.prepare(land)
    fgeo = [g for *_, g in foreign]
    big = WorldSpec(name="ctx", sw_tm2=(x0 - m, y0 - m), size_m=(x1 - x0 + 2 * m, y1 - y0 + 2 * m))
    mos, meta, _ = wc.dtm_mosaic(big)
    img, _ = base_map(cv, land, fgeo, mos, meta)
    d = ImageDraw.Draw(img, "RGBA")
    f12, f14, f18, f22 = font(12), font(14), font(18), font(22)
    # grid
    for v in np.arange(np.floor(ext[0] / 8000) * 8000, ext[2], 8000):
        w = 2 if v % 32000 == 0 else 1
        col = (60, 60, 90, 110 if w == 2 else 45)
        d.line([cv.px(v, ext[1]), cv.px(v, ext[3])], fill=col, width=w)
    for v in np.arange(np.floor(ext[1] / 8000) * 8000, ext[3], 8000):
        w = 2 if v % 32000 == 0 else 1
        col = (60, 60, 90, 110 if w == 2 else 45)
        d.line([cv.px(ext[0], v), cv.px(ext[2], v)], fill=col, width=w)
    # core regions + Phase-1
    for code in ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE", "TW-ILA"]:
        draw_poly(d, cv, tw[code][1], (90, 40, 20, 200), 1)
    # median line (approximate)
    ml = [wc.TO_TM2.transform(*p) for p in MEDIAN_LINE_LONLAT]
    pts = [cv.px(*p) for p in ml]
    for i in range(40):
        t0, t1 = i / 40, (i + 0.5) / 40
        d.line([(pts[0][0] + t0 * (pts[1][0] - pts[0][0]), pts[0][1] + t0 * (pts[1][1] - pts[0][1])),
                (pts[0][0] + t1 * (pts[1][0] - pts[0][0]), pts[0][1] + t1 * (pts[1][1] - pts[0][1]))], fill=(110, 110, 110, 200), width=2)
    mx, my = cv.px(*wc.TO_TM2.transform(120.35, 25.40))
    d.text((mx + 6, my), "approx. Strait median line\n(commonly cited, not official)", fill=(80, 80, 80), font=f12)
    # alternatives
    for k, alt in raw.get("alternatives", {}).items():
        ax, ay = alt["sw_corner_epsg3826"]
        p0, p1 = cv.px(ax, ay + spec.size_m[1]), cv.px(ax + spec.size_m[0], ay)
        d.rectangle([p0, p1], outline=(30, 90, 200, 170), width=2)
        d.text((p0[0] + 6, p0[1] + 4 if k == "north_deep" else p1[1] - 20), f"alt: {k}", fill=(30, 90, 200), font=f14)
    # world box
    d.rectangle([cv.px(x0, y1), cv.px(x1, y0)], outline=(210, 20, 20), width=4)
    # Xinyi
    mask = json.loads((REPO / "data/ntw/world/xinyi_l3_mask_epsg3826.geojson").read_text())
    xs = shapely.geometry.shape(mask["features"][0]["geometry"])
    c = xs.centroid
    d.rectangle([cv.px(c.x - 2500, c.y + 2500), cv.px(c.x + 2500, c.y - 2500)], outline=(255, 0, 180), width=3)
    tx, ty = cv.px(c.x + 3000, c.y + 2000)
    d.text((tx, ty), "信義 Xinyi L3 (accepted)", fill=(200, 0, 140), font=f14)
    # runtime origin
    ox, oy = spec.runtime_origin_tm2
    p = cv.px(ox, oy)
    d.line([(p[0] - 9, p[1]), (p[0] + 9, p[1])], fill=(0, 0, 0), width=2)
    d.line([(p[0], p[1] - 9), (p[0], p[1] + 9)], fill=(0, 0, 0), width=2)
    d.text((p[0] + 8, p[1] + 4), "UE origin", fill=(0, 0, 0), font=f12)
    # features
    feats = json.loads((REPO / "data/ntw/world/features.json").read_text(encoding="utf-8"))["features"]
    for f in feats:
        if "lon" not in f:
            continue
        fx, fy = cv.px(*wc.TO_TM2.transform(f["lon"], f["lat"]))
        if not (0 <= fx < cv.w and 0 <= fy < cv.h):
            continue
        col = {"airport": (20, 20, 160), "port": (0, 120, 120), "peak": (90, 50, 10)}[f["role"]]
        if f["tier"].startswith("info_foreign"):
            col = (120, 120, 120)
        r = 6 if f["tier"] == "required" else 4
        if f["role"] == "airport":
            d.polygon([(fx, fy - r - 2), (fx - r, fy + r), (fx + r, fy + r)], fill=col)
        elif f["role"] == "port":
            d.rectangle([fx - r, fy - r, fx + r, fy + r], fill=col)
        else:
            d.polygon([(fx, fy - r - 1), (fx - r, fy + r - 1), (fx + r, fy + r - 1)], outline=col, width=2)
        lab = f["name"].replace("南寮舊港愛之船咖啡", "南寮港").replace("空軍", "")
        if f["role"] == "peak" and f.get("elevation_m"):
            lab += f" {f['elevation_m']}m"
        d.text((fx + r + 3, fy - 8), lab, fill=col, font=f12)
    # text block
    s = spec.summary()
    summ = json.loads((REPO / f"data/ntw/world/{spec.name}_summary.json").read_text(encoding="utf-8"))
    t = summ["totals"]
    lines = [f"{spec.name}  {int(s['size_km'][0])} x {int(s['size_km'][1])} km  ({s['cells'][0]} x {s['cells'][1]} cells of 8 km)",
             f"EPSG:3826 bounds  E {int(x0):,}-{int(x1):,}  N {int(y0):,}-{int(y1):,}",
             f"UE origin (world centre) E {int(ox):,} N {int(oy):,}   max |coord| {s['max_abs_ue_coordinate_km']:.0f} km",
             f"land {t['tw_land_km2']:,.0f} km2 ({t['land_pct']}%)  sea {t['sea_km2']:,.0f} km2  foreign 0  coastline {t['coastline_km']:.0f} km",
             "thin grid 8 km (L1) / bold 32 km (L0)  |  red = world, blue = alternatives, brown = core regions",
             "magenta = DTM data hole (mirror NODATA / 0 m inland); land outside the world drawn without DTM"]
    bw = max(d.textlength(l, font=f14) for l in lines) + 16
    d.rectangle([8, 8, 8 + bw, 8 + 20 * len(lines) + 10], fill=(255, 255, 255, 215))
    for i, l in enumerate(lines):
        d.text((16, 14 + 20 * i), l, fill=(0, 0, 0), font=f14)
    # scale bar 50 km
    sb = 50000 / cv.res
    d.rectangle([cv.w - sb - 30, cv.h - 36, cv.w - 30, cv.h - 28], fill=(0, 0, 0))
    d.text((cv.w - sb - 30, cv.h - 56), "50 km", fill=(0, 0, 0), font=f14)
    OUT.mkdir(parents=True, exist_ok=True)
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(OUT / f"{spec.name}_plan.png", optimize=True)

    # ---------------- tiers map
    cells = json.loads((REPO / f"data/ntw/world/{spec.name}_cells_epsg3826.geojson").read_text(encoding="utf-8"))["features"]
    ti, _ = base_map(cv, land, fgeo, mos, meta)
    ti = Image.blend(ti, Image.new("RGB", ti.size, (255, 255, 255)), 0.45)
    d2 = ImageDraw.Draw(ti, "RGBA")
    for cf in cells:
        pr = cf["properties"]
        col = TIER_COL[pr["tier"]]
        b = np.asarray(cf["geometry"]["coordinates"][0])
        p0, p1 = cv.px(b[:, 0].min(), b[:, 1].max()), cv.px(b[:, 0].max(), b[:, 1].min())
        if col:
            d2.rectangle([p0, p1], fill=col + (140,), outline=(255, 255, 255, 120))
        if pr["buildings_best"] > 0:
            r = min(16, 1.5 + np.sqrt(pr["buildings_best"]) / 14)
            cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            d2.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 0, 160), width=1)
    d2.rectangle([cv.px(x0, y1), cv.px(x1, y0)], outline=(210, 20, 20), width=4)
    for code in ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE", "TW-ILA"]:
        draw_poly(d2, cv, tw[code][1], (60, 30, 10, 180), 1)
    leg = [(k, TIER_COL[k], v) for k, v in summ["tiers"].items() if k != "T4_sea"]
    names = {"T1_high": "T1 high detail (core urban / key sites / Xinyi)", "T2_medium": "T2 medium (core suburban)",
             "T2_periphery_urban": "T2p periphery urban - massing only", "T3_low_rural_coastal": "T3 low (rural / coastal)",
             "T3_low_mountain": "T3m low (mountain, mean elev >= 500 m)"}
    order = ["T1_high", "T2_medium", "T2_periphery_urban", "T3_low_rural_coastal", "T3_low_mountain"]
    d2.rectangle([8, 8, 600, 40 + 22 * 6], fill=(255, 255, 255, 225))
    d2.text((16, 14), f"{spec.name}: detail tier per 8 km cell (circle area ~ best building count)", fill=(0, 0, 0), font=f14)
    for i, k in enumerate(order):
        v = summ["tiers"].get(k, {"cells": 0, "buildings_best": 0, "land_km2": 0})
        y = 40 + 22 * i
        d2.rectangle([16, y, 34, y + 16], fill=TIER_COL[k])
        d2.text((42, y), f"{names[k]}: {v['cells']} cells, {v['land_km2']:,.0f} km2 land, {v['buildings_best']:,} bldgs", fill=(0, 0, 0), font=f12)
    sv = summ["tiers"].get("T4_sea", {"cells": 0})
    d2.text((16, 40 + 22 * 5), f"T4 sea (no colour): {sv['cells']} cells", fill=(0, 0, 0), font=f12)
    ti.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(OUT / f"{spec.name}_tiers.png", optimize=True)

    # ---------------- size options
    so, _ = base_map(cv, land, fgeo, mos, meta)
    so = Image.blend(so, Image.new("RGB", so.size, (255, 255, 255)), 0.3)
    d3 = ImageDraw.Draw(so, "RGBA")
    cols = {192: (40, 160, 60), 224: (210, 20, 20), 256: (30, 90, 200), 288: (140, 60, 170)}
    yy = 14
    d3.rectangle([8, 8, 760, 8 + 24 * 5], fill=(255, 255, 255, 225))
    d3.text((16, yy), "Best feasible placement per map size (same planner, 8 km grid, no foreign land)", fill=(0, 0, 0), font=f14)
    for sz, col in cols.items():
        pth = REPO / f"data/ntw/world/placement_{sz}.json"
        if not pth.exists():
            continue
        top = json.loads(pth.read_text(encoding="utf-8"))["top"][0]
        bx0, by0, bx1, by1 = top["bounds_epsg3826"]
        d3.rectangle([cv.px(bx0, by1), cv.px(bx1, by0)], outline=col, width=3)
        yy += 24
        dk = top["depth_km"]
        d3.text((16, yy), f"{sz} km: min core sea depth {top['objective_min_core_depth_km']} km (W {dk['west_core_min']} / N {dk['north_core_min']} / E {dk['east_core_min']}), "
                          f"land {top['land_tw_pct']}%, nearest foreign {top['nearest_foreign_land_km']} km", fill=col, font=f12)
    so.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(OUT / "size_options.png", optimize=True)
    for f in sorted(OUT.glob("*.png")):
        print(f, f.stat().st_size)


if __name__ == "__main__":
    main()
