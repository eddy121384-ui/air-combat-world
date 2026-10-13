"""End-to-end evaluation of the quantisation fallback on EVERY part the strict accepted path rejects (fragment_scan.json).

For each failing source part: accepted prepare_footprint (must fail, as recorded) -> fallback -> unchanged mesher
(extrude_geos_polygon) -> unchanged strict_mesh_gate float64 -> GLB export/reload -> strict_mesh_gate float32 (tile-local and
world). Writes data/ntw/terrain/fallback_eval.json.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))
import frame  # noqa: E402
from geometry import extrude_geos_polygon, repair_worldmodel_polygon  # noqa: E402
from heights import derive_wfs_height  # noqa: E402
from quantization_fallback import fallback  # noqa: E402
from serialization_space import prepare_footprint, tile_origin, tile_transform  # noqa: E402
from strict_qa import strict_mesh_gate  # noqa: E402


def main():
    scan = json.loads((REPO / "data/ntw/terrain/fragment_scan.json").read_text(encoding="utf-8"))["taipei_wfs"]
    targets = {(f["id"], f["part"]) for f in scan["largest_piece_failures"] + scan["non_largest_examples"]}
    rows = []
    for line in (REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson").open(encoding="utf-8"):
        r = json.loads(line)
        g = r["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for si, poly in enumerate(polys):
            if (r["id"], si) not in targets:
                continue
            ox, oy = frame.NTW_ORIGIN_TM2
            rings = [[(x - ox, y - oy) for x, y in ring] for ring in poly]
            parts, _ = repair_worldmodel_polygon({"footprint_enu": rings[0], "holes_enu": rings[1:]})
            a = np.asarray(rings[0])
            origin = tile_origin((a[:, 0].mean(), a[:, 1].mean()))
            h = derive_wfs_height(r["p"])[0]
            largest = max(range(len(parts)), key=lambda i: parts[i].area)
            for ri, rp in enumerate(parts):
                sp, fg = prepare_footprint(rp, origin)
                if fg["pass"]:
                    continue
                serial, rep = fallback(rp, origin, ri == largest)
                row = {"id": r["id"], "part": si, "repaired_part": ri, "is_largest": ri == largest, "area_m2": rp.area,
                       "accepted_failures": fg["failures"], "fallback": {k: v for k, v in rep.items() if k != "accepted_gate_on_snapped"},
                       "accepted_gate_on_snapped": rep.get("accepted_gate_on_snapped")}
                mesh_ok = []
                for spp in serial:
                    m = extrude_geos_polygon(spp, float(h))
                    g64 = strict_mesh_gate(m, spp, float(h), precision="float64")
                    sc = trimesh.Scene()
                    sc.add_geometry(m, geom_name="n", node_name="n", transform=tile_transform(origin))
                    rl = trimesh.load_scene(io.BytesIO(sc.export(file_type="glb")), file_type="glb", process=False)
                    tr, gn = rl.graph["n"]
                    m2 = rl.geometry[gn].copy()
                    g32 = strict_mesh_gate(m2, spp, float(h), precision="float32")
                    w = m2.copy()
                    w.apply_transform(tr)
                    gw = strict_mesh_gate(w, affinity.translate(spp, xoff=origin[0], yoff=origin[1]), float(h), precision="float32")
                    mesh_ok.append({"float64": g64["pass"], "float32_local": g32["pass"], "float32_world": gw["pass"],
                                    "failures": g64["failures"] + g32["failures"] + gw["failures"], "triangles": int(len(m.faces))})
                row["mesh_gates"] = mesh_ok
                row["end_to_end_pass"] = bool(rep.get("pass_")) and all(x["float64"] and x["float32_local"] and x["float32_world"] for x in mesh_ok)
                row["outcome"] = ("ledgered_fragment" if rep.get("ledgered") else "meshed" if row["end_to_end_pass"] else "FAIL")
                rows.append(row)
    out = {"evaluated_failing_parts": len(rows), "outcomes": {k: sum(1 for r in rows if r["outcome"] == k) for k in ("meshed", "ledgered_fragment", "FAIL")},
           "rows": rows}
    (REPO / "data/ntw/terrain/fallback_eval.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({"evaluated": out["evaluated_failing_parts"], "outcomes": out["outcomes"]}, indent=1))
    for r in rows:
        print(r["id"], r["outcome"], {k: r["fallback"].get(k) for k in ("hausdorff_m", "area_delta_m2", "holes_before", "holes_after", "failures", "reason")},
              r.get("accepted_gate_on_snapped"))


if __name__ == "__main__":
    main()
