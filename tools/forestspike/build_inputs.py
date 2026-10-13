"""ForestSpike B0 offline inputs (numpy / scipy / Pillow only; deterministic).

  python tools/forestspike/build_inputs.py [--out DIR]

Writes (default DIR = unreal/ForestSpike/Saved/ForestSpike/inputs, git-ignored, regenerated on demand):
  terrain_core.glb      1 km x 1 km core terrain, 5 m grid + edge skirt
  terrain_context.glb   6 km x 6 km shared context terrain, 20 m grid, 1 km hole for the core + edge skirt
  field_core.png        512^2 RGBA8  R forest coverage, G edge distance (0.25 m units, <= 63.75 m),
                        B slope (deg/45), A 255. Texel (i, j) = centre of east/north cell; row j increases north.
  field_ctx.png         1024^2 same layout over the 6 km context
  pool.f32 + pool.json  forest instance candidate pool (core only), ordered by random priority rank
  inputs.manifest.json  parameters, measured statistics and SHA-256 of every output and of the PR #18 models

The PR #18 models (assets/forestspike/b0/models, copied from spike/north-taiwan-vegetation-pilot @ e05a959)
are verified against that PR's own manifest; PR #18 itself is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "lookdev"))
import fs_world as w  # noqa: E402
from gltf_writer import read_glb_primitives, ue_local_bounds_cm, write_glb  # noqa: E402

CORE_GRID_M = 5.0
CTX_GRID_M = 20.0
SKIRT_M = 4.0
FIELD_CORE_PX = 512
FIELD_CTX_PX = 1024
POOL_CELL_M = 2.8
MODELS = REPO / "assets" / "forestspike" / "b0" / "models"
PR18_MANIFEST = REPO / "assets" / "forestspike" / "b0" / "pr18_manifest.json"


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def game(e, up, n):
    """ENU -> game frame used by the XinyiLook importer (UE X = e, UE Y = -n, UE Z = up after the X,Z,Y swap)."""
    return np.column_stack([e, up, -n]).astype(np.float32)


def normals_game(e, n):
    _, he, hn = w.height_and_grad(e, n)
    v = np.column_stack([-he, np.ones_like(he), hn])
    return (v / np.linalg.norm(v, axis=1, keepdims=True)).astype(np.float32)


def grid_mesh(e0, e1, n0, n1, step, skip=None):
    """Regular grid over [e0,e1] x [n0,n1]; cells whose (i, j) satisfy skip(i, j) are omitted. Returns verts/tris."""
    ni = int(round((e1 - e0) / step))
    nj = int(round((n1 - n0) / step))
    ge = e0 + np.arange(ni + 1) * step
    gn = n0 + np.arange(nj + 1) * step
    E, N = np.meshgrid(ge, gn)                      # shape (nj+1, ni+1)
    vid = np.arange((ni + 1) * (nj + 1)).reshape(nj + 1, ni + 1)
    tris = []
    for j in range(nj):
        for i in range(ni):
            if skip is not None and skip(i, j):
                continue
            a, b, c, d = vid[j, i], vid[j, i + 1], vid[j + 1, i + 1], vid[j + 1, i]
            # alternate the diagonal for a less directional triangulation
            if (i + j) % 2 == 0:
                tris += [(a, b, c), (a, c, d)]
            else:
                tris += [(a, b, d), (b, c, d)]
    tris = np.asarray(tris, np.uint32)
    used = np.unique(tris)
    remap = -np.ones(E.size, np.int64)
    remap[used] = np.arange(len(used))
    return E.reshape(-1)[used], N.reshape(-1)[used], remap[tris].astype(np.uint32), (ni, nj)


def add_skirt(E, N, tris, outward_is_left):
    """Vertical skirt under every boundary edge (edge used by exactly one triangle)."""
    edges = {}
    for t in tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            key = (min(a, b), max(a, b))
            edges.setdefault(key, []).append((a, b))
    bnd = [v[0] for v in edges.values() if len(v) == 1]
    nv = len(E)
    new_e, new_n, new_t = [], [], []
    ofs = {}
    for a, b in bnd:
        for v in (a, b):
            if v not in ofs:
                ofs[v] = nv + len(new_e)
                new_e.append(E[v])
                new_n.append(N[v])
        new_t += [(a, b, ofs[b]), (a, ofs[b], ofs[a])]
    return np.concatenate([E, new_e]), np.concatenate([N, new_n]), np.concatenate([tris, np.asarray(new_t, np.uint32)]), nv


def terrain_glb(path, E, N, tris, n_surface):
    up = w.height(E, N)
    up = up.copy()
    up[n_surface:] -= SKIRT_M
    pos = game(E, up, N)
    nrm = normals_game(E, N)
    # winding: make every triangle's geometric normal point up in the game frame (+Y)
    p0, p1, p2 = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    ny = np.cross(p1 - p0, p2 - p0)[:, 1]
    surf = (tris < n_surface).all(axis=1)
    flip = surf & (ny < 0)
    t2 = tris.copy()
    t2[flip, 1], t2[flip, 2] = tris[flip, 2], tris[flip, 1]
    # skirt triangles: orientation does not matter (the material is two-sided); keep as built
    uv = np.column_stack([(E + w.CTX_HALF) / w.CTX_M, (N + w.CTX_HALF) / w.CTX_M]).astype(np.float32)
    write_glb(path, [{"name": "FS_Terrain", "positions": pos, "normals": nrm, "uv0": uv, "indices": t2,
                      "base_color": [0.1, 0.2, 0.08, 1.0]}], mesh_name=Path(path).stem)
    return {"vertices": int(len(pos)), "triangles": int(len(t2)), "flipped_for_winding": int(flip.sum())}


def build_terrain(out):
    res = {}
    # core: 200 x 200 cells of 5 m
    E, N, tris, (ni, nj) = grid_mesh(-w.CORE_HALF, w.CORE_HALF, -w.CORE_HALF, w.CORE_HALF, CORE_GRID_M)
    ns = len(E)
    E, N, tris, _ = add_skirt(E, N, tris, True)
    res["core"] = terrain_glb(out / "terrain_core.glb", E, N, tris, ns)
    # context: 300 x 300 cells of 20 m minus the core hole
    lo = -w.CTX_HALF
    cells = int(w.CTX_M / CTX_GRID_M)
    h0 = int((w.CTX_HALF - w.CORE_HALF) / CTX_GRID_M)
    h1 = int((w.CTX_HALF + w.CORE_HALF) / CTX_GRID_M)
    E, N, tris, _ = grid_mesh(lo, -lo, lo, -lo, CTX_GRID_M, skip=lambda i, j: h0 <= i < h1 and h0 <= j < h1)
    ns = len(E)
    E, N, tris, _ = add_skirt(E, N, tris, True)
    res["context"] = terrain_glb(out / "terrain_context.glb", E, N, tris, ns)
    res["context"]["cells"] = cells
    return res


def build_fields(out):
    stats = {}
    for name, extent, px in (("core", w.CORE_M, FIELD_CORE_PX), ("ctx", w.CTX_M, FIELD_CTX_PX)):
        cov = w.raster(extent, px, ss=4)
        texel = extent / px
        inside = cov > 0.5
        edt = ndimage.distance_transform_edt(inside) * texel          # metres to the nearest non-forest texel
        half = extent / 2.0
        c = (np.arange(px) + 0.5) / px * extent - half
        E, N = np.meshgrid(c, c)
        sl = w.slope_deg(E, N)
        img = np.zeros((px, px, 4), np.uint8)
        img[..., 0] = np.round(cov * 255.0)
        img[..., 1] = np.round(np.clip(edt, 0.0, 63.75) * 4.0)
        img[..., 2] = np.round(np.clip(sl / 45.0, 0.0, 1.0) * 255.0)
        img[..., 3] = 255
        Image.fromarray(img, "RGBA").save(out / ("field_%s.png" % name), optimize=False, compress_level=6)
        stats[name] = {"texel_m": texel, "forest_fraction": float(inside.mean()), "slope_mean_deg": float(sl.mean())}
    return stats


def build_pool(out):
    rng = np.random.default_rng(w.SEED + 7)
    half = w.CORE_HALF
    nc = int(w.CORE_M / POOL_CELL_M)
    gc = (np.arange(nc) + 0.5) * POOL_CELL_M - half
    E, N = np.meshgrid(gc, gc)
    E = (E + rng.uniform(-0.5, 0.5, E.shape) * POOL_CELL_M).reshape(-1)
    N = (N + rng.uniform(-0.5, 0.5, N.shape) * POOL_CELL_M).reshape(-1)
    keep = w.forest_binary(E, N) & (np.abs(E) < half) & (np.abs(N) < half)
    E, N = E[keep], N[keep]
    order = rng.permutation(len(E))              # priority rank: instance i of a run uses the first n entries
    E, N = E[order], N[order]
    Z = w.height(E, N)
    yaw = rng.uniform(0.0, 360.0, len(E))
    scale = rng.uniform(0.8, 1.25, len(E))
    variant = rng.choice(4, size=len(E), p=[0.40, 0.20, 0.20, 0.20])
    color = rng.integers(0, 4, len(E))
    u = rng.uniform(0.0, 1.0, len(E))
    arr = np.column_stack([E, N, Z, yaw, scale, variant, color, u]).astype("<f4")
    arr.tofile(out / "pool.f32")
    meta = {"count": int(len(arr)), "columns": ["e", "n", "z", "yaw_deg", "scale", "variant", "color", "u"],
            "dtype": "<f4", "cell_m": POOL_CELL_M, "density_per_km2_all": len(arr) / w.CORE_M ** 2 * 1e6,
            "archetype_weights": [0.40, 0.20, 0.20, 0.20]}
    (out / "pool.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def verify_models():
    m = json.loads(PR18_MANIFEST.read_text(encoding="utf-8"))
    want = {a["filename"].split("/")[-1]: a["sha256"] for a in m["assets"]}
    ref = m["reference_original"]
    want[Path(ref["filename"]).name if "filename" in ref else "xinyi_reference_original.glb"] = ref.get("sha256")
    got, bad = {}, []
    for p in sorted(MODELS.glob("*.glb")):
        h = sha256(p)
        got[p.name] = h
        if want.get(p.name) and want[p.name] != h:
            bad.append(p.name)
    missing = [k for k in want if k not in got]
    return {"count": len(got), "mismatch": bad, "missing_from_copy": missing, "sha256": got,
            "pr18_manifest_baseline_sha": m.get("baseline_sha")}


def expected_bounds(out):
    """Expected Unreal-local bounds (cm) of every GLB; the UE adapters correct pivots by (expected - imported)."""
    res = {}
    for p in sorted(list(out.glob("*.glb")) + list(MODELS.glob("*.glb"))):
        pos = np.concatenate([np.asarray(q["position"], np.float64) for q in read_glb_primitives(p)])
        res[p.name] = ue_local_bounds_cm(pos)
    (out / "bounds.json").write_text(json.dumps(res, indent=2) + "
")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "unreal" / "ForestSpike" / "Saved" / "ForestSpike" / "inputs"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = np.linspace(-w.CORE_HALF, w.CORE_HALF, 401)
    E, N = np.meshgrid(c, c)
    h = w.height(E, N)
    sl = w.slope_deg(E, N)
    world = {
        "seed": w.SEED, "core_m": w.CORE_M, "context_m": w.CTX_M, "base_elevation_m": w.BASE_ELEVATION_M,
        "forest_threshold": w.FOREST_THRESHOLD,
        "core_relief_m": float(h.max() - h.min()), "core_height_min_m": float(h.min()), "core_height_max_m": float(h.max()),
        "core_slope_mean_deg": float(sl.mean()), "core_slope_p90_deg": float(np.percentile(sl, 90)),
        "core_forest_fraction": float(w.forest_binary(E, N).mean()),
        "note": "synthetic analytic test fixture; not Northern Taiwan terrain or a land-use dataset",
    }
    terrain = build_terrain(out)
    fields = build_fields(out)
    pool = build_pool(out)
    models = verify_models()
    expected_bounds(out)
    files = {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != "inputs.manifest.json"}
    manifest = {"world": world, "terrain": terrain, "fields": fields, "pool": pool, "models": models, "outputs_sha256": files}
    (out / "inputs.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("world", "terrain", "fields")}, indent=2))
    print("pool", pool["count"], "candidates;", "models", models["count"], "mismatch", models["mismatch"], "missing", models["missing_from_copy"])
    if models["mismatch"]:
        raise SystemExit("PR #18 model copy does not match its manifest")


if __name__ == "__main__":
    main()
