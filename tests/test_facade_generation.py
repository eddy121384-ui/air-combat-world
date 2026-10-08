"""Facade generation payload v0: classification semantics + TEXCOORD_2 headroom encoding."""
from __future__ import annotations

import ast
import random
import re
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools/lookdev"))
sys.path.insert(0, str(REPO / "tools/building_era"))

import era_schema as es  # noqa: E402
import facade_generation as fg  # noqa: E402
from gltf_writer import pack_rgba8  # noqa: E402

HLSL = (REPO / "tools/lookdev/shaders/xinyi_city.hlsl").read_text(encoding="utf-8")


def era(bucket, conf="exact", source=es.SRC_USE_PERMIT, ambiguous=False):
    year = {"pre_1980": 1970, "1980_1999": 1990, "2000_2009": 2005, "2010_2019": 2015, "2020_plus": 2022}.get(bucket)
    if conf == "exact":
        return es.EraRecord(year, year, year, bucket, source, conf, "parcel_overlap", ("P1",))
    if conf == "inferred":
        return es.EraRecord(None, None, None, bucket, es.SRC_PROFILE_INFERENCE, conf, "profile_rule")
    return es.EraRecord(None, year, year, bucket, source, conf, "parcel_overlap", ("P1",))


def cls(arch=fg.ARCH_HUAXIA, floors=8, height=26.0, fh=3.25, core=False, e=None, landmark=False):
    return fg.classify(arch, floors, height, fh, core, e, landmark)


