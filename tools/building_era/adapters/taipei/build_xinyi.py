"""Taipei regional adapter + Xinyi look-dev build: OPTIONAL enrichment of the generic building-era pipeline.

Everything Taipei-specific lives here and in use_permits.py: the permit XML, the 段小段+地號 parcel keys, the
Dashboard cadastral WFS, the Xinyi footprint cache and the look-dev grouping. The generic pipeline
(tools/building_era/pipeline.py) and schema know none of it; other regions write their own adapter (or none).

Inputs
  data/lookdev_cache/sample_buildings_epsg3826.geojson.gz  accepted footprints (EPSG:3826, projected precision)
  data/lookdev_cache/taipei_use_permits_new_build.json.gz  open use permits (use_permits.py)
  parcel polygons (EPSG:3826) -- JOIN GEOMETRY ONLY, never committed, never emitted:
      data/generated/taipei/era/parcels_xinyi_epsg3826.json.gz  (gitignored; `--fetch-parcels` pulls it from the
      Dashboard WFS layer building_cadastralmap, whose licence is UNVERIFIED -- same tier as the accepted
      footprint source; see the docs). Without it this adapter is simply not instantiated.
Output (committed, offline-rebuildable)
  data/lookdev_cache/xinyi_building_era_v0.json.gz / .meta.json

The City Dashboard `building_age` layer is research-only and is deliberately NOT referenced by this tool.

Run:  python tools/building_era/adapters/taipei/build_xinyi.py [--fetch-parcels] [--groups] [--no-write]
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

ERA_ROOT = Path(__file__).resolve().parents[2]
REPO = ERA_ROOT.parents[1]
sys.path.insert(0, str(ERA_ROOT))
import era_schema as es  # noqa: E402
import pipeline  # noqa: E402
from adapters import parcel_permit  # noqa: E402
from adapters.taipei import use_permits as permits_mod  # noqa: E402

CACHE = REPO / "data/lookdev_cache"
FOOTPRINTS = CACHE / "sample_buildings_epsg3826.geojson.gz"
FOOTPRINTS_MANIFEST = CACHE / "sample_buildings_epsg3826.manifest.json"
PARCEL_CACHE = REPO / "data/generated/taipei/era/parcels_xinyi_epsg3826.json.gz"
OUT = CACHE / "xinyi_building_era_v0.json.gz"
META = CACHE / "xinyi_building_era_v0.meta.json"

WFS = "https://citydashboard.taipei/geo_server/taipei_vioc/ows"
PARCEL_LAYER = "taipei_vioc:building_cadastralmap"
PARCEL_MARGIN_M = 60.0
PAGE = 2000
UA = "air-combat-world-era/1.0 (join-geometry fetch; github.com/eddy121384-ui/air-combat-world)"
ADAPTER_NAME = "taipei_use_permit_parcel"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_footprints(path: Path = FOOTPRINTS) -> dict:
    """-> {id: {'geom', 'height_m', 'floors'}} (EPSG:3826)."""
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
    """Page the Taipei cadastral WFS inside `bounds` (EPSG:3826). Join geometry only; stays out of git."""
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


def make_adapter(permits=None, parcels=None):
    """The Taipei enrichment adapter, or None when its inputs are absent (the pipeline then runs without it)."""
    permits = permits if permits is not None else (permits_mod.load() if permits_mod.OUT.exists() else None)
    if parcels is None and PARCEL_CACHE.exists():
        parcels = load_parcels()
    if not permits or not parcels:
        return None
    return parcel_permit.ParcelPermitAdapter(ADAPTER_NAME, permits, parcels)


def group_stats(records: dict, footprints: dict) -> dict:
    """Group-level era numbers using the *existing* look-dev grouping (build_look_tiles.classify), unmodified."""
    sys.path[:0] = [str(REPO / "tools/lookdev"), str(REPO / "tools/compiler")]
    import build_look_tiles as blt  # noqa: E402
    from worldmodel import build_worldmodel
    src = json.loads(blt.SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    wm = build_worldmodel(blt.SOURCE, blt.CITY, source_crs="EPSG:3826")
    recs, _arch, n_groups, _m, _c = blt.classify(wm, props)
    members = defaultdict(list)
    for fid, r in recs.items():
        members[r["group"]].append(fid)
    areas = {fid: footprints[fid]["geom"].area for fid in footprints}
    grp = pipeline.group_records(records, members, areas)
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
    if args.fetch_parcels:
        b = unary_union([f["geom"] for f in fps.values()]).bounds
        print("fetching parcels for", b)
        fetch_parcels(b)
    adapter = make_adapter()
    records, stats = pipeline.build_records(fps, [adapter] if adapter else [])
    meta = {
        "schema": "acw.building_era_meta/0",
        "region_adapters": [ADAPTER_NAME] if adapter else [],
        "inputs": {
            "footprints_sha256": sha256_file(FOOTPRINTS),
            "footprints_manifest": json.loads(FOOTPRINTS_MANIFEST.read_text(encoding="utf-8")),
            "permits_cache_sha256": sha256_file(permits_mod.OUT),
            "permits_meta": json.loads(permits_mod.META.read_text(encoding="utf-8")),
            "parcel_geometry": {
                "layer": PARCEL_LAYER, "endpoint": WFS, "n_parcels": len(load_parcels()) if adapter else 0,
                "licence": "UNVERIFIED (same Dashboard WFS family as the accepted footprint source)",
                "role": "optional join geometry only; not committed, not emitted",
            },
        },
        "join": adapter.params() if adapter else None,
        "sources_used": sorted({r.era_source for r in records.values()}),
        "research_only_not_used": sorted(es.RESEARCH_ONLY_SOURCES),
        "stats": _flat_stats(stats),
        "bucket_counts": dict(sorted(Counter(r.era_bucket for r in records.values()).items())),
    }
    if args.groups:
        meta["group_stats"] = group_stats(records, fps)
        print(json.dumps(meta["group_stats"], indent=1))
    print(json.dumps(meta["stats"], indent=1), json.dumps(meta["bucket_counts"]))
    if not args.no_write:
        pipeline.write_cache(records, meta, OUT, META)
        print("wrote", OUT)


def _flat_stats(stats: dict) -> dict:
    """Keep the v0 flat stat names (adapter counters + footprint tallies) for report continuity."""
    ad = stats["adapters"].get(ADAPTER_NAME, {})
    return dict(ad, footprints_total=stats["footprints_total"], footprints_exact=stats["footprints_exact"],
                footprints_range=stats["footprints_range"], footprints_ambiguous=stats["footprints_ambiguous"],
                footprints_unmatched=stats["footprints_unknown"] - stats["footprints_ambiguous"])


def load_records(path: Path = OUT) -> dict:
    return pipeline.load_records(path)


if __name__ == "__main__":
    main()
