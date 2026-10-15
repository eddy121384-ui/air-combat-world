"""Offline foliage-card overdraw for the 紅楠 game LODs (project venv: numpy + Pillow).

python tools/treegen/card_overdraw.py <game_out_dir> <out_dir> [view,view,...]

For every LOD and camera in views.json, rasterises the exported leaf-card quads (cards_lod*.npz: world corners in
Blender metres + atlas UV rect) at 1920x1080 with perspective-correct UVs and counts per pixel:
* raster layers  - every card fragment (what the depth pre-pass / masked pixel shader is invoked for, worst case);
* opaque layers  - fragments whose atlas alpha >= 0.4 (the material's clip value).
Branch triangles are not included (opaque, small screen share). This is a geometric upper bound: the engine's early-Z
can reject fragments behind already-written depth, so real shaded overdraw is lower; it is still the right number for
comparing LODs and for spotting card density problems.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

GAME, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
PROFILE = os.environ.get("ACW_TL_PROFILE", "v1")  # budget profile files: cards_budget_lodN.npz
VIEWS = {v["name"]: v for v in json.load(open(os.path.join(GAME, os.environ.get("ACW_TL_VIEWS", "views.json"))))["views"]}
names = sys.argv[3].split(",") if len(sys.argv) > 3 else ["front", "oblique", "close", "agl50", "agl200"]
alpha = np.asarray(Image.open(os.path.join(GAME, "textures", "T_Machilus_LeafAtlas_BC.png")).getchannel("A"), np.float32) / 255.0
AH, AW = alpha.shape
W, H = 1920, 1080


def camera(v):
    L = np.array(v["loc"], float)
    F = np.array(v["fwd"], float)
    F /= np.linalg.norm(F)
    if "ortho_m" in v:
        return dict(L=L, F=F, R=np.array([1.0, 0, 0]), U=np.array([0, 1.0, 0]), ortho=W / v["ortho_m"])
    R = np.cross(F, [0, 0, 1.0])
    R /= np.linalg.norm(R)
    U = np.cross(R, F)
    return dict(L=L, F=F, R=R, U=U, f=(W / 2) / math.tan(math.radians(v["hfov_deg"]) / 2))


def project(c, P):
    d = P - c["L"]
    x, y, z = d @ c["R"], d @ c["U"], d @ c["F"]
    if "ortho" in c:
        return np.column_stack([W / 2 + x * c["ortho"], H / 2 - y * c["ortho"]]), np.ones_like(z)
    return np.column_stack([W / 2 + c["f"] * x / z, H / 2 - c["f"] * y / z]), z


def raster(npz, c):
    d = np.load(npz)
    corners, uvr = d["corners"].astype(float), d["uvrect"]
    n = len(corners)
    sp, z = project(c, corners.reshape(-1, 3))
    sp, z = sp.reshape(n, 4, 2), z.reshape(n, 4)
    ras = np.zeros((H, W), np.uint16)
    opq = np.zeros((H, W), np.uint16)
    quv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)  # corner order of machilus_game.build_cards
    for i in range(n):
        if (z[i] <= 0.05).any():
            continue
        u0, v0, u1, v1 = uvr[i]
        for tri in ((0, 1, 2), (0, 2, 3)):
            p = sp[i, list(tri)]
            x0, x1 = int(max(0, np.floor(p[:, 0].min()))), int(min(W - 1, np.ceil(p[:, 0].max())))
            y0, y1 = int(max(0, np.floor(p[:, 1].min()))), int(min(H - 1, np.ceil(p[:, 1].max())))
            if x1 < x0 or y1 < y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = p
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-9:
                continue
            w0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
            w1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            iz = 1.0 / z[i, list(tri)]
            q = quv[list(tri)]
            wz = np.stack([w0 * iz[0], w1 * iz[1], w2 * iz[2]], -1)
            wz /= wz.sum(-1, keepdims=True)
            uu = (wz * q[:, 0]).sum(-1)
            vv = (wz * q[:, 1]).sum(-1)
            au = u0 + uu * (u1 - u0)
            av = v0 + vv * (v1 - v0)  # Blender UV (origin bottom-left)
            tx = np.clip((au * AW).astype(int), 0, AW - 1)
            ty = np.clip(((1 - av) * AH).astype(int), 0, AH - 1)
            a = alpha[ty, tx] >= 0.4
            sl = (slice(y0, y1 + 1), slice(x0, x1 + 1))
            ras[sl] += inside
            opq[sl] += inside & a
    return ras, opq


def stats(ras, opq):
    foot = ras > 0
    cov = opq > 0
    return dict(card_footprint_px=int(foot.sum()), covered_px=int(cov.sum()),
                raster_layers_mean=round(float(ras[foot].mean()), 2) if foot.any() else 0,
                raster_layers_p95=int(np.percentile(ras[foot], 95)) if foot.any() else 0,
                raster_layers_max=int(ras.max()),
                opaque_layers_mean=round(float(opq[cov].mean()), 2) if cov.any() else 0,
                opaque_layers_p95=int(np.percentile(opq[cov], 95)) if cov.any() else 0,
                card_fragments_total=int(ras.sum()))


def heat(ras, path):
    v = np.clip(ras / 40.0, 0, 1)
    rgb = np.stack([np.clip(3 * v, 0, 1), np.clip(3 * v - 1, 0, 1), np.clip(3 * v - 2, 0, 1)], -1)
    Image.fromarray((rgb * 255).astype(np.uint8)).save(path)


res = {}
for name in names:
    c = camera(VIEWS[name])
    for lod in ("lod0", "lod1", "lod2", "lod3"):
        npz = os.path.join(GAME, "cards_%s.npz" % lod if PROFILE == "v1" else "cards_%s_%s.npz" % (PROFILE, lod))
        if not os.path.isfile(npz):
            continue
        ras, opq = raster(npz, c)
        res["%s/%s" % (name, lod)] = stats(ras, opq)
        heat(ras, os.path.join(OUT, "overdraw_%s_%s.png" % (name, lod)))
        print(PROFILE, name, lod, res["%s/%s" % (name, lod)], flush=True)
json.dump(dict(note=__doc__.split("\n\n")[1], resolution=[W, H], results=res), open(os.path.join(OUT, "overdraw.json"), "w"), indent=1)