class TestClassification(unittest.TestCase):
    def test_deterministic_and_order_independent(self):
        cases = [(a, f, f * 3.3, 3.3, c, e) for a in range(8) for f in (2, 5, 9, 15, 30) for c in (False, True)
                 for e in (None, era("pre_1980"), era("2010_2019", "inferred"), era("2020_plus", "range"))]
        first = [fg.classify(a, f, h, fh, c, e) for a, f, h, fh, c, e in cases]
        shuffled = list(range(len(cases)))
        random.Random(7).shuffle(shuffled)
        again = {i: fg.classify(*cases[i][:5], cases[i][5]) for i in shuffled}
        self.assertEqual(first, [again[i] for i in range(len(cases))])

    def test_unknown_is_valid_without_any_era(self):
        self.assertEqual(cls(core=True), (fg.GEN_UNKNOWN, fg.BASIS_NONE))              # core: morphology can't decide
        self.assertEqual(cls(floors=30, height=100.0), (fg.GEN_UNKNOWN, fg.BASIS_NONE))
        self.assertEqual(cls(height=0.0), (fg.GEN_UNKNOWN, fg.BASIS_NONE))
        for a in (fg.ARCH_OFFICE, fg.ARCH_PODIUM, fg.ARCH_CIVIC, fg.ARCH_SCHOOL):
            self.assertEqual(cls(arch=a), (fg.GEN_UNKNOWN, fg.BASIS_NOT_APPLICABLE))
        self.assertEqual(cls(landmark=True), (fg.GEN_UNKNOWN, fg.BASIS_NOT_APPLICABLE))

    def test_unknown_and_ambiguous_era_fall_back_to_morphology(self):
        amb = es.EraRecord(None, 1990, 2005, "unknown", es.SRC_USE_PERMIT, "unknown", "parcel_overlap", ("P1", "P2"), True)
        for e in (None, es.UNKNOWN, amb):
            self.assertEqual(cls(arch=fg.ARCH_WALKUP, floors=5, e=e), (fg.GEN_LEGACY, fg.BASIS_MORPHOLOGY))
            self.assertEqual(cls(e=e), (fg.GEN_HUAXIA, fg.BASIS_MORPHOLOGY))

    def test_morphology_prior(self):
        self.assertEqual(cls(arch=fg.ARCH_LOW, floors=2)[0], fg.GEN_LEGACY)
        self.assertEqual(cls(arch=fg.ARCH_WALKUP, floors=5)[0], fg.GEN_LEGACY)
        self.assertEqual(cls(arch=fg.ARCH_HUAXIA)[0], fg.GEN_HUAXIA)
        self.assertEqual(cls(arch=fg.ARCH_RESTOWER, floors=20, height=65.0)[0], fg.GEN_HUAXIA)

    def test_era_bucket_mapping(self):
        want = {"pre_1980": fg.GEN_LEGACY, "1980_1999": fg.GEN_HUAXIA, "2000_2009": fg.GEN_MODERN,
                "2010_2019": fg.GEN_MODERN, "2020_plus": fg.GEN_MODERN}
        for bucket, code in want.items():
            self.assertEqual(cls(e=era(bucket)), (code, fg.BASIS_OBSERVED), bucket)
            self.assertEqual(cls(e=era(bucket, "range")), (code, fg.BASIS_OBSERVED), bucket)
            self.assertEqual(cls(e=era(bucket, "inferred")), (code, fg.BASIS_INFERRED), bucket)

    def test_premium_needs_new_era_and_tall_core_tower(self):
        tower = dict(arch=fg.ARCH_RESTOWER, floors=22, height=75.0, fh=3.4, core=True)
        self.assertEqual(fg.classify(*tower.values(), era("2010_2019")), (fg.GEN_PREMIUM, fg.BASIS_OBSERVED))
        self.assertEqual(fg.classify(*tower.values(), era("2020_plus", "inferred")), (fg.GEN_PREMIUM, fg.BASIS_INFERRED))
        self.assertEqual(fg.classify(*tower.values(), era("2000_2009"))[0], fg.GEN_MODERN)
        self.assertEqual(fg.classify(*tower.values(), None)[0], fg.GEN_UNKNOWN)       # morphology alone never premium
        self.assertEqual(cls(arch=fg.ARCH_HUAXIA, core=True, e=era("2020_plus"))[0], fg.GEN_MODERN)
        self.assertEqual(cls(arch=fg.ARCH_RESTOWER, floors=22, height=75.0, fh=3.0, core=True, e=era("2020_plus"))[0],
                         fg.GEN_MODERN)

    def test_observed_era_beats_inferred_beats_morphology(self):
        # morphology says huaxia; an observed pre-1980 era wins, an inferred one is used only when no observed exists
        self.assertEqual(cls(e=era("pre_1980"))[0], fg.GEN_LEGACY)
        self.assertEqual(cls(e=era("2000_2009", "inferred"))[0], fg.GEN_MODERN)
        self.assertEqual(cls(e=None)[0], fg.GEN_HUAXIA)
        # era_schema.aggregate_group already ranks observed over inferred; the classifier must keep that ranking
        group = es.aggregate_group([("a", 100.0, era("2000_2009", "inferred")), ("b", 50.0, era("pre_1980"))])
        self.assertEqual(cls(e=group), (fg.GEN_LEGACY, fg.BASIS_OBSERVED))

    def test_era_does_not_override_inapplicable_family(self):
        self.assertEqual(cls(arch=fg.ARCH_OFFICE, e=era("2010_2019")), (fg.GEN_UNKNOWN, fg.BASIS_NOT_APPLICABLE))

    def test_no_taipei_dependency(self):
        tree = ast.parse((REPO / "tools/lookdev/facade_generation.py").read_text(encoding="utf-8"))
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertTrue(all("taipei" not in (m or "").lower() and "adapters" not in (m or "") for m in mods), mods)
        code = ("import sys; sys.path[:0] = [r'%s', r'%s']; import facade_generation; "
                "bad = [m for m in sys.modules if 'taipei' in m or m == 'adapters' or m.startswith('adapters.')]; "
                "sys.exit(1 if bad else 0)" % (REPO / "tools/lookdev", REPO / "tools/building_era"))
        self.assertEqual(subprocess.run([sys.executable, "-I", "-c", code]).returncode, 0)


PROFILE_PATH = REPO / "tools/lookdev/profiles/facade_taipei_xinyi_v0.json"


