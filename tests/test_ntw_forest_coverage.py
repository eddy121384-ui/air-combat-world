"""Spatial/source contracts for actual whole-world outputs, plus fail-closed rules."""
import csv
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
from PIL import Image
from pyproj import Transformer
import pytest
import rasterio
from rasterio.windows import Window

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/ntw"))
import forest_coverage as fc

C = fc.read_json(fc.CONFIG)
SPEC = fc.WorldSpec.load(REPO / C["world"])
OUT = fc.DEFAULT_OUT


def layers(cover, **kwargs):
    a = np.asarray(cover, dtype=np.uint8)
    z = np.zeros(a.shape, bool)
    args = dict(cover=a, coast=z, urban_near=z, edge_near=z, xinyi=z,
                stats={"elev_max_m": 500, "dtm_hole_km2": 0, "land_km2": 64},
                zone="flyable", yms=z, c=C)
    args.update(kwargs)
    return fc.review_layers(**args)


def test_source_classes_cloud_and_ocean_are_not_silently_forested():
    raw = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0]], np.uint8)
    land = np.ones(raw.shape, bool)
    land[0, -1] = False
    cover, ocean = fc.reclassify(raw, land)
    assert cover.tolist() == [[0, 5, 1, 2, 7, 3, 8, 4, 6, 9, 0, 2, 5]]
    assert ocean.sum() == 1
    with pytest.raises(ValueError, match="Unrecognized"):
        fc.reclassify(np.array([[42]], np.uint8), np.ones((1, 1), bool))


def test_rules_require_tree_cover_and_never_infer_completed_montane_assets():
    cover = [[1, 2, 3, 4, 5, 6, 7, 0]]
    rule, flags, rgba = layers(cover)
    assert rule.tolist() == [[1, 0, 0, 0, 0, 0, 0, 0]]
    assert np.count_nonzero(rgba[..., 2]) == 1
    rule, flags, rgba = layers(cover, stats={"elev_max_m": 2000, "dtm_hole_km2": 0, "land_km2": 64})
    assert rule[0, 0] == 3 and flags[0, 0] & 32
    assert not rgba[..., 2].any()
    assert all(not r.get("default_spawn", False) for r in C["species_rules"].values())


@pytest.mark.parametrize("gate", ["coast", "urban_near", "edge_near", "xinyi", "yms"])
def test_review_and_protected_masks_remove_available_palette_area(gate):
    rule, flags, rgba = layers([[1]], **{gate: np.ones((1, 1), bool)})
    assert not rgba[..., 2].any()
    assert rgba[..., 0].item() == 255  # evidence retained even when deployment is held
    if gate == "yms":
        assert rule.item() == 2  # never automatically cypress


@pytest.mark.parametrize("zone", ["production_halo", "far_field"])
def test_non_core_does_not_enable_individual_tree_placement(zone):
    _, flags, rgba = layers([[1]], zone=zone)
    assert flags.item() & 64 and not rgba[..., 2].any()


def test_missing_terrain_never_becomes_flat_lowland():
    rule, flags, rgba = layers([[1]], stats={"elev_max_m": None, "dtm_hole_km2": 5, "land_km2": 64})
    assert rule.item() == 5 and flags.item() & 8
    assert not rgba[..., 2].any()


def test_config_rejects_grid_and_bounds_drift():
    for key, value in (("pixel_m", 23), ("far_pixel_m", 150), ("runtime_chunk_m", 1700)):
        with pytest.raises(ValueError):
            fc.validate_config({**C, key: value}, SPEC)


def test_committed_outputs_hashes_and_whole_world_area_balance():
    manifest = fc.read_json(OUT / "manifest.json")
    for name, digest in manifest["outputs_sha256"].items():
        assert fc.sha(OUT / name) == digest, name
    for name, digest in manifest["inputs_sha256"].items():
        assert fc.sha(REPO / name) == digest, name
    assert manifest["zone_cells"] == {"far_field": 528, "production_halo": 60, "flyable": 196}
    for zone, areas in manifest["class_area_km2"].items():
        assert sum(areas.values()) == pytest.approx(manifest["zone_cells"][zone] * (SPEC.cell_m/1000)**2, abs=1e-6)
    gap = {"C+0031+0338", "C+0031+0339", "C+0032+0338", "C+0032+0339"}
    assert gap <= set(manifest["terrain_hold_cells"])
    stats = fc.read_json(REPO / C["cell_stats"])["features"]
    no_height = {f["properties"]["cell_id"] for f in stats
                 if f["properties"]["elev_max_m"] is None and f["properties"]["land_km2"] > 0}
    assert set(manifest["terrain_hold_cells"]) == gap | no_height
    assert manifest["official_forest_attempt"]["used"] is False


