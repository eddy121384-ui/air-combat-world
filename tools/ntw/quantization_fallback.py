"""Candidate production policy for footprints the accepted float32 quantisation cannot serialise (PR #23 review P0 #2).

Accepted path FIRST and unchanged: prepare_footprint(part, origin). Only if it fails:
  1. snap-round the tile-local part to a float32-exact grid (GEOS set_precision, grid 2**-13 m: exactly representable for
     |x| < 1024 m, i.e. any footprint within ~500 m of its 500 m owner tile) - valid output by construction;
  2. SOURCE-FIDELITY gates vs the ORIGINAL part (never relaxed accepted gates): every region removed or added by the
     snap is narrower than 2 x grid (it vanishes under an erosion by `grid`) - a WIDTH criterion, because zero-width
     digitising hairs (out-and-back spikes) can be metres long yet carry no area; |area delta| and symmetric difference
     <= perimeter x grid + pi grid^2; every original courtyard core (eroded by 2 grid) still empty (Hausdorff is reported), a non-largest repair fragment that snaps to nothing is ledgered with id + area (it carries < perimeter x grid
     area by construction);
  3. the UNCHANGED accepted prepare_footprint runs on the snapped part, then the unchanged mesher and strict mesh gates.
Default OFF everywhere. Regression evidence: it can only change parts that already FAIL the accepted path, so any accepted
build (e.g. full Xinyi, 0 failures) is byte-identical by construction - fragment_scan.py proves the trigger set.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/citygen_v2"))
from serialization_space import prepare_footprint  # noqa: E402

GRID_M = 2.0 ** -13


def fallback(part, origin, is_largest, grid=GRID_M):
    """-> (serial_parts, report). serial_parts == [] with report['ledgered'] for a collapsed non-largest fragment."""
    local = affinity.translate(part, xoff=-origin[0], yoff=-origin[1])
    snapped = shapely.set_precision(local, grid)
    rep = {"policy": "float32_grid_snap_fallback", "grid_m": grid, "source_area_m2": float(local.area)}
    if snapped.is_empty or snapped.area == 0:
        if not is_largest and local.area <= local.length * grid + math.pi * grid ** 2:
            rep.update(ledgered=True, reason="repair_fragment_below_quantum", pass_=True)
            return [], rep
        rep.update(pass_=False, failures=["snap_collapsed_a_non_fragment"])
        return [], rep
    budget = local.length * grid + math.pi * grid ** 2
    haus = float(shapely.hausdorff_distance(snapped, local))
    sym = float(snapped.symmetric_difference(local).area)
    da = float(snapped.area - local.area)
    core = [float(snapped.intersection(Polygon(h).buffer(-2 * grid)).area) for h in local.interiors]
    fails = []
    removed = local.difference(snapped)
    added = snapped.difference(local)
    wide_removed = float(removed.buffer(-grid).area) if not removed.is_empty else 0.0
    wide_added = float(added.buffer(-grid).area) if not added.is_empty else 0.0
    if wide_removed > 0 or wide_added > 0:
        fails.append("snap_changed_a_region_wider_than_2_grid")
    rep.update(wide_removed_m2=wide_removed, wide_added_m2=wide_added)
    if sym > budget or abs(da) > budget:
        fails.append("snap_area_exceeds_budget")
    if any(c > 1e-9 for c in core):
        fails.append("snap_filled_a_courtyard")
    rep.update(hausdorff_m=haus, symmetric_difference_m2=sym, area_delta_m2=da, budget_m2=budget,
               holes_before=len(local.interiors), holes_after=sum(len(p.interiors) for p in shapely.get_parts(snapped) if p.geom_type == "Polygon"))
    if fails:
        rep.update(pass_=False, failures=fails)
        return [], rep
    back = affinity.translate(snapped, xoff=origin[0], yoff=origin[1])
    parts, fg = prepare_footprint(back, origin)       # unchanged accepted gate on the snapped footprint
    rep["accepted_gate_on_snapped"] = {"pass": fg["pass"], "failures": fg.get("failures", [])}
    rep["pass_"] = bool(fg["pass"])
    if not fg["pass"]:
        rep["failures"] = ["accepted_gate_failed_after_snap"] + fg.get("failures", [])
    return parts if fg["pass"] else [], rep
