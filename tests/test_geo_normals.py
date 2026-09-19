"""Extrusion winding regression tests; no generated artifacts required."""
import math
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/compiler"))
from geo import extrude, triangulate


def face_normal(vertices):
    a, b, c = vertices
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    cross = (u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
    length = math.sqrt(sum(x * x for x in cross))
    return tuple(x / length for x in cross)


class TestExtrudeNormals(unittest.TestCase):
    HEIGHT = 7.0
    # CCW outlines and outward normals in the Y-up, north=-Z frame.
    CASES = (
        ("rectangle", [(0, 0), (4, 0), (4, 3), (0, 3)],
         [(0, 0, 1), (1, 0, 0), (0, 0, -1), (-1, 0, 0)], 12),
        ("concave_L", [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)],
         [(0, 0, 1), (1, 0, 0), (0, 0, -1), (1, 0, 0),
          (0, 0, -1), (-1, 0, 0)], 20),
    )

    def meshes(self):
        for name, outline, outward, count in self.CASES:
            for reverse in (False, True):
                source = outline[::-1] if reverse else outline
                parts = triangulate([source + [source[0]]])
                self.assertEqual(len(parts), 1)
                ring, tris = parts[0]
                pos, normals, indices = extrude(ring, tris, self.HEIGHT)
                vertices = [tuple(pos[i:i + 3]) for i in range(0, len(pos), 3)]
                faces = [tuple(vertices[j] for j in indices[i:i + 3])
                         for i in range(0, len(indices), 3)]
                yield (name, reverse), outline, outward, count, faces, normals, indices

    def test_roofs_face_up(self):
        for case, outline, _, _, faces, _, _ in self.meshes():
            with self.subTest(case=case):
                roofs = [f for f in faces if all(p[1] == self.HEIGHT for p in f)]
                self.assertEqual(len(roofs), len(outline) - 2)
                for face in roofs:
                    self.assertEqual(face_normal(face), (0, 1, 0))

    def test_bases_face_down(self):
        for case, outline, _, _, faces, _, _ in self.meshes():
            with self.subTest(case=case):
                bases = [f for f in faces if all(p[1] == 0 for p in f)]
                self.assertEqual(len(bases), len(outline) - 2)
                for face in bases:
                    self.assertEqual(face_normal(face), (0, -1, 0))

    def test_walls_remain_outward(self):
        for case, outline, outward, _, faces, _, _ in self.meshes():
            with self.subTest(case=case):
                walls = [f for f in faces if len({p[1] for p in f}) > 1]
                self.assertEqual(len(walls), 2 * len(outline))
                for i, expected in enumerate(outward):
                    edge = {tuple(outline[i]), tuple(outline[(i + 1) % len(outline)])}
                    pair = [f for f in walls if {(p[0], -p[2]) for p in f} == edge]
                    self.assertEqual(len(pair), 2)
                    for face in pair:
                        self.assertEqual(face_normal(face), expected)

    def test_triangle_counts_unchanged(self):
        for case, _, _, expected, faces, normals, indices in self.meshes():
            with self.subTest(case=case):
                self.assertEqual(len(faces), expected)
                self.assertEqual(len(indices), expected * 3)
                self.assertEqual(len(normals), expected * 9)

    def test_stored_normals_match_winding(self):
        for case, _, _, _, faces, normals, indices in self.meshes():
            with self.subTest(case=case):
                for i, face in enumerate(faces):
                    normal = face_normal(face)
                    for vertex in indices[i * 3:i * 3 + 3]:
                        self.assertEqual(tuple(normals[vertex * 3:vertex * 3 + 3]), normal)

    def test_solids_have_paired_opposite_edges(self):
        # Weld by position for inspection only: flat-shaded output duplicates vertices.
        for case, _, _, _, faces, _, _ in self.meshes():
            with self.subTest(case=case):
                edges = Counter((face[i], face[(i + 1) % 3])
                                for face in faces for i in range(3))
                for (a, b), count in edges.items():
                    self.assertEqual(count, 1)
                    self.assertEqual(edges[(b, a)], 1)


if __name__ == "__main__":
    unittest.main()
