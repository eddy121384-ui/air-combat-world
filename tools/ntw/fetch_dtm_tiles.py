"""Fetch MOI 2025 20 m DTM Terrarium z13 tiles (accepted Xinyi transport) covering a world spec, in parallel.

Only tiles with valid_fraction > 0 in the mirror's tile-index are fetched (sea-only tiles are skipped).
Cache: data/generated/ntw/dtm/tiles/<x>_<y>.png (ignored) + a manifest with per-tile sha256.
usage: fetch_dtm_tiles.py --world worlds/north_taiwan_224.json [--threads 8]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pyproj import Transformer

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from dtm import BASE, CACHE, Z  # noqa: E402
from world_spec import WorldSpec  # noqa: E402

INDEX = REPO / "data/generated/ntw/dtm/tile-index.csv"


def tiles_for(spec, pad_deg=0.02):
    t = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)
    x0, y0, x1, y1 = spec.bounds_tm2
    ll = [t.transform(x, y) for x in (x0, x1) for y in (y0, y1)]
    lo0, lo1 = min(p[0] for p in ll) - pad_deg, max(p[0] for p in ll) + pad_deg
    la0, la1 = min(p[1] for p in ll) - pad_deg, max(p[1] for p in ll) + pad_deg
    n = 2 ** Z
    tx = lambda lon: int((lon + 180) / 360 * n)  # noqa: E731
    ty = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)  # noqa: E731
    X0, X1, Y0, Y1 = tx(lo0), tx(lo1), ty(la1), ty(la0)
    rows = csv.DictReader(INDEX.open(encoding="utf-8"))
    return sorted((int(r["x"]), int(r["y"])) for r in rows
                  if X0 <= int(r["x"]) <= X1 and Y0 <= int(r["y"]) <= Y1 and float(r["valid_fraction"]) > 0)


def fetch(xy):
    x, y = xy
    f = CACHE / f"{x}_{y}.png"
    if not f.exists():
        for i in range(4):
            try:
                req = urllib.request.Request(f"{BASE}/{x}/{y}.png", headers={"User-Agent": "air-combat-world/ntw"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                f.write_bytes(data)
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 * (i + 1))
        else:
            return xy, None
    return xy, hashlib.sha256(f.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    spec = WorldSpec.load(a.world)
    CACHE.mkdir(parents=True, exist_ok=True)
    want = tiles_for(spec)
    t0 = time.time()
    with ThreadPoolExecutor(a.threads) as ex:
        res = list(ex.map(fetch, want))
    missing = [list(xy) for xy, h in res if h is None]
    man = {"world": spec.name, "mirror": "yhzkiki/taiwan-dtm-2025-terrarium-z13", "zoom": Z, "tiles": len(want),
           "missing": missing, "seconds": round(time.time() - t0, 1),
           "tiles_sha256": {f"{x}/{y}": h for (x, y), h in res if h}}
    out = REPO / f"data/generated/ntw/dtm/manifest_{spec.name}.json"
    out.write_text(json.dumps(man, indent=0), encoding="utf-8")
    print(json.dumps({k: v for k, v in man.items() if k != "tiles_sha256"}))


if __name__ == "__main__":
    main()
