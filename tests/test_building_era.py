"""Building era metadata v0: schema, determinism, join, provenance and licence-gate tests."""
from __future__ import annotations

import gzip
import io
import json
import random
import sys
import unittest
from pathlib import Path

from shapely.geometry import box, mapping

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/building_era"))

import build_era_metadata as bem  # noqa: E402
import era_schema as es  # noqa: E402
import taipei_use_permits as tup  # noqa: E402


class TestBuckets(unittest.TestCase):
    def test_boundary_years(self):
        cases = {1700: "pre_1980", 1979: "pre_1980", 1980: "1980_1999", 1999: "1980_1999",
                 2000: "2000_2009", 2009: "2000_2009", 2010: "2010_2019", 2019: "2010_2019",
                 2020: "2020_plus", 2099: "2020_plus", None: "unknown"}
        for year, want in cases.items():
            self.assertEqual(es.bucket_for_year(year), want, year)

    def test_every_bucket_reachable_and_bounded(self):
        self.assertEqual(set(es.ERA_BUCKETS) - {"unknown"}, {es.bucket_for_year(y) for y in range(1900, 2031)})


class TestResolve(unittest.TestCase):
    def test_single_exact(self):
        r = es.resolve_candidates([("P1", 2005)], "parcel_overlap")
        self.assertEqual((r.era_confidence, r.construction_year, r.era_bucket, r.era_source),
                         ("exact", 2005, "2000_2009", "open_use_permit"))

    def test_same_year_duplicates_are_exact(self):
        r = es.resolve_candidates([("P1", 2005), ("P2", 2005), ("P1", 2005)], "parcel_overlap")
        self.assertEqual((r.era_confidence, r.era_evidence), ("exact", ("P1", "P2")))

    def test_same_bucket_is_range_without_year(self):
        r = es.resolve_candidates([("P1", 2003), ("P2", 2008)], "parcel_overlap")
        self.assertEqual((r.era_confidence, r.construction_year, r.year_min, r.year_max, r.era_bucket),
                         ("range", None, 2003, 2008, "2000_2009"))

    def test_cross_bucket_is_ambiguous_unknown(self):
        r = es.resolve_candidates([("P1", 2008), ("P2", 2012)], "parcel_overlap")
        self.assertEqual((r.era_confidence, r.era_bucket, r.era_ambiguous), ("unknown", "unknown", True))
        self.assertEqual(r.era_evidence, ("P1", "P2"))

    def test_input_order_independent(self):
        base = [("P%d" % i, y) for i, y in enumerate([2001, 2004, 2013, 2013, 2021])]
        want = es.resolve_candidates(base, "j")
        rng = random.Random(7)
        for _ in range(20):
            rng.shuffle(base)
            self.assertEqual(es.resolve_candidates(base, "j"), want)

    def test_none_is_unknown(self):
        self.assertEqual(es.resolve_candidates([], "j"), es.UNKNOWN)


class TestProvenanceRules(unittest.TestCase):
    def test_labels_stable(self):
        self.assertEqual(es.ERA_SOURCES, ("open_use_permit", "open_construction_permit", "profile_inference",
                                          "unknown"))
        self.assertEqual(es.SCHEMA, "acw.building_era/0")

    def test_inferred_cannot_pose_as_observed(self):
        with self.assertRaises(ValueError):
            es.validate_record(es.EraRecord(2005, 2005, 2005, "2000_2009", es.SRC_PROFILE_INFERENCE, "exact"))
        with self.assertRaises(ValueError):
            es.validate_record(es.EraRecord(None, 2000, 2009, "2000_2009", es.SRC_USE_PERMIT, "inferred"))

    def test_bounds_must_fit_bucket(self):
        with self.assertRaises(ValueError):
            es.validate_record(es.EraRecord(2012, 2012, 2012, "2000_2009", es.SRC_USE_PERMIT, "exact"))

    def test_research_only_source_rejected(self):
        for src in es.RESEARCH_ONLY_SOURCES:
            with self.assertRaises(ValueError):
                es.validate_record(es.EraRecord(2005, 2005, 2005, "2000_2009", src, "exact"))

    def test_roundtrip_dict(self):
        r = es.resolve_candidates([("P1", 2015)], "parcel_overlap")
        self.assertEqual(es.EraRecord.from_dict(json.loads(json.dumps(r.to_dict()))), r)


