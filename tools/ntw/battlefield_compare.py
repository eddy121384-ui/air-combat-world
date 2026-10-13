"""Compare fixed candidate flyable boxes for a battlefield (GIS only; does NOT change the battlefield config).

Candidates (EPSG:3826, from worlds/battlefields/<name>.json `compare_boxes` or the defaults below) are evaluated with the
battlefield planner's hard constraints and depth metric, plus counter-landing / naval-air oriented measures:
  * core-coast sea depth west / north / east (east labelled: the NE coast leaves the box)
  * western ocean inside the box (sea west of the main-island coast, per 1 km row) and the 0-50 km "front-line" sea band
    measured from the core west coast; share of the extension strip that is water
  * coastline length inside the box; "flat low shore" length = coast segments whose 1 km inland strip has mean DTM < 20 m
    (a landing-capable shore PROXY, not a landing study); Overture beach features
  * production cost: land cells / land km2 / buildings / LOD0 terrain triangles of the production zone (box + halo) relative to
    the 112 km baseline, for two policies: production follows the box, or production stays at the 112 km baseline
Writes data/ntw/battlefield/<name>_compare.json and docs/evidence/ntw/battlefield/<name>_compare.png.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely import box

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import battlefield_planner as bp  # noqa: E402
import render_world_maps as rwm  # noqa: E402
import world_cells as wc  # noqa: E402
from world_planner import load_geography, row_extents, to_tm2  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

DEFAULT_BOXES = {
    "112x112 (proposed)": (224000, 2728000, 336000, 2840000),
    "120x120": (216000, 2728000, 336000, 2848000),
    "128x112 west-extended": (208000, 2728000, 336000, 2840000),
}
LOD0_TRIS_PER_LAND_CELL = 320000  # measured Phase 2B: 25 chunks x 12,800 terrain triangles per 8 km cell


def beaches(world):
    cache = REPO / "data/generated/ntw/world/beaches.wkb.json"
    if not cache.exists():
        c = duckdb.connect()
        c.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
        rows = c.execute("""select id, class, ST_AsWKB(geometry) from read_parquet('s3://overturemaps-us-west-2/release/2026-09-23.1/theme=base/type=land/*', hive_partitioning=1)
                            where bbox.xmin >= 120.6 and bbox.xmax <= 122.2 and bbox.ymin >= 24.5 and bbox.ymax <= 25.5 and class in ('beach','sand')""").fetchall()
        cache.write_text(json.dumps([[r[0], r[1], bytes(r[2]).hex()] for r in rows]), encoding="utf-8")
    rows = json.loads(cache.read_text(encoding="utf-8"))
    return [(i, c, to_tm2(shapely.from_wkb(bytes.fromhex(h)))) for i, c, h in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=REPO / "worlds/battlefields/north_core_v1.json")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    boxes = {k: tuple(v) for k, v in cfg.get("compare_boxes", DEFAULT_BOXES).items()}
    world = WorldSpec.load(REPO / cfg["world"])
    main_island, islands, _, foreign, tw_regions, feats = load_geography()
    regions = {code: shapely.intersection(g, main_island.buffer(1.0)) for code, (name, g) in tw_regions.items()}
    req = {code: regions[code] for code in cfg["required"]["regions_full"]}
    derived = bp.derived_geometry(world, main_island, feats)
    core_codes = ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE"]
    core = shapely.union_all([regions[c] for c in core_codes])
    core_buf = core.buffer(300.0)
    shapely.prepare(core_buf)
    ys = np.arange(2_600_000, 2_900_001, 1000.0)
    xs = np.arange(150_000, 450_001, 1000.0)
    wlo, whi = row_extents(main_island, ys, True)
    _, nhi = row_extents(main_island, xs, False)

    def inc(xv, yv):
        ok = ~np.isnan(xv) & ~np.isnan(yv)
        o = np.zeros(len(xv), bool)
        o[ok] = shapely.contains_xy(core_buf, xv[ok], yv[ok])
        return o
    core_w = inc(wlo, ys)
    scan = (ys, wlo, whi, xs, nhi, core_w, inc(whi, ys), inc(xs, nhi))
    geo = (main_island, islands, regions, feats)
    # west core coastline (where the west-facing coast belongs to a core region) for the front-line band
    west_coast_pts = shapely.multipoints(np.column_stack([wlo[core_w], ys[core_w]]))
    front_band = shapely.intersection(west_coast_pts.buffer(50000.0), shapely.box(150000, 2600000, 450000, 2900000)).difference(main_island)
    # flat low shore proxy from the DTM mosaic
    mos, meta, _ = wc.dtm_mosaic(world)
    coast = main_island.exterior
    segs = shapely.segmentize(coast, 500.0)
    co = shapely.get_coordinates(segs)
    mids = (co[:-1] + co[1:]) / 2
    seglen = np.hypot(*(co[1:] - co[:-1]).T)
    inland = []
    for (x, y) in mids:
        p = shapely.Point(x, y)
        q = shapely.ops.nearest_points(main_island.boundary, p)[0]
        # sample 1 km inland along the inward normal approx: 4 points towards the island centroid direction
        cx, cy = main_island.centroid.x, main_island.centroid.y
        v = np.array([cx - x, cy - y])
        v /= np.linalg.norm(v)
        pts = np.array([[x + v[0] * d, y + v[1] * d] for d in (200, 400, 700, 1000)])
        lon, lat = wc.TO_LL.transform(pts[:, 0], pts[:, 1])
        z = wc.sample_dtm(mos, meta, np.asarray(lon), np.asarray(lat))
        inland.append(float(np.nanmean(z)) if np.isfinite(z).any() else np.nan)
    inland = np.array(inland)
    flat = inland < 20.0
    bch = beaches(world)
    cells = json.loads((REPO / f"data/ntw/world/{world.name}_cells_epsg3826.geojson").read_text(encoding="utf-8"))["features"]
    h = cfg["zones"]["production_halo_km"] * 1000

    def prod_stats(bx):
        x0, y0, x1, y1 = bx
        pz = (max(x0 - h, world.bounds_tm2[0]), max(y0 - h, world.bounds_tm2[1]), min(x1 + h, world.bounds_tm2[2]), min(y1 + h, world.bounds_tm2[3]))
        land_cells = land = bld = 0
        for cf in cells:
            p = cf["properties"]
            b = np.asarray(cf["geometry"]["coordinates"][0])
            cx, cy = b[:, 0].mean(), b[:, 1].mean()
            if pz[0] <= cx <= pz[2] and pz[1] <= cy <= pz[3]:
                if p["land_km2"] >= 0.32:
                    land_cells += 1
                land += p["land_km2"]
                bld += p["buildings_best"]
        return {"production_zone_epsg3826": list(pz), "land_cells": land_cells, "land_km2": round(land, 1), "buildings_best": bld,
                "lod0_terrain_triangles_estimate": land_cells * LOD0_TRIS_PER_LAND_CELL}

    base_key = next(iter(boxes))
    out = {"config": cfg["name"], "note": "GIS comparison only; the proposed battlefield config is NOT changed", "boxes": {}}
    for name, bx in boxes.items():
        r = bp.evaluate(bx, geo, req, derived, scan, cfg, core_buf)
        mb = box(*bx)
        sea_in = mb.difference(main_island).difference(islands)
        west_sea = 0.0
        for y, xl in zip(ys, wlo):
            if bx[1] <= y < bx[3] and not np.isnan(xl):
                west_sea += max(0.0, min(xl, bx[2]) - bx[0]) * 1000.0
        fl = shapely.intersection(front_band, mb).area
        m_in = shapely.contains_xy(mb, mids[:, 0], mids[:, 1])
        ext = None
        if name != base_key:
            strip = mb.difference(box(*boxes[base_key]))
            ext = {"area_km2": round(strip.area / 1e6, 1), "water_share_pct": round(100 * strip.difference(main_island).difference(islands).area / max(strip.area, 1), 1),
                   "land_km2": round(shapely.intersection(strip, main_island).area / 1e6, 1)}
        out["boxes"][name] = {
            "bounds_epsg3826": list(bx), "size_km": [(bx[2] - bx[0]) / 1000, (bx[3] - bx[1]) / 1000],
            "area_km2": round(mb.area / 1e6, 1), "feasible": r["feasible"], "violations": r["violations"],
            "depth_km": r["depth_km"], "east_limitation": "east_core_min = 0: the NE coast (Keelung -> Sandiaojiao) leaves the box; no eastern sea buffer",
            "sea_km2": round(sea_in.area / 1e6, 1), "west_ocean_km2": round(west_sea / 1e6, 1),
            "front_line_sea_0_50km_km2": round(fl / 1e6, 1),
            "coastline_km": round(float(seglen[m_in].sum()) / 1000, 1),
            "flat_low_shore_km_proxy": round(float(seglen[m_in & flat].sum()) / 1000, 1),
            "beach_features": int(sum(1 for _, _, g in bch if shapely.intersects(g, mb))),
            "extension_vs_112": ext,
            "production_follows_box": prod_stats(bx),
        }
        print(name, out["boxes"][name]["depth_km"], out["boxes"][name]["west_ocean_km2"], out["boxes"][name]["front_line_sea_0_50km_km2"], ext)
    base = out["boxes"][base_key]["production_follows_box"]
    for name, v in out["boxes"].items():
        p = v["production_follows_box"]
        v["extra_cost_if_production_follows_box"] = {k: (p[k] - base[k]) for k in ("land_cells", "land_km2", "buildings_best", "lod0_terrain_triangles_estimate")}
        v["extra_cost_if_production_stays_112"] = {"land_cells": 0, "terrain": "added flyable area rendered as 0 m water plane + far-field terrain only",
                                                   "risk": "land inside the flyable box but outside production would be far-field quality"}
    od = REPO / "data/ntw/battlefield"
    (od / f"{cfg['name']}_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    draw(world, main_island, islands, foreign, boxes, out, front_band, mids, flat, cfg)
    print(json.dumps({k: {kk: v[kk] for kk in ("extension_vs_112", "extra_cost_if_production_follows_box", "flat_low_shore_km_proxy", "beach_features", "coastline_km")}
                      for k, v in out["boxes"].items()}, ensure_ascii=False, indent=1))


def draw(world, main_island, islands, foreign, boxes, out, front_band, mids, flat, cfg):
    x0, y0, x1, y1 = (200000, 2700000, 352000, 2860000)
    cv = rwm.Canvas((x0, y0, x1, y1), 100.0)
    GX, GY = cv.grid()
    cv.inside_world = np.ones(GX.shape, bool)
    land = shapely.union(main_island, islands)
    shapely.prepare(land)
    mos, meta, _ = wc.dtm_mosaic(world)
    img, _ = rwm.base_map(cv, land, [g for *_, g in foreign], mos, meta)
    d = ImageDraw.Draw(img, "RGBA")
    for p in shapely.get_parts(shapely.intersection(front_band, box(x0, y0, x1, y1))):
        if p.geom_type == "Polygon":
            d.polygon([cv.px(*c) for c in p.exterior.coords], fill=(40, 120, 220, 45))
    for (x, y), f in zip(mids, flat):
        if f and x0 < x < x1 and y0 < y < y1:
            px, py = cv.px(x, y)
            d.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(230, 160, 0, 220))
    cols = [(210, 20, 20), (30, 150, 120), (140, 60, 200)]
    f14 = rwm.font(14)
    for (name, bx), c in zip(boxes.items(), cols):
        d.rectangle([cv.px(bx[0], bx[3]), cv.px(bx[2], bx[1])], outline=c + (230,), width=3)
    lines = [f"{cfg['name']}: candidate flyable boxes (GIS only; proposed 112 km config unchanged)"]
    for (name, v), c in zip(out["boxes"].items(), cols):
        dk = v["depth_km"]
        lines.append(f"{name}: W {dk['west_core_min']}/{dk['west_core_median']} km, N {dk['north_core_min']} km, west ocean {v['west_ocean_km2']:.0f} km2, "
                     f"front-line sea {v['front_line_sea_0_50km_km2']:.0f} km2, +land cells {v['extra_cost_if_production_follows_box']['land_cells']}")
    lines.append("blue tint = sea within 50 km of the core west coast; orange dots = flat low shore proxy (1 km inland mean DTM < 20 m)")
    bw = max(d.textlength(l, font=f14) for l in lines) + 16
    d.rectangle([8, 8, 8 + bw, 14 + 20 * len(lines)], fill=(255, 255, 255, 230))
    for i, (l, c) in enumerate(zip(lines, [(0, 0, 0)] + cols + [(0, 0, 0)])):
        d.text((16, 12 + 20 * i), l, fill=c, font=f14)
    o = REPO / "docs/evidence/ntw/battlefield"
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(o / f"{cfg['name']}_compare.png", optimize=True)


if __name__ == "__main__":
    main()
