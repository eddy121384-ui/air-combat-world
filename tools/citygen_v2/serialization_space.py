"""Mesh only coordinates representable by GLB POSITION, before triangulation.

Ownership uses the existing source-part centroid and 500 m floor grid. No
building identity enters this policy. GEOS alone may repair invalid polygons;
unstable repair output or changes beyond the global precision budget fail shut.
"""
from __future__ import annotations

import math
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Polygon
from shapely.validation import explain_validity

from geometry import _polygonal_parts

TILE_SIZE_M = 500.0


def tile_origin(centroid):
    return tuple(math.floor(float(c) / TILE_SIZE_M) * TILE_SIZE_M for c in centroid)


def tile_transform(origin):
    transform = np.eye(4)
    transform[:3, 3] = [origin[0], 0., -origin[1]]
    return transform


def quantize_polygon(poly):
    def ring(coords):
        return np.asarray(coords, dtype=np.float64).astype(np.float32).astype(np.float64)
    return Polygon(ring(poly.exterior.coords), [ring(h.coords) for h in poly.interiors])


def prepare_footprint(original, origin):
    local = affinity.translate(original, xoff=-origin[0], yoff=-origin[1])
    quantized = quantize_polygon(local)
    valid_before = bool(quantized.is_valid)
    reason = explain_validity(quantized)
    repaired = quantized if valid_before else shapely.make_valid(
        quantized, method='structure', keep_collapsed=False)
    # GEOS intersections can introduce new non-float32 points. Requantize once,
    # then require valid, disjoint polygonal output. No repeated repair/search.
    parts = [quantize_polygon(p) for p in _polygonal_parts(repaired)]
    failures = []
    if not parts or any(p.is_empty or not p.is_valid or p.area <= 0 for p in parts):
        failures.append('quantized_footprint_invalid_or_collapsed')
        return [], {'pass':False, 'failures':failures,
                    'valid_after_first_quantization':valid_before, 'validity_reason':reason}
    combined = shapely.union_all(parts)
    coords = shapely.get_coordinates(local)
    xy_error = max(1e-6, 2*float(np.max(np.abs(np.spacing(coords.astype(np.float32))))))
    area_error = max(1e-8, local.length*xy_error + math.pi*xy_error**2)
    area_delta = float(combined.area-local.area)
    symmetric = float(combined.symmetric_difference(local).area)
    bounds_delta = np.abs(np.asarray(combined.bounds)-np.asarray(local.bounds))
    holes = sum(len(p.interiors) for p in parts)
    core_fill = [float(combined.intersection(Polygon(h).buffer(-xy_error)).area)
                 for h in local.interiors]
    if abs(area_delta) > area_error:
        failures.append('quantized_area_delta_exceeds_budget')
    if symmetric > area_error:
        failures.append('quantized_symmetric_difference_exceeds_budget')
    if float(bounds_delta.max()) > xy_error:
        failures.append('quantized_bounds_displacement_exceeds_budget')
    if holes != len(local.interiors) or any(a > 1e-8 for a in core_fill):
        failures.append('quantized_courtyard_not_preserved')
    if sum(p.area for p in parts)-combined.area > 1e-8:
        failures.append('quantized_parts_overlap')
    report = {'pass':not failures, 'failures':failures,
              'valid_after_first_quantization':valid_before, 'validity_reason':reason,
              'geos_make_valid_used':not valid_before, 'result_parts':len(parts),
              'original_area_m2':float(local.area), 'quantized_area_m2':float(combined.area),
              'area_delta_m2':area_delta, 'symmetric_difference_m2':symmetric,
              'original_holes':len(local.interiors), 'quantized_holes':holes,
              'hole_core_filled_m2':core_fill,
              'bounds_displacement_m':bounds_delta.tolist(),
              'max_bounds_displacement_m':float(bounds_delta.max()),
              'precision_budget':{'xy_m':xy_error, 'area_m2':area_error},
              'coordinate_policy':'float32 -> float64 before earcut; GEOS structure only'}
    return parts, report