class TestInferenceHook(unittest.TestCase):
    def test_default_leaves_unknown(self):
        self.assertEqual(es.apply_inference(es.UNKNOWN, {"floors": 5}), es.UNKNOWN)

    def test_observed_beats_inference(self):
        obs = es.resolve_candidates([("P1", 2005)], "j")

        class Always:
            def infer(self, attrs):
                return es.EraRecord(None, 1960, 1979, "pre_1980", es.SRC_PROFILE_INFERENCE, "inferred")
        self.assertEqual(es.apply_inference(obs, {}, Always()), obs)

    def test_inferred_is_labelled_and_ambiguity_not_overwritten(self):
        class Always:
            def infer(self, attrs):
                return es.EraRecord(None, 1960, 1979, "pre_1980", es.SRC_PROFILE_INFERENCE, "inferred")
        got = es.apply_inference(es.UNKNOWN, {}, Always())
        self.assertEqual((got.era_source, got.era_confidence), ("profile_inference", "inferred"))
        amb = es.resolve_candidates([("P1", 2008), ("P2", 2012)], "j")
        self.assertEqual(es.apply_inference(amb, {}, Always()), amb)

    def test_dishonest_inferer_rejected(self):
        class Liar:
            def infer(self, attrs):
                return es.EraRecord(2001, 2001, 2001, "2000_2009", es.SRC_USE_PERMIT, "exact")
        with self.assertRaises(ValueError):
            es.apply_inference(es.UNKNOWN, {}, Liar())


class TestGroupAggregation(unittest.TestCase):
    def test_order_independent_and_conflict_is_ambiguous(self):
        a = es.resolve_candidates([("P1", 2003)], "j")
        b = es.resolve_candidates([("P2", 2014)], "j")
        members = [("a", 100.0, a), ("b", 90.0, b), ("c", 5.0, es.UNKNOWN)]
        r1 = es.aggregate_group(members)
        r2 = es.aggregate_group(list(reversed(members)))
        self.assertEqual(r1, r2)
        self.assertTrue(r1.era_ambiguous)
        self.assertEqual(r1.era_bucket, "unknown")

    def test_agreeing_members_and_unknown_podium(self):
        a = es.resolve_candidates([("P1", 2003)], "j")
        self.assertEqual(es.aggregate_group([("x", 50, es.UNKNOWN), ("y", 80, a)]), a)

    def test_all_unknown(self):
        self.assertEqual(es.aggregate_group([("x", 1, es.UNKNOWN)]), es.UNKNOWN)


