"""Hash-locked, source-mesh first-hit oracle for Xinyi packaged collision probes.

The presence of a witness triangle in a chosen tile does NOT prove that tile is
the first obstruction along a longer probe ray. Never use runtime hits to choose
the expected source-mesh first-hit identity.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _position_bounds(path: Path):
    data = path.read_bytes()
    if data[:4] != b"glTF" or struct.unpack_from("<I", data, 8)[0] != len(data):
        raise ValueError(f"Invalid GLB: {path}")
    n = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + n])
    if len(doc["meshes"]) != 1 or len(doc["meshes"][0]["primitives"]) != 1:
        raise ValueError(f"Unexpected runtime tile GLB topology: {path}")
    primitive = doc["meshes"][0]["primitives"][0]
    position = doc["accessors"][primitive["attributes"]["POSITION"]]
    if "min" not in position or "max" not in position:
        raise ValueError(f"GLB missing POSITION bounds: {path}")
    return position["min"], position["max"]


def tile_sources(contract: dict, base: Path) -> list[dict]:
    """Hash-check all 25 source runtime meshes before constructing expectations."""
    if len(contract["tiles"]) != 25:
        raise ValueError("Expected exactly 25 runtime building tiles")
    tiles = []
    for tile in contract["tiles"]:
        path = base / "building_runtime_tiles" / tile["runtime_building_glb"]
        digest = sha256(path)
        if digest != tile["runtime_building_sha256"]:
            raise ValueError(f"Runtime GLB hash drift: {tile['tile']}")
        lower, upper = _position_bounds(path)
        ox, oy, _ = tile["expected_ue_translation_cm"]
        tiles.append({
            "tile": tile["tile"], "path": path, "sha256": digest,
            "origin": (ox, oy),
            "lo": (ox + lower[0]*100, oy + lower[2]*100, lower[1]*100),
            "hi": (ox + upper[0]*100, oy + upper[2]*100, upper[1]*100),
        })
    if len({tile["tile"] for tile in tiles}) != 25:
        raise ValueError("Duplicate runtime tile identity")
    return tiles


def _overlaps_segment(start, end, low, high):
    """Slab cull using mesh POSITION bounds, including cross-tile geometry."""
    t0, t1 = 0.0, 1.0
    for axis in range(3):
        delta = end[axis] - start[axis]
        if abs(delta) < 1e-12:
            if start[axis] < low[axis] or start[axis] > high[axis]:
                return False
            continue
        lo = (low[axis] - start[axis]) / delta
        hi = (high[axis] - start[axis]) / delta
        t0, t1 = max(t0, min(lo, hi)), min(t1, max(lo, hi))
        if t0 > t1:
            return False
    return True


def _triangle_fraction(start, direction, a, b, c):
    """Double-sided Moller-Trumbore. Fraction of segment, not distance."""
    e1 = tuple(b[i]-a[i] for i in range(3))
    e2 = tuple(c[i]-a[i] for i in range(3))
    p = (direction[1]*e2[2]-direction[2]*e2[1],
         direction[2]*e2[0]-direction[0]*e2[2],
         direction[0]*e2[1]-direction[1]*e2[0])
    det = sum(e1[i]*p[i] for i in range(3))
    if abs(det) < 1e-12:
        return None
    inv = 1.0/det
    v0 = tuple(start[i]-a[i] for i in range(3))
    u = sum(v0[i]*p[i] for i in range(3))*inv
    if u < -1e-9 or u > 1+1e-9:
        return None
    q = (v0[1]*e1[2]-v0[2]*e1[1],
         v0[2]*e1[0]-v0[0]*e1[2],
         v0[0]*e1[1]-v0[1]*e1[0])
    v = sum(direction[i]*q[i] for i in range(3))*inv
    if v < -1e-9 or u+v > 1+1e-9:
        return None
    t = sum(e2[i]*q[i] for i in range(3))*inv
    return t if 0 <= t <= 1 else None


def first_hit(tiles: list[dict], start_cm, end_cm) -> dict:
    """Return closest source-triangle hit across every eligible runtime tile."""
    # Import on use, keeping glb_faces' accepted position/index decoding in one place.
    from prepare_collision_plan import glb_faces

    total_cm = math.dist(start_cm, end_cm)
    if total_cm < 1e-6:
        raise ValueError("Zero-length collision probe")
    hits = []
    for tile in tiles:
        if not _overlaps_segment(start_cm, end_cm, tile["lo"], tile["hi"]):
            continue
        ox, oy = tile["origin"]
        # UE coordinates (cm) -> source GLB (m): X=east, Y=up, Z=-north.
        start = ((start_cm[0]-ox)/100, start_cm[2]/100, (start_cm[1]-oy)/100)
        end = ((end_cm[0]-ox)/100, end_cm[2]/100, (end_cm[1]-oy)/100)
        direction = tuple(end[i]-start[i] for i in range(3))
        closest = None
        for index, (a, b, c) in enumerate(glb_faces(tile["path"])):
            fraction = _triangle_fraction(start, direction, a, b, c)
            if fraction is not None and (closest is None or fraction < closest[0]):
                closest = (fraction, index)
        if closest is not None:
            hits.append((closest[0], tile, closest[1]))
    if not hits:
        raise ValueError("Positive probe has no source-triangle intersection")
    hits.sort(key=lambda h: h[0])
    fraction, tile, triangle_index = hits[0]
    # Coincident different-tile hits have no stable owner for an identity gate.
    if len(hits) > 1 and hits[1][1]["tile"] != tile["tile"] and (hits[1][0]-fraction)*total_cm <= 0.1:
        raise ValueError("Ambiguous first-hit tile ownership within 0.1 cm")
    return {
        "method": "source-GLB-double-sided-first-hit/v1",
        "tile": tile["tile"], "triangle_index": triangle_index,
        "source_glb_sha256": tile["sha256"],
        "distance_cm": fraction*total_cm,
        "hit_cm": [start_cm[i]+(end_cm[i]-start_cm[i])*fraction for i in range(3)],
    }


def certify_positive_samples(steps: list[dict], tiles: list[dict]) -> int:
    """Populate expected owner from source geometry, never from UE observations."""
    count = 0
    for step in steps:
        for sample in step["building_samples"]:
            if not sample["expect_hit"]:
                continue
            source_witness_tile = sample["expected_tile"]
            hit = first_hit(tiles, sample["start_cm"], sample["end_cm"])
            sample["certificate"]["source_witness_tile"] = source_witness_tile
            sample["certificate"]["first_hit"] = hit
            sample["expected_tile"] = hit["tile"]
            count += 1
    return count


def verify_positive_samples(steps: list[dict], tiles: list[dict]) -> bool:
    """Fail closed on edited expectations, altered rays, missing or stale evidence."""
    count = 0
    for step in steps:
        for sample in step["building_samples"]:
            if not sample["expect_hit"]:
                continue
            cert = sample.get("certificate", {}).get("first_hit")
            if not isinstance(cert, dict):
                return False
            calculated = first_hit(tiles, sample["start_cm"], sample["end_cm"])
            if sample["expected_tile"] != calculated["tile"]:
                return False
            for field in ("method", "tile", "triangle_index", "source_glb_sha256"):
                if cert.get(field) != calculated[field]:
                    return False
            if abs(cert.get("distance_cm", math.inf) - calculated["distance_cm"]) > 0.01:
                return False
            if len(cert.get("hit_cm", [])) != 3 or any(
                abs(a-b) > 0.01 for a, b in zip(cert["hit_cm"], calculated["hit_cm"])
            ):
                return False
            count += 1
    return count == 15
