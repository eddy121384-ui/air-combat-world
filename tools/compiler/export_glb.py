"""Minimal GLB 2.0 writer (stdlib only: json + struct).

One buffer, float32 POSITION/NORMAL/TEXCOORD_0 + uint32 indices, N meshes each
with one primitive, one white/grey material (baseColorFactor only — v0 massing).
UVs are planar (x,z normalized per mesh): strict importers (UE MeshDescription)
require at least one UV set; values carry no texture meaning in v0.
"""
from __future__ import annotations

import json
import struct


def write_glb(path, meshes: list[dict], material_color=(0.82, 0.83, 0.85, 1.0)) -> None:
    """meshes: [{name, positions:[f], normals:[f], indices:[i]}] -> .glb file."""
    blob = bytearray()
    buffer_views = []
    accessors = []
    gl_meshes = []

    def push(data: bytes) -> int:
        off = len(blob)
        blob.extend(data)
        while len(blob) % 4:
            blob.append(0)
        return off

    for m in meshes:
        pos_b = struct.pack(f"<{len(m['positions'])}f", *m["positions"])
        nrm_b = struct.pack(f"<{len(m['normals'])}f", *m["normals"])
        idx_b = struct.pack(f"<{len(m['indices'])}I", *m["indices"])
        xs = m["positions"][0::3]
        ys = m["positions"][1::3]
        zs = m["positions"][2::3]
        # planar UVs from x/z, normalized per mesh (finite even for flat meshes)
        minx, maxx = min(xs), max(xs)
        minz, maxz = min(zs), max(zs)
        sx = (maxx - minx) or 1.0
        sz = (maxz - minz) or 1.0
        # interleave u,v
        uvs = [v for pair in zip([(x - minx) / sx for x in xs],
                                 [(z - minz) / sz for z in zs]) for v in pair]
        uv_b = struct.pack(f"<{len(uvs)}f", *uvs)
        p_off, n_off = push(pos_b), push(nrm_b)
        uv_off, i_off = push(uv_b), push(idx_b)

        p_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": p_off, "byteLength": len(pos_b)})
        n_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": n_off, "byteLength": len(nrm_b)})
        uv_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": uv_off, "byteLength": len(uv_b)})
        i_vi = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": i_off, "byteLength": len(idx_b)})
        p_ai = len(accessors)
        accessors.append({"bufferView": p_vi, "componentType": 5126, "count": len(xs),
                          "type": "VEC3", "min": [min(xs), min(ys), min(zs)],
                          "max": [max(xs), max(ys), max(zs)]})
        n_ai = len(accessors)
        accessors.append({"bufferView": n_vi, "componentType": 5126,
                          "count": len(xs), "type": "VEC3"})
        uv_ai = len(accessors)
        accessors.append({"bufferView": uv_vi, "componentType": 5126,
                          "count": len(xs), "type": "VEC2"})
        i_ai = len(accessors)
        accessors.append({"bufferView": i_vi, "componentType": 5125,
                          "count": len(m["indices"]), "type": "SCALAR"})
        gl_meshes.append({"name": m["name"], "primitives": [{
            "attributes": {"POSITION": p_ai, "NORMAL": n_ai, "TEXCOORD_0": uv_ai},
            "indices": i_ai, "material": 0}]})

    doc = {
        "asset": {"version": "2.0", "generator": "air-combat-world greybox-core v0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(gl_meshes)))}],
        "nodes": [{"mesh": i, "name": m["name"]} for i, m in enumerate(meshes)],
        "meshes": gl_meshes,
        "materials": [{"name": "massing_grey",
                       "pbrMetallicRoughness": {"baseColorFactor": list(material_color),
                                                "metallicFactor": 0.0, "roughnessFactor": 0.9}}],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    j = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    while len(j) % 4:
        j += b" "
    total = 12 + 8 + len(j) + 8 + len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))  # glTF
        f.write(struct.pack("<II", len(j), 0x4E4F534A))      # JSON
        f.write(j)
        f.write(struct.pack("<II", len(blob), 0x004E4942))   # BIN
        f.write(blob)


def read_glb_info(path) -> dict:
    """Parse back a GLB (used by tests): magic, version, mesh/prim counts, bounds."""
    import struct as _s
    data = open(path, "rb").read()
    magic, ver, _len = _s.unpack_from("<III", data, 0)
    assert magic == 0x46546C67 and ver == 2, "not a GLB 2.0 file"
    jl, jt = _s.unpack_from("<II", data, 12)
    assert jt == 0x4E4F534A
    doc = json.loads(data[20:20 + jl])
    info: dict = {"meshes": len(doc.get("meshes", [])),
            "primitives": sum(len(m.get("primitives", [])) for m in doc.get("meshes", [])),
            "nodes": len(doc.get("nodes", []))}
    acc = doc.get("accessors", [])
    pos_acc = [a for m in doc.get("meshes", []) for p in m.get("primitives", [])
               for a in [acc[p["attributes"]["POSITION"]]]]
    if pos_acc:
        info["bounds"] = [(a["min"], a["max"]) for a in pos_acc]
    return info
