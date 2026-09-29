"""Build the Taipei-basin backdrop mesh and a preview mesh of the Xinyi terrain.

Backdrop (runtime deliverable)
  The mountains that enclose the basin — Yangmingshan / Qixing (N), the Four
  Beasts and Nangang ridges (SE), the Linkou plateau (W) — are the single
  strongest "this is Taipei" cue after 101 itself. They come from the same MOI
  2025 bare-earth DTM mirror used for Xinyi terrain, sampled at ~150 m. The
  accepted 2.5 km Xinyi Landscape is cut out of the backdrop so the playable
  terrain contract is untouched.

  TEXCOORD_2 (plain floats, varies per vertex so NOT packed):
           x = urban-floor weight (low, flat basin floor), y = forest weight.
  Output: unreal/Saved/XinyiLook/backdrop/taipei_basin_backdrop.glb
          (game frame X=east, Y=up, Z=-north, origin = Xinyi ENU origin)

Xinyi terrain (preview only)
  unreal/Saved/XinyiLook/preview/xinyi_terrain_preview.glb, decoded from the
  accepted 631 x 631 contract heightfield. Unreal keeps using its Landscape.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import enu_origin_from_city_yaml, lonlat_to_enu  # noqa: E402

CITY = REPO / "cities/taipei/city.yaml"
BASIN = REPO / "data/lookdev_cache/basin_dtm_mirror.npz"
CONTRACT = REPO / "unreal/Saved/XinyiUnrealV2Contract"
OUT = REPO / "unreal/Saved/XinyiLook"

STRIDE = 2              # 76 m source cells -> ~152 m backdrop cells
XINYI = (-1500.0, 1000.0, -1000.0, 1500.0)   # accepted Landscape extent (E0,E1,N0,N1)
CUT_MARGIN_M = 150.0    # backdrop quads fully inside (extent - margin) are removed
BACKDROP_SINK_M = 1.5   # keep the backdrop under the Landscape where they overlap


def grid_mesh(E, N, Z, keep_quad):
    h, w = Z.shape
    idx = np.arange(h * w).reshape(h, w)
    a = idx[:-1, :-1]; b = idx[:-1, 1:]; c = idx[1:, 1:]; d = idx[1:, :-1]
    quads = np.stack([a, b, c, d], axis=-1)[keep_quad]
    tris = np.concatenate([quads[:, [0, 2, 1]], quads[:, [0, 3, 2]]])
    pos = np.column_stack([E.ravel(), Z.ravel(), -N.ravel()])  # game frame
    # smooth normals (terrain)
    p = pos[tris]
    fn = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    nrm = np.zeros_like(pos)
    for k in range(3):
        np.add.at(nrm, tris[:, k], fn)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    used = np.unique(tris)
    remap = -np.ones(len(pos), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return pos[used], nrm[used], remap[tris], used


def build_backdrop():
    lon0, lat0 = enu_origin_from_city_yaml(CITY)
    d = np.load(BASIN)
    Zs = d["elevation_m"].astype(np.float64)
    west, south, east, north = [float(v) for v in d["bounds_3857"]]
    rows, cols = Zs.shape
    # cell centres in EPSG:3857
    xs = west + (np.arange(cols) + 0.5) * (east - west) / cols
    ys = north - (np.arange(rows) + 0.5) * (north - south) / rows
    xs, ys = xs[::STRIDE], ys[::STRIDE]
    Z = Zs[::STRIDE, ::STRIDE]
    X, Y = np.meshgrid(xs, ys)
    to_ll = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    lon, lat = to_ll.transform(X, Y)
    E = np.empty_like(lon); Nn = np.empty_like(lat)
    for i in range(lon.shape[0]):
        for j in range(lon.shape[1]):
            E[i, j], Nn[i, j] = lonlat_to_enu(float(lon[i, j]), float(lat[i, j]), lon0, lat0)
    Z = np.maximum(Z, 0.0) - BACKDROP_SINK_M

    # cut out the accepted Xinyi Landscape
    e0, e1, n0, n1 = XINYI
    qe = 0.25 * (E[:-1, :-1] + E[:-1, 1:] + E[1:, :-1] + E[1:, 1:])
    qn = 0.25 * (Nn[:-1, :-1] + Nn[:-1, 1:] + Nn[1:, :-1] + Nn[1:, 1:])
    inside = (qe > e0 + CUT_MARGIN_M) & (qe < e1 - CUT_MARGIN_M) & (qn > n0 + CUT_MARGIN_M) & (qn < n1 - CUT_MARGIN_M)
    pos, nrm, tris, used = grid_mesh(E, Nn, Z, ~inside)

    # classification weights
    zf = Z.ravel()[used] + BACKDROP_SINK_M
    slope = 1.0 - nrm[:, 1]
    lap = np.zeros_like(Z)
    lap[1:-1, 1:-1] = Z[1:-1, 1:-1] - 0.25 * (Z[:-2, 1:-1] + Z[2:, 1:-1] + Z[1:-1, :-2] + Z[1:-1, 2:])
    ridge = np.clip(lap.ravel()[used] / 25.0 + 0.5, 0, 1)
    urban = np.clip((45.0 - zf) / 25.0, 0, 1) * np.clip((0.06 - slope) / 0.04, 0, 1)
    forest = np.clip((zf - 25.0) / 40.0, 0, 1) * (1.0 - urban)

    out = OUT / "backdrop"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "taipei_basin_backdrop.glb"
    write_glb(path, [{
        "name": "XinyiBackdrop",
        "positions": pos.astype(np.float32),
        "normals": nrm.astype(np.float32),
        "uv0": np.column_stack([pos[:, 0], -pos[:, 2]]).astype(np.float32),
        "uv2": np.column_stack([urban, forest]).astype(np.float32),
        "indices": tris.astype(np.uint32),
        "base_color": [0.3, 0.4, 0.3, 1.0],
    }], mesh_name="SM_TaipeiBasinBackdrop")
    rep = {
        "asset": path.name,
        "vertices": int(len(pos)),
        "triangles": int(len(tris)),
        "extent_enu_m": [float(pos[:, 0].min()), float(pos[:, 0].max()), float(-pos[:, 2].max()), float(-pos[:, 2].min())],
        "elevation_max_m": float(zf.max()),
        "cutout_enu_m": list(XINYI),
        "cut_margin_m": CUT_MARGIN_M,
        "sink_m": BACKDROP_SINK_M,
        "role": "distant visual backdrop only; accepted Xinyi Landscape is untouched",
        "ue_actor_location_cm": [0.0, 0.0, 0.0],
        "expected_ue_local_bounds": ue_local_bounds_cm(pos),
    }
    (out / "taipei_basin_backdrop.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(rep))


def build_xinyi_terrain_preview():
    c = json.loads((CONTRACT / "xinyi_unreal_v2_contract.json").read_text())
    ls = c["landscape"]
    n = ls["heightmap_size"][0]
    raw = np.fromfile(CONTRACT / "xinyi_moi2025_landscape_631.r16", dtype="<u2").reshape(n, n)
    elev = (raw.astype(np.float64) - 32768.0) * ls["scale_xyz"][2] / 128.0 / 100.0
    e0, n1 = XINYI[0], XINYI[3]
    step = ls["sample_spacing_m"]
    s = 2
    elev = elev[::s, ::s]
    m = elev.shape[0]
    E = e0 + np.arange(m)[None, :] * step * s + np.zeros((m, 1))
    Nn = n1 - np.arange(m)[:, None] * step * s + np.zeros((1, m))
    pos, nrm, tris, _ = grid_mesh(E, Nn, elev, np.ones((m - 1, m - 1), dtype=bool))
    out = OUT / "preview"
    out.mkdir(parents=True, exist_ok=True)
    write_glb(out / "xinyi_terrain_preview.glb", [{
        "name": "XinyiTerrain",
        "positions": pos.astype(np.float32), "normals": nrm.astype(np.float32),
        "uv0": np.column_stack([pos[:, 0], -pos[:, 2]]).astype(np.float32),
        "indices": tris.astype(np.uint32),
    }], mesh_name="XinyiTerrainPreview")
    print("terrain preview", len(pos), len(tris))


if __name__ == "__main__":
    build_backdrop()
    build_xinyi_terrain_preview()
