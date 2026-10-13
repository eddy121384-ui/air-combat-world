"""Whole-cell building shard test (PR #23 review P0 #2, runtime-gate round).

Two WHOLE neighbouring 8 km cells, built independently and jointly with the unchanged accepted geometry stack
(build_pilot.build), mixed providers across the Taipei / New Taipei admin border:
  A      C+0038+0345  E 304-312 km, N 2760-2768 km
  B      C+0038+0346  E 304-312 km, N 2768-2776 km   (contains the accepted Xinyi sector: its WFS ids are suppressed, L3)
  joint  E 304-312 km, N 2760-2776 km
Provider ownership: Taipei WFS owns parts whose vertex-mean centroid is inside TW-TPE (Overture divisions polygon, local cache);
Overture (cached release 2026-09-23.1, ovt_taipei_fp) owns the rest; the non-owner copy is ledgered. Parts of the cells that
are outside TW-TPE AND outside the cached Overture bbox are reported BLOCKED (no source fetched this round) - never "empty".
Policies under test (strict accepted gates unchanged): FRAGMENT_POLICY off; the CANDIDATE quantisation fallback ON (it runs
only where the accepted path already failed; the set of parts it touched IS the strict-mode failure set, recorded per part).
Checks: per-tile GLB SHA independent == joint, ownership exactly once, no orphans, Xinyi ids never emitted, cross-provider
footprint overlaps at the admin border, measured culling bounds (overhang), and a loader scenario: cell-rectangle vs
culling-bounds loading rules for a building view distance V.
Writes data/ntw/terrain/building_cell_shard_test.json ; GLBs stay in data/generated/ntw/cell_shards (ignored).
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
import shapely
import trimesh
from shapely import box

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import frame  # noqa: E402

OUT = REPO / "data/generated/ntw/cell_shards"
OVT = REPO / "data/generated/ntw/ovt_taipei_fp.parquet"
CELLS = {"A": (304000, 2760000, 312000, 2768000), "B": (304000, 2768000, 312000, 2776000), "joint": (304000, 2760000, 312000, 2776000)}
VIEW_M = [1500.0, 3000.0]


def xinyi_ids():
    src = json.loads((REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson").read_text(encoding="utf-8"))
    return frozenset(str(f["id"]) for f in src["features"])


def taipei_polygon_tm2():
    from world_planner import load_geography
    regions = load_geography()[4]
    return regions["TW-TPE"][1]


def overture_coverage_tm2():
    from world_planner import to_tm2
    bb = json.loads((OVT.parent / (OVT.name + ".manifest.json")).read_text(encoding="utf-8"))["bbox_lonlat"]
    return to_tm2(shapely.segmentize(box(*bb), 0.001))


def ntw(g):
    return shapely.affinity.translate(g, xoff=-frame.NTW_ORIGIN_TM2[0], yoff=-frame.NTW_ORIGIN_TM2[1])


def cfg_for(name):
    return {"id": f"cellshard_{name}", "provider": "mixed_wfs_overture", "overture_parquet": str(OVT),
            "wfs_owner_polygon_ntw_wkb": shapely.to_wkb(ntw(taipei_polygon_tm2())).hex(),
            "role": f"runtime-gate whole-cell building shard test ({name})"}


def run(name):
    import build_pilot as bp
    bp.FRAGMENT_POLICY["enabled"] = False
    bp.QUANT_FALLBACK["enabled"] = True
    # the first run failed closed on one MESH-stage part (tp_building_height.307096) in A / joint, so no tiles were written;
    # shard mechanics are measured with the explicit diagnostic flag (gate result stays FAIL, failures reported)
    bp.DIAGNOSTIC_WRITE_ON_FAILURE["enabled"] = True
    x0, y0, x1, y1 = CELLS[name]
    b = (x0 - frame.NTW_ORIGIN_TM2[0], y0 - frame.NTW_ORIGIN_TM2[1], x1 - frame.NTW_ORIGIN_TM2[0], y1 - frame.NTW_ORIGIN_TM2[1])
    r = bp.build(f"cellshard_{name}", OUT / name, bounds_ntw=b, suppress_ids=xinyi_ids(), cfg=cfg_for(name))
    return name, r["gate_result"]["pass"]


def tiles_of(d):
    rep = json.loads((d / "pilot.report.json").read_text(encoding="utf-8"))
    return {t["tile"]: t for t in rep["tiles"]}, rep


def comp_boxes(d):
    out = []
    for g in sorted((d / "tiles").glob("*.glb")):
        sc = trimesh.load_scene(io.BytesIO(g.read_bytes()), file_type="glb", process=False)
        for n in sc.graph.nodes_geometry:
            tr, gn = sc.graph[n]
            m = sc.geometry[gn].copy()
            m.apply_transform(tr)
            v = np.asarray(m.vertices)
            x, y = v[:, 0] + frame.NTW_ORIGIN_TM2[0], -v[:, 2] + frame.NTW_ORIGIN_TM2[1]
            out.append((x.min(), y.min(), x.max(), y.max()))
    return np.array(out)


def rect_dist(px, py, b):
    dx = np.maximum(np.maximum(b[..., 0] - px, 0), px - b[..., 2])
    dy = np.maximum(np.maximum(b[..., 1] - py, 0), py - b[..., 3])
    return np.hypot(dx, dy)


def loader_scenario(boxes, cells):
    """Camera grid (50 m) around the A/B seam. A component is visible within V; its shard is loaded if the camera is within V
    of (rule 1) the 8 km cell rectangle or (rule 2) the measured culling bounds. Only components overhanging their cell can
    break rule 1, so the test is exact while evaluating only those."""
    res = {}
    for V in VIEW_M:
        xs = np.arange(300000.0, 316001.0, 50.0)
        ys = np.arange(2756000.0, 2780001.0, 50.0)
        GX, GY = np.meshgrid(xs, ys)
        r = {}
        for rule in ("cell_rectangle", "culling_bounds"):
            bad = np.zeros(GX.shape, bool)
            for nm in ("A", "B"):
                b = boxes[nm]
                cell = np.array(cells[nm], float)
                over = (b[:, 0] < cell[0]) | (b[:, 1] < cell[1]) | (b[:, 2] > cell[2]) | (b[:, 3] > cell[3])
                cull = np.array([b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()])
                ref = cell if rule == "cell_rectangle" else cull
                loaded = rect_dist(GX, GY, ref) <= V
                for bb in b[over]:
                    bad |= (rect_dist(GX, GY, bb) <= V) & ~loaded
            r[rule] = {"camera_positions": int(GX.size), "positions_with_visible_but_unloaded_building": int(bad.sum()),
                       "pass": not bad.any()}
        res["V_%d_m" % V] = r
    return res


def provider_overlaps(cfg):
    """Emitted-owner footprints of the two providers that overlap (> 1 m2) near the admin border (double buildings)."""
    import build_pilot as bp
    x0, y0, x1, y1 = CELLS["joint"]
    b = (x0 - frame.NTW_ORIGIN_TM2[0], y0 - frame.NTW_ORIGIN_TM2[1], x1 - frame.NTW_ORIGIN_TM2[0], y1 - frame.NTW_ORIGIN_TM2[1])
    feats = bp.load_mixed(cfg, *b)
    owner = shapely.from_wkb(bytes.fromhex(cfg["wfs_owner_polygon_ntw_wkb"]))
    band = shapely.buffer(owner.boundary, 200.0)
    shapely.prepare(band)
    w, o = [], []
    for f in feats:
        if f["excluded"]:
            continue
        for si, rings in f["polys"]:
            g = shapely.make_valid(shapely.Polygon(rings[0], rings[1:]))
            if shapely.intersects(band, g):
                (w if f["provider"].startswith("taipei_wfs") else o).append((f["id"], g))
    tree = shapely.STRtree([g for _, g in w])
    pairs = []
    for oid, g in o:
        for j in tree.query(g, predicate="intersects"):
            a = float(shapely.intersection(g, w[j][1]).area)
            if a > 1.0:
                pairs.append({"overture_id": oid, "wfs_id": w[j][0], "overlap_m2": round(a, 2),
                              "overture_area_m2": round(float(g.area), 1), "wfs_area_m2": round(float(w[j][1].area), 1)})
    return {"border_band_m": 200.0, "wfs_parts_in_band": len(w), "overture_parts_in_band": len(o), "overlapping_pairs": len(pairs),
            "overlap_m2_total": round(sum(p["overlap_m2"] for p in pairs), 1), "examples": sorted(pairs, key=lambda p: -p["overlap_m2"])[:10]}


def analyse():
    t, r, led = {}, {}, {}
    for nm in CELLS:
        t[nm], r[nm] = tiles_of(OUT / nm)
        led[nm] = [json.loads(x) for x in gzip.open(OUT / nm / "buildings.ledger.jsonl.gz", "rt", encoding="utf-8")]
    union = {**t["A"], **t["B"]}
    same = [k for k in t["joint"] if k in union and union[k]["sha256"] == t["joint"][k]["sha256"]]
    em = lambda rows: [(r_["building_id"], r_["polygon_index"], r_["provider"]) for r_ in rows if r_["status"] == "emitted"]  # noqa: E731
    e = {nm: em(led[nm]) for nm in CELLS}
    both = set(e["A"]) & set(e["B"])
    xin = xinyi_ids()
    emitted_xinyi = sum(1 for nm in CELLS for b, _, p in e[nm] if b in xin and p.startswith("taipei_wfs"))
    status = lambda rows: {s: sum(1 for x in rows if x["status"] == s) for s in sorted({x["status"] for x in rows})}  # noqa: E731
    cells_tm2 = {nm: box(*v) for nm, v in CELLS.items()}
    tpe = taipei_polygon_tm2()
    cov = overture_coverage_tm2()
    blocked = {nm: round(float(shapely.difference(shapely.difference(g, tpe), cov).area) / 1e6, 3) for nm, g in cells_tm2.items()}
    boxes = {nm: comp_boxes(OUT / nm) for nm in ("A", "B")}
    cull = {}
    for nm in ("A", "B"):
        b = boxes[nm]
        x0, y0, x1, y1 = CELLS[nm]
        cb = [float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max())]
        cull[nm] = {"culling_bounds_epsg3826": [round(v, 2) for v in cb], "overhang_m": {"west": round(x0 - cb[0], 2), "south": round(y0 - cb[1], 2),
                    "east": round(cb[2] - x1, 2), "north": round(cb[3] - y1, 2)},
                    "components_overhanging_cell": int(((b[:, 0] < x0) | (b[:, 1] < y0) | (b[:, 2] > x1) | (b[:, 3] > y1)).sum())}
    fb = r["joint"].get("quantization_fallback_applied", [])
    out = {"cells_epsg3826": CELLS,
           "policy": {"ownership": "vertex-mean centroid -> 500 m tile -> cell (no clipping, no duplication)",
                      "providers": "Taipei WFS inside TW-TPE, Overture (2026-09-23.1 cached) outside; non-owner copy ledgered",
                      "fetch_halo_m": 0, "fragment_policy": r["joint"].get("fragment_policy"),
                      "quantization_fallback": r["joint"].get("quantization_fallback_policy"),
                      "strict_gates": "unchanged (accepted prepare_footprint, strict_mesh_gate float64/float32/world)"},
           "blocked_source_km2": {"meaning": "inside the cell, outside TW-TPE and outside the cached Overture bbox: no source this round",
                                  **blocked},
           "gate": {nm: r[nm]["gate_result"]["pass"] for nm in CELLS},
           "build_failures": {nm: r[nm]["failures"] for nm in CELLS},
           "diagnostic_write_on_failure": {nm: r[nm].get("diagnostic_write_on_failure") for nm in CELLS},
           "tiles": {nm: len(t[nm]) for nm in CELLS} | {"union_independent": len(union), "joint_tiles_byte_identical_to_independent": len(same),
                                                        "tile_sets_equal": set(t["joint"]) == set(union)},
           "ownership": {"emitted_parts": {nm: len(e[nm]) for nm in CELLS}, "parts_emitted_by_both_cells": len(both),
                         "independent_union_equals_joint": sorted(e["A"] + e["B"]) == sorted(e["joint"]),
                         "duplicates_within_joint": len(e["joint"]) - len(set(e["joint"])),
                         "emitted_by_provider_joint": {p: sum(1 for *_, q in e["joint"] if q == p) for p in sorted({q for *_, q in e["joint"]})}},
           "ledger_status": {nm: status(led[nm]) for nm in CELLS},
           "orphans": {nm: r[nm]["accounting"]["unaccounted_parts"] for nm in CELLS},
           "xinyi": {"xinyi_wfs_ids_emitted": emitted_xinyi, "suppressed_parts_joint": r["joint"]["accounting"].get("suppressed_l3_xinyi")},
           "strict_mode": {"meaning": "parts the ACCEPTED path rejects = exactly the parts the fallback was invoked on",
                           "strict_failures_joint": len(fb),
                           "parts": [{k: f.get(k) for k in ("building_id", "polygon_index", "repaired_part", "accepted_failures", "pass", "ledgered",
                                                             "reason", "failures", "source_area_m2", "area_delta_m2", "symmetric_difference_m2",
                                                             "hausdorff_m", "wide_removed_m2", "wide_added_m2", "holes_before", "holes_after")} for f in fb]},
           "geometry": {nm: {"components": r[nm]["accounting"]["emitted_serialization_components"], "triangles": r[nm]["tile_summary"]["total_triangles"],
                             "glb_bytes": r[nm]["tile_summary"]["total_glb_bytes"], "manifest_sha256": r[nm]["tile_summary"]["manifest_sha256"],
                             "runtime_s": r[nm]["performance"]["runtime_seconds"]} for nm in CELLS},
           "culling": cull,
           "loader_scenario": loader_scenario(boxes, CELLS),
           "provider_border": provider_overlaps(cfg_for("joint"))}
    out["mechanics_pass"] = (out["tiles"]["tile_sets_equal"] and len(same) == len(t["joint"])
                             and out["ownership"]["independent_union_equals_joint"] and not both and emitted_xinyi == 0
                             and all(v == 0 for v in out["orphans"].values()))
    out["pass"] = all(out["gate"].values()) and out["mechanics_pass"]
    p = REPO / "data/ntw/terrain/building_cell_shard_test.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("gate", "build_failures", "mechanics_pass", "tiles", "ownership", "orphans", "xinyi", "blocked_source_km2", "culling", "loader_scenario", "pass")},
                     ensure_ascii=False, indent=1, default=float))
    print("strict failures:", len(fb), "provider overlaps:", out["provider_border"]["overlapping_pairs"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyse-only", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    if not a.analyse_only:
        OUT.mkdir(parents=True, exist_ok=True)
        names = a.only or list(CELLS)
        with ProcessPoolExecutor(len(names)) as ex:
            for name, ok in ex.map(run, names):
                print(name, "pass" if ok else "FAIL", flush=True)
    analyse()


if __name__ == "__main__":
    main()
