"""Phase 1F: full-theater resource estimate, derived ONLY from committed measurements.

Inputs  data/ntw/coverage_manifest.json (exact Overture counts), data/ntw/taipei_wfs_vs_overture.json (exact),
        data/ntw/pilot_results.json (measured pilots), data/ntw/lod_prototype.json (measured LOD ratios)
Output  data/ntw/scale_estimate.json

Every number is labelled MEASURED (read from a manifest) or ESTIMATE (arithmetic on measured values, assumption
stated). Nothing here is a mobile performance result.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
D = REPO / "data/ntw"


def load(n):
    return json.loads((D / n).read_text(encoding="utf-8"))


def main():
    cov, cmp_, pil, lod = load("coverage_manifest.json"), load("taipei_wfs_vs_overture.json"), load("pilot_results.json"), load("lod_prototype.json")
    P = {p["pilot"][0]: p for p in pil["pilots"]}
    a, b, c = P["A"]["geometry"], P["B"]["geometry"], P["C"]["geometry"]
    ovt_core = cov["core_6"]["buildings"]
    ovt_all = cov["core_6_plus_yilan"]["buildings"]
    tpe_ovt = next(r for r in cov["regions"] if r["key"] == "taipei")["buildings"]
    wfs = cmp_["wfs_hits"]
    under_core = cov["core_6"]["underground_flagged"]
    # per-component costs (MEASURED on pilots)
    tri_wfs, tri_ovt = a["triangles_per_component"], (b["triangles"] + c["triangles"]) / (b["components"] + c["components"])
    by_wfs = a["glb_bytes_per_component"]
    by_ovt = (b["glb_bytes"] + c["glb_bytes"]) / (b["components"] + c["components"])
    # seconds per component (MEASURED but pilots ran concurrently -> pessimistic)
    s_wfs = P["A"]["performance_wall_clock"]["run1_seconds"] / a["components"]
    s_ovt = (P["B"]["performance_wall_clock"]["run1_seconds"] + P["C"]["performance_wall_clock"]["run1_seconds"]) / (b["components"] + c["components"])
    rss_kb_per_comp = P["A"]["performance_wall_clock"]["max_rss_mb"] * 1024 / a["components"]

    def scenario(name, n_wfs, n_ovt, note):
        tri = n_wfs * tri_wfs + n_ovt * tri_ovt
        by = n_wfs * by_wfs + n_ovt * by_ovt
        cpu_s = n_wfs * s_wfs + n_ovt * s_ovt
        return {"name": name, "components_wfs_like": int(n_wfs), "components_overture_like": int(n_ovt),
                "components_total": int(n_wfs + n_ovt), "triangles_millions": round(tri / 1e6, 1), "glb_gb": round(by / 1e9, 2),
                "single_core_hours_upper_bound": round(cpu_s / 3600, 1), "label": "ESTIMATE", "note": note}

    other_core = ovt_core - tpe_ovt
    ratio = wfs / tpe_ovt
    out = {
        "unit_costs_measured_on_pilots": {
            "triangles_per_component_wfs_like_A": tri_wfs, "triangles_per_component_overture_like_BC": round(tri_ovt, 2),
            "glb_bytes_per_component_A": by_wfs, "glb_bytes_per_component_BC": round(by_ovt, 1),
            "seconds_per_component_A_concurrent": round(s_wfs, 4), "seconds_per_component_BC_concurrent": round(s_ovt, 4),
            "builder_rss_kb_per_component_A": round(rss_kb_per_comp, 1),
            "xinyi_reference": {"components": 11130, "triangles": 485936, "glb_bytes": 14853448, "tri_per_component": 43.66}},
        "exact_inputs": {"overture_core6_rows": ovt_core, "overture_core6_underground_flagged": under_core,
                         "overture_core6_plus_yilan_rows": ovt_all, "taipei_overture_rows": tpe_ovt, "taipei_wfs_records": wfs,
                         "taipei_wfs_over_overture_record_ratio": round(ratio, 2),
                         "taipei_overture_area_vs_wfs_area_pct": round(100 * cmp_["overture_total_footprint_km2"] / cmp_["wfs_total_footprint_km2"], 1)},
        "scenarios": [
            scenario("S1 Overture only, 6 core regions (exact count, lower bound)", 0, ovt_core - under_core,
                     "Footprint completeness of Overture outside Taipei is UNKNOWN; this is the minimum, not the expected count."),
            scenario("S2 Taipei WFS + Overture elsewhere, 6 core regions (recommended planning case)", wfs, other_core - under_core,
                     "Uses the authoritative Taipei WFS record count; elsewhere only what Overture holds."),
            scenario("S3 S2 + Yilan (Overture)", wfs, other_core + (ovt_all - ovt_core) - under_core,
                     "Adds Yilan as evaluated extra region."),
            scenario("S4 STRESS bound: non-Taipei regions as under-recorded as Overture is in Taipei", wfs, (other_core) * ratio,
                     "ASSUMPTION ONLY: applies Taipei's WFS/Overture record ratio to other regions. Taipei WFS is per-unit and "
                     "Overture merges complexes, so this overstates; kept only to bound memory/disk planning."),
        ],
        "partitioning": {"L1_8km_nonempty_cells": cov["grids_all_regions"]["L1"]["nonempty_cells"],
                         "L2_500m_nonempty_owner_tiles_overture_only": cov["grids_all_regions"]["L2"]["nonempty_cells"],
                         "overture_buildings_per_L2_tile": cov["grids_all_regions"]["L2"]["buildings_per_cell"],
                         "note": "full build must be partitioned per L1 (8 km) cell: build_pilot.py holds a whole block in memory "
                                 f"(~{round(rss_kb_per_comp)} KB RSS/component measured); one process for the theater would need tens of GB."},
        "lod_prototype_ratios_measured": {p["pilot"][0]: {"L1_triangle_reduction_x": p["L1"]["reduction_vs_L2_triangles_x"],
                                                          "L0_triangle_reduction_x": p["L0"]["reduction_vs_L2_triangles_x"],
                                                          "L2_tri_per_km2": p["L2"]["tri_per_km2"], "L1_tri_per_km2": p["L1"]["tri_per_km2"],
                                                          "L0_tri_per_km2": p["L0"]["tri_per_km2"]} for p in lod["pilots"]},
    }
    # visible-budget illustration: radius of L2 that fits a triangle budget, per measured density (NOT a phone result)
    import math
    vis = {}
    for p in lod["pilots"]:
        d = p["L2"]["tri_per_km2"]
        vis[p["pilot"][0]] = {f"L2_radius_km_for_{int(bud/1e6*10)/10}M_tris": round(math.sqrt(bud / d / math.pi), 2) for bud in (0.5e6, 1.0e6, 2.0e6)}
    out["l2_radius_for_triangle_budget_illustration"] = {"label": "ARITHMETIC on measured pilot densities; budgets are assumptions, no device was measured", "by_pilot": vis}
    (D / "scale_estimate.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
