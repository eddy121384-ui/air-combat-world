"""Landmark hero roofs (look-only), from tools/lookdev/landmarks.json.

Some Taipei landmarks are surveyed only to their base: the WFS record for the
Sun Yat-sen Memorial Hall stops at ~9.8 m, while its yellow glazed hip roof
rises to ~30.4 m. This adds the roof as a separate hero mesh sitting on the
surveyed record (like the Taipei 101 hero) — the record itself is untouched.

Roof: hip roof over the record's minimum rotated rectangle grown by the eave
overhang, ridge along the long axis, eave corners lifted (翼角起翹).
Vertex contract = M_XinyiCity (UV1 = (height, 3.3), UV2 packed civic/variant).

Output: unreal/Saved/XinyiLook/hero/landmark_roofs.glb (+ .json), ENU-absolute
game frame, actor at the world origin.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import build_worldmodel, lonlat_to_enu  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
OUT = REPO / "unreal/Saved/XinyiLook/hero"
ARCH_CIVIC = 6


def hip_roof(rect, z0, top, lift):
    """rect: 4 corners CCW (ENU). Returns list of (tri corners)."""
    c = np.asarray(rect, float)
    e01, e12 = np.linalg.norm(c[1] - c[0]), np.linalg.norm(c[2] - c[1])
    if e12 > e01:                      # make c0->c1 the long side
        c = np.roll(c, -1, axis=0)
        e01, e12 = e12, e01
    u = (c[1] - c[0]) / e01
    centre = c.mean(axis=0)
    half_ridge = max(0.0, (e01 - e12) * 0.5)
    r0 = np.append(centre - u * half_ridge, top)
    r1 = np.append(centre + u * half_ridge, top)
    k = [np.append(p, z0 + lift) for p in c]
    return [
        (k[0], k[1], r1), (k[0], r1, r0),       # long side
        (k[1], k[2], r1),                       # end
        (k[2], k[3], r0), (k[2], r0, r1),       # long side
        (k[3], k[0], r0),                       # end
    ], k


def main():
    cfg = json.loads((HERE / "landmarks.json").read_text(encoding="utf-8"))
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    lon0, lat0 = wm["local_frame"]["origin_lonlat"]
    pos, nrm, uv0, uv1, uv2, idx = [], [], [], [], [], []
    report = []
    for lm in cfg["landmarks"]:
        hr = lm.get("hero_roof")
        if not hr:
            continue
        ex, ey = lonlat_to_enu(lm["lonlat"][0], lm["lonlat"][1], lon0, lat0)
        best = None
        for b in wm["buildings"]:
            for p in b["polygons"]:
                cx, cy = p["centroid_enu"]
                if math.dist((cx, cy), (ex, ey)) <= lm["radius_m"] and p["area_m2"] >= lm["min_area_m2"]:
                    if best is None or p["area_m2"] > best[1]["area_m2"]:
                        best = (b, p)
        if best is None:
            raise RuntimeError("landmark %s: no surveyed record matched" % lm["name"])
        b, p = best
        ground = float(props[b["id"]]["ground_elev_m"])
        z0 = ground + float(b["height_m"])
        top = ground + float(hr["top_m"])
        poly = Polygon(p["footprint_enu"]).buffer(float(hr["overhang_m"]), join_style=2)
        rect = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:4]
        # enforce CCW
        if Polygon(rect).exterior.is_ccw is False:
            rect = rect[::-1]
        tris, eave = hip_roof(rect, z0, top, float(hr["corner_lift_m"]))
        code = (ARCH_CIVIC * 16 + int(lm["variant"]), 97, 40, 0)
        H = top - ground
        for t in tris:
            t = [np.asarray(v, float) for v in t]
            n = np.cross(t[1] - t[0], t[2] - t[0])
            n /= np.linalg.norm(n)
            if n[2] < 0:
                t = [t[0], t[2], t[1]]
                n = -n
            base = len(pos)
            for v in t:
                pos.append(v); nrm.append(n); uv0.append((v[0], v[1])); uv1.append((H, 3.3)); uv2.append(code)
            idx.append((base, base + 1, base + 2))
        # eave fascia + soffit (thin band under the lifted corners)
        for i in range(4):
            a, bb = eave[i], eave[(i + 1) % 4]
            a0, b0 = a - np.array([0, 0, 1.0]), bb - np.array([0, 0, 1.0])
            q = [a0, b0, bb, a]
            n = np.cross(q[1] - q[0], q[3] - q[0]); n /= np.linalg.norm(n)
            base = len(pos)
            for v in q:
                pos.append(v); nrm.append(n); uv0.append((0.0, v[2] - ground)); uv1.append((H, 3.3)); uv2.append(code)
            idx += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        report.append({"name": lm["name"], "record": b["id"], "record_height_m": b["height_m"],
                       "roof_base_m": z0, "roof_top_m": top})
    P = np.asarray(pos, float)
    Nn = np.asarray(nrm, float)
    game = np.column_stack([P[:, 0], P[:, 2], -P[:, 1]]).astype(np.float32)
    gn = np.column_stack([Nn[:, 0], Nn[:, 2], -Nn[:, 1]]).astype(np.float32)
    OUT.mkdir(parents=True, exist_ok=True)
    write_glb(OUT / "landmark_roofs.glb", [{
        "name": "XinyiCity", "positions": game, "normals": gn,
        "uv0": np.asarray(uv0, np.float32), "uv1": np.asarray(uv1, np.float32),
        "uv2": pack_rgba8(np.asarray(uv2, np.uint8)), "indices": np.asarray(idx, np.uint32)}],
        mesh_name="SM_XinyiLandmarkRoofs")
    rep = {"asset": "landmark_roofs.glb", "landmarks": report, "triangles": len(idx),
           "ue_actor_location_cm": [0.0, 0.0, 0.0], "expected_ue_local_bounds": ue_local_bounds_cm(game)}
    (OUT / "landmark_roofs.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
