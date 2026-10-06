"""Snapshot Taipei's painted pedestrian walkways (標線型人行道) for the Xinyi look-dev extent.

Source: 臺北市交通管制工程處 open dataset 「臺北市標線型人行道」 (data.gov.tw 145867, data.taipei resource
2d82d5f1-...), Shapefile, EPSG:3826 (TWD97 TM2) polygons, one record per painted walkway patch.
Licence: Open Government Data License, version 1.0 (Taiwan) — attribution: 臺北市政府交通局交通管制工程處.

  data/lookdev_cache/taipei_marked_walkways_xinyi.json.gz   polygons clipped to the look extent (+100 m), in
                                                            EPSG:3826 metres (projected precision kept; the
                                                            ground builder transforms them like the WFS
                                                            buildings: pyproj -> lon/lat -> ENU)
  data/lookdev_cache/taipei_marked_walkways_xinyi.meta.json provenance, zip sha256, counts, licence

Taipei Street Reality v0D uses the polygons only as *evidence of where a walkway is painted*: the green paint
itself is regenerated road-aligned by curb_zone.py and still yields to the v0C curb priorities.
No shapefile library is needed: the SHP (polygon, type 5) and DBF readers below use struct only.

Run:  python tools/lookdev/fetch_ped_walkways.py [--force] [--zip PATH]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
from worldmodel import enu_origin_from_city_yaml, lonlat_to_enu  # noqa: E402

CITY = REPO / "cities/taipei/city.yaml"
CACHE = REPO / "data/lookdev_cache"
OUT = CACHE / "taipei_marked_walkways_xinyi.json.gz"
META = CACHE / "taipei_marked_walkways_xinyi.meta.json"
URL = ("https://data.taipei/api/dataset/d647b3af-4bbd-4e8f-b420-8f6c1bc1b597/resource/"
       "2d82d5f1-8f97-45db-89df-162ba161dedb/download")
DATASET = "https://data.gov.tw/dataset/145867"
EXTENT_ENU = (-1500.0, 1000.0, -1000.0, 1500.0)          # build_ground.py E0, E1, N0, N1
MARGIN_M = 100.0
KEEP = ("keyid", "rddate", "sirean", "rdlbwt", "rdlblg", "liarea", "zlocation", "rdcode", "roadid")
UA = "air-combat-world-lookdev/1.0 (offline cache build; github.com/eddy121384-ui/air-combat-world)"


def read_dbf(raw):
    nrec, hlen, rlen = struct.unpack("<IHH", raw[4:12])
    fields, o = [], 32
    while raw[o] != 0x0D:
        f = raw[o:o + 32]
        fields.append((f[:11].split(b"\0")[0].decode("ascii"), f[16]))
        o += 32
    recs = []
    for i in range(nrec):
        r = raw[hlen + i * rlen: hlen + (i + 1) * rlen]
        p, d = 1, {}
        for name, ln in fields:
            d[name] = r[p:p + ln].decode("utf-8", "replace").strip()
            p += ln
        recs.append(d)
    return recs


def read_shp_polygons(raw):
    """-> list of rings-per-record (list of [(x, y), ...]); SHP polygon type 5 only."""
    stype, = struct.unpack("<i", raw[32:36])
    if stype != 5:
        raise SystemExit("expected polygon shapefile (type 5), got %d" % stype)
    out, o = [], 100
    while o < len(raw):
        _num, clen = struct.unpack(">ii", raw[o:o + 8])
        body = raw[o + 8: o + 8 + clen * 2]
        o += 8 + clen * 2
        t, = struct.unpack("<i", body[:4])
        if t == 0:
            out.append([])
            continue
        nparts, npts = struct.unpack("<ii", body[36:44])
        parts = list(struct.unpack("<%di" % nparts, body[44:44 + 4 * nparts]))
        xy = struct.unpack("<%dd" % (2 * npts), body[44 + 4 * nparts: 44 + 4 * nparts + 16 * npts])
        pts = [(xy[2 * k], xy[2 * k + 1]) for k in range(npts)]
        out.append([pts[a:b] for a, b in zip(parts, parts[1:] + [npts])])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--zip", type=Path, help="use an already downloaded zip instead of fetching")
    a = ap.parse_args()
    if OUT.is_file() and META.is_file() and not a.force:
        print("cached:", OUT)
        return
    if a.zip:
        blob = a.zip.read_bytes()
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            blob = r.read()
    zsha = hashlib.sha256(blob).hexdigest()
    z = zipfile.ZipFile(io.BytesIO(blob))
    by_ext = {n.rsplit(".", 1)[1].lower(): n for n in z.namelist() if "." in n}
    prj = z.read(by_ext["prj"]).decode("latin1")
    if "TWD_1997_TM_Taiwan" not in prj or "Central_Meridian\",121" not in prj:
        raise SystemExit("unexpected CRS: %s" % prj)
    recs = read_dbf(z.read(by_ext["dbf"]))
    shapes = read_shp_polygons(z.read(by_ext["shp"]))
    if len(recs) != len(shapes):
        raise SystemExit("dbf / shp record mismatch %d != %d" % (len(recs), len(shapes)))

    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    E0, E1, N0, N1 = EXTENT_ENU
    feats = []
    for d, rings in zip(recs, shapes):
        if not rings:
            continue
        xs = [x for r in rings for x, _ in r]
        ys = [y for r in rings for _, y in r]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        lon, lat = tr.transform(cx, cy)
        e, n = lonlat_to_enu(lon, lat, lon0, lat0)
        if not (E0 - MARGIN_M <= e <= E1 + MARGIN_M and N0 - MARGIN_M <= n <= N1 + MARGIN_M):
            continue
        feats.append({"props": {k: d.get(k, "") for k in KEEP},
                      "rings_epsg3826": [[[round(x, 3), round(y, 3)] for x, y in r] for r in rings]})
    feats.sort(key=lambda f: (int(f["props"]["keyid"] or 0), f["rings_epsg3826"][0][0]))
    doc = {"schema": "acw.marked_walkways/0", "crs": "EPSG:3826", "source_url": URL, "dataset": DATASET,
           "zip_sha256": zsha, "features": feats}
    raw = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress(raw, mtime=0))
    meta = {"schema": "acw.marked_walkways_meta/0",
            "title": "臺北市標線型人行道 (Taipei painted pedestrian walkways)",
            "publisher": "臺北市政府交通局交通管制工程處 (Taipei Traffic Engineering Office)",
            "licence": "Open Government Data License, version 1.0 (Taiwan); attribution required",
            "dataset": DATASET, "source_url": URL, "zip_files": sorted(z.namelist()),
            "zip_sha256": zsha, "zip_bytes": len(blob), "records_citywide": len(recs),
            "records_in_extent": len(feats), "extent_enu_m": list(EXTENT_ENU), "margin_m": MARGIN_M,
            "crs": "EPSG:3826 (TWD97 TM2), kept projected; transformed like the WFS buildings",
            "use": "evidence of where a walkway is painted (Taipei Street Reality v0D); geometry regenerated",
            "cache_sha256": hashlib.sha256(raw).hexdigest()}
    META.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("records_citywide", "records_in_extent", "zip_sha256")}))


if __name__ == "__main__":
    main()
