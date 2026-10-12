"""Phase 2A world bounds: size-agnostic WorldSpec, committed world artefacts, Xinyi compatibility, QA detectors.

Network-free. Run with the NTW venv:  python -m pytest tests/test_ntw_world.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/ntw"))
sys.path.insert(0, str(REPO / "tools/compiler"))

import frame  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

W = REPO / "data/ntw/world"
SPEC_FILE = REPO / "worlds/north_taiwan_224.json"
TO_TM2 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)


def load(name):
    return json.loads((W / name).read_text(encoding="utf-8"))


class WorldSpecTests(unittest.TestCase):
    def test_224_spec_is_grid_aligned(self):
        s = WorldSpec.load(SPEC_FILE)
        self.assertEqual(s.cells_xy, (28, 28))
        self.assertEqual(s.bounds_tm2, (184000.0, 2648000.0, 408000.0, 2872000.0))
        self.assertEqual(s.runtime_origin_tm2, (296000.0, 2760000.0))
        self.assertEqual(s.summary()["max_abs_ue_coordinate_km"], 112.0)

    def test_size_is_data_not_a_constant(self):
        for km in (160, 192, 224, 256, 288, 320):
            s = WorldSpec.centred("t", (296000.0, 2760000.0), (km, km))
            self.assertEqual(s.cells_xy, (km // 8, km // 8))
            self.assertEqual(len(list(s.cells())), (km // 8) ** 2)
        rect = WorldSpec(name="r", sw_tm2=(184000.0, 2648000.0), size_m=(224000.0, 160000.0))
        rect.validate()
        self.assertEqual(rect.cells_xy, (28, 20))

    def test_misaligned_specs_are_rejected(self):
        with self.assertRaises(ValueError):
            WorldSpec(name="bad", sw_tm2=(184500.0, 2648000.0), size_m=(224000.0, 224000.0)).validate()
        with self.assertRaises(ValueError):
            WorldSpec(name="bad", sw_tm2=(184000.0, 2648000.0), size_m=(225000.0, 224000.0)).validate()
        with self.assertRaises(ValueError):
            WorldSpec(name="bad", sw_tm2=(184000.0, 2648000.0), size_m=(224000.0, 224000.0), cell_m=7700.0).validate()

    def test_cell_ids_and_tile_keys_do_not_depend_on_world_size(self):
        a = WorldSpec.load(SPEC_FILE)
        b = WorldSpec(name="big", sw_tm2=(168000.0, 2632000.0), size_m=(256000.0, 256000.0))
        ida = {a.cell_id(c[2], c[3]) for c in a.cells()}
        idb = {b.cell_id(c[2], c[3]) for c in b.cells()}
        self.assertEqual(len(ida), 784)
        self.assertTrue(ida <= idb)  # every 224 cell keeps its id inside the 256 world
        x, y = 307056.8, 2769551.8  # Xinyi ENU origin in TM2
        self.assertEqual(a.cell_id(*a.cell_index_abs(x, y)), b.cell_id(*b.cell_index_abs(x, y)))
        # storage-frame L2 tile key uses only frame.NTW_ORIGIN_TM2, never a world's bounds
        ix, iy = frame.cell_index(*frame.tm2_to_ntw(np.array([x]), np.array([y])), 500.0)
        self.assertEqual((int(ix[0]), int(iy[0])), (int((x - frame.NTW_ORIGIN_TM2[0]) // 500), int((y - frame.NTW_ORIGIN_TM2[1]) // 500)))

    def test_ue_mapping_follows_accepted_axis_contract(self):
        s = WorldSpec.load(SPEC_FILE)
        ox, oy = s.runtime_origin_tm2
        self.assertEqual(s.tm2_to_ue_cm(ox + 1.0, oy + 2.0, 3.0), (100.0, -200.0, 300.0))

    def test_load_roundtrip_through_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.json"
            p.write_text(json.dumps({"name": "x", "size_km": [192, 192], "cell_km": 8, "sw_corner_epsg3826": [200000, 2640000]}))
            s = WorldSpec.load(p)
            self.assertEqual(s.cells_xy, (24, 24))


class WorldArtefactTests(unittest.TestCase):
    def test_bounds_geojson_matches_spec(self):
        s = WorldSpec.load(SPEC_FILE)
        b = json.loads((W / "north_taiwan_224_bounds.geojson").read_text(encoding="utf-8"))
        ring = b["features"][0]["geometry"]["coordinates"][0]
        self.assertEqual(tuple(ring[0]) + tuple(ring[2]), s.bounds_tm2)
        c = b["features"][0]["properties"]["corners_lonlat"]
        self.assertTrue(120.0 < c["SW"][0] < c["SE"][0] < 123.0 and 23.5 < c["SW"][1] < c["NW"][1] < 26.5)

    def test_cells_cover_world_exactly_and_balance_area(self):
        cells = json.loads((W / "north_taiwan_224_cells_epsg3826.geojson").read_text(encoding="utf-8"))["features"]
        self.assertEqual(len(cells), 784)
        ids = [c["properties"]["cell_id"] for c in cells]
        self.assertEqual(len(set(ids)), 784)
        for c in cells:
            p = c["properties"]
            self.assertAlmostEqual(p["land_km2"] + p["sea_km2"] + p["foreign_land_km2"], 64.0, places=1)
            self.assertEqual(p["buildings_best"], p["buildings_wfs"] + p["buildings_overture"])
            self.assertEqual(p["foreign_land_km2"], 0.0)

    def test_summary_totals_are_consistent(self):
        sm = load("north_taiwan_224_summary.json")
        t = sm["totals"]
        self.assertAlmostEqual(t["tw_land_km2"] + t["sea_km2"] + t["foreign_land_km2"], t["area_km2"], delta=1.0)
        self.assertEqual(sum(v["cells"] for v in sm["tiers"].values()), 784)
        self.assertEqual(sum(v["buildings_best"] for v in sm["tiers"].values()), t["buildings_best"])
        # exact partition: WFS inside the Taipei polygon + boundary records reported separately = all 373,532
        self.assertEqual(t["buildings_wfs_taipei"] + t["wfs_records_excluded_outside_overture_taipei_polygon"], 373532)
        hv = t["overture_height_validity_world"]
        self.assertEqual(sum(hv.values()), t["buildings_overture_outside_taipei"])

    def test_required_features_and_regions_are_inside_with_margin(self):
        s = WorldSpec.load(SPEC_FILE)
        for f in load("features.json")["features"]:
            if f["tier"] == "required":
                self.assertIn("lon", f, f["name"])
                self.assertTrue(s.contains(*TO_TM2.transform(f["lon"], f["lat"]), margin_m=8000.0), f["name"])
            if f["tier"] == "info_foreign":
                self.assertFalse(s.contains(*TO_TM2.transform(f["lon"], f["lat"])), f["name"])
        sm = load("north_taiwan_224_summary.json")["admin_regions_in_world"]
        for code in ("TW-HSZ", "TW-HSQ", "TW-TAO", "TW-TPE", "TW-NWT", "TW-ILA"):
            self.assertGreaterEqual(sm[code]["pct_in_world"], 99.9, code)

    def test_selected_spec_is_the_top_ranked_feasible_placement(self):
        top = load("placement_224.json")["top"][0]
        self.assertTrue(top["feasible"])
        self.assertEqual(top["sw_corner_epsg3826"], list(WorldSpec.load(SPEC_FILE).sw_tm2))
        self.assertGreaterEqual(top["objective_min_core_depth_km"], 50.0)
        self.assertEqual(top["foreign_land_km2"], 0.0)

    def test_dtm_hole_is_reported_not_hidden(self):
        h = load("north_taiwan_224_summary.json")["terrain_qa"]["inland_dtm_hole"]
        gaps = [c for c in h["components"] if c["interpretation"].startswith("DTM data gap")]
        self.assertTrue(gaps)
        self.assertGreater(gaps[0]["surrounding_land_median_elev_m"], 500)


class XinyiCompatTests(unittest.TestCase):
    def test_xinyi_inside_world_and_suppression_by_identity_is_exact(self):
        x = load("xinyi_compat.json")
        self.assertTrue(x["placement"]["inside_world"])
        self.assertGreater(min(x["placement"]["distance_to_world_edges_km"].values()), 90)
        s = x["l3_suppression"]
        self.assertEqual(s["xinyi_source_sha256"], "c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d")
        self.assertEqual(s["ids_found_in_current_wfs"], s["xinyi_source_features"])
        self.assertEqual(s["ids_with_identical_geometry"], s["xinyi_source_features"])
        self.assertEqual(s["non_xinyi_features_overlapping_a_xinyi_footprint_gt_0p01m2"], 0)
        g = x["accepted_glb_integrity"]
        if "sha256_match" in g:
            self.assertEqual(g["sha256_match"], g["tiles"])

    def test_sector_outline_is_the_exact_inverse_of_the_accepted_enu(self):
        from worldmodel import lonlat_to_enu
        import xinyi_world_compat as xc
        for ex, ey in ((-1500.0, -1000.0), (1000.0, 1500.0), (123.4, -567.8)):
            lon, lat = xc.enu_to_lonlat(ex, ey)
            e2, n2 = lonlat_to_enu(lon, lat, xc.O_LON, xc.O_LAT)
            self.assertAlmostEqual(e2, ex, places=6)
            self.assertAlmostEqual(n2, ey, places=6)
        m = json.loads((W / "xinyi_l3_mask_epsg3826.geojson").read_text())
        sector = shapely.geometry.shape(m["features"][0]["geometry"])
        self.assertAlmostEqual(sector.area / 1e6, 6.25 * 1.00054 * 0.99503, places=2)


class DetectorTests(unittest.TestCase):
    def test_hole_detector_keeps_large_blocks_and_ignores_thin_rivers(self):
        import world_cells as wc
        land = shapely.box(0, 0, 40000, 40000)
        xs = np.arange(125, 40000, 250.0)
        GX, GY = np.meshgrid(xs, xs)
        e = np.full(GX.shape, 300.0)
        e[(GX > 15000) & (GX < 18000) & (GY > 15000) & (GY < 18000)] = 0.0     # 9 km2 block: data hole
        e[(GX > 10000) & (GX < 10300)] = 0.0                                    # 300 m wide river: genuine 0 m
        hole, small = wc.inland_holes(GX.ravel(), GY.ravel(), e.ravel(), land, GX.shape, 0.0625)
        self.assertAlmostEqual(hole.sum() * 0.0625, 9.0, delta=0.5)
        self.assertGreater(small.sum(), 0)
        self.assertFalse((hole & small).any())


class CoverageValidityTests(unittest.TestCase):
    def test_validated_height_categories_partition_each_region(self):
        c = json.loads((REPO / "data/ntw/coverage_manifest.json").read_text(encoding="utf-8"))
        for r in c["regions"] + [c["core_6"]]:
            v = r["validated"]
            self.assertEqual(v["valid_height"] + v["valid_floors_only"] + v["no_usable_height"], r["buildings"])
            self.assertLessEqual(v["present_but_invalid"], v["no_usable_height"])
            self.assertGreaterEqual(v["no_usable_height"], r["fallback_needed"])


if __name__ == "__main__":
    unittest.main()
