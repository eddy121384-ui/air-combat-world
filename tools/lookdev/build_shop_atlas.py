"""Taipei horizontal storefront atlas (Taipei Street Reality v0E).

One 2048 x 2048 RGBA atlas for the horizontal shop boards painted by xc_wall in the street band, and the menu
strips inside breakfast shops:
  RGB = sRGB board face, A = emissive mask (lit light-box panel or lit letters; 0 = never lit).

Bins (power-of-two aligned, box-filtered mips never mix cells):
  h4  32 cells 512 x 128  (4:1) fascia: one line, name + trade        y    0..1024 (4 per row)
  h2  16 cells 512 x 256  (2:1) tall board: big trade word + sub line  y 1024..2048 (4 per row)
Every cell keeps a pure background margin of 10 % on the left / right (the shader extends a board wider than
the cell with that colour) and a board rim top / bottom only.

Cell ranges per storefront category are the contract read by xinyi_city.hlsl (xc_shop_cell):
  h4  0..3 convenience store   4..5 breakfast fascia   6..7 breakfast menu strip   8..13 food   14..16 beverage
      17..21 pharmacy / clinic   22..31 neighbourhood retail
  h2  0..3 breakfast   4..5 food   6..7 pharmacy / clinic   8..15 neighbourhood retail

Content: ORIGINAL generic Traditional-Chinese shop identities (two-character name from the v0B pool + a trade
word). No trademarks, no logos, no chain trade dress (convenience stores: white board, ONE stripe from a generic
palette, an invented name + 超商), no political content; the v0B brand / chain blacklist applies.
Fonts: Noto Sans TC / Noto Serif TC (SIL OFL), recorded with SHA-256. Deterministic (fixed seed, 2x supersampled).

Outputs: unreal/Saved/XinyiLook/street/shop_atlas.png, shop_atlas.json
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_sign_atlas import BLACKLIST, NAME_CHARS, OUT, STYLES, find_font, glyph  # noqa: E402

SIZE = 2048
SS = 2
SEED = 20261007
BINS = [("h4", 512, 128, 4, 8, 0), ("h2", 512, 256, 4, 4, 1024)]
# category -> cell ranges (first, count) in h4 / h2 (contract with xinyi_city.hlsl xc_shop_cell)
LAYOUT = {"h4": [("cvs", 4), ("breakfast", 2), ("menu", 2), ("food", 6), ("beverage", 3), ("medical", 5),
                 ("retail", 10)],
          "h2": [("breakfast", 4), ("food", 2), ("medical", 2), ("retail", 8)]}
TRADES = {
    "breakfast": ["早餐", "豆漿", "早餐店", "飯糰", "蛋餅"],
    "food": ["麵店", "牛肉麵", "便當", "滷味", "水餃", "小吃", "自助餐", "米粉湯", "麵館"],
    "beverage": ["茶飲", "飲料", "果汁", "冰品"],
    "medical": ["藥局", "診所", "牙醫診所", "中醫診所", "藥房", "眼科"],
    "retail": ["五金行", "眼鏡", "電器行", "通訊行", "文具", "洗衣", "髮廊", "房屋", "鐘錶", "茶行", "布莊",
               "影印", "機車行", "商行"],
}
H2_BIG = {"breakfast": ["早餐", "豆漿", "早點"], "food": ["麵", "便當", "小吃"], "medical": ["藥局", "牙醫"],
          "retail": ["五金", "眼鏡", "電器", "洗衣", "髮廊", "房屋", "文具", "通訊"]}
H2_SUB = {"breakfast": ["漢堡 蛋餅 奶茶", "燒餅 油條 米漿", "飯糰 豆漿 蘿蔔糕"], "food": ["牛肉麵 水餃 小菜", "排骨 雞腿 素食"],
          "medical": ["健保特約", "處方調劑 健保特約"], "retail": ["專業 老店", "批發 零售", "誠信 服務", "修理 買賣"]}
MENU = ["蛋餅", "漢堡", "吐司", "奶茶", "豆漿", "飯糰", "鐵板麵", "蘿蔔糕", "紅茶", "薯餅", "燒餅", "熱狗"]
STYLE_BY_CAT = {"medical": ["white_blue", "green_white", "white_red", "blue_white", "white_black"],
                "breakfast": ["yellow_red", "white_red", "orange_white", "red_white", "yellow_black"],
                "food": ["red_white", "white_red", "maroon_gold", "yellow_black", "white_black", "orange_white"],
                "beverage": ["teal_white", "green_white", "orange_white", "white_blue"],
                "retail": [s[0] for s in STYLES]}
CVS_STRIPES = [(18, 132, 140), (26, 70, 150), (196, 52, 44), (44, 140, 76)]   # one stripe each, generic


def make_name(rng, used):
    for _ in range(400):
        a, b = rng.choice(NAME_CHARS), rng.choice(NAME_CHARS)
        n = a + b
        if a != b and n not in BLACKLIST and n not in used:
            used.add(n)
            return n
    raise RuntimeError("name pool exhausted")


def line(d, text, x0, x1, cy, size, font, weight, fill):
    """Centre one line of characters between x0 and x1 at cy (square character boxes)."""
    n = len(text)
    s = min(size, (x1 - x0) / max(n, 1))
    for i, ch in enumerate(text):
        cx = (x0 + x1) / 2 + (i - (n - 1) / 2) * s
        if ch != " ":
            glyph(d, ch, cx, cy, s * 0.92, font, weight, fill)


def render(kind, w, h, cat, rng, used, fonts):
    W, H = w * SS, h * SS
    mx = int(W * 0.10)                     # pure-background side margins
    rim = int(H * (0.07 if kind == "h4" else 0.05))
    meta = {"category": cat}
    if cat == "cvs":
        bg, fg = (238, 238, 234), (52, 54, 58)
        stripe = CVS_STRIPES[len(used) % len(CVS_STRIPES)]
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        d.rectangle([0, int(H * 0.70), W, int(H * 0.86)], fill=stripe)
        name = make_name(rng, used) + "超商"
        line(d, name, mx, W * 0.74, H * 0.37, H * 0.46, fonts["sans"], 800, fg)
        line(d, "24H", W * 0.76, W - mx, H * 0.37, H * 0.30, fonts["sans"], 900, stripe)
        mask = Image.new("L", (W, H), 230)
        meta.update(text=name, sub="24H", stripe=list(stripe), lit_mode="box")
        return img.resize((w, h), Image.LANCZOS), mask.resize((w, h), Image.LANCZOS), meta
    style_name = rng.choice(STYLE_BY_CAT[cat if cat != "menu" else "breakfast"])
    _, bg, fg, bd = next(s for s in STYLES if s[0] == style_name)
    if cat == "menu":                      # menu strip: light board, three rows of dishes + prices
        bg, fg, bd = rng.choice([((246, 236, 196), (120, 30, 24), (190, 150, 60)),
                                 ((242, 242, 236), (30, 50, 110), (120, 120, 120))])
    img = Image.new("RGB", (W, H), bg)
    mask = Image.new("L", (W, H), 0)
    d, dm = ImageDraw.Draw(img), ImageDraw.Draw(mask)
    d.rectangle([0, 0, W, rim], fill=bd)
    d.rectangle([0, H - rim, W, H], fill=bd)
    font = fonts["serif"] if cat == "food" and rng.random() < 0.5 else fonts["sans"]
    weight = rng.choice([700, 800, 900])
    lit_mode = rng.choices(["box", "letters", "none"], [5, 3, 2])[0]
    if cat == "menu":
        items = rng.sample(MENU, 9)
        rows = [items[i * 3:(i + 1) * 3] for i in range(3)]
        for r, row in enumerate(rows):
            cy = rim + (r + 0.5) * (H - 2 * rim) / 3
            txt = "  ".join("%s%d" % (it, rng.choice([20, 25, 30, 35, 40, 45, 50])) for it in row)
            from PIL import ImageFont  # noqa: PLC0415
            f = ImageFont.truetype(str(fonts["sans"]), int((H - 2 * rim) / 3 * 0.62))
            try:
                f.set_variation_by_axes([700])
            except Exception:
                pass
            x0, y0, x1, y1 = d.textbbox((0, 0), txt, font=f)
            s = min(1.0, (W - 2 * mx) / max(1, x1 - x0))
            if s < 1.0:
                f = ImageFont.truetype(str(fonts["sans"]), max(8, int((H - 2 * rim) / 3 * 0.62 * s)))
                x0, y0, x1, y1 = d.textbbox((0, 0), txt, font=f)
            d.text((W / 2 - (x1 - x0) / 2 - x0, cy - (y1 - y0) / 2 - y0), txt, font=f, fill=fg)
        lit_mode = "box"
        meta.update(text="/".join(items), sub="", lit_mode=lit_mode, style="menu")
    elif kind == "h4":
        name = make_name(rng, used)
        trade = rng.choice(TRADES[cat])
        text = name + trade
        line(d, text, mx, W - mx, H / 2, (H - 2 * rim) * 0.78, font, weight, fg)
        meta.update(text=text, sub="", lit_mode=lit_mode, style=style_name)
    else:
        big = rng.choice(H2_BIG[cat])
        sub = make_name(rng, used) + " " + rng.choice(H2_SUB[cat])
        line(d, big, mx, W - mx, rim + (H - 2 * rim) * 0.36, (H - 2 * rim) * 0.62, font, weight, fg)
        d.line([(mx, H * 0.68), (W - mx, H * 0.68)], fill=fg, width=max(2, int(H * 0.012)))
        line(d, sub, mx, W - mx, H * 0.82, (H - 2 * rim) * 0.20, fonts["sans"], 700, fg)
        meta.update(text=big, sub=sub, lit_mode=lit_mode, style=style_name)
    if lit_mode == "box":
        dm.rectangle([0, rim, W, H - rim], fill=200)
    elif lit_mode == "letters":            # lit letters: pixels far from the background colour
        a = img.convert("RGB").load()
        mp = mask.load()
        for y in range(rim, H - rim):
            for x in range(W):
                p = a[x, y]
                dd = abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2])
                if dd > 120:
                    mp[x, y] = 230
    return img.resize((w, h), Image.LANCZOS), mask.resize((w, h), Image.LANCZOS), meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    fonts = {"sans": find_font("sans"), "serif": find_font("serif")}
    atlas = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    alpha = Image.new("L", (SIZE, SIZE), 0)
    used = set()
    cells = []
    for kind, w, h, cols, rows, y0 in BINS:
        cats = [c for c, n in LAYOUT[kind] for _ in range(n)]
        assert len(cats) == cols * rows
        for k, cat in enumerate(cats):
            x, y = (k % cols) * w, y0 + (k // cols) * h
            img, mask, meta = render(kind, w, h, cat, rng, used, fonts)
            atlas.paste(img, (x, y))
            alpha.paste(mask, (x, y))
            cells.append({"bin": kind, "index": k, "rect_px": [x, y, w, h], **meta})
    atlas.putalpha(alpha)
    png = OUT / "shop_atlas.png"
    atlas.save(png, optimize=False, compress_level=6)
    layout = {b: [{"category": c, "first": sum(n for _, n in LAYOUT[b][:i]), "count": n}
                  for i, (c, n) in enumerate(LAYOUT[b])] for b in LAYOUT}
    meta = {"schema": "acw.shop_atlas/0", "size": SIZE,
            "bins": [{"bin": b, "cell_px": [w, h], "count": c * r, "y0": y} for b, w, h, c, r, y in BINS],
            "layout": layout, "channels": {"rgb": "sRGB board face", "a": "emissive mask"}, "cells": cells,
            "fonts": {k: {"file": v.name, "sha256": hashlib.sha256(v.read_bytes()).hexdigest(),
                          "license": "SIL Open Font License 1.1 (Noto)"} for k, v in fonts.items()},
            "content_policy": "original generic names; v0B brand / chain blacklist; no logos; convenience stores: "
                              "white board + one generic stripe + invented name; no political content",
            "seed": SEED, "sha256": hashlib.sha256(png.read_bytes()).hexdigest()}
    (OUT / "shop_atlas.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"shop atlas: {len(cells)} cells -> {png} ({png.stat().st_size // 1024} KB) sha {meta['sha256'][:12]}")


if __name__ == "__main__":
    main()
