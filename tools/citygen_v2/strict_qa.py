"""Read-only solid QA adapted from PR #7; no meshing or repair code.

The expected footprint is GEOS output in ENU meters; mesh is glTF Y-up.
Tolerances are global numerical error budgets, never building-specific overrides.
"""
from __future__ import annotations

import math
import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient
import trimesh

TRI_AREA_EPS_M2 = 1e-8
AREA_NOISE_M2 = 1e-8


def strict_mesh_gate(mesh, footprint, height_m, *, precision='float64'):
    failures = []
    result = {'pass': False, 'failures': failures, 'precision': precision}
    v, f = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    result.update(vertices=len(v), triangles=len(f))
    if v.ndim != 2 or v.shape[1] != 3 or len(v) == 0:
        failures.append('no_valid_vertices')
        return result
    if f.ndim != 2 or f.shape[1] != 3 or len(f) == 0 or f.min() < 0 or f.max() >= len(v):
        failures.append('no_valid_triangles_or_indices')
        return result
    nonfinite = int(np.count_nonzero(~np.isfinite(v).all(axis=1)))
    result['nonfinite_vertices'] = nonfinite
    if nonfinite:
        failures.append(f'nonfinite_vertices:{nonfinite}')
        return result
    if not math.isfinite(height_m) or height_m <= 0 or footprint.is_empty or not footprint.is_valid:
        failures.append('invalid_expected_footprint_or_height')
        return result
    if precision not in ('float64', 'float32'):
        raise ValueError('unknown precision')

    # Two float32 ULPs cover quantization and one import/world-transform step.
    # The floor protects double-precision GEOS predicates; no geometry is snapped.
    if precision == 'float32':
        xy_error = max(1e-6, 2*float(np.max(np.abs(np.spacing(v[:, [0,2]].astype(np.float32))))))
        z_error = max(1e-6, 2*float(abs(np.spacing(np.float32(height_m)))))
    else:
        xy_error = z_error = 1e-7
    area_error = max(AREA_NOISE_M2, footprint.length*xy_error + math.pi*xy_error**2)
    volume_error = area_error*height_m + footprint.area*z_error
    result['tolerances'] = {'xy_m':xy_error, 'height_m':z_error,
                            'coverage_m2':area_error, 'volume_m3':volume_error,
                            'zero_triangle_m2':TRI_AREA_EPS_M2, 'overlap_m2':AREA_NOISE_M2}

    tri = v[f]
    cross = np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0])
    magnitudes = np.linalg.norm(cross, axis=1)
    areas = magnitudes/2
    zero = int(np.count_nonzero(areas <= TRI_AREA_EPS_M2))
    normals = np.divide(cross, magnitudes[:,None], out=np.zeros_like(cross), where=magnitudes[:,None] > 0)
    result['zero_area_triangles'] = zero
    if zero:
        failures.append(f'zero_area_triangles:{zero}')

    # Exact position welding solely for topology QA of split normals/UVs.
    # np.unique does not move any coordinate and never repairs the output mesh.
    unique, inverse = np.unique(v, axis=0, return_inverse=True)
    topology = trimesh.Trimesh(vertices=unique, faces=inverse[f], process=False)
    result.update(watertight=bool(topology.is_watertight),
                  winding_consistent=bool(topology.is_winding_consistent),
                  volume_m3=float(topology.volume))
    if not topology.is_watertight:
        failures.append('not_watertight')
    if not topology.is_winding_consistent:
        failures.append('inconsistent_winding')
    if not math.isfinite(topology.volume) or topology.volume <= 0:
        failures.append('not_positive_volume')
    expected_volume = float(footprint.area * height_m)
    volume_delta = abs(topology.volume - expected_volume)
    result.update(expected_volume_m3=expected_volume, volume_error_m3=float(volume_delta))
    if volume_delta > volume_error:
        failures.append('volume_not_footprint_area_times_height')
    if abs(v[:,1].min()) > z_error or abs(v[:,1].max()-height_m) > z_error:
        failures.append('base_or_roof_elevation_mismatch')

    roof = np.all(np.isclose(tri[:,:,1], height_m, atol=z_error, rtol=0), axis=1)
    base = np.all(np.isclose(tri[:,:,1], 0, atol=z_error, rtol=0), axis=1)
    wrong_roof = int(np.count_nonzero(normals[roof,1] <= .999))
    wrong_base = int(np.count_nonzero(normals[base,1] >= -.999))
    result.update(roof_triangles=int(roof.sum()), base_triangles=int(base.sum()),
                  wrong_roof_triangles=wrong_roof, wrong_base_triangles=wrong_base,
                  expected_holes=len(footprint.interiors))
    if wrong_roof:
        failures.append(f'roof_normal_not_up:{wrong_roof}')
    if wrong_base:
        failures.append(f'base_normal_not_down:{wrong_base}')

    result['caps'] = {}
    for name, mask in [('roof',roof), ('base',base)]:
        if not mask.any():
            failures.append(f'missing_{name}_cap')
            continue
        # glTF (x,y,z) -> footprint (east=x,north=-z).
        triangles_2d = [Polygon(t[:,[0,2]] * [1,-1]) for t in tri[mask]]
        cap = shapely.union_all(triangles_2d)
        symmetric = float(cap.symmetric_difference(footprint).area)
        area_sum = sum(p.area for p in triangles_2d)
        overlap = max(0., area_sum-cap.area)
        missing = float(footprint.difference(cap).area)
        outside = float(cap.difference(footprint).area)
        polygons = [cap] if cap.geom_type == 'Polygon' else list(getattr(cap,'geoms',[]))
        holes = sum(len(p.interiors) for p in polygons if p.geom_type == 'Polygon')
        # A tiny hole cannot disappear merely because the whole-footprint area
        # budget is larger: also require exact hole count and empty hole cores.
        hole_fill = [float(cap.intersection(Polygon(h).buffer(-xy_error)).area) for h in footprint.interiors]
        result['caps'][name] = {'symmetric_difference_m2':symmetric, 'missing_m2':missing,
                                'outside_m2':outside, 'overlap_m2':float(overlap),
                                'triangle_area_sum_m2':float(area_sum), 'union_area_m2':float(cap.area),
                                'holes':holes, 'hole_core_filled_m2':hole_fill}
        if symmetric > area_error:
            failures.append(f'{name}_footprint_coverage_mismatch')
        if overlap > AREA_NOISE_M2:
            failures.append(f'{name}_overlapping_triangles')
        if abs(area_sum-footprint.area) > area_error:
            failures.append(f'{name}_cap_area_missing_or_excess')
        if holes != len(footprint.interiors) or any(a > AREA_NOISE_M2 for a in hole_fill):
            failures.append(f'{name}_courtyard_not_preserved')

    # Wall direction is checked against the exact oriented footprint boundary,
    # not by probing a fixed distance on either side. Fixed-distance probes can
    # cross sub-millimetre notches that are still perfectly representable and
    # therefore report false reversed walls. Canonical GEOS ring orientation
    # gives a scale-independent expected outward direction: exterior CCW and
    # holes CW both place solid interior on the left, so outward is the
    # right-hand normal of each directed boundary edge.
    canonical = orient(footprint, sign=1.0)
    expected_edges = {}
    ambiguous_edges = set()

    def add_ring(ring):
        coords = list(ring.coords)
        for a, b in zip(coords, coords[1:]):
            a = (float(a[0]), float(a[1]))
            b = (float(b[0]), float(b[1]))
            if a == b:
                continue
            key = tuple(sorted((a, b)))
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            expected = np.asarray([dy/length, -dx/length])
            if key in expected_edges and np.dot(expected_edges[key], expected) < .999999:
                ambiguous_edges.add(key)
            else:
                expected_edges[key] = expected

    add_ring(canonical.exterior)
    for ring in canonical.interiors:
        add_ring(ring)

    bad_walls = []
    unmatched_walls = []
    ambiguous_walls = []
    for index in np.flatnonzero(~(roof|base)):
        normal = normals[index]
        projected = tri[index][:,[0,2]] * [1,-1]
        unique = np.unique(projected, axis=0)
        if len(unique) != 2 or abs(normal[1]) > 1e-5:
            bad_walls.append(int(index))
            unmatched_walls.append(int(index))
            continue
        key = tuple(sorted((tuple(map(float, unique[0])), tuple(map(float, unique[1])))))
        if key in ambiguous_edges:
            bad_walls.append(int(index))
            ambiguous_walls.append(int(index))
            continue
        expected = expected_edges.get(key)
        horizontal = normal[[0,2]] * [1,-1]
        hlen = float(np.linalg.norm(horizontal))
        if expected is None or hlen == 0 or float(np.dot(horizontal / hlen, expected)) <= .999:
            bad_walls.append(int(index))
            if expected is None:
                unmatched_walls.append(int(index))

    result.update(wall_direction_policy='oriented_boundary_edge',
                  wrong_wall_triangles=len(bad_walls),
                  wrong_wall_face_indices=bad_walls,
                  unmatched_wall_face_indices=unmatched_walls,
                  ambiguous_wall_face_indices=ambiguous_walls)
    if bad_walls:
        failures.append(f'wall_normal_not_outward:{len(bad_walls)}')
    result['pass'] = not failures
    return result
