"""Pack the UE canopy bake (adapters/unreal/ntwforest/nf_bake.py) into 8-bit textures for the Landscape material.

For each tile (broad / acacia / crypt): T_NF_Canopy_<Tile>_BC.png = sRGB base colour (RGB) + canopy height above ground / 32 m (A);
T_NF_Canopy_<Tile>_N.png = world normal packed 0.5 + 0.5 * n (the tile is baked on flat ground, so it is the canopy's local perturbation of
"up"; the material bends the Landscape normal by its xy). Also writes a contact sheet bake_sheet.png and canopy_stats.json (mean linear
colour per tile, used to check the far canopy against the near trees).
    python tools/ntw/forest_world/pack_canopy.py <bake_dir> <out_dir>
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import numpy as np
from PIL import Image

CAM_Z_CM = 20000.0


def load(p):
    p = Path(p)
    for ext in (".exr", ".hdr", ".png"):
        q = p.with_suffix(ext)
        if q.exists():
            if ext == ".exr":
                import imageio.v3 as iio  # noqa: PLC0415
                return iio.imread(q).astype(np.float32)
            if ext == ".hdr":
                return read_hdr(q)
            return np.asarray(Image.open(q)).astype(np.float32) / 255.0
    raise FileNotFoundError(p)


def read_hdr(path):
    """Minimal Radiance RGBE reader (new-style RLE)."""
    data = Path(path).read_bytes()
    i = data.index(b"\n\n") + 2
    j = data.index(b"\n", i)
    dims = data[i:j].split()
    h, w = int(dims[1]), int(dims[3])
    pos = j + 1
    img = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        if data[pos] != 2 or data[pos + 1] != 2:
            raise ValueError("unsupported HDR encoding")
        pos += 4
        for c in range(4):
            x = 0
            while x < w:
                n = data[pos]
                pos += 1
                if n > 128:
                    n -= 128
                    img[y, x:x + n, c] = data[pos]
                    pos += 1
                else:
                    img[y, x:x + n, c] = np.frombuffer(data[pos:pos + n], np.uint8)
                    pos += n
                x += n
    e = img[..., 3].astype(np.int32)
    f = np.where(e > 0, np.ldexp(1.0, e - 136), 0.0)
    return (img[..., :3] * f[..., None]).astype(np.float32)


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def main(bake, out):
    bake, out = Path(bake), Path(out)
    stats, sheet = {}, []
    for t in ("broad", "acacia", "crypt"):
        bc = load(bake / f"{t}_basecolor")[..., :3]
        nm = load(bake / f"{t}_normal")[..., :3]
        dp = load(bake / f"{t}_depth")[..., 0]
        h = np.clip((CAM_Z_CM - dp) / 100.0, 0, 40)
        a = np.clip(h / 32.0, 0, 1)
        rgba = np.dstack([srgb(bc), a])
        Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA").save(out / f"T_NF_Canopy_{t.capitalize()}_BC.png")
        n = nm / np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
        Image.fromarray(np.round(np.clip(0.5 + 0.5 * n, 0, 1) * 255).astype(np.uint8), "RGB").save(out / f"T_NF_Canopy_{t.capitalize()}_N.png")
        cover = float((h > 2.0).mean())
        stats[t] = {"mean_linear_rgb": [float(x) for x in bc.reshape(-1, 3).mean(0)], "canopy_cover_gt2m": cover,
                    "height_m": {"p50": float(np.median(h)), "p90": float(np.percentile(h, 90)), "max": float(h.max())},
                    "normal_z_mean": float(n[..., 2].mean())}
        sheet.append(np.round(srgb(bc * 4.0) * 255).astype(np.uint8))
    Image.fromarray(np.hstack(sheet)).save(out / "bake_sheet.png")
    (out / "canopy_stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
