"""Taipei Street Reality v0E: storefront plan (ground-floor shop units on commercial frontage).

Every commercial frontage edge (roles 5 / 6 / 7 of urban_identity/frontage_roles.json.gz) of an old-stock building
(low / walk-up / huaxia: the walls xc_wall paints a 騎樓 arcade and a sign band on; never civic, school or rooftop
records) is split into shop units of ~3.6-5.5 m. Each unit gets one category, deterministically (sha256 of the unit
id), with role-dependent weights; ordinary shops stay the majority:

  id  category              role 7  role 6  role 5   lit at night
  1   convenience store     placed separately (below)        always (24 h)
  2   breakfast / soy milk   0.10    0.12    0.07     never (closed by early afternoon)
  3   food (noodle / bento)  0.16    0.16    0.10     0.70
  4   beverage               0.05    0.04    0.03     0.75
  5   pharmacy / clinic      0.09    0.07    0.05     0.55
  6   neighbourhood retail   0.25    0.24    0.25     0.50
  7   ordinary / generic     rest    rest    rest     0.40

Convenience stores are rare anchors placed first: candidate edges are commercial frontages of corner buildings
(role 7, then 6, then 5) and then long role-7 frontages; a candidate is accepted if it is >= 7 m long and at least
CVS_SPACING_M from every accepted store, until one store per CVS_PER_M of commercial frontage. A store takes
8-11 m at the corner end of its edge (the end nearest another street edge of the same building).

Output (consumed by xc_wall through the M_XinyiCity material, one Texture.Load per street-band pixel):
  street/storefront_plan_2048.png  L8, nearest, no mips, over the ground extent (row 0 = north, 1.2207 m / px).
      value = category * 32 + lit * 16 + seed (0..15); 0 = no plan. Each unit is painted as a band 0.15-3.0 m
      outward from its edge (street side), so a facade pixel samples its own unit 1.4 m along the wall normal.
  urban_identity/storefronts.json.gz  acw.storefronts/0: units (edge, building, role, category, lit, seed, ENU
      endpoints), counts and rules.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOOK = REPO / "unreal/Saved/XinyiLook"
E0, E1, N0, N1 = -1500.0, 1000.0, -1000.0, 1500.0          # build_ground.py extent
RES = 2048
OLD_ARCH = {0, 1, 2}
CATS = {1: "convenience", 2: "breakfast", 3: "food", 4: "beverage", 5: "medical", 6: "retail", 7: "ordinary"}
WEIGHTS = {7: [(2, 0.10), (3, 0.16), (4, 0.05), (5, 0.09), (6, 0.25)],
           6: [(2, 0.12), (3, 0.16), (4, 0.04), (5, 0.07), (6, 0.24)],
           5: [(2, 0.07), (3, 0.10), (4, 0.03), (5, 0.05), (6, 0.25)]}
LIT_P = {1: 1.0, 2: 0.0, 3: 0.70, 4: 0.75, 5: 0.55, 6: 0.50, 7: 0.40}
UNIT_M = 4.5
MIN_UNIT_M = 3.0
CVS_SPACING_M = 160.0
CVS_PER_M = 380.0
CVS_LEN = (8.0, 11.0)
BAND = (0.15, 3.0)


def h01(*key):
    return int.from_bytes(hashlib.sha256("|".join(map(str, key)).encode()).digest()[:8], "big") / 2.0 ** 64


def main():
    roles = json.loads(gzip.decompress((LOOK / "urban_identity/frontage_roles.json.gz").read_bytes()))
    look = {}
    with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            look[r["building_id"]] = r
    edges = []
    for b in sorted(roles["buildings"], key=lambda x: x["building_id"]):
        rec = look.get(b["building_id"])
        if rec is None or rec["archetype"] not in OLD_ARCH or rec["flags"] & 8:
            continue
        street = [e for e in b["edges"] if e["role"] >= 3]
        for e in b["edges"]:
            if e["role"] < 5 or e["len"] < MIN_UNIT_M:
                continue
            p0, p1 = np.array(e["p0"], float), np.array(e["p1"], float)
            a = math.radians(e["normal_deg"])
            n = np.array([math.cos(a), math.sin(a)])
            # corner end: the endpoint closest to another street edge of the same building
            best = None
            for o in street:
                if o is e:
                    continue
                for q in (o["p0"], o["p1"]):
                    for k, p in enumerate((p0, p1)):
                        d = float(np.hypot(*(p - np.array(q))))
                        if best is None or d < best[0]:
                            best = (d, k)
            corner_end = best[1] if best is not None and best[0] < 1.5 else None
            edges.append({"bid": b["building_id"], "edge": e["edge"], "part": e.get("part", 0), "role": e["role"],
                          "corner": bool(b["corner"]) and corner_end is not None, "corner_end": corner_end,
                          "p0": p0, "p1": p1, "n": n, "len": float(np.hypot(*(p1 - p0))),
                          "id": "%s|%d|%d" % (b["building_id"], e.get("part", 0), e["edge"])})
    comm_m = sum(e["len"] for e in edges)

    # ---- convenience-store anchors ------------------------------------------------------------------------------
    def rank(e):
        tier = 0 if (e["corner"] and e["role"] == 7) else 1 if (e["corner"] and e["role"] == 6) else \
            2 if (e["corner"] and e["role"] == 5) else 3 if e["role"] == 7 else 9
        return (tier, h01("cvs", e["id"]))
    target = int(round(comm_m / CVS_PER_M))
    cvs = {}
    sites = []
    for e in sorted(edges, key=rank):
        if len(sites) >= target or rank(e)[0] == 9:
            break
        if e["len"] < 7.0:
            continue
        span = min(e["len"], CVS_LEN[0] + (CVS_LEN[1] - CVS_LEN[0]) * h01("cvslen", e["id"]))
        start, end = (e["p0"], e["p1"]) if e["corner_end"] in (None, 0) else (e["p1"], e["p0"])
        d = (end - start) / e["len"]
        mid = start + d * span / 2
        if any(np.hypot(*(mid - s)) < CVS_SPACING_M for s in sites):
            continue
        sites.append(mid)
        cvs[e["id"]] = (start, d, span)

    # ---- shop units ---------------------------------------------------------------------------------------------
    units = []
    for e in edges:
        start, d = e["p0"], (e["p1"] - e["p0"]) / e["len"]
        segs = []
        if e["id"] in cvs:
            s0, dd, span = cvs[e["id"]]
            segs.append((s0, s0 + dd * span, 1))
            rest = e["len"] - span
            if rest >= MIN_UNIT_M:
                segs += [(s0 + dd * span, s0 + dd * span + dd * rest, None)]
        else:
            segs.append((start, e["p1"], None))
        for a, b, fixed in segs:
            L = float(np.hypot(*(b - a)))
            if fixed is not None:
                parts = [(a, b)]
            else:
                k = max(1, int(round(L / UNIT_M)))
                dd = (b - a) / k
                parts = [(a + dd * i, a + dd * (i + 1)) for i in range(k)]
            for i, (ua, ub) in enumerate(parts):
                uid = "%s|%.2f,%.2f" % (e["id"], ua[0], ua[1])
                cat = fixed
                if cat is None:
                    r, acc, cat = h01("cat", uid), 0.0, 7
                    for c, w in WEIGHTS[e["role"]]:
                        acc += w
                        if r < acc:
                            cat = c
                            break
                lit = 1 if h01("lit", uid) < LIT_P[cat] else 0
                seed = int(h01("seed", uid) * 16) & 15
                units.append({"id": uid, "bid": e["bid"], "edge": e["edge"], "role": e["role"], "cat": cat,
                              "lit": lit, "seed": seed, "a": [round(float(ua[0]), 2), round(float(ua[1]), 2)],
                              "b": [round(float(ub[0]), 2), round(float(ub[1]), 2)], "n": e["n"],
                              "len": round(float(np.hypot(*(ub - ua))), 2)})

    # ---- rasterise ----------------------------------------------------------------------------------------------
    px = (E1 - E0) / RES
    img = Image.new("L", (RES, RES), 0)
    dr = ImageDraw.Draw(img)

    def to_px(p):
        return ((p[0] - E0) / px, (N1 - p[1]) / px)
    for u in sorted(units, key=lambda x: x["id"]):
        a, b, n = np.array(u["a"]), np.array(u["b"]), u["n"]
        poly = [a + n * BAND[0], b + n * BAND[0], b + n * BAND[1], a + n * BAND[1]]
        dr.polygon([to_px(p) for p in poly], fill=u["cat"] * 32 + u["lit"] * 16 + u["seed"])
    out = LOOK / "street/storefront_plan_2048.png"
    img.save(out, optimize=True)

    counts = Counter(CATS[u["cat"]] for u in units)
    length = Counter()
    for u in units:
        length[CATS[u["cat"]]] += u["len"]
    lit = Counter(CATS[u["cat"]] for u in units if u["lit"])
    doc = {"schema": "acw.storefronts/0",
           "rules": {"unit_m": UNIT_M, "min_unit_m": MIN_UNIT_M, "weights": {str(k): v for k, v in WEIGHTS.items()},
                     "lit_p": {CATS[k]: v for k, v in LIT_P.items()}, "cvs_spacing_m": CVS_SPACING_M,
                     "cvs_per_m_frontage": CVS_PER_M, "cvs_len_m": CVS_LEN, "band_m": BAND, "eligible":
                     "roles 5-7 on old-stock (low / walk-up / huaxia) non-rooftop buildings"},
           "frontage_m": round(comm_m, 1), "edges": len(edges),
           "units": [{k: v for k, v in u.items() if k != "n"} for u in units],
           "counts": dict(sorted(counts.items())), "length_m": {k: round(v, 1) for k, v in sorted(length.items())},
           "lit_at_night": dict(sorted(lit.items())), "convenience_sites": len(sites)}
    raw = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    (LOOK / "urban_identity/storefronts.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    rep = {k: doc[k] for k in ("frontage_m", "edges", "counts", "length_m", "lit_at_night", "convenience_sites")}
    rep["plan_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    rep["doc_sha256"] = hashlib.sha256(raw).hexdigest()
    (LOOK / "street/storefronts.report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n",
                                                         encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
