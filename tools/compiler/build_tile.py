"""Phase 3+4 — build the 2 km Xinyi massing tile + 101 hero placeholder.

Layer A: all non-suppressed WorldModel buildings merged into ONE mesh
         (white/grey, flat roofs — v0 validates position/footprint/height/scale).
Layer C: suppressed 101 footprint -> placeholder tower box at its centroid,
         footprint-scale base, 508 m height (real 101 height, validates scale).
No Blender in this round: direct WorldModel -> GLB. Headless + rerunnable.

Usage: python tools/compiler/build_tile.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from geo import extrude, triangulate
from export_glb import write_glb

PLACEHOLDER_HEIGHT_M = 508.0  # real Taipei 101 height -> validates real-world scale


def placeholder_tower(cx: float, cy: float, base_half: float = 30.0) -> tuple[list, list, list]:
    """Simple stepped tower: wide base + shaft + spire block. Y-up meters."""
    boxes = [
        (-base_half, 0.0, -base_half, base_half, 60.0, base_half),       # podium
        (-base_half * 0.55, 60.0, -base_half * 0.55,
         base_half * 0.55, 380.0, base_half * 0.55),                      # shaft
        (-6.0, 380.0, -6.0, 6.0, PLACEHOLDER_HEIGHT_M, 6.0),              # crown/spire
    ]
    pos, nrm, idx = [], [], []

    for (x0, y0, z0, x1, y1, z1) in boxes:
        X0, X1 = cx + x0, cx + x1
        Z0, Z1 = -cy + z0, -cy + z1  # game z = -enu_y
        v = [(X0, y0, Z0), (X1, y0, Z0), (X1, y0, Z1), (X0, y0, Z1),
             (X0, y1, Z0), (X1, y1, Z0), (X1, y1, Z1), (X0, y1, Z1)]
        # bottom, top, 4 sides (outward winding)
        faces = [(0, 2, 1), (0, 3, 2),
                 (4, 5, 6), (4, 6, 7),
                 (0, 1, 5), (0, 5, 4),
                 (1, 2, 6), (1, 6, 5),
                 (2, 3, 7), (2, 7, 6),
                 (3, 0, 4), (3, 4, 7)]
        base = len(pos) // 3
        for (a, c, d) in faces:
            p1, p2, p3 = v[a], v[c], v[d]
            ux, uy, uz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
            vx, vy, vz = p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            l = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            for p in (p1, p2, p3):
                pos.extend(p)
                nrm.extend([nx / l, ny / l, nz / l])
        idx.extend(range(base, base + 36))
    return pos, nrm, idx


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    gen = repo / "data/generated/taipei"
    wm = json.loads((gen / "worldmodel_sample.json").read_text(encoding="utf-8"))

    layer_a_pos, layer_a_nrm, layer_a_idx = [], [], []
    extruded_ids: list[str] = []
    skip_reasons: dict[str, int] = {}
    for b in wm["buildings"]:
        if b["suppressed"]:
            continue
        wrote_any = False
        for poly in b["polygons"]:
            for ring, tris in triangulate([poly["footprint_enu"]]):
                if not tris:
                    key = ("zero_area" if len(ring) < 3 else "self_intersecting")
                    skip_reasons[key] = skip_reasons.get(key, 0) + 1
                    continue
                p, n, ix = extrude(ring, tris, b["height_m"])
                base = len(layer_a_pos) // 3
                layer_a_pos.extend(p)
                layer_a_nrm.extend(n)
                layer_a_idx.extend(i + base for i in ix)
                wrote_any = True
        if wrote_any:
            extruded_ids.append(b["id"])
        else:
            skip_reasons["building_fully_skipped"] = skip_reasons.get("building_fully_skipped", 0) + 1

    hero = wm["hero_match"]
    hero_mesh = None
    anchor = None
    if hero["matched_count"]:
        # Anchor the placeholder at the KNOWN hero coordinates (not at an
        # artifact centroid — WFS hero records include degenerate points).
        from worldmodel import TAIPEI_101_LONLAT, lonlat_to_enu
        lon0, lat0 = wm["local_frame"]["origin_lonlat"]
        cx, cy = lonlat_to_enu(*TAIPEI_101_LONLAT, lon0, lat0)
        anchor = [cx, cy]
        sup = [b for b in wm["buildings"] if b["suppressed"]]
        biggest = max(
            (max(p["area_m2"] for p in b["polygons"]) for b in sup),
            default=900.0,
        )
        half = min(max(math.sqrt(biggest) / 2.0, 20.0), 45.0)
        hp, hn, hi = placeholder_tower(cx, cy, half)
        hero_mesh = {"name": "hero_taipei101_placeholder", "positions": hp,
                     "normals": hn, "indices": hi}

    meshes = [{"name": "layerA_city_massing", "positions": layer_a_pos,
               "normals": layer_a_nrm, "indices": layer_a_idx}]
    if hero_mesh:
        meshes.append(hero_mesh)
    out = gen / "xinyi_tile_2km.glb"
    write_glb(str(out), meshes)

    report = {
        "tile": "xinyi_2km",
        "layer_a_buildings_extruded": len(extruded_ids),
        "layer_a_skip_reasons": skip_reasons,
        "suppressed_ids": [b["id"] for b in wm["buildings"] if b["suppressed"]],
        "hero_placeholder": hero_mesh["name"] if hero_mesh else None,
        "hero_anchor_enu": anchor,
        "vertices": len(layer_a_pos) // 3 + (len(hero_mesh["positions"]) // 3 if hero_mesh else 0),
        "glb": str(out),
    }
    (gen / "xinyi_tile_2km.report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "suppressed_ids"}, indent=2))
    print(f"suppressed: {report['suppressed_ids']}")


if __name__ == "__main__":
    main()
