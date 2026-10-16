"""Fail-closed check that the fetched projected source is the frozen accepted baseline.

CI re-fetches the live Taipei WFS. When reproducing the accepted baseline, the bytes
must match the SHA-256 locked in representative_selection.json. A mismatch is reported
as source drift and is never auto-accepted: updating the lock needs a separate,
reviewed new-source-candidate task (re-run representative + full-Xinyi + Blender gates).

Usage: python tools/citygen_v2/source_lock.py [source.geojson]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOCK = HERE / "representative_selection.json"
DEFAULT_SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"


class SourceDriftError(RuntimeError):
    pass


def frozen_source_sha256() -> str:
    return json.loads(LOCK.read_text(encoding="utf-8"))["source_sha256"]


def verify_frozen_source(actual_sha256: str) -> None:
    expected = frozen_source_sha256()
    if actual_sha256 != expected:
        raise SourceDriftError(
            "SOURCE DRIFT: fetched projected WFS source does not match the frozen accepted baseline.\n"
            f"  expected sha256: {expected}\n"
            f"  actual   sha256: {actual_sha256}\n"
            "Refusing to continue. Do not update the lock to turn CI green; treat this as a "
            "new-source candidate and re-run the representative, full-Xinyi and Blender gates."
        )


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        verify_frozen_source(sha)
    except SourceDriftError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    print(f"source sha256 matches frozen baseline: {sha}")
