"""Phase 2B-C analysis: seam collision (flange variants, micro / exact-line rays, high-speed sweeps, physics drops) and LOD
runtime closure (Landscape border policy, every stitch x chunk LOD combination, chunk checkerboards, automatic-LOD dolly
transitions, crack-mode 300 m/s flights). Raw UE outputs: D:/Users/EDDY/UEIsolated/gate_out/runtime_closure (not committed).
Writes data/ntw/runtime/closure_result.json and docs/evidence/ntw/runtime_closure/*.png.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("ACW_GATE_TERRAIN_RUN_NAME", "joint_ue_local_v3")
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyse_runtime as ar  # noqa: E402

GATE = ar.GATE
RAW = GATE / "runtime_closure"              # LOD matrix, dollies, crack-mode flights (closure run, editor exit 0)
RAW_PHYS = GATE / "runtime_physics_c3"      # FINAL collision configuration (v5 level, EXACT flange) (surface-only complex collision + flange variants):
                                            # traces, micro, sweeps, physics drops with controls / CCD
RAW_TIME = GATE / "runtime_physics"         # clean timing flights (closure-run flights overlapped offline CPU work)
RAW_PROBE = GATE / "runtime_probe_points"
RAW_LOD = GATE / "runtime_closure_lod_v4"     # LOD re-run on the neighbour-skirt terrain (v4) + Landscape distribution policies
RAW_LOD5 = GATE / "runtime_closure_lod_v5"   # v4 + 20 m Xinyi-edge skirt; Landscape distribution x16 / x64
RAW_LOD6 = GATE / "runtime_closure_lod_v6"   # v5 + render apron (+-0.5 m exact strip sunk 2 cm, no collision)
BOX = (304000.0, 2760000.0, 312000.0, 2776000.0)
REPO = ar.REPO
OUT_JSON = REPO / "data/ntw/runtime/closure_result.json"
EVID = REPO / "docs/evidence/ntw/runtime_closure"
VARIANTS = ("none", "w10", "w05")
BALL_R = 0.05


def load(name, raw=None):
    return json.loads(((raw or RAW) / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ collision
def micro_table(T, H):
    tab = defaultdict(Counter)
    for t, h in zip(T, H):
        tab["%s %+.4f" % (t["set"].split("_")[1], t["off"])][h[1] if h else "miss"] += 1
    off = [(t, h) for t, h in zip(T, H) if t["off"] != 0.0]
    return {"table": {k: dict(v) for k, v in sorted(tab.items())}, "exact_line_rays": sum(1 for t in T if t["off"] == 0.0),
            "exact_line_misses": sum(1 for t, h in zip(T, H) if t["off"] == 0.0 and h is None),
            "offline_misses": sum(1 for _, h in off if h is None)}


def exact_ground(ref, x, y):
    """Exact collision surface under (x, y): Landscape triangulation inside the sector, shipped chunk / stitch mesh outside."""
    e, n = ref.enu(np.asarray(x, float), np.asarray(y, float))
    za, _ = ar.landscape_tri_heights(ref.xin, e, n)
    ins = ref.inside(e, n, tol=0.0)
    zm = np.full(len(e), np.nan)
    if (~ins).any():
        zm[~ins] = ref.top_z(np.asarray(x, float)[~ins], np.asarray(y, float)[~ins])
    return np.where(ins, za, zm)


def sweeps(ref, inp, v):
    S = inp["sweeps"]
    H = load("sweeps_%s.json" % v, RAW_PHYS)["hits"]
    miss = [i for i, h in enumerate(H) if h is None]
    by = defaultdict(lambda: [0, 0])
    for i, sw in enumerate(S):
        k = "%s|r%.2f|%s|L%d" % ("corner" if sw["set"].startswith("corner") else "edge", sw["radius_m"], sw["profile"], sw["len_m"])
        by[k][0] += 1
        by[k][1] += H[i] is None
    hit = [(i, h) for i, h in enumerate(H) if h is not None]
    xy = np.array([[h[0] + ar.ORIGIN[0], -h[1] + ar.ORIGIN[1]] for _, h in hit])     # impact point (UE cm -> m already, Y flipped)
    # decode_full stored metres in UE axes: x = E - E0, y = -(N - N0)
    xy = np.array([[h[0] + ar.ORIGIN[0], -h[1] + ar.ORIGIN[1]] for _, h in hit])
    gz = exact_ground(ref, xy[:, 0], xy[:, 1])
    dz = np.array([h[2] for _, h in hit]) - gz
    r_ = np.array([S[i]["radius_m"] for i, _ in hit])
    # line traces hit the surface itself; sphere sweeps report the contact point on the surface
    return {"n": len(S), "misses": len(miss), "miss_examples": [S[i] | {"i": i} for i in miss[:5]],
            "by_class": {k: {"n": a, "misses": b} for k, (a, b) in sorted(by.items())},
            "hit_kinds": dict(Counter(h[3] for _, h in hit)), "initial_overlaps": sum(1 for _, h in hit if h[5]),
            "impact_dz_vs_exact_surface_m": ar.stats(dz.tolist()),
            "impact_dz_line_traces_m": ar.stats(dz[r_ == 0].tolist())}


def drops(ref, v, tag, raw=None, name=None):
    d = load(name or ("drops_%s_%s.json" % (v, tag)), raw)
    res = []
    for D, tr in zip(d["drops"], d["trajectories"]):
        A = np.array(tr)
        x = A[:, 1] + ar.ORIGIN[0]
        y = -A[:, 2] + ar.ORIGIN[1]
        g = exact_ground(ref, x, y)
        pen = (g + BALL_R) - A[:, 3]                       # >0: centre below where it should rest
        last = A[A[:, 0] >= A[-1, 0] - 1.0]
        res.append({"set": D["set"], "t": D["t"], "max_penetration_m": round(float(np.nanmax(pen)), 3),
                    "fell_through": bool(np.nanmax(pen) > 0.5), "final_rest_error_m": round(float(pen[-1]), 4),
                    "travel_m": round(float(math.hypot(x[-1] - x[0], y[-1] - y[0])), 2), "last_second_z_std_m": round(float(last[:, 3].std()), 4),
                    "ground_found": bool(np.isfinite(g).all())})
    return {"v0_mps": d["v0_mps"], "height_m": d["height_m"], "balls": len(res), "fell_through": sum(r["fell_through"] for r in res),
            "max_penetration_m": max(r["max_penetration_m"] for r in res), "max_last_second_z_std_m": max(r["last_second_z_std_m"] for r in res),
            "balls_detail": res}


# ------------------------------------------------------------------------------------------------ LOD / cracks
def classify(ref, cam, xs, ys, Hpoly, max_samples=120):
    """ar.classify_cracks plus the fixed-hole edge (stitch / chunk seam) class."""
    import shapely
    if len(xs) > max_samples:
        k = np.linspace(0, len(xs) - 1, max_samples).astype(int)
        xs, ys = xs[k], ys[k]
    o, d = ar.camera_rays(cam, xs.astype(float), ys.astype(float))
    art = under_test_area_edge(ref, o, d)
    t = np.arange(5.0, 9000.0, 2.0)
    P = o[:, None, :] + t[None, :, None] * d[:, None, :]
    zs, _, _ = ar.surface_z(ref, P[..., 0].ravel(), P[..., 1].ravel())
    zs = zs.reshape(P.shape[:2])
    below = np.nan_to_num(P[..., 2] - zs, nan=1.0) <= 0
    out = Counter()
    x = ref.xin
    hb = Hpoly.exterior
    for k in range(len(xs)):
        if art[k]:
            out["under_test_area_edge"] += 1
            continue
        idx = int(np.argmax(below[k]))
        if not below[k, idx]:
            out["no_reference_hit"] += 1
            continue
        q = P[k, idx]
        e, n = ref.enu(np.array([q[0]]), np.array([q[1]]))
        e, n = float(e[0]), float(n[0])
        if ref.inside(np.array([e]), np.array([n]), tol=0.0)[0]:
            d_in = min(e - x.e0, x.e1 - e, n - x.n0, x.n1 - n)
            if d_in < 6.0:
                out["xinyi_seam"] += 1
                continue
            col, row = (e - x.e0) / x.step, (x.n1 - n) / x.step
            dc = min(col % 126, 126 - col % 126) * x.step
            dr = min(row % 126, 126 - row % 126) * x.step
            out["landscape_component_boundary" if min(dc, dr) < 6.0 else "landscape_interior"] += 1
            continue
        d_out = math.hypot(max(x.e0 - e, 0.0, e - x.e1), max(x.n0 - n, 0.0, n - x.n1))
        if d_out < 6.0:
            out["xinyi_seam"] += 1
        elif float(shapely.distance(shapely.points(q[0], q[1]), hb)) < 12.0:
            out["hole_edge_stitch_chunk"] += 1
        elif shapely.contains_xy(Hpoly, q[0], q[1]):
            out["stitch_interior"] += 1
        else:
            gx = (q[0] - 304000.0) % 1600.0
            gy = (q[1] - 2760000.0) % 1600.0
            out["chunk_seam" if min(gx, 1600 - gx, gy, 1600 - gy) < 12.0 else "chunk_interior"] += 1
    return {k: int(v) for k, v in out.items() if v}, len(xs)


def under_test_area_edge(ref, o, d):
    """Rays from a camera OUTSIDE the two-cell test area that enter it below the terrain at its outer edge see the detector
    plane UNDER the terrain - an artefact of the bounded test area (there is no neighbouring terrain), not a crack."""
    x0, y0, x1, y1 = BOX
    res = np.zeros(len(o), bool)
    for i in range(len(o)):
        ox_, oy_ = o[i, 0], o[i, 1]
        if x0 <= ox_ <= x1 and y0 <= oy_ <= y1:
            continue
        tmin, tmax = 0.0, 1e9
        for a, da, lo, hi in ((ox_, d[i, 0], x0, x1), (oy_, d[i, 1], y0, y1)):
            if abs(da) < 1e-12:
                if not lo <= a <= hi:
                    tmin = 1e18
                continue
            t1, t2 = (lo - a) / da, (hi - a) / da
            tmin, tmax = max(tmin, min(t1, t2)), min(tmax, max(t1, t2))
        if tmin > tmax or tmin > 1e8:
            continue
        p = o[i] + tmin * d[i]
        zs, _, _ = ar.surface_z(ref, np.array([min(max(p[0], x0 + 0.01), x1 - 0.01)]), np.array([min(max(p[1], y0 + 0.01), y1 - 0.01)]))
        res[i] = bool(np.isfinite(zs[0]) and p[2] < zs[0] - 1.0)
    return res


def crack_rows(ref, shots, cams, Hpoly, raw=None):
    rows = []
    for s_ in shots:
        m = ar.magenta((raw or RAW) / "img" / s_["file"])
        ys, xs = np.nonzero(m)
        r = dict(s_, crack_px=int(m.sum()))
        if len(xs):
            cam = cams.get(s_["camera"])
            if cam is not None:
                cls, n = classify(ref, cam, xs, ys, Hpoly)
                r["crack_px_est_by_class"] = {k: round(v * len(xs) / n, 1) for k, v in cls.items()}
            r["bbox"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        rows.append(r)
    return rows


def agg(rows, key):
    g = defaultdict(lambda: {"captures": 0, "with_crack": 0, "crack_px": 0, "by_class": Counter()})
    for r in rows:
        a = g[key(r)]
        a["captures"] += 1
        a["crack_px"] += r["crack_px"]
        a["with_crack"] += r["crack_px"] > 0
        a["by_class"].update(r.get("crack_px_est_by_class", {}))
    return {k: dict(v, by_class={c: round(x, 1) for c, x in sorted(v["by_class"].items())}) for k, v in sorted(g.items())}


# ------------------------------------------------------------------------------------------------ evidence
def tile(path, label, px, w=320, h=180):
    im = Image.open(path).convert("RGB").resize((w, h), Image.LANCZOS)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, w, 14], fill=(0, 0, 0))
    dr.text((3, 1), "%s  crack px=%d" % (label, px), fill=(255, 255, 0) if px else (200, 255, 200))
    return im


def sheet(tiles, cols, path):
    w, h = tiles[0].size
    S = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * h), (20, 20, 20))
    for i, t in enumerate(tiles):
        S.paste(t, ((i % cols) * w, (i // cols) * h))
    S.save(path, optimize=True)
    return path.name


def dolly_chart(rows, path, pols=("none", "border0", "bias")):
    W, Hh, L, R, T = 1100, 420, 70, 220, 30
    im = Image.new("RGB", (W, Hh), "white")
    dr = ImageDraw.Draw(im)
    dr.text((L, 8), "Automatic-LOD dolly (120 m -> 7 km out, 40 m -> 2.5 km up): crack px per frame excl. test-area-edge artefact (sqrt), 6 paths", fill="black")
    pal = {"none": (214, 39, 40), "border0": (255, 127, 14), "bias": (148, 103, 189), "dist4": (31, 119, 180), "dist16": (44, 160, 44),
           "dist64": (23, 190, 207)}
    cols = {p_: pal[p_] for p_ in pols}
    mx = max([r.get("crack_px_real_est", r["crack_px"]) for r in rows] + [1])
    dr.rectangle([L, T, W - R, Hh - 40], outline=(120, 120, 120))
    for pol, c in cols.items():
        paths = sorted({r["path"] for r in rows if r["policy"] == pol})
        for p_ in paths:
            pts = sorted((r["step"], r.get("crack_px_real_est", r["crack_px"])) for r in rows if r["policy"] == pol and r["path"] == p_)
            xy = [(L + (W - R - L) * s / 29.0, Hh - 40 - (Hh - 40 - T) * math.sqrt(v / mx)) for s, v in pts]
            if len(xy) > 1:
                dr.line(xy, fill=c, width=2)
        dr.text((W - R + 10, T + 16 * list(cols).index(pol)), "%s (max %d px)" % (pol, max([r.get("crack_px_real_est", r["crack_px"]) for r in rows if r["policy"] == pol] + [0])), fill=c)
    dr.text((L, Hh - 30), "x: dolly step 0..29 (log distance 120 m .. 7 km); y: sqrt(crack px), top = %d px" % mx, fill="black")
    im.save(path, optimize=True)
    return path.name


def analyse_lod(raw, inp, ref, Hpoly, tag, evid):
    """Crack rows + aggregates + evidence for one LOD session (raw folder)."""
    shots = load("closure_lod.json", raw)
    pols = sorted({s["policy"] for s in shots if s["test"] in ("landscape_policy", "dolly")},
                  key=lambda p_: ["none", "border0", "bias", "dist4", "dist16", "dist64"].index(p_))
    cams = {c["name"]: c for c in inp["cameras"]}
    rows = crack_rows(ref, [s for s in shots if s["test"] != "dolly"], cams, Hpoly, raw)
    drows = []
    for s_ in [s for s in shots if s["test"] == "dolly"]:
        path = next(p_ for p_ in inp["dolly"] if p_["name"] == s_["path"])
        cam = {"loc": path["steps"][s_["step"]]["loc"], "target": path["target"], "fov": path["fov"]}
        m = ar.magenta(raw / "img" / s_["file"])
        ys, xs = np.nonzero(m)
        r = dict(s_, crack_px=int(m.sum()))
        if len(xs):
            cls, n = classify(ref, cam, xs, ys, Hpoly)
            r["crack_px_est_by_class"] = {k: round(v * len(xs) / n, 1) for k, v in cls.items()}
        drows.append(r)
    for r in rows + drows:                               # exclude the test-area artefact (rays entering below the outer edge)
        est = r.get("crack_px_est_by_class", {})
        art = est.get("under_test_area_edge", 0.0)
        r["crack_px_real_est"] = round(max(0.0, r["crack_px"] - art), 1) if r["crack_px"] else 0.0
    lod = {"policies": pols,
           "landscape_policy_auto": agg([r for r in rows if r["test"] == "landscape_policy"], lambda r: r["policy"]),
           "stitch_x_chunk": agg([r for r in rows if r["test"] == "stitch_x_chunk"], lambda r: "T%d_C%d" % (r["stitch_lod"], r["chunk_lod"])),
           "chunk_checkerboard": agg([r for r in rows if r["test"] == "chunk_checkerboard"], lambda r: "chk_" + r["chunk_lod"]),
           "dolly_by_policy": agg(drows, lambda r: r["policy"]),
           "dolly_by_policy_path": agg(drows, lambda r: "%s|%s" % (r["policy"], r["path"]))}
    fl = {}
    for f in sorted((raw / "flights").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        F = d["frames"]
        dt = np.array([r[1] for r in F])
        caps = [c for c in d.get("captures", []) if c.get("crack_mode")]
        px, real, cls_tot = [], [], Counter()
        path = inp["flight"]["paths"][str(d["agl_m"])]
        ux, uy = d["dir"]
        yaw = math.atan2(uy, ux)
        for c in caps:
            m = ar.magenta(raw / "img" / c["file"])
            ys, xs = np.nonzero(m)
            px.append(int(m.sum()))
            if not len(xs):
                real.append(0)
                continue
            sc = c["s_m"] * 100.0
            i = min(int(sc // 5000.0), len(path) - 2)
            f = (sc - i * 5000.0) / 5000.0
            pp = [path[i][k] + f * (path[i + 1][k] - path[i][k]) for k in range(3)]
            loc = [pp[0] - ux * 30000.0, pp[1] - uy * 30000.0, pp[2] + 8000.0]       # as captured (UE cm, yaw from the UE-space dir)
            pit = math.radians(-10.0)
            tgt = [loc[0] + 100000.0 * math.cos(pit) * math.cos(yaw), loc[1] + 100000.0 * math.cos(pit) * math.sin(yaw), loc[2] + 100000.0 * math.sin(pit)]
            cam = {"loc": loc, "target": tgt, "fov": 70.0}
            # magenta whose detector-plane hit is > 7 km from the aircraft (the streaming source) lies beyond the 8 km
            # loading range: unloaded cells, not a crack (no HLOD / far field in this pilot)
            o_, d_ = ar.camera_rays(cam, xs.astype(float), ys.astype(float))
            tp = (-200.0 - o_[:, 2]) / np.where(np.abs(d_[:, 2]) < 1e-9, -1e-9, d_[:, 2])
            hx, hy = o_[:, 0] + tp * d_[:, 0], o_[:, 1] + tp * d_[:, 1]
            px_, py_ = pp[0] / 100.0 + ar.ORIGIN[0], -pp[1] / 100.0 + ar.ORIGIN[1]
            far = np.hypot(hx - px_, hy - py_) > 7000.0
            est = {"beyond_loading_range": float(far.sum())}
            if (~far).any():
                cls, n = classify(ref, cam, xs[~far], ys[~far], Hpoly)
                est.update({k: v * int((~far).sum()) / n for k, v in cls.items()})
            cls_tot.update(est)
            real.append(round(len(xs) - est.get("under_test_area_edge", 0.0) - est.get("beyond_loading_range", 0.0), 1))
        fl[d["tag"]] = {"frames": len(F), "dt_ms_p50": round(float(np.median(dt)), 2), "dt_ms_p95": round(float(np.percentile(dt, 95)), 2),
                        "dt_ms_p99": round(float(np.percentile(dt, 99)), 2), "dt_ms_max": round(float(dt.max()), 2),
                        "ground_presence_0_to_2km": round(float(np.mean([("-" not in r[9][:4]) for r in F])), 4),
                        "crack_mode_captures": len(caps), "crack_mode_captures_with_magenta": sum(1 for v in px if v),
                        "magenta_px_total": sum(px), "magenta_px_max": max(px) if px else None,
                        "real_crack_px_est": round(sum(real), 1), "by_class_est": {k: round(v, 1) for k, v in sorted(cls_tot.items())}}
    seam_cls = ("xinyi_seam", "hole_edge_stitch_chunk", "chunk_seam", "landscape_component_boundary")
    real = lambda a: round(sum(x for c, x in a["by_class"].items() if c != "under_test_area_edge"), 1)  # noqa: E731
    tc = lod["stitch_x_chunk"]
    gate = {"stitch_x_chunk_combos": len(tc), "stitch_x_chunk_crack_px": sum(v["crack_px"] for v in tc.values()),
            "checkerboard_crack_px": {k: v["crack_px"] for k, v in lod["chunk_checkerboard"].items()},
            "checkerboard_real_px_est": {k: real(v) for k, v in lod["chunk_checkerboard"].items()},
            "landscape_policy_auto_crack_px": {k: v["crack_px"] for k, v in lod["landscape_policy_auto"].items()},
            "dolly_crack_px_raw": {k: v["crack_px"] for k, v in lod["dolly_by_policy"].items()},
            "dolly_real_px_est": {k: real(v) for k, v in lod["dolly_by_policy"].items()},
            "dolly_real_by_class": {k: {c: x for c, x in v["by_class"].items() if c != "under_test_area_edge"} for k, v in lod["dolly_by_policy"].items()},
            "crack_flights_magenta_px": {k: v["magenta_px_total"] for k, v in fl.items() if "crackcap" in k},
            "crack_flights_real_px_est": {k: v["real_crack_px_est"] for k, v in fl.items() if "crackcap" in k}}

    # evidence
    evid.mkdir(parents=True, exist_ok=True)
    ev = {}
    byf = {r["file"]: r for r in rows}
    for cam in ("edge_south_250m", "corner_SE", "edge_east_900m"):
        tl = [tile(raw / "img" / ("tc_T%d_C%d_%s.png" % (T, C, cam)), "T%d C%d" % (T, C), byf["tc_T%d_C%d_%s.png" % (T, C, cam)]["crack_px"])
              for T in range(5) for C in range(5)]
        ev["stitch_x_chunk_" + cam] = sheet(tl, 5, evid / ("%s_stitch_x_chunk_%s.png" % (tag, cam)))
    tl = []
    for cam in ("edge_south_250m", "edge_east_900m", "edge_north_900m", "corner_SE"):
        for pol in pols:
            fn = "pol_%s_auto_%s.png" % (pol, cam)
            tl.append(tile(raw / "img" / fn, "%s %s" % (pol, cam), byf[fn]["crack_px"]))
    ev["landscape_policy"] = sheet(tl, len(pols), evid / ("%s_landscape_policy_auto.png" % tag))
    tl = []
    for k in ("chk_0_2", "chk_0_4"):
        for cam in ("edge_south_250m", "corner_SE", "cell_seam_low", "edge_east_900m"):
            fn = "%s_%s.png" % (k, cam)
            if fn in byf:
                tl.append(tile(raw / "img" / fn, "%s %s" % (k, cam), byf[fn]["crack_px"]))
    if tl:
        ev["checkerboard"] = sheet(tl, 4, evid / ("%s_chunk_checkerboard.png" % tag))
    ev["dolly_chart"] = dolly_chart(drows, evid / ("%s_dolly_auto_lod_cracks.png" % tag), pols)
    tl = []
    for pol in (pols[0], pols[-1]):
        for st_ in (0, 8, 14, 20, 26, 29):
            fn = "dolly_%s_south_%02d.png" % (pol, st_)
            r = next(x for x in drows if x["file"] == fn)
            tl.append(tile(raw / "img" / fn, "%s south step %d (%.0f m)" % (pol, st_, r["dist_m"]), r["crack_px"]))
    ev["dolly_south"] = sheet(tl, 6, evid / ("%s_dolly_south.png" % tag))
    for t_ in [t for t in fl if "crackcap" in t]:
        d = json.loads((raw / "flights" / (t_ + ".json")).read_text(encoding="utf-8"))
        caps = d["captures"][::max(1, len(d["captures"]) // 12)][:12]
        tl = [tile(raw / "img" / c["file"], "%s t=%.1fs" % (t_.split("_agl")[0], c["t"]), int(ar.magenta(raw / "img" / c["file"]).sum())) for c in caps]
        ev["flight_" + t_] = sheet(tl, 4, evid / ("%s_flight_%s.png" % (tag, t_)))
    return {"lod": lod, "gate": gate, "flights": fl, "evidence": ev}


def main():
    import shapely
    inp = json.loads((GATE / "gate_inputs_v3p.json").read_text(encoding="utf-8"))
    run = load("runtime.json")
    runner = json.loads((RAW / "runner_runtime.json").read_text(encoding="utf-8")) if (RAW / "runner_runtime.json").exists() else None
    EVID.mkdir(parents=True, exist_ok=True)
    ref = ar.Reference()
    rep_t = json.loads((ar.REPO / "data/generated/ntw/terrain/joint_ue_local_v3/terrain.report.json").read_text(encoding="utf-8"))
    rep_4 = json.loads((ar.REPO / "data/generated/ntw/terrain/joint_ue_local_v4/terrain.report.json").read_text(encoding="utf-8"))
    Hpoly = shapely.box(*rep_t["fixed_hole"]["bounds_epsg3826"])

    col = {}
    for v in VARIANTS:
        tr = load("traces_%s.json" % v, RAW_PHYS)
        mi = load("micro_%s.json" % v, RAW_PHYS)["hits"]
        c = ar.collision(inp, tr, inp["micro_traces"], mi, ref)
        col[v] = {"main_traces": {"gate": c["gate"], "landscape_triangulation": c["landscape_triangulation"],
                                  "expectation_corrections": c["expectation_corrections"],
                                  "sets": {k: {kk: s_[kk] for kk in ("n", "misses", "misses_on_exact_boundary", "wrong_actor", "kinds", "dz_mesh_m",
                                                                     "dz_landscape_vs_triangulation_m")} for k, s_ in c["sets"].items()},
                                  "seam_steps_m": c["seam_steps_m"]},
                  "micro": micro_table(inp["micro_traces"], mi), "sweeps": sweeps(ref, inp, v), "physics": {}}
        for rep_ in (1, 2):
            for key in ("drops", "drops_in", "drops_out"):
                for tg in ("v0", "v100", "v100_ccd"):
                    nm = "phys_r%d_%s_%s_%s.json" % (rep_, v, key, tg)
                    if (RAW_PHYS / nm).exists():
                        d_ = drops(ref, v, tg, RAW_PHYS, nm)
                        col[v]["physics"]["r%d|%s|%s" % (rep_, key, tg)] = {k_: d_[k_] for k_ in ("v0_mps", "height_m", "balls", "fell_through",
                                                                                                 "max_penetration_m", "max_last_second_z_std_m")} | {
                            "fell": [b["set"] + "@%.2f" % b["t"] for b in d_["balls_detail"] if b["fell_through"]]}

    v3 = analyse_lod(RAW, inp, ref, Hpoly, "v3", EVID)
    v4 = analyse_lod(RAW_LOD, json.loads((GATE / "gate_inputs_v4.json").read_text(encoding="utf-8")), ref, Hpoly, "v4", EVID)
    v5 = analyse_lod(RAW_LOD5, json.loads((GATE / "gate_inputs_v4.json").read_text(encoding="utf-8")), ref, Hpoly, "v5", EVID)         if (RAW_LOD5 / "closure_lod.json").exists() else None
    v6 = analyse_lod(RAW_LOD6, json.loads((GATE / "gate_inputs_v4.json").read_text(encoding="utf-8")), ref, Hpoly, "v6", EVID)         if (RAW_LOD6 / "closure_lod.json").exists() else None
    timing = {}
    for raw_, lab in ((RAW_TIME, "physics_session"), (RAW_LOD, "v4_lod_session"), (RAW_LOD5, "v5_lod_session"), (RAW_LOD6, "v6_lod_session")):
        for f in sorted((raw_ / "flights").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if "crackcap" in d["tag"]:
                continue
            dt = np.array([r[1] for r in d["frames"]])
            timing["%s:%s" % (lab, d["tag"])] = {"frames": len(dt), "p50": round(float(np.median(dt)), 2), "p95": round(float(np.percentile(dt, 95)), 2),
                                                 "p99": round(float(np.percentile(dt, 99)), 2), "max": round(float(dt.max()), 2),
                                                 "ground_presence_0_to_2km": round(float(np.mean([("-" not in r[9][:4]) for r in d["frames"]])), 4)}

    w = col["w10"]
    coll_gate = {"flange": "w10 (10 cm each side); w05 equivalent for queries",
                 "main_trace_misses": w["main_traces"]["gate"]["misses"], "wrong_actor": w["main_traces"]["gate"]["wrong_actor"],
                 "micro_exact_line_misses": w["micro"]["exact_line_misses"], "micro_exact_line_rays": w["micro"]["exact_line_rays"],
                 "sweep_misses": w["sweeps"]["misses"], "mesh_dz_max_m": w["main_traces"]["gate"]["mesh_dz_max_m"],
                 "landscape_dz_max_m": w["main_traces"]["gate"]["landscape_dz_max_m"], "seam_step_max_m": w["main_traces"]["gate"]["seam_step_max_m"],
                 "baseline_no_flange": {"main_trace_misses": col["none"]["main_traces"]["gate"]["misses"],
                                        "micro_exact_line_misses": col["none"]["micro"]["exact_line_misses"], "sweep_misses": col["none"]["sweeps"]["misses"]}}
    coll_gate["query_status"] = "PASS" if (coll_gate["main_trace_misses"] == 0 and coll_gate["wrong_actor"] == 0 and coll_gate["micro_exact_line_misses"] == 0
                                           and coll_gate["sweep_misses"] == 0 and coll_gate["mesh_dz_max_m"] <= ar.TH["mesh_dz_max_m"]
                                           and coll_gate["landscape_dz_max_m"] <= ar.TH["landscape_dz_max_m"]
                                           and coll_gate["seam_step_max_m"] <= ar.TH["seam_step_max_m"]) else "FAIL"
    phys = {}
    for v in VARIANTS:
        P_ = col[v]["physics"]
        phys[v] = {"boundary_3m_fell_by_rep": [P_.get("r%d|drops|v0" % r_, {}).get("fell_through") for r_ in (1, 2)],
                   "boundary_3m_fell_points": sorted({x for r_ in (1, 2) for x in P_.get("r%d|drops|v0" % r_, {}).get("fell", [])}),
                   "controls_3m_fell": {k: x["fell_through"] for k, x in P_.items() if "|drops_" in k and k.endswith("|v0")},
                   "v100_no_ccd_fell_max": max(x["fell_through"] for k, x in P_.items() if k.endswith("|v100")),
                   "v100_ccd_fell_max": max(x["fell_through"] for k, x in P_.items() if k.endswith("|v100_ccd"))}
    coll_gate["physics"] = phys
    coll_gate["physics_status"] = "PASS" if (all(x == 0 for x in phys["w10"]["boundary_3m_fell_by_rep"])
                                             and all(x == 0 for x in phys["w10"]["controls_3m_fell"].values())
                                             and phys["w10"]["v100_ccd_fell_max"] == 0) else "FAIL"
    coll_gate["status"] = "PASS" if coll_gate["query_status"] == "PASS" and coll_gate["physics_status"] == "PASS" else (
        "FAIL (queries PASS, physics FAIL)" if coll_gate["query_status"] == "PASS" else "FAIL")

    fin = v6 or v5 or v4
    g4 = fin["gate"]
    pol_ok = [p_ for p_ in fin["lod"]["policies"] if g4["landscape_policy_auto_crack_px"].get(p_) == 0 and g4["dolly_real_px_est"].get(p_, 1) == 0
              and all(v == 0 for k, v in g4["crack_flights_real_px_est"].items() if "_%s_" % p_ in k)]
    lod_gate = {"v3_own_lod_skirts": v3["gate"], "v4_neighbour_skirts": v4["gate"], "v5_neighbour_skirts_20m_edge_skirt": v5["gate"] if v5 else None,
                "v6_plus_render_apron": v6["gate"] if v6 else None,
                "final_configuration": "v6" if v6 else ("v5" if v5 else "v4"), "landscape_policies_with_zero_real_cracks": pol_ok}
    lod_gate["status"] = "PASS" if (g4["stitch_x_chunk_crack_px"] == 0 and all(v == 0 for v in g4["checkerboard_real_px_est"].values()) and pol_ok) else "FAIL"
    probe = load("probe_points.json", RAW_PROBE) if (RAW_PROBE / "probe_points.json").exists() else []
    runs = {}
    for raw_ in (RAW, RAW_PHYS, RAW_TIME, RAW_PROBE, RAW_LOD, RAW_LOD5, RAW_LOD6):
        if (raw_ / "runtime.json").exists():
            rj = json.loads((raw_ / "runtime.json").read_text(encoding="utf-8"))
            rf = sorted(raw_.glob("runner_runtime*.json"))
            rn = json.loads(rf[0].read_text(encoding="utf-8")) if rf else {}
            runs[raw_.name] = {"status": rj.get("status"), "seconds": rj.get("seconds"), "editor_exit_code": rn.get("editor_exit_code"),
                               "terrain_run": rn.get("terrain_run"), "census": [s.get("census") for s in rj["steps"] if s["name"] == "pie_started"]}
    res = {"schema": "ntw.runtime_closure.v1", "engine": "UE 5.8 UnrealEditor.exe PIE (D3D12), isolated project",
           "hardware": "i7-12700, Intel UHD Graphics 770 (integrated) - desktop development PC, NOT mobile",
           "terrain_v3_manifest": rep_t["chunk_manifest_sha256"], "terrain_v4_manifest": rep_4["chunk_manifest_sha256"],
           "fixed_hole": rep_t["fixed_hole"], "neighbour_skirts": rep_4.get("neighbour_skirts"), "runs": runs,
           "collision": col, "collision_gate": coll_gate,
           "probe_points_south055_east010": [{k: x[k] for k in ("name", "type", "r", "flange", "hits")} for x in probe],
           "lod_v3": v3["lod"], "lod_v4": v4["lod"], "lod_v5": v5["lod"] if v5 else None, "lod_v6": v6["lod"] if v6 else None, "lod_gate": lod_gate,
           "flights_v3": v3["flights"], "flights_v4": v4["flights"], "flights_v5": v5["flights"] if v5 else None,
           "flights_v6": v6["flights"] if v6 else None,
           "timing": timing, "evidence": {"v3": v3["evidence"], "v4": v4["evidence"], "v5": v5["evidence"] if v5 else None,
                                          "v6": v6["evidence"] if v6 else None},
           "terrain_runs": {"v3": "joint_ue_local_v3 (fixed hole, own-LOD chunk skirts)", "v4": "joint_ue_local_v4 (+ neighbour chunk skirts)",
                            "v5": "joint_ue_local_v5 (+ 20 m Xinyi-edge skirt; run with gate_inputs_v4.json - identical surfaces)",
                            "v6": "joint_ue_local_v6 = v5 + render apron xinyi_apron_w50.glb (collision flanges unchanged)"},
           "precision": [s for s in run["steps"] if s["name"] == "precision"],
           "not_tested": ["mobile / packaged build", "HLOD", "network", "more than two 8 km cells"]}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"collision_gate": {k: v for k, v in coll_gate.items() if k != "physics"}, "physics": phys, "lod_gate": lod_gate, "timing": timing},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
