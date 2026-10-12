"""Fetch Overture building footprints (with geometry) for a lon/lat bbox from a pinned release.

Writes a parquet (ignored cache) and a manifest with the release pin, query, row count, sha256.
usage: fetch_overture_footprints.py --bbox minlon,minlat,maxlon,maxlat --out file.parquet [--release 2026-09-23.1]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

RELEASE = "2026-09-23.1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--release", default=RELEASE)
    a = ap.parse_args()
    x0, y0, x1, y1 = (float(v) for v in a.bbox.split(","))
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    src = f"s3://overturemaps-us-west-2/release/{a.release}/theme=buildings/type=building/*"
    # ORDER BY id => deterministic file content for a fixed release + bbox
    con.execute(f"""
      COPY (SELECT id, height, min_height, num_floors, class, subtype, is_underground, has_parts,
                   sources[1].dataset AS src, sources[1].record_id AS src_record, ST_AsWKB(geometry) AS wkb
            FROM read_parquet('{src}', hive_partitioning=1)
            WHERE bbox.xmin >= {x0} AND bbox.xmax <= {x1} AND bbox.ymin >= {y0} AND bbox.ymax <= {y1}
            ORDER BY id) TO '{a.out}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    n = con.execute(f"select count(*) from read_parquet('{a.out}')").fetchone()[0]
    man = {"overture_release": a.release, "bbox_lonlat": [x0, y0, x1, y1], "rows": n,
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "file_sha256": hashlib.sha256(Path(a.out).read_bytes()).hexdigest(),
           "license": "Overture buildings: ODbL (OSM-derived rows) / CC-BY-4.0 (zenodo.8174931 rows); see docs"}
    Path(a.out + ".manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    print(json.dumps(man))


if __name__ == "__main__":
    main()
