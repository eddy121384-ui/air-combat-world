"""Taipei large wall ads v0: eligibility rules, deterministic placement, atlas content policy, shader isolation."""
from __future__ import annotations

import gzip
import json
import math
import random
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/lookdev"))

import build_wall_ad_atlas as wa_atlas  # noqa: E402
import build_wall_ads as wa  # noqa: E402
import ue_custom_code as ucc  # noqa: E402

OUT = REPO / "unreal/Saved/XinyiLook/wall_ads"
CITY_HLSL = (REPO / "tools/lookdev/shaders/xinyi_city.hlsl").read_text(encoding="utf-8")
WA_HLSL = (REPO / "tools/lookdev/shaders/xinyi_wall_ads.hlsl").read_text(encoding="utf-8")


def rec(arch=wa.ARCH_WALKUP, gen="legacy", flags=0):
    return {"archetype": arch, "facade_generation": gen, "flags": flags}


def wall(i=0, run=10.0, band=14.0, gen="legacy", arch="walkup", cond="road_face", major=True, core=False):
    return {"wall_id": "b%d/0/%d" % (i, i), "building_id": "b%d" % i, "group": "g%d" % i, "archetype": arch,
            "generation": gen, "core": core, "weather": 150, "tile": [i // 10, 0], "p0": [i * 60.0, 0.0],
            "p1": [i * 60.0 + run, 0.0], "normal_deg": -90.0, "edge_len_m": run, "run_len_m": run, "ground_m": 8.0,
            "top_m": 8.0 + band + 12.0, "neighbour_top_m": 18.0, "z_bottom_m": 19.0, "z_top_m": 19.0 + band,
            "band_m": band, "area_m2": run * band, "condition": cond, "major_road": major, "face_road": None,
            "end_role": 7}


class TestEligibility(unittest.TestCase):
    def test_host_classes(self):
        self.assertIsNone(wa.host_reason(rec()))
        self.assertIsNone(wa.host_reason(rec(wa.ARCH_RESTOWER, "huaxia")))
        for r, why in ((rec(wa.ARCH_SCHOOL), "class_school"), (rec(wa.ARCH_CIVIC), "class_civic_or_landmark"),
                       (rec(wa.ARCH_OFFICE, "unknown"), "class_office_or_podium"),
                       (rec(wa.ARCH_PODIUM, "unknown"), "class_office_or_podium"),
                       (rec(flags=wa.FLAG_ROOFTOP), "class_rooftop_structure"),
                       (rec(wa.ARCH_RESTOWER, "modern"), "class_modern_or_premium"),
                       (rec(wa.ARCH_RESTOWER, "premium"), "class_modern_or_premium"),
                       (rec(wa.ARCH_HUAXIA, "unknown"), "class_unknown_generation")):
            self.assertEqual(wa.host_reason(r), why)

    def test_longest_run(self):
        self.assertEqual(wa.longest_run([0, 1, 1, 0, 1, 1, 1, 0]), (4, 3))
        self.assertEqual(wa.longest_run([0, 0]), (0, 0))
        self.assertEqual(wa.longest_run([1, 1, 1]), (0, 3))

    def test_lot_line_distance_is_the_regulation(self):
        # 建築技術規則 §45(2): windows toward the neighbour only when the wall is >= 1 m from the boundary
        self.assertEqual(wa.LOT_LINE_M, 1.0)
        self.assertLessEqual(max(wa.LOT_PROBES), wa.LOT_LINE_M)

    def test_no_building_ids_in_rules(self):
        src = (REPO / "tools/lookdev/build_wall_ads.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"tp_building_height\.\d+", src))


class TestPlacement(unittest.TestCase):
    def test_board_size(self):
        self.assertIsNone(wa.board_size(wall(run=4.0, band=20.0)))       # 0.85 x 4 m < 4 m minimum width
        b, w, h = wa.board_size(wall(run=10.0, band=30.0))
        self.assertEqual(b, "T")
        self.assertAlmostEqual(h, 2.0 * w)
        b, w, h = wa.board_size(wall(run=20.0, band=7.0))
        self.assertEqual(b, "W")
        for run, band in ((6, 6), (12, 9), (40, 80), (8, 40)):
            s = wa.board_size(wall(run=run, band=band))
            if s:
                self.assertLessEqual(s[1], min(wa.FILL_W * run, wa.MAX_BOARD_W_M) + 1e-9)
                self.assertLessEqual(s[2], min(wa.FILL_H * band, wa.MAX_BOARD_H_M) + 1e-9)

    def _atlas(self):
        p = OUT / "wall_ad_atlas.json"
        if not p.is_file():
            self.skipTest("atlas not built")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_select_deterministic_and_order_independent(self):
        atlas = self._atlas()
        walls = [wall(i, run=8 + (i % 5) * 3, band=8 + (i % 7) * 4, gen=("legacy", "huaxia")[i % 2],
                      cond=("road_face", "street_end", "corner")[i % 3], major=bool(i % 2)) for i in range(60)]
        a, _ = wa.select(walls, atlas)
        sh = list(walls)
        random.Random(3).shuffle(sh)
        b, _ = wa.select(sh, atlas)
        key = lambda ps: [(p["wall"]["wall_id"], p["cell"]["id"], round(p["z"], 6), round(p["w"], 6)) for p in ps]
        self.assertEqual(key(a), key(b))
        self.assertEqual(len(a), round(wa.OCCUPANCY * len(walls)))
        self.assertGreaterEqual(sum(p["cell"]["aged"] for p in a), wa.AGED_MIN_SHARE * len(a))
        for i, p in enumerate(a):           # placement order: each board saw < CLUSTER_CAP earlier boards nearby
            self.assertLess(sum(math.hypot(p["e"] - q["e"], p["n"] - q["n"]) < wa.CLUSTER_R_M for q in a[:i]),
                            wa.CLUSTER_CAP)
            for q in a[i + 1:]:
                d = math.hypot(p["e"] - q["e"], p["n"] - q["n"])
                self.assertGreaterEqual(d, wa.SPACING_M)
                if p["cell"]["id"] == q["cell"]["id"]:
                    self.assertGreaterEqual(d, wa.SAME_CELL_SPACING_M)

    def test_plane_faces_plus_x(self):
        import tempfile
        import numpy as np
        from gltf_writer import read_glb_primitives
        with tempfile.TemporaryDirectory() as td:
            wa.write_plane(Path(td) / "p.glb")
            pr = read_glb_primitives(Path(td) / "p.glb")[0]
        pos = np.asarray(pr["position"], float)
        enu = np.column_stack([pos[:, 0], -pos[:, 2], pos[:, 1]])
        tri = enu[np.asarray(pr["indices"]).reshape(-1, 3)]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        self.assertTrue((n[:, 0] > 0).all())                      # counter-clockwise seen from +x (the front)


class TestAtlasContent(unittest.TestCase):
    def test_text_policy(self):
        fonts = {"sans": wa_atlas.sa.find_font("sans"), "serif": wa_atlas.sa.find_font("serif")}
        self.assertEqual(wa_atlas.check_text(wa_atlas.CELLS, fonts), [])
        for c in wa_atlas.CELLS:
            txt = c.get("title", "") + c.get("sub", "") + c.get("tag", "")
            self.assertIsNone(re.search(r"\d{3,}|[0-9]-[0-9]|https?|www|\.com", txt))   # no phone / web
            txt.replace(" ", "").encode("big5")

    def test_bins_fit_and_aged_share(self):
        n = {b: sum(1 for c in wa_atlas.CELLS if c["bin"] == b) for b, *_ in wa_atlas.BINS}
        for b, w, h, cols, rows, y0 in wa_atlas.BINS:
            self.assertLessEqual(n[b], cols * rows)
            self.assertEqual(w & (w - 1), 0)
            self.assertEqual(h & (h - 1), 0)
        aged = sum(1 for c in wa_atlas.CELLS if c.get("age", "none") != "none")
        self.assertGreaterEqual(aged / len(wa_atlas.CELLS), 0.2)


class TestShaderIsolation(unittest.TestCase):
    def test_wall_ads_not_in_city_or_street_materials(self):
        self.assertNotIn("M_XinyiWallAds", ucc.MATERIALS)
        self.assertNotIn("wa_shade", CITY_HLSL)
        for m in ucc.MATERIALS:
            self.assertNotIn("XinyiWallAdFns", ucc.custom_code(m))
        self.assertIn("wa_uv", ucc.wallads_uv_code())
        self.assertIn("wa_shade", ucc.wallads_custom_code())
        self.assertNotIn("xc_", WA_HLSL.replace("xc_unpack", ""))       # no dependency on the city shader

    def test_hlsl_uv_layout_matches_atlas(self):
        """Python mirror of wa_uv's cell -> rect mapping equals the atlas builder's slots for every cell id."""
        slots, base = {}, 0
        for b, w, h, cols, rows, y0 in wa_atlas.BINS:
            for k in range(cols * rows):
                slots[base + k] = ((k % cols) * w, y0 + (k // cols) * h, w, h)
            base += cols * rows
        for cell, rect in slots.items():
            isS = 15.5 < cell < 31.5
            isW = cell > 31.5
            k = cell - 16 * isS - 32 * isW
            cols = 4 if isW else 8
            size = (512, 256) if isW else (256, 256) if isS else (256, 512)
            row = k // cols
            org = ((k - row * cols) * size[0], 1024 * isS + 1536 * isW + row * size[1])
            self.assertEqual((org[0], org[1], size[0], size[1]), rect, cell)
        self.assertIn("256.0, 512.0", WA_HLSL)
        self.assertIn("512.0, 256.0", WA_HLSL)


class TestBuiltPlan(unittest.TestCase):
    """Checks on the built plan (skipped when the offline outputs are absent)."""

    @classmethod
    def setUpClass(cls):
        p, r = OUT / "wall_ads.json", OUT / "wall_ads.report.json"
        if not p.is_file() or not r.is_file():
            raise unittest.SkipTest("wall ads not built")
        cls.inst = json.loads(p.read_text(encoding="utf-8"))["instances"]
        cls.rep = json.loads(r.read_text(encoding="utf-8"))
        cls.audit = json.loads((OUT / "wall_ad_audit.json").read_text(encoding="utf-8"))
        side = {}
        with gzip.open(REPO / "unreal/Saved/XinyiLook/look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
            for line in fh:
                x = json.loads(line)
                side[x["building_id"]] = x
        cls.side = side

    def test_status_and_attachment(self):
        self.assertEqual(self.rep["status"], "PASS_WALL_ADS")
        self.assertEqual(self.rep["attachment_failures"], [])

    def test_hosts_respect_exclusions(self):
        valid = {w["wall_id"] for w in self.audit["walls"]}
        groups = set()
        for i in self.inst:
            self.assertIn(i["wall_id"], valid)
            r = self.side[i["wall_id"].split("/")[0]]
            self.assertIsNone(wa.host_reason(r))
            self.assertNotIn(r["group"], groups)                  # one board per building
            groups.add(r["group"])
            self.assertIn(i["condition"], ("road_face", "street_end", "corner"))

    def test_mix_and_night(self):
        n = len(self.inst)
        self.assertGreaterEqual(sum(i["aged"] for i in self.inst), wa.AGED_MIN_SHARE * n)
        self.assertLessEqual(sum(i["lit"] for i in self.inst), 0.25 * n)
        self.assertFalse(any(i["lit"] and (i["painted"] or i["aged"]) for i in self.inst))
        self.assertLessEqual(n, round(wa.OCCUPANCY * len(self.audit["walls"])))


if __name__ == "__main__":
    unittest.main()
