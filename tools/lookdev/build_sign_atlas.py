"""Taipei street signage atlas (Street & Facade Identity v0B).

One compact 2048 x 2048 RGBA atlas for every projecting street sign:
  RGB = sRGB sign face, A = emissive mask (lit light-box panel or lit letters; 0 = never lit).

Bins are power-of-two aligned so box-filtered mips never mix neighbouring cells:
  v4  32 cells 128 x 512   narrow vertical blade (1:4), 3-4 stacked characters     y    0..1024
  v2   8 cells 256 x 512   wide vertical light box (1:2), big name + side column   y 1024..1536
  sq  16 cells 256 x 256   small projecting box (1:1), one or two characters        y 1536..2048
Cell order (index = id) is the contract read by xinyi_city.hlsl xc_street_uv.

Content: ORIGINAL generic Traditional-Chinese business identities (two-character auspicious name + a
trade word: 診所 / 牙醫 / 藥局 / 補習 / 房屋 / 小吃 / 麵 / 美髮 / 電器 / 通訊 / 五金 / 眼鏡 / 停車場 ...).
No trademarks, no logos, no political content; a blacklist rejects names that collide with well-known
Taiwanese chains / brands. Restrained colour families (red, white, blue, green, yellow, navy, maroon,
orange) - no neon palette. Ageing / fading and lit-or-not are per-instance shader parameters, not cells.

Font: Noto Sans TC / Noto Serif TC (SIL Open Font License), variable weight; font files and their SHA-256
are recorded in the metadata. Rendering is deterministic (fixed seed, 2x supersampled, Lanczos).

Outputs: unreal/Saved/XinyiLook/street/sign_atlas.png, sign_atlas.json
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "unreal/Saved/XinyiLook/street"
SIZE = 2048
SS = 2                       # supersampling factor
SEED = 20261006
FONT_DIRS = [Path("C:/Windows/Fonts"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
             Path("/usr/share/fonts/opentype/noto"), Path("/usr/share/fonts/truetype/noto")]
FONT_FILES = {"sans": ["NotoSansTC-VF.ttf", "NotoSansCJK-Bold.ttc", "NotoSansTC-Bold.otf"],
              "serif": ["NotoSerifTC-VF.ttf", "NotoSerifCJK-Bold.ttc", "NotoSerifTC-Bold.otf"]}

BINS = [("v4", 128, 512, 16, 2, 0), ("v2", 256, 512, 8, 1, 1024), ("sq", 256, 256, 8, 2, 1536)]

NAME_CHARS = "永福安康仁和興順大新金寶美華德明豐吉昌盛益合泰隆元長成光正宏全利祥慶滿春"
# two-character names that are (or read as) well-known chains / brands / institutions: never generated
BLACKLIST = {"信義", "永慶", "住商", "全家", "統一", "大樹", "杏一", "丁丁", "長庚", "台大", "和泰", "國泰", "富邦",
             "中信", "玉山", "新光", "遠東", "大同", "聲寶", "燦坤", "全國", "三商", "光泉", "義美", "全聯", "寶雅",
             "長榮", "華南", "合庫", "台新", "永豐", "元大", "泰山", "大成", "統元", "金山", "全利", "長春"}

# category -> (trade suffixes for v4 / v2, single-character box glyphs, weight)
CATEGORIES = {
    "clinic":   (["診所", "牙醫", "中醫", "內科", "小兒科"], ["醫"], 3),
    "pharmacy": (["藥局", "藥房"], ["藥"], 2),
    "tutoring": (["美語", "數理", "補習班", "文理"], ["書"], 2),
    "realty":   (["房屋", "不動產", "地產"], ["屋"], 2),
    "snack":    (["小吃", "麵館", "水餃", "牛肉麵", "便當"], ["麵", "食"], 3),
    "restaurant": (["餐廳", "熱炒", "火鍋"], ["食"], 2),
    "beauty":   (["美髮", "美容", "髮廊"], ["髮"], 2),
    "barber":   (["理髮", "男士理容"], ["剪"], 1),
    "appliance": (["電器", "家電"], ["電"], 1),
    "phone":    (["通訊", "手機"], ["機"], 1),
    "retail":   (["五金", "眼鏡", "鐘錶", "文具", "商行", "布莊"], ["五金"], 3),
    "office":   (["會計", "企業社", "事務所"], ["會"], 1),
    "hotel":    (["旅社", "商旅"], ["宿"], 1),
    "parking":  (["停車場"], ["P"], 1),
}

# restrained Taipei sign colour families: (name, panel, text, border)
STYLES = [
    ("red_white", (186, 32, 36), (246, 242, 232), (130, 22, 26)),
    ("white_red", (236, 233, 224), (176, 26, 32), (176, 26, 32)),
    ("white_blue", (234, 233, 226), (28, 62, 140), (28, 62, 140)),
    ("white_black", (232, 230, 222), (30, 30, 30), (60, 60, 60)),
    ("blue_white", (30, 72, 150), (242, 242, 236), (18, 44, 100)),
    ("green_white", (24, 112, 72), (242, 242, 232), (14, 74, 46)),
    ("yellow_black", (236, 196, 46), (36, 30, 24), (150, 110, 20)),
    ("yellow_red", (238, 204, 60), (178, 28, 30), (160, 120, 24)),
    ("navy_yellow", (24, 34, 66), (238, 198, 64), (238, 198, 64)),
    ("maroon_gold", (118, 28, 32), (230, 190, 100), (230, 190, 100)),
    ("orange_white", (222, 108, 34), (248, 244, 236), (160, 70, 20)),
    ("teal_white", (20, 104, 112), (240, 242, 236), (12, 70, 76)),
]
STYLE_BY_CAT = {"clinic": ["white_blue", "white_red", "green_white", "blue_white", "white_black"],
                "pharmacy": ["green_white", "white_red", "blue_white", "white_blue"],
                "parking": ["blue_white"],
                "office": ["white_black", "navy_yellow", "white_blue"],
                "realty": ["red_white", "yellow_red", "orange_white", "white_red"],
                "hotel": ["maroon_gold", "navy_yellow", "white_black"]}


def find_font(kind):
    for d in FONT_DIRS:
        for name in FONT_FILES[kind]:
            p = d / name
            if p.is_file():
                return p
    raise SystemExit(f"no OFL Noto {kind} TC font found in {FONT_DIRS}")


def load_font(path, px, weight):
    f = ImageFont.truetype(str(path), px)
    try:
        f.set_variation_by_axes([weight])
    except Exception:             # static (non-variable) font file: use as is
        pass
    return f


def glyph(draw, ch, cx, cy, box, font_path, weight, fill):
    """Draw one character centred in a box x box square (tight ink bounds)."""
    f = load_font(font_path, int(box), weight)
    x0, y0, x1, y1 = draw.textbbox((0, 0), ch, font=f)
    w, h = x1 - x0, y1 - y0
    scale = box * 0.92 / max(w, h, 1)
    if scale < 0.999:
        f = load_font(font_path, max(8, int(box * scale)), weight)
        x0, y0, x1, y1 = draw.textbbox((0, 0), ch, font=f)
        w, h = x1 - x0, y1 - y0
    draw.text((cx - w / 2 - x0, cy - h / 2 - y0), ch, font=f, fill=fill)


def make_name(rng, used):
    for _ in range(200):
        a, b = rng.choice(NAME_CHARS), rng.choice(NAME_CHARS)
        n = a + b
        if a != b and n not in BLACKLIST and n not in used:
            used.add(n)
            return n
    raise RuntimeError("name pool exhausted")


def render_cell(kind, w, h, cat, text, sub, style, lit_mode, fonts, rng):
    W, H = w * SS, h * SS
    _, bg, fg, bd = style
    img = Image.new("RGB", (W, H), bd)
    mask = Image.new("L", (W, H), 0)
    d, dm = ImageDraw.Draw(img), ImageDraw.Draw(mask)
    edge = int(min(W, H) * 0.045)                         # board frame
    d.rectangle([edge, edge, W - 1 - edge, H - 1 - edge], fill=bg)
    if lit_mode == "box":
        dm.rectangle([edge, edge, W - 1 - edge, H - 1 - edge], fill=200)
    font_path, weight = fonts
    ink = []
    if kind == "sq":
        if len(text) == 1:
            glyph(d, text, W / 2, H * 0.44, W * 0.62, font_path, weight, fg)
            ink.append((W / 2, H * 0.44, W * 0.62))
            if sub:                                        # small line under the big character
                n = len(sub)
                s = min(W * 0.78 / n, H * 0.17)
                for i, ch in enumerate(sub):
                    cx = W / 2 + (i - (n - 1) / 2) * s
                    glyph(d, ch, cx, H * 0.84, s * 0.9, font_path, weight, fg)
                    ink.append((cx, H * 0.84, s * 0.9))
        else:                                              # two characters side by side
            s = W * 0.40
            for i, ch in enumerate(text[:2]):
                cx = W / 2 + (i - 0.5) * s * 1.05
                glyph(d, ch, cx, H / 2, s, font_path, weight, fg)
                ink.append((cx, H / 2, s))
    elif kind == "v4":
        n = len(text)
        band = 0
        if rng.random() < 0.45:                            # coloured top band (decor, store number area)
            band = int(H * 0.08)
            d.rectangle([edge, edge, W - 1 - edge, edge + band], fill=fg)
        top, bot = edge + band + H * 0.03, H - edge - H * 0.03
        s = min(W * 0.80, (bot - top) / n)
        for i, ch in enumerate(text):
            cy = top + (i + 0.5) * (bot - top) / n
            glyph(d, ch, W / 2, cy, s, font_path, weight, fg)
            ink.append((W / 2, cy, s))
    else:  # v2: big name column on the right, small trade column on the left (right-to-left reading)
        n = len(text)
        top, bot = edge + H * 0.05, H - edge - H * 0.05
        s = min(W * 0.52, (bot - top) / n)
        for i, ch in enumerate(text):
            cy = top + (i + 0.5) * (bot - top) / n
            glyph(d, ch, W * 0.62, cy, s, font_path, weight, fg)
            ink.append((W * 0.62, cy, s))
        d.line([(W * 0.30, top), (W * 0.30, bot)], fill=fg, width=max(2, int(W * 0.012)))
        m = len(sub)
        s2 = min(W * 0.20, (bot - top) * 0.7 / max(m, 1))
        for i, ch in enumerate(sub):
            cy = top + (bot - top) * 0.15 + (i + 0.5) * s2 * 1.1
            glyph(d, ch, W * 0.16, cy, s2, font_path, weight, fg)
            ink.append((W * 0.16, cy, s2))
    if lit_mode == "letters":                              # LED / neon-tube letters only
        lum = img.convert("L")
        bgl = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        fgl = 0.299 * fg[0] + 0.587 * fg[1] + 0.114 * fg[2]
        lo, hi = (bgl, fgl) if fgl > bgl else (fgl, bgl)
        t = lum.point(lambda v: 0 if hi - lo < 1 else int(max(0.0, min(1.0, (v - lo) / (hi - lo))) * 255)
                      if fgl > bgl else int(max(0.0, min(1.0, (hi - v) / (hi - lo))) * 255))
        inner = Image.new("L", (W, H), 0)
        ImageDraw.Draw(inner).rectangle([edge, edge, W - 1 - edge, H - 1 - edge], fill=255)
        mask = Image.composite(t, mask, inner)
    img = img.resize((w, h), Image.LANCZOS)
    mask = mask.resize((w, h), Image.LANCZOS)
    return img, mask


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    fonts = {"sans": find_font("sans"), "serif": find_font("serif")}
    atlas = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    alpha = Image.new("L", (SIZE, SIZE), 0)
    cats = sorted(CATEGORIES)
    weights = [CATEGORIES[c][2] for c in cats]
    used = set()
    cells = []
    for kind, w, h, cols, rows, y0 in BINS:
        for k in range(cols * rows):
            cid = len(cells)
            x, y = (k % cols) * w, y0 + (k // cols) * h
            cat = rng.choices(cats, weights)[0] if kind != "sq" or k % 8 else "parking"   # one P box per row
            suffixes, box_glyphs, _ = CATEGORIES[cat]
            name = make_name(rng, used)
            sub = ""
            if kind == "v4":
                suf = rng.choice([s for s in suffixes if len(s) <= 2] or suffixes)
                text = (name + suf)[:4] if cat != "parking" else "停車場"
            elif kind == "v2":
                text = rng.choice(suffixes) if len(rng.choice(suffixes)) >= 2 else name + rng.choice(suffixes)
                text = text if len(text) >= 3 else name + text
                sub = name + "專業" if cat in ("clinic", "tutoring", "realty") else name + "老店"
            else:
                g = rng.choice(box_glyphs)
                text = g if len(g) == 1 else g[:2]
                sub = "" if cat == "parking" and rng.random() < 0.5 else (name if len(g) == 1 else "")
                if cat == "parking":
                    sub = "停車場"
            style_name = rng.choice(STYLE_BY_CAT.get(cat, [s[0] for s in STYLES]))
            style = next(s for s in STYLES if s[0] == style_name)
            lit_mode = rng.choices(["box", "letters", "none"], [5, 3, 2])[0]
            fam = "serif" if (cat in ("hotel", "snack", "restaurant", "office") and rng.random() < 0.5) else "sans"
            weight = rng.choice([700, 800, 900])
            img, mask = render_cell(kind, w, h, cat, text, sub, style, lit_mode, (fonts[fam], weight), rng)
            atlas.paste(img, (x, y))
            alpha.paste(mask, (x, y))
            cells.append({"id": cid, "bin": kind, "rect_px": [x, y, w, h],
                          "uv_rect": [x / SIZE, y / SIZE, (x + w) / SIZE, (y + h) / SIZE],
                          "aspect": round(h / w, 3), "category": cat, "text": text, "sub": sub,
                          "style": style_name, "lit_mode": lit_mode, "font": fam, "weight": weight})
    atlas.putalpha(alpha)
    png = OUT / "sign_atlas.png"
    atlas.save(png, optimize=False, compress_level=6)
    meta = {"schema": "acw.sign_atlas/0", "size": SIZE, "bins": [{"bin": b, "cell_px": [w, h], "count": c * r, "y0": y}
                                                                    for b, w, h, c, r, y in BINS],
            "channels": {"rgb": "sRGB sign face", "a": "emissive mask (lit panel / letters)"},
            "cells": cells,
            "fonts": {k: {"file": v.name, "sha256": hashlib.sha256(v.read_bytes()).hexdigest(),
                          "license": "SIL Open Font License 1.1 (Noto)"} for k, v in fonts.items()},
            "content_policy": "original generic names; brand / chain blacklist; no logos; no political content",
            "seed": SEED, "sha256": hashlib.sha256(png.read_bytes()).hexdigest()}
    (OUT / "sign_atlas.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"sign atlas: {len(cells)} cells -> {png} ({png.stat().st_size // 1024} KB) sha {meta['sha256'][:12]}")


if __name__ == "__main__":
    main()
