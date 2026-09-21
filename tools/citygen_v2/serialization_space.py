"""Mesh only coordinates representable by GLB POSITION, before triangulation.

Ownership uses the existing source-part centroid and 500 m floor grid. No
building identity enters this policy. GEOS alone owns validity, precision
regularization and manifold linework canonicalization before triangulation.
"""
from __future__ import annotations

import math
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize
from shapely.validation import explain_validity

from geometry import _polygonal_parts

TILE_SIZE_M = 500.0
MIN_CONTACT_GAP_M = 0.000125


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


def _point_contact_holes(poly):
    exterior = LineString(poly.exterior.coords)
    holes = [LineString(h.coords) for h in poly.interiors]
    touched = set()
    unsupported = []
    for i, hole in enumerate(holes):
        inter = exterior.intersection(hole)
        if not inter.is_empty:
            if inter.geom_type in ("Point", "MultiPoint"):
                touched.add(i)
            else:
                unsupported.append(f"exterior_hole_contact:{i}:{inter.geom_type}")
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            inter = holes[i].intersection(holes[j])
            if not inter.is_empty:
                if inter.geom_type in ("Point", "MultiPoint"):
                    touched.update((i, j))
                else:
                    unsupported.append(f"hole_hole_contact:{i}:{j}:{inter.geom_type}")
    return touched, unsupported


def _regularize_point_contacts(poly, gap):
    touched, unsupported = _point_contact_holes(poly)
    if unsupported:
        return None, {
            "pass": False,
            "failures": unsupported,
            "touched_holes": sorted(touched),
            "gap_m": gap,
        }
    if not touched:
        return poly, {
            "pass": True,
            "failures": [],
            "touched_holes": [],
            "gap_m": gap,
            "touched_hole_perimeter_m": 0.0,
            "area_delta_m2": 0.0,
        }

    holes = []
    perimeter = 0.0
    for i, ring in enumerate(poly.interiors):
        hp = Polygon(ring.coords)
        if i in touched:
            perimeter += hp.length
            hp = hp.buffer(-gap, join_style=2)
        if hp.is_empty or hp.geom_type != "Polygon":
            return None, {
                "pass": False,
                "failures": [f"point_contact_hole_regularization_failed:{i}:{hp.geom_type}"],
                "touched_holes": sorted(touched),
                "gap_m": gap,
            }
        holes.append(hp.exterior.coords)

    regularized = quantize_polygon(Polygon(poly.exterior.coords, holes))
    if regularized.is_empty or not regularized.is_valid:
        return None, {
            "pass": False,
            "failures": ["point_contact_regularization_invalid_after_quantization"],
            "touched_holes": sorted(touched),
            "gap_m": gap,
        }
    remaining, unsupported_after = _point_contact_holes(regularized)
    if remaining or unsupported_after:
        return None, {
            "pass": False,
            "failures": ["point_contact_regularization_did_not_separate_boundaries", *unsupported_after],
            "touched_holes": sorted(touched),
            "remaining_touched_holes": sorted(remaining),
            "gap_m": gap,
        }
    return regularized, {
        "pass": True,
        "failures": [],
        "touched_holes": sorted(touched),
        "gap_m": gap,
        "touched_hole_perimeter_m": float(perimeter),
        "area_delta_m2": float(regularized.area - poly.area),
    }


def _canonical_faces(poly):
    """Rebuild exact GEOS boundary faces so earcut receives manifold rings."""
    lines = [LineString(poly.exterior.coords)]
    lines.extend(LineString(h.coords) for h in poly.interiors)
    noded = shapely.unary_union(lines)
    faces = list(polygonize(noded))
    kept = [
        quantize_polygon(face)
        for face in faces
        if face.area > 0 and poly.covers(face.representative_point())
    ]
    if not kept or any(p.is_empty or not p.is_valid or p.area <= 0 for p in kept):
        return []
    return kept


