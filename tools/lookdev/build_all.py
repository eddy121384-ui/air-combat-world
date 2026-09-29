"""One-shot XinyiLook offline build (workstation or CI).

1. Restore the locked projected WFS source + accepted DTM mirror crop from
   data/lookdev_cache/ when the live fetch outputs are absent, verifying the
   accepted source SHA-256 (fails closed on drift).
2. Run the *unchanged* accepted pipeline where its outputs are missing:
   build_full_xinyi -> build_xinyi_terrain_dtm -> build_contract.
   Re-checks the accepted tile-manifest and terrain-manifest hashes.
3. Run the look-dev builders (tiles, Taipei 101, backdrop, ground).

Usage: python tools/lookdev/build_all.py [--force-look]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data/lookdev_cache"
SRC = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
SRC_MANIFEST = REPO / "data/generated/taipei/sample_buildings_epsg3826.manifest.json"
DTM = REPO / "data/generated/taipei/terrain/cache/moi_2025_dtm_xinyi_mirror.tif"
DTM_MANIFEST = REPO / "data/generated/taipei/terrain/moi_2025_dtm_mirror_source.json"
FULL = REPO / "unreal/Saved/XinyiV2Full/run-01/full_xinyi.report.json"
TERRAIN = REPO / "unreal/Saved/XinyiTerrainV0/terrain_dtm.report.json"
CONTRACT = REPO / "unreal/Saved/XinyiUnrealV2Contract/xinyi_unreal_v2_contract.json"
LOOK = REPO / "unreal/Saved/XinyiLook"

ACCEPTED_SOURCE = "c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d"
ACCEPTED_TILE_MANIFEST = "bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15"
ACCEPTED_TERRAIN_MANIFEST = "3f6b5f319fee237113864ceb67d30b59ff2914f8125e7a819d83eb8c70381176"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    print("+", " ".join(str(a) for a in args), flush=True)
    subprocess.run([sys.executable, *[str(a) for a in args]], cwd=REPO, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-look", action="store_true", help="rebuild look outputs even if present")
    args = ap.parse_args()

    if not SRC.exists():
        SRC.parent.mkdir(parents=True, exist_ok=True)
        SRC.write_bytes(gzip.decompress((CACHE / "sample_buildings_epsg3826.geojson.gz").read_bytes()))
        shutil.copy2(CACHE / "sample_buildings_epsg3826.manifest.json", SRC_MANIFEST)
    if sha(SRC) != ACCEPTED_SOURCE:
        raise SystemExit(f"projected source drifted from accepted SHA: {sha(SRC)}")
    if not DTM.exists():
        DTM.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CACHE / "moi_2025_dtm_xinyi_mirror.tif", DTM)
        shutil.copy2(CACHE / "moi_2025_dtm_mirror_source.json", DTM_MANIFEST)

    if not FULL.exists():
        run("tools/citygen_v2/build_full_xinyi.py")
    full = json.loads(FULL.read_text())
    got = full["tile_summary"]["manifest_sha256"]
    if got != ACCEPTED_TILE_MANIFEST:
        raise SystemExit(f"full-Xinyi tile manifest drifted: {got}")
    if not TERRAIN.exists():
        run("tools/terrain/build_xinyi_terrain_dtm.py")
    terr = json.loads(TERRAIN.read_text())
    if terr["output"]["manifest_sha256"] != ACCEPTED_TERRAIN_MANIFEST:
        raise SystemExit(f"terrain manifest drifted: {terr['output']['manifest_sha256']}")
    if not CONTRACT.exists():
        run("tools/unreal_xinyi_v2/build_contract.py")

    if args.force_look and (LOOK / "tiles").exists():
        shutil.rmtree(LOOK / "tiles")
    if args.force_look or not (LOOK / "look_tiles.report.json").exists():
        run("tools/lookdev/build_look_tiles.py")
    run("tools/lookdev/build_taipei101.py")
    run("tools/lookdev/build_backdrop.py")
    run("tools/lookdev/build_ground.py")
    print("XINYI_LOOK_OFFLINE_BUILD_OK")


if __name__ == "__main__":
    main()
