"""Regression and acceptance tests for Xinyi Robust Whitebox v2."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from shapely.geometry import Polygon
import numpy as np
import trimesh
import io

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))

from audit_source import audit  # noqa: E402
from geometry import extrude_geos_polygon, mesh_gate, repair_worldmodel_polygon  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402
from strict_qa import strict_mesh_gate  # noqa: E402

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


class TestStrictSolidQA(unittest.TestCase):
    def setUp(self):
        self.poly = Polygon([(100,100),(120,100),(120,108),(112,108),(112,120),(100,120)],
                            holes=[[(103,103),(108,103),(108,107),(103,107)]])
        self.height = 18.75
        self.mesh = extrude_geos_polygon(self.poly, self.height)

    def test_valid_courtyard_survives_real_glb_float32_roundtrip(self):
        blob = trimesh.Scene(self.mesh).export(file_type='glb')
        scene = trimesh.load_scene(io.BytesIO(blob),file_type='glb',process=False)
        mesh = next(iter(scene.geometry.values()))
        gate = strict_mesh_gate(mesh,self.poly,self.height,precision='float32')
        self.assertTrue(gate['pass'],gate)
        self.assertEqual(gate['caps']['roof']['holes'],1)
        self.assertEqual(gate['wrong_wall_triangles'],0)

    def test_projected_real_lowrise_regression_roundtrip_reverses_caps(self):
        # Unmodified EPSG:3826 -> WorldModel footprint from PR #6's locked
        # tp_building_height.269018 part 0. Regression evidence, not a repair rule.
        p = Polygon([(-154.89226328475928,-293.24782850628304),
                     (-154.8539740774945,-290.5180084681076),
                     (-147.6455872215108,-290.57402114769087),
                     (-147.50756792275445,-290.5751016221337),
                     (-147.49675819940646,-293.32241321671927)])
        mesh = extrude_geos_polygon(p,3.5)
        self.assertTrue(strict_mesh_gate(mesh,p,3.5)['pass'])
        blob = trimesh.Scene(mesh).export(file_type='glb')
        loaded = next(iter(trimesh.load_scene(io.BytesIO(blob),file_type='glb',process=False).geometry.values()))
        gate = strict_mesh_gate(loaded,p,3.5,precision='float32')
        self.assertTrue(gate['watertight'])
        self.assertTrue(gate['winding_consistent'])
        self.assertGreater(gate['volume_m3'],0)
        self.assertFalse(gate['pass'])
        self.assertEqual(gate['wrong_roof_triangles'],1)
        self.assertEqual(gate['wrong_base_triangles'],1)
        self.assertIn('roof_overlapping_triangles',gate['failures'])

    def test_shifted_closed_solid_fails_footprint_coverage(self):
        self.mesh.apply_translation([2,0,0])
        gate = strict_mesh_gate(self.mesh,self.poly,self.height)
        self.assertTrue(gate['watertight'])
        self.assertIn('roof_footprint_coverage_mismatch',gate['failures'])

    def test_filled_hole_fails_volume_and_hole_checks(self):
        filled = extrude_geos_polygon(Polygon(self.poly.exterior),self.height)
        gate = strict_mesh_gate(filled,self.poly,self.height)
        self.assertIn('volume_not_footprint_area_times_height',gate['failures'])
        self.assertIn('roof_courtyard_not_preserved',gate['failures'])

    def test_overlapping_cap_is_reported_even_when_union_coverage_matches(self):
        i = np.flatnonzero(self.mesh.face_normals[:,1] > .999)[0]
        self.mesh.faces = np.vstack([self.mesh.faces,self.mesh.faces[i]])
        gate = strict_mesh_gate(self.mesh,self.poly,self.height)
        self.assertIn('roof_overlapping_triangles',gate['failures'])
        self.assertLess(gate['caps']['roof']['symmetric_difference_m2'],1e-8)

    def test_missing_cap_and_wrong_wall_are_detected(self):
        missing = self.mesh.copy()
        missing.update_faces(missing.face_normals[:,1] < .999)
        self.assertIn('missing_roof_cap',strict_mesh_gate(missing,self.poly,self.height)['failures'])
        wall = np.flatnonzero(abs(self.mesh.face_normals[:,1]) < .1)[0]
        faces = self.mesh.faces.copy()
        faces[wall] = faces[wall,::-1]
        self.mesh.faces = faces
        self.assertGreater(strict_mesh_gate(self.mesh,self.poly,self.height)['wrong_wall_triangles'],0)

    def test_nonfinite_and_degenerate_faces_are_not_repaired(self):
        bad = self.mesh.copy()
        vertices = bad.vertices.copy()
        vertices[0,0] = np.nan
        bad.vertices = vertices
        self.assertEqual(strict_mesh_gate(bad,self.poly,self.height)['nonfinite_vertices'],1)
        self.mesh.faces = np.vstack([self.mesh.faces,[0,0,1]])
        self.assertEqual(strict_mesh_gate(self.mesh,self.poly,self.height)['zero_area_triangles'],1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
