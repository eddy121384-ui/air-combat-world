"""Shared, engine-independent contracts for XinyiV2 workstation gates."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "xinyi-host-gate/v1"
RUN_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def new_run_id(repo: Path, now: datetime | None = None) -> str:
    instant = now or datetime.now(UTC)
    return f"{instant:%Y%m%dT%H%M%SZ}-{git(repo, 'rev-parse', '--short=8', 'HEAD')}"


def machine() -> dict[str, Any]:
    return {"hostname": socket.gethostname(), "platform": platform.platform(), "python": platform.python_version()}


def file_rows(root: Path, paths: Iterable[Path], category: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted({p.resolve() for p in paths}, key=lambda p: str(p).lower()):
        if not path.is_file():
            continue
        try:
            display = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            display = str(path)
        rows.append({"category": category, "path": display, "size_bytes": path.stat().st_size, "sha256": sha256(path)})
    return rows


def write_json_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
