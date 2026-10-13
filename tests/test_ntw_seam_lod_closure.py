"""Phase 2B-C (seam collision + LOD runtime closure): fixed-hole stitch, collision flange, neighbour skirts, committed UE
evidence and the fallback before/after review. Network-free.  python -m pytest tests/test_ntw_seam_lod_closure.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
for p_ in ("tools/ntw", "tools/ntw/ue_gate", "tools/compiler", "tools/citygen_v2"):
    sys.path.insert(0, str(REPO / p_))


def load(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


class TerrainDefaultsTests(unittest.TestCase):
    def test_new_behaviour_is_opt_in(self):
        import build_terrain_cells as btc
        p = btc.TerrainParams()
        self.assertEqual(p.stitch_hole, "per_lod")
        self.assertFalse(p.collision_meshes)
        self.assertFalse(p.neighbour_skirts)

    def test_centroid_drop_and_two_sided_hole_skirt(self):
        import shapely
        import build_terrain_cells as btc
        xs = ys = np.arange(0.0, 81.0, 20.0)
        Z = np.zeros((5, 5))
        nrm = np.zeros((5, 5, 3))
        nrm[..., 2] = 1
        uv = np.zeros((5, 5, 2))
        hole = shapely.box(20, 20, 60, 60)            # 2 x 2 grid cells
        m, nterr, removed = btc.chunk_mesh(xs, ys, Z, nrm, uv, 2.0, drop_poly=hole, hole_skirt=7.0)
        self.assertEqual(len(removed), 8)             # 4 cells x 2 triangles
        self.assertEqual(nterr, 32 - 8)
        V = np.asarray(m.vertices)
        self.assertAlmostEqual(float(V[:, 1].min()), -7.0)
        sk = np.asarray(m.faces)[nterr:]
        n = np.cross(V[sk[:, 1]] - V[sk[:, 0]], V[sk[:, 2]] - V[sk[:, 0]])
        self.assertTrue(np.allclose(n[:, 1], 0.0))     # every skirt face vertical (glTF Y up)


class FlangeTests(unittest.TestCase):
    def test_corner_offsets_are_diagonal(self):
        import build_collision_flange as bcf

        class X:
            e0, e1, n0, n1 = 0.0, 10.0, 0.0, 10.0
        R = np.array([[0.0, 0.0], [5.0, 0.0], [10.0, 5.0], [10.0, 10.0]])
        inn, out = bcf.offsets(X, R, 0.1)
        np.testing.assert_allclose(inn[0], [0.1, 0.1])
        np.testing.assert_allclose(out[0], [-0.1, -0.1])
        np.testing.assert_allclose(inn[1], [5.0, 0.1])
        np.testing.assert_allclose(out[2], [10.1, 5.0])
        np.testing.assert_allclose(inn[3], [9.9, 9.9])


class StitchV3EvidenceTests(unittest.TestCase):
    def test_fixed_hole_stitch_qa(self):
        q = load("data/ntw/terrain/stitch_v3_qa.json")
        self.assertEqual(q["params"]["stitch_hole"], "fixed")
        self.assertEqual(q["fixed_hole"]["bounds_epsg3826"], [305280.0, 2768320.0, 308160.0, 2771200.0])
        self.assertEqual(q["stitch_footprint_max_symdiff_vs_lod0_m2"], 0.0)
        for r in q["xinyi_stitch"].values():
            self.assertEqual(r["edge_vertices"], 2520)
            self.assertEqual(r["edge_vertices_missing"], 0)
            self.assertEqual(r["edge_segments_present_as_mesh_edges"], 2520)
            self.assertEqual(r["hole_side_vertices_not_equal_to_chunk_vertices"], 0)


class ClosureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.r = load("data/ntw/runtime/closure_result.json")

    def test_measured_in_engine_with_clean_exit(self):
        self.assertIn("NOT mobile", self.r["hardware"])
        for name in ("runtime_closure", "runtime_physics_c3", "runtime_closure_lod_v4", "runtime_closure_lod_v6"):
            self.assertEqual(self.r["runs"][name]["status"], "COMPLETED")
            self.assertEqual(self.r["runs"][name]["editor_exit_code"], 0)

    def test_flange_closes_query_leaks_and_baseline_is_kept(self):
        g = self.r["collision_gate"]
        self.assertEqual(g["baseline_no_flange"]["micro_exact_line_misses"], 562)
        self.assertEqual(g["baseline_no_flange"]["main_trace_misses"], 26)
        self.assertEqual(g["query_status"], "PASS")
        self.assertEqual(g["micro_exact_line_misses"], 0)
        self.assertEqual(g["sweep_misses"], 0)
        self.assertIn(g["physics_status"], ("PASS", "FAIL"))
        self.assertEqual(g["physics"]["w10"]["v100_ccd_fell_max"], 0)

    def test_every_stitch_chunk_combination_is_watertight(self):
        g = self.r["lod_gate"]
        self.assertEqual(g["v4_neighbour_skirts"]["stitch_x_chunk_combos"], 25)
        self.assertEqual(g["v4_neighbour_skirts"]["stitch_x_chunk_crack_px"], 0)
        self.assertEqual(g["v3_own_lod_skirts"]["stitch_x_chunk_crack_px"], 0)
        self.assertGreater(g["v3_own_lod_skirts"]["checkerboard_crack_px"]["chk_0/2"], 0)       # failure evidence kept
        v6 = g["v6_plus_render_apron"]
        self.assertTrue(all(v == 0 for v in v6["checkerboard_real_px_est"].values()))
        self.assertEqual(v6["stitch_x_chunk_crack_px"], 0)
        self.assertIn(g["status"], ("PASS", "FAIL"))


class FallbackReviewTests(unittest.TestCase):
    def test_review_only_and_bounded(self):
        import build_pilot as bp
        self.assertFalse(bp.QUANT_FALLBACK["enabled"])
        r = load("data/ntw/terrain/fallback_review.json")
        self.assertTrue(r["status"].startswith("REVIEW ONLY"))
        self.assertEqual(sum(r["summary"].values()), 10)
        by = {p["building_id"]: p for p in r["parts"]}
        self.assertEqual(by["tp_building_height.301157"]["proposed_verdict"], "EXCEPTION")
        self.assertGreater(by["tp_building_height.301157"]["hausdorff_m"], 3.0)
        self.assertTrue(by["tp_building_height.179103"]["far_source_vertices"][0]["kind"].startswith("inward"))
        self.assertTrue(any("pinch" in h["after"] for h in by["tp_building_height.360929"]["holes"]))
        self.assertIn("PROPOSED", r["case_307096"]["proposed_case_decision"])
        self.assertIn("PROPOSED", r["case_provider_overlap"]["proposed_case_decision"])


if __name__ == "__main__":
    unittest.main()
