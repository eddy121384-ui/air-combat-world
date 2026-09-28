"""Offline façade metadata encoding for the XinyiV2 canary.

This module is deliberately downstream of accepted geometry. It decorates an
already-valid mesh with deterministic COLOR_0 vertex data only; it must not move
vertices, change faces, alter tile ownership, or replace authoritative GIS data.
"""
from __future__ import annotations

import hashlib
import math
from typing import Mapping

import numpy as np
import trimesh

PROFILE_GENERIC = 0
PROFILE_LOW_RISE = 1
PROFILE_MID_RISE = 2
PROFILE_HIGH_RISE = 3

FLOOR_HEIGHT_MIN_M = 2.4
FLOOR_HEIGHT_MAX_M = 6.0
FLOOR_HEIGHT_DEFAULT_M = 3.2


def _finite_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalized_floors(value):
    number = _finite_number(value)
    if number is None or number < 1 or number > 150:
        return None
    rounded = int(round(number))
    if not math.isclose(number, rounded, rel_tol=0.0, abs_tol=1.0e-6):
        return None
    return rounded


def appearance_seed(building_id: str) -> int:
    """Return a stable 8-bit appearance seed. This is variation, not identity."""
    payload = str(building_id).encode("utf-8")
    return hashlib.sha256(payload).digest()[0]


def facade_profile_id(building: Mapping) -> int:
    """Provisional debug profile for the canary, not production art direction."""
    height = _finite_number(building.get("height_m"))
    floors = normalized_floors(building.get("floors"))
    if height is None or height <= 0:
        return PROFILE_GENERIC
    if floors is not None:
        if floors <= 4:
            return PROFILE_LOW_RISE
        if floors <= 12:
            return PROFILE_MID_RISE
        return PROFILE_HIGH_RISE
    if height <= 15.0:
        return PROFILE_LOW_RISE
    if height <= 45.0:
        return PROFILE_MID_RISE
    return PROFILE_HIGH_RISE


def derive_floor_height_m(building: Mapping) -> tuple[float, str]:
    """Derive a bounded visual floor rhythm without changing building geometry."""
    height = _finite_number(building.get("height_m"))
    if height is None or height <= 0:
        return FLOOR_HEIGHT_DEFAULT_M, "default"

    floors = normalized_floors(building.get("floors"))
    if floors is not None:
        candidate = height / floors
        if FLOOR_HEIGHT_MIN_M <= candidate <= FLOOR_HEIGHT_MAX_M:
            return candidate, "surveyed_floors"

    estimated = max(1, int(round(height / FLOOR_HEIGHT_DEFAULT_M)))
    candidate = height / estimated
    candidate = min(FLOOR_HEIGHT_MAX_M, max(FLOOR_HEIGHT_MIN_M, candidate))
    return candidate, "estimated_floors"


def floor_phase(building: Mapping, floor_height_m: float) -> tuple[float, str]:
    ground = _finite_number(building.get("ground_elev_m"))
    if ground is None:
        return 0.0, "zero_default"
    return (ground / floor_height_m) % 1.0, "surveyed_ground"


def _encode_unit(value: float) -> int:
    return int(round(min(1.0, max(0.0, value)) * 255.0))


def _decode_unit(value: int) -> float:
    return int(value) / 255.0


def encode_floor_height(floor_height_m: float) -> int:
    t = (floor_height_m - FLOOR_HEIGHT_MIN_M) / (
        FLOOR_HEIGHT_MAX_M - FLOOR_HEIGHT_MIN_M
    )
    return _encode_unit(t)


def decode_floor_height(value: int) -> float:
    return FLOOR_HEIGHT_MIN_M + _decode_unit(value) * (
        FLOOR_HEIGHT_MAX_M - FLOOR_HEIGHT_MIN_M
    )


def encode_facade_rgba(building: Mapping) -> tuple[tuple[int, int, int, int], dict]:
    """Encode v1 COLOR_0 = profile / seed / floor-height / floor-phase."""
    floor_height_m, floor_height_source = derive_floor_height_m(building)
    phase, phase_source = floor_phase(building, floor_height_m)
    rgba = (
        facade_profile_id(building),
        appearance_seed(str(building.get("id", ""))),
        encode_floor_height(floor_height_m),
        _encode_unit(phase),
    )
    return rgba, {
        "profile_id": rgba[0],
        "appearance_seed": rgba[1],
        "floor_height_m": floor_height_m,
        "floor_height_source": floor_height_source,
        "floor_phase": phase,
        "floor_phase_source": phase_source,
        "encoded_rgba": list(rgba),
    }


def apply_facade_vertex_color(mesh: trimesh.Trimesh, rgba) -> trimesh.Trimesh:
    """Decorate one mesh in place while preserving geometry exactly."""
    color = np.asarray(tuple(rgba), dtype=np.uint8)
    if color.shape != (4,):
        raise ValueError("rgba must contain exactly four channels")
    before_vertices = np.asarray(mesh.vertices).copy()
    before_faces = np.asarray(mesh.faces).copy()
    before_bounds = np.asarray(mesh.bounds).copy()
    mesh.visual.vertex_colors = np.repeat(color[None, :], len(mesh.vertices), axis=0)
    np.testing.assert_array_equal(np.asarray(mesh.vertices), before_vertices)
    np.testing.assert_array_equal(np.asarray(mesh.faces), before_faces)
    np.testing.assert_array_equal(np.asarray(mesh.bounds), before_bounds)
    return mesh
