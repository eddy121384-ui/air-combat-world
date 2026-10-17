"""Region-wide land-cover masks for native UE PCG/Foliage/WP, not a renderer.

prepare: pin/download upstream, create the committed 20 m source clip + vector coast.
build: entirely offline; reclassify, label review rules, export native textures/CSV/GIS.
Pixels describe land cover, NOT surveyed canopy density, species or tree positions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, transform_geom
from rasterio.windows import Window
from scipy.ndimage import distance_transform_edt
from shapely import make_valid
from shapely.geometry import box, mapping, shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from world_spec import WorldSpec  # noqa: E402

CONFIG = REPO / "worlds/vegetation/north_taiwan_forest_v1.json"
DEFAULT_OUT = REPO / "data/ntw/forest/coverage_v1"
CLASSES = {0: "unknown", 1: "tree_cover_candidate", 2: "grass_or_rangeland",
           3: "agriculture", 4: "urban", 5: "water", 6: "bare",
           7: "flooded_vegetation", 8: "other_open_shrub", 9: "snow_ice"}
COLORS = [(210, 75, 195), (43, 106, 67), (174, 194, 108), (221, 182, 83),
          (174, 103, 102), (57, 99, 137), (190, 180, 158), (87, 165, 161),
          (172, 155, 111), (238, 241, 245)]
# Preserve 2021 code 11 (rangeland) as mixed open cover, never forest.
ESRI_TO_CLASS = {0: 0, 1: 5, 2: 1, 3: 2, 4: 7, 5: 3,
                 6: 8, 7: 4, 8: 6, 9: 9, 10: 0, 11: 2}
FLAGS = {1: "unknown_cover", 2: "non_tree_cover", 4: "coast_review",
         8: "terrain_BLOCKED_cell", 16: "accepted_Xinyi_hold",
         32: "unresolved_species", 64: "outside_flyable_core",
         128: "forest_edge_clearance"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def png_bytes(array):
    f = io.BytesIO()
    Image.fromarray(array).save(f, format="PNG", compress_level=9)
    return f.getvalue()


def zip_write(z, name, data):
    # Stable archive timestamps/permissions; byte-identical repeat builds.
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    z.writestr(info, data)


def profile(spec, pixel, count=1):
    x0, _, _, y1 = spec.bounds_tm2
    return dict(driver="GTiff", width=int(spec.size_m[0] / pixel), height=int(spec.size_m[1] / pixel),
                count=count, dtype="uint8", crs="EPSG:3826", transform=from_origin(x0, y1, pixel, pixel),
                tiled=True, blockxsize=256, blockysize=256, compress="DEFLATE", zlevel=9)


def validate_config(c, spec):
    p, f, chunk = c["pixel_m"], c["far_pixel_m"], c["runtime_chunk_m"]
    if p <= 0 or f <= 0 or chunk <= 0 or any(v % p for v in (*spec.size_m, spec.cell_m, f, chunk)):
        raise ValueError("Pixel/far/chunk sizes must nest on the world cell grid")
    if spec.cell_m % chunk:
        raise ValueError("Runtime chunks must nest inside existing world cells")
    if min(c["coast_review_m"], c["edge_clearance_m"], c["urban_review_m"]) < 0:
        raise ValueError("Negative review/clearance distance")
    zones = read_json(REPO / c["zones"])
    if tuple(zones["far_field_epsg3826"]) != spec.bounds_tm2:
        raise ValueError("World/zones bounds drift")
    world_box = box(*spec.bounds_tm2)
    for name in ("flyable_epsg3826", "production_epsg3826"):
        b = zones[name]
        if not world_box.covers(box(*b)) or any(v % spec.cell_m for v in b):
            raise ValueError("Zone bounds must be contained and on world cell grid")
    if not box(*zones["production_epsg3826"]).covers(box(*zones["flyable_epsg3826"])):
        raise ValueError("Core not contained in production")
    return zones


def fetch_pinned(meta, path):
    if not path.exists():
        tmp = path.with_suffix(".download")
        with urllib.request.urlopen(meta["url"], timeout=60) as r, tmp.open("wb") as f:
            while chunk := r.read(1024 * 1024):
                f.write(chunk)
        if sha(tmp) != meta["sha256"]:
            tmp.unlink()
            raise ValueError("Upstream checksum mismatch")
        tmp.replace(path)
    if sha(path) != meta["sha256"]:
        raise ValueError(f"Cache checksum mismatch: {path}")


def prepare(c, spec, inputs, cache):
    inputs.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    source, coast = cache / "esri2021.gpkg", cache / "taiwan_land.json"
    fetch_pinned(c["source"], source)
    fetch_pinned(c["coast"], coast)
    coast_data = read_json(coast)
    projected = shape(transform_geom("EPSG:4326", "EPSG:3826", coast_data["geometry"]))
    original_valid = projected.is_valid
    # This simplified third-party coastline has intersecting rings. Repair generically,
    # preserving all polygon parts; retain the raw-source checksum and repair disclosure.
    projected = make_valid(projected)
    clipped = projected.intersection(box(*spec.bounds_tm2).buffer(c["coast_review_m"] * 2))
    output = inputs / "esri2021_20m.tif"
    with rasterio.open(source) as src, rasterio.open(output, "w", **profile(spec, c["pixel_m"])) as dst:
        if src.crs.to_epsg() != 3826 or src.count != 1:
            raise ValueError("Unexpected upstream CRS/bands")
        # Read the categorical base resolution explicitly; do not select a display overview.
        reproject(rasterio.band(src, 1), rasterio.band(dst, 1), src_nodata=src.nodata, dst_nodata=0,
                  resampling=Resampling.mode, warp_mem_limit=256, OVR_LEVEL="NONE")
        dst.set_band_description(1, "Esri_2021_codes_categorical_mode_20m")
    write_json(inputs / "coast_epsg3826.geojson", {
        "type": "Feature", "crs": {"type": "name", "properties": {"name": "EPSG:3826"}},
        "properties": coast_data["properties"], "geometry": mapping(clipped)})
    write_json(inputs / "provenance.json", {
        "source": c["source"], "coast": c["coast"],
        "coast_original_valid": original_valid, "coast_repair": "GEOS make_valid; no part filtering or manual edits",
        "processing": "Full upstream categorical band -> EPSG:3826 20m mode; zero remains unknown, not sea. Coast projected/clipped separately.",
        "world": spec.summary(), "files": {p.name: sha(p) for p in (output, inputs / "coast_epsg3826.geojson")}})


def reclassify(raw, land_or_shore):
    valid = set(map(int, np.unique(raw)))
    if not valid <= ESRI_TO_CLASS.keys():
        raise ValueError(f"Unrecognized land-cover codes: {valid - ESRI_TO_CLASS.keys()}")
    lut = np.zeros(256, dtype=np.uint8)
    for k, v in ESRI_TO_CLASS.items():
        lut[k] = v
    cover = lut[raw]
    # Only missing source OUTSIDE the buffered vector land is inferred ocean.
    # Never override an observed class or call cloud/unknown inland grass/forest.
    ocean = (raw == 0) & ~land_or_shore
    cover[ocean] = 5
    return cover, ocean


def review_layers(cover, coast, urban_near, edge_near, xinyi, stats, zone, yms, c):
    forest = cover == 1
    rule = np.zeros(cover.shape, dtype=np.uint8)
    rule[forest] = 5
    peak = stats["elev_max_m"]  # 250m sampled CELL summary; not per-pixel elevation.
    if peak is not None and stats["dtm_hole_km2"] == 0:
        if peak <= c["lowland_cell_sample_max_m"]:
            rule[forest] = 1
        elif peak >= c["montane_cell_sample_max_m"]:
            rule[forest] = 3
    rule[forest & urban_near] = 6
    rule[forest & yms] = 2
    rule[forest & coast] = 4
    flags = np.zeros(cover.shape, dtype=np.uint8)
    for mask, bit in ((cover == 0, 1), (~forest, 2), (coast, 4), (xinyi, 16),
                      (forest & (rule != 1), 32), (forest & edge_near, 128)):
        flags[mask] |= bit
    # Whole-cell hold is deliberately conservative; no precise missing-DEM polygon available.
    if stats["dtm_hole_km2"] > 0 or (peak is None and stats["land_km2"] > 0):
        flags[:] |= 8
    if zone != "flyable":
        flags[:] |= 64
    interior = forest & ~edge_near
    reviewable = forest & (rule == 1) & (flags == 0)
    rgba = np.stack([forest * 255, interior * 255, reviewable * 255, (cover != 0) * 255], axis=-1).astype(np.uint8)
    return rule, flags, rgba


def raster_mask(geometry, transform, size, all_touched=False):
    if geometry.is_empty:
        return np.zeros(size, dtype=bool)
    return rasterize([(mapping(geometry), 1)], out_shape=size, transform=transform,
                     all_touched=all_touched, dtype="uint8").astype(bool)


def zone_for(bounds, zones):
    b = box(*bounds)
    if box(*zones["flyable_epsg3826"]).covers(b):
        return "flyable"
    if box(*zones["production_epsg3826"]).covers(b):
        return "production_halo"
    return "far_field"


def write_overview(out, cover_small, far, cells, zones, spec, c):
    # Fixed-size map and legend; no external images/fonts or map services.
    size, top, left, gap = 1008, 110, 36, 36
    canvas = Image.new("RGB", (size * 2 + left * 2 + gap, size + top + 160), (22, 29, 36))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=17)
    title = ImageFont.load_default(size=28)
    draw.text((left, 18), f"North Taiwan Forest Coverage v1 | {spec.size_m[0]/1000:g} x {spec.size_m[1]/1000:g} km development bounds", font=title, fill="white")
    draw.text((left, 58), "2021 Esri land-cover derivative | 20 m categorical grid | species NOT surveyed | north up", font=font, fill="#bdcbd6")
    rgb = np.asarray(COLORS, dtype=np.uint8)[cover_small]
    density = np.stack([30 + far // 4, 42 + far // 2, 47 + far // 6], -1)
    for k, array in enumerate((rgb, density)):
        xoff = left + k * (size + gap)
        canvas.paste(Image.fromarray(array).resize((size, size), Image.Resampling.NEAREST), (xoff, top))
        def xy(e, n):
            return xoff + (e - spec.sw_tm2[0]) / spec.size_m[0] * size, top + (spec.bounds_tm2[3] - n) / spec.size_m[1] * size
        for bounds, color in ((zones["production_epsg3826"], "#e5ac42"), (zones["flyable_epsg3826"], "#ffffff")):
            x0, y0, x1, y1 = bounds
            draw.rectangle([xy(x0, y1), xy(x1, y0)], outline=color, width=2)
        for f in cells:
            if f["properties"]["terrain_hold"]:
                b = shape(f["geometry"]).bounds
                draw.rectangle([xy(b[0], b[3]), xy(b[2], b[1])], outline="#ff52ee", width=2)
        yms = c["yangmingshan_review_envelope_epsg3826"]
        draw.rectangle([xy(yms[0], yms[3]), xy(yms[2], yms[1])], outline="#c6e5ff", width=1)
        labels = {"臺灣桃園國際機場": "Taoyuan Airport", "臺北松山機場": "Taipei Songshan",
                  "空軍新竹基地": "Hsinchu Airbase", "基隆港": "Keelung Port", "七星山": "Qixing Mt"}
        project = Transformer.from_crs(4326, 3826, always_xy=True)
        for point in read_json(REPO / "data/ntw/world/features.json")["features"]:
            if point["name"] in labels and "lon" in point:
                xx, yy = xy(*project.transform(point["lon"], point["lat"]))
                draw.ellipse((xx-3, yy-3, xx+3, yy+3), fill="white")
                draw.text((xx+7, yy-17), labels[point["name"]], font=font, fill="white", stroke_width=2, stroke_fill="#162028")
        draw.text((xoff + 10, top + 10), "N ^", font=font, fill="white")
        draw.text((xoff, top + size + 12), "Land-cover classes" if k == 0 else "160 m tree-cover area fraction (not measured canopy closure)", font=font, fill="white")
    y = top + size + 48
    for i, (code, label) in enumerate(CLASSES.items()):
        x = left + (i % 5) * 410
        yy = y + (i // 5) * 30
        draw.rectangle((x, yy + 3, x + 16, yy + 19), fill=COLORS[code])
        draw.text((x + 23, yy), label, font=font, fill="white")
    draw.text((left, y + 68), "White: flyable 112 km | amber: production 128 km | magenta cells: terrain HOLD | pale blue: Yangmingshan review envelope", font=font, fill="#bdcbd6")
    canvas.save(out / "overview.png")


def write_core_review(out, zones, c):
    """Readable core-scale inspection, keeping open land visible beside review rules."""
    n = 1400
    with rasterio.open(out / "coverage.tif") as src:
        window = rasterio.windows.from_bounds(*zones["flyable_epsg3826"], src.transform)
        a = src.read([1, 2, 3], window=window, out_shape=(3, n, n), resampling=Resampling.nearest)
    palette = np.asarray([(33, 45, 53), (103, 154, 77), (87, 171, 202), (127, 111, 173),
                          (220, 168, 86), (135, 144, 137), (208, 125, 147)], np.uint8)
    colors = np.asarray(COLORS, np.uint8)[a[0]]
    rules = palette[a[1]]
    rules[(a[2] & 16) != 0] = [255, 255, 255]
    image = Image.new("RGB", (2*n+72, n+170), (22, 29, 36))
    image.paste(Image.fromarray(colors), (24, 65))
    image.paste(Image.fromarray(rules), (48+n, 65))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    draw.text((24, 18), "Flyable core | land cover (20 m data; display subsampled)", font=font, fill="white")
    draw.text((48+n, 18), "Review rules | NO surveyed species or default spawning", font=font, fill="white")
    labels = ["non-tree", "lowland REVIEW", "Yangmingshan REVIEW", "montane unresolved", "coast unresolved", "other unresolved", "urban-edge unresolved"]
    for i, label in enumerate(labels):
        xx = 24 + (i % 4)*710
        yy = n+85 + (i//4)*32
        draw.rectangle((xx, yy+3, xx+18, yy+21), fill=tuple(palette[i]))
        draw.text((xx+26, yy), label, font=font, fill="white")
    draw.text((24, n+148), "North up | white in right panel = accepted Xinyi hold | Yangmingshan open cover is retained, not converted to forest", font=ImageFont.load_default(size=16), fill="#bdcbd6")
    image.save(out / "core_review.png")


def build(c, spec, inputs, out):
    zones = validate_config(c, spec)
    provenance = read_json(inputs / "provenance.json")
    if provenance["source"] != c["source"] or provenance["coast"] != c["coast"]:
        raise ValueError("Prepared source provenance/config drift")
    for name, digest in provenance["files"].items():
        if sha(inputs / name) != digest:
            raise ValueError(f"Prepared input checksum mismatch: {name}")
    if provenance["world"]["bounds_epsg3826"] != list(spec.bounds_tm2):
        raise ValueError("Prepared source world bounds drift")
    land = shape(read_json(inputs / "coast_epsg3826.geojson")["geometry"])
    coastal = land.boundary.buffer(c["coast_review_m"])
    land_or_shore = land.buffer(c["coast_review_m"])
    yms = box(*c["yangmingshan_review_envelope_epsg3826"])
    xinyi = shape(read_json(REPO / c["xinyi_protected"])["features"][0]["geometry"])
    stats = {f["properties"]["cell_id"]: f["properties"] for f in read_json(REPO / c["cell_stats"])["features"]}
    out.mkdir(parents=True, exist_ok=True)
    p, f = c["pixel_m"], c["far_pixel_m"]
    n, factor = int(spec.cell_m / p), int(f / p)
    halo = int(np.ceil(max(c["edge_clearance_m"], c["urban_review_m"]) / p)) + 2
    far = np.zeros((int(spec.size_m[1] / f), int(spec.size_m[0] / f)), dtype=np.uint8)
    small = np.zeros_like(far)
    totals, records, features, chunks = {}, [], [], []
    with rasterio.open(inputs / "esri2021_20m.tif") as src, \
            rasterio.open(out / "coverage.tif", "w", **profile(spec, p, 4)) as dst, \
            zipfile.ZipFile(out / "unreal_masks.zip", "w") as bundle:
        if src.crs.to_epsg() != 3826 or src.transform != dst.transform or src.shape != dst.shape:
            raise ValueError("Prepared input grid drift")
        # Four categorical bands are NOT RGBA (band 4 is an evidence flag, not opacity).
        dst.colorinterp = tuple(rasterio.enums.ColorInterp.undefined for _ in range(4))
        for b, name in enumerate(("landcover_class", "review_rule", "restriction_bits", "ocean_inferred_from_vector"), 1):
            dst.set_band_description(b, name)
        nx, ny = spec.cells_xy
        for col, row, ix, iy, bounds in spec.cells():
            cell_id, zone = spec.cell_id(ix, iy), zone_for(bounds, zones)
            props = stats[cell_id]
            px, py = col * n, (ny - row - 1) * n
            trans = from_origin(bounds[0] - halo * p, bounds[3] + halo * p, p, p)
            size = (n + 2 * halo, n + 2 * halo)
            raw = src.read(1, window=Window(px - halo, py - halo, size[1], size[0]), boundless=True, fill_value=0)
            mask_land = raster_mask(land_or_shore.intersection(box(*bounds).buffer(halo*p)), trans, size)
            cover, ocean = reclassify(raw, mask_land)
            forest = cover == 1
            # Halo reads make edge/urban decisions independent of partition seams.
            edge_near = distance_transform_edt(forest) * p <= c["edge_clearance_m"]
            urban = cover == 4
            urban_near = distance_transform_edt(~urban) * p <= c["urban_review_m"] if urban.any() else np.zeros(size, bool)
            tile = (slice(halo, -halo), slice(halo, -halo))
            cover, ocean = cover[tile], ocean[tile]
            t = from_origin(bounds[0], bounds[3], p, p)
            cs = (n, n)
            rule, flags, rgba = review_layers(cover,
                raster_mask(coastal.intersection(box(*bounds)), t, cs, True), urban_near[tile], edge_near[tile],
                raster_mask(xinyi.intersection(box(*bounds)), t, cs, True), props, zone,
                raster_mask(yms.intersection(box(*bounds)), t, cs), c)
            dst.write(np.stack([cover, rule, flags, ocean.astype(np.uint8)]), window=Window(px, py, n, n))
            for name, arr in (("masks", rgba), ("classes", cover), ("rules", rule)):
                zip_write(bundle, f"cells/{cell_id}/{name}.png", png_bytes(arr))
            counts = np.bincount(cover.ravel(), minlength=len(CLASSES))
            zone_counts = totals.setdefault(zone, np.zeros(len(CLASSES), dtype=np.int64))
            zone_counts += counts
            # Far layer aggregates CLASS AREA, not alpha filtering or invented trees.
            frac = (cover == 1).reshape(n // factor, factor, n // factor, factor).mean(axis=(1, 3))
            fy, fx = py // factor, px // factor
            far[fy:fy+n//factor, fx:fx+n//factor] = np.rint(frac * 255).astype(np.uint8)
            # Overview only, choose centre class to avoid small multi-class mode work.
            small[fy:fy+n//factor, fx:fx+n//factor] = cover[factor//2::factor, factor//2::factor]
            ue_nw = spec.tm2_to_ue_cm(bounds[0], bounds[3])
            terrain_hold = bool(np.any(flags & 8))
            rec = dict(Name=cell_id, CellId=cell_id, Zone=zone, MaskFile=f"cells/{cell_id}/masks.png",
                       ClassFile=f"cells/{cell_id}/classes.png", RuleFile=f"cells/{cell_id}/rules.png",
                       NWXcm=ue_nw[0], NWYcm=ue_nw[1], SizeCm=spec.cell_m * 100,
                       Pixels=n, TreeCoverKm2=round(int(counts[1]) * p*p/1e6, 6),
                       ReviewableKm2=round(int(np.count_nonzero(rgba[..., 2])) * p*p/1e6, 6),
                       TerrainHold=terrain_hold, DefaultSpawn=False)
            records.append(rec)
            features.append({"type": "Feature", "properties": {**rec, "terrain_hold": terrain_hold,
                "classes_km2": {CLASSES[k]: round(int(counts[k])*p*p/1e6, 6) for k in CLASSES},
                "sampled_cell_max_m": props["elev_max_m"], "rule_counts": {str(k): int(v) for k,v in enumerate(np.bincount(rule.ravel(), minlength=7))}},
                "geometry": mapping(box(*bounds))})
            per = int(spec.cell_m / c["runtime_chunk_m"])
            chunk_px = int(c["runtime_chunk_m"] / p)
            for cy in range(per):
                for cx in range(per):
                    # Same SW indices as build_terrain_cells; texture row goes south from NW.
                    chunks.append(dict(Name=f"{cell_id}_ch{cx}{cy}", CellId=cell_id, ChunkId=f"ch{cx}{cy}",
                        UMin=cx/per, VMin=(per-cy-1)/per, UMax=(cx+1)/per, VMax=(per-cy)/per,
                        PixelX=cx*chunk_px, PixelY=(per-cy-1)*chunk_px, PixelSize=chunk_px))
            if len(records) % 112 == 0:
                print(f"built {len(records)}/{nx*ny} cells", flush=True)
    (out / "far_canopy_density.png").write_bytes(png_bytes(far))
    # A separate validity/terrain gate prevents unknowns or missing terrain being silently deployed.
    with rasterio.open(out / "coverage.tif") as src:
        far_hold = np.zeros_like(far)
        for col, row, ix, iy, bounds in spec.cells():
            px, py = col*n, (spec.cells_xy[1]-row-1)*n
            fl = src.read(3, window=Window(px, py, n, n))
            cl = src.read(1, window=Window(px, py, n, n))
            hold = ((fl & (8 | 16)) != 0) | (cl == 0)
            h = hold.reshape(n//factor, factor, n//factor, factor).any(axis=(1,3))
            far_hold[py//factor:(py+n)//factor, px//factor:(px+n)//factor] = h * 255
    (out / "far_hold.png").write_bytes(png_bytes(far_hold))
    for name, rows in (("cells.csv", records), ("runtime_chunks.csv", chunks)):
        with (out / name).open("w", newline="", encoding="utf-8") as fobj:
            writer = csv.DictWriter(fobj, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    write_json(out / "cells_epsg3826.geojson", {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:3826"}}, "features": features})
    write_overview(out, small, far, features, zones, spec, c)
    write_core_review(out, zones, c)
    summary = {
        "schema": c["schema"], "world": spec.summary(), "pixel_m": p, "far_pixel_m": c["far_pixel_m"],
        "classes": CLASSES, "restriction_bits": FLAGS, "species_rules": c["species_rules"],
        "zone_cells": {z: sum(r["Zone"] == z for r in records) for z in totals},
        "class_area_km2": {z: {CLASSES[k]: round(int(v[k])*p*p/1e6, 6) for k in CLASSES} for z,v in totals.items()},
        "reviewable_lowland_km2": round(sum(r["ReviewableKm2"] for r in records), 6),
        "terrain_hold_cells": [r["CellId"] for r in records if r["TerrainHold"]],
        "default_spawn": False, "engine_validation": "NOT TESTED; data/texture interface only",
        "inputs_sha256": {str(path.relative_to(REPO)): sha(path) for path in [CONFIG, Path(__file__), REPO/"requirements-ntw-forest.txt", REPO/c["world"], REPO/c["zones"], REPO/c["cell_stats"], REPO/c["xinyi_protected"], REPO/"data/ntw/world/features.json", *sorted(inputs.iterdir())] if path.is_file()},
        "masks_rgba": {"R": "2021 tree-cover candidate", "G": "interior tree-cover >40m from nonforest", "B": "core lowland palette REVIEW area, not approved species placement", "A": "known land-cover class (including inferred ocean)"},
        "uv": "u=(E-cell_west)/cell_m; v=(cell_north-N)/cell_m; pixel centres=(col+0.5,row+0.5)/pixels; clamp/nearest/no mipmaps",
        "far_layer": "160m mean area fraction of 20m tree-cover labels. Multiply by 1-far_hold; project to accepted terrain. No generated 3D trees/heights.",
        "official_forest_attempt": c["official_forest_attempt"],
        "outputs_sha256": {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != "manifest.json"}}
    write_json(out / "manifest.json", summary)
    print(json.dumps({"zone_cells": summary["zone_cells"], "reviewable_km2": summary["reviewable_lowland_km2"], "terrain_hold_cells": summary["terrain_hold_cells"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "build"))
    parser.add_argument("--inputs", type=Path, default=DEFAULT_OUT.parent / "inputs_v1")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=REPO / "data/generated/ntw/forest_source")
    args = parser.parse_args()
    c = read_json(CONFIG)
    spec = WorldSpec.load(REPO / c["world"])
    validate_config(c, spec)
    if args.action == "prepare":
        prepare(c, spec, args.inputs, args.cache)
    else:
        build(c, spec, args.inputs, args.out)


if __name__ == "__main__":
    main()
