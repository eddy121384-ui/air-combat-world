"""Build one real Xinyi 500 m façade-metadata canary tile.

The canary regenerates geometry from the locked projected WFS source using the
accepted XinyiV2 GEOS/serialization-space path, selects the densest ordinary
source tile deterministically, and writes two tile-local GLBs:

- baseline: accepted geometry + surveyed ground-Z placement only
- metadata: byte-equivalent geometry intent plus COLOR_0 façade metadata

It fails closed on source hash drift, geometry drift, or COLOR_0 loss.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))

from facade_metadata import apply_facade_vertex_color, encode_facade_rgba  # noqa: E402
from geometry import extrude_geos_polygon, repair_worldmodel_polygon  # noqa: E402
from serialization_space import prepare_footprint, tile_origin  # noqa: E402
from strict_qa import strict_mesh_gate  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
EXPECTED_SOURCE_SHA256 = "c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def tile_key(origin) -> str:
    return f"{int(origin[0] // 500):+04d}_{int(origin[1] // 500):+04d}"


def choose_densest_tile(buildings) -> tuple[str, tuple[float, float], dict]:
    counts = Counter()
    unique_buildings = defaultdict(set)
    for building in buildings:
        if building["suppressed"]:
            continue
        for poly in building["polygons"]:
            origin = tile_origin(poly["centroid_enu"])
            key = tile_key(origin)
            counts[key] += 1
            unique_buildings[key].add(building["id"])
    if not counts:
        raise RuntimeError("no ordinary building polygons available")
    key = sorted(counts, key=lambda k: (-counts[k], k))[0]
    origin = None
    for building in buildings:
        if building["suppressed"]:
            continue
        for poly in building["polygons"]:
            candidate = tile_origin(poly["centroid_enu"])
            if tile_key(candidate) == key:
                origin = candidate
                break
        if origin is not None:
            break
    return key, origin, {
        "ordinary_source_polygon_parts": counts[key],
        "ordinary_unique_buildings": len(unique_buildings[key]),
    }


def compare_meshes_exact(a: trimesh.Trimesh, b: trimesh.Trimesh, *, label: str):
    av, bv = np.asarray(a.vertices), np.asarray(b.vertices)
    af, bf = np.asarray(a.faces), np.asarray(b.faces)
    ab, bb = np.asarray(a.bounds), np.asarray(b.bounds)
    failures = []
    if not np.array_equal(av, bv):
        failures.append(f"{label}:vertices_changed")
    if not np.array_equal(af, bf):
        failures.append(f"{label}:faces_changed")
    if not np.array_equal(ab, bb):
        failures.append(f"{label}:bounds_changed")
    return failures


def compare_roundtrip_geometry(a: trimesh.Trimesh, b: trimesh.Trimesh):
    failures = []
    av, bv = np.asarray(a.vertices), np.asarray(b.vertices)
    af, bf = np.asarray(a.faces), np.asarray(b.faces)
    if av.shape != bv.shape or not np.array_equal(av, bv):
        failures.append("roundtrip_vertices_changed")
    if af.shape != bf.shape or not np.array_equal(af, bf):
        failures.append("roundtrip_faces_changed")
    if not np.array_equal(np.asarray(a.bounds), np.asarray(b.bounds)):
        failures.append("roundtrip_bounds_changed")
    return failures


def build(out_dir: Path) -> dict:
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {out_dir}")
    out_dir.mkdir(parents=True)

    if not SOURCE.is_file():
        raise RuntimeError("projected source missing; run fetch_projected_sample.mjs first")
    source_sha = sha256_file(SOURCE)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            "projected WFS source drifted; refusing canary: "
            f"{source_sha} != {EXPECTED_SOURCE_SHA256}"
        )

    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    selected_key, selected_origin, selection = choose_densest_tile(wm["buildings"])

    baseline_meshes = []
    metadata_meshes = []
    component_rows = []
    failures = []
    profile_counts = Counter()
    floor_source_counts = Counter()
    phase_source_counts = Counter()
    seed_counts = Counter()
    rgba_counts = Counter()
    building_ids = set()
    floors_present = set()
    ground_present = set()

    for building in wm["buildings"]:
        if building["suppressed"]:
            continue
        building_has_selected_part = False
        for pi, poly_record in enumerate(building["polygons"]):
            origin = tile_origin(poly_record["centroid_enu"])
            if tile_key(origin) != selected_key:
                continue
            building_has_selected_part = True
            repaired_parts, repair = repair_worldmodel_polygon(poly_record)
            if not repaired_parts:
                failures.append({
                    "building_id": building["id"],
                    "polygon_index": pi,
                    "reason": "source_repair_failed",
                    "repair": repair,
                })
                continue

            for ri, repaired in enumerate(repaired_parts):
                serial_parts, footprint_gate = prepare_footprint(repaired, origin)
                if not footprint_gate["pass"]:
                    failures.append({
                        "building_id": building["id"],
                        "polygon_index": pi,
                        "repaired_part_index": ri,
                        "reason": "serialization_space_failed",
                        "failures": footprint_gate["failures"],
                    })
                    continue

                for si, serial_poly in enumerate(serial_parts):
                    mesh = extrude_geos_polygon(serial_poly, float(building["height_m"]))
                    gate = strict_mesh_gate(
                        mesh, serial_poly, float(building["height_m"]), precision="float64"
                    )
                    if not gate["pass"]:
                        failures.append({
                            "building_id": building["id"],
                            "polygon_index": pi,
                            "repaired_part_index": ri,
                            "serialization_part_index": si,
                            "reason": "strict_mesh_gate_failed",
                            "failures": gate["failures"],
                        })
                        continue

                    ground = building.get("ground_elev_m")
                    if ground is None or not np.isfinite(float(ground)):
                        failures.append({
                            "building_id": building["id"],
                            "polygon_index": pi,
                            "reason": "missing_surveyed_ground",
                        })
                        continue

                    baseline = mesh.copy()
                    baseline.apply_translation([0.0, float(ground), 0.0])
                    decorated = baseline.copy()
                    rgba, meta = encode_facade_rgba(building)
                    apply_facade_vertex_color(decorated, rgba)
                    failures.extend(compare_meshes_exact(
                        baseline, decorated,
                        label=f"{building['id']}:p{pi}:r{ri}:s{si}",
                    ))

                    baseline_meshes.append(baseline)
                    metadata_meshes.append(decorated)
                    profile_counts[meta["profile_id"]] += 1
                    floor_source_counts[meta["floor_height_source"]] += 1
                    phase_source_counts[meta["floor_phase_source"]] += 1
                    seed_counts[meta["appearance_seed"]] += 1
                    rgba_counts[tuple(meta["encoded_rgba"])] += 1
                    component_rows.append({
                        "building_id": building["id"],
                        "polygon_index": pi,
                        "repaired_part_index": ri,
                        "serialization_part_index": si,
                        "height_m": building["height_m"],
                        "floors": building.get("floors"),
                        "ground_elev_m": building.get("ground_elev_m"),
                        **meta,
                    })

        if building_has_selected_part:
            building_ids.add(building["id"])
            if building.get("floors") is not None:
                floors_present.add(building["id"])
            if building.get("ground_elev_m") is not None:
                ground_present.add(building["id"])

    if failures:
        report = {
            "status": "FAIL_REAL_TILE_CANARY",
            "source_sha256": source_sha,
            "selected_tile": selected_key,
            "selection": selection,
            "failure_count": len(failures),
            "failures": failures[:100],
        }
        (out_dir / "xinyi_facade_real_tile_canary.report.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        raise RuntimeError(f"real tile canary failed before export: {len(failures)} failures")

    baseline_combined = trimesh.util.concatenate(baseline_meshes)
    metadata_combined = trimesh.util.concatenate(metadata_meshes)
    geometry_failures = compare_meshes_exact(
        baseline_combined, metadata_combined, label="combined_pre_export"
    )
    if geometry_failures:
        raise RuntimeError("metadata changed combined geometry: " + ", ".join(geometry_failures))

    baseline_blob = baseline_combined.export(file_type="glb")
    metadata_blob = metadata_combined.export(file_type="glb")
    baseline_path = out_dir / f"xinyi_facade_canary_{selected_key}_baseline.glb"
    metadata_path = out_dir / f"xinyi_facade_canary_{selected_key}_metadata.glb"
    baseline_path.write_bytes(baseline_blob)
    metadata_path.write_bytes(metadata_blob)

    baseline_loaded = trimesh.load(
        io.BytesIO(baseline_blob), file_type="glb", force="mesh", process=False
    )
    metadata_loaded = trimesh.load(
        io.BytesIO(metadata_blob), file_type="glb", force="mesh", process=False
    )
    geometry_failures = compare_roundtrip_geometry(baseline_loaded, metadata_loaded)

    loaded_colors = np.asarray(metadata_loaded.visual.vertex_colors, dtype=np.uint8)
    if loaded_colors.ndim != 2 or loaded_colors.shape[1] < 4:
        geometry_failures.append("roundtrip_color0_missing")
        loaded_unique_rgba = []
    else:
        loaded_unique_rgba = sorted(
            tuple(map(int, row))
            for row in np.unique(loaded_colors[:, :4], axis=0)
        )
        expected_unique_rgba = sorted(rgba_counts)
        if loaded_unique_rgba != expected_unique_rgba:
            geometry_failures.append("roundtrip_rgba_set_changed")

    if geometry_failures:
        raise RuntimeError("real tile round-trip failed: " + ", ".join(geometry_failures))

    building_count = len(building_ids)
    surveyed_floor_buildings = len(floors_present)
    surveyed_ground_buildings = len(ground_present)
    report = {
        "status": "PASS_REAL_TILE_CANARY",
        "source": {
            "path": str(SOURCE),
            "sha256": source_sha,
            "expected_sha256": EXPECTED_SOURCE_SHA256,
        },
        "selection_policy": (
            "densest ordinary 500 m owner tile by source polygon-part count; "
            "ties resolved by tile key"
        ),
        "selected_tile": selected_key,
        "tile_origin_enu_m": list(selected_origin),
        "selection": selection,
        "geometry": {
            "building_count": building_count,
            "serialization_components": len(component_rows),
            "vertices": int(len(metadata_combined.vertices)),
            "triangles": int(len(metadata_combined.faces)),
            "bounds_tile_local_game_m": np.asarray(metadata_combined.bounds).tolist(),
            "baseline_glb_bytes": len(baseline_blob),
            "metadata_glb_bytes": len(metadata_blob),
            "metadata_overhead_bytes": len(metadata_blob) - len(baseline_blob),
            "baseline_sha256": sha256_bytes(baseline_blob),
            "metadata_sha256": sha256_bytes(metadata_blob),
            "pre_export_vertices_equal": True,
            "pre_export_faces_equal": True,
            "pre_export_bounds_equal": True,
            "roundtrip_vertices_equal": True,
            "roundtrip_faces_equal": True,
            "roundtrip_bounds_equal": True,
        },
        "coverage": {
            "surveyed_floors_buildings": surveyed_floor_buildings,
            "surveyed_floors_building_pct": (
                100.0 * surveyed_floor_buildings / building_count if building_count else 0.0
            ),
            "surveyed_ground_buildings": surveyed_ground_buildings,
            "surveyed_ground_building_pct": (
                100.0 * surveyed_ground_buildings / building_count if building_count else 0.0
            ),
        },
        "metadata": {
            "contract": "COLOR_0 = profile / appearance seed / floor height / floor phase",
            "profile_component_counts": dict(sorted(profile_counts.items())),
            "floor_height_source_component_counts": dict(sorted(floor_source_counts.items())),
            "floor_phase_source_component_counts": dict(sorted(phase_source_counts.items())),
            "unique_appearance_seeds": len(seed_counts),
            "appearance_seed_colliding_components": sum(v - 1 for v in seed_counts.values() if v > 1),
            "unique_rgba_values": len(rgba_counts),
            "roundtrip_unique_rgba_values": len(loaded_unique_rgba),
        },
        "outputs": {
            "baseline_glb": baseline_path.name,
            "metadata_glb": metadata_path.name,
            "component_metadata_json": "xinyi_facade_real_tile_canary.components.json",
        },
        "limitations": [
            "This proves only Python/Trimesh/GLB transport on one real accepted Xinyi tile.",
            "It does not prove Unreal Interchange vertex-color import.",
            "It does not prove Nanite, HLOD, World Partition or packaged runtime behavior.",
            "Profile IDs are diagnostic placeholders, not production Taipei art classifications.",
        ],
    }

    (out_dir / "xinyi_facade_real_tile_canary.components.json").write_text(
        json.dumps(component_rows, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "xinyi_facade_real_tile_canary.report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO / "unreal/Saved/XinyiFacadeCanary/real-tile",
    )
    args = parser.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
