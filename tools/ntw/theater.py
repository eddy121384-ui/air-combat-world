"""Build the Northern Taiwan theater footprint from pinned Overture `divisions`.

Output: data/ntw/theater_regions.json  (compact, committed)
 - per-region land area (EPSG:3826 planar, km2), lon/lat bbox, TM2 bbox, part counts
 - simplified (150 m) boundary rings for coverage mapping + point-in-region tests
Mainland/near-shore only: outlying islets (e.g. Keelung's Pengjia/Mianhua/Huaping, Yilan's
Guishan) are kept as separate parts but flagged and excluded from `mainland` figures.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import duckdb
from pyproj import Transformer
from shapely import wkb
from shapely.geometry import mapping, MultiPolygon
from shapely.ops import transform, unary_union

RELEASE = "2026-09-23.1"
REGIONS = [  # (key, Chinese name, ISO 3166-2 code, tier)
    ("taipei", "臺北市", "TW-TPE", "core"),
    ("new_taipei", "新北市", "TW-NWT", "core"),
    ("keelung", "基隆市", "TW-KEE", "core"),
    ("taoyuan", "桃園市", "TW-TAO", "core"),
    ("hsinchu_city", "新竹市", "TW-HSZ", "core"),
    ("hsinchu_county", "新竹縣", "TW-HSQ", "core"),
    ("yilan", "宜蘭縣", "TW-ILA", "evaluate"),
]
MAINLAND_BBOX = (120.85, 24.30, 122.05, 25.31)  # lon/lat window containing the main island parts
OUT = Path(__file__).resolve().parents[2] / "data/ntw/theater_regions.json"


def main():
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    codes = ",".join(f"'{r[2]}'" for r in REGIONS)
    rows = con.execute(f"""
      SELECT id, region, names.primary, ST_AsWKB(geometry)
      FROM read_parquet('s3://overturemaps-us-west-2/release/{RELEASE}/theme=divisions/type=division_area/*', hive_partitioning=1)
      WHERE country='TW' AND subtype='region' AND class='land' AND region IN ({codes})""").fetchall()
    by_code = {r[1]: r for r in rows}
    to3826 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True).transform
    out = {"overture_release": RELEASE, "source": "Overture Maps divisions/division_area (subtype=region, class=land)",
           "license_note": "Overture divisions: ODbL (OSM-derived) -- attribution required", "regions": []}
    for key, name, code, tier in REGIONS:
        div_id, _, _, w = by_code[code]
        g = wkb.loads(bytes(w))
        parts = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        main_parts, islands = [], []
        for p in parts:
            c = p.representative_point()
            ok = MAINLAND_BBOX[0] <= c.x <= MAINLAND_BBOX[2] and MAINLAND_BBOX[1] <= c.y <= MAINLAND_BBOX[3]
            (main_parts if ok else islands).append(p)
        m = unary_union(main_parts)
        m3826 = transform(to3826, m)
        simp = m3826.simplify(150.0, preserve_topology=True)
        simp4326 = transform(Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True).transform, simp)
        isl_area = sum(transform(to3826, p).area for p in islands) / 1e6
        out["regions"].append({
            "key": key, "name": name, "iso": code, "tier": tier, "overture_division_id": div_id,
            "parts_total": len(parts), "parts_mainland": len(main_parts), "parts_excluded_islets": len(islands),
            "land_area_km2_mainland": round(m3826.area / 1e6, 2),
            "land_area_km2_excluded_islets": round(isl_area, 2),
            "bbox_lonlat": [round(v, 5) for v in m.bounds],
            "bbox_epsg3826": [round(v, 1) for v in m3826.bounds],
            "boundary_simplified_150m": mapping(simp4326),
        })
    union = unary_union([transform(to3826, unary_union([p for p in (wkb.loads(bytes(by_code[r[2]][3])).geoms
                          if wkb.loads(bytes(by_code[r[2]][3])).geom_type == 'MultiPolygon' else [wkb.loads(bytes(by_code[r[2]][3]))])
                          if MAINLAND_BBOX[0] <= p.representative_point().x <= MAINLAND_BBOX[2]
                          and MAINLAND_BBOX[1] <= p.representative_point().y <= MAINLAND_BBOX[3]])) for r in REGIONS])
    core_keys = {r[0] for r in REGIONS if r[3] == "core"}
    core_union = unary_union([transform(to3826, unary_union([p for p in (lambda g: list(g.geoms) if g.geom_type=='MultiPolygon' else [g])(wkb.loads(bytes(by_code[r[2]][3])))
                          if MAINLAND_BBOX[0] <= p.representative_point().x <= MAINLAND_BBOX[2]
                          and MAINLAND_BBOX[1] <= p.representative_point().y <= MAINLAND_BBOX[3]])) for r in REGIONS if r[0] in core_keys])
    for label, u in (("core_6_regions", core_union), ("core_plus_yilan", union)):
        b = u.bounds
        out[label] = {"land_area_km2": round(u.area / 1e6, 2), "bbox_epsg3826": [round(v, 1) for v in b],
                      "extent_km": [round((b[2] - b[0]) / 1000, 1), round((b[3] - b[1]) / 1000, 1)],
                      "bbox_area_km2": round((b[2] - b[0]) * (b[3] - b[1]) / 1e6, 1)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(OUT, OUT.stat().st_size, "bytes")
    for r in out["regions"]:
        print(r["name"], r["land_area_km2_mainland"], r["bbox_lonlat"], "islets:", r["parts_excluded_islets"], round(r["land_area_km2_excluded_islets"], 2))
    for k in ("core_6_regions", "core_plus_yilan"):
        print(k, out[k])


if __name__ == "__main__":
    main()