def toy_profile(**over):
    """Small synthetic acw.facade_profile/0 (no regional numbers) for rule tests."""
    flat = {"pre_1980": 1.0, "1980_1999": 1.0, "2000_plus": 1.0}
    data = {
        "schema": "acw.facade_profile/0", "name": "toy",
        "band_prior": {z: {k: {"pre_1980": 0.2, "1980_1999": 0.5, "2000_plus": 0.3}
                           for k in ("low", "walkup", "huaxia", "res_tower")} for z in ("default", "core")},
        "floor_height_likelihood": {"default": [dict(flat, max_fh=99.0)]},
        "evidence_recall": {"2000_plus": 0.8},
        "premium": {"share_of_2000_plus": {"default": {"res_tower": 0.5}, "core": {"res_tower": 0.5}},
                    "floor_height": [{"max_fh": 99.0, "x": 1.0}], "floors": [{"max_floors": 999, "x": 1.0}],
                    "bucket": {}, "max_p": 0.9},
    }
    data.update(over)
    return fg.FacadeProfile(data)


class TestProfileClassification(unittest.TestCase):
    def test_shipped_profile_loads_and_is_generic_data(self):
        p = fg.FacadeProfile.load(PROFILE_PATH)
        self.assertEqual(p.name, "taipei_xinyi_v0")
        for core in (False, True):
            for a in fg.RESIDENTIAL_ARCHETYPES:
                for fh in (2.8, 3.2, 3.5, 4.0):
                    post = p.posterior(a, fh, core, era_consulted=True)
                    self.assertAlmostEqual(sum(post.values()), 1.0)
                    self.assertTrue(all(v >= 0 for v in post.values()))

    def test_bad_profile_rejected(self):
        with self.assertRaises(ValueError):
            fg.FacadeProfile({"schema": "something/0"})
        with self.assertRaises(ValueError):
            toy_profile(evidence_recall={"2000_plus": 1.0})

    def test_key_required_and_deterministic(self):
        p = toy_profile()
        with self.assertRaises(ValueError):
            fg.classify(fg.ARCH_HUAXIA, 8, 26.0, 3.25, False, None, profile=p)
        keys = ["tp_building_height.%d" % i for i in range(400)]
        first = [fg.classify(fg.ARCH_RESTOWER, 18, 60.0, 3.3, False, None, profile=p, key=k) for k in keys]
        order = list(range(len(keys)))
        random.Random(11).shuffle(order)
        again = {i: fg.classify(fg.ARCH_RESTOWER, 18, 60.0, 3.3, False, None, profile=p, key=keys[i]) for i in order}
        self.assertEqual(first, [again[i] for i in range(len(keys))])
        self.assertEqual({b for _, b in first}, {fg.BASIS_PROFILE})

    def test_draw_follows_posterior_and_preserves_mixture(self):
        p = toy_profile()
        got = [fg.classify(fg.ARCH_HUAXIA, 8, 26.0, 3.25, False, None, profile=p, key="g%d" % i)[0] for i in range(6000)]
        share = {c: got.count(c) / len(got) for c in set(got)}
        self.assertAlmostEqual(share[fg.GEN_LEGACY], 0.2, delta=0.03)
        self.assertAlmostEqual(share[fg.GEN_HUAXIA], 0.5, delta=0.03)
        self.assertAlmostEqual(share[fg.GEN_MODERN], 0.3, delta=0.03)       # huaxia archetype: no premium share
        towers = [fg.classify(fg.ARCH_RESTOWER, 20, 66.0, 3.3, True, None, profile=p, key="t%d" % i)[0]
                  for i in range(6000)]
        self.assertAlmostEqual(towers.count(fg.GEN_PREMIUM) / 6000, 0.15, delta=0.03)   # 0.3 x 0.5
        self.assertAlmostEqual(towers.count(fg.GEN_MODERN) / 6000, 0.15, delta=0.03)

    def test_consulted_era_source_without_record_lowers_its_band(self):
        p = toy_profile()
        none = p.posterior(fg.ARCH_HUAXIA, 3.25, False, era_consulted=False)
        miss = p.posterior(fg.ARCH_HUAXIA, 3.25, False, era_consulted=True)
        self.assertAlmostEqual(none["2000_plus"], 0.3)
        self.assertAlmostEqual(miss["2000_plus"], 0.3 * 0.2 / (0.7 + 0.3 * 0.2))
        self.assertGreater(miss["1980_1999"], none["1980_1999"])

    def test_unknown_mass_stays_unknown(self):
        prior = {z: {k: {"unknown": 1.0} for k in ("low", "walkup", "huaxia", "res_tower")} for z in ("default", "core")}
        p = toy_profile(band_prior=prior)
        for i in range(50):
            self.assertEqual(fg.classify(fg.ARCH_LOW, 2, 7.0, 3.5, True, None, profile=p, key="k%d" % i),
                             (fg.GEN_UNKNOWN, fg.BASIS_NONE))

    def test_evidence_and_applicability_outrank_profile(self):
        p = toy_profile()
        for i in range(30):
            k = "k%d" % i
            self.assertEqual(fg.classify(fg.ARCH_HUAXIA, 8, 26.0, 3.25, False, era("pre_1980"), profile=p, key=k),
                             (fg.GEN_LEGACY, fg.BASIS_OBSERVED))
            self.assertEqual(fg.classify(fg.ARCH_OFFICE, 30, 120.0, 4.0, True, era("2010_2019"), profile=p, key=k),
                             (fg.GEN_UNKNOWN, fg.BASIS_NOT_APPLICABLE))
            self.assertEqual(fg.classify(fg.ARCH_HUAXIA, 8, 26.0, 3.25, False, None, landmark=True, profile=p, key=k),
                             (fg.GEN_UNKNOWN, fg.BASIS_NOT_APPLICABLE))
            code, basis = fg.classify(fg.ARCH_RESTOWER, 20, 66.0, 3.3, True, era("2010_2019"), profile=p, key=k)
            self.assertIn(code, (fg.GEN_MODERN, fg.GEN_PREMIUM))
            self.assertEqual(basis, fg.BASIS_OBSERVED)

    def test_walkup_family_persists_through_1980s(self):
        self.assertEqual(fg.family(fg.ARCH_WALKUP, "1980_1999"), fg.GEN_LEGACY)
        self.assertEqual(fg.family(fg.ARCH_LOW, "1980_1999"), fg.GEN_LEGACY)
        self.assertEqual(fg.family(fg.ARCH_HUAXIA, "1980_1999"), fg.GEN_HUAXIA)
        self.assertEqual(fg.family(fg.ARCH_RESTOWER, "2000_plus"), fg.GEN_MODERN)

    def test_shader_consumes_generation_only_through_xc_wall(self):
        self.assertIn("float weather, float flags, float gen, float3 wpos", HLSL)
        code = (REPO / "tools/lookdev/ue_custom_code.py").read_text(encoding="utf-8")
        self.assertIn("xl.xc_city(WP, N, UV0, UV1, vc, fgen, Night", code)
        self.assertIn("xl.xc_city(WP, N, UV0, UV1, xl.xc_unpack(UV2), 0.0, Night", code)   # Taipei 101: gen 0


