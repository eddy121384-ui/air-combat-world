"""Greybox cleanup pass — derived presentation tile (DOES NOT touch source truth).

Why this file exists (narrow scope):
  - tools/compiler/build_tile.py merges ALL LayerA buildings into ONE mesh with
    ONE white material -> reads as one uniform pile at flight speed.
  - This script re-exports the SAME WorldModel footprints/positions/heights
    into a PRESENTATION-ONLY GLB with deterministic visual grouping:
      low  (h <= 20m): light grey
      mid  (20 < h <= 60m): medium grey
      high (h > 60m): darker tower tone
      + ground plane (flat dark, 2600x2600m at y=-0.2m, closes street/block gaps)
      + hero Taipei 101 placeholder (unchanged form, 508m, warm accent)
  - Source files untouched: sample_buildings.geojson, worldmodel_sample.json,
    build_tile.py, export_glb.py, geo.py, worldmodel.py.
  - Reversible: delete the *_greybox.glb + report to revert. Re-runnable.
  - Mobile-safe: 5 opaque flat materials, no textures, no transparency,
    no Lumen/Nanite/VSM, +4 draw calls vs v0 (1 -> 5 meshes).

Usage: python tools/compiler/build_greybox_tile.py
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import extrude, triangulate  # noqa: E402  (reuse, do not fork logic)
from worldmodel import TAIPEI_101_LONLAT, lonlat_to_enu  # noqa: E402
from build_tile import placeholder_tower, PLACEHOLDER_HEIGHT_M  # noqa: E402

LOW_MAX = 20.0
MID_MAX = 60.0

COLORS = {
    "layerA_low": (0.87, 0.88, 0.90, 1.0),
    "layerA_mid": (0.62, 0.63, 0.66, 1.0),
    "layerA_high": (0.30, 0.31, 0.34, 1.0),
    "ground_plane": (0.55, 0.51, 0.44, 1.0),
    "hero_taipei101_placeholder": (0.85, 0.55, 0.20, 1.0),
}


def write_glb_multi(path: str, meshes: list[dict]) -> None:
    """Minimal GLB 2.0 writer with one material PER MESH (same layout as export_glb).

    meshes: [{name, positions:[f], normals:[f], indices:[i], color:(r,g,b,a)}]
    """
    blob = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    gl_meshes: list[dict] = []
    materials: list[dict] = []

    def push(data: bytes) -> int:
        off = len(blob)
        blob.extend(data)
        while len(blob) % 4:
            blob.append(0)
        return off

    for mi, m in enumerate(meshes):
        pos_b = struct.pack(f"<{len(m['positions'])}f", *m["positions"])
        nrm_b = struct.pack(f"<{len(m['normals'])}f", *m["normals"])
        idx_b = struct.pack(f"<{len(m['indices'])}I", *m["indices"])
        xs = m["positions"][0::3]
        ys = m["positions"][1::3]
        zs = m["positions"][2::3]
        minx, maxx = min(xs), max(xs)
        minz, maxz = min(zs), max(zs)
        sx = (maxx - minx) or 1.0
        sz = (maxz - minz) or 1.0
        uvs = [v for pair in zip([(x - minx) / sx for x in xs],
                                 [(z - minz) / sz for z in zs]) for v in pair]
        uv_b = struct.pack(f"<{len(uvs)}f", *uvs)
        p_off, n_off = push(pos_b), push(nrm_b)
        uv_off, i_off = push(uv_b), push(idx_b)

        p_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": p_off, "byteLength": len(pos_b)})
        n_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": n_off, "byteLength": len(nrm_b)})
        uv_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": uv_off, "byteLength": len(uv_b)})
        i_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": i_off, "byteLength": len(idx_b)})
        p_ai = len(accessors)
        accessors.append({"bufferView": p_vi, "componentType": 5126, "count": len(xs),
                          "type": "VEC3", "min": [min(xs), min(ys), min(zs)],
                          "max": [max(xs), max(ys), max(zs)]})
        n_ai = len(accessors)
        accessors.append({"bufferView": n_vi, "componentType": 5126,
                          "count": len(xs), "type": "VEC3"})
        uv_ai = len(accessors)
        accessors.append({"bufferView": uv_vi, "componentType": 5126,
                          "count": len(xs), "type": "VEC2"})
        i_ai = len(accessors)
        accessors.append({"bufferView": i_vi, "componentType": 5125,
                          "count": len(m["indices"]), "type": "SCALAR"})
        gl_meshes.append({"name": m["name"], "primitives": [{
            "attributes": {"POSITION": p_ai, "NORMAL": n_ai, "TEXCOORD_0": uv_ai},
            "indices": i_ai, "material": mi}]})
        c = m["color"]
        materials.append({"name": m["name"] + "_mat",
                          "pbrMetallicRoughness": {"baseColorFactor": list(c),
                                                   "metallicFactor": 0.0,
                                                   "roughnessFactor": 0.9}})

    doc = {
        "asset": {"version": "2.0", "generator": "air-combat-world greybox-cleanup v1"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(gl_meshes)))}],
        "nodes": [{"mesh": i, "name": m["name"]} for i, m in enumerate(meshes)],
        "meshes": gl_meshes,
        "materials": materials,
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    j = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    while len(j) % 4:
        j += b" "
    total = 12 + 8 + len(j) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(j), 0x4E4F534A))
        f.write(j)
        f.write(struct.pack("<II", len(blob), 0x004E4942))
        f.write(blob)


def bucket(height_m: float) -> str:
    if height_m <= LOW_MAX:
        return "layerA_low"
    if height_m <= MID_MAX:
        return "layerA_mid"
    return "layerA_high"


def ground_quad(cx: float = -100.0, cz: float = -94.0,
                size: float = 2600.0, y: float = -0.2) -> tuple[list, list, list]:
    """Single quad at y, DOUBLE-SIDED (up + down triangles).

    Why double-sided: the v1 single-sided quad never rendered from above in
    UE (winding-convention mismatch somewhere between our writer and
    Interchange — buildings render, the lone ground quad did not). 4 tris
    total is zero perf cost and renders from every viewpoint, above or below.
    Y-up meters. Center covers LayerA span + margin.
    """
    h = size / 2.0
    x0, x1 = cx - h, cx + h
    z0, z1 = cz - h, cz + h
    pos = [x0, y, z0, x1, y, z0, x1, y, z1,   # up face
           x0, y, z0, x1, y, z1, x0, y, z1,
           x0, y, z0, x0, y, z1, x1, y, z1,   # down face (reversed)
           x0, y, z0, x1, y, z1, x1, y, z0]
    nrm = [0.0, 1.0, 0.0] * 6 + [0.0, -1.0, 0.0] * 6
    return pos, nrm, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    gen = repo / "data/generated/taipei"
    wm = json.loads((gen / "worldmodel_sample.json").read_text(encoding="utf-8"))

    buckets: dict[str, dict] = {
        "layerA_low": {"pos": [], "nrm": [], "idx": [], "buildings": 0},
        "layerA_mid": {"pos": [], "nrm": [], "idx": [], "buildings": 0},
        "layerA_high": {"pos": [], "nrm": [], "idx": [], "buildings": 0},
    }
    skip_reasons: dict[str, int] = {}
    extruded_total = 0

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
                bk = buckets[bucket(b["height_m"])]
                base = len(bk["pos"]) // 3
                bk["pos"].extend(p)
                bk["nrm"].extend(n)
                bk["idx"].extend(i + base for i in ix)
                wrote_any = True
        if wrote_any:
            buckets[bucket(b["height_m"])]["buildings"] += 1
            extruded_total += 1
        else:
            skip_reasons["building_fully_skipped"] = skip_reasons.get("building_fully_skipped", 0) + 1

    # Hero: identical construction to build_tile.py (form + 508m + anchor untouched).
    lon0, lat0 = wm["local_frame"]["origin_lonlat"]
    cx, cy = lonlat_to_enu(*TAIPEI_101_LONLAT, lon0, lat0)
    sup = [b for b in wm["buildings"] if b["suppressed"]]
    biggest = max((max(p["area_m2"] for p in b["polygons"]) for b in sup), default=900.0)
    half = min(max(math.sqrt(biggest) / 2.0, 20.0), 45.0)
    hp, hn, hi = placeholder_tower(cx, cy, half)
    assert abs(max(hp[1::3]) - PLACEHOLDER_HEIGHT_M) < 1e-6, "hero must stay 508m"

    gp, gn, gi = ground_quad()

    meshes = []
    for name in ("layerA_low", "layerA_mid", "layerA_high"):
        bk = buckets[name]
        meshes.append({"name": name, "positions": bk["pos"], "normals": bk["nrm"],
                       "indices": bk["idx"], "color": COLORS[name]})
    meshes.append({"name": "ground_plane", "positions": gp, "normals": gn,
                   "indices": gi, "color": COLORS["ground_plane"]})
    meshes.append({"name": "hero_taipei101_placeholder", "positions": hp, "normals": hn,
                   "indices": hi, "color": COLORS["hero_taipei101_placeholder"]})

    out = gen / "xinyi_tile_2km_greybox.glb"
    write_glb_multi(str(out), meshes)

    verts = sum(len(m["positions"]) // 3 for m in meshes)
    report = {
        "tile": "xinyi_2km_greybox_v1",
        "source_worldmodel": "worldmodel_sample.json (untouched)",
        "buckets": {k: {"buildings": v["buildings"],
                        "verts": len(v["pos"]) // 3,
                        "tris": len(v["idx"]) // 3} for k, v in buckets.items()},
        "extruded_total": extruded_total,
        "skip_reasons": skip_reasons,
        "thresholds_m": {"low_max": LOW_MAX, "mid_max": MID_MAX},
        "colors": {k: list(v) for k, v in COLORS.items()},
        "hero": {"height_m": PLACEHOLDER_HEIGHT_M, "anchor_enu": [cx, cy],
                 "base_half_m": half},
        "ground": {"size_m": 2600.0, "center_xz": [-100.0, -94.0], "y_m": -0.2},
        "vertices": verts,
        "meshes": [m["name"] for m in meshes],
        "materials": 5,
        "mobile_notes": "5 opaque flat materials, no textures/transparency/Lumen/Nanite/VSM",
        "glb": str(out),
    }
    (gen / "xinyi_tile_2km_greybox.report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
