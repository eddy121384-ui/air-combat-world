"""Minimal deterministic glTF 2.0 (GLB) writer for XinyiLook assets.

trimesh cannot emit TEXCOORD_0 + TEXCOORD_1 + COLOR_0 together, and the look
layer needs all three. This writer is numpy-only, emits no timestamps, and
produces byte-identical output for identical input arrays.

Each primitive dict:
  name        str (material name; becomes the Unreal material slot)
  positions   float32 (N, 3)
  indices     uint32 (M, 3)
  normals     float32 (N, 3)            optional
  uv0         float32 (N, 2)            optional
  uv1         float32 (N, 2)            optional
  uv2         float32 (N, 2)            optional (packed RGBA8 data, see pack_rgba8)
  color0      uint8   (N, 4)            optional (normalized UNSIGNED_BYTE)
  base_color  [r, g, b, a]              material factor
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

FLOAT, UBYTE, UINT = 5126, 5121, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963


class _Buf:
    def __init__(self):
        self.chunks: list[bytes] = []
        self.size = 0
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def add(self, arr: np.ndarray, comp: int, typ: str, target: int, normalized=False, minmax=False):
        data = np.ascontiguousarray(arr).tobytes()
        pad = (-self.size) % 4
        if pad:
            self.chunks.append(b"\x00" * pad)
            self.size += pad
        self.views.append({"buffer": 0, "byteOffset": self.size, "byteLength": len(data), "target": target})
        self.chunks.append(data)
        self.size += len(data)
        acc = {
            "bufferView": len(self.views) - 1,
            "componentType": comp,
            "count": int(arr.shape[0]),
            "type": typ,
        }
        if normalized:
            acc["normalized"] = True
        if minmax:
            acc["min"] = [float(v) for v in arr.min(axis=0)]
            acc["max"] = [float(v) for v in arr.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def pack_rgba8(rgba) -> np.ndarray:
    """Pack uint8 RGBA rows into TEXCOORD-safe floats: (R*256+G, B*256+A).

    Values <= 65535 are exact in float32. XinyiLook uses TEXCOORD_2 for
    per-vertex data so the Unreal material never depends on the importer's
    vertex-colour policy. Decode in the shader with xc_unpack().

    Interpolation rule: the rasteriser interpolates the packed float, so only
    pack data whose high bytes (R, B) are constant across every triangle
    (per-building / per-part data). Smoothly varying data (terrain weights,
    tree height) must be written as plain 0..1 floats instead.
    """
    c = np.asarray(rgba, dtype=np.uint32)
    return np.column_stack([c[:, 0] * 256 + c[:, 1], c[:, 2] * 256 + c[:, 3]]).astype(np.float32)


def ue_local_bounds_cm(positions_game) -> dict:
    """Expected Unreal-local bounds of a game-frame mesh (game X,Y,Z -> UE X,Z,Y, cm).

    Unreal adapters compare these with the imported StaticMesh bounds and
    correct placement by the difference, instead of assuming how the importer
    treated the source pivot (same rule as the accepted runtime tiles).
    """
    p = np.asarray(positions_game, dtype=np.float64)
    ue = np.column_stack([p[:, 0], p[:, 2], p[:, 1]]) * 100.0
    lo, hi = ue.min(axis=0), ue.max(axis=0)
    return {"origin_cm": ((lo + hi) * 0.5).tolist(), "extent_cm": ((hi - lo) * 0.5).tolist()}


def write_glb(path: Path, primitives: list[dict], mesh_name: str = "mesh") -> None:
    buf = _Buf()
    materials, prims = [], []
    for p in primitives:
        pos = np.asarray(p["positions"], dtype=np.float32)
        idx = np.asarray(p["indices"], dtype=np.uint32).reshape(-1)
        attrs = {"POSITION": buf.add(pos, FLOAT, "VEC3", ARRAY_BUFFER, minmax=True)}
        if p.get("normals") is not None:
            attrs["NORMAL"] = buf.add(np.asarray(p["normals"], np.float32), FLOAT, "VEC3", ARRAY_BUFFER)
        if p.get("uv0") is not None:
            attrs["TEXCOORD_0"] = buf.add(np.asarray(p["uv0"], np.float32), FLOAT, "VEC2", ARRAY_BUFFER)
        if p.get("uv1") is not None:
            attrs["TEXCOORD_1"] = buf.add(np.asarray(p["uv1"], np.float32), FLOAT, "VEC2", ARRAY_BUFFER)
        if p.get("uv2") is not None:
            attrs["TEXCOORD_2"] = buf.add(np.asarray(p["uv2"], np.float32), FLOAT, "VEC2", ARRAY_BUFFER)
        if p.get("color0") is not None:
            attrs["COLOR_0"] = buf.add(np.asarray(p["color0"], np.uint8), UBYTE, "VEC4", ARRAY_BUFFER, normalized=True)
        ind = buf.add(idx.reshape(-1, 1), UINT, "SCALAR", ELEMENT_ARRAY_BUFFER)
        materials.append({
            "name": p["name"],
            "pbrMetallicRoughness": {
                "baseColorFactor": [float(c) for c in p.get("base_color", [0.8, 0.8, 0.8, 1.0])],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.8,
            },
        })
        prims.append({"attributes": attrs, "indices": ind, "material": len(materials) - 1, "mode": 4})

    gltf = {
        "asset": {"version": "2.0", "generator": "air-combat-world/xinyi-lookdev"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": mesh_name, "mesh": 0}],
        "meshes": [{"name": mesh_name, "primitives": prims}],
        "materials": materials,
        "buffers": [{"byteLength": buf.size}],
        "bufferViews": buf.views,
        "accessors": buf.accessors,
    }
    js = json.dumps(gltf, separators=(",", ":"), sort_keys=True).encode()
    js += b" " * ((-len(js)) % 4)
    bin_ = b"".join(buf.chunks)
    bin_ += b"\x00" * ((-len(bin_)) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    out = struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(bin_), 0x004E4942) + bin_
    Path(path).write_bytes(out)


def read_glb_primitives(path: Path) -> list[dict]:
    """Read back POSITION/indices/attributes for round-trip verification."""
    b = Path(path).read_bytes()
    jl = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20:20 + jl])
    bin_off = 20 + jl + 8
    dt = {FLOAT: np.float32, UBYTE: np.uint8, UINT: np.uint32, 5123: np.uint16}
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = g["accessors"][i]
        v = g["bufferViews"][a["bufferView"]]
        start = bin_off + v.get("byteOffset", 0) + a.get("byteOffset", 0)
        n = a["count"] * ncomp[a["type"]]
        arr = np.frombuffer(b, dtype=dt[a["componentType"]], count=n, offset=start)
        return arr.reshape(a["count"], ncomp[a["type"]]) if ncomp[a["type"]] > 1 else arr

    out = []
    for mesh in g["meshes"]:
        for p in mesh["primitives"]:
            rec = {k.lower(): acc(v) for k, v in p["attributes"].items()}
            rec["indices"] = acc(p["indices"]).reshape(-1, 3) if "indices" in p else None
            rec["material"] = g["materials"][p["material"]]["name"] if "material" in p and g.get("materials") else None
            out.append(rec)
    return out
