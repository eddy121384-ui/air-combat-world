"""Decorate the accepted 25 Xinyi runtime tiles with look-dev vertex data.

Geometry contract
-----------------
This is a *representation* stage downstream of the accepted contract. For every
tile the output triangle soup is bit-identical to the accepted runtime tile
(`build_contract.build_runtime_tile_glbs`): same triangles, same order, same
float32 corner positions. The script fails closed if that is not true.

What changes is vertex *sharing* and vertex *attributes*:

- The accepted runtime GLB carries POSITION only and shares vertices between
  roofs and walls. Engines then invent smoothed normals across 90-degree eaves,
  which is a large part of why the whitebox reads as "GIS". Here every corner
  gets its planar face normal and vertices are welded only where all
  attributes agree.
- TEXCOORD_0  walls: (perimeter metres along the footprint ring, metres above
              the building's surveyed ground) -> exact per-wall window grids
              that stay continuous around corners.
              roofs/soffits: tile-local (east, north) metres.
- TEXCOORD_1  (record height_m, visual floor height m)  [real WFS data]
- TEXCOORD_2  packed RGBA8 (gltf_writer.pack_rgba8; decode xc_unpack):
              R = archetype * 16 + variant
              G = appearance seed (per building group)
              B = weathering 0..255
              A = flags (bit0 core district, bit1 group anchor, bit2 podium part,
                         bit3 rooftop structure)

Building groups
---------------
The WFS models one real building as several height-zone records. Records are
grouped (union-find) so a tower and its podium / stair cores share one
archetype, palette and floor rhythm. Equal-sized row houses stay separate.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))

from gltf_writer import pack_rgba8, read_glb_primitives, write_glb  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
TILES = REPO / "unreal/Saved/XinyiV2Full/run-01/tiles"
Z_OFFSETS = REPO / "unreal/Saved/XinyiTerrainV0/building_z_offsets.json"
CONTRACT = REPO / "unreal/Saved/XinyiUnrealV2Contract"
OUT = REPO / "unreal/Saved/XinyiLook"

ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM = range(6)
ARCH_NAMES = ["low", "walkup", "huaxia", "res_tower", "office_glass", "commercial_podium"]

FLAG_CORE, FLAG_ANCHOR, FLAG_PODIUM, FLAG_ROOFTOP = 1, 2, 4, 8

# Xinyi Special District (信義計畫區), from OSM boundary roads in Xinyi ENU:
# 基隆路 (W, diagonal) / 忠孝東路 (N) / 松德路 (E) / 信義路 (S).
CORE_DISTRICT = Polygon([(-590, -10), (-85, 905), (1000, 1010), (1110, 720), (930, -10)])
TAIPEI101_ENU = (-59.58, 74.40)


def sha_byte(text: str, k: int = 0) -> int:
    return hashlib.sha256(text.encode()).digest()[k]


# --------------------------------------------------------------------------
# Grouping + classification
# --------------------------------------------------------------------------

class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, child, parent):
        a, b = self.find(child), self.find(parent)
        if a != b:
            self.p[a] = b


def classify(wm, props):
    feats = [b for b in wm["buildings"] if not b["suppressed"]]
    polys = []
    for b in feats:
        parts = [Polygon(p["footprint_enu"], p.get("holes_enu") or []) for p in b["polygons"]]
        parts = [q if q.is_valid else q.buffer(0) for q in parts]
        polys.append(parts[0] if len(parts) == 1 else _union(parts))
    areas = np.array([p.area for p in polys])
    tree = STRtree(polys)
    uf = UF(len(feats))
    order = np.argsort(areas, kind="stable")
    for i in order:
        pi = polys[i]
        if pi.is_empty:
            continue
        cand = tree.query(pi.buffer(0.3))
        best, best_area = None, -1.0
        per = max(pi.length, 1e-6)
        for j in cand:
            if j == i or areas[j] <= areas[i]:
                continue
            shared = pi.buffer(0.3).intersection(polys[j].boundary).length
            small = areas[i] < 40.0
            nested = areas[i] < 0.6 * areas[j] and shared >= 0.45 * per
            if (small and shared > 0.5) or nested:
                if areas[j] > best_area:
                    best, best_area = j, areas[j]
        if best is not None:
            uf.join(i, best)

    groups = defaultdict(list)
    for i in range(len(feats)):
        groups[uf.find(i)].append(i)

    records = {}
    stats = Counter()
    for root, members in groups.items():
        heights = [feats[m]["height_m"] for m in members]
        anchor = members[int(np.argmax([heights[k] * 1e6 + areas[m] for k, m in enumerate(members)]))]
        ap = props[feats[anchor]["id"]]
        floors = int(ap.get("floors") or max(1, round(feats[anchor]["height_m"] / 3.2)))
        height = float(feats[anchor]["height_m"])
        fh = height / max(floors, 1)
        if not (2.6 <= fh <= 6.0):
            floors = max(1, round(height / 3.3))
            fh = min(6.0, max(2.6, height / floors))
        total_area = float(sum(areas[m] for m in members))
        c = polys[anchor].representative_point()
        core = CORE_DISTRICT.contains(c)
        d101 = math.dist((c.x, c.y), TAIPEI101_ENU)
        gid = min(feats[m]["id"] for m in members)
        seed = sha_byte(gid)

        if floors <= 3:
            arch = ARCH_LOW
            if total_area >= 2500 and fh >= 4.5:
                arch = ARCH_PODIUM
        elif floors <= 5:
            arch = ARCH_WALKUP
            if core or (total_area >= 1500 and fh >= 4.2):
                arch = ARCH_PODIUM if fh >= 4.2 else ARCH_HUAXIA
        elif floors <= 12:
            arch = ARCH_HUAXIA
            if total_area >= 2500 and fh >= 4.2:
                arch = ARCH_PODIUM
        elif floors <= 24:
            arch = ARCH_RESTOWER
            if core and (fh >= 3.7 or total_area >= 1500):
                arch = ARCH_OFFICE
        else:
            arch = ARCH_OFFICE if (fh >= 3.55 or (core and total_area >= 700)) else ARCH_RESTOWER

        # Weathering: old stock outside the planned district weathers hardest.
        base_w = {ARCH_LOW: 170, ARCH_WALKUP: 190, ARCH_HUAXIA: 150, ARCH_RESTOWER: 80,
                  ARCH_OFFICE: 30, ARCH_PODIUM: 70}[arch]
        if core:
            base_w = int(base_w * 0.55)
        weather = int(max(0, min(255, base_w + (seed % 64) - 32)))
        stats[ARCH_NAMES[arch]] += 1

        for m in members:
            b = feats[m]
            flags = (FLAG_CORE if core else 0)
            if m == anchor:
                flags |= FLAG_ANCHOR
            elif b["height_m"] < 0.8 * height:
                flags |= FLAG_PODIUM
            elif areas[m] < 40.0 and b["height_m"] > height - 8.0:
                flags |= FLAG_ROOFTOP
            records[b["id"]] = {
                "group": gid,
                "archetype": arch,
                "variant": sha_byte(b["id"], 1) & 15,
                "seed": seed,
                "weather": weather,
                "flags": flags,
                "height_m": float(b["height_m"]),
                "floor_h": float(fh),
                "core": bool(core),
                "d101_m": float(d101),
            }
    return records, stats, len(groups)


def _union(parts):
    from shapely.ops import unary_union
    return unary_union(parts)


# --------------------------------------------------------------------------
# Per-component attribute computation
# --------------------------------------------------------------------------

def ring_params(mesh_v: np.ndarray, faces: np.ndarray, up: np.ndarray):
    """Map (x,z) float32 keys of the top-cap boundary loops to perimeter params."""
    top = faces[up]
    edges = np.concatenate([top[:, [0, 1]], top[:, [1, 2]], top[:, [2, 0]]])
    key = np.sort(edges, axis=1)
    uniq, inv, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    boundary = edges[counts[inv.reshape(-1)] == 1]
    nxt = {}
    for a, b in boundary:
        nxt.setdefault(int(a), []).append(int(b))
    params = {}  # xz key -> list of (param, loop_len)
    visited = set()
    for start in sorted(nxt):
        if start in visited:
            continue
        loop = [start]
        visited.add(start)
        cur = start
        while True:
            outs = [n for n in nxt.get(cur, []) if n not in visited or n == start]
            if not outs:
                break
            n = outs[0]
            if n == start:
                break
            loop.append(n)
            visited.add(n)
            cur = n
        pts = mesh_v[loop][:, [0, 2]].astype(np.float64)
        seg = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
        total = float(seg.sum())
        for vi, u in zip(loop, cum):
            k = mesh_v[vi][[0, 2]].astype(np.float32).tobytes()
            params.setdefault(k, []).append((float(u), total))
    return params


def component_attributes(mesh: trimesh.Trimesh, ground_offset: float, rec: dict, tile_origin):
    """Return per-corner arrays (T*3 rows) for one validated component mesh."""
    v = np.asarray(mesh.vertices, dtype=np.float64)
    f = np.asarray(mesh.faces, dtype=np.int64)
    p = v[f]  # (T,3,3) game frame, before ground translation
    fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    up = fn[:, 1] > 0.7
    down = fn[:, 1] < -0.7
    wall = ~(up | down)

    T = len(f)
    uv0 = np.zeros((T, 3, 2), dtype=np.float64)
    # roofs + soffits: tile-local east/north metres
    uv0[:, :, 0] = p[:, :, 0]
    uv0[:, :, 1] = -p[:, :, 2]

    params = ring_params(v, f, up)
    for t in np.nonzero(wall)[0]:
        us, lens = [], []
        for c in range(3):
            k = v[f[t, c]][[0, 2]].astype(np.float32).tobytes()
            cands = params.get(k)
            if not cands:
                us.append(None)
                lens.append(None)
                continue
            us.append(cands)
            lens.append(cands[0][1])
        # resolve ambiguous keys against the other corners
        chosen = []
        ref = next((c[0][0] for c in us if c), 0.0)
        for c in us:
            if not c:
                chosen.append((ref, 0.0))
                continue
            best = min(c, key=lambda pl: abs(pl[0] - ref))
            chosen.append(best)
        u = np.array([c[0] for c in chosen])
        L = max((c[1] for c in chosen), default=0.0)
        if L > 0 and u.max() - u.min() > 0.5 * L:
            u = np.where(u < 0.5 * L, u + L, u)
        uv0[t, :, 0] = u
        uv0[t, :, 1] = p[t, :, 1]  # metres above surveyed ground (pre-offset)

    uv1 = np.empty((T, 3, 2), dtype=np.float64)
    uv1[:, :, 0] = rec["height_m"]
    uv1[:, :, 1] = rec["floor_h"]
    col = np.empty((T, 3, 4), dtype=np.uint8)
    col[:, :] = (rec["archetype"] * 16 + rec["variant"], rec["seed"], rec["weather"], rec["flags"])
    normals = np.repeat(fn[:, None, :], 3, axis=1)
    return normals, uv0, uv1, col


def weld(pos, nrm, uv0, uv1, col):
    """Weld corners whose full attribute rows are bit-identical (deterministic)."""
    rows = np.concatenate([
        pos.astype(np.float32).view(np.uint32),
        nrm.astype(np.float32).view(np.uint32),
        uv0.astype(np.float32).view(np.uint32),
        uv1.astype(np.float32).view(np.uint32),
        col.astype(np.uint32),
    ], axis=1)
    uniq, first, inv = np.unique(rows, axis=0, return_index=True, return_inverse=True)
    # keep first-appearance order for stable, cache-friendly output
    order = np.argsort(first, kind="stable")
    remap = np.empty_like(order)
    remap[order] = np.arange(len(order))
    idx = remap[inv.reshape(-1)].reshape(-1, 3).astype(np.uint32)
    sel = first[order]
    return pos[sel], nrm[sel], uv0[sel], uv1[sel], col[sel], idx


# --------------------------------------------------------------------------

def build(out_dir: Path):
    contract = json.loads((CONTRACT / "xinyi_unreal_v2_contract.json").read_text())
    z_offsets = json.loads(Z_OFFSETS.read_text())
    z_offsets = z_offsets["offsets_m"]
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    records, arch_stats, group_count = classify(wm, props)

    tiles_out = out_dir / "tiles"
    tiles_out.mkdir(parents=True, exist_ok=True)
    manifest = []
    sidecar = []
    import re
    bid_re = re.compile(r"^(tp_building_height\.\d+)")

    for row in contract["tiles"]:
        tile = row["tile"]
        scene = trimesh.load_scene(TILES / row["building_glb"], file_type="glb", process=False)
        P, N, U0, U1, C = [], [], [], [], []
        comp = 0
        for node in sorted(scene.graph.nodes_geometry):
            bid = bid_re.match(str(node)).group(1)
            _, gname = scene.graph[node]
            mesh = scene.geometry[gname]
            rec = records[bid]
            nrm, uv0, uv1, col = component_attributes(mesh, float(z_offsets[bid]), rec, row["origin_enu_m"])
            m2 = mesh.copy()
            m2.apply_translation([0.0, float(z_offsets[bid]), 0.0])
            corners = np.asarray(m2.vertices, dtype=np.float64)[np.asarray(m2.faces)]
            P.append(corners.reshape(-1, 3))
            N.append(nrm.reshape(-1, 3))
            U0.append(uv0.reshape(-1, 2))
            U1.append(uv1.reshape(-1, 2))
            C.append(col.reshape(-1, 4))
            comp += 1
        # float32 exactly as the accepted runtime GLB serialises it
        pos = np.concatenate(P).astype(np.float32)
        nrm = np.concatenate(N).astype(np.float32)
        uv0 = np.concatenate(U0).astype(np.float32)
        uv1 = np.concatenate(U1).astype(np.float32)
        col = np.concatenate(C).astype(np.uint8)
        wpos, wnrm, wuv0, wuv1, wcol, idx = weld(pos, nrm, uv0, uv1, col)

        # ---- fail-closed geometry equivalence against the accepted runtime tile
        ref = read_glb_primitives(CONTRACT / "building_runtime_tiles" / row["runtime_building_glb"])[0]
        ref_soup = ref["position"][ref["indices"].reshape(-1)]
        look_soup = wpos[idx.reshape(-1)]
        if ref_soup.shape != look_soup.shape or not np.array_equal(
            ref_soup.view(np.uint32), look_soup.view(np.uint32)
        ):
            raise RuntimeError(f"look tile triangle soup differs from accepted runtime tile {tile}")

        name = f"xinyi_look_{tile}.glb"
        write_glb(tiles_out / name, [{
            "name": "XinyiCity",
            "positions": wpos, "normals": wnrm, "uv0": wuv0, "uv1": wuv1, "uv2": pack_rgba8(wcol),
            "indices": idx, "base_color": [0.7, 0.7, 0.7, 1.0],
        }], mesh_name=f"SM_XinyiLook_{tile}")
        manifest.append({
            "tile": tile,
            "path": name,
            "sha256": hashlib.sha256((tiles_out / name).read_bytes()).hexdigest(),
            "components": comp,
            "triangles": int(len(idx)),
            "vertices_accepted": int(len(ref["position"])),
            "vertices_look": int(len(wpos)),
            "accepted_runtime_sha256": row["runtime_building_sha256"],
            "triangle_soup_bit_identical": True,
            "origin_enu_m": row["origin_enu_m"],
            "expected_ue_translation_cm": row["expected_ue_translation_cm"],
        })
        print(f"{tile}: {len(idx)} tris, verts {len(ref['position'])} -> {len(wpos)}", flush=True)

    for bid, rec in sorted(records.items()):
        sidecar.append({"building_id": bid, **{k: rec[k] for k in ("group", "archetype", "variant", "seed",
                                                                   "weather", "flags", "floor_h")},
                        "archetype_name": ARCH_NAMES[rec["archetype"]]})
    with gzip.open(out_dir / "look_buildings.jsonl.gz", "wt", encoding="utf-8", compresslevel=9) as fh:
        for r in sidecar:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    report = {
        "status": "PASS_LOOK_TILES",
        "tiles": manifest,
        "building_groups": group_count,
        "archetype_group_counts": dict(sorted(arch_stats.items())),
        "totals": {
            "triangles": int(sum(t["triangles"] for t in manifest)),
            "vertices_accepted": int(sum(t["vertices_accepted"] for t in manifest)),
            "vertices_look": int(sum(t["vertices_look"] for t in manifest)),
        },
        "contract": "triangle soup bit-identical to accepted runtime tiles; attributes are look-dev only",
    }
    (out_dir / "look_tiles.report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("building_groups", "archetype_group_counts", "totals")}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
