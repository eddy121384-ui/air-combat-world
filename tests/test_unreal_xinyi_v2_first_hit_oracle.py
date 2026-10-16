"""Regression: a selected witness triangle is not necessarily the first ray hit."""
import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "unreal_xinyi_v2"
sys.path.insert(0, str(TOOLS))

from first_hit_oracle import (  # noqa: E402
    certify_positive_samples,
    first_hit,
    tile_sources,
    verify_positive_samples,
)


def _triangle_glb(path, x_local):
    """Minimal single-mesh GLB using the same layout as packaged runtime tiles."""
    vertices = [(x_local, 0, -200), (x_local, 30, -200), (x_local, 0, -160)]
    positions = struct.pack("<9f", *(v for point in vertices for v in point))
    indices = struct.pack("<3I", 0, 1, 2)
    payload = positions + indices
    doc = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(payload)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(indices)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [x_local, 0, -200], "max": [x_local, 30, -160]},
            {"bufferView": 1, "componentType": 5125, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    encoded = json.dumps(doc, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    body = struct.pack("<I4s", len(encoded), b"JSON") + encoded
    body += struct.pack("<I4s", len(payload), b"BIN\x00") + payload
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)


def _scene(tmp_path):
    base = tmp_path
    meshdir = base / "building_runtime_tiles"
    meshdir.mkdir()
    contract = {"tiles": []}
    for i in range(25):
        # Tile 0 has real geometry at world X=492m. Tile 1 has a selected
        # witness wall at world X=498m. The ray travels from 480m to 520m.
        local_x = 492 if i == 0 else -2 if i == 1 else 250
        name = f"tile-{i:02d}.glb"
        path = meshdir / name
        _triangle_glb(path, local_x)
        contract["tiles"].append({
            "tile": "+000_+000" if i == 0 else "+001_+000" if i == 1 else f"+{i:03d}_+000",
            "runtime_building_glb": name,
            "runtime_building_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "expected_ue_translation_cm": [i * 50000, 0, 0],
        })
    return base, contract


def _steps():
    return [{
        "id": f"positive_toy_{i}",
        "building_samples": [{
            "id": f"toy_{i}", "expect_hit": True, "kind": "mass",
            "expected_tile": "+001_+000",
            "start_cm": [48000, -18000, 1000],
            "end_cm": [52000, -18000, 1000],
            "certificate": {"source_glb_sha256": "witness-only"},
        }],
    } for i in range(15)]


def test_witness_tile_is_not_necessarily_first_hit(tmp_path):
    base, contract = _scene(tmp_path)
    tiles = tile_sources(contract, base)
    hit = first_hit(tiles, [48000, -18000, 1000], [52000, -18000, 1000])
    assert hit["tile"] == "+000_+000"
    assert hit["triangle_index"] == 0
    assert hit["distance_cm"] == pytest.approx(1200)
    assert hit["hit_cm"] == pytest.approx([49200, -18000, 1000])
    steps = _steps()
    assert certify_positive_samples(steps, tiles) == 15
    assert {s["building_samples"][0]["expected_tile"] for s in steps} == {"+000_+000"}
    assert {s["building_samples"][0]["certificate"]["source_witness_tile"]
            for s in steps} == {"+001_+000"}
    assert verify_positive_samples(steps, tiles)


def test_editing_expected_tile_or_distance_cannot_promote_pass(tmp_path):
    base, contract = _scene(tmp_path)
    tiles = tile_sources(contract, base)
    steps = _steps()
    certify_positive_samples(steps, tiles)
    tampered = copy.deepcopy(steps)
    tampered[0]["building_samples"][0]["expected_tile"] = "+001_+000"
    assert not verify_positive_samples(tampered, tiles)
    tampered = copy.deepcopy(steps)
    tampered[0]["building_samples"][0]["certificate"]["first_hit"]["distance_cm"] += 1
    assert not verify_positive_samples(tampered, tiles)
    tampered = copy.deepcopy(steps)
    del tampered[0]["building_samples"][0]["certificate"]["first_hit"]
    assert not verify_positive_samples(tampered, tiles)


def test_hash_drift_and_missing_positive_hit_fail_closed(tmp_path):
    base, contract = _scene(tmp_path)
    contract["tiles"][1]["runtime_building_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash drift"):
        tile_sources(contract, base)
    contract["tiles"][1]["runtime_building_sha256"] = hashlib.sha256(
        (base / "building_runtime_tiles/tile-01.glb").read_bytes()
    ).hexdigest()
    tiles = tile_sources(contract, base)
    with pytest.raises(ValueError, match="no source-triangle"):
        first_hit(tiles, [48000, -18000, 9000], [52000, -18000, 9000])


def test_cross_tile_tie_is_ambiguous_not_arbitrarily_assigned(tmp_path):
    base, contract = _scene(tmp_path)
    path = base / "building_runtime_tiles/tile-01.glb"
    _triangle_glb(path, -8)  # second tile also intersects at world X=492m
    contract["tiles"][1]["runtime_building_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    tiles = tile_sources(contract, base)
    with pytest.raises(ValueError, match="Ambiguous first-hit"):
        first_hit(tiles, [48000, -18000, 1000], [52000, -18000, 1000])
