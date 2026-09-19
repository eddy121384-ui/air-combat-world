"""Auditable Shapely/GEOS -> earcut/trimesh -> spatial GLB pipeline.

Run from the repository: python -m tools.citygen_v2.build --stage sample
All geometry is ENU meters until the explicit right-handed glTF transform.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import time

import numpy as np
import psutil
import shapely
from shapely.geometry import Polygon, Point
from shapely import affinity
import trimesh

from tools.compiler.worldmodel import (
    build_worldmodel, enu_origin_from_city_yaml, lonlat_to_enu, TAIPEI_101_LONLAT,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/generated/taipei/sample_buildings.geojson'
CITY = ROOT / 'cities/taipei/city.yaml'
OUT = ROOT / 'unreal/Saved/CitygenV2/output'
AREA_EPS = 1e-6  # square meters; measured/reportable, never a footprint inflation
TRI_EPS = 1e-10
GLTF_FROM_ENU = np.array([[1, 0, 0, 0], [0, 0, 1, 0],
                          [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def polygon_leaves(geometry):
    """Only unpack GEOS output; this implements no geometric operation."""
    if geometry.geom_type == 'Polygon':
        return [geometry], []
    if hasattr(geometry, 'geoms'):
        polygons, collapsed = [], []
        for child in geometry.geoms:
            p, c = polygon_leaves(child)
            polygons.extend(p)
            collapsed.extend(c)
        return polygons, collapsed
    return [], [{'type': geometry.geom_type, 'wkt': geometry.wkt}]


def classify(rings):
    """GEOS decides validity/repair; retain all rejected/collapsed evidence."""
    record = {'interior_rings': max(0, len(rings) - 1)}
    points = [p for ring in rings for p in ring]
    if not points or not all(len(p) == 2 and all(math.isfinite(x) for x in p) for p in points):
        return {**record, 'outcome': 'rejected', 'reason': 'empty_or_nonfinite_coordinates'}, []
    record['repeated_vertices'] = sum(
        len(r[:-1] if len(r) > 1 and r[0] == r[-1] else r)
        - len(set(map(tuple, r))) for r in rings)
    try:
        original = Polygon(rings[0], rings[1:])
    except ValueError as exc:
        return {**record, 'outcome': 'rejected', 'reason': f'polygon_construction:{exc}'}, []
    record.update(input_valid=bool(original.is_valid),
                  validity_reason=shapely.is_valid_reason(original), input_area_m2=original.area)
    fixed = original if original.is_valid else shapely.make_valid(original, method='linework')
    polys, collapsed = polygon_leaves(fixed)
    # GEOS exact duplicate/collinear normalization, never an authored repair algorithm.
    polys = [shapely.remove_repeated_points(p, tolerance=0).simplify(0, preserve_topology=True)
             for p in polys]
    record['repair_result_type'] = fixed.geom_type
    record['collapsed_components'] = collapsed
    record['near_zero_components_m2'] = [p.area for p in polys if p.area <= AREA_EPS]
    polys = sorted((shapely.normalize(p) for p in polys if p.area > AREA_EPS), key=lambda p: p.wkb_hex)
    record['output_polygon_count'] = len(polys)
    record['output_area_m2'] = sum(p.area for p in polys)
    if not polys:
        record.update(outcome='rejected', reason='no_polygonal_area_after_GEOS_make_valid')
    else:
        record.update(outcome='valid_as_is' if original.is_valid else 'repaired',
                      reason='valid_geometry' if original.is_valid else 'GEOS_make_valid_linework')
    return record, polys


def audit(source=SOURCE, city=CITY):
    features = json.loads(source.read_text(encoding='utf-8'))['features']
    wm = build_worldmodel(source, city)  # existing height, ENU and hero contract
    by_id = {b['id']: b for b in wm['buildings']}
    origin = enu_origin_from_city_yaml(city)
    rows, parts = [], {}
    source_types, reasons, outcomes = Counter(), Counter(), Counter()
    coordinate_count = on_grid = 0
    ids = [str(f.get('id', f'source-{i}')) for i, f in enumerate(features)]
    if len(set(ids)) != len(ids):
        raise ValueError('Source IDs must be unique: refusing ambiguous WorldModel join')
    feature_rejections = []
    for fi, f in enumerate(features):
        fid = ids[fi]
        geom = f.get('geometry') or {}
        kind = geom.get('type', 'null')
        source_types[kind] += 1
        if kind not in ('Polygon', 'MultiPolygon'):
            feature_rejections.append({'id': fid, 'reason': f'unsupported_geometry:{kind}'})
            continue
        polygons = [geom['coordinates']] if kind == 'Polygon' else geom['coordinates']
        if not polygons:
            feature_rejections.append({'id': fid, 'reason': 'empty_polygon_collection'})
        b = by_id.get(fid)
        for pi, coordinates in enumerate(polygons):
            for ring in coordinates:
                for x, y in ring:
                    coordinate_count += 2
                    on_grid += int(abs(x*10000-round(x*10000)) < 1e-7)
                    on_grid += int(abs(y*10000-round(y*10000)) < 1e-7)
            rings = [[list(lonlat_to_enu(x, y, *origin)) for x, y in r] for r in coordinates]
            row, result = classify(rings)
            key = f'{fid}/part-{pi}'
            row.update(key=key, feature_id=fid, part_index=pi, source_type=kind,
                       source_feature_part_count=len(polygons), height_m=f['properties'].get('height_m'),
                       height_source=f['properties'].get('height_source'),
                       suppressed=bool(b and b['suppressed']),
                       suppress_reason=b['suppress_reason'] if b else None)
            if b is None:
                row.update(outcome='rejected', reason='not_in_WorldModel_invalid_height_or_geometry')
                result = []
            else:
                if row['height_m'] != b['height_m']:
                    raise ValueError(f'WorldModel height mismatch: {key}')
                # Existing v0 contains exteriors only; source supplies missing holes.
                if pi < len(b['polygons']):
                    if rings[0] != [list(p) for p in b['polygons'][pi]['footprint_enu']]:
                        raise ValueError(f'WorldModel exterior mismatch: {key}')
            row['output_holes'] = sum(len(p.interiors) for p in result)
            row['output_triangle_footprints'] = sum(len(p.exterior.coords) == 4 and not p.interiors for p in result)
            rows.append(row)
            parts[key] = result
            outcomes[row['outcome']] += 1
            reasons[row.get('validity_reason', row['reason']).split('[')[0]] += 1
    summary = {
        'source_sha256': sha(source), 'source_features': len(features),
        'worldmodel_features': len(wm['buildings']), 'geometry_types': dict(source_types),
        'polygon_parts': len(rows), 'outcomes': dict(outcomes), 'validity_reasons': dict(reasons),
        'feature_rejections': feature_rejections,
        'rejection_reasons': dict(Counter(r['reason'] for r in rows if r['outcome'] == 'rejected')),
        'source_interior_rings': sum(r['interior_rings'] for r in rows),
        'parts_with_holes': sum(r['interior_rings'] > 0 for r in rows),
        'parts_with_repeated_vertices': sum(r.get('repeated_vertices', 0) > 0 for r in rows),
        'parts_with_near_zero_input_area': sum(r.get('input_area_m2', 0) <= AREA_EPS for r in rows),
        'repaired_with_collapsed_components': sum(r['outcome'] == 'repaired' and bool(r['collapsed_components']) for r in rows),
        'output_polygon_components': sum(len(p) for p in parts.values()),
        'output_holes': sum(r['output_holes'] for r in rows),
        'output_triangle_footprints': sum(r['output_triangle_footprints'] for r in rows),
        'hero_suppressed_features': wm['hero_match']['matched_count'],
        'hero_suppressed_parts': sum(r['suppressed'] for r in rows),
        'coordinate_values': coordinate_count, 'values_on_0_0001_degree_grid': on_grid,
        'grid_step_m': [lonlat_to_enu(origin[0]+0.0001, origin[1], *origin)[0],
                        lonlat_to_enu(origin[0], origin[1]+0.0001, *origin)[1]],
        'local_frame': wm['local_frame'], 'hero_match': wm['hero_match'],
    }
    assert sum(outcomes.values()) == len(rows)
    return summary, rows, parts, wm


def check_solid(mesh, polygon, height, atol=1e-6):
    """Independent invariants, including cap coverage and outward cavity walls."""
    v, tri = mesh.vertices, mesh.triangles
    if not np.isfinite(v).all() or np.any(mesh.area_faces <= TRI_EPS):
        raise ValueError('nonfinite_coordinates_or_zero_area_triangles')
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError('not_a_closed_outward_solid')
    if not np.isclose(mesh.volume, polygon.area * height, rtol=1e-5, atol=atol):
        raise ValueError('volume_does_not_match_footprint_times_height')
    roof = np.all(np.isclose(tri[:, :, 2], height, rtol=0, atol=atol), axis=1)
    base = np.all(np.isclose(tri[:, :, 2], 0, rtol=0, atol=atol), axis=1)
    if not roof.any() or not base.any():
        raise ValueError('missing_caps')
    if np.any(mesh.face_normals[roof, 2] < .999) or np.any(mesh.face_normals[base, 2] > -.999):
        raise ValueError('wrong_cap_direction')
    for mask in (roof, base):
        cap = shapely.union_all([Polygon(t[:, :2]) for t in tri[mask]])
        if cap.symmetric_difference(polygon).area > max(atol, polygon.area * 1e-5):
            raise ValueError('cap_does_not_cover_footprint_or_fills_hole')
        if abs(sum(mesh.area_faces[mask]) - polygon.area) > max(atol, polygon.area * 1e-5):
            raise ValueError('overlapping_or_missing_cap_triangles')
    for t, normal in zip(tri[~(roof | base)], mesh.face_normals[~(roof | base)]):
        middle = t[:, :2].mean(axis=0)
        # Probe sides only, using GEOS containment (including courtyard holes).
        delta = normal[:2] * 0.0001
        if polygon.contains(Point(middle + delta)) or not polygon.covers(Point(middle - delta)):
            raise ValueError('wall_not_outward')
    return {'vertices': len(v), 'triangles': len(mesh.faces), 'roof_triangles': int(roof.sum()),
            'base_triangles': int(base.sum()), 'volume_m3': float(mesh.volume)}


def representative(rows, parts, count=80):
    candidates = [r for r in rows if parts[r['key']] and not r['suppressed']]
    selected, reasons = {}, defaultdict(list)

    def take(tag, ordered, n):
        for row in ordered[:n]:
            selected[row['key']] = row
            reasons[row['key']].append(tag)

    def primary(r):
        return max(parts[r['key']], key=lambda p: p.area)

    take('complex', sorted(candidates, key=lambda r: (-len(primary(r).exterior.coords), r['key'])), 8)
    take('courtyard', [r for r in candidates if r['output_holes']], 8)
    take('multipart_source', [r for r in candidates if r['source_feature_part_count'] > 1], 4)
    take('repaired', [r for r in candidates if r['outcome'] == 'repaired'], 8)
    take('rectangle', [r for r in candidates if len(primary(r).exterior.coords) == 5 and
                      math.isclose(primary(r).area, primary(r).minimum_rotated_rectangle.area)], 8)
    take('concave', [r for r in candidates if primary(r).convex_hull.area > primary(r).area * 1.2], 8)
    # Prior PR #3 bad low-rise triangle at ENU (-908,-902); nearby unchanged GIS.
    target = Point(-900, -900)
    take('previous_failure_neighborhood_lowrise', sorted(
        [r for r in candidates if r['height_m'] < 20],
        key=lambda r: (primary(r).distance(target), r['key'])), count - len(selected))
    if len(selected) < count:
        take('fill', [r for r in candidates if r['key'] not in selected], count-len(selected))
    return sorted(selected.values(), key=lambda r: r['key']), dict(reasons)


def export_tiles(rows, parts, destination, tile_size=500):
    """One complete part per ownership cell; no clipping or seam reconstruction."""
    destination.mkdir(parents=True, exist_ok=False)
    buckets = defaultdict(list)
    for row in rows:
        if row['suppressed'] or not parts[row['key']]:
            continue
        point = shapely.union_all(parts[row['key']]).representative_point()
        tile = (math.floor(point.x / tile_size), math.floor(point.y / tile_size))
        buckets[tile].append(row)
    files, failures, checks, diagnostics = [], [], [], []
    for (ix, iy), members in sorted(buckets.items()):
        origin = [ix*tile_size, iy*tile_size, 0]
        meshes = []
        for row in members:
            row_meshes, row_checks = [], []
            try:
                for component, p in enumerate(parts[row['key']]):
                    local = affinity.translate(p, -origin[0], -origin[1])
                    mesh = trimesh.creation.extrude_polygon(local, row['height_m'], engine='earcut')
                    # Validate the actual float32 positions the GLB will contain.
                    mesh.vertices = mesh.vertices.astype(np.float32).astype(np.float64)
                    row_meshes.append(mesh)
                    stats = check_solid(mesh, local, row['height_m'], atol=2e-4)
                    row_checks.append({'key': row['key'], 'component': component, **stats})
            except (ValueError, RuntimeError) as exc:
                failure = {'key': row['key'], 'component': component, 'reason': str(exc)}
                failures.append(failure)
                if row_meshes:
                    diagnostic = trimesh.util.concatenate(row_meshes)
                    diagnostic.apply_translation(origin)
                    diagnostic.apply_transform(GLTF_FROM_ENU)
                    diagnostics.append((row['key'].replace('/', '_'), diagnostic))
                continue  # explicitly reported; any failure fails the gate
            meshes.extend(row_meshes)
            checks.extend(row_checks)
        if not meshes:
            continue
        merged = trimesh.util.concatenate(meshes)
        merged.apply_transform(GLTF_FROM_ENU)
        topology_vertices = len(merged.vertices)
        # Library operation for flat shading. Validate topology before splitting;
        # independent GLB QA welds coincident positions per component.
        merged.unmerge_vertices()
        merged.vertex_normals = np.repeat(merged.face_normals, 3, axis=0)
        merged.visual = trimesh.visual.TextureVisuals(
            uv=merged.vertices[:, [0, 2]] / 100,
            material=trimesh.visual.material.PBRMaterial(name='whitebox_grey',
                baseColorFactor=[190, 190, 190, 255], metallicFactor=0, roughnessFactor=1,
                doubleSided=False))
        scene = trimesh.Scene()
        name = f'xinyi_v2_{ix}_{iy}'
        transform = np.eye(4)
        transform[:3, 3] = GLTF_FROM_ENU[:3, :3] @ origin
        scene.add_geometry(merged, node_name=name, geom_name=name, transform=transform,
                           metadata={'tile_origin_enu_m': origin, 'source_parts': [r['key'] for r in members]})
        path = destination / f'{name}.glb'
        path.write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))
        files.append({'file': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size,
                      'origin_enu_m': origin, 'vertices': len(merged.vertices),
                      'topology_vertices': topology_vertices,
                      'triangles': len(merged.faces), 'bounds_gltf_m': scene.bounds.tolist()})
    diagnostic_file = None
    if diagnostics:
        scene = trimesh.Scene()
        for name, mesh in diagnostics:
            mesh.unmerge_vertices()
            mesh.vertex_normals = np.repeat(mesh.face_normals, 3, axis=0)
            scene.add_geometry(mesh, node_name=name, geom_name=name)
        diagnostic_file = destination / 'FAILED_DIAGNOSTICS_DO_NOT_IMPORT_TO_UE.glb'
        diagnostic_file.write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))
    return {'tiles': files, 'failures': failures, 'component_checks': checks,
            'diagnostic_file': diagnostic_file.name if diagnostic_file else None,
            'processed_features': len(set(r['feature_id'] for r in rows)),
            'processed_parts': len(rows), 'emitted_parts': len(set(c['key'] for c in checks)),
            'triangles': sum(f['triangles'] for f in files),
            'vertices': sum(f['vertices'] for f in files),
            'output_bytes': sum(f['bytes'] for f in files)}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', choices=['audit', 'sample'], default='sample')
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    started = time.perf_counter()
    summary, rows, parts, wm = audit()
    audit_seconds = time.perf_counter() - started
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / 'accounting.json', summary)
    with (args.out / 'parts.jsonl').open('w', encoding='utf-8') as out:
        for row in rows:
            out.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
    if args.stage == 'audit':
        print(json.dumps(summary, indent=2))
        return
    # Full generation is deliberately unavailable until the representative gate
    # passes. This spike stopped at that gate; no speculative UE/hero exporter.
    chosen, reasons = representative(rows, parts)
    generation_start = time.perf_counter()
    result = export_tiles(chosen, parts, args.out / args.stage)
    result.update(stage=args.stage, source_sha256=summary['source_sha256'],
                  selected_parts=[r['key'] for r in chosen], selection_reasons=reasons,
                  elapsed_seconds=time.perf_counter()-started,
                  audit_seconds=audit_seconds,
                  sample_selection_and_reporting_seconds=generation_start-started-audit_seconds,
                  mesh_generation_export_seconds=time.perf_counter()-generation_start,
                  peak_working_set_bytes=getattr(psutil.Process().memory_info(), 'peak_wset', None),
                  dependencies={p: importlib.metadata.version(p) for p in
                                ['numpy', 'shapely', 'trimesh', 'mapbox-earcut', 'psutil']},
                  geos_version=shapely.geos_version_string,
                  raw_geometry_gate='pass' if not result['failures'] else 'fail')
    write_json(args.out / f'{args.stage}.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in
                      ('tiles','selected_parts','selection_reasons','component_checks')}, indent=2))
    if result['failures']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
