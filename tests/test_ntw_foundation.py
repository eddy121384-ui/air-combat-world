"""Northern Taiwan world foundation: frame, hierarchy nesting, height policy, committed manifests.

Network-free and fast. Run with the NTW venv:  python -m pytest tests/test_ntw_foundation.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np
from pyproj import Geod

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/ntw"))
sys.path.insert(0, str(REPO / "tools/compiler"))

import frame  # noqa: E402
import heights  # noqa: E402
from worldmodel import lonlat_to_enu  # noqa: E402

GEOD = Geod(ellps="WGS84")
XINYI_ORIGIN = (121.5654, 25.0330)
FAR_POINTS = [(120.9686, 24.8138), (121.7532, 24.7570), (121.8100, 25.1000), (121.2250, 24.9653), (120.9500, 24.5500)]


class FrameTests(unittest.TestCase):
    def test_roundtrip_is_sub_millimetre(self):
        lon = np.array([p[0] for p in FAR_POINTS])
        lat = np.array([p[1] for p in FAR_POINTS])
        x, y = frame.lonlat_to_ntw(lon, lat)
        lon2, lat2 = frame.ntw_to_lonlat(x, y)
        for a, b, c, d in zip(lon, lat, lon2, lat2):
            _, _, dist = GEOD.inv(a, b, c, d)
            self.assertLess(dist, 1e-3)

    def test_origin_is_multiple_of_coarsest_cell_so_levels_nest(self):
        top = frame.LEVEL_CELL_M["L0"]
        self.assertEqual(frame.NTW_ORIGIN_TM2[0] % top, 0)
        self.assertEqual(frame.NTW_ORIGIN_TM2[1] % top, 0)
        for coarse, fine in (("L0", "L1"), ("L1", "L2")):
            self.assertEqual(frame.LEVEL_CELL_M[coarse] % frame.LEVEL_CELL_M[fine], 0)
        self.assertEqual(frame.LEVEL_CELL_M["L2"], 500.0)  # must equal accepted Xinyi tile size

    def test_every_l2_owner_cell_sits_inside_exactly_one_l1_and_l0(self):
        rng = np.random.default_rng(7)
        x, y = rng.uniform(0, 120_000, 5000), rng.uniform(0, 112_000, 5000)
        i2 = frame.cell_index(x, y, 500.0)
        i1 = frame.cell_index(x, y, 8000.0)
        i0 = frame.cell_index(x, y, 32000.0)
        np.testing.assert_array_equal(i2[0] // 16, i1[0])
        np.testing.assert_array_equal(i2[1] // 16, i1[1])
        np.testing.assert_array_equal(i1[0] // 4, i0[0])
        np.testing.assert_array_equal(i1[1] // 4, i0[1])

    def test_theater_stays_positive_and_float32_exact_at_tile_scale(self):
        x, y = frame.lonlat_to_ntw(np.array([120.85, 122.05]), np.array([24.30, 25.31]))
        self.assertGreater(float(x.min()), 0)
        self.assertGreater(float(y.min()), 0)
        # tile-local (<= 500 m) float32 spacing must stay far below QA tolerances (1e-4 m)
        self.assertLess(float(np.spacing(np.float32(500.0))), 1e-4)

    def test_tm2_distance_matches_geodesic_within_0p02_percent(self):
        ox, oy = frame.lonlat_to_ntw(*XINYI_ORIGIN)
        for lon, lat in FAR_POINTS:
            x, y = frame.lonlat_to_ntw(lon, lat)
            tm2 = float(np.hypot(x - ox, y - oy))
            _, _, truth = GEOD.inv(*XINYI_ORIGIN, lon, lat)
            self.assertLess(abs(tm2 / truth - 1), 2e-4, (lon, lat))


class XinyiFrameRegression(unittest.TestCase):
    def test_accepted_xinyi_enu_formula_is_unchanged(self):
        # Pinned from the accepted tools/compiler/worldmodel.py; if this moves, Xinyi geometry would move.
        e, n = lonlat_to_enu(121.5645, 25.0337, *XINYI_ORIGIN)
        self.assertAlmostEqual(e, -90.77634744617912, places=9)
        self.assertAlmostEqual(n, 77.92364355510989, places=9)

    def test_xinyi_enu_maps_into_ntw_by_one_documented_affine(self):
        study = json.loads((REPO / "data/ntw/coordinate_study.json").read_text(encoding="utf-8"))
        a = study["xinyi_enu_to_ntw_affine"]
        self.assertLess(a["max_residual_m"], 0.2)
        # the accepted ENU frame is anisotropic vs. true ground: the doc/contract relies on these numbers
        self.assertAlmostEqual(a["east_axis_scale"], 1.0005, places=3)
        self.assertAlmostEqual(a["north_axis_scale"], 0.9950, places=3)
        self.assertAlmostEqual(a["east_axis_rotation_deg"], 0.239, places=2)
        m = np.array(a["linear_part"])
        t = np.array(a["translation_m"])
        # independent re-check at a point not used by the fit's grid centre
        lon, lat = 121.5671, 25.0349
        enu = np.array(lonlat_to_enu(lon, lat, *XINYI_ORIGIN))
        ntw = m @ enu + t
        x, y = frame.lonlat_to_ntw(lon, lat)
        self.assertLess(float(np.linalg.norm(ntw - np.array([float(x), float(y)]))), 0.2)


class HeightPolicyTests(unittest.TestCase):
    WFS_CASES = [
        {"1_bud_high": 87.9, "1_top_high": 100.0, "1_ent_heig": 12.1, "1_floor": 24},
        {"1_bud_high": None, "1_top_high": 160.0, "1_ent_heig": 100.0, "1_floor": 5},
        {"1_bud_high": 0.5, "1_top_high": None, "1_ent_heig": None, "1_floor": 10},
        {"1_bud_high": None, "1_top_high": None, "1_ent_heig": None, "1_floor": None},
        {"1_bud_high": 900, "1_top_high": 20, "1_ent_heig": 10, "1_floor": 200},
        {"1_bud_high": "", "1_top_high": "55.5", "1_ent_heig": "5.5", "1_floor": "3"},
    ]

    def test_overture_policy(self):
        self.assertEqual(heights.derive_overture_height(12.3, 4), (12.3, "overture_height"))
        self.assertEqual(heights.derive_overture_height(None, 5), (16.0, "overture_floors_x3.2"))
        self.assertEqual(heights.derive_overture_height(None, None), (9.6, "fallback_9.6m"))
        self.assertEqual(heights.derive_overture_height(0.4, None)[1], "fallback_9.6m")  # implausible
        self.assertEqual(heights.derive_overture_height(1000, 3)[1], "overture_floors_x3.2")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_python_wfs_port_matches_vendored_buju_semantics(self):
        mjs = (REPO / "tools/taipei/vendor/buju/taipei_building_height_semantics.mjs").as_uri()
        js = (f'import {{deriveBuildingHeight}} from "{mjs}";'
              f"const c={json.dumps(self.WFS_CASES)};"
              "console.log(JSON.stringify(c.map(p=>{const d=deriveBuildingHeight(p);return [d.height_m,d.source,d.ground_elev_m]})))")
        out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, check=True).stdout
        expected = json.loads(out)
        for case, exp in zip(self.WFS_CASES, expected):
            got = heights.derive_wfs_height(case)
            self.assertEqual(got[0], exp[0], case)
            self.assertEqual(got[1], exp[1], case)
            self.assertEqual(got[2], exp[2], case)


class CommittedManifests(unittest.TestCase):
    def load(self, name):
        return json.loads((REPO / "data/ntw" / name).read_text(encoding="utf-8"))

    def test_theater_regions(self):
        t = self.load("theater_regions.json")
        keys = [r["key"] for r in t["regions"]]
        self.assertEqual(keys, ["taipei", "new_taipei", "keelung", "taoyuan", "hsinchu_city", "hsinchu_county", "yilan"])
        for r in t["regions"]:
            w, s, e, n = r["bbox_lonlat"]
            self.assertTrue(119 < w < e < 123 and 23 < s < n < 26)
            self.assertGreater(r["land_area_km2_mainland"], 50)
        # a 60 x 60 km box (3,600 km2) cannot cover the six core regions
        self.assertGreater(t["core_6_regions"]["land_area_km2"], 3600)

    def test_coverage_manifest_accounting_is_exact(self):
        c = self.load("coverage_manifest.json")
        total = sum(r["buildings"] for r in c["regions"]) + c["outside_all_regions"]["buildings"]
        self.assertEqual(total, c["total_rows_in_theater_bbox"])
        for r in c["regions"]:
            self.assertEqual(r["explicit_height"] + r["floors_only"] + r["fallback_needed"], r["buildings"])
            self.assertEqual(sum(r["sources"].values()), r["buildings"])

    def test_pilot_results_record_passing_reproducible_unambiguous_ownership(self):
        res = self.load("pilot_results.json")
        self.assertEqual(len(res["pilots"]), 3)
        for p in res["pilots"]:
            self.assertTrue(p["gate_pass"], p["pilot"])
            self.assertTrue(p["determinism"]["tile_sha256_identical"], p["pilot"])
            self.assertEqual(p["ownership"]["parts_in_more_than_one_tile"], 0)
            self.assertEqual(p["ownership"]["parts_with_tile_not_equal_floor_centroid_rule"], 0)
            self.assertEqual(p["ownership"]["duplicate_node_names"], 0)
            self.assertEqual(p["accounting"]["unaccounted"], 0)
            self.assertLess(p["placement"]["max_vertex_to_source_boundary_m"], 0.001)
            self.assertEqual(p["blender_5_2_headless"]["failed_meshes"], 0)
            self.assertEqual(p["blender_5_2_headless"]["imported_triangles"], p["geometry"]["triangles"])
            self.assertTrue(all(v == 0 for v in p["blender_5_2_headless"]["totals"].values()))

    def test_scale_estimate_is_labelled_and_internally_consistent(self):
        s = self.load("scale_estimate.json")
        for sc in s["scenarios"]:
            self.assertEqual(sc["label"], "ESTIMATE")
            self.assertEqual(sc["components_total"], sc["components_wfs_like"] + sc["components_overture_like"])
        s1, s2 = s["scenarios"][0], s["scenarios"][1]
        self.assertLess(s1["components_total"], s2["components_total"])
        self.assertIn("no device was measured", s["l2_radius_for_triangle_budget_illustration"]["label"])

    def test_committed_data_is_small(self):
        total = sum(p.stat().st_size for p in (REPO / "data/ntw").glob("*"))
        self.assertLess(total, 2_000_000)


if __name__ == "__main__":
    unittest.main()
