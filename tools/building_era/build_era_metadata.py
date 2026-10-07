"""Build per-footprint building-era metadata for the Xinyi look-dev extent (permit -> parcel -> footprint).

Inputs
  data/lookdev_cache/sample_buildings_epsg3826.geojson.gz  accepted footprints (EPSG:3826, projected precision)
  data/lookdev_cache/taipei_use_permits_new_build.json.gz  open use permits (see taipei_use_permits.py)
  parcel polygons (EPSG:3826)  -- JOIN GEOMETRY ONLY, never committed, never emitted:
      data/generated/taipei/era/parcels_xinyi_epsg3826.json.gz  (gitignored; fetched on demand with --fetch-parcels
      from the Dashboard WFS layer building_cadastralmap, whose licence is UNVERIFIED -- same tier as the accepted
      footprint source; see the docs)
Output (committed, offline-rebuildable)
  data/lookdev_cache/xinyi_building_era_v0.json.gz    {footprint id: EraRecord dict}  (all buildings listed)
  data/lookdev_cache/xinyi_building_era_v0.meta.json  provenance, input hashes, join statistics

The City Dashboard `building_age` layer is research-only and is deliberately NOT referenced by this tool.

Join rule (strong -> weak; only the first is implemented, the rest are documented gaps):
  1. parcel key: a permit lists 段小段 + 8-digit 地號; a footprint is a candidate for a permit when
     >= MIN_OVERLAP of its area lies inside the union of that permit's parcels.
  2. permit id: no footprint carries one -> not applicable.
  3. spatial containment alone: not used (parcel overlap already is the spatial test).
A candidate whose height exceeds the permit height by > HEIGHT_SLACK is rejected (`height_conflict`).
Candidates then fold deterministically through era_schema.resolve_candidates.

Run:  python tools/building_era/build_era_metadata.py [--fetch-parcels] [--no-write]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import era_schema as es  # noqa: E402
import taipei_use_permits as permits_mod  # noqa: E402

CACHE = REPO / "data/lookdev_cache"
FOOTPRINTS = CACHE / "sample_buildings_epsg3826.geojson.gz"
FOOTPRINTS_MANIFEST = CACHE / "sample_buildings_epsg3826.manifest.json"
PARCEL_CACHE = REPO / "data/generated/taipei/era/parcels_xinyi_epsg3826.json.gz"
OUT = CACHE / "xinyi_building_era_v0.json.gz"
META = CACHE / "xinyi_building_era_v0.meta.json"

MIN_OVERLAP = 0.6        # share of the footprint inside the permit's parcels
HEIGHT_SLACK_M = 3.0     # footprint taller than permit height by more than this (and 25 %) -> conflict
HEIGHT_SLACK_REL = 0.25
JOIN_METHOD = "parcel_overlap"
WFS = "https://citydashboard.taipei/geo_server/taipei_vioc/ows"
PARCEL_LAYER = "taipei_vioc:building_cadastralmap"
PARCEL_MARGIN_M = 60.0
PAGE = 2000
UA = "air-combat-world-era/1.0 (join-geometry fetch; github.com/eddy121384-ui/air-combat-world)"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_footprints(path: Path = FOOTPRINTS) -> dict:
    """-> {id: {'geom': shapely geometry, 'height_m', 'floors'}} (EPSG:3826)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        fc = json.load(f)
    out = {}
    for ft in fc["features"]:
        g = shape(ft["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        p = ft.get("properties") or {}
        out[str(ft["id"])] = {"geom": g, "height_m": p.get("height_m"), "floors": p.get("floors")}
    return out


def fetch_parcels(bounds, path: Path = PARCEL_CACHE):
    """Page the cadastral WFS inside `bounds` (EPSG:3826). Join geometry only; stays out of git."""
    minx, miny, maxx, maxy = (bounds[0] - PARCEL_MARGIN_M, bounds[1] - PARCEL_MARGIN_M,
                              bounds[2] + PARCEL_MARGIN_M, bounds[3] + PARCEL_MARGIN_M)
    feats, start = [], 0
    while True:
        q = {"service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": PARCEL_LAYER,
             "outputFormat": "application/json", "srsName": "EPSG:3826", "sortBy": "thekey",
             "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:3826", "maxFeatures": PAGE, "startIndex": start}
        req = urllib.request.Request(WFS + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=180) as r:
            page = json.load(r)["features"]
        feats += [{"key": f["properties"]["kcnt"] + "|" + f["properties"]["aa49"], "geometry": f["geometry"]}
                  for f in page]
        if len(page) < PAGE:
            break
        start += PAGE
        time.sleep(0.5)
    feats.sort(key=lambda f: f["key"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps({"layer": PARCEL_LAYER, "bbox": [minx, miny, maxx, maxy],
                                               "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                               "features": feats}, separators=(",", ":")).encode(), mtime=0))
    return feats


def load_parcels(path: Path = PARCEL_CACHE):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["features"]


def join(footprints: dict, permits: list, parcels: list):
    """Pure, order-independent join. -> (records {id: EraRecord}, stats dict)."""
    parcel_geom = defaultdict(list)
    for p in parcels:
        g = shape(p["geometry"])
        parcel_geom[p["key"]].append(g if g.is_valid else g.buffer(0))
    ids = sorted(footprints)
    geoms = [footprints[i]["geom"] for i in ids]
    tree = STRtree(geoms)

    cands = defaultdict(list)         # footprint id -> [(permit_no, year)]
    st = Counter()
    for pm in sorted(permits, key=lambda p: p["permit_no"]):
        gs = [g for k in pm["parcels"] for g in parcel_geom.get(k, ())]
        if not gs:
            st["permits_without_parcel_in_extent"] += 1
            continue
        union = unary_union(gs)
        pu = prep(union)
        hit = False
        for idx in tree.query(union):
            fid = ids[int(idx)]
            g = geoms[int(idx)]
            if g.area <= 0 or not pu.intersects(g):
                continue
            if g.intersection(union).area / g.area < MIN_OVERLAP:
                continue
            h, ph = footprints[fid]["height_m"], pm.get("height_m")
            if h and ph and h > ph + max(HEIGHT_SLACK_M, HEIGHT_SLACK_REL * ph):
                st["candidates_rejected_height_conflict"] += 1
                continue
            cands[fid].append((pm["permit_no"], pm["year"]))
            hit = True
        st["permits_matched_to_footprint" if hit else "permits_in_extent_no_footprint"] += 1

    records = {fid: es.resolve_candidates(cands.get(fid, ()), JOIN_METHOD) for fid in ids}
    st["permits_total"] = len(permits)
    st["footprints_total"] = len(ids)
    st["footprints_exact"] = sum(r.era_confidence == es.CONF_EXACT for r in records.values())
    st["footprints_range"] = sum(r.era_confidence == es.CONF_RANGE for r in records.values())
    st["footprints_ambiguous"] = sum(r.era_ambiguous for r in records.values())
    st["footprints_unmatched"] = sum((not r.era_evidence) for r in records.values())
    return records, dict(st)


def write_cache(records: dict, meta: dict, out: Path = OUT, meta_out: Path = META):
    body = {fid: records[fid].to_dict() for fid in sorted(records)}
    payload = {"schema": es.SCHEMA, "ids": "WFS tp_building_height feature id", "records": body}
    blob = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(),
                         mtime=0)
    meta = dict(meta, cache_sha256=hashlib.sha256(blob).hexdigest())
    out.write_bytes(blob)
    meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def load_records(path: Path = OUT) -> dict:
    """Consumer entry point: {footprint id: EraRecord}, validated."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {k: es.EraRecord.from_dict(v) for k, v in json.load(f)["records"].items()}


def group_stats(records: dict, footprints: dict) -> dict:
    """Group-level era numbers using the *existing* look-dev grouping (build_look_tiles.classify), unmodified.

    Imported lazily: it needs the accepted WorldModel + cached OSM education context, all offline.
    """
    sys.path[:0] = [str(REPO / "tools/lookdev"), str(REPO / "tools/compiler")]
    import build_look_tiles as blt  # noqa: E402
    from worldmodel import build_worldmodel
    src = json.loads(blt.SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    wm = build_worldmodel(blt.SOURCE, blt.CITY, source_crs="EPSG:3826")
    recs, _arch, n_groups, _m, _c = blt.classify(wm, props)
    members = defaultdict(list)
    for fid, r in recs.items():
        members[r["group"]].append((fid, footprints[fid]["geom"].area, records[fid]))
    grp = {g: es.aggregate_group(m) for g, m in members.items()}
    return {
        "building_groups": n_groups,
        "groups_exact": sum(r.era_confidence == es.CONF_EXACT for r in grp.values()),
        "groups_range": sum(r.era_confidence == es.CONF_RANGE for r in grp.values()),
        "groups_era_known": sum(r.era_bucket != "unknown" for r in grp.values()),
        "groups_ambiguous": sum(r.era_ambiguous for r in grp.values()),
        "groups_unknown": sum(r.era_bucket == "unknown" for r in grp.values()),
        "group_bucket_counts": dict(sorted(Counter(r.era_bucket for r in grp.values()).items())),
        "group_source_counts": dict(sorted(Counter(r.era_source for r in grp.values()).items())),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-parcels", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--groups", action="store_true", help="also compute group-level stats (slow, offline)")
    args = ap.parse_args()
    fps = load_footprints()
    if args.fetch_parcels or not PARCEL_CACHE.exists():
        b = unary_union([f["geom"] for f in fps.values()]).bounds
        print("fetching parcels for", b)
        fetch_parcels(b)
    permits = permits_mod.load()
    parcels = load_parcels()
    records, stats = join(fps, permits, parcels)
    meta = {
        "schema": "acw.building_era_meta/0",
        "inputs": {
            "footprints_sha256": sha256_file(FOOTPRINTS),
            "footprints_manifest": json.loads(FOOTPRINTS_MANIFEST.read_text(encoding="utf-8")),
            "permits_cache_sha256": sha256_file(permits_mod.OUT),
            "permits_meta": json.loads(permits_mod.META.read_text(encoding="utf-8")),
            "parcel_geometry": {
                "layer": PARCEL_LAYER, "endpoint": WFS, "n_parcels": len(parcels),
                "licence": "UNVERIFIED (same Dashboard WFS family as the accepted footprint source)",
                "role": "join geometry only; not committed, not emitted",
            },
        },
        "join": {"method": JOIN_METHOD, "min_overlap": MIN_OVERLAP,
                 "height_slack_m": HEIGHT_SLACK_M, "height_slack_rel": HEIGHT_SLACK_REL},
        "sources_used": sorted({r.era_source for r in records.values()}),
        "research_only_not_used": sorted(es.RESEARCH_ONLY_SOURCES),
        "stats": stats,
        "bucket_counts": dict(sorted(Counter(r.era_bucket for r in records.values()).items())),
    }
    if args.groups:
        meta["group_stats"] = group_stats(records, fps)
        print(json.dumps(meta["group_stats"], indent=1))
    print(json.dumps(meta["stats"], indent=1), json.dumps(meta["bucket_counts"]))
    if not args.no_write:
        write_cache(records, meta)
        print("wrote", OUT)


if __name__ == "__main__":
    main()
