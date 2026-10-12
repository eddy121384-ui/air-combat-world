"""Fetch official MOI 2025 20 m DEM sheet packages from TGOS (catalog: data.gov.tw dataset 176927).

This is the OFFICIAL source of the Terrarium mirror used so far. Packages are per county ("分幅_<縣市>20MDEM(2025).zip").
Cache (ignored): data/generated/ntw/tgos/<name>.zip  + manifest with URL, bytes, sha256, Last-Modified.
usage: fetch_tgos_dtm.py 臺北市 新北市 新竹縣
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/generated/ntw/tgos"
CATALOG_URL = ("https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
               "A964612F-0D64-4C81-BFE5-6C1F2BA61DED/resource/A0B94F67-8ADF-48A1-8DF0-C60719AD2B28/download")


def get(url, path):
    p = urllib.parse.urlsplit(url)
    u = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path), p.query, p.fragment))
    for i in range(4):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "air-combat-world/ntw"})
            with urllib.request.urlopen(req, timeout=600) as r:
                data = r.read()
                return data, dict(r.headers)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"download failed {url}: {last}")


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    cat, _ = get(CATALOG_URL, None)
    (CACHE / "catalog.csv").write_bytes(cat)
    rows = list(csv.reader(cat.decode("utf-8-sig").splitlines()))
    want = sys.argv[1:] + ["schema_hdr"]
    man_path = CACHE / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    man["catalog_sha256"] = hashlib.sha256(cat).hexdigest()
    for r in rows[1:]:
        name, url = r[0], r[-1]
        if not any(w in name for w in want):
            continue
        f = CACHE / (name.replace("/", "_") + ".zip")
        if not f.exists():
            data, hdr = get(url, f)
            f.write_bytes(data)
            lm = hdr.get("Last-Modified")
        else:
            lm = man.get(name, {}).get("last_modified")
        man[name] = {"url": url, "bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                     "last_modified": lm, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "coordinate_system": r[3], "year": r[4]}
        print(name, man[name]["bytes"], man[name]["sha256"][:16])
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
