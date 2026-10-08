"""Blank side-wall v0B: face selection rules, payload codes, shader contract, patched-tile integrity."""
from __future__ import annotations

import gzip
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import box
from shapely.strtree import STRtree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/lookdev"))

import build_blank_walls as bb  # noqa: E402
import build_wall_ads as wa  # noqa: E402
import facade_generation as fg  # noqa: E402
from gltf_writer import read_glb_primitives, write_glb  # noqa: E402

HLSL = (REPO / "tools/lookdev/shaders/xinyi_city.hlsl").read_text(encoding="utf-8")
OUT = REPO / "unreal/Saved/XinyiLook/blank_walls"
LOOK = REPO / "unreal/Saved/XinyiLook"


def body(fn):
    i = HLSL.index("void %s(" % fn)
    return HLSL[i:HLSL.index("\n}\n", i)]


class TestPayloadCodes(unittest.TestCase):
    def test_blank_codes_are_the_reserved_ones(self):
        self.assertEqual(fg.BLANK_FACE_OFFSET, 5)
        self.assertEqual(fg.GEN_PREMIUM + 1, fg.BLANK_FACE_OFFSET)
        self.assertLessEqual(fg.GEN_HUAXIA + fg.BLANK_FACE_OFFSET, fg.PAYLOAD_MAX)

    def test_round_trip_and_shader_mirror(self):
        for code in range(0, 3):
            for base in (0, 255, 256, 32767):
                x = np.float32((code + 5) * fg.PAYLOAD_UNIT + base)
                b0, c = fg.decode_x(float(x))
                self.assertEqual((b0, c), (base, code + 5))
                blank = 1.0 if c > 4.5 else 0.0                   # xc_wall: blankF = step(4.5, gen)
                self.assertEqual((blank, c - 5 * blank), (1.0, code))
        for code in range(0, 5):                                 # ordinary codes pass through untouched
            blank = 1.0 if code > 4.5 else 0.0
            self.assertEqual(code - 5 * blank, code)


class TestShaderContract(unittest.TestCase):
    def test_flag_decoded_before_generation_terms(self):
        w = body("xc_wall")
        i_dec = w.index("float blankF = step(4.5, gen);")
        self.assertIn("gen -= 5.0 * blankF;", w)
        self.assertLess(i_dec, w.index("float gHx = xc_eq(gen, 2.0);"))

    def test_branch_zeroes_every_opening_and_night_source(self):
        w = body("xc_wall")
        i = w.index("[branch] if (blankF > 0.5)")
        br = w[i:w.index("\n    }\n", i)]
        for v in ("win", "winMean", "balc", "knee", "frame", "cageCover", "ac", "tPier", "dBay", "isTower"):
            self.assertRegex(br, r"\b%s = 0\.0;" % v)
        # first arm of the composition chain: the accepted modern / premium / archetype arms follow unchanged
        self.assertLess(w.index("float3 c;"), i)
        end = w.index("\n    }\n", i) + len("\n    }\n")
        self.assertEqual(w.index("else if (gMo > 0.5)", i), end + 4)
        self.assertIn("c = lerp(bw0,", br)

    def test_unpack_and_other_materials_untouched(self):
        self.assertIn("gen = floor((d.x + 0.5) / 32768.0);", HLSL)
        self.assertNotIn("blankF", body("xc_city"))
        for fn in ("xc_school_wall", "xc_roof", "xc_taipei101", "xc_street", "xc_prop", "xc_ground"):
            self.assertNotIn("blankF", body(fn))


def part(bid, grp, poly, top=30.0):
    return (bid, grp, poly, top, 8.0)


class TestFaceRules(unittest.TestCase):
    """evaluate() rejects on geometry before touching any mesh."""

    def _run(self, parts):
        ctx = {"parts": parts}
        tree = STRtree([p[2] for p in parts])
        groups = [p[1] for p in parts]
        a, b = np.array([10.0, 0.0]), np.array([10.0, 10.0])     # east edge of the 10 x 10 host, outward +x
        return bb.probe(ctx, tree, groups, a, b, 0)

    def test_touching_party_wall(self):
        t, lot, own, *_ = self._run([part("h", "g1", box(0, 0, 10, 10)), part("n", "g2", box(10.05, 0, 20, 10))])
        self.assertGreaterEqual(t, bb.TOUCH_FRAC)
        self.assertGreaterEqual(lot, bb.LOT_FRAC)
        self.assertEqual(own, 0.0)

    def test_gap_is_ambiguous(self):
        t, lot, own, *_ = self._run([part("h", "g1", box(0, 0, 10, 10)), part("n", "g2", box(10.8, 0, 20, 10))])
        self.assertLess(t, bb.TOUCH_FRAC)                         # within 1 m but not shared: keep the facade

    def test_partial_lot_line(self):
        t, lot, own, *_ = self._run([part("h", "g1", box(0, 0, 10, 10)), part("n", "g2", box(10.0, 0, 20, 6))])
        self.assertLess(lot, bb.LOT_FRAC)                         # the open 4 m may hold windows

    def test_own_wing(self):
        t, lot, own, *_ = self._run([part("h", "g1", box(0, 0, 10, 10)), part("w", "g1", box(10.0, 0, 20, 10))])
        self.assertGreater(own, 0.0)
        self.assertEqual(lot, 0.0)


class TestBuiltTiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = OUT / "blank_walls.report.json"
        if not r.is_file():
            raise unittest.SkipTest("blank walls not built")
        cls.rep = json.loads(r.read_text(encoding="utf-8"))
        cls.doc = json.loads((OUT / "blank_walls.json").read_text(encoding="utf-8"))

    def test_status_scope_and_plan_unchanged(self):
        self.assertEqual(self.rep["status"], "PASS_BLANK_WALLS")
        self.assertLessEqual(self.rep["secondary_faces"], bb.SECONDARY_MAX)
        plan = (REPO / "unreal/Saved/XinyiLook/wall_ads/wall_ads.json").read_bytes()
        import hashlib
        self.assertEqual(self.rep["wall_ads_sha256"], hashlib.sha256(plan).hexdigest())
        hosts = {i["wall_id"] for i in json.loads(plan)["instances"]}
        side = {}
        with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
            for line in fh:
                x = json.loads(line)
                side[x["building_id"]] = x
        for f in self.doc["faces"]:
            self.assertEqual(f["scope"] == "ad_host", f["wall_id"] in hosts)
            self.assertIsNone(wa.host_reason(side[f["building_id"]]))        # no school / office / civic / modern
            self.assertEqual(f["roles"], [bb.FRONT_REAR])
            self.assertEqual(f["own_frac"], 0.0)
            self.assertGreaterEqual(f["touch_frac"], bb.TOUCH_FRAC)

    def test_only_marked_vertices_change(self):
        src_rows = {r["tile"]: r for r in json.loads((LOOK / "look_tiles.report.json").read_text())["tiles"]}
        for row in self.rep["tiles"]:
            a = read_glb_primitives(LOOK / "tiles" / src_rows[row["tile"]]["path"])[0]
            b = read_glb_primitives(OUT / "tiles_blank" / row["path"])[0]
            self.assertEqual(row["source_sha256"], src_rows[row["tile"]]["sha256"])
            sa = np.asarray(a["position"])[np.asarray(a["indices"]).reshape(-1, 3)]
            sb = np.asarray(b["position"])[np.asarray(b["indices"]).reshape(-1, 3)]
            self.assertTrue(np.array_equal(sa, sb))                          # triangle soup identical
            n = len(a["position"])
            for k in ("position", "normal", "texcoord_0", "texcoord_1"):
                self.assertTrue(np.array_equal(np.asarray(a[k]), np.asarray(b[k])[:n]), k)
            self.assertTrue(np.array_equal(np.asarray(a["texcoord_2"])[:, 1], np.asarray(b["texcoord_2"])[:n, 1]))
            xa, xb = np.asarray(a["texcoord_2"])[:, 0], np.asarray(b["texcoord_2"])[:n, 0]
            changed = np.nonzero(xa != xb)[0]
            self.assertEqual(len(changed) + row["vertices_duplicated"], row["vertices_marked"])
            for v in changed:
                b0, c0 = fg.decode_x(float(xa[v]))
                b1, c1 = fg.decode_x(float(xb[v]))
                self.assertEqual((b1, c1), (b0, c0 + bb.BLANK_OFFSET))
                self.assertLessEqual(c0, fg.GEN_HUAXIA)

    def test_writer_round_trip_is_byte_identical(self):
        row = json.loads((LOOK / "look_tiles.report.json").read_text())["tiles"][0]
        src = LOOK / "tiles" / row["path"]
        p = read_glb_primitives(src)[0]
        with tempfile.TemporaryDirectory() as td:
            write_glb(Path(td) / "t.glb", [{
                "name": "XinyiCity", "positions": np.asarray(p["position"]), "normals": np.asarray(p["normal"]),
                "uv0": np.asarray(p["texcoord_0"]), "uv1": np.asarray(p["texcoord_1"]),
                "uv2": np.asarray(p["texcoord_2"]), "indices": np.asarray(p["indices"]).astype(np.uint32),
                "base_color": [0.7, 0.7, 0.7, 1.0]}], mesh_name=f"SM_XinyiLook_{row['tile']}")
            self.assertEqual((Path(td) / "t.glb").read_bytes(), src.read_bytes())


if __name__ == "__main__":
    unittest.main()
