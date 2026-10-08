"""No-visual-change gate for the facade generation payload.

Compares look tiles built with the payload (--payload DIR) against tiles built without it (--baseline DIR):
every attribute except TEXCOORD_2.x must be bit-identical, TEXCOORD_2.x with the payload stripped must equal
the baseline; payload statistics are reported.

Usage: python tools/lookdev/verify_facade_payload.py --payload OUT_A --baseline OUT_B
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import facade_generation as fg  # noqa: E402
from gltf_writer import read_glb_primitives  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, required=True)
    a = ap.parse_args()
    seen, nz_verts, total = Counter(), 0, 0
    for tp in sorted((a.payload / "tiles").glob("*.glb")):
        P = read_glb_primitives(tp)[0]
        B = read_glb_primitives(a.baseline / "tiles" / tp.name)[0]
        assert P.keys() == B.keys(), (tp.name, P.keys(), B.keys())
        for k in P:
            if k in ("texcoord_2", "material"):
                continue
            assert np.array_equal(np.asarray(P[k]).view(np.uint8), np.asarray(B[k]).view(np.uint8)), (tp.name, k)
        assert P["material"] == B["material"]
        px, py = P["texcoord_2"][:, 0], P["texcoord_2"][:, 1]
        assert np.array_equal(py.view(np.uint32), B["texcoord_2"][:, 1].view(np.uint32)), tp.name
        code = np.floor((px.astype(np.float64) + 0.5) / fg.PAYLOAD_UNIT).astype(np.int64)
        base = px.astype(np.int64) - code * fg.PAYLOAD_UNIT
        assert np.array_equal(base.astype(np.float32).view(np.uint32), B["texcoord_2"][:, 0].view(np.uint32)), tp.name
        assert code.max() <= fg.GEN_PREMIUM and base.max() <= fg.BASE_MAX
        for c in np.unique(code):
            seen[fg.GEN_NAMES[c]] += int((code == c).sum())
        nz_verts += int((code > 0).sum())
        total += len(code)
    print(json.dumps({"verdict": "PASS_NO_VISUAL_CHANGE", "tiles": len(list((a.payload / "tiles").glob("*.glb"))),
                      "vertices": total, "vertices_with_payload": nz_verts, "vertices_by_generation": dict(seen)}, indent=1))


if __name__ == "__main__":
    main()
