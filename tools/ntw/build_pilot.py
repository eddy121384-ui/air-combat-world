"""NTW whitebox pilot: real-data tiled whitebox for a 5 x 5 (2.5 km) block of 500 m tiles.

Reuses the ACCEPTED Xinyi geometry stack unchanged (tools/citygen_v2 + tools/compiler):
  source repair (GEOS make_valid structure) -> deterministic 500 m owner tile (vertex-mean centroid, floor grid)
  -> tile-local float32 footprint quantisation -> GEOS revalidate -> GEOS constrained Delaunay
  -> trimesh extrusion -> GLB export + reload -> strict float32/float64 QA (+ world-space check).
Only the INPUT ADAPTERS (Taipei WFS EPSG:3826 / Overture lon-lat) and the FRAME (NTW = EPSG:3826 - fixed origin)
differ from build_full_xinyi.py. Nothing in tools/citygen_v2 is modified.

Accounting differs from the Xinyi fail-closed gate in one declared way: source parts that GEOS cannot turn into
polygonal area (collapsed / zero-area) and Overture rows flagged is_underground are LEDGERED with a reason
(`source_rejected` / `excluded_underground`) instead of failing the gate; any mesh/serialization/QA failure still
fails the pilot. unaccounted_parts must be 0.

usage: build_pilot.py --pilot A_taipei_main_station --out <dir>   (refuses to overwrite)
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import shapely
import trimesh
from pyproj import Geod, Transformer
from shapely import affinity
from shapely.geometry import Polygon, mapping, shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(REPO / "tools/citygen_v2"))
sys.path.insert(0, str(HERE))

from geometry import extrude_geos_polygon, repair_worldmodel_polygon  # noqa: E402
from serialization_space import prepare_footprint, tile_origin, tile_transform  # noqa: E402
from strict_qa import strict_mesh_gate  # noqa: E402

import frame  # noqa: E402
from heights import derive_overture_height, derive_wfs_height  # noqa: E402

CACHE = REPO / "data/generated/ntw"
# Phase 2B: repair-fragment policy. DEFAULT OFF = the accepted strict fail-closed behaviour. When enabled, a non-largest
# GEOS make_valid fragment smaller than max_area_m2 whose float32 tile-local footprint collapses is LEDGERED (id + area) instead
# of failing the build. Enabling it for production requires the locked representative + full-Xinyi regression (AGENTS.md).
FRAGMENT_POLICY = {"enabled": False, "max_area_m2": 0.01}
# Runtime-gate round (PR #23 review P0 #2): CANDIDATE float32-grid snap fallback (tools/ntw/quantization_fallback.py).
# DEFAULT OFF. Runs ONLY after the accepted prepare_footprint has FAILED a part, so every build that passes today is
# byte-identical with it enabled; accepted gates are re-run unchanged on the snapped part. Production use needs approval.
QUANT_FALLBACK = {"enabled": False}
# DIAGNOSTIC ONLY (default off): still serialise / write the tiles of the PASSING parts when some part failed, so shard
# mechanics (tile identity, ownership, culling) can be measured. The gate result stays FAIL and every failure is reported;
# never use it for a production build.
DIAGNOSTIC_WRITE_ON_FAILURE = {"enabled": False}
TILE_M = 500.0
BLOCK_TILES = 5
GEOD = Geod(ellps="WGS84")
TO_TM2 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
FROM_TM2 = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)


def pilot_cfg(pid):
    cfg = json.loads((HERE / "pilots.json").read_text(encoding="utf-8"))
    for p in cfg["pilots"]:
        if p["id"] == pid:
            return p
    raise SystemExit(f"unknown pilot {pid}")


def block_of(cfg):
    e, n = TO_TM2.transform(*cfg["center_lonlat"])
    x, y = frame.tm2_to_ntw(e, n)
    ix, iy = int(math.floor(x / TILE_M)) - BLOCK_TILES // 2, int(math.floor(y / TILE_M)) - BLOCK_TILES // 2
    return ix, iy  # SW tile index; block spans [ix*500, (ix+5)*500)


def vmean(ring):
    """Source-part centroid exactly as WorldModel: arithmetic mean of ring vertices (incl. closing vertex)."""
    a = np.asarray(ring, dtype=float)
    return float(a[:, 0].mean()), float(a[:, 1].mean())


def iter_polys(geom):
    if geom["type"] == "Polygon":
        yield geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        yield from geom["coordinates"]


def load_wfs(cfg, bx0, by0, bx1, by1):
    feats = []
    ox, oy = frame.NTW_ORIGIN_TM2
    for line in (CACHE / "wfs_taipei_citywide.ndjson").open(encoding="utf-8"):
        r = json.loads(line)
        polys = []
        for si, poly in enumerate(iter_polys(r["geometry"])):
            rings = [[(x - ox, y - oy) for x, y in ring] for ring in poly]
            cx, cy = vmean(rings[0])
            if bx0 <= cx < bx1 and by0 <= cy < by1:
                polys.append((si, rings))
        if not polys:
            continue
        h, src, ground = derive_wfs_height(r["p"])
        feats.append({"id": r["id"], "provider": "taipei_wfs_tp_building_height", "record_id": r["id"],
                      "height_m": h, "height_source": src, "ground_elev_m": ground, "polys": polys, "excluded": None})
    return feats


def load_overture(cfg, bx0, by0, bx1, by1):
    import duckdb
    f = Path(cfg["overture_parquet"]) if cfg.get("overture_parquet") else CACHE / f"ovt_{cfg['id']}.parquet"
    if not f.exists():
        raise SystemExit(f"missing {f}; run fetch_overture_footprints.py (see pilots.json bbox)")
    rows = duckdb.connect().execute(
        f"select id, wkb, height, num_floors, is_underground, class, src from read_parquet('{f.as_posix()}') order by id").fetchall()
    feats = []
    for rid, wkb, h, nf, ug, cls, src in rows:
        g = shapely.from_wkb(bytes(wkb))
        co = shapely.get_coordinates(g)
        x, y = TO_TM2.transform(co[:, 0], co[:, 1])
        g = shapely.set_coordinates(g, np.column_stack([x - frame.NTW_ORIGIN_TM2[0], y - frame.NTW_ORIGIN_TM2[1]]))
        polys = []
        for si, poly in enumerate(iter_polys(mapping(g))):
            rings = [[tuple(p) for p in ring] for ring in poly]
            cx, cy = vmean(rings[0])
            if bx0 <= cx < bx1 and by0 <= cy < by1:
                polys.append((si, rings))
        if not polys:
            continue
        hm, hs = derive_overture_height(h, nf)
        feats.append({"id": rid, "provider": f"overture:{src}", "record_id": rid, "height_m": hm, "height_source": hs,
                      "ground_elev_m": None, "polys": polys, "excluded": "underground" if ug else None})
    return feats


def load_mixed(cfg, bx0, by0, bx1, by1):
    """Runtime-gate round: provider ownership by admin polygon. WFS (surveyed) owns every source part whose vertex-mean centroid
    lies inside cfg['wfs_owner_polygon_ntw_wkb'] (Taipei City, NTW frame); Overture owns the parts outside it. The non-owner
    copy is LEDGERED as excluded (never silently dropped). One feature per source part so ownership is per part."""
    owner = shapely.from_wkb(bytes.fromhex(cfg["wfs_owner_polygon_ntw_wkb"]))
    shapely.prepare(owner)
    out = []
    for loader, own_inside in ((load_wfs, True), (load_overture, False)):
        for f in loader(cfg, bx0, by0, bx1, by1):
            for si, rings in f["polys"]:
                cx, cy = vmean(rings[0])
                g = dict(f, polys=[(si, rings)])
                if bool(shapely.contains_xy(owner, cx, cy)) != own_inside:
                    g["excluded"] = g["excluded"] or ("provider_owner_overture" if own_inside else "provider_owner_wfs")
                out.append(g)
    return out


LOADERS = {"taipei_wfs": load_wfs, "overture": load_overture, "mixed_wfs_overture": load_mixed}


def rss_mb():
    try:
        import psutil  # noqa: F401
        return psutil.Process().memory_info().rss / 1048576
    except Exception:
        return None


def build(pid, out_dir: Path, bounds_ntw=None, suppress_ids=None, cfg=None):
    """Pilot block build. Phase 2B: `bounds_ntw` (500 m-aligned NTW bounds) builds an arbitrary shard with the same code,
    and `suppress_ids` skips source ids owned by an accepted L3 sector (Xinyi, PR #22 identity rule) - ledgered, never hidden."""
    t0 = time.perf_counter()
    cfg = cfg or pilot_cfg(pid)
    if bounds_ntw is None:
        ix0, iy0 = block_of(cfg)
        bx0, by0, bx1, by1 = ix0 * TILE_M, iy0 * TILE_M, (ix0 + BLOCK_TILES) * TILE_M, (iy0 + BLOCK_TILES) * TILE_M
    else:
        bx0, by0, bx1, by1 = bounds_ntw
        if any(abs(v / TILE_M - round(v / TILE_M)) > 1e-9 for v in bounds_ntw):
            raise ValueError("shard bounds must be on the 500 m tile grid")
        ix0, iy0 = int(round(bx0 / TILE_M)), int(round(by0 / TILE_M))
    if out_dir.exists():
        raise FileExistsError(out_dir)
    out_dir.mkdir(parents=True)
    feats = LOADERS[cfg["provider"]](cfg, bx0, by0, bx1, by1)
    if suppress_ids:
        for f in feats:
            if f["id"] in suppress_ids:
                f["excluded"] = "suppressed_l3_xinyi"
    src_hash = hashlib.sha256(json.dumps(
        [(f["id"], f["height_m"], [[r for r in p[1]] for p in f["polys"]]) for f in feats], separators=(",", ":")).encode()).hexdigest()

    ledger, failures, tiles = [], [], defaultdict(list)
    repair_outcomes, reasons = Counter(), Counter()
    source_parts = excluded = rejected = 0
    prov = Counter()
    hsrc = Counter()
    for b in feats:
        for si, rings in b["polys"]:
            source_parts += 1
            prov[b["provider"]] += 1
            row = {"building_id": b["id"], "provider": b["provider"], "polygon_index": si, "height_m": b["height_m"],
                   "height_source": b["height_source"], "ground_elev_m": b["ground_elev_m"], "status": None, "tile": None, "failures": []}
            if b["excluded"]:
                row["status"] = "excluded_" + b["excluded"]
                excluded += 1
                ledger.append(row)
                continue
            hsrc[b["height_source"]] += 1
            rec = {"footprint_enu": rings[0], "holes_enu": rings[1:]}
            parts, rep = repair_worldmodel_polygon(rec)
            repair_outcomes[rep["status"]] += 1
            if not parts:
                row["status"], row["reason"] = "source_rejected", rep.get("reason")
                reasons[rep.get("reason")] += 1
                rejected += 1
                ledger.append(row)
                continue
            origin = tile_origin(vmean(rings[0]))
            key = frame.cell_key(origin[0] // TILE_M, origin[1] // TILE_M)
            row["tile"] = key
            pend, bad = [], False
            for ri, rp in enumerate(parts):
                try:
                    sparts, fg = prepare_footprint(rp, origin)
                except Exception as exc:  # noqa: BLE001
                    sparts, fg = [], {"pass": False, "failures": [f"footprint_exception:{type(exc).__name__}:{exc}"]}
                if not fg["pass"]:
                    largest = max(range(len(parts)), key=lambda i: parts[i].area)
                    if (FRAGMENT_POLICY["enabled"] and ri != largest and rp.area < FRAGMENT_POLICY["max_area_m2"]
                            and all("collapsed" in x for x in fg["failures"])):
                        # explicit, global, OPT-IN policy (default off): a GEOS repair fragment below GLB float32 resolution
                        row.setdefault("ledgered_fragments", []).append(
                            {"repaired_part": ri, "area_m2": float(rp.area), "reason": "repair_fragment_below_serialization_resolution"})
                        continue
                    if QUANT_FALLBACK["enabled"]:
                        import quantization_fallback as qf
                        sparts, frep = qf.fallback(rp, origin, ri == largest)
                        frep = {k: v for k, v in frep.items() if k != "pass_"} | {"pass": bool(frep.get("pass_")), "repaired_part": ri,
                                                                                  "accepted_failures": list(fg["failures"])}
                        row.setdefault("quantization_fallback", []).append(frep)
                        if frep["pass"] and frep.get("ledgered"):
                            row.setdefault("ledgered_fragments", []).append(
                                {"repaired_part": ri, "area_m2": float(rp.area), "reason": frep["reason"]})
                            continue
                        if not frep["pass"]:
                            bad = True
                            row["failures"] += [f"r{ri}:footprint:{x}" for x in fg["failures"]]
                            row["failures"] += [f"r{ri}:fallback:{x}" for x in frep.get("failures", [])]
                            continue
                    else:
                        bad = True
                        row["failures"] += [f"r{ri}:footprint:{x}" for x in fg["failures"]]
                        continue
                for sj, sp in enumerate(sparts):
                    name = f"{b['id']}_p{si}_r{ri}_s{sj}"
                    try:
                        mesh = extrude_geos_polygon(sp, float(b["height_m"]))
                        gate = strict_mesh_gate(mesh, sp, float(b["height_m"]), precision="float64")
                        xy = np.asarray(mesh.vertices)[:, [0, 2]]
                        if not np.array_equal(xy, xy.astype(np.float32).astype(np.float64)):
                            gate["failures"].append("mesher_introduced_nonserializable_xy")
                            gate["pass"] = False
                    except Exception as exc:  # noqa: BLE001
                        mesh, gate = None, {"pass": False, "failures": [f"mesh_exception:{type(exc).__name__}:{exc}"]}
                    if not gate["pass"] or mesh is None:
                        bad = True
                        row["failures"] += [f"r{ri}s{sj}:float64:{x}" for x in gate["failures"]]
                        continue
                    pend.append({"node_name": name, "mesh": mesh, "building_id": b["id"], "height_m": float(b["height_m"]),
                                 "origin": [float(origin[0]), float(origin[1])], "transform": tile_transform(origin),
                                 "expected_local": mapping(sp),
                                 "expected_enu": mapping(affinity.translate(sp, xoff=origin[0], yoff=origin[1])),
                                 "vertices": int(gate["vertices"]), "triangles": int(gate["triangles"]), "holes": len(sp.interiors),
                                 "repair_status": rep["status"], "provider": b["provider"]})
            if bad or not pend:
                row["status"] = "failed_pre_serialization"
                failures.append(dict(row))
                ledger.append(row)
                continue
            row["status"], row["components"] = "ready", len(pend)
            row["vertices"], row["triangles"] = sum(e["vertices"] for e in pend), sum(e["triangles"] for e in pend)
            ledger.append(row)
            tiles[key].extend(pend)

    tile_bytes, tile_reports = {}, []
    if not failures or DIAGNOSTIC_WRITE_ON_FAILURE["enabled"]:
        for key in sorted(tiles):
            entries = tiles[key]
            scene = trimesh.Scene()
            for e in entries:
                scene.add_geometry(e["mesh"], geom_name=e["node_name"], node_name=e["node_name"], transform=e["transform"])
            glb = scene.export(file_type="glb")
            rl = trimesh.load_scene(io.BytesIO(glb), file_type="glb", process=False)
            tfail = []
            for e in entries:
                try:
                    tr, gname = rl.graph[e["node_name"]]
                    m = rl.geometry[gname].copy()
                    g1 = strict_mesh_gate(m, shape(e["expected_local"]), e["height_m"], precision="float32")
                    reasons_ = list(g1["failures"])
                    if not np.array_equal(np.asarray(m.vertices)[:, [0, 2]], np.asarray(e["mesh"].vertices)[:, [0, 2]]):
                        reasons_.append("serialized_xy_changed")
                    if not np.array_equal(m.faces, e["mesh"].faces):
                        reasons_.append("serialized_faces_changed")
                    if not np.array_equal(tr, e["transform"]):
                        reasons_.append("tile_transform_changed")
                    w = m.copy()
                    w.apply_transform(tr)
                    g2 = strict_mesh_gate(w, shape(e["expected_enu"]), e["height_m"], precision="float32")
                    reasons_ += [f"world:{x}" for x in g2["failures"]]
                    if reasons_:
                        tfail.append({"tile": key, "node": e["node_name"], "failures": reasons_})
                except Exception as exc:  # noqa: BLE001
                    tfail.append({"tile": key, "node": e["node_name"], "failures": [f"roundtrip_exception:{type(exc).__name__}:{exc}"]})
            if tfail:
                failures += tfail
                continue
            tile_bytes[key] = glb
            tile_reports.append({"tile": key, "nodes": len(entries), "vertices": sum(e["vertices"] for e in entries),
                                 "triangles": sum(e["triangles"] for e in entries), "holes": sum(e["holes"] for e in entries),
                                 "repaired_nodes": sum(e["repair_status"] == "repaired" for e in entries),
                                 "bytes": len(glb), "sha256": hashlib.sha256(glb).hexdigest(), "origin_ntw_m": entries[0]["origin"]})

    ok = not failures
    write = ok or DIAGNOSTIC_WRITE_ON_FAILURE["enabled"]
    if write:
        td = out_dir / "tiles"
        td.mkdir()
        for k, g in sorted(tile_bytes.items()):
            (td / f"ntw_{pid}_{k}.glb").write_bytes(g)
        for r in ledger:
            if r["status"] == "ready":
                r["status"] = "emitted"

    # ---- placement verification: GLB world vertices -> lon/lat (independent inverse), vs source ring in lon/lat
    placement = place_check(cfg, feats, tile_bytes, pid) if write else None
    terrain = terrain_check(cfg, ledger, feats) if write else None

    with gzip.open(out_dir / "buildings.ledger.jsonl.gz", "wt", encoding="utf-8") as fh:
        for r in ledger:
            fh.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")
    tile_reports.sort(key=lambda r: r["tile"])
    digest = hashlib.sha256("\n".join(f'{r["tile"]}:{r["sha256"]}' for r in tile_reports).encode()).hexdigest() if write else None
    status_counts = Counter(r["status"] for r in ledger)
    emitted_components = sum(len(v) for v in tiles.values()) if ok else 0
    report = {
        "gate": f"NTW whitebox pilot {pid}",
        "pipeline": "source -> NTW frame (EPSG:3826 - origin) -> GEOS repair -> 500 m tile-local -> float32 footprint -> GEOS revalidate -> "
                    "GEOS CDT -> trimesh -> GLB reload -> strict QA",
        "pilot": cfg, "frame": {"ntw_origin_epsg3826": frame.NTW_ORIGIN_TM2, "block_sw_tile": [ix0, iy0],
                                 "block_extent_ntw_m": [bx0, by0, bx1, by1]},
        "source": {"features": len(feats), "normalized_input_sha256": src_hash, "provider_part_counts": dict(prov)},
        "fragment_policy": dict(FRAGMENT_POLICY),
        "quantization_fallback_policy": dict(QUANT_FALLBACK),
        "quantization_fallback_applied": [dict(building_id=r["building_id"], polygon_index=r["polygon_index"], **f)
                                          for r in ledger for f in r.get("quantization_fallback", [])],
        "ledgered_repair_fragments": [dict(building_id=r["building_id"], polygon_index=r["polygon_index"], **f)
                                      for r in ledger for f in r.get("ledgered_fragments", [])],
        "accounting": {"source_polygon_parts": source_parts, "excluded_underground": status_counts.get("excluded_underground", 0),
                       "suppressed_l3_xinyi": status_counts.get("excluded_suppressed_l3_xinyi", 0), "source_rejected": rejected,
                       "rejection_reasons": dict(reasons), "repair_outcomes": dict(repair_outcomes),
                       "emitted_source_polygon_parts": status_counts.get("emitted", 0),
                       "emitted_serialization_components": emitted_components,
                       "unaccounted_parts": source_parts - sum(status_counts.values()) + 0,
                       "ledger_status_counts": dict(status_counts), "height_source_counts": dict(hsrc)},
        "gate_result": {"pass": ok, "failure_count": len(failures)},
        "failures": failures[:50],
        "tiles": tile_reports,
        "diagnostic_write_on_failure": bool(DIAGNOSTIC_WRITE_ON_FAILURE["enabled"]),
        "tile_summary": {"count": len(tile_reports) if write else 0,
                         "nodes": q([r["nodes"] for r in tile_reports]), "triangles": q([r["triangles"] for r in tile_reports]),
                         "total_vertices": sum(r["vertices"] for r in tile_reports), "total_triangles": sum(r["triangles"] for r in tile_reports),
                         "total_glb_bytes": sum(r["bytes"] for r in tile_reports), "manifest_sha256": digest},
        "placement_check": placement, "terrain_check": terrain,
        "performance": {"runtime_seconds": round(time.perf_counter() - t0, 1), "max_rss_mb": rss_mb()},
    }
    (out_dir / "pilot.report.json").write_text(json.dumps(report, indent=2, allow_nan=False, default=_j) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("gate", "gate_result")} | {"tiles": report["tile_summary"]["count"],
          "components": emitted_components, "triangles": report["tile_summary"]["total_triangles"],
          "glb_bytes": report["tile_summary"]["total_glb_bytes"], "manifest_sha256": digest,
          "unaccounted": report["accounting"]["unaccounted_parts"], "runtime_s": report["performance"]["runtime_seconds"]}, default=_j))
    return report


