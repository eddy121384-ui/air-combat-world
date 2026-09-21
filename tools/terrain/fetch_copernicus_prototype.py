"""Fetch the public Copernicus GLO-30 tile covering Xinyi for terrain prototyping.

IMPORTANT: Copernicus GLO-30 is a DSM (buildings/vegetation included), not the
production bare-earth DTM target. This adapter exists only so the coordinate,
tiling, elevation-anchor and Blender preview pipeline can be exercised in cloud
CI while the official MOI/TGOS DTM is blocked from GitHub-hosted runners.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data/generated/taipei/terrain"
CACHE = OUT / "cache"
MANIFEST = OUT / "copernicus_glo30_prototype_source.json"

BUCKET = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
PREFIX = "Copernicus_DSM_COG_10_N25_00_E121_00_DEM/"
REGISTRY = "https://registry.opendata.aws/copernicus-dem/"


def fetch_bytes(url: str) -> tuple[bytes, str | None]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "air-combat-world/xinyi-terrain-v0"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read(), r.headers.get("content-type")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

list_url = BUCKET + "/?" + urllib.parse.urlencode({
    "list-type": "2",
    "prefix": PREFIX,
})
xml, list_ctype = fetch_bytes(list_url)
root = ET.fromstring(xml)
keys = []
for elem in root.iter():
    if elem.tag.endswith("Key") and elem.text:
        keys.append(elem.text)

dem_keys = [k for k in keys if k.endswith("_DEM.tif")]
if len(dem_keys) != 1:
    raise RuntimeError(f"Expected exactly one DEM COG under {PREFIX}, found {dem_keys}")

key = dem_keys[0]
url = BUCKET + "/" + urllib.parse.quote(key, safe="/")
target = CACHE / "copernicus_glo30_xinyi_prototype.tif"

req = urllib.request.Request(url, headers={"User-Agent": "air-combat-world/xinyi-terrain-v0"})
with urllib.request.urlopen(req, timeout=180) as r, target.open("wb") as out:
    while True:
        block = r.read(1024 * 1024)
        if not block:
            break
        out.write(block)
    content_type = r.headers.get("content-type")

manifest = {
    "role": "PROTOTYPE_DSM_NOT_PRODUCTION_TERRAIN",
    "provider": "Copernicus DEM GLO-30 Public on AWS Open Data",
    "registry": REGISTRY,
    "bucket": "s3://copernicus-dem-30m",
    "key": key,
    "download_url": url,
    "source_semantics": (
        "Digital Surface Model (DSM): includes buildings, infrastructure and vegetation. "
        "Used only to exercise Xinyi terrain pipeline while official MOI 20m DTM cloud download is blocked."
    ),
    "resolution_class": "GLO-30 (~30 m)",
    "source_release": "Copernicus DEM 2021 release",
    "catalog_content_type": list_ctype,
    "download_content_type": content_type,
    "bytes": target.stat().st_size,
    "sha256": sha256_file(target),
    "local_path": str(target.relative_to(REPO)),
    "production_replacement_rule": (
        "Replace this source adapter with locked official MOI/TGOS bare-earth DTM; "
        "do not change the ENU/500m tile/building-Z contracts merely because the source changes."
    ),
}
MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

print(json.dumps({
    "key": key,
    "bytes": manifest["bytes"],
    "sha256": manifest["sha256"],
    "local_path": manifest["local_path"],
    "role": manifest["role"],
}, indent=2))
