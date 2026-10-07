"""Generic building-era pipeline: optional source adapters -> observed eras -> profile inference -> unknown.

    BuildingEra schema (era_schema)
        -> optional regional EraSourceAdapter(s)     (exact / partial / no data; none is required)
        -> high-confidence observed ages where available
        -> deterministic CityProfile / morphology inference (EraInferer; none ships priors by default)
        -> unknown when evidence is insufficient

Nothing here knows a jurisdiction, a parcel scheme or a data vendor. A region with no adapters, no parcel data
or no age data at all still yields a complete, valid result (every building `unknown`).

Footprint contract (all that adapters / inferers may rely on):
    {building_id: {"geom": shapely geometry in a projected CRS (metres), "height_m": float|None,
                   "floors": int|None, ...optional extras}}
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Optional, Protocol, Sequence

import era_schema as es


class EraSourceAdapter(Protocol):
    """One regional source of observed building years. Optional; independent; order = priority."""

    name: str
    source: str      # an era_schema observed source label (e.g. "open_use_permit")
    join: str        # how evidence reaches a building (e.g. "parcel_overlap")

    def observe(self, footprints: Mapping[str, dict]) -> tuple[dict, dict]:
        """-> ({building_id: [(evidence_id, year), ...]}, stats). May return nothing for most buildings."""
        ...


def build_records(footprints: Mapping[str, dict], adapters: Sequence[EraSourceAdapter] = (),
                  inferer: Optional[es.EraInferer] = None) -> tuple[dict, dict]:
    """-> ({id: EraRecord}, stats). Deterministic; independent of footprint / adapter-internal order.

    Per building, adapters are consulted in priority order: the first adapter that resolves a concrete era
    (exact / range) wins; an ambiguous result is kept only if no later adapter resolves one. Buildings still
    unknown (and not ambiguous) go to the inferer, whose output is always labelled profile_inference.
    """
    ids = sorted(footprints)
    stats: dict = {"footprints_total": len(ids), "adapters": {}}
    per_adapter = []
    for ad in adapters:
        cands, ast = ad.observe(footprints)
        stats["adapters"][ad.name] = ast
        per_adapter.append((ad, cands))
    records, from_adapter = {}, {}
    for fid in ids:
        best = es.UNKNOWN
        for ad, cands in per_adapter:
            rec = es.resolve_candidates(cands.get(fid, ()), ad.join, ad.source)
            if rec.era_confidence in (es.CONF_EXACT, es.CONF_RANGE):
                best = rec
                break
            if rec.era_ambiguous and not best.era_ambiguous:
                best = rec
        records[fid] = es.apply_inference(best, _attrs(fid, footprints[fid]), inferer)
    cnt = lambda pred: sum(1 for r in records.values() if pred(r))  # noqa: E731
    stats.update(footprints_exact=cnt(lambda r: r.era_confidence == es.CONF_EXACT),
                 footprints_range=cnt(lambda r: r.era_confidence == es.CONF_RANGE),
                 footprints_inferred=cnt(lambda r: r.era_confidence == es.CONF_INFERRED),
                 footprints_ambiguous=cnt(lambda r: r.era_ambiguous),
                 footprints_unknown=cnt(lambda r: r.era_bucket == "unknown"))
    return records, stats


def _attrs(fid: str, fp: Mapping) -> dict:
    d = {k: v for k, v in fp.items() if k != "geom"}
    d["id"] = fid
    g = fp.get("geom")
    if g is not None:
        d["area_m2"] = float(g.area)
    return d


# --------------------------------------------------------------------------
# Deterministic CityProfile / morphology inference
# --------------------------------------------------------------------------

class ProfileEraInferer:
    """Rule table supplied by a CityProfile: morphology -> era distribution, sampled deterministically.

    rules: [{"when": {"floors": [lo, hi], "height_m": [lo, hi], "area_m2": [lo, hi], "<extra attr>": value|[..]},
             "distribution": {bucket: weight, ...}}, ...]   first matching rule wins.
    A rule must test at least one attribute and use only real era buckets (never "unknown"). A building the
    rules do not cover returns None and stays unknown. The draw is a pure function of (salt, building id), so
    results never depend on order or run. Rules must come from licensed / project-owned evidence; this class
    ships none -- an empty table means "no trustworthy priors", never a guess.
    """

    def __init__(self, rules: Sequence[dict] = (), salt: str = "era-v0"):
        self.salt = salt
        self.rules = []
        for r in rules:
            when, dist = r.get("when") or {}, r.get("distribution") or {}
            if not when:
                raise ValueError("inference rule must test at least one attribute")
            bad = [b for b in dist if b not in es.ERA_BUCKETS or b == "unknown"]
            if bad or not dist or any(w < 0 for w in dist.values()) or sum(dist.values()) <= 0:
                raise ValueError(f"invalid era distribution {dist!r}")
            self.rules.append((dict(when), sorted(dist.items())))

    @staticmethod
    def _match(when: Mapping, attrs: Mapping) -> bool:
        for key, want in when.items():
            val = attrs.get(key)
            if val is None:
                return False
            if isinstance(want, (list, tuple)) and len(want) == 2 and all(isinstance(x, (int, float)) for x in want):
                if not (want[0] <= val <= want[1]):
                    return False
            elif isinstance(want, (list, tuple)):
                if val not in want:
                    return False
            elif val != want:
                return False
        return True

    def infer(self, attrs: dict) -> Optional[es.EraRecord]:
        for when, dist in self.rules:
            if self._match(when, attrs):
                total = float(sum(w for _, w in dist))
                u = int.from_bytes(hashlib.sha256(f"{self.salt}|{attrs['id']}".encode()).digest()[:8], "big") / 2 ** 64
                acc = 0.0
                for bucket, w in dist:
                    acc += w / total
                    if u < acc:
                        break
                return es.EraRecord(None, None, None, bucket, es.SRC_PROFILE_INFERENCE, es.CONF_INFERRED,
                                    "profile_rule", (), False)
        return None


# --------------------------------------------------------------------------
# Generic cache IO (region-neutral; the id space is whatever the caller's footprints use)
# --------------------------------------------------------------------------

def write_cache(records: Mapping[str, es.EraRecord], meta: dict, out: Path, meta_out: Path) -> dict:
    body = {fid: records[fid].to_dict() for fid in sorted(records)}
    payload = {"schema": es.SCHEMA, "ids": "footprint id as supplied by the region's footprint source",
               "records": body}
    blob = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(),
                         mtime=0)
    meta = dict(meta, cache_sha256=hashlib.sha256(blob).hexdigest())
    out.write_bytes(blob)
    meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def load_records(path: Path) -> dict:
    """Consumer entry point: {footprint id: EraRecord}, validated."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {k: es.EraRecord.from_dict(v) for k, v in json.load(f)["records"].items()}


def group_records(records: Mapping[str, es.EraRecord], groups: Mapping[str, Iterable[str]],
                  areas: Mapping[str, float]) -> dict:
    """{group id: member footprint ids} -> {group id: EraRecord} via era_schema.aggregate_group."""
    return {g: es.aggregate_group([(m, areas.get(m, 0.0), records.get(m, es.UNKNOWN)) for m in members])
            for g, members in groups.items()}
