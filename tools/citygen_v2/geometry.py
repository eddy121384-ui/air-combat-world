"""Mature-library geometry path for Xinyi Robust Whitebox v2.

Policy:
- Shapely/GEOS owns polygon validity and repair.
- GEOS constrained Delaunay triangulation owns cap triangulation.
- trimesh owns extrusion and mesh topology checks.
- No custom triangulator, hole bridge, or polygon repair lives here.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import shapely
import trimesh
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.validation import explain_validity

AREA_EPS_M2 = 1.0e-6
TRI_AREA_EPS_M2 = 1.0e-8

# ENU polygon is (east=x, north=y), trimesh extrusion starts Z-up.
# Game/GLB frame is (east=x, up=y, north=-z). This is a proper rotation
# (determinant +1), so face winding is preserved.
GAME_FROM_ENU_ZUP = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
    dtype=float,
)


def _distinct_xy_count(ring: Iterable[Iterable[float]]) -> int:
    """Exact distinct coordinate count; diagnostic only, not geometry repair."""
    return len({(float(p[0]), float(p[1])) for p in ring})


def _polygonal_parts(geom) -> list[Polygon]:
    """Extract polygonal members from a GEOS result without inventing geometry."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    if isinstance(geom, GeometryCollection):
        out: list[Polygon] = []
        for child in geom.geoms:
            out.extend(_polygonal_parts(child))
        return out
    return []


def repair_worldmodel_polygon(poly_record: dict) -> tuple[list[Polygon], dict]:
    """Convert one WorldModel polygon record into valid polygonal GEOS parts.

    Lower-dimensional/collapsed inputs are rejected explicitly. Invalid
    area-bearing polygons are repaired only by GEOS make_valid(structure).
    """
    outer = poly_record["footprint_enu"]
    holes = poly_record.get("holes_enu", [])

    if _distinct_xy_count(outer) < 3:
        return [], {
            "status": "rejected",
            "reason": "collapsed_source_outer",
            "source_valid": False,
            "validity_reason": "fewer than 3 distinct exterior coordinates",
            "repaired": False,
            "source_area_m2": 0.0,
            "result_area_m2": 0.0,
            "result_parts": 0,
            "source_holes": len(holes),
            "result_holes": 0,
        }

    try:
        source = Polygon(outer, holes)
    except Exception as exc:
        return [], {
            "status": "rejected",
            "reason": "polygon_constructor_error",
            "source_valid": False,
            "validity_reason": f"{type(exc).__name__}: {exc}",
            "repaired": False,
            "source_area_m2": 0.0,
            "result_area_m2": 0.0,
            "result_parts": 0,
            "source_holes": len(holes),
            "result_holes": 0,
        }

    source_area = float(source.area) if math.isfinite(float(source.area)) else 0.0
    source_valid = bool(source.is_valid)
    validity_reason = "Valid Geometry" if source_valid else explain_validity(source)

    if source.is_empty or source_area <= AREA_EPS_M2:
        return [], {
            "status": "rejected",
            "reason": "zero_or_near_zero_source_area",
            "source_valid": source_valid,
            "validity_reason": validity_reason,
            "repaired": False,
            "source_area_m2": source_area,
            "result_area_m2": 0.0,
            "result_parts": 0,
            "source_holes": len(holes),
            "result_holes": 0,
        }

    repaired = False
    result = source
    if not source_valid:
        repaired = True
        # GEOS structure mode uses ring structure. keep_collapsed=False
        # deliberately rejects line/point remnants instead of inventing mass.
        result = make_valid(source, method="structure", keep_collapsed=False)

    parts = [p for p in _polygonal_parts(result) if (not p.is_empty and p.area > AREA_EPS_M2)]
    if not parts:
        return [], {
            "status": "rejected",
            "reason": "no_polygonal_area_after_make_valid",
            "source_valid": source_valid,
            "validity_reason": validity_reason,
            "repaired": repaired,
            "source_area_m2": source_area,
            "result_area_m2": 0.0,
            "result_parts": 0,
            "source_holes": len(holes),
            "result_holes": 0,
        }

    bad = [explain_validity(p) for p in parts if not p.is_valid]
    if bad:
        return [], {
            "status": "rejected",
            "reason": "invalid_after_make_valid",
            "source_valid": source_valid,
            "validity_reason": "; ".join(bad),
            "repaired": repaired,
            "source_area_m2": source_area,
            "result_area_m2": float(sum(p.area for p in parts)),
            "result_parts": len(parts),
            "source_holes": len(holes),
            "result_holes": sum(len(p.interiors) for p in parts),
        }

    return parts, {
        "status": "repaired" if repaired else "ready",
        "reason": None,
        "source_valid": source_valid,
        "validity_reason": validity_reason,
        "repaired": repaired,
        "source_area_m2": source_area,
        "result_area_m2": float(sum(p.area for p in parts)),
        "result_parts": len(parts),
        "source_holes": len(holes),
        "result_holes": sum(len(p.interiors) for p in parts),
    }


