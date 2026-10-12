"""Extract a slim per-building attribute table from a pinned Overture release.

Streams Overture GeoParquet from S3 (public bucket) via DuckDB and writes ONLY
survey columns (centroid, height/floors presence, class, source dataset, vertex
count, approx footprint area) to a local parquet cache. No footprints geometry.
Partitioned by bbox.xmin so bands can run in parallel and never double count.

usage: extract_overture_buildings.py --release 2026-09-23.1 --xmin A --xmax B --out file.parquet
"""
from __future__ import annotations
import argparse, json, time
import duckdb

BBOX_Y = (24.30, 25.31)  # theater latitude span (see theater.py)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", required=True)
    ap.add_argument("--xmin", type=float, required=True)
    ap.add_argument("--xmax", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    root = f"s3://overturemaps-us-west-2/release/{a.release}/theme=buildings/type=building/*"
    t = time.time()
    con.execute(f"""
    COPY (
      SELECT id,
        (bbox.xmin+bbox.xmax)/2 AS cx, (bbox.ymin+bbox.ymax)/2 AS cy,
        height, min_height, num_floors, class, subtype, is_underground, has_parts,
        sources[1].dataset AS src, len(sources) AS nsrc,
        ST_NPoints(geometry) AS npts,
        ST_Area(geometry) * 111320.0*cos(radians((bbox.ymin+bbox.ymax)/2)) * 110574.0 AS area_m2
      FROM read_parquet('{root}', hive_partitioning=1)
      WHERE bbox.xmin >= {a.xmin} AND bbox.xmin < {a.xmax}
        AND bbox.ymin >= {BBOX_Y[0]} AND bbox.ymax <= {BBOX_Y[1]}
    ) TO '{a.out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"select count(*) from read_parquet('{a.out}')").fetchone()[0]
    print(json.dumps({"out": a.out, "rows": n, "seconds": round(time.time() - t, 1)}))


if __name__ == "__main__":
    main()
