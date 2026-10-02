"""Cheap Cloud Renderer v0 (EXPERIMENTAL): renderer inputs derived from the existing cloud state.

This is NOT a second placement system. It reads the cells that build_clouds.py already produced from
tools/lookdev/clouds/cloud_state_v0.json and only decides how the CHEAP renderer draws each cell:

  cell (archetype, centre, radius, base, top)  ->  one analytic impostor = up to 8 ellipsoid lobes
                                                   inside one inward-facing proxy box

The lobe layout is renderer detail (like the volumetric renderer's billow noise), generated
deterministically from the state seed + cell index, so the same cell always gets the same shape and
gameplay keeps querying the renderer-independent cells, never these lobes.

Input:  tools/lookdev/clouds/cloud_state_v0.json   (seed, tile size)
        unreal/Saved/XinyiLook/clouds/clouds_v0.cells.json   (build_clouds.py output)
Output: unreal/Saved/XinyiLook/clouds/cheap/
  clouds_v0.cheap.json      one record per drawn instance (cell + 64 km wrap copies near Xinyi):
                            UE location (cm), UE scale (proxy box half extents, m) and the 36
                            custom-primitive-data floats the material reads:
                              [0..31]  8 lobes x (dx, dy, dz, radius) in m, UE axes, box-relative
                              [32] cloud base z (box-relative m)  [33] lobe vertical squash
                              [34] per-cell variation seed 0..1   [35] bounding-sphere radius (m)
  cloud_cheap_box.glb       unit proxy box [-1, 1]^3 m with INWARD-facing triangles (only the far
                            side rasterises, once per pixel, also with the camera inside the box)
  cloud_cheap_noise_256.png RGBA8 value-noise lattice for the shader's 3D texture noise
                            (G = R shifted by (37, 17): one fetch gives two z slices)
  cloud_cheap.report.json

Deterministic; numpy + stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from gltf_writer import write_glb  # noqa: E402

STATE = HERE / "cloud_state_v0.json"
CELLS = REPO / "unreal/Saved/XinyiLook/clouds/clouds_v0.cells.json"
OUT = REPO / "unreal/Saved/XinyiLook/clouds/cheap"
MAX_LOBES = 8
SPAWN_RADIUS_M = 52000.0   # instances (incl. wrap copies) within this distance of the ENU origin
ERODE_PAD = 1.16           # shader erosion may grow a lobe by up to ~15.5 %; the proxy must contain it


def cumulus_lobes(rng, r, base, top):
    """Fair-weather cumulus: one broad core (the cloud reads as a single mass, not a pile of balls),
    skirt lobes cut flat by the base plane, and an overlapping, leaning tower whose crown reaches the
    state's cell top (consecutive tower lobes overlap by ~half: no stacked 'snowman')."""
    h = top - base
    size = min(1.0, max(0.0, (r - 420.0) / 830.0))
    n = int(np.clip(round(4 + 3.0 * size + rng.uniform(-0.5, 1.5)), 4, MAX_LOBES))
    k = rng.uniform(0.80, 0.95)
    lobes = []
    rc = min(0.66 * r * rng.uniform(0.9, 1.1), (0.6 * h + 150.0) / k)
    zc = base + rc * k * 0.55
    lobes.append([rng.uniform(-0.08, 0.08) * r, rng.uniform(-0.08, 0.08) * r, zc, rc])
    n_skirt = max(2, (n - 1) // 2)
    a0 = rng.uniform(0, 2 * math.pi)
    for i in range(n_skirt):
        rho = r * rng.uniform(0.38, 0.52)
        rho = min(rho, (h + 120.0) / (k + 0.3))          # skirts never poke far above the cell top
        ang = a0 + 2 * math.pi * (i + rng.uniform(-0.25, 0.25)) / n_skirt
        d = max(0.0, r - rho) * rng.uniform(0.55, 1.0)
        # centre above the base: the plane cuts below the lobe's widest part -> rounded flanks over a
        # flat bottom (a cut through the widest part reads as a plate / lip)
        z = base + rho * k * rng.uniform(0.45, 0.8)
        lobes.append([d * math.cos(ang), d * math.sin(ang), z, rho])
    n_tower = n - 1 - n_skirt
    shear = rng.uniform(0.05, 0.18) * r                  # towers lean a little downwind (+east)
    for j in range(n_tower):
        f = (j + 1) / n_tower                            # 0..1 up the tower, last one is the crown
        rho = min(rc * rng.uniform(0.62, 0.8) * (1.0 - 0.25 * f), 0.55 * h + 80.0)
        z = zc + f * max(0.0, top - rho * k * 0.95 - zc)  # crown top = cell top
        spread = 0.22 + 0.4 * max(0.0, 1.0 - (top - zc) / max(r, 1.0))   # flat cells: bumps spread out
        ang = rng.uniform(0, 2 * math.pi)
        d = r * spread * math.sqrt(rng.uniform(0.2, 1.0))
        lobes.append([d * math.cos(ang) + shear * f, d * math.sin(ang), z, rho])
    return lobes, k


def broken_lobes(rng, r, base, top):
    """Broken stratocumulus patch: wide flattened lobes in a lumpy sheet."""
    th = top - base
    n = MAX_LOBES
    rhos = r * rng.uniform(0.32, 0.5, n)
    k = float(np.clip(0.75 * th / rhos.mean(), 0.2, 0.7))
    lobes = []
    for i in range(n):
        ang = rng.uniform(0, 2 * math.pi)
        d = max(0.0, r - 0.6 * rhos[i]) * math.sqrt(rng.uniform(0, 1))
        z = base + th * rng.uniform(0.2, 0.6)
        lobes.append([d * math.cos(ang), d * math.sin(ang), z, float(rhos[i])])
    return lobes, k


def png_rgba8(path: Path, rgba: np.ndarray):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def inward_box(path: Path):
    """Unit box [-1, 1]^3 (glTF game frame) whose triangles face INTO the box."""
    pos, nrm, idx = [], [], []
    for axis in range(3):
        for sgn in (1.0, -1.0):
            n = np.zeros(3)
            n[axis] = sgn
            u = np.zeros(3)
            u[(axis + 1) % 3] = 1.0
            v = np.cross(n, u)                            # u x v = n (outward)
            c = n
            q = [c - u - v, c + u - v, c + u + v, c - u + v]
            b = len(pos)
            pos += q
            nrm += [-n] * 4
            idx += [[b, b + 2, b + 1], [b, b + 3, b + 2]]  # reversed winding: front face looks inward
    write_glb(path, [{"name": "M_XinyiClouds_Cheap", "positions": np.array(pos, np.float32),
                      "normals": np.array(nrm, np.float32), "indices": np.array(idx, np.uint32)}],
              "cloud_cheap_box")


def main():
    st = json.loads(STATE.read_text(encoding="utf-8"))
    cells_doc = json.loads(CELLS.read_text(encoding="utf-8"))
    if cells_doc.get("state") != STATE.name:
        raise SystemExit("cells file was not built from %s" % STATE.name)
    T = float(cells_doc["tile_m"])
    seed = int(st["seed"])
    cells = cells_doc["cells"]
    OUT.mkdir(parents=True, exist_ok=True)

    shapes = []
    for ci, c in enumerate(cells):
        rng = np.random.default_rng([seed, 0x0C4EA9, ci])
        broken = c["archetype"] != "fair_weather_cumulus"
        fn = broken_lobes if broken else cumulus_lobes
        lobes, k = fn(rng, float(c["radius_m"]), float(c["base_m"]), float(c["top_m"]))
        L = np.array(lobes, np.float64)
        ext_lo = np.array([(L[:, 0] - L[:, 3]).min(), (L[:, 1] - L[:, 3]).min(), float(c["base_m"])])
        ext_hi = np.array([(L[:, 0] + L[:, 3]).max(), (L[:, 1] + L[:, 3]).max(), (L[:, 2] + L[:, 3] * k).max()])
        mid = 0.5 * (ext_lo + ext_hi)
        half = 0.5 * (ext_hi - ext_lo) * ERODE_PAD + 5.0
        rel = L[:, :3] - mid
        bound = float((np.linalg.norm(rel, axis=1) + L[:, 3] * ERODE_PAD).max())
        shapes.append({"lobes": L, "k": k, "mid": mid, "half": half, "seed01": float(rng.uniform()),
                       "bound": bound, "base": float(c["base_m"])})

    inst = []
    for ci, (c, s) in enumerate(zip(cells, shapes)):
        e0, n0 = c["centre_enu_m"]
        for ox in (-T, 0.0, T):
            for oy in (-T, 0.0, T):
                e, n = e0 + ox + s["mid"][0], n0 + oy + s["mid"][1]
                if math.hypot(e, n) > SPAWN_RADIUS_M:
                    continue
                cpd = []
                for L in s["lobes"]:
                    # box-relative, UE axes (x = east, y = -north, z = up), metres
                    cpd += [L[0] - s["mid"][0], -(L[1] - s["mid"][1]), L[2] - s["mid"][2], L[3]]
                cpd += [0.0, 0.0, 0.0, 0.0] * (MAX_LOBES - len(s["lobes"]))
                cpd += [s["base"] - s["mid"][2], s["k"], s["seed01"], s["bound"]]
                inst.append({
                    "cell": ci, "wrap": [int(ox / T), int(oy / T)],
                    "ue_location_cm": [round(e * 100.0, 1), round(-n * 100.0, 1), round(s["mid"][2] * 100.0, 1)],
                    "ue_scale": [round(float(s["half"][0]), 3), round(float(s["half"][1]), 3), round(float(s["half"][2]), 3)],
                    "cpd": [round(float(v), 3) for v in cpd],
                })
    doc = {"schema": "acw.cloud_cheap/0", "role": "Cheap Cloud Renderer v0 (experimental) inputs; derived "
           "from clouds_v0.cells.json, renderer detail only (not cloud state)", "state": STATE.name,
           "cells_file": CELLS.name, "tile_m": T, "spawn_radius_m": SPAWN_RADIUS_M, "max_lobes": MAX_LOBES,
           "instances": inst}
    (OUT / "clouds_v0.cheap.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    inward_box(OUT / "cloud_cheap_box.glb")

    # value-noise lattice for the iq-style texture 3D noise: G(i, j) = R(i + 37, j + 17)
    nrng = np.random.default_rng([seed, 0x0A015E])
    r = nrng.integers(0, 256, (256, 256), dtype=np.int64)
    b = nrng.integers(0, 256, (256, 256), dtype=np.int64)
    g = np.roll(np.roll(r, -17, axis=0), -37, axis=1)
    a = np.roll(np.roll(b, -17, axis=0), -37, axis=1)
    noise = np.stack([r, g, b, a], axis=-1).astype(np.uint8)
    png_rgba8(OUT / "cloud_cheap_noise_256.png", noise)

    lobes_n = [len(s["lobes"]) for s in shapes]
    rep = {
        "status": "PASS_CLOUD_CHEAP",
        "experimental": True,
        "state": str(STATE.relative_to(REPO)).replace("\\", "/"),
        "seed": seed,
        "cells": len(cells),
        "instances": len(inst),
        "wrap_copies": sum(1 for i in inst if i["wrap"] != [0, 0]),
        "lobes_per_cell": {"min": min(lobes_n), "max": max(lobes_n), "mean": round(float(np.mean(lobes_n)), 2)},
        "max_proxy_half_extent_m": [round(float(max(s["half"][i] for s in shapes)), 1) for i in range(3)],
        "cheap_json_sha256": hashlib.sha256((OUT / "clouds_v0.cheap.json").read_bytes()).hexdigest(),
        "noise_sha256": hashlib.sha256((OUT / "cloud_cheap_noise_256.png").read_bytes()).hexdigest(),
    }
    (OUT / "cloud_cheap.report.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps(rep))


if __name__ == "__main__":
    main()
