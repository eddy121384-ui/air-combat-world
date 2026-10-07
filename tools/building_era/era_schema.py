"""City-agnostic building-era record, era buckets, provenance rules and the inference hook.

Pure Python, no I/O. Nothing here knows about a district or a data vendor; city-specific parsing lives in the
ingestion modules. This module is the *only* place that defines what an era record may claim.

Record fields (acw.building_era/0)
----------------------------------
construction_year  int | None   observed completion year; only for era_confidence == "exact"
year_min, year_max int | None   inclusive bounds of the evidence ("exact": equal; "range": spread of candidates)
era_bucket         str          one of ERA_BUCKETS ("unknown" whenever the evidence does not pin one bucket)
era_source         str          one of ERA_SOURCES (who said so)
era_confidence     str          "exact" | "range" | "inferred" | "unknown"
era_join           str | None   how the evidence reached this building ("parcel_overlap", ...); None if not joined
era_evidence       list[str]    sorted source record ids (permit numbers), capped at EVIDENCE_CAP
era_ambiguous      bool         True when several records competed and no single bucket survived

Invariants (enforced by validate_record):
* observed sources (open_*) never carry "inferred"; "profile_inference" never carries "exact"/"range";
* "unknown" carries source "unknown" unless it is an ambiguity (source keeps the competing permit source);
* a record whose era_bucket is not "unknown" must have bounds that fall inside that bucket;
* research-only sources are rejected outright (licence gate).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Optional, Protocol, Sequence

SCHEMA = "acw.building_era/0"

# Broad, region-neutral bands sized for facade / roof / construction grammar, not for demographics.
# Round-number boundaries keep them reusable across jurisdictions; a region may map its own evidence into
# them but must not add regional buckets. Upper bounds are inclusive years.
#   pre_1980   1980_1999   2000_2009   2010_2019   2020_plus   (+ unknown)
ERA_BUCKETS = ("pre_1980", "1980_1999", "2000_2009", "2010_2019", "2020_plus", "unknown")
_BUCKET_UPPER = (("pre_1980", 1979), ("1980_1999", 1999), ("2000_2009", 2009), ("2010_2019", 2019))
_BUCKET_RANGE = {"pre_1980": (-10_000, 1979), "1980_1999": (1980, 1999), "2000_2009": (2000, 2009),
                 "2010_2019": (2010, 2019), "2020_plus": (2020, 10_000)}

SRC_USE_PERMIT = "open_use_permit"
SRC_CONSTRUCTION_PERMIT = "open_construction_permit"   # reserved; not ingested in v0
SRC_PROFILE_INFERENCE = "profile_inference"
SRC_UNKNOWN = "unknown"
ERA_SOURCES = (SRC_USE_PERMIT, SRC_CONSTRUCTION_PERMIT, SRC_PROFILE_INFERENCE, SRC_UNKNOWN)
OBSERVED_SOURCES = (SRC_USE_PERMIT, SRC_CONSTRUCTION_PERMIT)

# Licence gate. These identifiers must never appear as an era_source or feed production output.
RESEARCH_ONLY_SOURCES = frozenset({"citydashboard_building_age"})

CONF_EXACT, CONF_RANGE, CONF_INFERRED, CONF_UNKNOWN = "exact", "range", "inferred", "unknown"
ERA_CONFIDENCES = (CONF_EXACT, CONF_RANGE, CONF_INFERRED, CONF_UNKNOWN)
EVIDENCE_CAP = 4


def bucket_for_year(year: Optional[int]) -> str:
    """Stable bucketing; each upper bound is inclusive (1979 -> pre_1980, 1980 -> 1980_1999, 2020 -> 2020_plus)."""
    if year is None:
        return "unknown"
    for name, upper in _BUCKET_UPPER:
        if year <= upper:
            return name
    return "2020_plus"


@dataclass(frozen=True)
class EraRecord:
    construction_year: Optional[int] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    era_bucket: str = "unknown"
    era_source: str = SRC_UNKNOWN
    era_confidence: str = CONF_UNKNOWN
    era_join: Optional[str] = None
    era_evidence: tuple = ()
    era_ambiguous: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["era_evidence"] = list(self.era_evidence)
        return d

    @staticmethod
    def from_dict(d: dict) -> "EraRecord":
        r = EraRecord(construction_year=d.get("construction_year"), year_min=d.get("year_min"),
                      year_max=d.get("year_max"), era_bucket=d.get("era_bucket", "unknown"),
                      era_source=d.get("era_source", SRC_UNKNOWN),
                      era_confidence=d.get("era_confidence", CONF_UNKNOWN), era_join=d.get("era_join"),
                      era_evidence=tuple(d.get("era_evidence") or ()),
                      era_ambiguous=bool(d.get("era_ambiguous", False)))
        validate_record(r)
        return r


UNKNOWN = EraRecord()


def validate_record(r: EraRecord) -> None:
    """Raise ValueError if a record claims more than its provenance allows."""
    if r.era_source in RESEARCH_ONLY_SOURCES:
        raise ValueError(f"research-only source not allowed in era output: {r.era_source}")
    if r.era_source not in ERA_SOURCES:
        raise ValueError(f"unknown era_source {r.era_source!r}")
    if r.era_bucket not in ERA_BUCKETS:
        raise ValueError(f"unknown era_bucket {r.era_bucket!r}")
    if r.era_confidence not in ERA_CONFIDENCES:
        raise ValueError(f"unknown era_confidence {r.era_confidence!r}")
    if r.era_source in OBSERVED_SOURCES and r.era_confidence == CONF_INFERRED:
        raise ValueError("observed source cannot be 'inferred'")
    if r.era_source == SRC_PROFILE_INFERENCE and r.era_confidence in (CONF_EXACT, CONF_RANGE):
        raise ValueError("inferred era cannot be labelled exact/range")
    if r.era_confidence == CONF_EXACT and (r.construction_year is None or r.year_min != r.year_max
                                           or r.year_min != r.construction_year):
        raise ValueError("exact record needs construction_year == year_min == year_max")
    if r.era_confidence != CONF_EXACT and r.construction_year is not None:
        raise ValueError("only exact records carry construction_year")
    if r.era_confidence == CONF_UNKNOWN:
        if r.era_bucket != "unknown":
            raise ValueError("unknown confidence requires era_bucket 'unknown'")
        if not r.era_ambiguous and r.era_source != SRC_UNKNOWN:
            raise ValueError("unknown confidence requires era_source 'unknown' unless ambiguous")
    elif r.era_bucket == "unknown":
        raise ValueError("known confidence requires a concrete era_bucket")
    if r.era_bucket != "unknown" and r.year_min is not None:
        lo, hi = _BUCKET_RANGE[r.era_bucket]
        if not (lo <= r.year_min <= r.year_max <= hi):
            raise ValueError("year bounds fall outside era_bucket")
    if len(r.era_evidence) > EVIDENCE_CAP:
        raise ValueError("era_evidence exceeds cap")


def _evidence(ids: Iterable[str]) -> tuple:
    return tuple(sorted(set(ids)))[:EVIDENCE_CAP]


def resolve_candidates(candidates: Sequence[tuple], join: str, source: str = SRC_USE_PERMIT) -> EraRecord:
    """Deterministically fold the observed records that compete for one building.

    candidates: (record_id, year) pairs, any order, duplicates by record_id ignored.
      * none                           -> UNKNOWN
      * one distinct year              -> exact
      * several years, one bucket      -> range (no construction_year; bounds kept)
      * several years, several buckets -> unknown + era_ambiguous (evidence kept for audit)
    A permit is never picked at random: the result depends only on the *set* of candidates.
    """
    by_id = {}
    for rid, year in sorted(candidates, key=lambda t: (str(t[0]), int(t[1]))):
        by_id.setdefault(str(rid), int(year))
    if not by_id:
        return UNKNOWN
    years = sorted(by_id.values())
    ev = _evidence(by_id)
    if years[0] == years[-1]:
        rec = EraRecord(years[0], years[0], years[0], bucket_for_year(years[0]), source, CONF_EXACT, join, ev, False)
    else:
        buckets = {bucket_for_year(y) for y in years}
        if len(buckets) == 1:
            rec = EraRecord(None, years[0], years[-1], buckets.pop(), source, CONF_RANGE, join, ev, False)
        else:
            rec = EraRecord(None, years[0], years[-1], "unknown", source, CONF_UNKNOWN, join, ev, True)
    validate_record(rec)
    return rec


def aggregate_group(members: Sequence[tuple]) -> EraRecord:
    """Fold per-footprint records into one building-group record.

    members: (member_id, area_m2, EraRecord). Only observed members (exact / range) vote.
    All voters in one bucket -> the largest exact voter (else largest voter; ties by member_id) represents
    the group; voters in several buckets -> unknown + era_ambiguous. No voters -> the best inferred member,
    else UNKNOWN. The order of `members` never matters.
    """
    voters = sorted(((m, a, r) for m, a, r in members if r.era_confidence in (CONF_EXACT, CONF_RANGE)),
                    key=lambda t: (-t[1], str(t[0])))
    if voters:
        buckets = {r.era_bucket for _, _, r in voters}
        if len(buckets) == 1:
            exact = [v for v in voters if v[2].era_confidence == CONF_EXACT]
            return (exact or voters)[0][2]
        ev = _evidence(e for _, _, r in voters for e in r.era_evidence)
        lo = min(r.year_min for _, _, r in voters)
        hi = max(r.year_max for _, _, r in voters)
        return EraRecord(None, lo, hi, "unknown", voters[0][2].era_source, CONF_UNKNOWN, voters[0][2].era_join,
                         ev, True)
    inferred = sorted(((m, a, r) for m, a, r in members if r.era_confidence == CONF_INFERRED),
                      key=lambda t: (-t[1], str(t[0])))
    return inferred[0][2] if inferred else UNKNOWN


class EraInferer(Protocol):
    """Hook for buildings with no observed record (CityProfile -> era distribution -> metadata).

    Implementations return None (no trustworthy evidence -> building stays UNKNOWN) or an EraRecord with
    era_source == "profile_inference" and era_confidence == "inferred". They may use only licensed /
    project-owned attributes (district, floors, height, use class, morphology), must be deterministic and
    must not read research-only data.
    """

    def infer(self, attrs: dict) -> Optional[EraRecord]: ...


class NullInferer:
    """v0 default: not enough licensed evidence to define priors, so nothing is invented."""

    def infer(self, attrs: dict) -> Optional[EraRecord]:
        return None


def apply_inference(observed: EraRecord, attrs: dict, inferer: Optional[EraInferer] = None) -> EraRecord:
    """Observed evidence always wins; the inferer is consulted only for UNKNOWN, non-ambiguous buildings."""
    if observed.era_confidence != CONF_UNKNOWN or observed.era_ambiguous:
        return observed
    got = (inferer or NullInferer()).infer(attrs)
    if got is None:
        return observed
    if got.era_source != SRC_PROFILE_INFERENCE or got.era_confidence != CONF_INFERRED:
        raise ValueError("inferer must emit profile_inference / inferred records")
    validate_record(got)
    return got
