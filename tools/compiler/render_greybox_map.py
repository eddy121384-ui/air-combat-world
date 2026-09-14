"""Offline greybox readability proof maps (PIL only, no new deps).

Reads WorldModel (source truth, read-only) and renders:
  1. docs/evidence/greybox_topdown.png — top-down footprints colored by the
     SAME deterministic buckets as build_greybox_tile.py (low/mid/high) on a
     dark ground, hero 101 site marked orange. Demonstrates block / road-gap /
     open-space hierarchy a player reads from the air.
  2. docs/evidence/greybox_heights.png — extruded-height histogram by bucket.

These are OFFLINE schematics from canonical data, NOT Unreal renders — they
prove the grouping rule is deterministic and matches the GLB the editor
imports. UE-side evidence comes from headless IMPORT/GREYBOX/BOUNDS logs.
Honest labels are drawn on both images (source + geometry version).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import triangulate  # noqa: E402  (same predicate as the tile builder)
from worldmodel import TAIPEI_101_LONLAT, lonlat_to_enu  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402  (already installed, no new dep)

LOW_MAX = 20.0
MID_MAX = 60.0
C_LOW = (222, 224, 230)
C_MID = (158, 161, 168)
C_HIGH = (77, 79, 87)
C_GROUND = (140, 130, 112)
C_HERO = (217, 140, 51)
C_ROAD_HINT = (56, 58, 56)


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    gen = repo / "data/generated/taipei"
    ev = repo / "docs/evidence"
    ev.mkdir(parents=True, exist_ok=True)
    wm = json.loads((gen / "worldmodel_sample.json").read_text(encoding="utf-8"))
    lon0, lat0 = wm["local_frame"]["origin_lonlat"]

    # --- collect extruded footprints (same skip predicate as tile builder) ---
    items = []  # (height, [rings_enu])
    skipped = 0
    for b in wm["buildings"]:
        if b["suppressed"]:
            continue
        drew = False
        rings = []
        for poly in b["polygons"]:
            for ring, tris in triangulate([poly["footprint_enu"]]):
                if not tris:
                    continue
                rings.append(ring)
                drew = True
        if drew:
            items.append((b["height_m"], rings))
        else:
            skipped += 1
    print(f"extruded buildings drawn: {len(items)}  fully-skipped: {skipped}")

    # --- top-down map ---
    W = H = 1600
    xs = [x for _, rings in items for r in rings for x, _ in r]
    ys = [y for _, rings in items for r in rings for _, y in r]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny)
    pad = span * 0.06
    s = (W - 40) / (span + 2 * pad)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    def px(x, y):
        return ((x - cx) * s + W / 2, H / 2 - (y - cy) * s)

    img = Image.new("RGB", (W, H), C_GROUND)
    d = ImageDraw.Draw(img)
    # painter: low first, then mid, then high (towers on top)
    for h, rings in sorted(items, key=lambda t: t[0]):
        col = C_LOW if h <= LOW_MAX else (C_MID if h <= MID_MAX else C_HIGH)
        for ring in rings:
            pts = [px(x, y) for x, y in ring]
            if len(pts) >= 3:
                d.polygon(pts, fill=col)
    hx, hy = lonlat_to_enu(*TAIPEI_101_LONLAT, lon0, lat0)
    hpx, hpy = px(hx, hy)
    r = 14
    d.ellipse([hpx - r, hpy - r, hpx + r, hpy + r], fill=C_HERO, outline=(255, 255, 255))
    d.text((20, 20), "Xinyi greybox v1 — top-down (OFFLINE schematic from worldmodel_sample.json)", fill=(255, 255, 255))
    d.text((20, 44), f"light<=20m  mid<=60m  dark>60m   orange=Taipei101 site   span ~2.10x2.15km", fill=(255, 255, 255))
    d.text((20, H - 30), "source: data/generated/taipei/worldmodel_sample.json + build_greybox_tile.py buckets", fill=(200, 200, 200))
    img.save(ev / "greybox_topdown.png")
    print("wrote", ev / "greybox_topdown.png")

    # --- height histogram by bucket ---
    HW, HH = 1000, 560
    hist = Image.new("RGB", (HW, HH), (24, 24, 26))
    dh = ImageDraw.Draw(hist)
    bins = [0, 10, 20, 30, 40, 50, 60, 80, 100, 150, 200, 275]
    counts = [0] * (len(bins) - 1)
    for h, _ in items:
        for i in range(len(bins) - 1):
            if bins[i] < h <= bins[i + 1] or (i == 0 and h <= bins[1]):
                counts[i] += 1
                break
    mx = max(counts)
    ox, oy, bw, bh = 80, HH - 80, (HW - 160) // len(counts), HH - 160
    for i, c in enumerate(counts):
        x0 = ox + i * bw + 4
        hgt = int((c / mx) * (bh - 40))
        mid = (bins[i] + bins[i + 1]) / 2
        col = C_LOW if mid <= LOW_MAX else (C_MID if mid <= MID_MAX else C_HIGH)
        dh.rectangle([x0, oy - hgt, x0 + bw - 8, oy], fill=col)
        dh.text((x0, oy + 8), f"{bins[i]}-{bins[i+1]}", fill=(180, 180, 180))
        if c > 0:
            dh.text((x0, oy - hgt - 18), str(c), fill=(255, 255, 255))
    dh.text((20, 20), "Extruded building heights by bucket (OFFLINE, n=5819 target)", fill=(255, 255, 255))
    dh.text((20, 44), "grey = bucket color in GLB + top-down map", fill=(200, 200, 200))
    hist.save(ev / "greybox_heights.png")
    print("wrote", ev / "greybox_heights.png")


if __name__ == "__main__":
    main()
