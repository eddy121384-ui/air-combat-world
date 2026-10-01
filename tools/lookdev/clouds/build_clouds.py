"""Cloud Prototype v0: renderer-agnostic cloud cells + a tileable weather map.

Input:  tools/lookdev/clouds/cloud_state_v0.json   (where / what kind of cloud)
        data/lookdev_cache/basin_dtm_mirror.npz      (orographic placement bias)
Output: unreal/Saved/XinyiLook/clouds/
  clouds_v0.cells.json   every cloud as {archetype, centre ENU, radius, base, top}. This is the
                         renderer-independent product: a volumetric renderer, impostor cards,
                         mobile sprites or gameplay (in-cloud checks) can all consume it.
  clouds_weather_1024.png RGBA8, tileable over tile_m, sampled by the UE volumetric renderer with
                         uv = (UE x, UE y) / tile_m  (UE y = -north), wrap addressing:
                           R = fair-weather cumulus coverage (dome profile, 1 at the cell core)
                           G = cumulus top height, normalised to the renderer layer
                           B = broken-layer coverage
                           A = broken-layer thickness, normalised to the renderer layer
  clouds.report.json

Deterministic (seeded); numpy + stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STATE = HERE / "cloud_state_v0.json"
REVIEW = HERE / "cloud_review_shots.json"
BASIN = REPO / "data/lookdev_cache/basin_dtm_mirror.npz"
CITY = REPO / "cities/taipei/city.yaml"
OUT = REPO / "unreal/Saved/XinyiLook/clouds"
RES = 1024
R_EARTH = 6378137.0


def enu_origin():
    for line in CITY.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("enu_origin:"):
            body = line.split("{", 1)[1].split("}", 1)[0]
            kv = {k.strip(): v.strip() for k, v in (p.split(":", 1) for p in body.split(",") if ":" in p)}
            return float(kv["lon"].strip()), float(kv["lat"].strip())
    raise SystemExit("enu_origin not found in city.yaml")


def elevation_lookup():
    """Bare-earth elevation (m) at ENU points; 0 outside the basin DTM mirror."""
    lon0, lat0 = enu_origin()
    d = np.load(BASIN)
    z = np.maximum(d["elevation_m"].astype(np.float64), 0.0)
    west, south, east, north = [float(v) for v in d["bounds_3857"]]
    rows, cols = z.shape

    def f(e, n):
        lon = lon0 + np.degrees(np.asarray(e) / (R_EARTH * math.cos(math.radians(lat0))))
        lat = lat0 + np.degrees(np.asarray(n) / R_EARTH)
        x = R_EARTH * np.radians(lon)
        y = R_EARTH * np.log(np.tan(math.pi / 4 + np.radians(lat) / 2))
        c = ((x - west) / (east - west) * cols).astype(int)
        r = ((north - y) / (north - south) * rows).astype(int)
        inside = (c >= 0) & (c < cols) & (r >= 0) & (r < rows)
        out = np.zeros(np.shape(c))
        out[inside] = z[r[inside], c[inside]]
        return out
    return f


def wrap(v, t):
    """Wrap into [-t/2, t/2)."""
    return (v + t / 2) % t - t / 2


def stamp(img, ux, wy, radius, px, fn):
    """Apply fn(dist_norm, mask_window_slices) over the wrapped window around (ux, wy)."""
    n = img.shape[0]
    r_px = int(math.ceil(radius / px)) + 2
    cj, ci = int(ux / px), int(wy / px)
    js = np.arange(cj - r_px, cj + r_px + 1)
    is_ = np.arange(ci - r_px, ci + r_px + 1)
    xs = (js + 0.5) * px - ux
    ys = (is_ + 0.5) * px - wy
    d = np.sqrt(xs[None, :] ** 2 + ys[:, None] ** 2) / radius
    fn(np.ix_(is_ % n, js % n), d)


def png_rgba8(path: Path, rgba: np.ndarray):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    st = json.loads(STATE.read_text(encoding="utf-8"))
    rng = np.random.default_rng(st["seed"])
    T = float(st["tile_m"])
    px = T / RES
    elev = elevation_lookup()
    cu, br = st["layers"]
    layer_bottom = float(cu["base_m"])
    layer_top = max(float(cu["top_m"][1]), float(br["base_m"]) + float(br["thickness_m"][1]))
    layer_h = layer_top - layer_bottom

    cells = []
    # --- fair-weather cumulus: clusters placed with an orographic bias ------------------------
    centres = []
    while len(centres) < cu["clusters"]:
        e, n = rng.uniform(-T / 2, T / 2, 2)
        w = 0.35 + cu["orographic_weight"] * min(float(elev(e, n)) / 600.0, 1.0)
        if rng.uniform(0, 0.35 + cu["orographic_weight"]) < w:
            centres.append((e, n))
    area = 0.0
    for ce, cn in centres:
        k = int(rng.integers(cu["cells_per_cluster"][0], cu["cells_per_cluster"][1] + 1))
        for _ in range(k):
            if area / (T * T) >= cu["target_area_fraction"]:
                break
            a = rng.uniform(0, 2 * math.pi)
            s = cu["cluster_radius_m"] * math.sqrt(rng.uniform(0, 1))
            e, n = wrap(ce + s * math.cos(a), T), wrap(cn + s * math.sin(a), T)
            r0, r1 = cu["radius_m"]
            r = math.exp(rng.uniform(math.log(r0), math.log(r1)))
            size = (r - r0) / (r1 - r0)
            t0, t1 = cu["top_m"]
            top = t0 + (t1 - t0) * min(1.0, 0.75 * size + 0.35 * rng.uniform(0, 1) ** 2)
            cells.append({"archetype": cu["archetype"], "centre_enu_m": [round(e, 1), round(n, 1)],
                          "radius_m": round(r, 1), "base_m": cu["base_m"], "top_m": round(top, 1)})
            area += math.pi * r * r * 0.55
    # --- broken layered field: large patches biased toward one sector -------------------------
    bce, bcn = br["bias_center_en_m"]
    for _ in range(br["patches"]):
        e = wrap(bce + rng.normal(0, br["bias_radius_m"] * 0.5), T)
        n = wrap(bcn + rng.normal(0, br["bias_radius_m"] * 0.5), T)
        r = rng.uniform(*br["radius_m"])
        th = rng.uniform(*br["thickness_m"])
        cells.append({"archetype": br["archetype"], "centre_enu_m": [round(e, 1), round(n, 1)],
                      "radius_m": round(r, 1), "base_m": br["base_m"], "top_m": round(br["base_m"] + th, 1)})

    # --- weather map ----------------------------------------------------------------------------
    R = np.zeros((RES, RES)); G = np.zeros((RES, RES)); B = np.zeros((RES, RES)); A = np.zeros((RES, RES))
    for c in cells:
        e, n = c["centre_enu_m"]
        ux, wy = e % T, (-n) % T               # UE plane: x = east, y = -north
        if c["archetype"] == cu["archetype"]:
            tn = (c["top_m"] - layer_bottom) / layer_h

            def f(ix, d, tn=tn):
                prof = np.clip(1.0 - d * d, 0.0, 1.0)
                take = prof > R[ix]
                G[ix] = np.where(take, tn, G[ix])
                R[ix] = np.maximum(R[ix], prof)
        else:
            thn = (c["top_m"] - c["base_m"]) / layer_h

            def f(ix, d, thn=thn):
                prof = np.clip(1.0 - d, 0.0, 1.0) ** 0.6     # flatter, wider sheet
                take = prof > B[ix]
                A[ix] = np.where(take, thn, A[ix])
                B[ix] = np.maximum(B[ix], prof)
        stamp(R, ux, wy, c["radius_m"], px, f)
    rgba = np.stack([R, G, B, A], axis=-1)
    rgba = np.clip(np.round(rgba * 255.0), 0, 255).astype(np.uint8)
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / "clouds_weather_1024.png"
    png_rgba8(png, rgba)

    review = json.loads(REVIEW.read_text(encoding="utf-8"))["shots"]
    at_eye = {}
    for k, s in review.items():
        e, n, z = s["eye"]
        i, j = int(((-n) % T) / px), int((e % T) / px)
        at_eye[k] = {"cumulus_cov": round(float(R[i, j]), 3), "broken_cov": round(float(B[i, j]), 3),
                     "eye_alt_m": z, "inside_layer": layer_bottom <= z <= layer_top}
    cum = [c for c in cells if c["archetype"] == cu["archetype"]]
    (OUT / "clouds_v0.cells.json").write_text(json.dumps({
        "schema": "acw.cloud_cells/0", "state": STATE.name, "tile_m": T, "wraps": True, "cells": cells}, indent=1) + "\n")
    rep = {
        "status": "PASS_CLOUDS",
        "state": str(STATE.relative_to(REPO)).replace("\\", "/"),
        "seed": st["seed"],
        "tile_m": T,
        "weather_map": png.name,
        "weather_px_m": px,
        "weather_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
        "renderer_layer_m": [layer_bottom, layer_top],
        "renderer_layer_height_m": layer_h,
        "broken_base_norm": (float(br["base_m"]) - layer_bottom) / layer_h,
        "cells": {"cumulus": len(cum), "broken": len(cells) - len(cum)},
        "coverage": {"cumulus_area_fraction": round(float((R > 0.05).mean()), 4),
                     "broken_area_fraction": round(float((B > 0.05).mean()), 4)},
        "review_eye_check": at_eye,
    }
    (OUT / "clouds.report.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(rep))


if __name__ == "__main__":
    main()
