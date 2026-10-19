"""Pack the UE canopy bake (adapters/unreal/ntwforest/nf_bake.py) into 8-bit textures for the Landscape material.

For each tile (broad / acacia / crypt): T_NF_Canopy_<Tile>_BC.png = sRGB base colour (RGB) + canopy height above ground / 32 m (A);
T_NF_Canopy_<Tile>_N.png = world normal packed 0.5 + 0.5 * n (the tile is baked on flat ground, so it is the canopy's local perturbation of
"up"; the material bends the Landscape normal by its xy). Also writes a contact sheet bake_sheet.png and canopy_stats.json (mean linear
colour per tile, used to check the far canopy against the near trees).
    python tools/ntw/forest_world/pack_canopy.py <bake_dir> <out_dir>
"""
import json
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

CAM_Z_CM = 20000.0
NUL = bytes([0])
EXR_MAGIC = bytes([0x76, 0x2F, 0x31, 0x01])


def read_exr(path):
    """Minimal OpenEXR reader: scanline, ZIP (16 lines) / ZIPS / NONE compression, HALF / FLOAT channels -> HxWxC float32 in R,G,B,A order."""
    b = Path(path).read_bytes()
    if b[:4] != EXR_MAGIC:
        raise ValueError("not an OpenEXR file: %s" % path)
    p, attrs = 8, {}
    while b[p] != 0:
        e = b.index(NUL, p); name = b[p:e].decode(); p = e + 1
        e = b.index(NUL, p); p = e + 1
        (sz,) = struct.unpack_from("<i", b, p); p += 4
        attrs[name] = b[p:p + sz]; p += sz
    p += 1
    chans, q, cl = [], 0, attrs["channels"]
    while cl[q] != 0:
        e = cl.index(NUL, q); nm = cl[q:e].decode(); q = e + 1
        (pt,) = struct.unpack_from("<i", cl, q); q += 16
        chans.append((nm, pt))
    x0, y0, x1, y1 = struct.unpack("<4i", attrs["dataWindow"])
    w, h = x1 - x0 + 1, y1 - y0 + 1
    comp = attrs["compression"][0]
    lines = {0: 1, 2: 1, 3: 16}[comp]
    nblk = (h + lines - 1) // lines
    offs = struct.unpack_from("<%dQ" % nblk, b, p)
    out = {nm: np.zeros((h, w), np.float32) for nm, _ in chans}
    for o in offs:
        y, size = struct.unpack_from("<ii", b, o)
        raw = b[o + 8:o + 8 + size]
        n = min(lines, h - (y - y0))
        expect = sum(n * w * (2 if pt == 1 else 4) for _, pt in chans)
        if comp in (2, 3) and size < expect:
            t = np.frombuffer(zlib.decompress(raw), np.uint8).astype(np.int64)
            t = (np.cumsum(np.r_[t[0], t[1:] - 128]) & 0xFF).astype(np.uint8)   # undo the delta predictor
            half = (len(t) + 1) // 2
            r = np.empty_like(t)
            r[0::2], r[1::2] = t[:half], t[half:]                               # undo the byte split
            raw = r.tobytes()
        off = 0
        for yy in range(n):
            for nm, pt in chans:
                nb = w * (2 if pt == 1 else 4)
                out[nm][y - y0 + yy] = np.frombuffer(raw[off:off + nb], np.float16 if pt == 1 else np.float32)
                off += nb
    return np.dstack([out[c] for c in ("R", "G", "B", "A") if c in out])


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def main(bake, out):
    bake, out = Path(bake), Path(out)
    stats, sheet = {}, []
    for t in ("broad", "acacia", "crypt"):
        bc = read_exr(bake / f"{t}_basecolor")[..., :3]
        nm = read_exr(bake / f"{t}_normal")[..., :3]
        dp = read_exr(bake / f"{t}_depth")[..., 0]
        h = np.clip((CAM_Z_CM - dp) / 100.0, 0, 40)
        a = np.clip(h / 32.0, 0, 1)
        rgba = np.dstack([srgb(bc), a])
        Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA").save(out / f"T_NF_Canopy_{t.capitalize()}_BC.png")
        n = nm / np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-6)
        Image.fromarray(np.round(np.clip(0.5 + 0.5 * n, 0, 1) * 255).astype(np.uint8), "RGB").save(out / f"T_NF_Canopy_{t.capitalize()}_N.png")
        stats[t] = {"mean_linear_rgb": [float(x) for x in bc.reshape(-1, 3).mean(0)], "canopy_cover_gt2m": float((h > 2.0).mean()),
                    "height_m": {"p50": float(np.median(h)), "p90": float(np.percentile(h, 90)), "max": float(h.max())},
                    "normal_mean": [float(x) for x in n.reshape(-1, 3).mean(0)]}
        sheet.append(np.round(srgb(bc * 3.0) * 255).astype(np.uint8))
        sheet.append(np.round(np.dstack([a, a, a]) * 255).astype(np.uint8))
    Image.fromarray(np.vstack([np.hstack(sheet[0::2]), np.hstack(sheet[1::2])])).resize((1536, 1024)).save(out / "bake_sheet.png")
    (out / "canopy_stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
