"""Fetch + compact Taipei's historical use-permit summaries (臺北市歷年使用執照摘要) for era metadata.

Source: Taipei Building Management and Engineering Office, data.gov.tw dataset 128203 (data.taipei resource
0f3f9675-...), XML ~68 MB, permits issued ROC 90-114 (2001-2025).
Licence: Government Open Data License, version 1.0 (Taiwan) -- attribution: 臺北市建築管理工程處.

The raw XML is NOT committed. This script keeps only what era metadata needs, for new-build permits:

  data/lookdev_cache/taipei_use_permits_new_build.json.gz   compact permit records, sorted by permit_no
  data/lookdev_cache/taipei_use_permits_new_build.meta.json provenance: URL, licence, retrieval time, raw sha256

Normal builds read only the compact cache (no network). Run:
  python tools/building_era/taipei_use_permits.py [--force] [--xml PATH]
`--xml` re-derives the cache from a previously downloaded file (the raw sha256 is recorded either way).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/lookdev_cache"
OUT = CACHE / "taipei_use_permits_new_build.json.gz"
META = CACHE / "taipei_use_permits_new_build.meta.json"
URL = ("https://data.taipei/api/dataset/c876ff02-af2e-4eb8-bd33-d444f5052733/resource/"
       "0f3f9675-8356-4f1a-9908-1ce8892012fa/download")
DATASET = "https://data.gov.tw/dataset/128203"
LICENCE = "Government Open Data License, version 1.0 (Taiwan); attribution required"
PUBLISHER = "臺北市政府都市發展局建築管理工程處 (Taipei Building Management and Engineering Office)"
NEW_BUILD = "新建"
UA = "air-combat-world-era/1.0 (offline cache build; github.com/eddy121384-ui/air-combat-world)"

_PARCEL = re.compile(r"^臺北市(?:[^區]+區)?(?P<seg>.+?)(?P<main>\d{4})-(?P<sub>\d{4})號?$")


def roc_date(text):
    """ROC 'yyymmdd' -> ISO date ('0910702' -> '2002-07-02'); None if absent / invalid."""
    s = (text or "").strip()
    if not re.fullmatch(r"\d{7}", s):
        return None
    y, m, d = int(s[:3]) + 1911, int(s[3:5]), int(s[5:7])
    try:
        return dt.date(y, m, d).isoformat()
    except ValueError:
        return None


def parcel_key(text):
    """'臺北市松山區寶清段四小段0547-0000號' -> '寶清段四小段|05470000' (matches WFS kcnt + aa49)."""
    m = _PARCEL.match((text or "").strip())
    return f"{m['seg']}|{m['main']}{m['sub']}" if m else None


def _height_m(text):
    m = re.match(r"\s*([\d.]+)\s*M", text or "")
    return float(m.group(1)) if m else None


def _int(text):
    try:
        return int((text or "").strip())
    except ValueError:
        return None


def permit_year(issue_iso, completion_iso):
    """Completion year when it is plausible next to the issue date, else the issue (use-permit) year."""
    iy = int(issue_iso[:4]) if issue_iso else None
    cy = int(completion_iso[:4]) if completion_iso else None
    if iy is None and cy is None:
        return None
    if cy is None or iy is None:
        return cy if iy is None else iy
    return cy if abs(cy - iy) <= 2 else iy


def parse_permits(stream):
    """Yield compact new-build records from the permit XML; deterministic order is applied by the caller."""
    for _, el in ET.iterparse(stream, events=("end",)):
        if el.tag != "Data":
            continue
        g = lambda tag: (el.findtext(tag) or "").strip()  # noqa: E731
        if g("建造類別") == NEW_BUILD:
            keys = sorted({k for k in (parcel_key(p.text) for p in el.iter("地段號")) if k})
            issue, done = roc_date(g("發照日期")), roc_date(g("竣工日期"))
            yield {
                "permit_no": g("執照號碼"),
                "issue_date": issue,
                "completion_date": done,
                "start_date": roc_date(g("開工日期")),
                "year": permit_year(issue, done),
                "floors_above": _int(el.findtext("建物資訊/地上層數")),
                "height_m": _height_m(g("建物高度")),
                "parcels": keys,
            }
        el.clear()


def build(xml_bytes: bytes, retrieved_at: str, source_url: str = URL):
    import io
    seen, permits = set(), []
    for p in parse_permits(io.BytesIO(xml_bytes)):
        if p["permit_no"] and p["permit_no"] not in seen and p["year"] and p["parcels"]:
            seen.add(p["permit_no"])
            permits.append(p)
    permits.sort(key=lambda p: p["permit_no"])
    payload = {"schema": "acw.use_permits_new_build/0", "permits": permits}
    blob = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
    meta = {
        "schema": "acw.use_permits_meta/0",
        "title": "臺北市歷年使用執照摘要 (new-build permits only, compacted)",
        "publisher": PUBLISHER,
        "licence": LICENCE,
        "dataset": DATASET,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "raw_xml_bytes": len(xml_bytes),
        "raw_xml_sha256": hashlib.sha256(xml_bytes).hexdigest(),
        "kept": "建造類別 == 新建 with a usable year and >=1 parcel key",
        "year_rule": "completion year if within 2 y of the issue year, else issue year",
        "permits_kept": len(permits),
        "year_range": [min(p["year"] for p in permits), max(p["year"] for p in permits)],
        "cache_sha256": hashlib.sha256(blob).hexdigest(),
    }
    return blob, meta


def load(path: Path = OUT):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["permits"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--xml", type=Path)
    args = ap.parse_args()
    if OUT.exists() and not args.force and not args.xml:
        print("cache exists:", OUT, "(use --force to refetch)")
        return
    if args.xml:
        raw, when = args.xml.read_bytes(), dt.datetime.fromtimestamp(args.xml.stat().st_mtime, dt.timezone.utc)
    else:
        with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": UA}), timeout=300) as r:
            raw, when = r.read(), dt.datetime.now(dt.timezone.utc)
    blob, meta = build(raw, when.strftime("%Y-%m-%dT%H:%M:%SZ"))
    OUT.write_bytes(blob)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
