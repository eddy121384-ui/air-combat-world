"""Generic permit-with-parcel-list adapter (jurisdiction-neutral). Optional: needs permits AND parcel geometry.

A region that has one without the other, or neither, simply does not instantiate this adapter.

permits: [{"permit_no": str, "year": int, "height_m": float|None, "parcels": [parcel_key, ...]}]
parcels: [{"key": parcel_key, "geometry": GeoJSON-like polygon in the SAME projected CRS as the footprints}]
Parcel keys are opaque strings; how a region builds them is its adapter's business.

A footprint is a candidate for a permit when >= min_overlap of its area lies in the union of that permit's
parcels and it is not taller than the permit allows (height_slack). Permit-number joins and bare spatial
containment are not used. Competing permits are folded later by era_schema.resolve_candidates.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Mapping, Sequence

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

import era_schema as es

MIN_OVERLAP = 0.6
HEIGHT_SLACK_M = 3.0
HEIGHT_SLACK_REL = 0.25


class ParcelPermitAdapter:
    def __init__(self, name: str, permits: Sequence[dict], parcels: Sequence[dict],
                 source: str = es.SRC_USE_PERMIT, join: str = "parcel_overlap", min_overlap: float = MIN_OVERLAP,
                 height_slack_m: float = HEIGHT_SLACK_M, height_slack_rel: float = HEIGHT_SLACK_REL):
        self.name, self.source, self.join = name, source, join
        self.permits, self.parcels = permits, parcels
        self.min_overlap, self.slack_m, self.slack_rel = min_overlap, height_slack_m, height_slack_rel

    def params(self) -> dict:
        return {"method": self.join, "min_overlap": self.min_overlap, "height_slack_m": self.slack_m,
                "height_slack_rel": self.slack_rel}

    def observe(self, footprints: Mapping[str, dict]) -> tuple[dict, dict]:
        parcel_geom = defaultdict(list)
        for p in self.parcels:
            g = shape(p["geometry"])
            parcel_geom[p["key"]].append(g if g.is_valid else g.buffer(0))
        ids = sorted(footprints)
        geoms = [footprints[i]["geom"] for i in ids]
        tree = STRtree(geoms)
        cands, st = defaultdict(list), Counter()
        for pm in sorted(self.permits, key=lambda p: p["permit_no"]):
            gs = [g for k in pm["parcels"] for g in parcel_geom.get(k, ())]
            if not gs:
                st["permits_without_parcel_in_extent"] += 1
                continue
            union = unary_union(gs)
            pu = prep(union)
            hit = False
            for idx in tree.query(union):
                fid, g = ids[int(idx)], geoms[int(idx)]
                if g.area <= 0 or not pu.intersects(g):
                    continue
                if g.intersection(union).area / g.area < self.min_overlap:
                    continue
                h, ph = footprints[fid].get("height_m"), pm.get("height_m")
                if h and ph and h > ph + max(self.slack_m, self.slack_rel * ph):
                    st["candidates_rejected_height_conflict"] += 1
                    continue
                cands[fid].append((pm["permit_no"], pm["year"]))
                hit = True
            st["permits_matched_to_footprint" if hit else "permits_in_extent_no_footprint"] += 1
        st["permits_total"] = len(self.permits)
        return dict(cands), dict(st)
