"""Phase 2B: battlefield bounds, official-DEM reader, terrain mesh rules, committed terrain / shard / seam evidence.

Network-free; unit tests build synthetic inputs. Run with the NTW venv:  python -m pytest tests/test_ntw_phase2b.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/ntw"))
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))


def load(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


class BattlefieldTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load("worlds/battlefields/north_core_v1.json")
        self.study = load("data/ntw/battlefield/north_core_v1_study.json")
        self.zones = load("data/ntw/battlefield/north_core_v1_zones.json")

    def test_sizes_are_8km_multiples_and_96_is_infeasible(self):
        for s in self.cfg["mission_sizes_km"]:
            self.assertEqual(s % self.cfg["grid_km"], 0)
        self.assertEqual(self.study["results"]["96"]["feasible"], 0)
        for s in ("104", "112", "120"):
            self.assertGreater(self.study["results"][s]["feasible"], 0)

    def test_recommended_flyable_is_top_ranked_and_grid_aligned(self):
        top = self.study["results"][str(self.cfg["recommended_size_km"])]["top"][0]
        self.assertEqual(top["bounds_epsg3826"], self.zones["flyable_epsg3826"])
        for v in self.zones["flyable_epsg3826"]:
            self.assertEqual(v % 8000, 0)
        x0, y0, x1, y1 = self.zones["flyable_epsg3826"]
        self.assertEqual((x1 - x0, y1 - y0), (112000.0, 112000.0))
        self.assertEqual(set(top["regions_fully_inside"]) & {"TW-TPE", "TW-KEE", "TW-HSZ"}, {"TW-TPE", "TW-KEE", "TW-HSZ"})

    def test_sea_depth_grows_with_size(self):
        w = [self.study["results"][s]["top"][0]["depth_km"]["west_core_min"] for s in ("104", "112", "120")]
        n = [self.study["results"][s]["top"][0]["depth_km"]["north_core_min"] for s in ("104", "112", "120")]
        self.assertEqual(w, sorted(w))
        self.assertEqual(n, sorted(n))

    def test_production_is_flyable_plus_halo_and_inside_world(self):
        h = self.cfg["zones"]["production_halo_km"] * 1000
        f, p, w = self.zones["flyable_epsg3826"], self.zones["production_epsg3826"], self.zones["far_field_epsg3826"]
        self.assertEqual(p, [max(f[0] - h, w[0]), max(f[1] - h, w[1]), min(f[2] + h, w[2]), min(f[3] + h, w[3])])

    def test_dtm_gap_is_outside_production_and_blocked(self):
        g = self.zones["dtm_gap"]
        self.assertEqual(g["zones"], ["far_field"])
        self.assertGreater(g["distance_to_production_km"], 0)
        self.assertTrue(g["status"].startswith("BLOCKED"))

    def test_only_approved_key_sites_and_t1_only_in_flyable(self):
        self.assertNotIn("花蓮機場", self.cfg["approved_key_sites"])
        self.assertNotIn("臺中清泉崗機場", self.cfg["approved_key_sites"])
        st = self.zones["zone_tier_stats"]
        for z in ("production", "far_field"):
            self.assertNotIn("T1_high", st.get(z, {}))
        self.assertEqual(sum(t["cells"] for z in st.values() for t in z.values()), 784)


class OfficialDemReaderTests(unittest.TestCase):
    def _package(self, d):
        """Two overlapping 3x3 sheets on the 20 m grid; header layout as the official .hdr files."""
        def hdr(no, sw):
            return "\n".join(["sheet", no, "TWD97[2020]", "TWVD2001", "5000", "20", "20", "9", "3", "3",
                              str(sw[0]), str(sw[1]), "10", "LiDAR", "sensor", "2500", "9", "0", "4", "20210101", "agency",
                              "20220101", "producer"]).encode("cp950")
        def grd(sw, f):
            return "\n".join(f"{sw[0] + 20 * i} {sw[1] + 20 * j} {f(i, j):.2f}" for j in range(3) for i in range(3)).encode()
        z = Path(d) / "分幅_測試20MDEM(2025).zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("00000001dem.hdr", hdr("00000001", (1000, 2000)))
            zf.writestr("00000001dem.grd", grd((1000, 2000), lambda i, j: i + 10 * j))
            zf.writestr("00000002dem.hdr", hdr("00000002", (1040, 2000)))
            zf.writestr("00000002dem.grd", grd((1040, 2000), lambda i, j: (i + 2) + 10 * j))
        return d

    def test_mosaic_duplicates_agree_and_missing_nodes_are_nan(self):
        from tgos_dem import Dem
        with tempfile.TemporaryDirectory() as d, Dem(cache_dir=self._package(d)) as dem:
            self.assertEqual(len(dem.sheets), 2)
            z, src, sheets, dup = dem.mosaic((1000.0, 2000.0, 1120.0, 2040.0))
            self.assertEqual(z.shape, (3, 7))
            self.assertEqual(dup["duplicate_nodes"], 3)            # shared column x = 1040
            self.assertEqual(dup["duplicate_max_abs_diff_m"], 0.0)
            self.assertTrue(np.isnan(z[:, 5:]).all())               # x >= 1100: no sheet -> NaN, never 0 m
            self.assertEqual(z[2, 4], 4 + 20)
            with self.assertRaises(ValueError):
                dem.mosaic((1001.0, 2000.0, 1120.0, 2040.0))


class TerrainMeshTests(unittest.TestCase):
    def test_chunk_faces_face_up_skirts_vertical_and_drop_mask(self):
        import trimesh  # noqa: F401
        from build_terrain_cells import chunk_mesh
        xs = np.array([0.0, 20.0, 40.0])
        ys = np.array([0.0, 20.0, 40.0])
        Z = np.array([[0.0, 1.0, 2.0], [0.5, 1.5, 2.5], [1.0, 2.0, 3.0]])
        nrm = np.zeros((3, 3, 3))
        nrm[..., 2] = 1
        uv = np.zeros((3, 3, 2))
        m, nterr, removed = chunk_mesh(xs, ys, Z, nrm, uv, 2.0)
        self.assertEqual(nterr, 8)
        fn = m.face_normals
        self.assertTrue((fn[:8, 1] > 0).all())
        self.assertTrue((np.abs(fn[8:, 1]) < 1e-9).all())
        drop = np.zeros((3, 3), bool)
        drop[2, 2] = True
        m2, n2, rem = chunk_mesh(xs, ys, Z, nrm, uv, 2.0, drop)
        self.assertEqual(len(rem), 2)
        self.assertEqual(n2, 6)

    def test_vectorised_xinyi_enu_matches_accepted_formula(self):
        from build_terrain_cells import tm2_to_xinyi_enu
        from worldmodel import lonlat_to_enu
        import world_cells as wc
        import xinyi_world_compat as xc
        x = np.array([305600.0, 306800.0, 308000.0])
        y = np.array([2768600.0, 2769800.0, 2771000.0])
        e, n = tm2_to_xinyi_enu(x, y)
        lon, lat = wc.TO_LL.transform(x, y)
        for i in range(3):
            ee, nn = lonlat_to_enu(lon[i], lat[i], xc.O_LON, xc.O_LAT)
            self.assertAlmostEqual(e[i], ee, places=6)
            self.assertAlmostEqual(n[i], nn, places=6)


class TerrainEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.q = load("data/ntw/terrain/pilot_terrain_qa.json")

    def test_independent_cells_equal_joint_build(self):
        s = self.q["shard"]
        self.assertTrue(s["joint_repeat_manifest_identical"])
        self.assertTrue(s["independent_vs_joint_identical"])
        self.assertEqual(s["orphans_or_duplicates"], {"in_joint_not_independent": 0, "in_independent_not_joint": 0})

    def test_seams_and_orientation(self):
        sl = self.q["seams_conformed"]["same_lod"]
        self.assertEqual(sl["position_mismatch"], 0)
        self.assertGreater(sl["cross_cell_edges"], 0)
        self.assertLess(sl["normal_max_angle_deg"], 1e-3)
        self.assertEqual(sl["uv_max_abs_diff"], 0.0)
        self.assertEqual(self.q["seams_conformed"]["cross_lod"]["max_gap_over_skirt"], 0)
        o = self.q["face_orientation"]
        self.assertEqual(o["faces_not_facing_up"], 0)
        self.assertEqual(o["skirt_faces_not_vertical"], 0)

    def test_xinyi_stitch_is_watertight_at_every_lod(self):
        for lod, r in self.q["xinyi_stitch"].items():
            self.assertEqual(r["edge_vertices_missing"], 0, lod)
            self.assertEqual(r["edge_height_max_err_m"], 0.0, lod)
            self.assertEqual(r["edge_segments_present_as_mesh_edges"], r["edge_segments"], lod)
            self.assertEqual(r["hole_side_vertices_not_equal_to_chunk_vertices"], 0, lod)
            self.assertLess(r["gap_area_m2"], 1.0, lod)
            self.assertLess(r["overlap_area_m2"], 1.0, lod)

    def test_datum_offset_is_measured_not_assumed(self):
        a = self.q["xinyi_seam"]["all_sides"]
        self.assertAlmostEqual(a["raw_official_minus_xinyi_median_m"], -a["accepted_xinyi_vertical_offset_m"], delta=0.05)
        rng = self.q["sources"]["official_minus_wfs_surveyed_ground"]["chunk_median_range_m"]
        self.assertGreater(rng[1] - rng[0], 0.5)   # spatially varying: no single global offset

    def test_source_is_official_and_fail_closed(self):
        s = self.q["terrain_report_summary"]
        self.assertEqual(s["fail_closed"]["land_nodes_missing"], 0)
        self.assertIn("TGOS", s["source"]["product"])
        self.assertEqual(s["source"]["duplicate_nodes"]["duplicate_max_abs_diff_m"], 0.0)


class UnrealImportEvidenceTests(unittest.TestCase):
    def test_isolated_ue_import(self):
        r = load("data/ntw/terrain/ue_import_check.json")
        for v in ("baked", "local"):
            self.assertEqual(r[v]["errors"], 0)
            self.assertTrue(r[v]["triangle_counts_equal_glb"])
            self.assertEqual(r[v]["surface_shared_vertex_max_height_diff_m"], 0.0)
        self.assertTrue(r["baked"]["interchange_baked_node_translation"])
        self.assertGreater(r["baked"]["max_vertex_error_ue_to_glb_m"], 0.001)   # float32 at ~80 km
        self.assertFalse(r["local"]["interchange_baked_node_translation"])
        self.assertLess(r["local"]["max_vertex_error_ue_to_glb_m"], 0.001)     # tile-local precision preserved
        self.assertIn("runtime streaming", r["local"]["not_tested"])


class BuildingShardTests(unittest.TestCase):
    def test_shard_evidence(self):
        r = load("data/ntw/terrain/building_shard_test.json")
        self.assertTrue(r["pass"])
        self.assertEqual(r["tiles"]["joint_tiles_byte_identical_to_independent"], r["tiles"]["joint"])
        self.assertEqual(r["ownership"]["parts_emitted_by_both_shards"], 0)
        self.assertEqual(r["xinyi"]["xinyi_ids_emitted"], 0)
        self.assertEqual(len(r["ledgered_repair_fragments_joint"]), 1)
        self.assertFalse(r["strict_mode_evidence"]["north_gate_pass"])   # strict accepted policy still fails closed

    def test_fragment_policy_defaults_to_strict(self):
        import build_pilot
        self.assertFalse(build_pilot.FRAGMENT_POLICY["enabled"])


if __name__ == "__main__":
    unittest.main()