def _constrained_delaunay_arrays(poly: Polygon) -> tuple[np.ndarray, np.ndarray]:
    """Return exact polygon vertices/faces from GEOS constrained Delaunay triangles.

    GEOS owns triangulation. This function only deduplicates identical 2D
    coordinates into an indexed array for trimesh.extrude_triangulation.
    """
    collection = shapely.constrained_delaunay_triangles(poly)
    triangles = _polygonal_parts(collection)
    if not triangles:
        raise ValueError("GEOS constrained Delaunay returned no triangles")

    vertices: list[tuple[float, float]] = []
    index: dict[tuple[float, float], int] = {}
    faces: list[list[int]] = []

    for triangle in triangles:
        coords = [(float(x), float(y)) for x, y in list(triangle.exterior.coords)[:-1]]
        if len(coords) != 3:
            raise ValueError("GEOS constrained Delaunay returned a non-triangle polygon")

        # Canonical CCW winding in ENU 2D before extrusion.
        signed2 = (
            coords[0][0] * (coords[1][1] - coords[2][1])
            + coords[1][0] * (coords[2][1] - coords[0][1])
            + coords[2][0] * (coords[0][1] - coords[1][1])
        )
        if signed2 < 0.0:
            coords[1], coords[2] = coords[2], coords[1]

        face = []
        for point in coords:
            if point not in index:
                index[point] = len(vertices)
                vertices.append(point)
            face.append(index[point])
        faces.append(face)

    return np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def extrude_geos_polygon(poly: Polygon, height_m: float) -> trimesh.Trimesh:
    """Constrained-Delaunay triangulate + extrude using mature libraries only."""
    if not math.isfinite(height_m) or height_m <= 0.0:
        raise ValueError(f"invalid building height: {height_m}")
    if poly.is_empty or not poly.is_valid or poly.area <= AREA_EPS_M2:
        raise ValueError("extrude_geos_polygon requires a valid area-bearing Polygon")

    vertices_2d, faces_2d = _constrained_delaunay_arrays(poly)
    mesh = trimesh.creation.extrude_triangulation(
        vertices=vertices_2d,
        faces=faces_2d,
        height=float(height_m),
    )
    mesh.apply_transform(GAME_FROM_ENU_ZUP)
    return mesh


def mesh_gate(mesh: trimesh.Trimesh, expected_height_m: float) -> dict:
    """Numerical acceptance gate for one extruded solid in game coordinates."""
    failures: list[str] = []
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)

    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        failures.append("no_vertices")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        failures.append("no_triangles")
    if not np.isfinite(vertices).all():
        failures.append("nonfinite_vertices")

    areas = np.asarray(mesh.area_faces)
    zero_area_count = int(np.count_nonzero(~np.isfinite(areas) | (areas <= TRI_AREA_EPS_M2)))
    if zero_area_count:
        failures.append(f"zero_area_triangles:{zero_area_count}")

    if not bool(mesh.is_watertight):
        failures.append("not_watertight")
    if not bool(mesh.is_winding_consistent):
        failures.append("inconsistent_winding")
    if not bool(mesh.is_volume):
        failures.append("not_positive_closed_volume")

    bounds = np.asarray(mesh.bounds)
    actual_height = float(bounds[1, 1] - bounds[0, 1])
    if not math.isclose(actual_height, expected_height_m, rel_tol=1.0e-7, abs_tol=1.0e-6):
        failures.append(f"height_mismatch:{actual_height:.9g}")

    triangles = np.asarray(mesh.triangles)
    normals = np.asarray(mesh.face_normals)
    y_min = float(bounds[0, 1])
    y_max = float(bounds[1, 1])
    atol = max(1.0e-6, expected_height_m * 1.0e-8)
    roof_mask = np.all(np.isclose(triangles[:, :, 1], y_max, atol=atol), axis=1)
    base_mask = np.all(np.isclose(triangles[:, :, 1], y_min, atol=atol), axis=1)
    roof_count = int(np.count_nonzero(roof_mask))
    base_count = int(np.count_nonzero(base_mask))
    if roof_count == 0:
        failures.append("missing_roof_cap")
    elif np.any(normals[roof_mask, 1] <= 0.999):
        failures.append("roof_normal_not_up")
    if base_count == 0:
        failures.append("missing_base_cap")
    elif np.any(normals[base_mask, 1] >= -0.999):
        failures.append("base_normal_not_down")

    return {
        "pass": not failures,
        "failures": failures,
        "vertices": int(len(vertices)),
        "triangles": int(len(faces)),
        "zero_area_triangles": zero_area_count,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "is_volume": bool(mesh.is_volume),
        "volume_m3": float(mesh.volume),
        "height_m": actual_height,
        "roof_triangles": roof_count,
        "base_triangles": base_count,
        "bounds_min": bounds[0].tolist(),
        "bounds_max": bounds[1].tolist(),
    }


def concavity_ratio(poly: Polygon) -> float:
    """1.0 means convex; lower values indicate increasingly concave footprints."""
    hull_area = float(poly.convex_hull.area)
    if hull_area <= AREA_EPS_M2:
        return 0.0
    return float(poly.area) / hull_area
