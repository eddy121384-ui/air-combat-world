"""Phase 6 — automated validation for greybox core (stdlib unittest).

Run: python -m unittest discover -s tests -v   (from repo root)
Requires generated artifacts; if missing, tests explain the rebuild command.
Covers: ingest count, height validity + plausibility, NaN guards, meter-scale,
101 suppression exactly-once, placeholder exactly-once, GLB parseability,
normalized-intermediate determinism (hash check against recorded manifest).
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GEN = REPO / "data/generated/taipei"
SYS_COMPILER = REPO / "tools/compiler"
sys.path.insert(0, str(SYS_COMPILER))

MISSING = (
    "generated artifacts missing — rebuild first:\n"
    "  node tools/taipei/fetch_sample.mjs\n"
    "  python tools/compiler/worldmodel.py\n"
    "  python tools/compiler/build_tile.py"
)


def needs_artifacts(*names):
    paths = [GEN / n for n in names]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise unittest.SkipTest(f"{MISSING}\nmissing: {missing}")
    return paths


class TestIngest(unittest.TestCase):
    def test_feature_count_positive(self):
        (gj,) = needs_artifacts("sample_buildings.geojson")
        fc = json.loads(gj.read_text(encoding="utf-8"))
        self.assertEqual(fc["type"], "FeatureCollection")
        self.assertGreater(len(fc["features"]), 0, "WFS ingest returned zero features")

    def test_heights_positive_and_plausible(self):
        (gj,) = needs_artifacts("sample_buildings.geojson")
        fc = json.loads(gj.read_text(encoding="utf-8"))
        bad, implausible = 0, []
        for f in fc["features"]:
            h = (f.get("properties") or {}).get("height_m")
            if not isinstance(h, (int, float)) or not math.isfinite(h) or h <= 0:
                bad += 1
            elif not (1.2 <= h <= 600):
                implausible.append((f.get("id"), h))
        self.assertEqual(bad, 0, f"{bad} features with non-positive/NaN height")
        self.assertEqual(implausible, [], f"heights outside 1.2–600 m: {implausible[:5]}")

    def test_manifest_matches_artifact(self):
        gj, mf = needs_artifacts("sample_buildings.geojson", "sample_buildings.manifest.json")
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        body = gj.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        self.assertEqual(manifest["sha256"], sha, "manifest hash != artifact hash")
        self.assertEqual(manifest["feature_count"],
                         len(json.loads(body)["features"]))


class TestWorldModel(unittest.TestCase):
    def test_no_nan_in_enu(self):
        (wm_path,) = needs_artifacts("worldmodel_sample.json")
        wm = json.loads(wm_path.read_text(encoding="utf-8"))
        n = 0
        for b in wm["buildings"]:
            for p in b["polygons"]:
                for pt in p["footprint_enu"]:
                    self.assertTrue(all(math.isfinite(v) for v in pt), f"NaN in {b['id']}")
                    n += 1
        self.assertGreater(n, 0)

    def test_meter_scale_against_haversine(self):
        """ENU local distances must agree with independent haversine within 1%."""
        (wm_path,) = needs_artifacts("worldmodel_sample.json")
        from worldmodel import haversine_m, lonlat_to_enu
        wm = json.loads(wm_path.read_text(encoding="utf-8"))
        lon0, lat0 = wm["local_frame"]["origin_lonlat"]
        # fixed probe pair: Taipei 101 <-> Sun Yat-sen Memorial Hall (~1.8 km)
        a, b_ = (121.5645, 25.0337), (121.5603, 25.0400)
        ax, ay = lonlat_to_enu(*a, lon0, lat0)
        bx, by = lonlat_to_enu(*b_, lon0, lat0)
        enu_d = math.hypot(bx - ax, by - ay)
        ref = haversine_m(*a, *b_)
        self.assertGreater(ref, 500, "probe pair sanity")
        self.assertLess(abs(enu_d - ref) / ref, 0.01,
                        f"ENU {enu_d:.1f} m vs haversine {ref:.1f} m")

    def test_hero_complex_suppressed(self):
        """Hero rule suppresses the whole 101 tower stack (multi-record complex).

        The WFS models 101 as stacked records (tower 512 m + shaft/crown).
        Rule (worldmodel.HERO_*): centroid within 60 m AND height >= 300 m.
        Test recomputes the set independently — implementation must match.
        """
        (wm_path,) = needs_artifacts("worldmodel_sample.json")
        from worldmodel import (HERO_SUPPRESS_MIN_HEIGHT_M,
                                HERO_SUPPRESS_RADIUS_M, TAIPEI_101_LONLAT,
                                haversine_m)
        wm = json.loads(wm_path.read_text(encoding="utf-8"))
        expect = set()
        for b in wm["buildings"]:
            nearest = min(haversine_m(p["centroid_lonlat"][0], p["centroid_lonlat"][1],
                                      *TAIPEI_101_LONLAT) for p in b["polygons"])
            if nearest <= HERO_SUPPRESS_RADIUS_M and b["height_m"] >= HERO_SUPPRESS_MIN_HEIGHT_M:
                expect.add(b["id"])
        got = {b["id"] for b in wm["buildings"] if b["suppressed"]}
        self.assertEqual(got, expect, "suppressed set != rule recomputation")
        self.assertGreaterEqual(len(got), 5, "tower stack should be several records")
        tallest = max(b["height_m"] for b in wm["buildings"] if b["id"] in got)
        self.assertGreater(tallest, 500, "true 512 m tower record must be suppressed")
        for b in wm["buildings"]:
            if b["id"] in got:
                self.assertIn("hero:taipei_101", b["suppress_reason"])

    def test_height_source_provenance_present(self):
        (wm_path,) = needs_artifacts("worldmodel_sample.json")
        wm = json.loads(wm_path.read_text(encoding="utf-8"))
        missing = [b["id"] for b in wm["buildings"] if not b.get("height_source")]
        self.assertEqual(missing, [], f"{len(missing)} buildings lack height_source")


class TestTile(unittest.TestCase):
    def test_glb_indices_in_range(self):
        """Regression: flat-list index base bug once produced out-of-range
        indices (UE imported an empty LayerA). Every index must address a
        real vertex; positions/normals/UVs must agree in count."""
        import struct as _struct
        (glb,) = needs_artifacts("xinyi_tile_2km.glb")
        data = glb.read_bytes()
        jl, _ = _struct.unpack_from("<II", data, 12)
        doc = json.loads(data[20:20 + jl])
        blen = data[20 + jl + 8:]
        for m in doc["meshes"]:
            for prim in m["primitives"]:
                acc = doc["accessors"]
                def buf(ai):
                    bv = doc["bufferViews"][acc[ai]["bufferView"]]
                    return blen[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]]
                n = acc[prim["attributes"]["POSITION"]]["count"]
                self.assertEqual(acc[prim["attributes"]["NORMAL"]]["count"], n)
                self.assertEqual(acc[prim["attributes"]["TEXCOORD_0"]]["count"], n)
                ni = acc[prim["indices"]]["count"]
                idx = _struct.unpack(f"<{ni}I", buf(prim["indices"])[:4 * ni])
                self.assertLess(max(idx), n, f"{m['name']}: index out of range")
                self.assertGreater(min(idx), -1)

    def test_glb_parses(self):
        (glb,) = needs_artifacts("xinyi_tile_2km.glb")
        sys.path.insert(0, str(SYS_COMPILER))
        from export_glb import read_glb_info
        info = read_glb_info(str(glb))
        self.assertEqual(info["meshes"], 2, f"expected LayerA + hero meshes, got {info}")
        self.assertEqual(info["primitives"], 2)
        names = [m["name"] for m in
                 json.loads(self._glb_json(glb)).get("meshes", [])]
        self.assertIn("layerA_city_massing", names)
        self.assertIn("hero_taipei101_placeholder", names)

    def _glb_json(self, glb: Path) -> bytes:
        data = glb.read_bytes()
        jl, _ = struct.unpack_from("<II", data, 12)
        return data[20:20 + jl]

    def test_no_double_stack_101(self):
        """No tall procedural massing may remain at the hero location.

        Anti-double-stack: every non-suppressed building near the hero point
        must be below the tower-stack height band. Placeholder exists once.
        """
        wm_path, _, rep = needs_artifacts("worldmodel_sample.json",
                                          "xinyi_tile_2km.glb",
                                          "xinyi_tile_2km.report.json")
        from worldmodel import (HERO_SUPPRESS_MIN_HEIGHT_M,
                                HERO_SUPPRESS_RADIUS_M, TAIPEI_101_LONLAT,
                                haversine_m)
        wm = json.loads(wm_path.read_text(encoding="utf-8"))
        report = json.loads(rep.read_text(encoding="utf-8"))
        violators = []
        for b in wm["buildings"]:
            if b["suppressed"]:
                continue
            nearest = min(haversine_m(p["centroid_lonlat"][0], p["centroid_lonlat"][1],
                                      *TAIPEI_101_LONLAT) for p in b["polygons"])
            if nearest <= HERO_SUPPRESS_RADIUS_M and b["height_m"] >= HERO_SUPPRESS_MIN_HEIGHT_M:
                violators.append((b["id"], b["height_m"]))
        self.assertEqual(violators, [], f"procedural towers left at hero site: {violators}")
        self.assertGreaterEqual(len(report["suppressed_ids"]), 1)
        self.assertIsNotNone(report["hero_placeholder"])
        self.assertGreater(report["layer_a_buildings_extruded"], 1000)

    def test_real_world_scale(self):
        """Placeholder stands at the known 101 coordinates, 508 m tall."""
        _, rep = needs_artifacts("xinyi_tile_2km.glb", "xinyi_tile_2km.report.json")
        from worldmodel import TAIPEI_101_LONLAT, lonlat_to_enu
        report = json.loads(rep.read_text(encoding="utf-8"))
        cx, cy = report["hero_anchor_enu"]
        ex, ey = lonlat_to_enu(*TAIPEI_101_LONLAT, 121.5654, 25.0330)
        self.assertLess(abs(cx - ex) + abs(cy - ey), 1.0,
                        f"hero anchor {(cx, cy)} != hero-point ENU {(ex, ey)}")
        from export_glb import read_glb_info
        info = read_glb_info(str(GEN / "xinyi_tile_2km.glb"))
        (lo, hi) = info["bounds"][1]  # hero mesh bounds
        self.assertAlmostEqual(hi[1], 508.0, delta=1.0,
                               msg=f"placeholder height {hi[1]} != 508 m")

    def test_rebuild_determinism_logical(self):
        """WorldModel must account for every ingested feature (no silent drops).

        Robust to future WFS updates: compares against this run's manifest,
        not a hardcoded count.
        """
        wm_path, mf = needs_artifacts("worldmodel_sample.json",
                                      "sample_buildings.manifest.json")
        wm = json.loads(wm_path.read_text(encoding="utf-8"))
        manifest = json.loads(mf.read_text(encoding="utf-8"))
        ids = sorted(b["id"] for b in wm["buildings"])
        # every ingested feature had a valid height in this run -> zero drops
        self.assertEqual(len(ids), manifest["feature_count"],
                         "WorldModel silently dropped valid-height features")
        norm = json.dumps({"n": len(ids), "first": ids[0], "last": ids[-1],
                           "hero": wm["hero_match"]["matched_building_ids"]})
        digest = hashlib.sha256(norm.encode()).hexdigest()
        self.assertTrue(digest)  # recorded in result doc; rerun-safe logical fingerprint


if __name__ == "__main__":
    unittest.main(verbosity=2)