def test_every_native_cell_texture_matches_gis_and_conservative_gates():
    rows = list(csv.DictReader((OUT / "cells.csv").open()))
    assert len(rows) == len(set(r["CellId"] for r in rows)) == len(list(SPEC.cells()))
    with rasterio.open(OUT / "coverage.tif") as src, \
            rasterio.open(OUT.parent / "inputs_v1/esri2021_20m.tif") as evidence, \
            zipfile.ZipFile(OUT / "unreal_masks.zip") as bundle:
        assert len(bundle.namelist()) == len(rows) * 3
        for r, (col, row, ix, iy, bounds) in zip(rows, SPEC.cells()):
            n = int(r["Pixels"])
            p = src.read(window=Window(col*n, (SPEC.cells_xy[1]-row-1)*n, n, n))
            raw = evidence.read(1, window=Window(col*n, (SPEC.cells_xy[1]-row-1)*n, n, n))
            assert np.array_equal(p[0] == 1, raw == 2)  # NO terrain-derived/invented forests
            assert np.all(raw[p[3] == 1] == 0)  # only absent source can become inferred ocean
            masks = np.asarray(Image.open(io.BytesIO(bundle.read(r["MaskFile"]))))
            classes = np.asarray(Image.open(io.BytesIO(bundle.read(r["ClassFile"]))))
            rules = np.asarray(Image.open(io.BytesIO(bundle.read(r["RuleFile"]))))
            assert np.array_equal(classes, p[0]) and np.array_equal(rules, p[1])
            assert np.array_equal(masks[..., 0] != 0, p[0] == 1)
            assert np.array_equal(masks[..., 2] != 0, (p[0] == 1) & (p[1] == 1) & (p[2] == 0))
            assert np.all((masks[..., 1] != 0) <= (p[0] == 1))
            assert float(r["TreeCoverKm2"]) == pytest.approx(np.count_nonzero(p[0] == 1) * C["pixel_m"]**2 / 1e6)
            nw = SPEC.tm2_to_ue_cm(bounds[0], bounds[3])
            assert (float(r["NWXcm"]), float(r["NWYcm"])) == nw[:2]


def test_far_fraction_and_hold_do_not_bridge_terrain_gap():
    far = np.asarray(Image.open(OUT / "far_canopy_density.png"))
    hold = np.asarray(Image.open(OUT / "far_hold.png"))
    ratio = C["far_pixel_m"] // C["pixel_m"]
    with rasterio.open(OUT / "coverage.tif") as src:
        for _, _, ix, iy, bounds in SPEC.cells():
            # Every cell, including far mountains, remains tied to actual source tree labels.
            win = rasterio.windows.from_bounds(*bounds, src.transform).round_offsets().round_lengths()
            a = src.read(window=win)
            n = a.shape[1]
            expected = np.rint((a[0] == 1).reshape(n//ratio, ratio, n//ratio, ratio).mean((1,3))*255).astype(np.uint8)
            y, x = int(win.row_off)//ratio, int(win.col_off)//ratio
            assert np.array_equal(far[y:y+n//ratio, x:x+n//ratio], expected)
            if np.any(a[2] & 8):
                assert np.all(hold[y:y+n//ratio, x:x+n//ratio] == 255)


def test_native_forest_clearance_has_no_artificial_cell_border():
    # Compare TWO real adjacent cells against one continuous image, so forgetting
    # the source halo cannot create a synthetic clearance band at their seam.
    from scipy.ndimage import distance_transform_edt
    with rasterio.open(OUT / "coverage.tif") as src:
        win = rasterio.windows.from_bounds(304000, 2760000, 312000, 2776000, src.transform)
        forest = src.read(1, window=win) == 1
    with zipfile.ZipFile(OUT / "unreal_masks.zip") as bundle:
        arrays = [np.asarray(Image.open(io.BytesIO(bundle.read(f"cells/{cell}/masks.png"))))[..., 1]
                  for cell in ("C+0038+0346", "C+0038+0345")]
    joined = np.concatenate(arrays, axis=0)
    expected = forest & (distance_transform_edt(forest) * C["pixel_m"] > C["edge_clearance_m"])
    assert np.array_equal(joined[5:-5, 5:-5] != 0, expected[5:-5, 5:-5])


def test_runtime_chunk_names_uv_and_half_open_ownership_match_terrain():
    cells = list(csv.DictReader((OUT / "cells.csv").open()))
    chunks = list(csv.DictReader((OUT / "runtime_chunks.csv").open()))
    per = int(SPEC.cell_m / C["runtime_chunk_m"])
    assert len(chunks) == len(cells) * per**2
    assert len(set(c["Name"] for c in chunks)) == len(chunks)
    for cell in cells:
        rows = [r for r in chunks if r["CellId"] == cell["CellId"]]
        assert {r["ChunkId"] for r in rows} == {f"ch{x}{y}" for x in range(per) for y in range(per)}
        covered = np.zeros((int(cell["Pixels"]), int(cell["Pixels"])), np.uint8)
        for r in rows:
            x, y, n = (int(r[k]) for k in ("PixelX", "PixelY", "PixelSize"))
            covered[y:y+n, x:x+n] += 1
        assert np.all(covered == 1)
        sw = next(r for r in rows if r["ChunkId"] == "ch00")
        assert float(sw["UMin"]) == 0 and float(sw["VMax"]) == 1


def test_real_geographic_controls_preserve_grass_city_water_and_mountains():
    # Independent named locations; neighbourhoods absorb source date/registration uncertainty.
    controls = [("Taipei101", 121.5645, 25.0339, 4), ("Qingtiangang", 121.5744, 25.1663, 2),
                ("TaiwanStrait", 121.2, 25.4, 5), ("Guanyinshan", 121.4266, 25.1309, 1),
                # Water upstream of the dam; the dam's west-bank park is open land.
                ("Lalashan", 121.436, 24.709, 1), ("ShimenReservoir_upstream", 121.250, 24.809, 5)]
    transform = Transformer.from_crs(4326, 3826, always_xy=True)
    with rasterio.open(OUT / "coverage.tif") as src:
        for name, lon, lat, expected in controls:
            row, col = src.index(*transform.transform(lon, lat))
            a = src.read(1, window=Window(col-5, row-5, 11, 11))
            assert np.count_nonzero(a == expected) > a.size * 0.5, name
