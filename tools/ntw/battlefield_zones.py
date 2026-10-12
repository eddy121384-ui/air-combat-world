"""Battlefield zones + zone-aware detail tiers + GIS plan map for the recommended mission size.

Zones (all parameters from the battlefield config, nothing hard-coded to North Taiwan):
  flyable      mission box chosen by battlefield_planner (8 km-grid aligned)
  production   flyable + production_halo_km (formal terrain / building production; cells)
  far_field    remaining world cells (low-resolution terrain + city silhouettes / impostors only)
  beyond_world ocean plane to the horizon + distant-mountain impostor ring + atmospheric fade (no geometry production)
Tiers per cell use ONLY the approved key sites (PR #22 review: Hualien / CCK / Taichung port are not v1 key sites) and cap the
detail by zone. Tiers are planning priority, not approval of per-building production.
Outputs: data/ntw/battlefield/<name>_zones.json, <name>_zones_epsg3826.geojson, docs/evidence/ntw/battlefield/<name>_plan.png
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely import box

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import render_world_maps as rwm  # noqa: E402
import world_cells as wc  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

GAP_LONLAT = (121.009, 24.450, 121.132, 24.567)  # PR #22 inland DTM gap (official 2025 product gap, Phase 2B)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=REPO / "worlds/battlefields/north_core_v1.json")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    world = WorldSpec.load(REPO / cfg["world"])
    study = json.loads((REPO / f"data/ntw/battlefield/{cfg['name']}_study.json").read_text(encoding="utf-8"))
    size = str(cfg["recommended_size_km"])
    fly = study["results"][size]["top"][0]
    fx0, fy0, fx1, fy1 = fly["bounds_epsg3826"]
    h = cfg["zones"]["production_halo_km"] * 1000
    prod = (max(fx0 - h, world.bounds_tm2[0]), max(fy0 - h, world.bounds_tm2[1]), min(fx1 + h, world.bounds_tm2[2]), min(fy1 + h, world.bounds_tm2[3]))
    cells = json.loads((REPO / f"data/ntw/world/{world.name}_cells_epsg3826.geojson").read_text(encoding="utf-8"))["features"]
    feats = json.loads((REPO / "data/ntw/world/features.json").read_text(encoding="utf-8"))["features"]
    approved = set(cfg["approved_key_sites"])
    site_cells = defaultdict(list)
    for f in feats:
        if f["name"] in approved and "lon" in f:
            x, y = wc.TO_TM2.transform(f["lon"], f["lat"])
            site_cells[world.cell_id(*world.cell_index_abs(x, y))].append(f["name"])
    xin_cells = set(json.loads((REPO / "data/ntw/world/xinyi_compat.json").read_text(encoding="utf-8"))["placement"]["world_cells_8km"])
    gx0, gy0 = wc.TO_TM2.transform(GAP_LONLAT[0], GAP_LONLAT[1])
    gx1, gy1 = wc.TO_TM2.transform(GAP_LONLAT[2], GAP_LONLAT[3])
    gap = box(gx0, gy0, gx1, gy1)
    T = {"t1_min_built_frac": 0.06, "t1_min_buildings": 6000, "t2_min_built_frac": 0.012, "t2_min_buildings": 800}
    zstats = defaultdict(lambda: defaultdict(lambda: {"cells": 0, "land_km2": 0.0, "sea_km2": 0.0, "buildings_best": 0}))
    out_cells = []
    for cf in cells:
        p = cf["properties"]
        b = np.asarray(cf["geometry"]["coordinates"][0])
        x0, y0, x1, y1 = b[:, 0].min(), b[:, 1].min(), b[:, 0].max(), b[:, 1].max()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        zone = ("flyable" if fx0 <= cx <= fx1 and fy0 <= cy <= fy1 else
                "production" if prod[0] <= cx <= prod[2] and prod[1] <= cy <= prod[3] else "far_field")
        site = site_cells.get(p["cell_id"], [])
        bf, nb, core = p["built_frac_of_land"], p["buildings_best"], p["core_theater"]
        mount = p["elev_mean_m"] is not None and p["elev_mean_m"] >= 500
        if p["land_km2"] < 0.32 and not site:
            tier = "T4_sea"
        elif zone == "far_field":
            tier = "F_far_field_silhouette" if nb >= T["t2_min_buildings"] else "F_far_field_terrain"
        elif zone == "production":
            tier = "P_halo_massing" if (bf >= T["t2_min_built_frac"] or nb >= T["t2_min_buildings"]) else ("T3_low_mountain" if mount else "T3_low_rural_coastal")
        elif p["cell_id"] in xin_cells or site or (core and (bf >= T["t1_min_built_frac"] or nb >= T["t1_min_buildings"])):
            tier = "T1_high"
        elif core and (bf >= T["t2_min_built_frac"] or nb >= T["t2_min_buildings"]):
            tier = "T2_medium"
        elif bf >= T["t2_min_built_frac"] or nb >= T["t2_min_buildings"]:
            tier = "T2_periphery_massing"
        else:
            tier = "T3_low_mountain" if mount else "T3_low_rural_coastal"
        dtm = "BLOCKED_official_dem_gap" if shapely.intersects(box(x0, y0, x1, y1), gap) else "ok"
        s = zstats[zone][tier]
        s["cells"] += 1
        s["land_km2"] += p["land_km2"]
        s["sea_km2"] += p["sea_km2"]
        s["buildings_best"] += p["buildings_best"]
        out_cells.append({"cell_id": p["cell_id"], "zone": zone, "tier_v1": tier, "key_sites": site, "dtm": dtm,
                          "bounds": [x0, y0, x1, y1], "land_km2": p["land_km2"], "buildings_best": nb})
    for z in zstats.values():
        for t in z.values():
            t["land_km2"] = round(t["land_km2"], 1)
            t["sea_km2"] = round(t["sea_km2"], 1)
    gap_zone = sorted({c["zone"] for c in out_cells if c["dtm"] != "ok"})
    res = {"battlefield": cfg["name"], "world": world.name, "recommended_size_km": int(size),
           "flyable_epsg3826": [fx0, fy0, fx1, fy1], "production_epsg3826": list(prod), "far_field_epsg3826": list(world.bounds_tm2),
           "flyable_depth_km": fly["depth_km"], "flyable_land_pct": fly["land_pct"], "regions_partly_inside_pct": fly.get("regions_partly_inside_pct"),
           "regions_fully_inside": fly.get("regions_fully_inside"),
           "approved_key_sites": sorted(approved), "zone_tier_stats": {z: dict(v) for z, v in zstats.items()},
           "dtm_gap": {"bbox_epsg3826": [round(v) for v in (gx0, gy0, gx1, gy1)], "zones": gap_zone,
                       "distance_to_production_km": round(shapely.distance(gap, box(*prod)) / 1000, 2),
                       "distance_to_flyable_km": round(shapely.distance(gap, box(fx0, fy0, fx1, fy1)) / 1000, 2),
                       "status": "BLOCKED (official 2025 DEM has no sheets there; no 0 m, no interpolation)"},
           "beyond_world": cfg["zones"]["beyond_world"], "detail_policy": cfg["detail_policy"]}
    od = REPO / "data/ntw/battlefield"
    (od / f"{cfg['name']}_zones.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3826"}},
          "features": [{"type": "Feature", "properties": {"zone": n}, "geometry": shapely.geometry.mapping(box(*bb))}
                       for n, bb in (("flyable", (fx0, fy0, fx1, fy1)), ("production", prod), ("far_field_world", world.bounds_tm2),
                                     ("dtm_gap_blocked", (gx0, gy0, gx1, gy1)))]
          + [{"type": "Feature", "properties": {k: v for k, v in c.items() if k != "bounds"}, "geometry": shapely.geometry.mapping(box(*c["bounds"]))}
             for c in out_cells]}
    (od / f"{cfg['name']}_zones_epsg3826.geojson").write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    draw_plan(cfg, world, study, res, out_cells, gap, feats, approved)
    print(json.dumps({k: res[k] for k in ("flyable_epsg3826", "production_epsg3826", "flyable_depth_km", "dtm_gap", "regions_partly_inside_pct")}, ensure_ascii=False, indent=1))
    print(json.dumps(res["zone_tier_stats"], ensure_ascii=False, indent=1))


def draw_plan(cfg, world, study, res, cells, gap, feats, approved):
    x0, y0, x1, y1 = world.bounds_tm2
    ext = (x0 - 8000, y0 - 8000, x1 + 8000, y1 + 8000)
    cv = rwm.Canvas(ext, 160.0)
    GX, GY = cv.grid()
    cv.inside_world = (GX >= x0) & (GX < x1) & (GY >= y0) & (GY < y1)
    tw, foreign, mi, isl = wc.load_land()
    land = shapely.union(mi, isl)
    shapely.prepare(land)
    mos, meta, _ = wc.dtm_mosaic(world)
    img, _ = rwm.base_map(cv, land, [g for *_, g in foreign], mos, meta)
    img = Image.blend(img, Image.new("RGB", img.size, (255, 255, 255)), 0.25)
    d = ImageDraw.Draw(img, "RGBA")
    col = {"T1_high": (200, 40, 40, 110), "T2_medium": (240, 150, 40, 100), "T2_periphery_massing": (170, 120, 200, 90),
           "P_halo_massing": (150, 100, 160, 70), "T3_low_rural_coastal": (150, 190, 110, 55), "T3_low_mountain": (110, 130, 100, 45),
           "F_far_field_silhouette": (90, 90, 90, 45), "F_far_field_terrain": (0, 0, 0, 0), "T4_sea": (0, 0, 0, 0)}
    for c in cells:
        b = c["bounds"]
        d.rectangle([cv.px(b[0], b[3]), cv.px(b[2], b[1])], fill=col[c["tier_v1"]])
    for v in np.arange(x0, x1 + 1, 8000):
        d.line([cv.px(v, y0), cv.px(v, y1)], fill=(60, 60, 90, 35), width=1)
    for v in np.arange(y0, y1 + 1, 8000):
        d.line([cv.px(x0, v), cv.px(x1, v)], fill=(60, 60, 90, 35), width=1)
    f12, f14, f16 = rwm.font(12), rwm.font(14), rwm.font(16)
    # other sizes
    for sz, cl in (("104", (30, 90, 200)), ("120", (30, 150, 120))):
        r = study["results"].get(sz)
        if r and r["top"]:
            bx = r["top"][0]["bounds_epsg3826"]
            d.rectangle([cv.px(bx[0], bx[3]), cv.px(bx[2], bx[1])], outline=cl + (200,), width=2)
            d.text(cv.px(bx[0] + 800, bx[3] - 600), f"{sz} km", fill=cl, font=f12)
    rot = study.get("rotated_mission_study", {}).get("50deg_104km")
    if rot:
        d.line([cv.px(*p) for p in rot["polygon_epsg3826"]], fill=(140, 60, 170, 220), width=2)
        p0 = rot["polygon_epsg3826"][0]
        d.text(cv.px(p0[0], p0[1]), "rotated 104 km (50 deg) option", fill=(140, 60, 170), font=f12)
    fx = res["flyable_epsg3826"]
    pr = res["production_epsg3826"]
    d.rectangle([cv.px(x0, y1), cv.px(x1, y0)], outline=(90, 90, 90), width=2)
    d.rectangle([cv.px(pr[0], pr[3]), cv.px(pr[2], pr[1])], outline=(240, 140, 0), width=3)
    d.rectangle([cv.px(fx[0], fx[3]), cv.px(fx[2], fx[1])], outline=(210, 20, 20), width=4)
    gb = gap.bounds
    d.rectangle([cv.px(gb[0], gb[3]), cv.px(gb[2], gb[1])], fill=(235, 0, 200, 170), outline=(150, 0, 120), width=2)
    d.text(cv.px(gb[2] + 1500, gb[3]), "DTM gap BLOCKED\n(official 2025 DEM)", fill=(150, 0, 120), font=f12)
    # pilot cells + Xinyi
    for cid in ("C+0038+0346", "C+0038+0345"):
        ix, iy = int(cid[1:6]), int(cid[6:11])
        d.rectangle([cv.px(ix * 8000, iy * 8000 + 8000), cv.px(ix * 8000 + 8000, iy * 8000)], outline=(0, 170, 220), width=3)
    d.text(cv.px(38 * 8000 + 8300, 346 * 8000 + 7000), "terrain pilot cells\n(incl. Xinyi L3)", fill=(0, 120, 170), font=f12)
    for f in feats:
        if "lon" not in f:
            continue
        x, y = wc.TO_TM2.transform(f["lon"], f["lat"])
        px, py = cv.px(x, y)
        if not (0 <= px < cv.w and 0 <= py < cv.h):
            continue
        ok = f["name"] in approved
        c_ = (20, 20, 160) if ok else (120, 120, 120)
        if f["role"] == "peak":
            c_ = (90, 50, 10)
        r = 6 if ok else 4
        d.ellipse([px - r, py - r, px + r, py + r], fill=c_ if ok or f["role"] == "peak" else None, outline=c_, width=2)
        lab = f["name"].replace("南寮舊港愛之船咖啡", "南寮港").replace("空軍", "")
        d.text((px + r + 3, py - 8), lab + ("" if ok or f["role"] == "peak" else " (not v1 key site)"), fill=c_, font=f12)
    dk = res["flyable_depth_km"]
    lines = [f"{cfg['name']}: flyable {res['recommended_size_km']} x {res['recommended_size_km']} km  E {int(fx[0]):,}-{int(fx[2]):,}  N {int(fx[1]):,}-{int(fx[3]):,} (EPSG:3826)",
             f"production zone (flyable + {cfg['zones']['production_halo_km']} km) E {int(pr[0]):,}-{int(pr[2]):,}  N {int(pr[1]):,}-{int(pr[3]):,};  far field = world 224 km (grey)",
             f"sea depth from core coast: west min {dk['west_core_min']} / median {dk['west_core_median']} km;  north min {dk['north_core_min']} / median {dk['north_core_median']} km",
             "red = flyable, orange = production, grey = world / far field, blue/green = 104 / 120 km options, purple line = rotated option",
             "cell fill: T1 red, T2 orange, massing purple, low green/olive, far-field silhouettes grey; filled dots = approved v1 key sites"]
    bw = max(d.textlength(l, font=f14) for l in lines) + 16
    d.rectangle([8, 8, 8 + bw, 14 + 20 * len(lines)], fill=(255, 255, 255, 225))
    for i, l in enumerate(lines):
        d.text((16, 12 + 20 * i), l, fill=(0, 0, 0), font=f14)
    sb = 20000 / cv.res
    d.rectangle([cv.w - sb - 30, cv.h - 36, cv.w - 30, cv.h - 28], fill=(0, 0, 0))
    d.text((cv.w - sb - 30, cv.h - 56), "20 km", fill=(0, 0, 0), font=f14)
    o = REPO / "docs/evidence/ntw/battlefield"
    o.mkdir(parents=True, exist_ok=True)
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(o / f"{cfg['name']}_plan.png", optimize=True)


if __name__ == "__main__":
    main()
