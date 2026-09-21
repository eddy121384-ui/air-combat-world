"""Full-Xinyi tiled generator using the validated serialization-space policy.

This is a fail-closed geometry gate. It emits no publishable tile set unless every
unsuppressed source polygon part is accounted for and every emitted component
passes strict QA before and after actual GLB serialization.
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
import trimesh
from shapely import affinity
from shapely.geometry import mapping, shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))

from geometry import extrude_geos_polygon, repair_worldmodel_polygon  # noqa: E402
from serialization_space import prepare_footprint, tile_origin, tile_transform  # noqa: E402
from strict_qa import strict_mesh_gate  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"


def _rss_mb():
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    except Exception:
        return None


def _tile_key(origin):
    return f"{int(origin[0] // 500):+04d}_{int(origin[1] // 500):+04d}"


def _node_name(building_id, polygon_index, repaired_index, serial_index):
    return f"{building_id}_p{polygon_index}_r{repaired_index}_s{serial_index}"


def _quantiles(values):
    if not values:
        return {"min": 0, "median": 0, "max": 0}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def _write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build(output_dir: Path) -> dict:
    started = time.perf_counter()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {output_dir}")
    output_dir.mkdir(parents=True)
    report_path = output_dir / "full_xinyi.report.json"
    ledger_path = output_dir / "full_xinyi.ledger.jsonl.gz"

    if not SOURCE.exists():
        raise RuntimeError("Projected source missing; run node tools/citygen_v2/fetch_projected_sample.mjs")

    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")

    repair_outcomes = Counter()
    rejection_reasons = Counter()
    source_parts = 0
    suppressed_features = 0
    suppressed_parts = 0
    emitted_source_parts = 0
    emitted_components = 0
    failures = []
    ledger = []
    tiles = defaultdict(list)

    for building in wm["buildings"]:
        if building["suppressed"]:
            suppressed_features += 1
            suppressed_parts += len(building["polygons"])
            for pi, poly in enumerate(building["polygons"]):
                ledger.append({
                    "building_id": building["id"],
                    "polygon_index": pi,
                    "status": "hero_suppressed",
                    "height_m": building["height_m"],
                })
            continue

        for pi, poly_record in enumerate(building["polygons"]):
            source_parts += 1
            repaired_parts, repair = repair_worldmodel_polygon(poly_record)
            repair_outcomes[repair["status"]] += 1
            if repair.get("reason"):
                rejection_reasons[repair["reason"]] += 1

            row = {
                "building_id": building["id"],
                "polygon_index": pi,
                "source_polygon_index": poly_record.get("source_polygon_index", pi),
                "height_m": building["height_m"],
                "repair_status": repair["status"],
                "repair_reason": repair.get("reason"),
                "repaired_components": len(repaired_parts),
                "emitted_components": 0,
                "status": None,
                "tile": None,
                "failures": [],
            }

            if not repaired_parts:
                row["status"] = "rejected"
                row["failures"].append("no_polygonal_output_after_source_repair")
                failures.append(dict(row))
                ledger.append(row)
                continue

            origin = tile_origin(poly_record["centroid_enu"])
            tile_key = _tile_key(origin)
            row["tile"] = tile_key
            pending = []
            part_failed = False

            for ri, repaired in enumerate(repaired_parts):
                try:
                    serial_parts, footprint_gate = prepare_footprint(repaired, origin)
                except Exception as exc:
                    serial_parts = []
                    footprint_gate = {
                        "pass": False,
                        "failures": [f"footprint_exception:{type(exc).__name__}:{exc}"],
                    }

                if not footprint_gate["pass"]:
                    part_failed = True
                    row["failures"].extend(
                        f"r{ri}:footprint:{reason}" for reason in footprint_gate["failures"]
                    )
                    continue

                for si, serial_poly in enumerate(serial_parts):
                    name = _node_name(building["id"], pi, ri, si)
                    try:
                        mesh = extrude_geos_polygon(serial_poly, float(building["height_m"]))
                        gate = strict_mesh_gate(
                            mesh, serial_poly, float(building["height_m"]), precision="float64"
                        )
                        xy = np.asarray(mesh.vertices)[:, [0, 2]]
                        if not np.array_equal(xy, xy.astype(np.float32).astype(np.float64)):
                            gate["failures"].append("mesher_introduced_nonserializable_xy")
                            gate["pass"] = False
                    except Exception as exc:
                        mesh = None
                        gate = {
                            "pass": False,
                            "failures": [f"mesh_exception:{type(exc).__name__}:{exc}"],
                            "vertices": 0,
                            "triangles": 0,
                        }

                    if not gate["pass"] or mesh is None:
                        part_failed = True
                        row["failures"].extend(
                            f"r{ri}s{si}:float64:{reason}" for reason in gate["failures"]
                        )
                        continue

                    pending.append({
                        "node_name": name,
                        "mesh": mesh,
                        "building_id": building["id"],
                        "polygon_index": pi,
                        "repaired_part_index": ri,
                        "serialization_part_index": si,
                        "height_m": float(building["height_m"]),
                        "tile_origin_enu_m": [float(origin[0]), float(origin[1])],
                        "transform": tile_transform(origin),
                        "expected_local": mapping(serial_poly),
                        "expected_enu": mapping(
                            affinity.translate(serial_poly, xoff=origin[0], yoff=origin[1])
                        ),
                        "holes": len(serial_poly.interiors),
                        "repair_status": repair["status"],
                        "vertices": int(gate["vertices"]),
                        "triangles": int(gate["triangles"]),
                    })

            if part_failed or not pending:
                row["status"] = "failed_pre_serialization"
                failures.append(dict(row))
                ledger.append(row)
                continue

            row["emitted_components"] = len(pending)
            row["status"] = "ready_for_tile_serialization"
            ledger.append(row)
            tiles[tile_key].extend(pending)

    pre_serialization_failures = len(failures)
    tile_bytes = {}
    tile_reports = []

    if pre_serialization_failures == 0:
        for tile_key in sorted(tiles):
            entries = tiles[tile_key]
            scene = trimesh.Scene()
            for entry in entries:
                scene.add_geometry(
                    entry["mesh"],
                    geom_name=entry["node_name"],
                    node_name=entry["node_name"],
                    transform=entry["transform"],
                )

            glb = scene.export(file_type="glb")
            reloaded = trimesh.load_scene(io.BytesIO(glb), file_type="glb", process=False)
            tile_failures = []
            tile_vertices = 0
            tile_triangles = 0
            tile_holes = 0
            repaired_nodes = 0

            for entry in entries:
                name = entry["node_name"]
                tile_vertices += entry["vertices"]
                tile_triangles += entry["triangles"]
                tile_holes += entry["holes"]
                repaired_nodes += int(entry["repair_status"] == "repaired")
                try:
                    transform, geometry_name = reloaded.graph[name]
                    mesh = reloaded.geometry[geometry_name].copy()
                    local_gate = strict_mesh_gate(
                        mesh,
                        shape(entry["expected_local"]),
                        entry["height_m"],
                        precision="float32",
                    )
                    exact_xy = np.array_equal(
                        np.asarray(mesh.vertices)[:, [0, 2]],
                        np.asarray(entry["mesh"].vertices)[:, [0, 2]],
                    )
                    exact_faces = np.array_equal(mesh.faces, entry["mesh"].faces)
                    exact_transform = np.array_equal(transform, entry["transform"])
                    reasons = list(local_gate["failures"])
                    if not exact_xy:
                        reasons.append("serialized_xy_changed")
                    if not exact_faces:
                        reasons.append("serialized_faces_changed")
                    if not exact_transform:
                        reasons.append("tile_transform_changed")

                    world = mesh.copy()
                    world.apply_transform(transform)
                    world_gate = strict_mesh_gate(
                        world,
                        shape(entry["expected_enu"]),
                        entry["height_m"],
                        precision="float32",
                    )
                    reasons.extend(f"world:{r}" for r in world_gate["failures"])
                    if reasons:
                        tile_failures.append({
                            "node_name": name,
                            "building_id": entry["building_id"],
                            "polygon_index": entry["polygon_index"],
                            "repaired_part_index": entry["repaired_part_index"],
                            "serialization_part_index": entry["serialization_part_index"],
                            "failures": reasons,
                        })
                except Exception as exc:
                    tile_failures.append({
                        "node_name": name,
                        "building_id": entry["building_id"],
                        "polygon_index": entry["polygon_index"],
                        "repaired_part_index": entry["repaired_part_index"],
                        "serialization_part_index": entry["serialization_part_index"],
                        "failures": [f"roundtrip_exception:{type(exc).__name__}:{exc}"],
                    })

            if tile_failures:
                failures.extend(
                    {"tile": tile_key, "status": "failed_glb_roundtrip", **f}
                    for f in tile_failures
                )
            else:
                digest = hashlib.sha256(glb).hexdigest()
                tile_bytes[tile_key] = glb
                tile_reports.append({
                    "tile": tile_key,
                    "nodes": len(entries),
                    "vertices": tile_vertices,
                    "triangles": tile_triangles,
                    "holes": tile_holes,
                    "repaired_nodes": repaired_nodes,
                    "bytes": len(glb),
                    "sha256": digest,
                    "origin_enu_m": entries[0]["tile_origin_enu_m"],
                })

    ready_to_publish = len(failures) == 0
    if ready_to_publish:
        tiles_dir = output_dir / "tiles"
        tiles_dir.mkdir()
        for tile_key, glb in sorted(tile_bytes.items()):
            (tiles_dir / f"xinyi_v2_{tile_key}.glb").write_bytes(glb)

        # Mark all nonhero source parts emitted only after every tile passed actual serialization.
        emitted_source_parts = source_parts
        emitted_components = sum(len(v) for v in tiles.values())
        for row in ledger:
            if row.get("status") == "ready_for_tile_serialization":
                row["status"] = "emitted"

    with gzip.open(ledger_path, "wt", encoding="utf-8") as fh:
        for row in ledger:
            fh.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")

    tile_reports = sorted(tile_reports, key=lambda x: x["tile"])
    node_counts = [r["nodes"] for r in tile_reports]
    tri_counts = [r["triangles"] for r in tile_reports]
    full_manifest_digest = hashlib.sha256(
        "\n".join(f'{r["tile"]}:{r["sha256"]}' for r in tile_reports).encode()
    ).hexdigest() if ready_to_publish else None

    report = {
        "gate": "Full Xinyi v2 serialization-space tiled geometry gate",
        "pipeline": (
            "EPSG:3826 -> WorldModel/ENU -> GEOS repair -> 500m tile-local -> "
            "float32 footprint -> GEOS revalidate -> earcut/trimesh -> GLB reload -> strict QA"
        ),
        "source": {
            "path": str(SOURCE),
            "crs": "EPSG:3826",
            "sha256": source_sha,
            "features": len(wm["buildings"]),
        },
        "accounting": {
            "ordinary_source_polygon_parts": source_parts,
            "hero_suppressed_features": suppressed_features,
            "hero_suppressed_polygon_parts": suppressed_parts,
            "repair_outcomes": dict(repair_outcomes),
            "rejection_reasons": dict(rejection_reasons),
            "emitted_source_polygon_parts": emitted_source_parts,
            "emitted_serialization_components": emitted_components,
            "unaccounted_parts": 0,
        },
        "gate_result": {
            "pass": ready_to_publish,
            "failure_count": len(failures),
            "pre_serialization_failure_count": pre_serialization_failures,
            "ready_for_blender_full_area_sampling": ready_to_publish,
            "ready_for_unreal": False,
        },
        "failures": failures,
        "tiles": tile_reports,
        "tile_summary": {
            "count": len(tile_reports) if ready_to_publish else 0,
            "nodes": _quantiles(node_counts),
            "triangles": _quantiles(tri_counts),
            "total_vertices": sum(r["vertices"] for r in tile_reports),
            "total_triangles": sum(r["triangles"] for r in tile_reports),
            "total_glb_bytes": sum(r["bytes"] for r in tile_reports),
            "manifest_sha256": full_manifest_digest,
        },
        "performance": {
            "runtime_seconds": time.perf_counter() - started,
            "max_rss_mb": _rss_mb(),
        },
        "output": {
            "directory": str(output_dir) if ready_to_publish else None,
            "ledger": str(ledger_path),
        },
        "next_gate": (
            "Blender imported-mesh + visual sampling of full-area tiles"
            if ready_to_publish else
            "STOP: diagnose geometry/serialization failures before Blender or Unreal"
        ),
    }
    _write_report(report_path, report)
    print(json.dumps({
        "pass": ready_to_publish,
        "failures": len(failures),
        "ordinary_source_polygon_parts": source_parts,
        "hero_suppressed_polygon_parts": suppressed_parts,
        "tiles": len(tile_reports) if ready_to_publish else 0,
        "total_triangles": report["tile_summary"]["total_triangles"],
        "total_glb_bytes": report["tile_summary"]["total_glb_bytes"],
        "manifest_sha256": full_manifest_digest,
        "runtime_seconds": report["performance"]["runtime_seconds"],
        "max_rss_mb": report["performance"]["max_rss_mb"],
    }, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO / "unreal/Saved/XinyiV2Full/run-01",
    )
    args = parser.parse_args()
    report = build(args.out)
    if not report["gate_result"]["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
