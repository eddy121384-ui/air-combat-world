"""Offline scalar-mask authoring/packing, never an Unreal or city-geometry writer.

Build: python tools/materials/build_xinyi_shared_masks.py
Audit: python tools/materials/build_xinyi_shared_masks.py --validate --reproduce
Inputs are preserved AI originals/candidates plus one authored SVG, not noise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "assets/materials/xinyi/shared_masks/v1"
PARENT = "assets/materials/xinyi/imagegen/batch1"
BASE = "6c2feb1611a3d07436c8222c3b67246a9b1ad8cd"
SPAN = 32
LEVELS = np.arange(104, 153, 8, dtype=np.uint8)
NAMES = {
    "facade": ["A1_stain", "A2_repair_a", "A3_rain_run", "A4_repair_b"],
    "roof": ["R1_membrane", "R2_recoat", "R3_drainage", "R4_aggregate"],
}
TEX = {"facade": "T_XinyiFacadeAge", "roof": "T_XinyiRoofSurface"}
ROLES = ["STAIN / MOULD", "REPAIR A", "RAIN RUN", "REPAIR B",
         "MEMBRANE", "RECOAT", "DRAINAGE / RUST", "COARSE SCATTER"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_image(a):
    return Image.fromarray(np.uint8(np.clip(np.rint(a), 0, 255)))


def wrap_blur(a, sigma):
    # Gaussian support is bounded by a 4-sigma wrapped halo, never black padding.
    r = math.ceil(4 * sigma)
    p = np.pad(np.uint8(a), r, mode="wrap")
    b = Image.fromarray(p).filter(ImageFilter.GaussianBlur(sigma))
    return np.asarray(b)[r:-r, r:-r].astype(float)


def periodic_edges(a, width):
    """Smooth opposing-edge correction; no reflected/duplicated stain quadrants."""
    a = a.copy()
    for axis in (1, 0):
        for i in range(width):
            t = i / (width - 1)
            weight = .5 * (1 - t * t * (3 - 2*t))
            if axis == 1:
                lo, hi = a[:, i].copy(), a[:, -1-i].copy()
                a[:, i] = lo*(1-weight) + hi*weight
                a[:, -1-i] = hi*(1-weight) + lo*weight
            else:
                lo, hi = a[i].copy(), a[-1-i].copy()
                a[i] = lo*(1-weight) + hi*weight
                a[-1-i] = hi*(1-weight) + lo*weight
    return a


def close_edges(a):
    a = a.copy()
    side = np.rint((a[:, 0].astype(float) + a[:, -1])*.5).astype(a.dtype)
    a[:, 0] = side; a[:, -1] = side
    side = np.rint((a[0].astype(float) + a[-1])*.5).astype(a.dtype)
    a[0] = side; a[-1] = side
    return a


def render_repair_svg(path, size):
    """Tiny deliberately restricted SVG reader: only explicit rect/polygon art.

    No synthesis, random positions, external references or runtime SVG dependency.
    The checked-in SVG is the editable source of truth, in metres.
    """
    root = ET.parse(path).getroot()
    assert root.attrib["viewBox"] == "0 0 32 32"
    ss = 2
    canvas = Image.new("L", (size*ss, size*ss), 128)
    d = ImageDraw.Draw(canvas)
    scale = size*ss/SPAN
    for e in root:
        tag = e.tag.rsplit("}", 1)[-1]
        if tag in ("title", "desc"):
            continue
        rgb = e.attrib["fill"].lstrip("#")
        assert rgb[0:2] == rgb[2:4] == rgb[4:6]
        value = int(rgb[:2], 16)
        if tag == "polygon":
            pts = [tuple(float(v)*scale for v in p.split(",")) for p in e.attrib["points"].split()]
            d.polygon(pts, fill=value)
        elif tag == "rect":
            x, y, w, h = [float(e.attrib[k])*scale for k in ("x", "y", "width", "height")]
            d.rectangle((x, y, x+w, y+h), fill=value)
        else:
            raise ValueError(f"Unsupported SVG element: {tag}")
    return canvas.resize((size, size), Image.Resampling.BOX)


def make_plane(im, size, *, authored=False):
    im = im.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    a = np.asarray(im, dtype=float)
    if not authored:
        # Preserve signed repairs / darker stains. Never histogram-equalize each tile.
        a += 128 - np.median(a)
        a = np.clip(a, 104, 152)
    a = wrap_blur(a, size*.16/SPAN)  # ~0.16m sigma, suppress generated micro-grain
    a = periodic_edges(a, round(size/32))  # 1m border support
    a = np.clip(np.rint((a-128)/8)*8+128, 104, 152).astype(np.uint8)
    # Quantize first, then copy the first periodic sample at the closing boundary.
    a[:, -1] = a[:, 0]; a[-1] = a[0]
    return Image.fromarray(a)


def mobile(im):
    return array_image(close_edges(np.asarray(im.resize((512, 512), Image.Resampling.BOX))))


def stats(im):
    a = np.asarray(im, dtype=float)
    gx = np.diff(a, axis=1); gy = np.diff(a, axis=0)
    return {
        "mean_255": round(float(a.mean()), 4), "std_255": round(float(a.std()), 4),
        "min": int(a.min()), "max": int(a.max()), "distinct_values": len(np.unique(a)),
        "wrap_x_max_255": int(abs(a[:, 0]-a[:, -1]).max()),
        "wrap_y_max_255": int(abs(a[0]-a[-1]).max()),
        "seam_slope_x_max_255": int(abs(gx[:, 0]-gx[:, -1]).max()),
        "seam_slope_y_max_255": int(abs(gy[0]-gy[-1]).max()),
        "adjacent_gradient_p99_255": round(float(np.percentile(np.concatenate((abs(gx).ravel(), abs(gy).ravel())), 99)), 3),
        "coarse_8_std_255": round(float(np.asarray(im.resize((im.width//8, im.height//8), Image.Resampling.BOX), dtype=float).std()), 4),
        "coarse_16_std_255": round(float(np.asarray(im.resize((im.width//16, im.height//16), Image.Resampling.BOX), dtype=float).std()), 4),
    }


def font(size):
    return ImageFont.load_default(size=size)


def review_sheet(title, size):
    im = Image.new("RGB", size, "#111e29")
    d = ImageDraw.Draw(im)
    d.text((24, 17), title, font=font(26), fill="#eaf3f3")
    return im, d


def label(d, pos, text, size=15, fill="#bad0d8"):
    d.text(pos, text, font=font(size), fill=fill)


def amplified(im):
    return array_image((np.asarray(im, dtype=float)-128)*4+128).convert("RGB")


def previews(out, planes, packed):
    ordered = NAMES["facade"] + NAMES["roof"]
    sheet, d = review_sheet("XINYI / SHARED MASKS v1    -    OFFLINE ART REVIEW", (1360, 900))
    label(d, (24, 54), "Eight scalar planes / 32m repeat / grayscale data; colour comes from building palettes.", 17)
    for i, name in enumerate(ordered):
        x = 24 + i % 4 * 334; y = 94 + i // 4 * 398
        label(d, (x, y), f"{'RGBA'[i%4]}   {name} / {ROLES[i]}", 15, "#f5cb84")
        sheet.paste(planes[name].convert("RGB").resize((306, 306), Image.Resampling.BOX), (x, y+28))
        st = stats(planes[name])
        label(d, (x, y+344), f"{planes[name].width}px  mean {st['mean_255']:.1f}  sigma {st['std_255']:.1f}")
        label(d, (x, y+368), "A is data, never transparency.", 14)
    sheet.save(out/"review/channels.png")

    sheet, d = review_sheet("3 x 3 REPEAT / 4x CONTRAST DIAGNOSTIC", (1360, 880))
    label(d, (24, 54), "Amplified for seam/repetition inspection; these are NOT the runtime contrast or a seamlessness approval.", 16)
    for i, name in enumerate(ordered):
        x = 24 + i % 4 * 334; y = 94 + i // 4 * 385
        label(d, (x, y), name, 17, "#f5cb84")
        tile = amplified(planes[name]).resize((102, 102), Image.Resampling.BOX)
        for yy in range(3):
            for xx in range(3): sheet.paste(tile, (x+xx*102, y+28+yy*102))
        label(d, (x, y+344), "Joins at 1/3 and 2/3; no gutters.", 13)
    sheet.save(out/"review/tiling.png")

    sheet, d = review_sheet("PACKED CHANNELS / LINEAR DATA", (1260, 570))
    label(d, (24, 54), "RGB false colour omits alpha. The separate A view below shows the FOURTH scalar plane.", 16)
    for j, family in enumerate(("facade", "roof")):
        x = 24+j*620
        label(d, (x, 92), TEX[family]+" / 512 RGBA", 20, "#f5cb84")
        im = packed[family]
        sheet.paste(im.convert("RGB").resize((280, 280)), (x, 126))
        sheet.paste(im.getchannel("A").convert("RGB").resize((280, 280)), (x+300, 126))
        label(d, (x, 420), "RGB DATA (not albedo)", 17)
        label(d, (x+300, 420), "A DATA (not opacity)", 17)
        label(d, (x, 461), "sRGB OFF | Masks | Wrap U/V | preserve alpha | native mips", 15)
        label(d, (x, 493), "No normals / AO / per-building texture / extra sample per channel", 14)
    sheet.save(out/"review/packed.png")

    sheet, d = review_sheet("DISTANCE / FLAT 32m SWATCH PROJECTION", (1400, 720))
    label(d, (24, 54), "1080px vertical, 60deg vFOV; ideal box filtering. Offline scalar evidence, NOT an Unreal capture.", 16)
    for col, distance in enumerate((150, 300, 600, 800)):
        x = 24+col*344
        px = round(1080/(2*math.tan(math.radians(30)))*SPAN/distance)
        label(d, (x, 100), f"{distance}m / 32m = {px}px", 20, "#f5cb84")
        for row, family in enumerate(("facade", "roof")):
            y = 145+row*215
            src = packed[family].getchannel("R")
            tile = src.resize((px, px), Image.Resampling.BOX).convert("RGB")
            sheet.paste(tile, (x, y)); label(d, (x, y+max(px, 50)+10), TEX[family], 16)
        label(d, (x, 650), "No perspective / lighting test.", 14)
    sheet.save(out/"review/distance.png")

    sheet, d = review_sheet("PALETTE APPLICATION / BASE vs MASKS", (1330, 830))
    label(d, (24, 54), "Illustrative 2D swatches only. Window rhythm is drawn separately; no buildings, shader or UE scene changed.", 15)
    recipes = [("LEGACY / warm render", "facade", (166,159,145), 1.),
               ("HUAXIA / muted tile", "facade", (161,146,133), .6),
               ("ROOF / grey membrane", "roof", (148,151,143), 1.)]
    for row, (title, family, color, weight) in enumerate(recipes):
        y = 105+row*235
        label(d, (24, y), title, 18, "#f5cb84")
        p = np.asarray(packed[family], dtype=float)
        v = (p-128)/24
        # Dark values carry stains; G/A repairs are signed palette variation.
        factor = 1 + weight*(.14*np.minimum(v[..., 0], 0) + .06*v[..., 1]
                             + .11*np.minimum(v[..., 2], 0) + .06*v[..., 3])
        factor = np.clip(factor, .75, 1.12)
        for col in range(2):
            x = 370+col*470
            a = np.full((180, 430, 3), color, dtype=np.uint8)
            if col:
                # 32m wide x 13.4m high: crop at the same metre scale, never stretch
                # a square roof/wall field to fit the rectangular review panel.
                crop_h = round(512*180/430)
                field = Image.fromarray(factor.astype(np.float32)).crop((0, 0, 512, crop_h))
                f = np.asarray(field.resize((430, 180), Image.Resampling.BOX))
                a = np.uint8(np.clip(a.astype(float)*f[..., None], 0, 255))
            swatch = Image.fromarray(a); dd = ImageDraw.Draw(swatch)
            if family == "facade":
                for floor in range(4):
                    for bay in range(9):
                        dd.rectangle((12+bay*47, 10+floor*43, 31+bay*47, 34+floor*43), fill=(76,88,87))
            sheet.paste(swatch, (x, y+20))
            label(d, (x, y-3), "BASE PALETTE" if not col else "+ SHARED MASKS", 17)
    sheet.save(out/"review/surfaces.png")


def load_inputs():
    spec = json.loads((PACK/"inputs.json").read_text())
    for item in spec["files"]:
        p = REPO/item["path"]
        if digest(p) != item["sha256"]:
            raise ValueError(f"Source changed; explicitly review provenance before updating inputs.json: {p}")
    return spec


def astc_bytes(size, block=6):
    return sum(math.ceil(max(1, size >> i)/block)**2*16 for i in range(int(math.log2(size))+1))


def generated_pngs(out):
    return sorted(p for folder in ("planes", "textures", "authoring", "review") for p in (out/folder).glob("*.png"))


def build(out):
    spec = load_inputs()
    for folder in ("planes", "textures", "authoring", "review"):
        (out/folder).mkdir(parents=True, exist_ok=True)
    parents = ["b1_taipei_weathering_field_candidate.png", "b2_taipei_sparse_repairs_r2_candidate.png", "b3_taipei_rain_run_candidate.png"]
    planes = {name: make_plane(Image.open(REPO/PARENT/"processed"/filename), 1024)
              for name, filename in zip(NAMES["facade"][:3], parents)}
    planes["A4_repair_b"] = make_plane(render_repair_svg(PACK/"sources/facade_repair_b.svg", 1024), 1024, authored=True)
    raw = Image.open(PACK/"sources/roof_macro_sheet.png")
    assert raw.width == raw.height and raw.width % 2 == 0
    half = raw.width//2
    for i, name in enumerate(NAMES["roof"]):
        x, y = i%2*half, i//2*half
        # 2px inset excludes the sheet's generated cross-divider. No source upscaling.
        crop = raw.crop((x+2, y+2, x+half-2, y+half-2))
        assert crop.width >= 512
        planes[name] = make_plane(crop, 512)
    for name, im in planes.items(): im.save(out/"planes"/(name+".png"))
    packed = {}
    for family, names in NAMES.items():
        images = [planes[name] for name in names]
        if family == "facade":
            Image.merge("RGBA", images).save(out/"authoring/T_XinyiFacadeAge_1024.png")
            images = [mobile(im) for im in images]
        packed[family] = Image.merge("RGBA", images)
        packed[family].save(out/"textures"/(TEX[family]+".png"))
    previews(out, planes, packed)
    metrics = {name: stats(im) for name, im in planes.items()}
    metrics["repair_a_b_correlation"] = round(float(np.corrcoef(np.asarray(planes["A2_repair_a"]).ravel(), np.asarray(planes["A4_repair_b"]).ravel())[0, 1]), 6)
    manifest = {
        "schema": "acw.material_pack/0", "pack": "xinyi-shared-masks-v1", "status": "offline candidate; pending art approval",
        "base_commit": BASE, "parent_pr": 14, "source_audit": spec,
        "generation_record": "generation.json", "span_metres": [32, 32],
        "independent_new_ai_outputs": 1, "new_ai_panels": 4, "reused_ai_planes": 3, "original_vector_planes": 1,
        "source_planes": 8, "runtime_textures": 2, "imported_into_unreal": False,
        "processing": ["strict grayscale L; recenter non-vector median to 128; clamp 104..152",
                       "wrapped Gaussian sigma 0.16m to remove micro-grain", "1m opposing-edge smoothstep correction",
                       "7 authored value levels 104,112,120,128,136,144,152; close both boundary samples",
                       "facade BOX-downsample 1024 to 512; recouple opposing mobile edges without dropping alpha"],
        "textures": {TEX[k]: {"file": f"textures/{TEX[k]}.png", "size": [512, 512], "mode": "RGBA", "bit_depth": 8,
                                  "channels": dict(zip("RGBA", names)), "srgb": False, "address_u": "wrap", "address_v": "wrap",
                                  "compression_intent": "Masks; ASTC 6x6 candidate; preserve alpha", "alpha_is_opacity": False}
                     for k, names in NAMES.items()},
        "memory_estimate": {"two_512_astc_6x6_full_mips_bytes": 2*astc_bytes(512), "measured_gpu_memory": False},
        "metrics": metrics,
        "limits": ["Numeric tiling PASS is not an art, engine, motion or compression acceptance.",
                   "Native generated metre scale is approximate; broad shapes can repeat within a 32m wall.",
                   "Facade rain-run +V points down in the PNG; verify wall-height-to-V sign, do not rotate/flip vertically.",
                   "PNG derivatives are reproducible; the native image-generation seed/model ID is not exposed.",
                   "UE automatic mips / ASTC / distance captures / performance remain downstream review gates."],
        "outputs": [{"path": str(p.relative_to(out)), "sha256": digest(p), "mode": Image.open(p).mode,
                     "size": list(Image.open(p).size)} for p in generated_pngs(out)],
    }
    (out/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    validate(out)


def check_edges(a, label):
    assert np.array_equal(a[:, 0], a[:, -1]), f"{label}: horizontal boundary mismatch"
    assert np.array_equal(a[0], a[-1]), f"{label}: vertical boundary mismatch"


def check_packed(actual, expected, label):
    assert actual.mode == "RGBA" and actual.size == (512, 512), f"{label}: must retain four 512-square channels"
    for channel, plane in zip("RGBA", expected):
        assert np.array_equal(np.asarray(actual.getchannel(channel)), np.asarray(plane)), f"{label}: {channel} channel packing mismatch"
    check_edges(np.asarray(actual), label)


def validate(out):
    load_inputs()
    m = json.loads((out/"manifest.json").read_text())
    pngs = generated_pngs(out)
    assert len(pngs) == 16  # 8 planes, 2 runtime packs, 1 authoring pack, 5 reviews
    for item in m["outputs"]:
        p = out/item["path"]
        assert digest(p) == item["sha256"], f"Output hash mismatch: {p}"
        with Image.open(p) as im:
            im.load(); assert list(im.size) == item["size"] and im.mode == item["mode"]
            assert not any(k in im.info for k in ("srgb", "gamma", "icc_profile", "transparency")), f"Unexpected colour transform: {p}"
        assert p.read_bytes()[24] == 8, f"Non-8-bit PNG: {p}"
    assert len(m["outputs"]) == len(pngs)
    for family, names in NAMES.items():
        planes = [Image.open(out/"planes"/(name+".png")) for name in names]
        for name, im in zip(names, planes):
            size = 1024 if family == "facade" else 512
            assert im.mode == "L" and im.size == (size, size)
            a = np.asarray(im); check_edges(a, name)
            assert set(np.unique(a)) <= set(LEVELS) and 3 <= len(np.unique(a)) <= 7, f"Invalid authored levels: {name}"
            st = stats(im)
            assert 124 <= st["mean_255"] <= 132 and 1 <= st["std_255"] <= 12, f"Tone/empty mask: {name}: {st}"
            assert max(st["seam_slope_x_max_255"], st["seam_slope_y_max_255"]) <= 16, f"Seam slope: {name}"
            assert st["coarse_8_std_255"] <= 8 and st["coarse_16_std_255"] <= 8, f"Coarse mask too strong: {name}"
        expected = [mobile(im) for im in planes] if family == "facade" else planes
        check_packed(Image.open(out/"textures"/(TEX[family]+".png")), expected, family)
        if family == "facade":
            author = Image.open(out/"authoring/T_XinyiFacadeAge_1024.png")
            assert author.mode == "RGBA" and author.size == (1024, 1024)
            for c, plane in zip("RGBA", planes): assert np.array_equal(np.asarray(author.getchannel(c)), np.asarray(plane))
    assert abs(m["metrics"]["repair_a_b_correlation"]) < .35, "Repair variants correlate too strongly"
    print(json.dumps({"validation": "PASS", "planes": 8, "packed_rgba": 2, "authoring_rgba": 1,
                      "review_sheets": 5, "pngs": len(pngs), "source_hashes": "PASS", "packed_alpha": "PASS"}))


def reproduce(out):
    with tempfile.TemporaryDirectory(prefix="xinyi-masks-") as tmp:
        rebuilt = Path(tmp); build(rebuilt)
        for p in generated_pngs(out):
            other = rebuilt/p.relative_to(out)
            a, b = Image.open(p), Image.open(other)
            assert a.mode == b.mode and np.array_equal(np.asarray(a), np.asarray(b)), f"Reproduction mismatch: {p}"
    print("REPRODUCE PASS: all 16 decoded PNGs match; sources are read-only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--reproduce", action="store_true")
    parser.add_argument("--output", type=Path, default=PACK)
    args = parser.parse_args()
    validate(args.output) if args.validate else build(args.output)
    if args.reproduce: reproduce(args.output)
