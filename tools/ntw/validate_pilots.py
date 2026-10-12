"""Cross-check pilot outputs and write data/ntw/pilot_results.json (compact, committed).

Checks per pilot (run1 vs run2 under data/generated/ntw/pilots/):
  determinism   run1 and run2 tile SHA-256 lists + manifest are identical
  ownership     every emitted (building, part) appears in exactly ONE tile; its tile equals floor(vertex-mean centroid / 500 m)
  node_unique   GLB node names are unique across all tiles of the pilot
  boundary      how many components extend beyond their owner tile (legal: ownership is by centroid) and by how much
  extent        every owner tile lies inside the pilot's 5 x 5 block
  accounting    emitted + excluded + rejected == source parts, unaccounted == 0
  blender       headless Blender 5.2 imported-buffer audit result (if present)
"""
from __future__ import annotations

import gzip
import io
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_pilot as bp  # noqa: E402
import frame  # noqa: E402

ROOT = REPO / "data/generated/ntw/pilots"


def load_report(d):
    return json.loads((d / "pilot.report.json").read_text(encoding="utf-8"))


def check(letter, pid):
    r1d, r2d = ROOT / f"{letter}_run1", ROOT / f"{letter}_run2"
    r1 = load_report(r1d)
    out = {"pilot": pid, "role": r1["pilot"]["role"], "provider": r1["pilot"]["provider"],
           "block_sw_tile": r1["frame"]["block_sw_tile"], "gate_pass": r1["gate_result"]["pass"]}
    if r2d.exists() and (r2d / "pilot.report.json").exists():
        r2 = load_report(r2d)
        same = [t["sha256"] for t in r1["tiles"]] == [t["sha256"] for t in r2["tiles"]]
        out["determinism"] = {"runs": 2, "tile_sha256_identical": same,
                              "manifest_sha256_run1": r1["tile_summary"]["manifest_sha256"],
                              "manifest_sha256_run2": r2["tile_summary"]["manifest_sha256"],
                              "normalized_input_sha256_identical": r1["source"]["normalized_input_sha256"] == r2["source"]["normalized_input_sha256"]}
    else:
        out["determinism"] = {"runs": 1, "note": "second run not available"}
    cfg = bp.pilot_cfg(pid)
    ix0, iy0 = r1["frame"]["block_sw_tile"]
    feats = (bp.load_wfs if cfg["provider"] == "taipei_wfs" else bp.load_overture)(
        cfg, ix0 * 500.0, iy0 * 500.0, (ix0 + 5) * 500.0, (iy0 + 5) * 500.0)
    cent = {(f["id"], si): bp.vmean(rings[0]) for f in feats for si, rings in f["polys"]}
    rows = [json.loads(x) for x in gzip.open(r1d / "buildings.ledger.jsonl.gz", "rt", encoding="utf-8")]
    emitted = [x for x in rows if x["status"] == "emitted"]
    keys = Counter((x["building_id"], x["polygon_index"]) for x in emitted)
    wrong_tile = 0
    for x in emitted:
        c = cent[(x["building_id"], x["polygon_index"])]
        want = frame.cell_key(math.floor(c[0] / 500.0), math.floor(c[1] / 500.0))
        wrong_tile += int(want != x["tile"])
    names, overhang, max_over, outside = Counter(), 0, 0.0, 0
    comps = 0
    for g in sorted((r1d / "tiles").glob("*.glb")):
        key = "_".join(g.stem.split("_")[-2:])
        tx, ty = (int(v) for v in key.split("_"))
        if not (ix0 <= tx < ix0 + 5 and iy0 <= ty < iy0 + 5):
            outside += 1
        sc = trimesh.load_scene(io.BytesIO(g.read_bytes()), file_type="glb", process=False)
        for n in sc.graph.nodes_geometry:
            names[n] += 1
            comps += 1
            tr, gn = sc.graph[n]
            m = sc.geometry[gn].copy()
            m.apply_transform(tr)
            v = np.asarray(m.vertices)
            wx, wy = v[:, 0], -v[:, 2]  # glTF world: x = NTW east, z = -NTW north
            ox, oy = tx * 500.0, ty * 500.0
            over = max(ox - wx.min(), wx.max() - (ox + 500.0), oy - wy.min(), wy.max() - (oy + 500.0), 0.0)
            if over > 1e-3:
                overhang += 1
                max_over = max(max_over, over)
    out["ownership"] = {
        "emitted_parts": len(emitted), "parts_in_more_than_one_tile": sum(1 for v in keys.values() if v > 1),
        "parts_with_tile_not_equal_floor_centroid_rule": wrong_tile, "glb_nodes": comps,
        "duplicate_node_names": sum(1 for v in names.values() if v > 1), "tiles_outside_block": outside}
    out["boundary"] = {"components_extending_past_owner_tile": overhang,
                       "pct": round(100.0 * overhang / max(comps, 1), 2), "max_overhang_m": round(max_over, 2),
                       "note": "legal by design: tile ownership is by source-part centroid; geometry is never clipped or duplicated"}
    a = r1["accounting"]
    out["accounting"] = {"source_parts": a["source_polygon_parts"], "emitted": a["emitted_source_polygon_parts"],
                         "excluded_underground": a["excluded_underground"], "source_rejected": a["source_rejected"],
                         "unaccounted": a["unaccounted_parts"], "height_source_counts": a["height_source_counts"],
                         "repair_outcomes": a["repair_outcomes"], "provider_part_counts": r1["source"]["provider_part_counts"]}
    ts = r1["tile_summary"]
    out["geometry"] = {"tiles": ts["count"], "components": a["emitted_serialization_components"], "triangles": ts["total_triangles"],
                       "vertices": ts["total_vertices"], "glb_bytes": ts["total_glb_bytes"],
                       "triangles_per_component": round(ts["total_triangles"] / a["emitted_serialization_components"], 2),
                       "glb_bytes_per_component": round(ts["total_glb_bytes"] / a["emitted_serialization_components"], 1),
                       "tile_triangles": ts["triangles"], "tile_nodes": ts["nodes"], "manifest_sha256": ts["manifest_sha256"]}
    out["placement"] = r1["placement_check"]
    tc = {k: v for k, v in r1["terrain_check"].items() if k != "dtm_tile_sha256"}
    out["terrain"] = tc
    out["performance_wall_clock"] = {"run1_seconds": r1["performance"]["runtime_seconds"], "max_rss_mb": r1["performance"]["max_rss_mb"],
                                     "note": "three pilots were run concurrently on one machine; timings are upper bounds"}
    ba = r1d / "blender_audit.json"
    if ba.exists():
        b = json.loads(ba.read_text(encoding="utf-8"))
        out["blender_5_2_headless"] = {"version": b["blender_version"], "pass": b["pass"], "failures": b["failures"],
                                       "imported_mesh_components": b["imported_mesh_components"], "imported_triangles": b["imported_triangles"],
                                       "failed_meshes": b["failed_meshes"], "totals": b["totals"]}
    return out


def main():
    res = {"note": "Pilot evidence. Large outputs are NOT committed (ignored: data/generated/ntw/pilots).",
           "pilots": [check(p["id"].split("_")[0], p["id"]) for p in json.loads((HERE / "pilots.json").read_text())["pilots"]]}
    (REPO / "data/ntw/pilot_results.json").write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    for p in res["pilots"]:
        print(p["pilot"], "gate", p["gate_pass"], "| determ", p["determinism"].get("tile_sha256_identical"), "| dupOwn",
              p["ownership"]["parts_in_more_than_one_tile"], "| wrongTile", p["ownership"]["parts_with_tile_not_equal_floor_centroid_rule"],
              "| dupNames", p["ownership"]["duplicate_node_names"], "| overhang", p["boundary"], "| blender", p.get("blender_5_2_headless", {}).get("pass"))


if __name__ == "__main__":
    main()
