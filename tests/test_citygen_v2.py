"""Geometry invariants and real-data gate regression; legacy tests stay intact."""
import unittest
import shutil
import uuid
from pathlib import Path

from shapely.geometry import Polygon
import trimesh

from tools.citygen_v2.build import ROOT, classify, check_solid, audit, representative, export_tiles


class GeometryTests(unittest.TestCase):
    def test_closed_concave_and_courtyard_with_both_orientations(self):
        polygons = [Polygon([(0,0),(10,0),(10,10),(0,10)]),
                    Polygon([(0,0),(10,0),(10,3),(3,3),(3,10),(0,10)]),
                    Polygon([(0,0),(10,0),(10,10),(0,10)],
                            [[(2,2),(2,8),(8,8),(8,2)]])]
        for polygon in polygons:
            for p in (polygon, polygon.reverse()):
                with self.subTest(p=p.wkt):
                    mesh = trimesh.creation.extrude_polygon(p, 12.5, engine='earcut')
                    check_solid(mesh, p, 12.5)

    def test_geos_repairs_bowtie_to_two_parts(self):
        row, polys = classify([[(0,0),(2,2),(0,2),(2,0),(0,0)]])
        self.assertEqual(row['outcome'], 'repaired')
        self.assertEqual(len(polys), 2)
        self.assertAlmostEqual(sum(p.area for p in polys), 2)

    def test_rejections_are_explicit(self):
        for rings in ([[[0,0],[0,0],[0,0]]], [[[0,0],[1,0],[0,0]]],
                      [[[0,0],[float('nan'),0],[1,1]]]):
            row, polys = classify(rings)
            self.assertEqual(row['outcome'], 'rejected')
            self.assertTrue(row['reason'])
            self.assertFalse(polys)

    def test_repeated_vertices_do_not_change_footprint(self):
        row, polys = classify([[(0,0),(2,0),(2,0),(2,2),(0,2),(0,0)]])
        self.assertEqual(row['repeated_vertices'], 1)
        self.assertEqual(polys[0].area, 4)

    def test_mesh_gate_detects_missing_caps_and_reversed_roofs(self):
        p = Polygon([(0,0),(2,0),(2,2),(0,2)])
        m = trimesh.creation.extrude_polygon(p, 10, engine='earcut')
        roof = m.face_normals[:,2] > .99
        for defect in ('missing','flipped'):
            bad = m.copy()
            if defect == 'missing':
                bad.update_faces(~roof)
            else:
                f = bad.faces.copy()
                f[roof] = f[roof, ::-1]
                bad.faces = f
            with self.assertRaises(ValueError):
                check_solid(bad, p, 10)

    def test_tiles_are_deterministic_and_keep_negative_enu_coordinates(self):
        row = {'key':'fixture/part-0', 'feature_id':'fixture', 'suppressed':False, 'height_m':7}
        p = Polygon([(-510,-12),(-490,-12),(-490,5),(-510,5)])
        temp = ROOT / 'unreal/Saved/CitygenV2' / ('test-' + uuid.uuid4().hex)
        temp.mkdir(parents=True)
        try:
            a = export_tiles([row], {row['key']:[p]}, temp/'a')
            b = export_tiles([row], {row['key']:[p]}, temp/'b')
            self.assertEqual(a['tiles'], b['tiles'])
            self.assertEqual(a['emitted_parts'], 1)
            self.assertEqual(a['tiles'][0]['bounds_gltf_m'], [[-510,0,-5],[-490,7,12]])
        finally:
            if not temp.resolve().is_relative_to((ROOT/'unreal/Saved/CitygenV2').resolve()):
                raise ValueError('unsafe test cleanup path')
            shutil.rmtree(temp)


class PinnedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.rows, cls.parts, cls.wm = audit()

    def test_every_source_part_is_accounted_for(self):
        self.assertEqual(self.summary['polygon_parts'], 11136)
        self.assertEqual(sum(self.summary['outcomes'].values()), 11136)
        self.assertEqual(self.summary['source_interior_rings'], 1200)
        self.assertEqual(self.summary['hero_suppressed_features'], 8)
        self.assertEqual(self.summary['values_on_0_0001_degree_grid'], self.summary['coordinate_values'])

    def test_sample_includes_complex_holes_multipart_and_failure_neighborhood(self):
        chosen, reasons = representative(self.rows, self.parts)
        self.assertEqual(len(chosen), 80)
        tags = {tag for group in reasons.values() for tag in group}
        self.assertTrue({'complex','courtyard','multipart_source','rectangle','concave',
                         'previous_failure_neighborhood_lowrise'}.issubset(tags))

    def test_point_touching_courtyard_is_not_claimed_a_solid(self):
        key = 'tp_building_height.240128/part-0'
        p = self.parts[key][0]
        r = next(r for r in self.rows if r['key'] == key)
        self.assertTrue(p.is_valid)  # OGC validity does not imply manifold extrusion
        self.assertFalse(p.exterior.intersection(p.interiors[0]).is_empty)
        mesh = trimesh.creation.extrude_polygon(p, r['height_m'], engine='earcut')
        with self.assertRaisesRegex(ValueError, 'not_a_closed_outward_solid'):
            check_solid(mesh, p, r['height_m'])


if __name__ == '__main__':
    unittest.main()
