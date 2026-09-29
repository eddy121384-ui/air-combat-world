"""Generalize the basin-wide WFS building layer into a FAR-LOD product.

Input : far_city_raw.ndjson.gz (tools/lookdev/fetch_far_city.mjs), EPSG:3826
Output: data/lookdev_cache/far_city_generalized.npz
  cells   50 m grid (EPSG:3826 cell index ix, iy): building coverage (0..1),
          area-weighted mean height, 90th-percentile height, mean ground
  towers  every record >= 50 m tall: minimum rotated rectangle
          (cx, cy, w, d, angle_deg), height, ground
Only derived statistics are stored; no footprint is edited or relocated.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

REPO = Path(__file__).resolve().parents[2]
CELL = 50.0
TOWER_M = 50.0


def main(src: Path, out: Path):
    cov = defaultdict(float)
    hsum = defaultdict(float)
    hs = defaultdict(list)
    gsum = defaultdict(float)
    towers = []
    n = 0
    digest = hashlib.sha256()
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        for line in fh:
            digest.update(line.encode())
            r = json.loads(line)
            h = r.get("h")
            if h is None or not math.isfinite(h) or h <= 0:
                continue
            g = r.get("g") or 0.0
            for ring in r["r"]:
                if len(ring) < 4:
                    continue
                p = Polygon(ring)
                if not p.is_valid:
                    p = p.buffer(0)
                if p.is_empty or p.area < 4.0:
                    continue
                n += 1
                c = p.centroid
                key = (int(math.floor(c.x / CELL)), int(math.floor(c.y / CELL)))
                a = p.area
                cov[key] += a
                hsum[key] += a * h
                hs[key].append(h)
                gsum[key] += a * g
                if h >= TOWER_M:
                    m = np.asarray(p.minimum_rotated_rectangle.exterior.coords)[:4]
                    e1, e2 = m[1] - m[0], m[2] - m[1]
                    towers.append((c.x, c.y, float(np.linalg.norm(e1)), float(np.linalg.norm(e2)),
                                   math.degrees(math.atan2(e1[1], e1[0])), h, g))
    keys = sorted(cov)
    ix = np.array([k[0] for k in keys], np.int32)
    iy = np.array([k[1] for k in keys], np.int32)
    area = np.array([cov[k] for k in keys])
    np.savez_compressed(
        out,
        cell_m=np.float64(CELL),
        ix=ix, iy=iy,
        coverage=np.clip(area / (CELL * CELL), 0, 1).astype(np.float32),
        h_mean=np.array([hsum[k] / cov[k] for k in keys], np.float32),
        h_p90=np.array([np.percentile(hs[k], 90) for k in keys], np.float32),
        ground=np.array([gsum[k] / cov[k] for k in keys], np.float32),
        towers=np.asarray(towers, np.float64).reshape(-1, 7),
    )
    meta = {"role": "FAR_LOD_ONLY", "crs": "EPSG:3826", "cell_m": CELL, "tower_threshold_m": TOWER_M,
            "records": n, "cells": len(keys), "towers": len(towers), "raw_sha256": digest.hexdigest(),
            "source": "taipei_vioc:tp_building_height (same WFS layer as the accepted Xinyi source)"}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data/generated/taipei/far_city_raw.ndjson.gz",
         Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data/lookdev_cache/far_city_generalized.npz")
