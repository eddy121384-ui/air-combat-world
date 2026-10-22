"""Far-LOD research: pack the octahedral impostor bake (adapters/unreal/ntwforest/fi_bake.py) into per-variant atlases.

Per variant v (0-9), N x N frames of OUT_PX each (frame (i, j) at column i, row j):
  T_FI_BC_V<v>.png  sRGB base colour (RGB) + coverage (A, box-filtered from the 2x / 4x supersampled capture)
  T_FI_ND_V<v>.png  object-space normal 0.5 + 0.5 n (RGB) + depth toward the camera 0.5 + 0.5 * dz / R (A)
Colour / normal are dilated into transparent texels (no dark halo when mips mix covered and empty texels).
Also: fi_sheet.png (a few frames of every variant, for review) and fi_pack.json (coverage, mean colour per variant).
    python tools/ntw/forest_world/fi_pack.py <bake_dir> <out_dir> [out_px=64]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pack_canopy import read_exr, srgb  # noqa: E402


def down(x, f):
    h, w = x.shape[:2]
    return x.reshape(h // f, f, w // f, f, *x.shape[2:]).mean(axis=(1, 3))


def dilate(rgb, a, iters):
    """Fill texels with a == 0 from their covered neighbours (coverage-weighted), repeated `iters` times."""
    w = (a > 0).astype(np.float32)
    c = rgb * w[..., None]
    for _ in range(iters):
        if w.min() > 0:
            break
        pw = np.pad(w, 1)
        pc = np.pad(c, ((1, 1), (1, 1), (0, 0)))
        sw = sum(pw[1 + dy:pw.shape[0] - 1 + dy, 1 + dx:pw.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        sc = sum(pc[1 + dy:pc.shape[0] - 1 + dy, 1 + dx:pc.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        fill = (w == 0) & (sw > 0)
        c[fill] = sc[fill] / sw[fill][:, None]
        w = np.where(fill, 1.0, w)
    return np.where(w[..., None] > 0, c, rgb.mean(axis=(0, 1)) if rgb.size else 0)


def main(bake, out, out_px=64):
    bake, out = Path(bake), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((bake / "fi_bake.json").read_text(encoding="utf-8"))
    n, cap, dist = meta["frames"], meta["capture_px"], meta["dist_cm"]
    f = cap // out_px
    stats, sheet = {}, []
    geo = {}
    for form, fm in meta["forms"].items():
        R = fm["R"]
        nd = np.zeros((n * out_px, n * out_px, 4), np.float32)
        cov = np.zeros((n * out_px, n * out_px), np.float32)
        for k in range(n * n):
            i, j = k % n, k // n
            dp = read_exr(bake / ("%s_dp_%03d" % (form, k)))[..., 0]
            nm = read_exr(bake / ("%s_nd_%03d" % (form, k)))[..., :3]
            m = (dp < dist + R + 100.0).astype(np.float32)
            nm = nm / np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
            dz = np.clip((dist - dp) / R, -1, 1) * m
            a = down(m, f)
            sw = np.maximum(down(m, f), 1e-6)
            nn = down(nm * m[..., None], f) / sw[..., None]
            zz = down(dz, f) / sw
            nn = dilate(nn, a, out_px)
            zz = dilate(zz[..., None], a, out_px)[..., 0]
            ys, xs = slice(j * out_px, (j + 1) * out_px), slice(i * out_px, (i + 1) * out_px)
            nd[ys, xs, :3] = 0.5 + 0.5 * nn / np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-6)
            nd[ys, xs, 3] = 0.5 + 0.5 * zz
            cov[ys, xs] = a
        geo[form] = (nd, cov)
    for vs, form in sorted(meta["variant_form"].items(), key=lambda t: int(t[0])):
        v = int(vs)
        nd, cov = geo[form]
        bc = np.zeros((n * out_px, n * out_px, 3), np.float32)
        for k in range(n * n):
            i, j = k % n, k // n
            dp = read_exr(bake / ("%s_dp_%03d" % (form, k)))[..., 0]
            m = (dp < dist + meta["forms"][form]["R"] + 100.0).astype(np.float32)
            c = read_exr(bake / ("V%d_bc_%03d" % (v, k)))[..., :3]
            sw = np.maximum(down(m, f), 1e-6)
            cc = down(c * m[..., None], f) / sw[..., None]
            ys, xs = slice(j * out_px, (j + 1) * out_px), slice(i * out_px, (i + 1) * out_px)
            bc[ys, xs] = dilate(cc, cov[ys, xs], out_px)
        rgba = np.dstack([srgb(bc), cov])
        Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA").save(out / ("T_FI_BC_V%d.png" % v))
        Image.fromarray(np.round(np.clip(nd, 0, 1) * 255).astype(np.uint8), "RGBA").save(out / ("T_FI_ND_V%d.png" % v))
        w = cov[..., None]
        stats[v] = {"form": form, "coverage_mean": float(cov.mean()),
                    "mean_linear_rgb_covered": [float(x) for x in (bc * w).reshape(-1, 3).sum(0) / max(float(w.sum()), 1e-6)]}
        # review strip: frames along the horizon row j = 0 and a top-down-ish frame, on grey
        pick = [(0, 0), (n // 3, 0), (2 * n // 3, 0), (n - 1, 0), (n // 2, n // 2), (n - 1, n - 1)]
        tiles = []
        for (i, j) in pick:
            ys, xs = slice(j * out_px, (j + 1) * out_px), slice(i * out_px, (i + 1) * out_px)
            a = cov[ys, xs][..., None]
            tiles.append(np.round((srgb(bc[ys, xs] * 2.0) * a + 0.45 * (1 - a)) * 255).astype(np.uint8))
        sheet.append(np.hstack(tiles))
    Image.fromarray(np.vstack(sheet)).resize((6 * 128, len(sheet) * 128), Image.NEAREST).save(out / "fi_sheet.png")
    rep = {"frames": n, "out_px": out_px, "atlas_px": n * out_px, "variants": stats, "forms": meta["forms"], "cam_sign_right_up": meta["cam_sign_right_up"]}
    (out / "fi_pack.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "variants"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:]))
