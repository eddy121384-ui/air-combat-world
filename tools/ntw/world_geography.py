"""Fetch the real geography used for world-bounds planning (pinned Overture release).

Writes (ignored cache)  data/generated/ntw/world/land.parquet   full-resolution land polygons, TW + foreign
Writes (committed)      data/ntw/world/features.json            curated airports / ports / peaks with Overture ids

Land: Overture divisions/division_area, subtype=region, class=land, for TW, CN, JP regions whose bbox meets the
search window. Features: Overture base (airport infrastructure, military airfield land_use, peaks) and places
(ports). Each feature records the Overture id so the selection is auditable; nothing is typed from memory.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
RELEASE = "2026-09-23.1"
WIN = (118.5, 22.8, 124.2, 27.6)  # lon/lat search window (generous around any 300 km box on north Taiwan)
CACHE = REPO / "data/generated/ntw/world"
OUT = REPO / "data/ntw/world/features.json"
R = f"s3://overturemaps-us-west-2/release/{RELEASE}"

# (role, tier, overture theme/type, name[, lon/lat hint box]) - names as they appear in Overture, verified by query;
# a hint box is required where a name is ambiguous (e.g. 太平山, 觀音山)
FEATURES = [
    ("airport", "required", "base/infrastructure", "臺灣桃園國際機場"),
    ("airport", "required", "base/infrastructure", "臺北松山機場"),
    ("airport", "required", "base/land_use", "空軍新竹基地"),
    ("airport", "optional", "base/land_use", "臺中清泉崗機場"),
    ("airport", "optional", "base/land_use", "花蓮機場"),
    ("airport", "optional", "base/land_use", "佳山基地"),
    ("airport", "info_taiwan_outlying", "base/infrastructure", "馬祖南竿機場"),
    ("airport", "info_taiwan_outlying", "base/infrastructure", "馬祖北竿機場"),
    ("airport", "info_foreign", "base/infrastructure", "福州长乐国际机场"),
    ("airport", "info_foreign", "base/infrastructure", "与那国空港"),
    ("port", "required", "places/place", "基隆港"),
    ("port", "required", "places/place", "台北港"),
    ("port", "required", "places/place", "蘇澳漁港"),
    ("port", "optional", "places/place", "台中港"),
    ("port", "optional", "places/place", "花蓮港"),
    ("port", "optional", "places/place", "烏石漁港"),
    ("port", "optional", "places/place", "南寮舊港愛之船咖啡"),
    ("peak", "required", "base/land", "雪山主峰"),
    ("peak", "required", "base/land", "南湖大山"),
    ("peak", "required", "base/land", "中央尖山"),
    ("peak", "required", "base/land", "大霸尖山"),
    ("peak", "required", "base/land", "七星山"),
    ("peak", "optional", "base/land", "太平山", (121.40, 24.40, 121.70, 24.65)),  # Yilan Taipingshan, not the Chiayi namesake
    ("peak", "optional", "base/land", "奇萊主山"),
    ("peak", "info", "base/land", "觀音山", (121.30, 25.05, 121.50, 25.20)),  # Bali/Tamsui Guanyinshan (11 namesakes)
]


def con():
    c = duckdb.connect()
    c.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    return c


def main():
    c = con()
    CACHE.mkdir(parents=True, exist_ok=True)
    w = f"bbox.xmax>={WIN[0]} AND bbox.xmin<={WIN[2]} AND bbox.ymax>={WIN[1]} AND bbox.ymin<={WIN[3]}"
    c.execute(f"""COPY (SELECT id, country, region, names.primary AS name, ST_AsWKB(geometry) AS wkb
                 FROM read_parquet('{R}/theme=divisions/type=division_area/*', hive_partitioning=1)
                 WHERE subtype='region' AND class='land' AND country IN ('TW','CN','JP') AND {w} ORDER BY id)
                 TO '{(CACHE / 'land.parquet').as_posix()}' (FORMAT PARQUET)""")
    print(c.execute(f"select country, count(*) from read_parquet('{(CACHE / 'land.parquet').as_posix()}') group by 1").fetchall())

    feats = []
    for role, tier, src, name, *hint in FEATURES:
        theme, typ = src.split("/")
        hw = w if not hint else (f"bbox.xmin>={hint[0][0]} AND bbox.xmax<={hint[0][2]} AND "
                                 f"bbox.ymin>={hint[0][1]} AND bbox.ymax<={hint[0][3]}")
        extra = ", elevation" if typ == "land" else ", NULL"
        rows = c.execute(f"""SELECT id, names.primary, ST_X(ST_Centroid(geometry)), ST_Y(ST_Centroid(geometry)){extra}
                             FROM read_parquet('{R}/theme={theme}/type={typ}/*', hive_partitioning=1)
                             WHERE {hw} AND names.primary = ? ORDER BY id""", [name]).fetchall()
        if typ == "land":
            rows = [r for r in rows if r[4] is not None] or rows
            rows.sort(key=lambda r: -(r[4] or 0))
        if not rows:
            feats.append({"role": role, "tier": tier, "name": name, "status": "NOT_FOUND"})
            print("NOT FOUND", name)
            continue
        r = rows[0]
        feats.append({"role": role, "tier": tier, "name": name, "overture_id": r[0], "source": f"overture {RELEASE} {src}",
                      "lon": round(r[2], 5), "lat": round(r[3], 5), "elevation_m": r[4], "matches": len(rows)})
        print(role, tier, name, round(r[2], 4), round(r[3], 4), r[4], "matches", len(rows))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"overture_release": RELEASE, "features": feats,
                               "note": "Ports use the best Overture place record for the harbour (some are quay/marina records); "
                                       "南寮舊港 marks Hsinchu Nanliao harbour. Positions are representative points, not port limits."},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
