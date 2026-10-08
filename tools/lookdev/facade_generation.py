"""Facade generation payload v0: classification + TEXCOORD_2 headroom encoding.

Pure Python, no geometry/GIS imports, no city-specific knowledge. The classifier consumes only
  * the look-tile archetype (ARCH_* of build_look_tiles.py), floors, height and visual floor height,
  * the core-district flag,
  * an OPTIONAL generic building-era record (tools/building_era/era_schema.EraRecord, or any object with
    era_bucket / era_confidence / era_source / era_ambiguous).
  * an OPTIONAL visual profile (FacadeProfile, loaded from an acw.facade_profile/0 JSON config): regional
    era-band priors per archetype and zone, a floor-height likelihood, the recall of the era evidence and the
    premium share. All regional numbers live in that config, never in this module.
It never reads permit data, cadastral parcels or any Taipei adapter: with era=None it still classifies from
morphology, and a building the evidence cannot place stays UNKNOWN.

Profile inference is a deterministic draw (hash of the building key) from the profile posterior, so a district
gets a believable mixture of visual generations without inventing a construction year: nothing but the class
code leaves this module.

Classes (stored value)         meaning for the future facade grammar
  0 UNKNOWN   no usable signal, or the facade family does not apply -> shader keeps its archetype prior
  1 LEGACY    old walk-up / mixed-use stock (pre-1980 character)
  2 HUAXIA    1980-1999 tile mid-rise / 1990s tile tower
  3 MODERN    2000+ residential
  4 PREMIUM   2010+ luxury-class residential (era-confirmed 2010+ AND a tall core-district tower)

Storage: bits 15-17 of TEXCOORD_2.x, i.e. `x = code * 32768 + (R*256 + G)`. R = archetype*16+variant is <= 127
for every look mesh, so the old value never reaches bit 15 and the payload is pure headroom. Zero extra bytes
per vertex. Decode in the shader with xc_unpack_tile() (xinyi_city.hlsl); every other consumer keeps
xc_unpack() and never sees a non-zero payload.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# --- archetypes: must equal build_look_tiles.ARCH_* (asserted there) -------------------------------------
ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM, ARCH_CIVIC, ARCH_SCHOOL = range(8)
RESIDENTIAL_ARCHETYPES = (ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER)

GEN_UNKNOWN, GEN_LEGACY, GEN_HUAXIA, GEN_MODERN, GEN_PREMIUM = range(5)
GEN_NAMES = ("unknown", "legacy", "huaxia", "modern", "premium")

# why a code was chosen (offline provenance only; never stored per vertex)
BASIS_OBSERVED, BASIS_INFERRED, BASIS_PROFILE, BASIS_MORPHOLOGY, BASIS_NONE, BASIS_NOT_APPLICABLE = (
    "observed_era", "inferred_era", "profile", "morphology", "none", "not_applicable")

PAYLOAD_UNIT = 32768           # bit 15
PAYLOAD_MAX = 7                # 3 bits; values above GEN_PREMIUM are reserved
BASE_MAX = 127 * 256 + 255     # largest legal R*256+G (R <= 127)

# morphology thresholds (v0, provisional; tuned only by a documented global change)
MAX_MORPH_FLOORS = 24          # taller than a residential tower: not a residential family
PREMIUM_MIN_FLOORS = 18
PREMIUM_MIN_FLOOR_H = 3.3

# era band of a generic era bucket (the visual system needs a band, never a year)
BANDS = ("pre_1980", "1980_1999", "2000_plus")
_BUCKET_BAND = {"pre_1980": "pre_1980", "1980_1999": "1980_1999", "2000_2009": "2000_plus",
                "2010_2019": "2000_plus", "2020_plus": "2000_plus"}
_NEW_BUCKETS = ("2010_2019", "2020_plus")
_OBSERVED_SOURCES = ("open_use_permit", "open_construction_permit")
ARCH_KEYS = {ARCH_LOW: "low", ARCH_WALKUP: "walkup", ARCH_HUAXIA: "huaxia", ARCH_RESTOWER: "res_tower"}


def family(arch: int, band: str) -> int:
    """Visual family of an era band for a residential archetype. A 1980s-90s 4-5 F walk-up or low house is still
    walk-up stock (same grammar as the 1970s ones); the 1980-99 tile family starts at the elevator mid-rise."""
    if band == "pre_1980":
        return GEN_LEGACY
    if band == "1980_1999":
        return GEN_LEGACY if arch in (ARCH_LOW, ARCH_WALKUP) else GEN_HUAXIA
    return GEN_MODERN


def premium_candidate(arch: int, floors: int, floor_h: float, core: bool) -> bool:
    """No-profile fallback for a luxury-class tower: a tall residential tower inside the planned core district."""
    return bool(core and arch == ARCH_RESTOWER and floors >= PREMIUM_MIN_FLOORS and floor_h >= PREMIUM_MIN_FLOOR_H)


def unit_hash(key: str, salt: str) -> float:
    """Deterministic uniform [0, 1) per (building key, purpose); independent of build order and platform."""
    return int.from_bytes(hashlib.sha256(f"{salt}|{key}".encode()).digest()[:8], "big") / 2.0 ** 64


def _lookup_band(table, value: float, field: str):
    """First row of an ascending threshold table whose `field` bound is >= value (the last row is open)."""
    for row in table:
        if value <= row[field]:
            return row
    return table[-1]


class FacadeProfile:
    """Regional visual-generation weights (acw.facade_profile/0). Pure data: the classifier logic stays generic.

    band_prior[zone][archetype]   relative weights of the era bands (+ optional "unknown" mass) when no era
                                  evidence exists; zone = "core" (planned-core flag) or "default"
    floor_height_likelihood       per archetype key (or "default"), ascending `max_fh` rows: likelihood ratio per
                                  band for the floor-to-floor height
    evidence_recall[band]         share of that band the era source would have found; applied (x (1 - recall))
                                  only when an era source was consulted and returned nothing for the building
    premium                       share of 2000+ residential drawn as premium, x floor-height / floors / bucket
                                  factors, capped by max_p
    max_floors                    taller residential groups stay unknown"""

    SCHEMA = "acw.facade_profile/0"

    def __init__(self, data: dict):
        if data.get("schema") != self.SCHEMA:
            raise ValueError(f"not an {self.SCHEMA} profile: {data.get('schema')!r}")
        self.name = data["name"]
        self.band_prior = data["band_prior"]
        self.fh_lr = data["floor_height_likelihood"]
        self.recall = data.get("evidence_recall", {})
        self.premium = data["premium"]
        self.max_floors = int(data.get("max_floors", MAX_MORPH_FLOORS))
        for zone in ("default", "core"):
            for arch, key in ARCH_KEYS.items():
                w = self.band_prior[zone][key]
                if any(k not in BANDS + ("unknown",) for k in w) or any(v < 0 for v in w.values()) or sum(w.values()) <= 0:
                    raise ValueError(f"bad band prior {zone}/{key}: {w}")
        for b, r in self.recall.items():
            if b not in BANDS or not 0.0 <= r < 1.0:
                raise ValueError(f"bad evidence recall {b}: {r}")
        self.sha256 = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    @classmethod
    def load(cls, path: Path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def posterior(self, arch: int, floor_h: float, core: bool, era_consulted: bool) -> dict:
        """Normalised weights over BANDS + "unknown" for a residential group without usable era evidence."""
        prior = self.band_prior["core" if core else "default"][ARCH_KEYS[arch]]
        key = ARCH_KEYS[arch]
        lr = _lookup_band(self.fh_lr.get(key, self.fh_lr["default"]), floor_h, "max_fh")
        w = {b: prior.get(b, 0.0) * lr.get(b, 1.0) * ((1.0 - self.recall.get(b, 0.0)) if era_consulted else 1.0)
             for b in BANDS}
        w["unknown"] = prior.get("unknown", 0.0)
        s = sum(w.values())
        return {k: v / s for k, v in w.items()}

    def premium_p(self, arch: int, floors: int, floor_h: float, core: bool, bucket: str | None) -> float:
        p = self.premium["share_of_2000_plus"]["core" if core else "default"].get(ARCH_KEYS[arch], 0.0)
        p *= _lookup_band(self.premium["floor_height"], floor_h, "max_fh")["x"]
        p *= _lookup_band(self.premium["floors"], floors, "max_floors")["x"]
        p *= self.premium["bucket"].get(bucket or "inferred", 1.0)
        return min(p, self.premium["max_p"])


def _era_band(era):
    """-> (band, bucket, basis) from an era record, or None when it carries no usable bucket."""
    if era is None or getattr(era, "era_ambiguous", False):
        return None
    bucket = getattr(era, "era_bucket", "unknown")
    conf = getattr(era, "era_confidence", "unknown")
    if bucket not in _BUCKET_BAND or conf == "unknown":
        return None
    if conf in ("exact", "range") and getattr(era, "era_source", "") in _OBSERVED_SOURCES:
        return _BUCKET_BAND[bucket], bucket, BASIS_OBSERVED
    if conf == "inferred":
        return _BUCKET_BAND[bucket], bucket, BASIS_INFERRED
    return None


def classify(arch: int, floors: int, height_m: float, floor_h: float, core: bool, era=None,
             landmark: bool = False, profile: FacadeProfile | None = None, key: str | None = None):
    """-> (generation code, basis). Pure and deterministic.

    Precedence: not applicable (non-residential archetype / landmark) > observed era > inferred era >
    profile inference (when a profile is given) or morphology prior (without one) > unknown. Observed always
    beats inferred; an ambiguous era record is ignored.

    `era` None means no era source was consulted; an era record without a usable bucket means the source was
    consulted and found nothing, which the profile may treat as weak negative evidence (evidence_recall).
    `key` (stable building / group id) seeds the deterministic profile draws and is required with a profile."""
    if landmark or arch not in RESIDENTIAL_ARCHETYPES:
        return GEN_UNKNOWN, BASIS_NOT_APPLICABLE
    if profile is not None and key is None:
        raise ValueError("profile inference needs a stable building key")
    got = _era_band(era)
    if got is not None:
        band, bucket, basis = got
        code = family(arch, band)
        if band == "2000_plus":
            if profile is None:
                premium = bucket in _NEW_BUCKETS and premium_candidate(arch, floors, floor_h, core)
            else:
                premium = unit_hash(key, "premium") < profile.premium_p(
                    arch, floors, floor_h, core, bucket if basis == BASIS_OBSERVED else None)
            code = GEN_PREMIUM if premium else code
        return code, basis
    if height_m <= 0:
        return GEN_UNKNOWN, BASIS_NONE
    if profile is not None:
        if floors > profile.max_floors:
            return GEN_UNKNOWN, BASIS_NONE
        post = profile.posterior(arch, floor_h, core, era_consulted=era is not None)
        u, acc, band = unit_hash(key, "band"), 0.0, "unknown"
        for b in BANDS + ("unknown",):
            acc += post[b]
            if u < acc:
                band = b
                break
        if band == "unknown":
            return GEN_UNKNOWN, BASIS_NONE
        code = family(arch, band)
        if band == "2000_plus" and unit_hash(key, "premium") < profile.premium_p(arch, floors, floor_h, core, None):
            code = GEN_PREMIUM
        return code, BASIS_PROFILE
    # Without a profile, morphology can only restate the archetype prior, and not inside the planned core district
    # (developed after ~1990, era spread too wide) or for buildings taller than a residential tower.
    if core or floors > MAX_MORPH_FLOORS:
        return GEN_UNKNOWN, BASIS_NONE
    if arch in (ARCH_LOW, ARCH_WALKUP):
        return GEN_LEGACY, BASIS_MORPHOLOGY
    return GEN_HUAXIA, BASIS_MORPHOLOGY


# --- encoding -------------------------------------------------------------------------------------------

def encode_x(base: int, code: int) -> int:
    """TEXCOORD_2.x value (exact integer in float32) for R*256+G = base and a generation code."""
    if not 0 <= base <= BASE_MAX:
        raise ValueError(f"base {base} outside 0..{BASE_MAX} (R must be <= 127 to leave bit 15 free)")
    if not 0 <= code <= GEN_PREMIUM:
        raise ValueError(f"generation code {code} outside 0..{GEN_PREMIUM}")
    return code * PAYLOAD_UNIT + base


def decode_x(x: float):
    """-> (base, code); mirrors xc_unpack_tile (round-to-nearest, tolerant of float interpolation noise)."""
    import math
    code = math.floor((x + 0.5) / PAYLOAD_UNIT)
    return int(math.floor(x - code * PAYLOAD_UNIT + 0.5)), int(code)
