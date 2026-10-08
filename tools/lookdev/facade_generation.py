"""Facade generation payload v0: classification + TEXCOORD_2 headroom encoding.

Pure Python, no geometry/GIS imports, no city-specific knowledge. The classifier consumes only
  * the look-tile archetype (ARCH_* of build_look_tiles.py), floors, height and visual floor height,
  * the core-district flag,
  * an OPTIONAL generic building-era record (tools/building_era/era_schema.EraRecord, or any object with
    era_bucket / era_confidence / era_source / era_ambiguous).
It never reads permit data, cadastral parcels or any Taipei adapter: with era=None it still classifies from
morphology, and a building the evidence cannot place stays UNKNOWN.

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

from typing import Optional

# --- archetypes: must equal build_look_tiles.ARCH_* (asserted there) -------------------------------------
ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM, ARCH_CIVIC, ARCH_SCHOOL = range(8)
RESIDENTIAL_ARCHETYPES = (ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER)

GEN_UNKNOWN, GEN_LEGACY, GEN_HUAXIA, GEN_MODERN, GEN_PREMIUM = range(5)
GEN_NAMES = ("unknown", "legacy", "huaxia", "modern", "premium")

# why a code was chosen (offline provenance only; never stored per vertex)
BASIS_OBSERVED, BASIS_INFERRED, BASIS_MORPHOLOGY, BASIS_NONE, BASIS_NOT_APPLICABLE = (
    "observed_era", "inferred_era", "morphology", "none", "not_applicable")

PAYLOAD_UNIT = 32768           # bit 15
PAYLOAD_MAX = 7                # 3 bits; values above GEN_PREMIUM are reserved
BASE_MAX = 127 * 256 + 255     # largest legal R*256+G (R <= 127)

# morphology thresholds (v0, provisional; tuned only by a documented global change)
MAX_MORPH_FLOORS = 24          # taller than a residential tower: not a residential family
PREMIUM_MIN_FLOORS = 18
PREMIUM_MIN_FLOOR_H = 3.3

_BUCKET_GEN = {"pre_1980": GEN_LEGACY, "1980_1999": GEN_HUAXIA, "2000_2009": GEN_MODERN,
               "2010_2019": GEN_MODERN, "2020_plus": GEN_MODERN}
_NEW_BUCKETS = ("2010_2019", "2020_plus")
_OBSERVED_SOURCES = ("open_use_permit", "open_construction_permit")


def premium_candidate(arch: int, floors: int, floor_h: float, core: bool) -> bool:
    """Morphology of a luxury-class tower: a tall residential tower inside the planned core district."""
    return bool(core and arch == ARCH_RESTOWER and floors >= PREMIUM_MIN_FLOORS and floor_h >= PREMIUM_MIN_FLOOR_H)


def _era_code(era, premium: bool):
    """-> (code, basis) from an era record, or None when it carries no usable bucket."""
    if era is None or getattr(era, "era_ambiguous", False):
        return None
    bucket = getattr(era, "era_bucket", "unknown")
    conf = getattr(era, "era_confidence", "unknown")
    if bucket not in _BUCKET_GEN or conf == "unknown":
        return None
    code = _BUCKET_GEN[bucket]
    if bucket in _NEW_BUCKETS and premium:
        code = GEN_PREMIUM
    if conf in ("exact", "range") and getattr(era, "era_source", "") in _OBSERVED_SOURCES:
        return code, BASIS_OBSERVED
    if conf == "inferred":
        return code, BASIS_INFERRED
    return None


def classify(arch: int, floors: int, height_m: float, floor_h: float, core: bool, era=None,
             landmark: bool = False):
    """-> (generation code, basis). Pure and deterministic.

    Precedence: not applicable (non-residential archetype / landmark) > observed era > inferred era >
    morphology > unknown. Observed always beats inferred; an ambiguous era record is ignored."""
    if landmark or arch not in RESIDENTIAL_ARCHETYPES:
        return GEN_UNKNOWN, BASIS_NOT_APPLICABLE
    got = _era_code(era, premium_candidate(arch, floors, floor_h, core))
    if got is not None:
        return got
    # Morphology can only restate the archetype prior, and not inside the planned core district
    # (developed after ~1990, era spread too wide) or for buildings taller than a residential tower.
    if core or floors > MAX_MORPH_FLOORS or height_m <= 0:
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
