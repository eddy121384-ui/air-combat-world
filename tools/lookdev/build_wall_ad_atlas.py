"""Taipei large wall-ad atlas v0 (one 2048 x 2048 sRGB atlas for M_XinyiWallAds).

RGB = board face (sRGB), A = night spot-light mask (255 on a printed canvas face, 0 on frames, painted walls and
empty / torn boards: those never light).

Bins are power-of-two aligned so box-filtered mips never mix neighbouring cells (as build_sign_atlas.py):
  T  16 cells 256 x 512  tall board 1:2 (vertical title)          y    0..1024
  S  16 cells 256 x 256  square board / painted wall sign          y 1024..1536
  W   8 cells 512 x 256  wide board 2:1                            y 1536..2048
Cell order (index = id) is the contract read by the material (wallads_uv_code, generated from this metadata).

Content is AUTHORED, not random: a fixed list of fictional Taiwanese large-format ads in the families of the
research (docs/xinyi-wall-ads-identity-research-v0.md §C / §K.7): pre-sale housing, clinics, cram schools /
education, local services, leasing, and aged / ghost boards (faded painted walls, weathered canvas, a bare
frame, a half-removed board). Flat 2-3 colour layouts, one big headline, one simple vector graphic, no fine
print (nothing under ~0.8 m on a 10 m board), saturation capped. Every name is invented; the sign-atlas brand
blacklist plus developer names are rejected; no logos, no phone numbers, no political content; every glyph is
checked against the font (no tofu) and must be Big5-encodable (no Simplified-only leakage).

Each cell records an `art` region (the vector graphic slot) separate from its text regions, so a later pass can
replace selected graphics with generated illustrations while text stays font-rendered.

Fonts: Noto Sans TC / Noto Serif TC (SIL OFL), as the sign atlas. Deterministic (fixed seed, 2x supersampling).
Outputs: unreal/Saved/XinyiLook/wall_ads/wall_ad_atlas.png, wall_ad_atlas.json
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_sign_atlas as sa  # noqa: E402  (font discovery / glyph helper / brand blacklist)

OUT = REPO / "unreal/Saved/XinyiLook/wall_ads"
SIZE = 2048
SS = 2
SEED = 20261008
BINS = [("T", 256, 512, 8, 2, 0), ("S", 256, 256, 8, 2, 1024), ("W", 512, 256, 4, 2, 1536)]
# developer / agency / chain names that must never appear (in addition to the sign-atlas blacklist)
BLACKLIST = sa.BLACKLIST | {"遠雄", "興富發", "華固", "冠德", "長虹", "潤泰", "宏盛", "寶佳", "太子", "鄉林", "皇翔",
                            "達欣", "昇陽", "聯聚", "甲山林", "璞園", "國揚", "富邦", "台北", "信義", "大安",
                            "長庚", "馬偕", "榮總", "台大", "康是美", "屈臣氏", "寶島", "小林", "仁愛", "敦南",
                            "何嘉仁", "長頸鹿", "吉的堡", "地球村", "巨匠", "大碩", "高點", "全家", "統一"}
POLITICAL = {"選", "黨", "票", "總統", "議員", "立委", "市長", "候選"}
MAX_SAT_P90 = 0.70          # 90th-percentile HSV saturation per cell (restrained, never neon)

# palettes (bg, fg, accent); sRGB, saturation <= ~0.65 on large fields
P = {
    "cream_green": ((236, 230, 212), (34, 84, 62), (176, 140, 64)),
    "navy_gold": ((30, 44, 78), (232, 214, 160), (196, 162, 84)),
    "green_cream": ((40, 92, 70), (240, 234, 214), (206, 176, 104)),
    "white_red": ((240, 238, 232), (168, 62, 54), (168, 62, 54)),
    "white_teal": ((240, 241, 238), (40, 110, 116), (60, 120, 180)),
    "white_brown": ((238, 234, 224), (122, 52, 42), (64, 110, 70)),
    "blue_white": ((48, 88, 146), (244, 244, 240), (226, 226, 220)),
    "white_blue": ((238, 239, 236), (44, 78, 140), (178, 64, 56)),
    "yellow_red": ((228, 196, 86), (160, 58, 50), (60, 60, 64)),
    "red_white": ((164, 60, 52), (244, 240, 230), (232, 196, 80)),
    "green_white": ((44, 120, 84), (244, 244, 236), (232, 200, 90)),
    "maroon_gold": ((110, 36, 38), (230, 196, 120), (230, 196, 120)),
    "white_orange": ((240, 238, 230), (186, 108, 62), (60, 60, 64)),
    "red_yellow": ((164, 60, 52), (240, 206, 82), (244, 240, 230)),
    "paint_cream": ((214, 206, 186), (150, 58, 48), (70, 92, 130)),     # painted wall sign base
    "paint_white": ((222, 220, 210), (60, 86, 136), (150, 58, 48)),
}

# ---- authored cells. layout: v (vertical title), h (horizontal), q (square headline)
# age: none | fade (sun-faded canvas) | paint (faded painted wall) | ghost (painted remnant) | frame (bare frame)
#      | torn (half-removed canvas) | blank (weathered empty canvas)
CELLS = [
    # W1 pre-sale / housing
    dict(bin="T", fam="realty", lay="v", pal="cream_green", title="青嵐苑", sub="公園第一排", tag="預售", art="skyline"),
    dict(bin="T", fam="realty", lay="v", pal="navy_gold", title="澄心居", sub="捷運生活圈", tag="接待中心", art="tower"),
    dict(bin="T", fam="realty", lay="v", pal="green_cream", title="森悅", sub="精裝三房", tag="預售中", art="house"),
    dict(bin="W", fam="realty", lay="h", pal="cream_green", title="和光邸", sub="二房 三房 預售", tag="接待中心", art="house"),
    dict(bin="W", fam="realty", lay="h", pal="navy_gold", title="晴川苑", sub="新案公開", tag="預售", art="skyline"),
    dict(bin="S", fam="realty", lay="q", pal="white_red", title="預售", sub="安和新邸", art="house"),
    dict(bin="T", fam="realty", lay="v", pal="white_blue", title="沐光居", sub="兩房景觀宅", tag="預售", art="house"),
    # W2 clinics
    dict(bin="T", fam="medical", lay="v", pal="white_teal", title="康和牙醫", sub="植牙 矯正", art="tooth"),
    dict(bin="T", fam="medical", lay="v", pal="white_brown", title="仁濟中醫", sub="針灸 推拿", art="gourd"),
    dict(bin="S", fam="medical", lay="q", pal="blue_white", title="耳鼻喉科", sub="", art="cross"),
    dict(bin="T", fam="medical", lay="v", pal="blue_white", title="復健科", sub="物理治療", art="cross"),
    dict(bin="W", fam="medical", lay="h", pal="white_blue", title="明德皮膚科", sub="專科醫師", art="cross"),
    dict(bin="T", fam="medical", lay="v", pal="paint_cream", title="中醫", sub="專治跌打損傷", art=None, age="paint"),
    dict(bin="S", fam="medical", lay="q", pal="paint_white", title="齒科", sub="鑲牙", art=None, age="paint"),
    # W3 education
    dict(bin="T", fam="education", lay="v", pal="yellow_red", title="啟明美語", sub="兒童美語 安親", art="book"),
    dict(bin="S", fam="education", lay="q", pal="white_blue", title="數理", sub="國中 高中", art="book"),
    dict(bin="T", fam="education", lay="v", pal="white_red", title="升學數理", sub="國中高中先修", art="pencil"),
    dict(bin="W", fam="education", lay="h", pal="red_white", title="文昇補習班", sub="會考 學測", art="book"),
    dict(bin="T", fam="education", lay="v", pal="green_white", title="才藝安親", sub="課後輔導", art="pencil"),
    # W7 / W10 local services
    dict(bin="S", fam="service", lay="q", pal="white_orange", title="眼鏡", sub="晶亮眼鏡", art="glasses"),
    dict(bin="T", fam="service", lay="v", pal="maroon_gold", title="養生館", sub="足體按摩", art="leaf"),
    dict(bin="W", fam="service", lay="h", pal="green_white", title="平安搬家", sub="專業 快速", art="truck"),
    dict(bin="S", fam="service", lay="q", pal="blue_white", title="冷氣", sub="家電 維修", art=None),
    dict(bin="T", fam="service", lay="v", pal="white_orange", title="汽車美容", sub="洗車 鍍膜", art=None),
    dict(bin="S", fam="service", lay="q", pal="white_red", title="五金", sub="建材 水電", art=None),
    # W4 leasing
    dict(bin="S", fam="leasing", lay="q", pal="red_yellow", title="招租", sub="", art=None),
    dict(bin="T", fam="leasing", lay="v", pal="red_yellow", title="出租", sub="整層辦公", art=None),
    dict(bin="W", fam="leasing", lay="h", pal="white_red", title="店面出租", sub="樓上可分租", art=None),
    # W5 aged / ghost
    dict(bin="T", fam="aged", lay="v", pal="paint_cream", title="旅社", sub="", art=None, age="ghost"),
    dict(bin="S", fam="aged", lay="q", pal="cream_green", title="", sub="", art=None, age="frame"),
    dict(bin="W", fam="aged", lay="h", pal="white_blue", title="新成屋", sub="現場看屋", art="house", age="torn"),
    dict(bin="T", fam="aged", lay="v", pal="green_cream", title="新成屋", sub="兩房 三房", art="house", age="fade"),
    dict(bin="S", fam="aged", lay="q", pal="paint_white", title="冷氣", sub="", art=None, age="ghost"),
    dict(bin="W", fam="aged", lay="h", pal="white_teal", title="", sub="", art=None, age="blank"),
]
AGED = {"paint", "ghost", "frame", "torn", "fade", "blank"}
PAINTED = {"paint", "ghost"}
STEEL = (78, 80, 82)


# ------------------------------------------------------------------ checks ---
def tofu_signature(font):
    m = font.getmask("")
    return (m.size, bytes(m))


def check_text(cells, fonts):
    """Every character renders with a real glyph and is Big5 (Traditional) encodable; no blacklisted name."""
    problems = []
    for i, c in enumerate(cells):
        for txt in (c.get("title", ""), c.get("sub", ""), c.get("tag", "")):
            for bad in BLACKLIST | POLITICAL:
                if bad in txt:
                    problems.append((i, txt, "blacklist:" + bad))
            for ch in txt:
                if ch == " ":
                    continue
                try:
                    ch.encode("big5")
                except UnicodeEncodeError:
                    problems.append((i, ch, "not_big5"))
                for kind, path in fonts.items():
                    f = sa.load_font(path, 64, 700)
                    m = f.getmask(ch)
                    if (m.size, bytes(m)) == tofu_signature(f) or m.getbbox() is None:
                        problems.append((i, ch, "missing_glyph_" + kind))
    return problems


# ------------------------------------------------------------------- art ---
def draw_art(d, kind, box, col):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    s = min(w, h)
    if kind == "house":
        b = s * 0.8
        bx0, by1 = cx - b / 2, cy + b * 0.42
        d.polygon([(bx0, by1), (bx0, cy - b * 0.05), (cx, cy - b * 0.45), (bx0 + b, cy - b * 0.05), (bx0 + b, by1)],
                  fill=col)
    elif kind == "skyline":
        rng = random.Random(7)
        n = 6
        bw = w * 0.86 / n
        for k in range(n):
            hh = h * rng.uniform(0.35, 0.95)
            xx = x0 + w * 0.07 + k * bw
            d.rectangle([xx + bw * 0.08, y1 - hh, xx + bw * 0.92, y1], fill=col)
    elif kind == "tower":
        tw = s * 0.34
        d.rectangle([cx - tw / 2, y0 + h * 0.08, cx + tw / 2, y1], fill=col)
        d.rectangle([cx - tw * 1.25, y0 + h * 0.45, cx - tw * 0.6, y1], fill=col)
        d.rectangle([cx + tw * 0.6, y0 + h * 0.3, cx + tw * 1.2, y1], fill=col)
    elif kind == "tooth":
        r = s * 0.36
        d.ellipse([cx - r, cy - r * 1.05, cx + r, cy + r * 0.35], fill=col)
        d.polygon([(cx - r, cy - r * 0.2), (cx - r * 0.75, cy + r * 1.05), (cx - r * 0.25, cy + r * 1.05),
                   (cx, cy + r * 0.35), (cx + r * 0.25, cy + r * 1.05), (cx + r * 0.75, cy + r * 1.05),
                   (cx + r, cy - r * 0.2)], fill=col)
    elif kind == "cross":
        a, b = s * 0.36, s * 0.12
        d.rectangle([cx - a, cy - b, cx + a, cy + b], fill=col)
        d.rectangle([cx - b, cy - a, cx + b, cy + a], fill=col)
    elif kind == "leaf":
        r = s * 0.36
        d.ellipse([cx - r * 0.55, cy - r, cx + r * 0.55, cy + r], fill=col)
        d.line([(cx, cy - r * 0.8), (cx, cy + r * 1.2)], fill=(240, 236, 226), width=max(2, int(s * 0.03)))
    elif kind == "gourd":
        r = s * 0.2
        d.ellipse([cx - r * 0.8, cy - r * 1.75, cx + r * 0.8, cy - r * 0.15], fill=col)
        d.ellipse([cx - r * 1.25, cy - r * 0.55, cx + r * 1.25, cy + r * 1.95], fill=col)
        d.rectangle([cx - r * 0.12, cy - r * 2.2, cx + r * 0.12, cy - r * 1.6], fill=col)
    elif kind == "book":
        a = s * 0.38
        d.polygon([(cx - a, cy - a * 0.55), (cx, cy - a * 0.35), (cx, cy + a * 0.65), (cx - a, cy + a * 0.45)], fill=col)
        d.polygon([(cx + a, cy - a * 0.55), (cx + a * 0.08, cy - a * 0.35), (cx + a * 0.08, cy + a * 0.65),
                   (cx + a, cy + a * 0.45)], fill=col)
    elif kind == "pencil":
        a = s * 0.4
        d.polygon([(cx - a * 0.18, cy - a), (cx + a * 0.18, cy - a), (cx + a * 0.18, cy + a * 0.55), (cx, cy + a),
                   (cx - a * 0.18, cy + a * 0.55)], fill=col)
    elif kind == "glasses":
        r = s * 0.2
        lw = max(3, int(s * 0.06))
        d.ellipse([cx - r * 2.3, cy - r, cx - r * 0.3, cy + r], outline=col, width=lw)
        d.ellipse([cx + r * 0.3, cy - r, cx + r * 2.3, cy + r], outline=col, width=lw)
        d.line([(cx - r * 0.3, cy - r * 0.2), (cx + r * 0.3, cy - r * 0.2)], fill=col, width=lw)
    elif kind == "truck":
        a = s * 0.42
        d.rectangle([cx - a * 1.3, cy - a * 0.55, cx + a * 0.35, cy + a * 0.35], fill=col)
        d.polygon([(cx + a * 0.42, cy - a * 0.25), (cx + a * 0.95, cy - a * 0.25), (cx + a * 1.25, cy + a * 0.05),
                   (cx + a * 1.25, cy + a * 0.35), (cx + a * 0.42, cy + a * 0.35)], fill=col)
        for wx in (cx - a * 0.9, cx + a * 0.8):
            d.ellipse([wx - a * 0.18, cy + a * 0.22, wx + a * 0.18, cy + a * 0.58], fill=(40, 40, 42))


# ---------------------------------------------------------------- layouts ---
def text_column(d, txt, cx, top, bot, maxw, font, fill):
    n = max(len(txt), 1)
    s = min(maxw, (bot - top) / n)
    for i, ch in enumerate(txt):
        sa.glyph(d, ch, cx, top + (i + 0.5) * (bot - top) / n, s * 0.94, font[0], font[1], fill)
    return s


def text_row(d, txt, cx, cy, maxw, maxh, font, fill):
    chars = [c for c in txt]
    n = max(len(chars), 1)
    s = min(maxh, maxw / n)
    for i, ch in enumerate(chars):
        if ch != " ":
            sa.glyph(d, ch, cx + (i - (n - 1) / 2) * s, cy, s * 0.92, font[0], font[1], fill)
    return s


def render(c, w, h, fonts):
    W, H = w * SS, h * SS
    bg, fg, ac = P[c["pal"]]
    age = c.get("age", "none")
    painted = age in PAINTED
    img = Image.new("RGB", (W, H), bg)
    mask = Image.new("L", (W, H), 0 if painted or age in ("frame", "blank") else 255)
    d = ImageDraw.Draw(img)
    fr = 0 if painted else int(min(W, H) * 0.025)               # steel frame ~0.2-0.3 m on a 8-12 m board
    serif = c["fam"] in ("medical",) and "中醫" in c["title"] or c["fam"] == "aged"
    title_font = (fonts["serif" if serif else "sans"], 900)
    sub_font = (fonts["sans"], 700)
    regions = {}
    ix0, iy0, ix1, iy1 = fr, fr, W - fr, H - fr
    if painted:                                                   # painted border line instead of a frame
        lw = max(2, int(min(W, H) * 0.02))
        d.rectangle([lw * 2, lw * 2, W - 1 - lw * 2, H - 1 - lw * 2], outline=fg, width=lw)
    iw, ih = ix1 - ix0, iy1 - iy0
    if c["lay"] == "v":
        band = 0
        if c.get("tag"):
            band = ih * 0.12                                      # tag bar at the bottom
            d.rectangle([ix0, iy1 - band, ix1, iy1], fill=ac)
            text_row(d, c["tag"], (ix0 + ix1) / 2, iy1 - band / 2, iw * 0.84, band * 0.7, sub_font,
                     bg if sum(ac) < 400 else fg)
            regions["tag"] = [ix0, iy1 - band, ix1, iy1]
        art_h = ih * 0.24 if c.get("art") else 0
        if art_h:
            ab = [ix0 + iw * 0.12, iy1 - band - art_h, ix1 - iw * 0.12, iy1 - band - ih * 0.02]
            draw_art(d, c["art"], ab, fg if c["art"] not in ("tooth", "cross") else ac)
            regions["art"] = ab
        top, bot = iy0 + ih * 0.05, iy1 - band - art_h - ih * 0.04
        if c.get("sub"):
            text_column(d, c["sub"].replace(" ", ""), ix0 + iw * 0.20, top + ih * 0.03, bot, iw * 0.22, sub_font, fg)
            regions["sub"] = [ix0, top, ix0 + iw * 0.36, bot]
            if c["title"]:
                text_column(d, c["title"], ix0 + iw * 0.63, top, bot, iw * 0.56, title_font, fg)
        elif c["title"]:
            text_column(d, c["title"], (ix0 + ix1) / 2, top, bot, iw * 0.70, title_font, fg)
        regions["title"] = [ix0 + iw * 0.36, top, ix1, bot]
    elif c["lay"] == "h":
        art_w = iw * 0.30 if c.get("art") else 0
        if art_w:
            ab = [ix0 + iw * 0.03, iy0 + ih * 0.12, ix0 + art_w, iy1 - ih * 0.12]
            draw_art(d, c["art"], ab, fg if c["art"] not in ("tooth", "cross") else ac)
            regions["art"] = ab
        tx0 = ix0 + art_w + iw * 0.02
        tcx = (tx0 + ix1) / 2
        tw = ix1 - tx0 - iw * 0.04
        if c.get("tag"):
            th = ih * 0.2
            d.rectangle([tx0 + tw * 0.25, iy1 - th - ih * 0.06, tx0 + tw * 0.98, iy1 - ih * 0.06], fill=ac)
            text_row(d, c["tag"], tx0 + tw * 0.615, iy1 - th / 2 - ih * 0.06, tw * 0.62, th * 0.72, sub_font,
                     bg if sum(ac) < 400 else fg)
            regions["tag"] = [tx0 + tw * 0.25, iy1 - th - ih * 0.06, tx0 + tw * 0.98, iy1 - ih * 0.06]
        if c["title"]:
            text_row(d, c["title"], tcx, iy0 + ih * (0.34 if c.get("sub") else 0.5), tw, ih * 0.46, title_font, fg)
            regions["title"] = [tx0, iy0, ix1, iy0 + ih * 0.6]
        if c.get("sub"):
            if c.get("tag"):
                text_row(d, c["sub"], tcx, iy0 + ih * 0.64, tw * 0.8, ih * 0.13, sub_font, fg)
            else:
                text_row(d, c["sub"], tcx, iy0 + ih * 0.72, tw * 0.6, ih * 0.2, sub_font, fg)
            regions["sub"] = [tx0, iy0 + ih * 0.55, ix1, iy0 + ih * 0.8]
    else:  # q: square headline (2 chars large, or 4 chars as 2 x 2), sub line below
        t = c["title"]
        art_h = ih * 0.26 if c.get("art") and len(t) <= 2 else 0
        if art_h:
            ab = [ix0 + iw * 0.3, iy0 + ih * 0.05, ix1 - iw * 0.3, iy0 + art_h]
            draw_art(d, c["art"], ab, fg if c["art"] not in ("tooth", "cross") else ac)
            regions["art"] = ab
        sub_h = ih * 0.18 if c.get("sub") else 0
        if t:
            if len(t) <= 2:
                text_row(d, t, (ix0 + ix1) / 2, iy0 + art_h + (ih - sub_h - art_h) * 0.52, iw * 0.84,
                         (ih - sub_h - art_h) * (0.78 if art_h else 0.62), title_font, fg)
            else:
                half = (len(t) + 1) // 2
                for r, part in enumerate((t[:half], t[half:])):
                    text_row(d, part, (ix0 + ix1) / 2, iy0 + (ih - sub_h) * (0.32 + 0.38 * r), iw * 0.80,
                             (ih - sub_h) * 0.36, title_font, fg)
            regions["title"] = [ix0, iy0, ix1, iy1 - sub_h]
        if sub_h:
            d.line([(ix0 + iw * 0.12, iy1 - sub_h), (ix1 - iw * 0.12, iy1 - sub_h)], fill=fg, width=max(2, int(W * 0.012)))
            text_row(d, c["sub"], (ix0 + ix1) / 2, iy1 - sub_h * 0.5, iw * 0.8, sub_h * 0.62, sub_font, fg)
            regions["sub"] = [ix0, iy1 - sub_h, ix1, iy1]
    if fr:
        d.rectangle([0, 0, W - 1, H - 1], outline=STEEL, width=fr)
        mask_d = ImageDraw.Draw(mask)
        mask_d.rectangle([0, 0, W - 1, H - 1], outline=0, width=fr)
    img, mask = age_cell(img, mask, c, age, fr)
    img = img.resize((w, h), Image.LANCZOS)
    mask = mask.resize((w, h), Image.LANCZOS)
    regions = {k: [round(v[0] / W, 4), round(v[1] / H, 4), round(v[2] / W, 4), round(v[3] / H, 4)]
               for k, v in regions.items()}
    return img, mask, regions


# ---------------------------------------------------------------- ageing ---
def noise(rng, w, h, sx, sy=None):
    """Smooth value noise with cell size sx x sy supersampled px (no texel-scale speckle: it would shimmer)."""
    sy = sy or sx
    a = np.array([[rng.random() for _ in range(max(2, w // sx + 2))] for _ in range(max(2, h // sy + 2))], np.float32)
    im = Image.fromarray((a * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(im, np.float32) / 255.0


def age_cell(img, mask, c, age, fr):
    if age == "none":
        return img, mask
    rng = random.Random("%s|%s|%s" % (SEED, c["title"], c["bin"]))
    a = np.asarray(img, np.float32) / 255.0
    H, W = a.shape[:2]
    lum = (a * [0.3, 0.59, 0.11]).sum(axis=2, keepdims=True)
    bg = np.array(P[c["pal"]][0], np.float32) / 255.0
    yy = np.linspace(0.0, 1.0, H)[:, None, None]
    streak = noise(rng, W, H, 16, 160)[:, :, None]     # vertical rain streaks
    blot = noise(rng, W, H, 70)[:, :, None]
    if age == "fade":                                   # sun-faded canvas: desaturated, lighter, top-down rain streaks
        a = a * 0.35 + (lum * np.array([1.05, 1.0, 0.9]) * 0.75 + 0.22) * 0.65
        a *= 1.0 - np.clip(streak * 1.5 - 0.9, 0, 1) * 0.25 * (1.0 - yy * 0.6)
        a *= 1.0 - np.clip(yy - 0.75, 0, 1) * 0.5      # grimy bottom
    elif age in ("paint", "ghost"):                     # paint on render: lettering faded into the wall colour
        k = 0.55 if age == "paint" else 0.22            # remaining contrast of the lettering
        a = bg + (a - bg) * k
        wall = np.array([0.70, 0.67, 0.60], np.float32)
        a = a * (1.0 - np.clip(blot * 1.8 - 1.0, 0, 1)[:, :, :1] * 0.8) + \
            wall * np.clip(blot * 1.8 - 1.0, 0, 1)[:, :, :1] * 0.8     # flaked patches back to bare render
        a *= 1.0 - np.clip(streak * 1.4 - 0.8, 0, 1) * 0.18
        a *= 1.0 - np.clip(yy - 0.8, 0, 1) * 0.4
    elif age == "frame":                                # stripped board: pale backing panels, a ghost of the old print
        a[:] = np.array([0.74, 0.73, 0.70])
        a *= 0.94 + blot * 0.08
        inner = (slice(int(H * 0.16), int(H * 0.84)), slice(int(W * 0.12), int(W * 0.88)))
        a[inner] *= np.array([0.93, 0.95, 0.97])        # where the old canvas shaded the backing
        x = W // 2
        a[:, x - 1:x + 2] *= 0.82                       # one panel joint, sub-metre: fades out in the mips
        a *= 1.0 - np.clip(streak * 1.4 - 0.7, 0, 1) * 0.28 * np.array([0.65, 0.85, 1.0])   # rust bleed (warm)
    elif age == "torn":                                 # half-removed canvas: lower right strip gone, lattice behind
        a = a * 0.7 + (lum * 0.85 + 0.1) * 0.3
        edge = 0.45 + 0.08 * noise(rng, W, H, 30)
        cols = np.linspace(0, 1, W)[None, :]
        gone = (np.linspace(0, 1, H)[:, None] > edge + (0.55 - cols) * 0.45)
        back = np.ones_like(a) * np.array([0.58, 0.57, 0.55])
        for k in (1, 2):
            back[:, int(W * k / 3) - fr // 2:int(W * k / 3) + fr // 2 + 1] = np.array(STEEL) / 255.0
        a = np.where(gone[:, :, None], back, a)
        m = np.asarray(mask, np.float32)
        mask = Image.fromarray(np.where(gone, 0, m).astype(np.uint8))
    elif age == "blank":                                # weathered empty canvas with a faint leftover print
        a = np.ones_like(a) * np.array([0.80, 0.80, 0.77]) * (0.92 + blot * 0.12)
        a *= 1.0 - np.clip(streak * 1.5 - 0.85, 0, 1) * 0.22
    a[:fr, :] = np.array(STEEL) / 255.0 if fr else a[:fr, :]
    if fr:
        a[-fr:, :], a[:, :fr], a[:, -fr:] = (np.array(STEEL) / 255.0,) * 3
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)), mask


def sat_p90(img):
    a = np.asarray(img.convert("RGB"), np.float32) / 255.0
    mx, mn = a.max(axis=2), a.min(axis=2)
    s = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-3), 0.0)
    return float(np.percentile(s, 90))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fonts = {"sans": sa.find_font("sans"), "serif": sa.find_font("serif")}
    problems = check_text(CELLS, fonts)
    if problems:
        raise SystemExit("wall-ad text check failed: %s" % problems)
    atlas = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    alpha = Image.new("L", (SIZE, SIZE), 0)
    slots = {b: [] for b, *_ in BINS}
    base = 0
    for b, w, h, cols, rows, y0 in BINS:
        slots[b] = [(base + k, (k % cols) * w, y0 + (k // cols) * h, w, h) for k in range(cols * rows)]
        base += cols * rows
    used = {b: 0 for b in slots}
    cells = []
    for c in CELLS:
        cid, x, y, w, h = slots[c["bin"]][used[c["bin"]]]
        used[c["bin"]] += 1
        img, mask, regions = render(c, w, h, fonts)
        s90 = sat_p90(img)
        if s90 > MAX_SAT_P90:
            raise SystemExit("cell %d (%s) too saturated: p90 %.2f" % (cid, c["title"], s90))
        atlas.paste(img, (x, y))
        alpha.paste(mask, (x, y))
        age = c.get("age", "none")
        cells.append({"id": cid, "bin": c["bin"], "rect_px": [x, y, w, h],
                      "uv_rect": [x / SIZE, y / SIZE, (x + w) / SIZE, (y + h) / SIZE], "aspect_hw": h / w,
                      "family": c["fam"], "title": c["title"], "sub": c.get("sub", ""), "tag": c.get("tag", ""),
                      "palette": c["pal"], "art": c.get("art"), "age": age, "aged": age in AGED,
                      "painted": age in PAINTED, "lit_ok": age == "none" and c["fam"] != "leasing",
                      "regions": regions, "sat_p90": round(s90, 3)})
    atlas.putalpha(alpha)
    png = OUT / "wall_ad_atlas.png"
    atlas.save(png, optimize=False, compress_level=6)
    meta = {"schema": "acw.wall_ad_atlas/0", "size": SIZE,
            "bins": [{"bin": b, "cell_px": [w, h], "count": c * r, "cols": c, "y0": y, "first_id": slots[b][0][0]}
                     for b, w, h, c, r, y in BINS],
            "channels": {"rgb": "sRGB board face", "a": "night spot-light mask (canvas faces only)"},
            "cells": cells,
            "fonts": {k: {"file": v.name, "sha256": hashlib.sha256(v.read_bytes()).hexdigest(),
                          "license": "SIL Open Font License 1.1 (Noto)"} for k, v in fonts.items()},
            "content_policy": "authored fictional names; brand / developer / chain blacklist; no logos; no phone "
                              "numbers; no political content; glyphs checked against the font; Big5 (Traditional) only",
            "seed": SEED, "sha256": hashlib.sha256(png.read_bytes()).hexdigest()}
    (OUT / "wall_ad_atlas.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fam = {}
    for c in cells:
        fam[c["family"]] = fam.get(c["family"], 0) + 1
    print("wall-ad atlas: %d cells %s aged %d -> %s (%d KB) sha %s" % (
        len(cells), fam, sum(c["aged"] for c in cells), png, png.stat().st_size // 1024, meta["sha256"][:12]))


if __name__ == "__main__":
    main()