class TestEncoding(unittest.TestCase):
    def test_round_trip_every_legal_base_and_code(self):
        bases = np.arange(fg.BASE_MAX + 1, dtype=np.int64)
        for code in range(fg.GEN_PREMIUM + 1):
            x = (bases + code * fg.PAYLOAD_UNIT).astype(np.float32)
            self.assertTrue(np.array_equal(x.astype(np.int64), bases + code * fg.PAYLOAD_UNIT))   # exact in float32
            self.assertTrue(x.max() < 2 ** 18)
        for base in (0, 1, 255, 256, 12345, fg.BASE_MAX):
            for code in range(fg.GEN_PREMIUM + 1):
                self.assertEqual(fg.decode_x(float(np.float32(fg.encode_x(base, code)))), (base, code))

    def test_boundaries_rejected(self):
        with self.assertRaises(ValueError):
            fg.encode_x(fg.BASE_MAX + 1, 0)            # R = 128 would collide with bit 15
        with self.assertRaises(ValueError):
            fg.encode_x(-1, 0)
        with self.assertRaises(ValueError):
            fg.encode_x(0, fg.GEN_PREMIUM + 1)         # codes 5..7 are reserved
        with self.assertRaises(ValueError):
            pack_rgba8(np.array([[128, 0, 0, 0]], np.uint8), payload=np.array([1]))
        with self.assertRaises(ValueError):
            pack_rgba8(np.array([[1, 0, 0, 0]], np.uint8), payload=np.array([8]))

    def test_interpolation_noise_does_not_corrupt_decode(self):
        # worst-case constants interpolated in float32 with perspective weights, then decoded as the shader does
        rng = np.random.default_rng(3)
        worst = 0.0
        for base in (0, 255, 256, 32767):
            for code in range(5):
                x = np.float32(fg.encode_x(base, code))
                w = rng.random((2000, 3)).astype(np.float32) + np.float32(0.01)
                invz = rng.uniform(0.01, 1.0, (2000, 3)).astype(np.float32)
                pw = w * invz
                got = (pw * x).sum(axis=1, dtype=np.float32) / pw.sum(axis=1, dtype=np.float32)
                worst = max(worst, float(np.abs(got - x).max()))
                for v in got:
                    self.assertEqual(fg.decode_x(float(v)), (base, code))
        self.assertLess(worst, 0.25)

    def test_pack_rgba8_without_payload_is_historical(self):
        rgba = np.array([[r, g, b, a] for r in (0, 17, 127, 250) for g in (0, 200) for b in (0, 255) for a in (0, 99, 255)],
                        np.uint8)
        hist = np.column_stack([rgba[:, 0].astype(np.uint32) * 256 + rgba[:, 1],
                                rgba[:, 2].astype(np.uint32) * 256 + rgba[:, 3]]).astype(np.float32)
        self.assertTrue(np.array_equal(pack_rgba8(rgba), hist))
        self.assertTrue(np.array_equal(pack_rgba8(rgba, payload=np.zeros(len(rgba), np.uint8)), hist))

    def test_existing_packed_bits_preserved(self):
        # every flag value baked today (bits 0-6 incl. frontage bits 4-6), every archetype/variant
        for code in range(5):
            rows = np.array([[arch * 16 + var, seed, weather, flags]
                             for arch in range(8) for var in (0, 15) for seed in (0, 255) for weather in (0, 255)
                             for flags in range(128)], np.uint8)
            packed = pack_rgba8(rows, payload=np.full(len(rows), code))
            x = packed[:, 0].astype(np.float64)
            base_code = np.array([fg.decode_x(v) for v in x[::97]])
            idx = np.arange(0, len(rows), 97)
            self.assertTrue(np.array_equal(base_code[:, 0], rows[idx, 0].astype(np.int64) * 256 + rows[idx, 1]))
            self.assertTrue((base_code[:, 1] == code).all())
            self.assertTrue(np.array_equal(packed[:, 1], pack_rgba8(rows)[:, 1]))   # B/A float untouched
            # hero tag (A >= 248) is unreachable from the payload: it lives only in the second float
            self.assertTrue(np.array_equal(packed[:, 1] % 256, rows[:, 3].astype(np.float32)))

    def test_shader_contract(self):
        m = re.search(r"float4 xc_unpack_tile\(float2 d, out float gen\)\s*\{(.*?)\n\}", HLSL, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("gen = floor((d.x + 0.5) / %.1f)" % fg.PAYLOAD_UNIT, body)
        self.assertIn("d.x - gen * %.1f + 0.5" % fg.PAYLOAD_UNIT, body)
        # the historical decoder is untouched (other materials keep using it)
        self.assertIn("float r = floor(d.x / 256.0 + 1e-4);\n    float g = d.x - r * 256.0;", HLSL)
        code = (REPO / "tools/lookdev/ue_custom_code.py").read_text(encoding="utf-8")
        self.assertEqual(code.count("xc_unpack_tile"), 1)    # only M_XinyiCity decodes the payload


class TestBuilderWiring(unittest.TestCase):
    def test_missing_era_cache_is_not_an_error(self):
        import build_look_tiles as blt
        self.assertIsNone(blt.load_era(None))
        self.assertIsNone(blt.load_era(REPO / "does/not/exist.json.gz"))

    def test_builder_archetypes_match(self):
        import build_look_tiles as blt
        self.assertEqual(blt.ARCH_NAMES[fg.ARCH_RESTOWER], "res_tower")


if __name__ == "__main__":
    unittest.main()
