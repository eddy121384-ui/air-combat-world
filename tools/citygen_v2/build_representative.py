"""Build the 50-100 building Xinyi v2 acceptance sample.

The selection is deterministic and category-balanced. It scans the entire
committed snapshot for accounting, but only meshes the representative set.
Full-Xinyi generation is intentionally out of scope until this gate passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))

from geometry import concavity_ratio, extrude_geos_polygon, mesh_gate, repair_worldmodel_polygon  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

DEFAULT_COUNT = 80
TILE_SIZE_M = 500.0


def _stable_key(building_id: str, polygon_index: int) -> str:
    return hashlib.sha256(f"{building_id}|{polygon_index}".encode()).hexdigest()


def _distinct_count(ring: list) -> int:
    return len({(float(p[0]), float(p[1])) for p in ring})


def _tile_key(cx: float, cy: float, size_m: float = TILE_SIZE_M) -> str:
    import math
    return f"{math.floor(cx / size_m):+04d}_{math.floor(cy / size_m):+04d}"


def _rss_mb():
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        if sys.platform == "darwin":
            return rss / (1024 * 1024)
        return rss / 1024
    except Exception:
        return None


def classify_candidate(building: dict, poly: dict, repaired_parts: list) -> set[str]:
    cats: set[str] = set()
    h = float(building["height_m"])
    unique_outer = _distinct_count(poly["footprint_enu"])
    result_holes = sum(len(p.interiors) for p in repaired_parts)
    min_concavity = min(concavity_ratio(p) for p in repaired_parts)

    if unique_outer == 4 and min_concavity > 0.995:
        cats.add("simple_rect")
    if h <= 20.0 and sum(p.area for p in repaired_parts) <= 500.0:
        cats.add("low_rise_small_footprint")
    if 20.0 < h <= 60.0:
        cats.add("mid_rise")
    if h > 60.0:
        cats.add("high_rise")
    if min_concavity < 0.95:
        cats.add("concave")
    if unique_outer >= 12:
        cats.add("complex")
    if poly.get("holes_enu") or result_holes:
        cats.add("holes")
    if len(building["polygons"]) > 1:
        cats.add("multipart_feature")
    return cats


def select_candidates(candidates: list[dict], target: int) -> list[dict]:
    quotas = [
        ("holes", 12),
        ("multipart_feature", 4),
        ("complex", 12),
        ("concave", 16),
        ("high_rise", 8),
        ("low_rise_small_footprint", 16),
        ("simple_rect", 12),
        ("mid_rise", 12),
    ]
    ordered = sorted(candidates, key=lambda c: c["stable_key"])
    selected: list[dict] = []
    seen: set[tuple[str, int]] = set()

    for category, quota in quotas:
        n = 0
        for c in ordered:
            key = (c["building_id"], c["polygon_index"])
            if key in seen or category not in c["categories"]:
                continue
            selected.append(c)
            seen.add(key)
            n += 1
            if n >= quota or len(selected) >= target:
                break
        if len(selected) >= target:
            break

    if len(selected) < target:
        for c in ordered:
            key = (c["building_id"], c["polygon_index"])
            if key in seen:
                continue
            selected.append(c)
            seen.add(key)
            if len(selected) >= target:
                break

    return selected


def build(target_count: int, output_glb: Path, output_report: Path) -> dict:
    if not 50 <= target_count <= 100:
        raise ValueError("representative gate must stay between 50 and 100 source polygon parts")

    started = time.perf_counter()
    source = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
    city = REPO / "cities/taipei/city.yaml"
    if not source.exists():
        raise RuntimeError(
            "projected v2 source missing; run: node tools/citygen_v2/fetch_projected_sample.mjs"
        )
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    wm = build_worldmodel(source, city, source_crs="EPSG:3826")

    outcome_counts = Counter()
    rejection_reasons = Counter()
    candidates: list[dict] = []
    suppressed = 0
    scanned_parts = 0
    repaired_parts_total = 0

    for b in wm["buildings"]:
        if b["suppressed"]:
            suppressed += 1
            continue
        for pi, poly in enumerate(b["polygons"]):
            scanned_parts += 1
            repaired_parts, outcome = repair_worldmodel_polygon(poly)
            outcome_counts[outcome["status"]] += 1
            if outcome["reason"]:
                rejection_reasons[outcome["reason"]] += 1
            if not repaired_parts:
                continue
            repaired_parts_total += len(repaired_parts)
            categories = classify_candidate(b, poly, repaired_parts)
            candidates.append({
                "building_id": b["id"],
                "height_m": b["height_m"],
                "polygon_index": pi,
                "source_polygon_index": poly.get("source_polygon_index", pi),
                "stable_key": _stable_key(b["id"], pi),
                "categories": sorted(categories),
                "centroid_enu": poly["centroid_enu"],
                "source_holes": len(poly.get("holes_enu", [])),
                "repair_outcome": outcome,
                "_parts": repaired_parts,
            })

    selected = select_candidates(candidates, target_count)
    if len(selected) < target_count:
        raise RuntimeError(f"only {len(selected)} meshable candidates for target {target_count}")

    scene = trimesh.Scene()
    mesh_rows: list[dict] = []
    category_coverage = Counter()
    tile_coverage = Counter()
    total_vertices = 0
    total_triangles = 0
    failed_selected = 0

    for c in selected:
        for category in c["categories"]:
            category_coverage[category] += 1
        cx, cy = c["centroid_enu"]
        tile_coverage[_tile_key(cx, cy)] += 1

        part_gates = []
        for ri, poly in enumerate(c["_parts"]):
            try:
                mesh = extrude_geos_polygon(poly, float(c["height_m"]))
                gate = mesh_gate(mesh, float(c["height_m"]))
            except Exception as exc:
                gate = {
                    "pass": False,
                    "failures": [f"exception:{type(exc).__name__}:{exc}"],
                    "vertices": 0,
                    "triangles": 0,
                }
                mesh = None

            part_gates.append(gate)
            total_vertices += int(gate.get("vertices", 0))
            total_triangles += int(gate.get("triangles", 0))
            if mesh is not None:
                name = f"{c['building_id']}_p{c['polygon_index']}_r{ri}"
                scene.add_geometry(mesh, geom_name=name, node_name=name)

        passed = bool(part_gates) and all(g["pass"] for g in part_gates)
        if not passed:
            failed_selected += 1
        mesh_rows.append({
            "building_id": c["building_id"],
            "polygon_index": c["polygon_index"],
            "height_m": c["height_m"],
            "categories": c["categories"],
            "centroid_enu": c["centroid_enu"],
            "tile_500m": _tile_key(cx, cy),
            "repair_outcome": c["repair_outcome"],
            "mesh_parts": part_gates,
            "pass": passed,
        })

    output_glb.parent.mkdir(parents=True, exist_ok=True)
    glb_bytes = scene.export(file_type="glb")
    output_glb.write_bytes(glb_bytes)

    report = {
        "gate": "Xinyi Robust Whitebox v2 representative real-building sample",
        "input": {
            "source": str(source),
            "source_crs": "EPSG:3826",
            "sha256": source_sha256,
        },
        "target_source_polygon_parts": target_count,
        "selected_source_polygon_parts": len(selected),
        "selected_all_pass": failed_selected == 0,
        "selected_failures": failed_selected,
        "source_accounting": {
            "features": len(wm["buildings"]),
            "suppressed_hero_features": suppressed,
            "unsuppressed_polygon_parts_scanned": scanned_parts,
            "geometry_outcomes": dict(outcome_counts),
            "rejection_reasons": dict(rejection_reasons),
            "polygonal_parts_after_repair": repaired_parts_total,
        },
        "selection_category_coverage": dict(category_coverage),
        "selection_tile_coverage_500m": dict(sorted(tile_coverage.items())),
        "mesh_totals": {
            "vertices": total_vertices,
            "triangles": total_triangles,
        },
        "performance": {
            "runtime_seconds": time.perf_counter() - started,
            "max_rss_mb": _rss_mb(),
            "output_glb_bytes": output_glb.stat().st_size,
        },
        "output_glb": str(output_glb),
        "tile_strategy_note": (
            "Representative GLB keeps inspectable per-building nodes. Full Xinyi, if gated, "
            "must batch by deterministic 500 m spatial tile rather than one district-wide mesh."
        ),
        "buildings": mesh_rows,
    }
    output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "buildings"}, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument(
        "--glb",
        type=Path,
        default=REPO / "data/generated/taipei/xinyi_v2_representative_80.glb",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPO / "data/generated/taipei/xinyi_v2_representative.report.json",
    )
    args = parser.parse_args()
    report = build(args.count, args.glb, args.report)
    if not report["selected_all_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
