"""Probe non-building data sources for the theater audit. Writes data/ntw/source_probe.json.

- Overpass (OSM): raw building way+relation counts per region (mark UNKNOWN when the public
  instances cannot answer; never invent a number)
- Overture transportation / base(water, infrastructure): feature counts by subtype/class in the theater bbox
- Overture buildings theme total vs. OSM source share is measured in coverage_survey.py instead.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
RELEASE = "2026-09-23.1"
BBOX = (120.85, 24.30, 122.05, 25.31)
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
ISO = {"taipei": "TW-TPE", "new_taipei": "TW-NWT", "keelung": "TW-KEE", "taoyuan": "TW-TAO",
       "hsinchu_city": "TW-HSZ", "hsinchu_county": "TW-HSQ", "yilan": "TW-ILA"}


def overpass_count(iso):
    q = (f'[out:json][timeout:180];area["ISO3166-2"="{iso}"]->.a;'
         '(way["building"](area.a);relation["building"](area.a););out count;')
    last = None
    for attempt in range(2):
        for m in MIRRORS:
            try:
                data = urllib.parse.urlencode({"data": q}).encode()
                req = urllib.request.Request(m, data=data, headers={"User-Agent": "air-combat-world/ntw-survey"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    j = json.loads(r.read())
                c = j["elements"][0]["tags"]
                return {"status": "OK", "mirror": m, "ways": int(c["ways"]), "relations": int(c["relations"]),
                        "total": int(c["total"]), "osm_base_timestamp": j.get("osm3s", {}).get("timestamp_osm_base")}
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(5)
    return {"status": "UNKNOWN", "error": last}


def main():
    out = {"overture_release": RELEASE, "overpass_raw_building_counts": {}, "overture_other_themes": {}}
    for k, iso in ISO.items():
        out["overpass_raw_building_counts"][k] = overpass_count(iso)
        print(k, out["overpass_raw_building_counts"][k])
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    w = f"bbox.xmin>={BBOX[0]} AND bbox.xmax<={BBOX[2]} AND bbox.ymin>={BBOX[1]} AND bbox.ymax<={BBOX[3]}"
    base = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme="
    queries = {
        "transportation_segment": f"select subtype, class, count(*) from read_parquet('{base}transportation/type=segment/*', hive_partitioning=1) where {w} group by 1,2 order by 3 desc",
        "base_water": f"select subtype, class, count(*) from read_parquet('{base}base/type=water/*', hive_partitioning=1) where {w} group by 1,2 order by 3 desc",
        "base_infrastructure": f"select subtype, class, count(*) from read_parquet('{base}base/type=infrastructure/*', hive_partitioning=1) where {w} and class in ('airport','aerodrome','runway','helipad','heliport','taxiway','apron','airport_terminal') group by 1,2 order by 3 desc",
    }
    for name, q in queries.items():
        t = time.time()
        try:
            rows = con.execute(q).fetchall()
            out["overture_other_themes"][name] = {"status": "OK", "seconds": round(time.time() - t, 1),
                                                  "rows": [[r[0], r[1], int(r[2])] for r in rows[:40]],
                                                  "total": int(sum(r[2] for r in rows))}
        except Exception as e:  # noqa: BLE001
            out["overture_other_themes"][name] = {"status": "UNKNOWN", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        print(name, out["overture_other_themes"][name].get("total"), out["overture_other_themes"][name].get("status"))
    p = REPO / "data/ntw/source_probe.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(p)


if __name__ == "__main__":
    main()
