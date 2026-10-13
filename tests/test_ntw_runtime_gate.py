"""Phase 2B runtime-gate round: quantisation fallback (candidate, default OFF), battlefield comparison, stitch v2, committed
UE runtime-gate and whole-cell shard evidence. Network-free.  python -m pytest tests/test_ntw_runtime_gate.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/ntw"))
sys.path.insert(0, str(REPO / "tools/ntw/ue_gate"))
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))


def load(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


class QuantizationFallbackTests(unittest.TestCase):
    def test_defaults_keep_the_accepted_strict_behaviour(self):
        import build_pilot as bp
        self.assertFalse(bp.QUANT_FALLBACK["enabled"])
        self.assertFalse(bp.FRAGMENT_POLICY["enabled"])
        self.assertFalse(bp.DIAGNOSTIC_WRITE_ON_FAILURE["enabled"])

    def test_snap_with_zero_width_hair_passes_fidelity_gates(self):
        from shapely.geometry import Polygon
        import quantization_fallback as qf
        o = (250.0, 250.0)
        # 12 x 9 m footprint with off-grid vertices and a 3 m out-and-back hair of width 2e-7 m
        ring = [(100.123456789, 100.987654321), (112.123456789, 100.987654321), (112.123456789, 105.0),
                (115.123456789, 105.0000002), (112.123456789, 105.0000004), (112.123456789, 109.987654321),
                (100.123456789, 109.987654321)]
        parts, rep = qf.fallback(Polygon([(x + o[0] - 250.0, y + o[1] - 250.0) for x, y in ring]), o, True)
        self.assertTrue(rep["pass_"], rep)
        self.assertEqual(rep["wide_removed_m2"], 0.0)
        self.assertEqual(rep["wide_added_m2"], 0.0)
        self.assertLessEqual(abs(rep["area_delta_m2"]), rep["budget_m2"])
        self.assertTrue(parts)

    def test_collapse_is_ledgered_only_for_a_non_largest_fragment(self):
        from shapely.geometry import box
        import quantization_fallback as qf
        tiny = box(10.0, 10.0, 10.1, 10.1)
        parts, rep = qf.fallback(tiny, (0.0, 0.0), False, grid=0.5)
        self.assertTrue(rep["pass_"] and rep.get("ledgered"))
        self.assertEqual(parts, [])
        parts, rep = qf.fallback(tiny, (0.0, 0.0), True, grid=0.5)
        self.assertFalse(rep["pass_"])
        self.assertIn("snap_collapsed_a_non_fragment", rep["failures"])

    def test_population_evidence(self):
        scan = load("data/ntw/terrain/fragment_scan.json")
        self.assertEqual(scan["taipei_wfs"]["polygon_parts"], 374238)
        self.assertEqual(scan["taipei_wfs"]["strict_footprint_stage_failures"], 10)
        self.assertEqual(scan["xinyi_accepted_enu"]["strict_footprint_stage_failures"], 0)
        ev = load("data/ntw/terrain/fallback_eval.json")
        self.assertEqual(ev["evaluated_failing_parts"], 10)
        self.assertEqual(ev["outcomes"].get("FAIL", 0), 0)


class BattlefieldCompareTests(unittest.TestCase):
    def test_proposed_112_unchanged_and_extensions_are_water(self):
        cfg = load("worlds/battlefields/north_core_v1.json")
        self.assertEqual(cfg["recommended_size_km"], 112)
        cmp_ = load("data/ntw/battlefield/north_core_v1_compare.json")["boxes"]
        self.assertEqual(cmp_["112x112 (proposed)"]["bounds_epsg3826"], [224000, 2728000, 336000, 2840000])
        self.assertEqual(cmp_["128x112 west-extended"]["bounds_epsg3826"], [208000, 2728000, 336000, 2840000])
        for k in ("120x120", "128x112 west-extended"):
            self.assertEqual(cmp_[k]["extension_vs_112"]["water_share_pct"], 100.0)
            self.assertEqual(cmp_[k]["extra_cost_if_production_follows_box"]["land_cells"], 0)
            self.assertGreater(cmp_[k]["west_ocean_km2"], cmp_["112x112 (proposed)"]["west_ocean_km2"])
        for b in cmp_.values():
            self.assertEqual(b["depth_km"]["east_core_min"], 0.0)
            self.assertIn("east", b["east_limitation"].lower())


class StitchV2Tests(unittest.TestCase):
    def test_full_resolution_edge_at_every_lod(self):
        st = load("data/ntw/terrain/pilot_terrain_qa.json")["xinyi_stitch"]
        self.assertEqual(sorted(st), ["lod0", "lod1", "lod2", "lod3", "lod4"])
        for r in st.values():
            self.assertEqual(r["stitch_edge"], "full")
            self.assertEqual(r["edge_vertices"], 2520)
            self.assertEqual(r["edge_vertices_missing"], 0)
            self.assertEqual(r["edge_segments_present_as_mesh_edges"], 2520)
            self.assertEqual(r["ring_vs_full_res_xinyi_edge_max_dev_m"], 0.0)
            self.assertEqual(r["hole_side_vertices_not_equal_to_chunk_vertices"], 0)


class LandscapeTriangulationTests(unittest.TestCase):
    def test_both_diagonals_interpolate_corners(self):
        import analyse_runtime as ar

        class X:
            e0, n1, step, n = 0.0, 1.0, 1.0, 2
            h = np.array([[0.0, 1.0], [2.0, 5.0]])   # rows north->south
        e = np.array([0.0, 1.0, 0.0, 1.0, 0.5])
        n = np.array([1.0, 1.0, 0.0, 0.0, 0.5])
        a, b = ar.landscape_tri_heights(X, e, n)
        np.testing.assert_allclose(a[:4], [0, 1, 2, 5])
        np.testing.assert_allclose(b[:4], [0, 1, 2, 5])
        self.assertAlmostEqual(a[4], 2.5)    # on diagonal A: mean of h00, h11
        self.assertAlmostEqual(b[4], 1.5)    # on diagonal B: mean of h10, h01


class RuntimeGateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.r = load("data/ntw/runtime/runtime_gate_result.json")

    def test_measured_in_engine_not_on_mobile(self):
        self.assertTrue(self.r["configured_session_completed"])
        self.assertEqual(self.r["runs"]["followup"]["status"], "COMPLETED")
        self.assertIn("NOT mobile", self.r["hardware"])
        self.assertTrue(any("mobile" in x for x in self.r["not_tested"]))

    def test_collision_covers_all_four_edges_corners_and_seams(self):
        sets = self.r["collision"]["sets"]
        for k in ("xinyi_south", "xinyi_east", "xinyi_north", "xinyi_west", "corner_SW", "corner_SE", "corner_NE", "corner_NW",
                  "cell_seam_N2768000", "chunk_seam_E305600", "chunk_seam_N2763200", "dem_nodes"):
            self.assertIn(k, sets)
            self.assertGreater(sets[k]["n"], 0)
        self.assertTrue(self.r["collision"]["gate"]["status"].startswith(("PASS", "FAIL")))
        m = self.r["collision"]["micro_offset_traces"]
        self.assertTrue(m["all_offline_rays_hit"])
        self.assertEqual(m["offline_wrong_actor"], 0)

    def test_lod_matrix_keeps_failure_evidence(self):
        g = self.r["lod"]["gate"]
        self.assertTrue(g["mixed_stitch_chunk_lod_rows"])
        self.assertTrue(any(t["crack_px_total"] > 0 for t in g["mixed_stitch_chunk_lod_rows"]))
        self.assertTrue({t["stitch"] for t in self.r["lod"]["table"]} >= {"v1", "v2"})

    def test_streaming_flights_and_template_grid_session(self):
        tags = set(self.r["flights"])
        for agl in (150, 300, 600, 800):
            self.assertIn("configured_agl%d" % agl, tags)
        self.assertTrue(any(t.startswith("template_default_grid") for t in tags))
        for f in self.r["flights"].values():
            self.assertGreater(f["frames"], 0)


class CellShardEvidenceTests(unittest.TestCase):
    def test_whole_cell_shards(self):
        r = load("data/ntw/terrain/building_cell_shard_test.json")
        self.assertEqual(r["ownership"]["parts_emitted_by_both_cells"], 0)
        self.assertTrue(r["ownership"]["independent_union_equals_joint"])
        self.assertTrue(r["tiles"]["tile_sets_equal"])
        self.assertEqual(r["xinyi"]["xinyi_wfs_ids_emitted"], 0)
        self.assertFalse(r["policy"]["fragment_policy"]["enabled"])
        self.assertIn("loader_scenario", r)
        # the strict failure is kept as a FAIL; diagnostic tiles never turn it into a pass
        if any(r["build_failures"].values()):
            self.assertFalse(r["pass"])


if __name__ == "__main__":
    unittest.main()