def prepare_footprint(original, origin):
    local = affinity.translate(original, xoff=-origin[0], yoff=-origin[1])
    coords = shapely.get_coordinates(local)
    max_spacing = float(np.max(np.abs(np.spacing(coords.astype(np.float32)))))
    xy_error = max(1e-6, 2 * max_spacing)
    contact_gap = max(MIN_CONTACT_GAP_M, 4 * max_spacing)

    quantized = quantize_polygon(local)
    valid_before = bool(quantized.is_valid)
    reason = explain_validity(quantized)
    repaired = quantized if valid_before else shapely.make_valid(
        quantized, method="structure", keep_collapsed=False)

    # GEOS intersections can introduce new non-float32 points. Requantize once,
    # then regularize only zero-dimensional ring contacts. A touching courtyard
    # is area-valid but extrudes to a non-manifold solid; shrinking only the
    # touching hole by a serialization-derived sub-millimetre gap preserves the
    # courtyard while creating a representable separator.
    initial_parts = [quantize_polygon(p) for p in _polygonal_parts(repaired)]
    failures = []
    if not initial_parts or any(p.is_empty or not p.is_valid or p.area <= 0 for p in initial_parts):
        failures.append("quantized_footprint_invalid_or_collapsed")
        return [], {
            "pass": False,
            "failures": failures,
            "valid_after_first_quantization": valid_before,
            "validity_reason": reason,
        }

    regularized_parts = []
    contact_rows = []
    contact_perimeter = 0.0
    contact_area_delta = 0.0
    touched_holes = 0
    for part in initial_parts:
        regularized, contact = _regularize_point_contacts(part, contact_gap)
        contact_rows.append(contact)
        if not contact["pass"] or regularized is None:
            failures.extend(contact["failures"])
            continue
        touched_holes += len(contact["touched_holes"])
        contact_perimeter += float(contact.get("touched_hole_perimeter_m", 0.0))
        contact_area_delta += float(contact.get("area_delta_m2", 0.0))
        regularized_parts.append(regularized)

    if failures or not regularized_parts:
        return [], {
            "pass": False,
            "failures": failures or ["no_parts_after_point_contact_regularization"],
            "valid_after_first_quantization": valid_before,
            "validity_reason": reason,
            "point_contact_regularization": contact_rows,
        }

    # Canonical GEOS linework face reconstruction is general and identity-based:
    # it changes ring decomposition/order, not intended covered area. It avoids
    # a small class of mature-earcut/trimesh non-manifold extrusions caused by
    # otherwise valid ring arrangements.
    parts = []
    for part in regularized_parts:
        parts.extend(_canonical_faces(part))
    if not parts:
        failures.append("linework_canonicalization_produced_no_faces")
        return [], {
            "pass": False,
            "failures": failures,
            "valid_after_first_quantization": valid_before,
            "validity_reason": reason,
            "point_contact_regularization": contact_rows,
        }

    combined = shapely.union_all(parts)
    base_area_error = max(1e-8, local.length * xy_error + math.pi * xy_error**2)
    contact_budget = contact_perimeter * contact_gap + touched_holes * math.pi * contact_gap**2
    area_error = base_area_error + contact_budget
    area_delta = float(combined.area - local.area)
    symmetric = float(combined.symmetric_difference(local).area)
    bounds_delta = np.abs(np.asarray(combined.bounds) - np.asarray(local.bounds))
    holes = sum(len(p.interiors) for p in parts)

    # A point-contact regularization intentionally adds only a sub-mm separator
    # along the touched hole boundary. Erode original hole cores by that same
    # documented gap before checking that courtyard interiors remain empty.
    core_margin = xy_error + (contact_gap if touched_holes else 0.0)
    core_fill = [
        float(combined.intersection(Polygon(h).buffer(-core_margin)).area)
        for h in local.interiors
    ]

    if abs(area_delta) > area_error:
        failures.append("quantized_area_delta_exceeds_budget")
    if symmetric > area_error:
        failures.append("quantized_symmetric_difference_exceeds_budget")
    if float(bounds_delta.max()) > xy_error:
        failures.append("quantized_bounds_displacement_exceeds_budget")
    if holes != len(local.interiors) or any(a > 1e-8 for a in core_fill):
        failures.append("quantized_courtyard_not_preserved")
    if sum(p.area for p in parts) - combined.area > 1e-8:
        failures.append("quantized_parts_overlap")

    report = {
        "pass": not failures,
        "failures": failures,
        "valid_after_first_quantization": valid_before,
        "validity_reason": reason,
        "geos_make_valid_used": not valid_before,
        "result_parts": len(parts),
        "original_area_m2": float(local.area),
        "quantized_area_m2": float(combined.area),
        "area_delta_m2": area_delta,
        "symmetric_difference_m2": symmetric,
        "original_holes": len(local.interiors),
        "quantized_holes": holes,
        "hole_core_filled_m2": core_fill,
        "bounds_displacement_m": bounds_delta.tolist(),
        "max_bounds_displacement_m": float(bounds_delta.max()),
        "point_contact_holes_regularized": touched_holes,
        "contact_gap_m": contact_gap,
        "contact_regularization_area_delta_m2": contact_area_delta,
        "contact_regularization_budget_m2": contact_budget,
        "point_contact_regularization": contact_rows,
        "linework_canonicalization": "GEOS unary_union + polygonize",
        "precision_budget": {
            "xy_m": xy_error,
            "base_area_m2": base_area_error,
            "contact_area_m2": contact_budget,
            "total_area_m2": area_error,
        },
        "coordinate_policy": (
            "tile-local float32 -> GEOS structure repair -> point-contact hole "
            "separator -> GEOS linework faces -> earcut"
        ),
    }
    return parts, report
