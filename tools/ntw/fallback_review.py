"""Phase 2B-C: reviewable before / after QA of the CANDIDATE float32 grid-snap fallback (review #5501430227 P0 #3) and the two
source cases the review asked to keep case-specific (P0 #4). Nothing here changes a policy flag; QUANT_FALLBACK stays OFF.

For each of the 10 parts the accepted path rejects (fragment_scan.json):
  * every region removed / added by the snap: area, length (longest extent), width (max inscribed circle), location;
    class: sub_quantum (fits in 2 grid cells), zero_width_spike (inscribed radius < grid; carries no area) or material
  * every original hole: area, max inscribed radius, class (degenerate_hole: radius < 2 grid, or courtyard) and its fate
  * the PROPOSED bounded policy (limits below) -> AUTO / EXCEPTION (named, reviewer sign-off) / REJECT
Case studies: tp_building_height.307096 part 1 (zero-area self-intersecting source) and the Overture outline that overlaps 4 WFS
buildings at the Taipei / New Taipei border. Proposed decisions are recorded as PROPOSED, never applied.
Writes data/ntw/terrain/fallback_review.json and docs/evidence/ntw/buildings/*.png.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely import affinity

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p_ in (HERE, REPO / "tools/compiler", REPO / "tools/citygen_v2"):
    sys.path.insert(0, str(p_))
import frame  # noqa: E402
from geometry import repair_worldmodel_polygon  # noqa: E402
from quantization_fallback import GRID_M  # noqa: E402
from serialization_space import prepare_footprint, tile_origin  # noqa: E402

EVID = REPO / "docs/evidence/ntw/buildings"
OUT = REPO / "data/ntw/terrain/fallback_review.json"
# PROPOSED limits (for review; not enabled anywhere)
LIMITS = {
    "auto_spike_max_length_m": 0.10,          # a zero-width spike longer than this is a visible silhouette change -> named exception
    "auto_hausdorff_max_m": 0.10,
    "auto_hole_removal_max_area_m2": 1e-4,    # only degenerate (sub-mm) holes may disappear automatically
    "reject_courtyard_min_radius_m": 0.25,    # removing / filling a hole with a >= 0.5 m inscribed circle is never allowed
    "reject_material_change_m2": 0.01,        # any non-spike region change larger than this -> reject
}


def wfs_rings(target_ids):
    ox, oy = frame.NTW_ORIGIN_TM2
    out = {}
    for line in (REPO / "data/generated/ntw/wfs_taipei_citywide.ndjson").open(encoding="utf-8"):
        if not any(t in line for t in target_ids):
            continue
        r = json.loads(line)
        if r["id"] not in target_ids:
            continue
        g = r["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        out[r["id"]] = [[[(x - ox, y - oy) for x, y in ring] for ring in poly] for poly in polys]
    return out


def regions(g, other):
    """Changed regions. protrusion = how far the region reaches from the OTHER outline (the silhouette change):
    edge_shift_sliver (<= 2 grid: an edge moved by less than the quantum, any length), zero_width_spike (protrudes further but
    has no width: a digitising hair), material (has width)."""
    res = []
    ob = other.boundary
    for q in shapely.get_parts(g):
        if q.is_empty or q.geom_type not in ("Polygon",):
            continue
        mic = shapely.maximum_inscribed_circle(q)
        rad = float(mic.length) if mic is not None and not mic.is_empty else 0.0
        x0, y0, x1, y1 = q.bounds
        pts = shapely.points(shapely.get_coordinates(q))
        prot = float(shapely.distance(pts, ob).max()) if len(pts) else 0.0
        far = shapely.get_coordinates(q)[int(np.argmax(shapely.distance(pts, ob)))] if len(pts) else [q.centroid.x, q.centroid.y]
        cls = "edge_shift_sliver" if prot <= 2 * GRID_M else ("zero_width_spike" if rad < GRID_M else "material")
        res.append({"area_m2": float(q.area), "length_m": round(math.hypot(x1 - x0, y1 - y0), 4), "protrusion_m": round(prot, 5),
                    "inscribed_radius_m": rad, "far_point_local": [round(float(far[0]), 3), round(float(far[1]), 3)], "class": cls})
    return res


def review_part(pid, si, ri, rings):
    parts, _ = repair_worldmodel_polygon({"footprint_enu": rings[0], "holes_enu": rings[1:]})
    a = np.asarray(rings[0])
    origin = tile_origin((a[:, 0].mean(), a[:, 1].mean()))
    rp = parts[ri]
    local = affinity.translate(rp, xoff=-origin[0], yoff=-origin[1])
    snapped = shapely.set_precision(local, GRID_M)
    rem, add = regions(local.difference(snapped), snapped), regions(snapped.difference(local), local)
    holes = []
    sint = [shapely.Polygon(hh) for q in shapely.get_parts(snapped) if q.geom_type == "Polygon" for hh in q.interiors]
    reps = [shapely.Polygon(h).representative_point() for h in local.interiors]
    for hi, h in enumerate(local.interiors):
        hp = shapely.Polygon(h)
        mic = shapely.maximum_inscribed_circle(hp)
        rad = float(mic.length) if not mic.is_empty else 0.0
        core = hp.buffer(-2 * GRID_M)
        empty = core.is_empty or float(snapped.intersection(core).area) == 0.0
        cls = "degenerate_hole" if rad < 2 * GRID_M else "courtyard"
        own = [si_ for si_ in sint if si_.contains(reps[hi])]
        if not empty:
            fate = "FILLED"
        elif own:
            shared = sum(1 for r_ in reps if own[0].contains(r_))
            fate = "own_hole" if shared == 1 else "merged_with_%d_other_hole(s)_at_pinch" % (shared - 1)
        elif not snapped.contains(reps[hi]):
            fate = "opened_to_exterior_at_pinch"
        else:
            fate = "FILLED"
        holes.append({"area_m2": float(hp.area), "inscribed_radius_m": rad, "class": cls, "empty_after": bool(empty), "after": fate})
    haus = float(shapely.hausdorff_distance(snapped, local))
    # source vertices that end up > 2 grid away from the snapped outline: zero-width spikes (outside) or slits (inside)
    Pv = shapely.get_coordinates(local)
    dv = shapely.distance(shapely.points(Pv), snapped.boundary)
    far = []
    for i in np.argsort(-dv)[:5]:
        if dv[i] <= 2 * GRID_M:
            break
        far.append({"vertex_local": [round(float(Pv[i, 0]), 3), round(float(Pv[i, 1]), 3)], "distance_m": round(float(dv[i]), 4),
                    "kind": "inward_zero_width_slit" if snapped.covers(shapely.points(Pv[i])) else "outward_zero_width_spike"})
    hp_ = shapely.shortest_line(snapped, local) if haus > 0 else None
    # proposed bounded policy
    spikes = [r for r in rem + add if r["class"] == "zero_width_spike"]
    mats = [r for r in rem + add if r["class"] == "material"]
    for r in spikes:
        r["length_m"] = r["protrusion_m"]
    reasons = []
    verdict = "AUTO"
    if any(r["area_m2"] > LIMITS["reject_material_change_m2"] for r in mats):
        verdict, reasons = "REJECT", reasons + ["material_region_change"]
    if any(h["class"] == "courtyard" and h["inscribed_radius_m"] >= LIMITS["reject_courtyard_min_radius_m"] and h["after"] == "FILLED" for h in holes):
        verdict, reasons = "REJECT", reasons + ["courtyard_filled"]
    if verdict != "REJECT":
        if any(r["length_m"] > LIMITS["auto_spike_max_length_m"] for r in spikes):
            verdict, reasons = "EXCEPTION", reasons + ["spike_longer_than_%.2fm" % LIMITS["auto_spike_max_length_m"]]
        if haus > LIMITS["auto_hausdorff_max_m"]:
            kinds = sorted({f["kind"] for f in far if f["distance_m"] > LIMITS["auto_hausdorff_max_m"]})
            verdict, reasons = "EXCEPTION", reasons + ["hausdorff_over_%.2fm:%s" % (LIMITS["auto_hausdorff_max_m"], "+".join(kinds))]
        if any(h["after"] != "own_hole" and h["area_m2"] > LIMITS["auto_hole_removal_max_area_m2"] for h in holes):
            verdict, reasons = "EXCEPTION", reasons + ["courtyard_topology_changed_at_zero_width_pinch"]
        if mats:
            verdict, reasons = "EXCEPTION", reasons + ["material_region_change_small"]
    _, fg = prepare_footprint(rp, origin)
    return {"building_id": pid, "polygon_index": si, "repaired_part": ri, "source_area_m2": float(local.area),
            "accepted_failures": fg.get("failures"), "hausdorff_m": round(haus, 4), "area_delta_m2": float(snapped.area - local.area),
            "removed": rem, "added": add, "far_source_vertices": far, "holes": holes, "proposed_verdict": verdict,
            "verdict_reasons": reasons}, local, snapped, hp_


# ------------------------------------------------------------------------------------------------- drawing (PIL, no deps)
def draw_panel(local, snapped, title, w=520, h=360, focus=None, zoom_m=None):
    im = Image.new("RGB", (w, h), "white")
    dr = ImageDraw.Draw(im)
    if focus is not None and zoom_m:
        cx, cy = focus
        x0, y0, x1, y1 = cx - zoom_m, cy - zoom_m * h / w, cx + zoom_m, cy + zoom_m * h / w
    else:
        x0, y0, x1, y1 = local.union(snapped).bounds
        pad = 0.06 * max(x1 - x0, y1 - y0)
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    sc = min((w - 10) / (x1 - x0), (h - 30) / (y1 - y0))
    T = lambda x, y: (5 + (x - x0) * sc, h - 5 - (y - y0) * sc)  # noqa: E731

    def ring(coords, col, wid):
        pts = [T(x, y) for x, y in coords]
        if len(pts) > 1:
            dr.line(pts, fill=col, width=wid)
    for g, col, wid in ((local, (40, 90, 220), 3), (snapped, (220, 40, 40), 1)):
        for q in shapely.get_parts(g):
            if q.geom_type != "Polygon":
                continue
            ring(q.exterior.coords, col, wid)
            for hh in q.interiors:
                ring(hh.coords, col, wid)
    dr.rectangle([0, 0, w, 16], fill=(0, 0, 0))
    dr.text((4, 2), title, fill=(255, 255, 0))
    span = (x1 - x0)
    dr.text((4, h - 14), "width shown %.3g m   blue = source (repaired), red = snapped" % span, fill=(80, 80, 80))
    return im


def main():
    scan = json.loads((REPO / "data/ntw/terrain/fragment_scan.json").read_text(encoding="utf-8"))["taipei_wfs"]
    ev = json.loads((REPO / "data/ntw/terrain/fallback_eval.json").read_text(encoding="utf-8"))
    targets = [(r["id"], r["part"], r["repaired_part"]) for r in ev["rows"]]
    rings = wfs_rings({t[0] for t in targets} | {"tp_building_height.307096", "tp_building_height.350589", "tp_building_height.350590",
                                                   "tp_building_height.350591", "tp_building_height.350592"})
    EVID.mkdir(parents=True, exist_ok=True)
    rows, panels = [], []
    for pid, si, ri in targets:
        row, local, snapped, sl = review_part(pid, si, ri, rings[pid][si])
        rows.append(row)
        panels.append(draw_panel(local, snapped, "%s  %s  H=%.3f m" % (pid.split(".")[-1], row["proposed_verdict"], row["hausdorff_m"])))
        big = sorted(row["removed"] + row["added"], key=lambda r: -r["protrusion_m"])
        if big:
            f = big[0]["far_point_local"]
            panels.append(draw_panel(local, snapped, "zoom: largest protrusion %.4f m, %.1e m2 (%s)" % (big[0]["protrusion_m"], big[0]["area_m2"], big[0]["class"]),
                                     focus=f, zoom_m=max(0.002, big[0]["protrusion_m"] * 1.5)))
        else:
            panels.append(Image.new("RGB", (520, 360), "white"))
    cols = 4
    S = Image.new("RGB", (cols * 520, ((len(panels) + cols - 1) // cols) * 360), (30, 30, 30))
    for i, pn in enumerate(panels):
        S.paste(pn, ((i % cols) * 520, (i // cols) * 360))
    S.save(EVID / "fallback_before_after.png", optimize=True)

    # ---- case: 307096 part 1
    r307 = rings["tp_building_height.307096"]
    src = shapely.Polygon(r307[1][0], r307[1][1:])
    parts, rep = repair_worldmodel_polygon({"footprint_enu": r307[1][0], "holes_enu": r307[1][1:]})
    p0 = shapely.Polygon(r307[0][0], r307[0][1:])
    case307 = {"building_id": "tp_building_height.307096", "polygon_parts_in_source": len(r307),
               "part0": {"valid": bool(p0.is_valid), "area_m2": round(float(p0.area), 2), "status": "emitted normally"},
               "part1": {"vertices": len(r307[1][0]), "valid": bool(src.is_valid), "invalid_reason": shapely.is_valid_reason(src),
                         "shoelace_area_m2": round(abs(float(src.area)), 6), "bounds_extent_m": [round(v, 2) for v in np.ptp(np.asarray(r307[1][0]), axis=0)],
                         "make_valid_pieces": len(parts), "make_valid_total_area_m2": round(sum(p.area for p in parts), 6),
                         "largest_piece_m2": round(max(p.area for p in parts), 6), "repair_status": rep.get("status"),
                         "distance_to_part0_m": round(float(src.distance(p0)), 3)},
               "proposed_case_decision": "PROPOSED (not applied): ledger part 1 as source_rejected 'degenerate_zero_area_outline' for this id "
                                         "only - its recoverable area is ~0.003 m2 in 23 sub-cm pieces, i.e. no building footprint; part 0 "
                                         "(the building) stays. Alternative: ask the data owner. No global source_area==0 rule."}
    pan = [draw_panel(src.buffer(0) if False else shapely.Polygon(r307[1][0]).exterior.buffer(0.001), shapely.union_all(parts),
                      "307096 part 1: source outline (blue) vs make_valid pieces (red)"),
           draw_panel(p0, shapely.union_all(parts), "307096 part 0 (blue) and part 1 pieces (red)")]
    S2 = Image.new("RGB", (1040, 360), "white")
    for i, pn in enumerate(pan):
        S2.paste(pn, (i * 520, 0))
    S2.save(EVID / "case_307096.png", optimize=True)

    # ---- case: Overture outline over 4 WFS buildings at the admin border
    import duckdb
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
    oid = "548d8e29-d7e1-4dfb-bee5-3d21a91a6a72"
    wkb = duckdb.connect().execute(f"select wkb from read_parquet('{(REPO / 'data/generated/ntw/ovt_taipei_fp.parquet').as_posix()}') where id = ?",
                                   [oid]).fetchone()[0]
    g = shapely.from_wkb(bytes(wkb))
    co = shapely.get_coordinates(g)
    x, y = tr.transform(co[:, 0], co[:, 1])
    og = shapely.set_coordinates(g, np.column_stack([x - frame.NTW_ORIGIN_TM2[0], y - frame.NTW_ORIGIN_TM2[1]]))
    wfs = shapely.union_all([shapely.Polygon(rings[i][0][0], rings[i][0][1:]) for i in
                             ("tp_building_height.350589", "tp_building_height.350590", "tp_building_height.350591", "tp_building_height.350592")])
    from world_planner import load_geography
    tpe = shapely.affinity.translate(load_geography()[4]["TW-TPE"][1], xoff=-frame.NTW_ORIGIN_TM2[0], yoff=-frame.NTW_ORIGIN_TM2[1])
    cx, cy = shapely.centroid(og).x, shapely.centroid(og).y
    case_ov = {"overture_id": oid, "overture_area_m2": round(float(og.area), 1), "wfs_ids": ["tp_building_height.35058%d" % i for i in (9,)] +
               ["tp_building_height.3505%d" % i for i in (90, 91, 92)], "wfs_union_area_m2": round(float(wfs.area), 1),
               "overlap_m2": round(float(og.intersection(wfs).area), 1), "overture_outside_wfs_m2": round(float(og.difference(wfs).area), 1),
               "overture_inside_taipei_m2": round(float(og.intersection(tpe).area), 1), "overture_centroid_in_taipei": bool(shapely.contains_xy(tpe, cx, cy)),
               "options": {"A_keep_both": "131 m2 double-built (current diagnostic output)",
                           "B_clip_overture_by_owner_wfs": "keeps the %.0f m2 of Overture coverage outside WFS; needs a clip + strict re-validation path"
                                                           % float(og.difference(wfs).area),
                           "C_suppress_overture": "loses %.0f m2 of legitimate coverage" % float(og.difference(wfs).area)},
               "proposed_case_decision": "PROPOSED (not applied): option B for this pair after visual check; no blanket suppression rule"}
    pan = [draw_panel(og, wfs, "Overture %s (blue) vs 4 Taipei WFS (red)" % oid[:8]),
           draw_panel(og, tpe.intersection(og.buffer(60)), "Overture (blue) vs TW-TPE boundary near it (red)")]
    S3 = Image.new("RGB", (1040, 360), "white")
    for i, pn in enumerate(pan):
        S3.paste(pn, (i * 520, 0))
    S3.save(EVID / "case_provider_overlap_548d8e29.png", optimize=True)

    summary = {k: sum(1 for r in rows if r["proposed_verdict"] == k) for k in ("AUTO", "EXCEPTION", "REJECT")}
    out = {"status": "REVIEW ONLY - QUANT_FALLBACK stays OFF (not approved for production, review #5501430227)", "grid_m": GRID_M,
           "proposed_limits": LIMITS, "summary": summary, "parts": rows, "case_307096": case307, "case_provider_overlap": case_ov,
           "not_done": ["locked representative / full-Xinyi regression with the fallback enabled (required before any opt-in)"]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({"summary": summary, "rows": [(r["building_id"], r["hausdorff_m"], r["proposed_verdict"], r["verdict_reasons"],
                                                    sorted({x["class"] for x in r["removed"] + r["added"]}),
                                                    max([x["protrusion_m"] for x in r["removed"] + r["added"] if x["class"] == "zero_width_spike"] or [0]),
                                                    [(h["class"], round(h["area_m2"], 3), h["after"]) for h in r["holes"]]) for r in rows],
                      "case307": case307["part1"], "case_ov": {k: v for k, v in case_ov.items() if k != "options"}}, indent=1, default=float))


if __name__ == "__main__":
    main()
