"""Building shard seam test (PR #22 review P0): two independently built adjacent shards vs one joint build.

Shards straddle the boundary between the two pilot cells (N = 2,768,000 m, EPSG:3826), 8 km wide x 1 km deep each, using the
unchanged accepted geometry stack via build_pilot.build(bounds_ntw=..., suppress_ids=...):
  south  E 304-312 km, N 2767-2768 km   (top of C+0038+0345)
  north  E 304-312 km, N 2768-2769 km   (bottom of C+0038+0346; contains the south part of the accepted Xinyi sector)
  joint  E 304-312 km, N 2767-2769 km
Policies under test
  ownership   source-part vertex-mean centroid -> 500 m tile -> shard (no clipping, no duplication)
  fetch halo  0 m: a part whose centroid lies in the shard always intersects the shard, so a bbox query on the shard suffices
  culling     per-shard culling bounds = union of emitted component bounds (MEASURED, never assumed); overhang above
              `max_overhang_m` fails the test (explicit policy instead of a fixed halo)
  L3          WFS ids owned by the accepted Xinyi sector are suppressed and ledgered
Checks: per-tile GLB SHA identical (independent vs joint), every emitted part owned exactly once, no orphan (every source part
with centroid in the joint region is emitted, suppressed or ledgered), cross-boundary components, Xinyi ids never emitted.
Writes data/ntw/terrain/building_shard_test.json (committed) ; GLBs stay in data/generated/ntw/shards (ignored).
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import frame  # noqa: E402

OUT = REPO / "data/generated/ntw/shards"
MAX_OVERHANG_M = 500.0
SHARDS = {"south": (304000, 2767000, 312000, 2768000), "north": (304000, 2768000, 312000, 2769000),
          "joint": (304000, 2767000, 312000, 2769000)}


def xinyi_ids():
    src = json.loads((REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson").read_text(encoding="utf-8"))
    return frozenset(str(f["id"]) for f in src["features"])


def run(name, fragment_policy=True):
    import build_pilot as bp
    bp.FRAGMENT_POLICY["enabled"] = fragment_policy
    x0, y0, x1, y1 = SHARDS[name]
    b = (x0 - frame.NTW_ORIGIN_TM2[0], y0 - frame.NTW_ORIGIN_TM2[1], x1 - frame.NTW_ORIGIN_TM2[0], y1 - frame.NTW_ORIGIN_TM2[1])
    cfg = {"id": f"shard_{name}", "provider": "taipei_wfs", "role": f"Phase 2B building shard seam test ({name})"}
    r = bp.build(cfg["id"], OUT / name, bounds_ntw=b, suppress_ids=xinyi_ids(), cfg=cfg)
    return name, r["gate_result"]["pass"]


def tiles_of(d):
    rep = json.loads((d / "pilot.report.json").read_text(encoding="utf-8"))
    return {t["tile"]: t for t in rep["tiles"]}, rep


def comp_bounds(d):
    bx = [np.inf, np.inf, -np.inf, -np.inf]
    for g in sorted((d / "tiles").glob("*.glb")):
        sc = trimesh.load_scene(io.BytesIO(g.read_bytes()), file_type="glb", process=False)
        for n in sc.graph.nodes_geometry:
            tr, gn = sc.graph[n]
            m = sc.geometry[gn].copy()
            m.apply_transform(tr)
            v = np.asarray(m.vertices)
            x, y = v[:, 0] + frame.NTW_ORIGIN_TM2[0], -v[:, 2] + frame.NTW_ORIGIN_TM2[1]
            bx = [min(bx[0], x.min()), min(bx[1], y.min()), max(bx[2], x.max()), max(bx[3], y.max())]
    return [round(float(v), 2) for v in bx]


def analyse():
    t_s, r_s = tiles_of(OUT / "south")
    t_n, r_n = tiles_of(OUT / "north")
    t_j, r_j = tiles_of(OUT / "joint")
    union = {**t_s, **t_n}
    same = [k for k in t_j if k in union and union[k]["sha256"] == t_j[k]["sha256"]]
    led = {}
    for nm in ("south", "north", "joint"):
        led[nm] = [json.loads(x) for x in gzip.open(OUT / nm / "buildings.ledger.jsonl.gz", "rt", encoding="utf-8")]
    em = lambda rows: [(r["building_id"], r["polygon_index"]) for r in rows if r["status"] == "emitted"]  # noqa: E731
    e_s, e_n, e_j = em(led["south"]), em(led["north"]), em(led["joint"])
    both = set(e_s) & set(e_n)
    xin = xinyi_ids()
    emitted_xinyi = sum(1 for b, _ in e_s + e_n + e_j if b in xin)
    status = lambda rows: {s: sum(1 for r in rows if r["status"] == s) for s in sorted({r["status"] for r in rows})}  # noqa: E731
    out = {"policy": {"ownership": "vertex-mean centroid -> 500 m tile -> shard", "fetch_halo_m": 0,
                      "culling_bounds": "measured union of emitted component bounds", "max_overhang_m": MAX_OVERHANG_M,
                      "l3_suppression": "Xinyi pinned source ids (11,132)"},
           "shards_epsg3826": SHARDS,
           "fragment_policy": r_j.get("fragment_policy"), "ledgered_repair_fragments_joint": r_j.get("ledgered_repair_fragments"),
           "strict_mode_result": "see strict_mode_evidence: the strict accepted policy FAILS CLOSED on 1 part in the north shard",
           "gate": {k: v["gate_result"]["pass"] for k, v in (("south", r_s), ("north", r_n), ("joint", r_j))},
           "tiles": {"south": len(t_s), "north": len(t_n), "joint": len(t_j), "union_independent": len(union),
                     "joint_tiles_byte_identical_to_independent": len(same), "tile_sets_equal": set(t_j) == set(union)},
           "ownership": {"emitted_parts_south": len(e_s), "emitted_parts_north": len(e_n), "emitted_parts_joint": len(e_j),
                         "parts_emitted_by_both_shards": len(both), "independent_union_equals_joint": sorted(e_s + e_n) == sorted(e_j),
                         "duplicates_within_joint": len(e_j) - len(set(e_j))},
           "ledger_status": {"south": status(led["south"]), "north": status(led["north"]), "joint": status(led["joint"])},
           "orphans": {"source_parts_in_joint_not_accounted": r_j["accounting"]["unaccounted_parts"],
                       "note": "every part with centroid in the joint region is emitted, suppressed (L3) or ledgered"},
           "xinyi": {"xinyi_ids_emitted": emitted_xinyi, "suppressed_parts_joint": r_j["accounting"].get("suppressed_l3_xinyi")},
           "geometry": {k: {"components": v["accounting"]["emitted_serialization_components"], "triangles": v["tile_summary"]["total_triangles"],
                            "glb_bytes": v["tile_summary"]["total_glb_bytes"], "manifest_sha256": v["tile_summary"]["manifest_sha256"],
                            "runtime_s": v["performance"]["runtime_seconds"]} for k, v in (("south", r_s), ("north", r_n), ("joint", r_j))},
           }
    cb = {}
    for nm in ("south", "north"):
        b = comp_bounds(OUT / nm)
        x0, y0, x1, y1 = SHARDS[nm]
        over = max(x0 - b[0], b[2] - x1, y0 - b[1], b[3] - y1, 0.0)
        cb[nm] = {"culling_bounds_epsg3826": b, "max_overhang_m": round(over, 2), "within_policy": over <= MAX_OVERHANG_M}
    out["culling"] = cb
    out["pass"] = (all(out["gate"].values()) and out["tiles"]["tile_sets_equal"] and len(same) == len(t_j)
                   and out["ownership"]["independent_union_equals_joint"] and not both and emitted_xinyi == 0
                   and out["orphans"]["source_parts_in_joint_not_accounted"] == 0 and all(c["within_policy"] for c in cb.values()))
    strict = REPO / "data/generated/ntw/shards_strict/north/pilot.report.json"
    if strict.exists():
        sr = json.loads(strict.read_text(encoding="utf-8"))
        out["strict_mode_evidence"] = {"north_gate_pass": sr["gate_result"]["pass"], "failures": sr["failures"][:3]}
    p = REPO / "data/ntw/terrain/building_shard_test.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyse-only", action="store_true")
    a = ap.parse_args()
    if not a.analyse_only:
        OUT.mkdir(parents=True, exist_ok=True)
        with ProcessPoolExecutor(3) as ex:
            for name, ok in ex.map(run, list(SHARDS)):
                print(name, "pass" if ok else "FAIL")
    analyse()


if __name__ == "__main__":
    main()
