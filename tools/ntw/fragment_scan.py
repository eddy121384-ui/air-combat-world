"""Population scan of strict-gate footprint failures (PR #23 review P0 #2: building shard blocked by tiny fragments).

Runs exactly the accepted pipeline's pre-mesh stages on every source polygon part, without meshing:
  repair_worldmodel_polygon (GEOS make_valid structure) -> 500 m owner tile -> prepare_footprint (tile-local float32
  quantisation + GEOS revalidation)
and records every part the STRICT gate would reject at this stage, with the geometry facts a production policy would need
(area, mean width, whether it is the largest repaired piece, failure reasons).
Sources: all Taipei WFS records (NTW frame) and the accepted Xinyi source in its accepted ENU frame (regression evidence).
Writes data/ntw/terrain/fragment_scan.json (committed, compact).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))


def scan_rings(fid, si, outer, holes):
    from geometry import repair_worldmodel_polygon
    from serialization_space import prepare_footprint, tile_origin
    import numpy as np
    parts, rep = repair_worldmodel_polygon({"footprint_enu": outer, "holes_enu": holes})
    out = []
    if not parts:
        return [{"id": fid, "part": si, "stage": "source_rejected", "reason": rep.get("reason")}]
    a = np.asarray(outer, float)
    origin = tile_origin((float(a[:, 0].mean()), float(a[:, 1].mean())))
    largest = max(range(len(parts)), key=lambda i: parts[i].area)
    for ri, rp in enumerate(parts):
        try:
            _, fg = prepare_footprint(rp, origin)
        except Exception as exc:  # noqa: BLE001
            fg = {"pass": False, "failures": [f"exception:{type(exc).__name__}"]}
        if not fg["pass"]:
            out.append({"id": fid, "part": si, "repaired_part": ri, "is_largest": ri == largest, "pieces": len(parts),
                        "area_m2": float(rp.area), "mean_width_m": float(2 * rp.area / rp.length) if rp.length else 0.0,
                        "largest_area_m2": float(parts[largest].area), "repair_status": rep["status"], "failures": fg["failures"]})
    return out


def wfs_line(line):
    import frame
    r = json.loads(line)
    g = r["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    ox, oy = frame.NTW_ORIGIN_TM2
    res = []
    for si, poly in enumerate(polys):
        rings = [[(x - ox, y - oy) for x, y in ring] for ring in poly]
        res.extend(scan_rings(r["id"], si, rings[0], rings[1:]))
    return len(polys), res


def main():
    t0 = time.time()
    lines = (REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson").read_text(encoding="utf-8").splitlines()
    with Pool(6) as pool:
        results = pool.map(wfs_line, lines, chunksize=500)
    parts = sum(n for n, _ in results)
    fails = [f for _, r in results for f in r]
    # accepted Xinyi source, accepted ENU frame (exactly what build_full_xinyi meshes)
    from worldmodel import build_worldmodel
    wm = build_worldmodel(REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson", REPO / "cities/taipei/city.yaml",
                          source_crs="EPSG:3826")
    xf, xparts = [], 0
    for b in wm["buildings"]:
        if b["suppressed"]:
            continue
        for pi, p in enumerate(b["polygons"]):
            xparts += 1
            xf.extend(scan_rings(b["id"], pi, p["footprint_enu"], p.get("holes_enu", [])))
    frag = [f for f in fails if f.get("stage") != "source_rejected"]
    nonlargest = [f for f in frag if not f["is_largest"]]
    largest = [f for f in frag if f["is_largest"]]
    areas = sorted(f["area_m2"] for f in nonlargest)
    out = {
        "taipei_wfs": {"records": len(lines), "polygon_parts": parts, "strict_footprint_stage_failures": len(frag),
                       "source_rejected": sum(1 for f in fails if f.get("stage") == "source_rejected"),
                       "failing_pieces_non_largest": len(nonlargest), "failing_pieces_largest": len(largest),
                       "non_largest_area_m2": {"max": max(areas) if areas else None, "median": areas[len(areas) // 2] if areas else None},
                       "non_largest_mean_width_max_m": max((f["mean_width_m"] for f in nonlargest), default=None),
                       "failure_reasons": dict(Counter(x.split(":")[0] for f in frag for x in f["failures"])),
                       "largest_piece_failures": largest[:20], "non_largest_examples": sorted(nonlargest, key=lambda f: -f["area_m2"])[:20]},
        "xinyi_accepted_enu": {"polygon_parts": xparts, "strict_footprint_stage_failures": len(xf), "failures": xf[:10]},
        "seconds": round(time.time() - t0, 1),
    }
    p = REPO / "data/ntw/terrain/fragment_scan.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: (v if k != "taipei_wfs" else {kk: vv for kk, vv in v.items() if "examples" not in kk and "largest_piece" not in kk})
                      for k, v in out.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
