"""Regression and acceptance tests for Xinyi Robust Whitebox v2."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))

from audit_source import audit  # noqa: E402
from geometry import extrude_geos_polygon, mesh_gate, repair_worldmodel_polygon  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings.geojson"
CITY = REPO / "cities/taipei/city.yaml"


class TestPinnedXinyiSourceAudit(unittest.TestCase):
    def test_source_loss_is_measured_before_meshing(self):
        report = audit(SOURCE)
        self.assertEqual(report["feature_count"], 11132)
        self.assertEqual(report["geometry_type_counts"], {"MultiPolygon": 11132})
        self.assertEqual(report["polygon_parts"], 11136)
        self.assertEqual(report["features_with_holes"], 715)
        self.assertEqual(report["collapsed_exterior_parts_lt3_distinct_xy"], 5297)
        self.assertEqual(report["max_coordinate_decimals_observed"], 4)
        self.assertIsNotNone(report["precision_warning"])

    def test_worldmodel_preserves_holes_without_breaking_v0_outer_fields(self):
        wm = build_worldmodel(SOURCE, CITY)
        with_holes = 0
        for b in wm["buildings"]:
            for p in b["polygons"]:
                self.assertIn("footprint_enu", p)
                self.assertIn("holes_enu", p)
                self.assertIn("source_polygon_index", p)
                if p["holes_enu"]:
                    with_holes += 1
        self.assertEqual(with_holes, 715)

    def test_legacy_zero_area_is_source_collapse_not_silent_triangulator_loss(self):
        wm = build_worldmodel(SOURCE, CITY)
        collapsed_unsuppressed = 0
        for b in wm["buildings"]:
            if b["suppressed"]:
                continue
            for p in b["polygons"]:
                _, outcome = repair_worldmodel_polygon(p)
                if outcome["reason"] == "collapsed_source_outer":
                    collapsed_unsuppressed += 1
        # This is the old build report's 5,296 zero_area count exactly.
        self.assertEqual(collapsed_unsuppressed, 5296)


class TestMatureExtrusionGate(unittest.TestCase):
    def test_concave_polygon_with_hole_is_closed_and_oriented(self):
        poly = Polygon(
            [(0, 0), (20, 0), (20, 8), (12, 8), (12, 20), (0, 20)],
            holes=[[(3, 3), (8, 3), (8, 7), (3, 7)]],
        )
        self.assertTrue(poly.is_valid)
        mesh = extrude_geos_polygon(poly, 18.75)
        gate = mesh_gate(mesh, 18.75)
        self.assertTrue(gate["pass"], gate)
        self.assertTrue(gate["watertight"])
        self.assertTrue(gate["winding_consistent"])
        self.assertTrue(gate["is_volume"])
        self.assertEqual(gate["zero_area_triangles"], 0)
        self.assertGreater(gate["roof_triangles"], 0)
        self.assertGreater(gate["base_triangles"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
