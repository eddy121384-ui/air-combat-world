"""Fetch Taipei City Dashboard WFS `taipei_vioc:tp_building_height` in EPSG:3826, paged + deduplicated.

Port of the Buju citywide downloader pattern (tools/data/download_taipei_building_height_citywide.mjs):
resultType=hits pre-count, count=5000 paging, dual-endpoint failover, dedupe by feature id.
Differences: projected output (EPSG:3826, per memory/Skyfront finding that 4326 rounds to ~10 m),
optional bbox (EPSG:3826 minx,miny,maxx,maxy), slim properties kept for height derivation.

Writes an ignored NDJSON cache plus a small manifest (hits, unique ids, sha256, fetch date).
usage: fetch_taipei_wfs.py --out data/generated/ntw/wfs_taipei_citywide.ndjson [--bbox3826 a,b,c,d]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINTS = [
    "https://citydashboard.taipei/geo_server/taipei_vioc/ows",
    "https://citydashboard.taipei/geo_server/ows",
]
TYPE = "taipei_vioc:tp_building_height"
KEEP = ("1_bud_high", "1_top_high", "1_ent_heig", "1_floor")
PAGE = 5000


def get(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "air-combat-world/ntw-survey", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {last}")


def params(extra, bbox):
    p = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": TYPE, "srsName": "EPSG:3826"}
    if bbox:
        p["bbox"] = bbox + ",EPSG:3826"
    p.update(extra)
    return urllib.parse.urlencode(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--bbox3826")
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    last_err = None
    for ep in ENDPOINTS:
        try:
            hits_xml = get(f"{ep}?{params({'resultType': 'hits'}, a.bbox3826)}").decode("utf-8", "replace")
            m = re.search(r'numberMatched="(\d+)"', hits_xml)
            hits = int(m.group(1)) if m else None
            seen, dup, start, pages = set(), 0, 0, 0
            h = hashlib.sha256()
            with out.open("w", encoding="utf-8") as fh:
                while True:
                    raw = get(f"{ep}?{params({'outputFormat': 'application/json', 'startIndex': start, 'count': PAGE}, a.bbox3826)}")
                    feats = json.loads(raw)["features"]
                    if not feats:
                        break
                    pages += 1
                    for f in feats:
                        fid = str(f.get("id"))
                        if fid in seen:
                            dup += 1
                            continue
                        seen.add(fid)
                        pr = f.get("properties") or {}
                        rec = {"id": fid, "geometry": f["geometry"], "p": {k: pr.get(k) for k in KEEP}}
                        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
                        fh.write(line + "\n")
                        h.update(line.encode("utf-8"))
                    start += PAGE
                    if len(feats) < PAGE:
                        break
            man = {
                "endpoint": ep, "typeName": TYPE, "srsName": "EPSG:3826", "bbox3826": a.bbox3826,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "hits": hits, "pages": pages, "unique_ids": len(seen), "duplicate_rows_dropped": dup,
                "ndjson_sha256": h.hexdigest(), "license_status": "UNVERIFIED (see docs)",
            }
            Path(str(out) + ".manifest.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
            print(json.dumps(man))
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            print("endpoint failed", ep, e)
    raise SystemExit(f"all endpoints failed: {last_err}")


if __name__ == "__main__":
    main()
