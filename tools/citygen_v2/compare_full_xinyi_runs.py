"""Compare two full-Xinyi runs for deterministic geometry output."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("first", type=Path)
    p.add_argument("second", type=Path)
    args = p.parse_args()
    a, b = load(args.first), load(args.second)

    checks = {
        "both_pass": a["gate_result"]["pass"] and b["gate_result"]["pass"],
        "source_hash": a["source"]["sha256"] == b["source"]["sha256"],
        "accounting": a["accounting"] == b["accounting"],
        "tile_manifest": a["tile_summary"]["manifest_sha256"] == b["tile_summary"]["manifest_sha256"],
        "tile_hashes": [(x["tile"], x["sha256"]) for x in a["tiles"]]
            == [(x["tile"], x["sha256"]) for x in b["tiles"]],
        "triangle_counts": a["tile_summary"]["total_triangles"] == b["tile_summary"]["total_triangles"],
        "byte_counts": a["tile_summary"]["total_glb_bytes"] == b["tile_summary"]["total_glb_bytes"],
    }
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