def _j(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


def q(v):
    return {"min": min(v), "median": statistics.median(v), "max": max(v)} if v else {"min": 0, "median": 0, "max": 0}


def place_check(cfg, feats, tile_bytes, pid, sample=400):
    """GLB (glTF Y-up: x=east, z=-north, tile transform) -> NTW -> lon/lat via the inverse projection, then measure the
    distance from each base vertex to the SOURCE ring boundary in a local azimuthal-equidistant plane at that building."""
    by_part = {(f["id"], si): rings for f in feats for si, rings in f["polys"]}
    rng = np.random.default_rng(20261012)
    names = []
    scenes = {k: trimesh.load_scene(io.BytesIO(g), file_type="glb", process=False) for k, g in tile_bytes.items()}
    for k, sc in scenes.items():
        for n in sc.graph.nodes_geometry:
            names.append((k, n))
    names.sort()
    pick = [names[i] for i in sorted(rng.choice(len(names), size=min(sample, len(names)), replace=False))]
    worst, dists = 0.0, []
    for k, n in pick:
        sc = scenes[k]
        tr, gname = sc.graph[n]
        m = sc.geometry[gname].copy()
        m.apply_transform(tr)
        v = np.asarray(m.vertices)
        base = v[np.isclose(v[:, 1], 0.0, atol=1e-6)]
        if len(base) == 0:
            continue
        bid, pi = n.split("_p")[0], int(n.split("_p")[1].split("_")[0])
        rings = by_part[(bid, pi)]
        to_ll = lambda ring: [FROM_TM2.transform(x + frame.NTW_ORIGIN_TM2[0], y + frame.NTW_ORIGIN_TM2[1]) for x, y in ring]  # noqa: E731
        src_ll = to_ll(rings[0])
        hole_ll = [to_ll(h) for h in rings[1:]]
        lon0, lat0 = np.mean([p[0] for p in src_ll]), np.mean([p[1] for p in src_ll])
        aeqd = Transformer.from_crs(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84", "EPSG:4326", always_xy=True)
        to_local = Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84", always_xy=True)
        src_loc = shapely.union_all([Polygon([to_local.transform(*p) for p in src_ll]).boundary] +
                                    [Polygon([to_local.transform(*p) for p in h]).boundary for h in hole_ll if len(h) >= 3])
        wl, wa = frame.ntw_to_lonlat(base[:, 0], -base[:, 2])
        d = max(src_loc.distance(shapely.Point(*to_local.transform(a, b))) for a, b in zip(wl, wa))
        dists.append(d)
        worst = max(worst, d)
    return {"sampled_components": len(dists), "method": "GLB world base vertices -> NTW -> lon/lat (inverse TM2) -> distance to source ring in local aeqd plane",
            "max_vertex_to_source_boundary_m": round(worst, 4), "p99_m": round(float(np.percentile(dists, 99)), 4) if dists else None,
            "note": "includes GEOS make_valid + float32 quantisation; repaired parts can legitimately add intersection vertices"}


def terrain_check(cfg, ledger, feats):
    from dtm import Dtm
    d = Dtm()
    by_part = {(f["id"], si): rings for f in feats for si, rings in f["polys"]}
    diffs, nan, sampled, base = [], 0, 0, []
    for r in ledger:
        if r["status"] != "emitted":
            continue
        rings = by_part[(r["building_id"], r["polygon_index"])]
        cx, cy = vmean(rings[0])
        lon, lat = frame.ntw_to_lonlat(cx, cy)
        z = d.sample(float(lon), float(lat))
        sampled += 1
        if not np.isfinite(z):
            nan += 1
            continue
        r["dtm_elev_m"] = round(float(z), 3)
        base.append(z)
        if r.get("ground_elev_m") is not None:
            diffs.append(z - r["ground_elev_m"])
    res = {"dtm_source": "MOI 2025 20 m DTM, Terrarium z13 mirror (yhzkiki/taiwan-dtm-2025-terrarium-z13)",
           "parts_sampled": sampled, "nodata_samples": nan,
           "dtm_elevation_m": {"min": round(float(min(base)), 2), "median": round(float(np.median(base)), 2), "max": round(float(max(base)), 2)} if base else None,
           "dtm_tile_sha256": d.tile_sha256}
    if diffs:
        a = np.array(diffs)
        res["dtm_minus_surveyed_ground_m"] = {
            "n": len(a), "median": round(float(np.median(a)), 3), "median_abs": round(float(np.median(np.abs(a))), 3),
            "p95_abs": round(float(np.percentile(np.abs(a), 95)), 3), "gt_3m": int((np.abs(a) > 3).sum()),
            "xinyi_accepted_global_offset_m": 0.341955,
            "median_after_applying_xinyi_offset_m": round(float(np.median(a + 0.341955)), 3)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--placement-only", action="store_true", help="recompute placement_check for an existing output dir")
    a = ap.parse_args()
    if a.placement_only:
        cfg = pilot_cfg(a.pilot)
        ix0, iy0 = block_of(cfg)
        feats = (load_wfs if cfg["provider"] == "taipei_wfs" else load_overture)(
            cfg, ix0 * TILE_M, iy0 * TILE_M, (ix0 + BLOCK_TILES) * TILE_M, (iy0 + BLOCK_TILES) * TILE_M)
        tiles = {f.stem.split("_")[-2] + "_" + f.stem.split("_")[-1]: f.read_bytes() for f in sorted((a.out / "tiles").glob("*.glb"))}
        rp = a.out / "pilot.report.json"
        rep = json.loads(rp.read_text(encoding="utf-8"))
        rep["placement_check"] = place_check(cfg, feats, tiles, a.pilot)
        rp.write_text(json.dumps(rep, indent=2, allow_nan=False, default=_j) + "\n", encoding="utf-8")
        print(json.dumps(rep["placement_check"]))
        return
    r = build(a.pilot, a.out)
    if not r["gate_result"]["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