class TestPermitParsing(unittest.TestCase):
    def test_roc_dates(self):
        self.assertEqual(tup.roc_date("0910702"), "2002-07-02")
        self.assertIsNone(tup.roc_date("0000000"))
        self.assertIsNone(tup.roc_date(""))
        self.assertIsNone(tup.roc_date("0911332"))

    def test_parcel_key_matches_wfs_form(self):
        self.assertEqual(tup.parcel_key("臺北市松山區寶清段四小段0547-0000號"), "寶清段四小段|05470000")
        self.assertEqual(tup.parcel_key("臺北市信義區信義段一小段0027-0020號"), "信義段一小段|00270020")
        self.assertIsNone(tup.parcel_key("garbage"))

    def test_year_rule(self):
        self.assertEqual(tup.permit_year("2002-01-03", "2002-07-02"), 2002)
        self.assertEqual(tup.permit_year("2005-01-03", "2001-01-01"), 2005)   # implausible completion -> issue year
        self.assertEqual(tup.permit_year("2005-01-03", None), 2005)
        self.assertIsNone(tup.permit_year(None, None))

    def test_xml_filters_new_build_only(self):
        def rec(no, kind):
            return ("<Data><執照號碼>%s</執照號碼><發照日期>0900103</發照日期><建造類別>%s</建造類別>"
                    "<竣工日期>0910702</竣工日期><建築地點/><地段地號><地段號>臺北市松山區寶清段四小段0547-0000號"
                    "</地段號></地段地號><建物高度>18M</建物高度></Data>" % (no, kind))
        xml = ("<Datas>" + rec("090使字第0001號", "新建") + rec("090使字第0002號", "增建") + "</Datas>").encode()
        out = list(tup.parse_permits(io.BytesIO(xml)))
        self.assertEqual([p["permit_no"] for p in out], ["090使字第0001號"])
        self.assertEqual((out[0]["year"], out[0]["height_m"], out[0]["parcels"]), (2002, 18.0, ["寶清段四小段|05470000"]))


def _fp(geom, h):
    return {"geom": geom, "height_m": h, "floors": None}


def _parcel(key, geom):
    return {"key": key, "geometry": mapping(geom)}


class TestJoin(unittest.TestCase):
    def setUp(self):
        self.parcels = [_parcel("S|00010000", box(0, 0, 20, 20)), _parcel("S|00020000", box(20, 0, 40, 20))]
        self.fps = {"b1": _fp(box(2, 2, 12, 12), 15.0),            # inside parcel 1
                    "b2": _fp(box(22, 2, 32, 12), 15.0),           # inside parcel 2
                    "b3": _fp(box(15, 2, 25, 12), 15.0),           # straddles: 50 % in each -> no match
                    "far": _fp(box(100, 100, 110, 110), 15.0)}
        self.permits = [{"permit_no": "A", "year": 2004, "height_m": 18.0, "parcels": ["S|00010000"]},
                        {"permit_no": "B", "year": 2011, "height_m": 18.0, "parcels": ["S|00020000"]}]

    def test_basic_exact_and_unmatched(self):
        recs, st = bem.join(self.fps, self.permits, self.parcels)
        self.assertEqual(recs["b1"].construction_year, 2004)
        self.assertEqual(recs["b2"].construction_year, 2011)
        self.assertEqual(recs["b3"], es.UNKNOWN)          # below MIN_OVERLAP: never guessed
        self.assertEqual(recs["far"], es.UNKNOWN)
        self.assertEqual(st["permits_matched_to_footprint"], 2)

    def test_competing_permits_same_parcel(self):
        permits = self.permits + [{"permit_no": "C", "year": 2018, "height_m": 18.0, "parcels": ["S|00010000"]}]
        recs, _ = bem.join(self.fps, permits, self.parcels)
        self.assertTrue(recs["b1"].era_ambiguous)         # 2004 vs 2018: different buckets
        self.assertEqual(recs["b1"].era_evidence, ("A", "C"))

    def test_height_conflict_rejected(self):
        permits = [{"permit_no": "A", "year": 2004, "height_m": 3.0, "parcels": ["S|00010000"]}]
        recs, st = bem.join(self.fps, permits, self.parcels)
        self.assertEqual(recs["b1"], es.UNKNOWN)
        self.assertEqual(st["candidates_rejected_height_conflict"], 1)

    def test_permit_outside_extent_counted(self):
        permits = [{"permit_no": "Z", "year": 2004, "height_m": 18.0, "parcels": ["Other|00010000"]}]
        _, st = bem.join(self.fps, permits, self.parcels)
        self.assertEqual(st["permits_without_parcel_in_extent"], 1)

    def test_input_order_independent(self):
        permits = self.permits + [{"permit_no": "C", "year": 2018, "height_m": 18.0, "parcels": ["S|00010000"]}]
        want, _ = bem.join(self.fps, permits, self.parcels)
        rng = random.Random(3)
        for _ in range(10):
            p, q = permits[:], self.parcels[:]
            rng.shuffle(p)
            rng.shuffle(q)
            fps = dict(reversed(list(self.fps.items())))
            got, _ = bem.join(fps, p, q)
            self.assertEqual(got, want)


class TestCommittedCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads(bem.META.read_text(encoding="utf-8"))
        cls.records = bem.load_records()

    def test_schema_valid_and_complete(self):
        fps = bem.load_footprints()
        self.assertEqual(set(self.records), set(fps))
        self.assertEqual(self.meta["stats"]["footprints_total"], len(fps))

    def test_cache_hash_matches_meta(self):
        import hashlib
        self.assertEqual(hashlib.sha256(bem.OUT.read_bytes()).hexdigest(), self.meta["cache_sha256"])

    def test_only_approved_sources_used(self):
        self.assertTrue(set(self.meta["sources_used"]) <= {"open_use_permit", "unknown"})
        self.assertTrue({r.era_source for r in self.records.values()} <= set(es.ERA_SOURCES))

    def test_bucket_counts_consistent(self):
        from collections import Counter
        self.assertEqual(dict(Counter(r.era_bucket for r in self.records.values())),
                         {k: v for k, v in self.meta["bucket_counts"].items()})

    @unittest.skipUnless(bem.PARCEL_CACHE.exists(), "parcel join geometry not cached locally")
    def test_rebuild_is_byte_identical(self):
        recs, stats = bem.join(bem.load_footprints(), tup.load(), bem.load_parcels())
        self.assertEqual(recs, self.records)
        self.assertEqual(stats, self.meta["stats"])


class TestLicenceGate(unittest.TestCase):
    """The City Dashboard `building_age` layer is research-only: it must never become a production input."""

    def test_no_building_age_dependency_in_era_tools(self):
        for p in (REPO / "tools/building_era").glob("*.py"):
            text = p.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "building_age" in line:
                    self.assertTrue(line.lstrip().startswith(("#", '"', "RESEARCH_ONLY", "The City", "*")) or
                                    "research-only" in line.lower() or "RESEARCH_ONLY" in line,
                                    f"{p.name}: unexpected building_age reference: {line!r}")
            self.assertNotIn("typeName=taipei_vioc:building_age", text)
            self.assertNotIn("taipei_vioc:building_age", text)

    def test_no_age_data_cached_in_repo(self):
        for d in (REPO / "data/lookdev_cache", REPO / "data/generated"):
            for p in d.rglob("*"):
                self.assertNotIn("building_age", p.name.lower(), p)

    def test_cache_meta_declares_research_only_not_used(self):
        meta = json.loads(bem.META.read_text(encoding="utf-8"))
        self.assertIn("citydashboard_building_age", meta["research_only_not_used"])
        self.assertNotIn("citydashboard_building_age", json.dumps(meta["sources_used"]))

    def test_permit_cache_records_open_licence_provenance(self):
        meta = json.loads(tup.META.read_text(encoding="utf-8"))
        for k in ("source_url", "licence", "retrieved_at", "raw_xml_sha256", "cache_sha256"):
            self.assertTrue(meta.get(k), k)
        self.assertIn("Government Open Data License", meta["licence"])

    def test_parcel_geometry_not_committed(self):
        self.assertFalse(any("parcel" in p.name.lower() for p in (REPO / "data/lookdev_cache").iterdir()))


class TestNoVisualWiring(unittest.TestCase):
    """v0 is data-only: nothing in the render / look-dev pipeline may consume era metadata yet."""

    def test_lookdev_and_shaders_do_not_reference_era(self):
        for p in list((REPO / "tools/lookdev").rglob("*.py")) + list((REPO / "tools/lookdev/shaders").rglob("*")):
            if p.is_file():
                text = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotIn("building_era", text, p)
                self.assertNotIn("era_bucket", text, p)


if __name__ == "__main__":
    unittest.main()
