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


def file_meta(url: str, path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Expected workflow-downloaded source package: {path}")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return {
        "url": url,
        "local_path": str(path.relative_to(REPO)),
        "sha256": h.hexdigest(),
        "bytes": path.stat().st_size,
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
provider_file = CACHE / "source_provider.txt"

provider = provider_file.read_text(encoding="utf-8").strip() if provider_file.exists() else "unknown"
taipei_meta = file_meta(TAIPEI_URL, taipei_zip)
taipei_meta["provider_selected"] = provider

taipei = inspect_zip(taipei_zip)
if schema_zip.exists() and schema_zip.stat().st_size:
    schema_meta = file_meta(SCHEMA_URL, schema_zip)
    schema = inspect_zip(schema_zip)
else:
    schema_meta = None
    schema = {"entries": [], "entry_count": 0, "extension_counts": {}, "total_uncompressed_bytes": 0}

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
