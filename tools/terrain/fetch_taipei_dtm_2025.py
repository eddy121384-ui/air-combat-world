"""Download and inspect the official 2025 Taipei City 20 m DTM package.

This is source discovery only. It records byte hashes, ZIP contents and text
samples without generating terrain geometry.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data/generated/taipei/terrain"
CACHE = OUT / "cache"
REPORT = OUT / "taipei_dtm_2025_package_audit.json"

TAIPEI_URL = (
    "https://www.tgos.tw:443/MDE/VirtualDir_TC/Product/"
    "60e634ea-7c59-47a4-a967-ac33694e0d05/"
    "%E5%88%86%E5%B9%85_%E8%87%BA%E5%8C%97%E5%B8%8220MDEM%282025%29.zip"
)
SCHEMA_URL = (
    "https://www.tgos.tw:443/MDE/VirtualDir_TC/Product/"
    "342505d1-81bc-490a-8e10-9f7e1ec0ed98/schema_hdr.zip"
)


def download(url: str, path: Path) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "air-combat-world/xinyi-terrain-v0"},
    )
    h = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(req, timeout=90) as r, path.open("wb") as f:
        while True:
            block = r.read(1024 * 1024)
            if not block:
                break
            h.update(block)
            size += len(block)
            f.write(block)
        ctype = r.headers.get("content-type")
        final_url = r.geturl()
    return {
        "url": url,
        "final_url": final_url,
        "sha256": h.hexdigest(),
        "bytes": size,
        "content_type": ctype,
    }


def decode_sample(data: bytes) -> str | None:
    for enc in ("utf-8-sig", "cp950", "big5", "latin1"):
        try:
            text = data.decode(enc)
            # Reject obviously binary chunks.
            printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
            if text and printable / len(text) > 0.90:
                return text
        except UnicodeDecodeError:
            pass
    return None


def inspect_zip(path: Path) -> dict:
    rows = []
    ext_counts = Counter()
    total_uncompressed = 0
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower() or "<none>"
            ext_counts[ext] += 1
            total_uncompressed += info.file_size
            sample_bytes = b""
            if info.file_size:
                with zf.open(info) as fh:
                    sample_bytes = fh.read(min(info.file_size, 4096))
            sample = decode_sample(sample_bytes)
            rows.append({
                "name": info.filename,
                "extension": ext,
                "compressed_bytes": info.compress_size,
                "uncompressed_bytes": info.file_size,
                "sample": sample[:1200] if sample else None,
            })
    return {
        "entries": rows,
        "entry_count": len(rows),
        "extension_counts": dict(ext_counts),
        "total_uncompressed_bytes": total_uncompressed,
    }


CACHE.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

taipei_zip = CACHE / "taipei_20m_dtm_2025.zip"
schema_zip = CACHE / "schema_hdr.zip"

taipei_meta = download(TAIPEI_URL, taipei_zip)
schema_meta = download(SCHEMA_URL, schema_zip)

taipei = inspect_zip(taipei_zip)
schema = inspect_zip(schema_zip)

# Surface likely DEM and header files first in the log.
interesting = [
    e for e in taipei["entries"]
    if e["extension"] in {".dem", ".grd", ".asc", ".txt", ".csv", ".hdr", ".xyz"}
    or re.search(r"hdr|dem|dtm|20m", e["name"], re.I)
]

report = {
    "gate": "Official Taipei 2025 20m DTM package audit",
    "status": "PACKAGE_DOWNLOADED_FORMAT_NOT_YET_LOCKED",
    "taipei_package": taipei_meta,
    "schema_package": schema_meta,
    "taipei_zip": {
        "entry_count": taipei["entry_count"],
        "extension_counts": taipei["extension_counts"],
        "total_uncompressed_bytes": taipei["total_uncompressed_bytes"],
        "entries": taipei["entries"],
    },
    "schema_zip": schema,
    "interesting_entries": interesting,
    "next_gate": (
        "Parse official header/schema, derive each sheet extent/CRS/vertical units, "
        "select sheets intersecting Xinyi EPSG:3826 bbox, then lock source hashes."
    ),
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(json.dumps({
    "report": str(REPORT.relative_to(REPO)),
    "taipei_package": taipei_meta,
    "schema_package": schema_meta,
    "taipei_entry_count": taipei["entry_count"],
    "taipei_extension_counts": taipei["extension_counts"],
    "schema_entries": schema["entries"],
    "interesting_preview": interesting[:25],
}, ensure_ascii=False, indent=2))
