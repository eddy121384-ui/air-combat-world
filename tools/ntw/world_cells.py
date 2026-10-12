"""Per-cell world analysis for a WorldSpec: land / sea / coast / terrain / buildings / detail tier.

Inputs (pinned, ignored caches): land.parquet (world_geography.py), DTM z13 tiles (fetch_dtm_tiles.py),
ovt_world_band*.parquet (extract_overture_buildings.py --centroid), wfs_taipei_citywide.ndjson.
Outputs (committed, compact):
  data/ntw/world/<name>_cells_epsg3826.geojson   one polygon per world cell with all attributes
  data/ntw/world/<name>_bounds.geojson            world rectangle (EPSG:3826) + densified lon/lat outline
  data/ntw/world/<name>_summary.json              totals, tiers, admin regions, sea sectors, L0 blocks, QA
Building numbers: Taipei City = authoritative WFS records; elsewhere = Overture rows (a LOWER BOUND of real
buildings, see Phase 1). Heights are classified with the real policy validator (tools/ntw/heights.py bounds),
separating "present but invalid" from "missing" (PR #16 review item 4).
Tier thresholds are parameters (--tiers JSON) - nothing here is specific to 224 km.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import numpy as np
import shapely
from PIL import Image
from pyproj import Transformer
from shapely import box
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import heights  # noqa: E402
from dtm import CACHE as DTM_CACHE, Z  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

TO_TM2 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
TO_LL = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
W = REPO / "data/generated/ntw/world"
DEFAULT_TIERS = {
    "sea_max_land_frac": 0.005,
    "t1_min_built_frac": 0.06, "t1_min_buildings": 6000,
    "t2_min_built_frac": 0.012, "t2_min_buildings": 800,
    "mountain_min_mean_elev_m": 500.0,
    "key_site_roles": ["airport", "port"], "key_site_tiers": ["required", "optional"],
    # theater priority: dense cells OUTSIDE these regions get massing-only detail (T2_periphery_urban)
    "core_regions": ["TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-KEE", "TW-ILA"],
    "core_min_share_of_cell_land": 0.5,
}


def to_tm2(g):
    co = shapely.get_coordinates(g)
    x, y = TO_TM2.transform(co[:, 0], co[:, 1])
    return shapely.set_coordinates(g, np.column_stack([x, y]))


# ---------------------------------------------------------------------------------------------- geography
def load_land():
    rows = duckdb.connect().execute(f"select country, region, name, wkb from read_parquet('{(W / 'land.parquet').as_posix()}') order by region").fetchall()
    tw, foreign = {}, []
    for c, r, n, wkb in rows:
        g = shapely.make_valid(to_tm2(shapely.from_wkb(bytes(wkb))))
        (tw.__setitem__(r, (n, g)) if c == "TW" else foreign.append((c, r, n, g)))
    tw_all = unary_union([g for _, g in tw.values()])
    parts = sorted(shapely.get_parts(tw_all), key=lambda p: -p.area)
    return tw, foreign, parts[0], shapely.union_all(parts[1:])


# ---------------------------------------------------------------------------------------------- terrain
def dtm_mosaic(spec, factor=4):
    """Decimated (factor x factor block nanmean) mosaic of the cached z13 tiles covering the world."""
    from fetch_dtm_tiles import tiles_for
    tl = tiles_for(spec)
    xs, ys = [t[0] for t in tl], [t[1] for t in tl]
    X0, Y0, X1, Y1 = min(xs), min(ys), max(xs), max(ys)
    s = 256 // factor
    mos = np.full(((Y1 - Y0 + 1) * s, (X1 - X0 + 1) * s), np.nan, dtype=np.float32)
    for x, y in tl:
        fpath = DTM_CACHE / f"{x}_{y}.png"
        if not fpath.exists():  # outside the fetched world (map context margins only)
            continue
        raw = fpath.read_bytes()
        rgb = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.float64)
        z = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0
        z[z < -1000] = np.nan
        with np.errstate(all="ignore"):
            zb = np.nanmean(z.reshape(s, factor, s, factor), axis=(1, 3))
        mos[(y - Y0) * s:(y - Y0 + 1) * s, (x - X0) * s:(x - X0 + 1) * s] = zb
    return mos, (X0, Y0, s), len(tl)


def sample_dtm(mos, meta, lon, lat):
    X0, Y0, s = meta
    n = 2.0 ** Z * s
    px = (lon + 180.0) / 360.0 * n - X0 * s
    py = (1.0 - np.arcsinh(np.tan(np.radians(lat))) / np.pi) / 2.0 * n - Y0 * s
    ix, iy = np.floor(px).astype(int), np.floor(py).astype(int)
    ok = (ix >= 0) & (iy >= 0) & (ix < mos.shape[1]) & (iy < mos.shape[0])
    out = np.full(len(lon), np.nan, dtype=np.float32)
    out[ok] = mos[iy[ok], ix[ok]]
    return out


def inland_holes(xv, yv, ev, land, grid_shape, sample_km2, min_coast_m=2000.0, zero_m=0.5, min_component_km2=4.0,
                 open_iter=2):
    """DTM data holes on land: samples > min_coast_m from the coast with NODATA or |z| < zero_m, kept only where they
    form a THICK component (survives a binary opening of `open_iter` samples, i.e. wider than ~1.25 km at 250 m
    sampling) of at least min_component_km2. Rivers / canals / lagoon strips inside the admin land polygon are
    genuinely ~0 m and thin, so they are reported separately, not as holes, regardless of their length."""
    from scipy import ndimage
    cand = shapely.contains_xy(land, xv, yv) & (np.isnan(ev) | (np.abs(ev) < zero_m))
    idx = np.nonzero(cand)[0]
    far = np.zeros(len(xv), bool)
    if len(idx):
        d = shapely.distance(shapely.points(xv[idx], yv[idx]), land.boundary)
        far[idx[d > min_coast_m]] = True
    far2d = far.reshape(grid_shape)
    # thin features (rivers, canals, lagoon strips) are removed by an opening of `open_iter` samples, however long
    # they are; thick blocks survive and are then reconstructed to their full extent inside the candidate mask.
    core = ndimage.binary_opening(far2d, iterations=open_iter)
    lab, n = ndimage.label(core)
    if n == 0:
        return np.zeros(len(xv), bool), far
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1)) * sample_km2
    seeds = np.isin(lab, np.nonzero(sizes >= min_component_km2)[0] + 1)
    keep = ndimage.binary_propagation(seeds, mask=far2d) if seeds.any() else seeds
    return keep.ravel(), far & ~keep.ravel()


def hole_components(hole, elev, on_land, GX, GY, sm, ring_m=1000.0):
    """Describe each hole component: area, lon/lat bbox and the median elevation of the land ring around it.
    High surroundings => data gap in the DTM; surroundings near 0 m => genuinely low ground (e.g. reclamation)."""
    from scipy import ndimage
    lab, n = ndimage.label(hole.reshape(GX.shape))
    out = []
    k = int(round(ring_m / sm))
    for i in range(1, n + 1):
        m = lab == i
        ring = ndimage.binary_dilation(m, iterations=k) & ~m & on_land.reshape(GX.shape)
        er = elev.reshape(GX.shape)[ring]
        er = er[~np.isnan(er)]
        xs, ys = GX[m], GY[m]
        lo0, la0 = TO_LL.transform(xs.min(), ys.min())
        lo1, la1 = TO_LL.transform(xs.max(), ys.max())
        med = float(np.median(er)) if len(er) else None
        out.append({"area_km2": round(float(m.sum()) * sm * sm / 1e6, 1),
                    "bbox_lonlat": [round(lo0, 3), round(la0, 3), round(lo1, 3), round(la1, 3)],
                    "surrounding_land_median_elev_m": None if med is None else round(med, 1),
                    "interpretation": ("DTM data gap (surrounding terrain is high)" if med is not None and med > 20 else
                                       "low-lying land near 0 m (coastline/reclamation vs DTM); verify, not necessarily a gap")})
    return sorted(out, key=lambda c: -c["area_km2"])


# ---------------------------------------------------------------------------------------------- buildings
def load_overture():
    df = duckdb.connect().execute(
        f"select id, cx, cy, height, num_floors, area_m2, src, is_underground from read_parquet('{(W / 'ovt_world_band*.parquet').as_posix()}')").fetchnumpy()

    def col(a, fill):
        return np.ma.filled(a, fill) if np.ma.isMaskedArray(a) else np.asarray(a)
    h = col(np.ma.asarray(df["height"]).astype(float), np.nan).astype(float)
    f = col(np.ma.asarray(df["num_floors"]).astype(float), np.nan).astype(float)
    x, y = TO_TM2.transform(np.asarray(df["cx"], float), np.asarray(df["cy"], float))
    h_present, f_present = ~np.isnan(h), ~np.isnan(f)
    h_valid = h_present & (h >= heights.MIN_M) & (h <= heights.MAX_M)
    f_valid = f_present & (f >= 1) & (f <= 150) & (f * heights.FLOOR_M >= heights.MIN_M) & (f * heights.FLOOR_M <= heights.MAX_M)
    cat = np.where(h_valid, "valid_height",
          np.where(f_valid, "valid_floors_only",
          np.where(h_present | f_present, "present_but_invalid", "missing")))
    return {"id": np.asarray(df["id"]), "lon": np.asarray(df["cx"], float), "lat": np.asarray(df["cy"], float),
            "x": np.asarray(x), "y": np.asarray(y), "area": np.asarray(df["area_m2"], float), "cat": cat,
            "underground": col(df["is_underground"], False).astype(bool),
            "h_present": h_present, "h_valid": h_valid, "f_present": f_present, "f_valid": f_valid}


def load_wfs_slim():
    cache = W / "wfs_slim.npz"
    if cache.exists():
        d = np.load(cache)
        return {k: d[k] for k in d.files}
    xs, ys, ar = [], [], []
    for line in (REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson").open(encoding="utf-8"):
        r = json.loads(line)
        g = shape(r["geometry"])
        ring = np.asarray(r["geometry"]["coordinates"][0] if r["geometry"]["type"] == "Polygon" else r["geometry"]["coordinates"][0][0])
        xs.append(ring[:, 0].mean()); ys.append(ring[:, 1].mean()); ar.append(abs(g.area))
    d = {"x": np.array(xs), "y": np.array(ys), "area": np.array(ar)}
    np.savez_compressed(cache, **d)
    return d


# ---------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=Path, default=REPO / "worlds/north_taiwan_224.json")
    ap.add_argument("--tiers", type=Path, help="JSON overriding DEFAULT_TIERS")
    ap.add_argument("--sample-m", type=float, default=250.0)
    a = ap.parse_args()
    spec = WorldSpec.load(a.world)
    T = dict(DEFAULT_TIERS) | (json.loads(a.tiers.read_text()) if a.tiers else {})
    x0, y0, x1, y1 = spec.bounds_tm2
    wb = box(x0, y0, x1, y1)
    tw, foreign, main_island, islands = load_land()
    tw_land = shapely.union(main_island, islands)
    shapely.prepare(tw_land)
    coast = tw_land.boundary
    feats = json.loads((REPO / "data/ntw/world/features.json").read_text(encoding="utf-8"))["features"]
    for f in feats:
        if "lon" in f:
            f["x"], f["y"] = TO_TM2.transform(f["lon"], f["lat"])
    xin = json.loads((REPO / "data/ntw/world/xinyi_compat.json").read_text(encoding="utf-8"))
    xin_cell = set(xin["placement"]["world_cells_8km"])

    # terrain samples
    mos, meta, ntiles = dtm_mosaic(spec)
    sm = a.sample_m
    gx = np.arange(x0 + sm / 2, x1, sm)
    gy = np.arange(y0 + sm / 2, y1, sm)
    GX, GY = np.meshgrid(gx, gy)
    lon, lat = TO_LL.transform(GX.ravel(), GY.ravel())
    elev = sample_dtm(mos, meta, np.asarray(lon), np.asarray(lat))
    on_land = shapely.contains_xy(tw_land, GX.ravel(), GY.ravel())
    dtm_valid = ~np.isnan(elev)
    hole, low_water = inland_holes(GX.ravel(), GY.ravel(), elev, tw_land, GX.shape, sm * sm / 1e6)
    elev_clean = np.where(hole, np.nan, elev)  # holes never enter elevation statistics
    agree = float(((on_land == dtm_valid)).mean())

    ovt = load_overture()
    wfs = load_wfs_slim()
    tpe = tw["TW-TPE"][1]
    shapely.prepare(tpe)
    o_in_world = (ovt["x"] >= x0) & (ovt["x"] < x1) & (ovt["y"] >= y0) & (ovt["y"] < y1) & ~ovt["underground"]
    o_in_tpe = shapely.contains_xy(tpe, ovt["x"], ovt["y"])
    use_ovt = o_in_world & ~o_in_tpe
    # exact partition: WFS inside the Taipei land polygon, Overture outside it (no double counting at the border)
    w_in_tpe = shapely.contains_xy(tpe, wfs["x"], wfs["y"])
    w_in_world = (wfs["x"] >= x0) & (wfs["x"] < x1) & (wfs["y"] >= y0) & (wfs["y"] < y1) & w_in_tpe

    c = spec.cell_m
    nx, ny = spec.cells_xy

    def cell_of(xv, yv):
        return (np.floor((xv - x0) / c).astype(int), np.floor((yv - y0) / c).astype(int))
    agg = defaultdict(lambda: Counter())
    oc, orow = cell_of(ovt["x"][use_ovt], ovt["y"][use_ovt])
    for i, j, ar, ct in zip(oc, orow, ovt["area"][use_ovt], ovt["cat"][use_ovt]):
        k = agg[(i, j)]
        k["ovt"] += 1; k["area"] += ar; k[ct] += 1
    wc, wr = cell_of(wfs["x"][w_in_world], wfs["y"][w_in_world])
    for i, j, ar in zip(wc, wr, wfs["area"][w_in_world]):
        k = agg[(i, j)]
        k["wfs"] += 1; k["area"] += ar; k["valid_height_wfs"] += 1
    sample_cell = cell_of(GX.ravel(), GY.ravel())
    per_cell_samples = defaultdict(list)
    lin = sample_cell[1] * nx + sample_cell[0]
    order = np.argsort(lin, kind="stable")
    bounds = np.searchsorted(lin[order], np.arange(nx * ny + 1))

    # nearest-coast direction for sea sectors (main island only)
    mi_b = main_island.boundary
    feats_by_cell = defaultdict(list)
    for f in feats:
        if "x" in f and spec.contains(f["x"], f["y"]):
            i, j = int((f["x"] - x0) // c), int((f["y"] - y0) // c)
            feats_by_cell[(i, j)].append(f)

    core_land = unary_union([tw[r][1] for r in T["core_regions"] if r in tw])
    shapely.prepare(core_land)
    cells = []
    for col, row, aix, aiy, (cx0, cy0, cx1, cy1) in spec.cells():
        cb = box(cx0, cy0, cx1, cy1)
        land = shapely.intersection(tw_land, cb)
        land_km2 = land.area / 1e6
        fland = sum(shapely.intersection(g, cb).area for *_, g in foreign) / 1e6
        coast_km = shapely.intersection(coast, cb).length / 1000
        idx = order[bounds[row * nx + col]:bounds[row * nx + col + 1]]
        e = elev_clean[idx][on_land[idx]]
        e = e[~np.isnan(e)]
        hole_km2 = float(hole[idx].sum()) * (sm * sm) / 1e6
        k = agg.get((col, row), Counter())
        nb = k["ovt"] + k["wfs"]
        built_frac = (k["area"] / 1e6) / land_km2 if land_km2 > 0.01 else 0.0
        cid = spec.cell_id(aix, aiy)
        site = [f["name"] for f in feats_by_cell.get((col, row), []) if f["role"] in T["key_site_roles"] and f["tier"] in T["key_site_tiers"]]
        mean_e = float(e.mean()) if len(e) else None
        core = land_km2 > 0 and shapely.intersection(core_land, cb).area / 1e6 >= T["core_min_share_of_cell_land"] * land_km2
        land_frac = land_km2 / (c * c / 1e6)
        if land_frac < T["sea_max_land_frac"] and not site:
            tier, why = "T4_sea", "land < 0.5 %"
        elif cid in xin_cell:
            tier, why = "T1_high", "contains accepted Xinyi L3 sector"
        elif site:
            tier, why = "T1_high", "key site: " + ", ".join(site)
        elif core and (built_frac >= T["t1_min_built_frac"] or nb >= T["t1_min_buildings"]):
            tier, why = "T1_high", f"core theater, built {built_frac:.3f} / {nb} bldgs"
        elif core and (built_frac >= T["t2_min_built_frac"] or nb >= T["t2_min_buildings"]):
            tier, why = "T2_medium", f"core theater, built {built_frac:.3f} / {nb} bldgs"
        elif not core and (built_frac >= T["t2_min_built_frac"] or nb >= T["t2_min_buildings"]):
            tier, why = "T2_periphery_urban", f"outside core theater, built {built_frac:.3f} / {nb} bldgs (massing only)"
        elif mean_e is not None and mean_e >= T["mountain_min_mean_elev_m"]:
            tier, why = "T3_low_mountain", f"mean elev {mean_e:.0f} m"
        else:
            tier, why = "T3_low_rural_coastal", f"built {built_frac:.4f}"
        sector = None
        if land_frac < 0.5:
            ctr = shapely.Point((cx0 + cx1) / 2, (cy0 + cy1) / 2)
            p = shapely.ops.nearest_points(ctr, mi_b)[1]
            ang = math.degrees(math.atan2(ctr.y - p.y, ctr.x - p.x)) % 360
            sector = ("east_pacific" if ang < 45 or ang >= 315 else "north_east_china_sea" if ang < 135
                      else "west_taiwan_strait" if ang < 225 else "south")
        cells.append({
            "cell_id": cid, "col": col, "row": row, "abs_ix": aix, "abs_iy": aiy, "bounds_epsg3826": [cx0, cy0, cx1, cy1],
            "land_km2": round(land_km2, 3), "foreign_land_km2": round(fland, 3), "sea_km2": round(c * c / 1e6 - land_km2 - fland, 3),
            "coastline_km": round(coast_km, 2),
            "elev_mean_m": None if mean_e is None else round(mean_e, 1), "elev_max_m": None if not len(e) else round(float(e.max()), 1),
            "elev_p90_m": None if not len(e) else round(float(np.percentile(e, 90)), 1),
            "share_land_above_1000m": None if not len(e) else round(float((e > 1000).mean()), 3),
            "dtm_hole_km2": round(hole_km2, 2),
            "buildings_best": int(nb), "buildings_wfs": int(k["wfs"]), "buildings_overture": int(k["ovt"]),
            "footprint_km2": round(k["area"] / 1e6, 4), "built_frac_of_land": round(built_frac, 4),
            "ovt_valid_height": int(k["valid_height"]), "ovt_valid_floors_only": int(k["valid_floors_only"]),
            "ovt_present_but_invalid": int(k["present_but_invalid"]), "ovt_missing_height": int(k["missing"]),
            "core_theater": bool(core), "key_sites": site, "tier": tier, "tier_reason": why, "sea_sector": sector,
        })

    # ---- summaries
    def tot(rows, k):
        return round(sum(r[k] for r in rows), 2)
    tiers = defaultdict(lambda: {"cells": 0, "land_km2": 0.0, "sea_km2": 0.0, "buildings_best": 0, "footprint_km2": 0.0})
    for r in cells:
        t = tiers[r["tier"]]
        t["cells"] += 1; t["land_km2"] += r["land_km2"]; t["sea_km2"] += r["sea_km2"]
        t["buildings_best"] += r["buildings_best"]; t["footprint_km2"] += r["footprint_km2"]
    for t in tiers.values():
        for k in ("land_km2", "sea_km2", "footprint_km2"):
            t[k] = round(t[k], 1)
    sea_sectors = defaultdict(lambda: {"cells": 0, "sea_km2": 0.0})
    for r in cells:
        if r["sea_sector"]:
            s = sea_sectors[r["sea_sector"]]
            s["cells"] += 1; s["sea_km2"] = round(s["sea_km2"] + r["sea_km2"], 1)
    regions = {}
    for code, (name, g) in sorted(tw.items()):
        inside = shapely.intersection(g, wb).area / 1e6
        if inside < 0.5:
            continue
        shapely.prepare(g)
        if code == "TW-TPE":
            nbld, src = int((shapely.contains_xy(g, wfs["x"], wfs["y"]) & w_in_world).sum()), "taipei_wfs"
            oc_ = None
        else:
            m = use_ovt & shapely.contains_xy(g, ovt["x"], ovt["y"])
            nbld, src = int(m.sum()), "overture_lower_bound"
            oc_ = {k: int((ovt["cat"][m] == k).sum()) for k in ("valid_height", "valid_floors_only", "present_but_invalid", "missing")}
        regions[code] = {"name": name, "land_km2_total": round(g.area / 1e6, 1), "land_km2_in_world": round(inside, 1),
                         "pct_in_world": round(100 * inside / (g.area / 1e6), 1), "buildings": nbld, "building_source": src,
                         "overture_height_validity": oc_}
    # L0 32 km blocks
    l0 = defaultdict(lambda: {"land_km2": 0.0, "sea_km2": 0.0, "buildings_best": 0, "tiers": Counter()})
    f = int(32000 // c)
    for r in cells:
        b = l0[(r["col"] // f, r["row"] // f)]
        b["land_km2"] += r["land_km2"]; b["sea_km2"] += r["sea_km2"]; b["buildings_best"] += r["buildings_best"]; b["tiers"][r["tier"]] += 1
    l0_rows = [{"block": f"L0_{i}_{j}", "col": i, "row": j, "land_km2": round(v["land_km2"], 1), "sea_km2": round(v["sea_km2"], 1),
                "buildings_best": v["buildings_best"], "tiers": dict(v["tiers"])} for (i, j), v in sorted(l0.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
    # edge-omission / border QA (review item 4): Phase-1 vs Phase-2A selection for the 7 Phase-1 regions
    p1 = json.loads((REPO / "data/ntw/coverage_manifest.json").read_text(encoding="utf-8"))
    theater = json.loads((REPO / "data/ntw/theater_regions.json").read_text(encoding="utf-8"))
    qa = {}
    for r1, rt in zip(p1["regions"], theater["regions"]):
        full = tw[rt["iso"]][1]
        simp = to_tm2(shape(rt["boundary_simplified_150m"]))
        shapely.prepare(full); shapely.prepare(simp)
        sel = ~ovt["underground"] | ovt["underground"]
        in_full = shapely.contains_xy(full, ovt["x"], ovt["y"]) & sel
        in_simp = shapely.contains_xy(simp, ovt["x"], ovt["y"]) & sel
        qa[rt["key"]] = {"phase1_bbox_contained_simplified": r1["buildings"], "phase2a_centroid_fullres": int(in_full.sum()),
                         "phase2a_centroid_simplified": int(in_simp.sum()), "border_flips_simplified_vs_full": int((in_full ^ in_simp).sum()),
                         "phase1_present_based_fallback": r1["fallback_needed"],
                         "phase2a_validated_no_usable_height": int((in_full & ~ovt["h_valid"] & ~ovt["f_valid"]).sum()),
                         "phase2a_present_but_invalid": int((in_full & (ovt["cat"] == "present_but_invalid")).sum())}
    world_land = sum(r["land_km2"] for r in cells)
    summary = {
        "world": spec.summary(), "tier_rules": T, "tiers": dict(tiers), "sea_sectors": dict(sea_sectors),
        "totals": {"area_km2": spec.size_m[0] * spec.size_m[1] / 1e6, "tw_land_km2": round(world_land, 1),
                   "foreign_land_km2": tot(cells, "foreign_land_km2"), "sea_km2": tot(cells, "sea_km2"),
                   "land_pct": round(100 * world_land / (spec.size_m[0] * spec.size_m[1] / 1e6), 2),
                   "coastline_km": round(shapely.intersection(coast, wb).length / 1000, 1),
                   "buildings_best": int(sum(r["buildings_best"] for r in cells)),
                   "buildings_wfs_taipei": int(sum(r["buildings_wfs"] for r in cells)),
                   "wfs_records_excluded_outside_overture_taipei_polygon": int((~w_in_tpe).sum()),
                   "buildings_overture_outside_taipei": int(sum(r["buildings_overture"] for r in cells)),
                   "overture_height_validity_world": {k: int(sum(r[f"ovt_{k}"] for r in cells)) for k in ("valid_height", "valid_floors_only", "present_but_invalid", "missing_height")}},
        "admin_regions_in_world": regions, "l0_blocks_32km": l0_rows,
        "terrain_qa": {"dtm_tiles": ntiles, "sample_spacing_m": sm, "samples": int(len(elev)),
                       "land_polygon_vs_dtm_valid_agreement": round(agree, 4),
                       "land_samples_without_dtm": int((on_land & ~dtm_valid).sum()),
                       "dtm_valid_samples_outside_land_polygon": int((~on_land & dtm_valid).sum()),
                       "max_land_elev_m": round(float(np.nanmax(elev[on_land])), 1),
                       "dtm_valid_outside_land_abs_lt_0p5m_share": round(float((np.abs(elev[~on_land & dtm_valid]) < 0.5).mean()), 3),
                       "finding_sea_encoded_as_zero": "the DTM mirror stores sea within ~6 km of the coast as 0.0 m (not NODATA); "
                                                      "land/sea must come from the vector coastline, never from DTM validity",
                       "land_samples_without_dtm_on_main_island": int((on_land & ~dtm_valid & shapely.contains_xy(main_island, GX.ravel(), GY.ravel())).sum()),
                       "inland_dtm_hole": {
                           "definition": "land sample > 2 km from the coast with DTM NODATA or |z| < 0.5 m, in a thick (> ~1.25 km wide) component >= 4 km2",
                           "samples": int(hole.sum()), "area_km2": round(float(hole.sum()) * sm * sm / 1e6, 1),
                           "bbox_lonlat": ([round(float(v), 3) for v in (*TO_LL.transform(GX.ravel()[hole].min(), GY.ravel()[hole].min()),
                                                                         *TO_LL.transform(GX.ravel()[hole].max(), GY.ravel()[hole].max()))]
                                           if hole.any() else None),
                           "cells": sorted({spec.cell_id(*spec.cell_index_abs(px_, py_)) for px_, py_ in zip(GX.ravel()[hole], GY.ravel()[hole])}),
                           "impact": "terrain in these cells must not be generated from this mirror until the official TGOS DTM sheet is checked",
                           "small_low_lying_components_not_holes_km2": round(float(low_water.sum()) * sm * sm / 1e6, 1),
                           "components": hole_components(hole, elev_clean, on_land, GX, GY, sm)},
                       "land_share_above_1000m": round(float((elev_clean[on_land & ~np.isnan(elev_clean)] > 1000).mean()), 3),
                       "land_share_above_2000m": round(float((elev_clean[on_land & ~np.isnan(elev_clean)] > 2000).mean()), 3),
                       "offshore": "no bathymetry: sea is 0.0 m within ~6 km of the coast and NODATA beyond; a sea plane / bathymetry source is a separate decision"},
        "edge_and_validity_qa_phase1_regions": qa,
        "notes": "Overture counts are lower bounds; Taipei uses WFS. Tiers are a planning classification, not a runtime result.",
    }
    name = spec.name
    od = REPO / "data/ntw/world"
    gj = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3826"}},
          "features": [{"type": "Feature", "properties": {k: v for k, v in r.items() if k != "bounds_epsg3826"},
                        "geometry": mapping(box(*r["bounds_epsg3826"]))} for r in cells]}
    (od / f"{name}_cells_epsg3826.geojson").write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    dens = []
    for (ax_, ay_), (bx_, by_) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        for t in np.linspace(0, 1, 57)[:-1]:
            dens.append([round(v, 6) for v in TO_LL.transform(ax_ + t * (bx_ - ax_), ay_ + t * (by_ - ay_))])
    dens.append(dens[0])
    corners = {k: [round(v, 6) for v in TO_LL.transform(px, py)] for k, (px, py) in
               {"SW": (x0, y0), "SE": (x1, y0), "NE": (x1, y1), "NW": (x0, y1)}.items()}
    bj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": name, "crs": "EPSG:3826", **spec.summary(), "corners_lonlat": corners},
         "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}},
        {"type": "Feature", "properties": {"name": name + "_outline_wgs84_densified", "crs": "EPSG:4326",
                                           "note": "TM2 straight edges are slightly curved in lon/lat; 4 km densification"},
         "geometry": {"type": "Polygon", "coordinates": [dens]}}]}
    (od / f"{name}_bounds.geojson").write_text(json.dumps(bj, ensure_ascii=False), encoding="utf-8")
    (od / f"{name}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("totals", "tiers", "sea_sectors", "terrain_qa")}, ensure_ascii=False, indent=1))
    print(json.dumps(summary["edge_and_validity_qa_phase1_regions"], ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
