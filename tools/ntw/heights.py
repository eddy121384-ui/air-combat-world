"""Height policy for NTW whitebox sources.

derive_wfs_height  - Python port of the vendored Buju `deriveBuildingHeight`
                     (tools/taipei/vendor/buju/taipei_building_height_semantics.mjs); same order + bounds.
derive_overture_height - Overture rows: explicit `height` -> floors x 3.2 -> 9.6 m, mirroring Buju's
                     render-time fallback (`height ? height : num_floors*3.2 : 9.6`) and the WFS constants.
Every result carries `source` so downstream QA never has to guess how a height was produced.
"""
from __future__ import annotations

import math

DEFAULT_M = 9.6
MIN_M, MAX_M = 1.2, 600.0
FLOOR_M = 3.2


def _num(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _plausible(v):
    return v is not None and MIN_M <= v <= MAX_M


def derive_wfs_height(p: dict):
    """-> (height_m, source, ground_elev_m|None). `p` has WFS keys 1_bud_high/1_top_high/1_ent_heig/1_floor."""
    top, ent = _num(p.get("1_top_high")), _num(p.get("1_ent_heig"))
    bud, floors = _num(p.get("1_bud_high")), _num(p.get("1_floor"))
    delta = top - ent if top is not None and ent is not None else None
    if _plausible(bud):
        return round(bud, 3), "1_bud_high", ent
    if _plausible(delta):
        return round(delta, 3), "top_minus_entrance", ent
    if floors is not None and 1 <= floors <= 150 and _plausible(floors * FLOOR_M):
        return round(floors * FLOOR_M, 3), "floors_x3.2", ent
    return DEFAULT_M, "fallback_9.6m", ent


def derive_overture_height(height, num_floors):
    h, f = _num(height), _num(num_floors)
    if _plausible(h):
        return round(h, 3), "overture_height"
    if f is not None and 1 <= f <= 150 and _plausible(f * FLOOR_M):
        return round(f * FLOOR_M, 3), "overture_floors_x3.2"
    return DEFAULT_M, "fallback_9.6m"
