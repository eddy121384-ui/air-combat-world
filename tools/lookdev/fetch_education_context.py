"""Fetch the OSM education / sports features that the ground-art fetch discards.

tools/lookdev/fetch_lookdev_inputs.py only asks Overpass for `way[amenity=school...]`. Real Xinyi
campuses are mapped as multipolygon RELATIONS (仁愛 / 信義 / 興雅 / 吳興 ... 19 of them), and their
classrooms are separate `building=school|university|...` ways, so the ground cache holds just 5 school
polygons and no school buildings. This tool snapshots the missing data into its own cache file:

  data/lookdev_cache/osm_education_context.json.gz   raw Overpass response (out body geom)
  data/lookdev_cache/osm_education_context.meta.json provenance, counts, sha256 (ODbL notice)

It is NOT read by any renderer-facing stage yet (osm_xinyi_context.json.gz and the accepted ground
texture are untouched). tools/lookdev/build_urban_identity.py consumes it to produce the campus
metadata contract for the future Taipei Urban Identity pass.

Run:  python tools/lookdev/fetch_education_context.py [--force]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE = REPO / "data/lookdev_cache"
OUT = CACHE / "osm_education_context.json.gz"
META = CACHE / "osm_education_context.meta.json"
# same bbox as the ground context (south, west, north, east)
OSM_BBOX = (25.0195, 121.55, 25.048, 121.579)
OVERPASS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
# overpass-api.de answers 406 to clients without a descriptive User-Agent
UA = "air-combat-world-lookdev/1.0 (offline cache build; github.com/eddy121384-ui/air-combat-world)"


def query() -> str:
    s, w, n, e = OSM_BBOX
    b = f"{s},{w},{n},{e}"
    return f"""
[out:json][timeout:180];
(
  way["amenity"~"^(school|university|college|kindergarten)$"]({b});
  relation["amenity"~"^(school|university|college|kindergarten)$"]({b});
  way["building"~"^(school|university|college|kindergarten)$"]({b});
  way["landuse"="education"]({b});
  relation["landuse"="education"]({b});
  way["leisure"~"^(track|stadium|sports_centre|pitch|playground|swimming_pool)$"]({b});
  way["sport"~"athletics|running"]({b});
);
out body geom;
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if OUT.exists() and not args.force:
        print("cache exists (use --force to refetch):", OUT)
        return
    body = urllib.parse.urlencode({"data": query()}).encode()
    last = None
    raw = None
    for url in OVERPASS:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=240) as r:
                raw = r.read()
            json.loads(raw)            # must be JSON, not an HTML error page
            break
        except Exception as exc:       # noqa: BLE001 - try the next mirror
            last = exc
            raw = None
            time.sleep(2)
    if raw is None:
        raise SystemExit(f"all overpass endpoints failed: {last}")
    doc = json.loads(raw)
    OUT.write_bytes(gzip.compress(json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 9, mtime=0))
    kinds = {}
    for e in doc["elements"]:
        t = e.get("tags", {})
        k = t.get("amenity") or t.get("building") or t.get("landuse") or t.get("leisure") or t.get("sport") or "-"
        kinds[f"{e['type']}:{k}"] = kinds.get(f"{e['type']}:{k}", 0) + 1
    META.write_text(json.dumps({
        "role": "LOOKDEV_EDUCATION_CONTEXT_ONLY (not consumed by any renderer-facing stage yet)",
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0 — © OpenStreetMap contributors",
        "bbox_swne": list(OSM_BBOX),
        "osm_base_timestamp": doc.get("osm3s", {}).get("timestamp_osm_base"),
        "element_count": len(doc["elements"]),
        "kinds": dict(sorted(kinds.items())),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "note": "Building geometry stays on the WFS contract; this only classifies campuses / school "
                "buildings / sports surfaces for the future school identity layer.",
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"elements": len(doc["elements"]), "kinds": kinds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
