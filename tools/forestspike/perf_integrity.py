"""Fail-closed UE5.8 CSV and engine-completion validation. Standard library only.

Legacy semicolon metadata is decoded explicitly for historical audits. New runs
must use separate tag/level/run_id fields and cannot pass via legacy decoding.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path

REQUIRED = ("FrameTime", "GameThreadTime", "RenderThreadTime", "RHIThreadTime", "GPUTime")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    csv.field_size_limit(16 * 1024 * 1024)  # UE boot EVENTS can exceed 400KB.
    lines = Path(path).read_text(encoding="utf-8-sig", errors="strict").splitlines()
    headers = [i for i, line in enumerate(lines) if line.startswith("EVENTS,")]
    if not headers:
        raise ValueError("CSV header missing")
    end = headers[-1]
    header = next(csv.reader([lines[end]]))
    for key in REQUIRED:
        if header.count(key) != 1:
            raise ValueError("Required column missing or duplicated: " + key)
    rows = [next(csv.reader([line])) for line in lines[:end] if line and not line.startswith("EVENTS,")]
    if not rows:
        raise ValueError("CSV contains no frames")
    cols = {}
    omitted_optional = {}
    for key in dict.fromkeys(header[1:]):
        if header.count(key) != 1:
            continue  # UE also emits duplicate optional stat names.
        index = header.index(key)
        values = []
        for n, row in enumerate(rows):
            if len(row) > len(header):
                raise ValueError("Row %d wider than header" % n)
            if index >= len(row) and key not in REQUIRED:
                # UE can add an optional stat to the final header after earlier
                # frames were written. Keep row alignment and disclose absence.
                values.append(None)
                omitted_optional[key] = omitted_optional.get(key, 0) + 1
                continue
            try:
                value = float(row[index])
            except (ValueError, IndexError):
                raise ValueError("Invalid numeric value at frame %d column %s" % (n, key)) from None
            if not math.isfinite(value) or (key in REQUIRED and value < 0):
                raise ValueError("Nonfinite/negative value at frame %d column %s" % (n, key))
            values.append(value)
        cols[key] = values
    meta = {}
    for line in lines[end + 1:]:
        # UE writes commandline last, with unescaped internal quotes/commas.
        # Parse the preceding key/value pairs normally and retain that tail.
        prefix, marker, commandline = line.partition(",[commandline],")
        parts = next(csv.reader([prefix if marker else line]))
        for i, part in enumerate(parts[:-1]):
            if re.fullmatch(r"\[[A-Za-z0-9_.]+\]", part):
                key = part[1:-1]
                if key in meta:
                    raise ValueError("Duplicate metadata: " + key)
                meta[key] = parts[i + 1]
        if marker:
            if "commandline" in meta:
                raise ValueError("Duplicate metadata: commandline")
            meta["commandline"] = commandline[1:-1] if commandline.startswith('"') and commandline.endswith('"') else commandline
    raw_meta = dict(meta)
    legacy = False
    if ";" in meta.get("tag", ""):
        tag, *fields = meta["tag"].split(";")
        meta["tag"] = tag
        for field in fields:
            if "=" not in field:
                raise ValueError("Malformed legacy metadata")
            key, value = field.split("=", 1)
            if key not in ("level", "run_id") or key in meta:
                raise ValueError("Ambiguous legacy metadata: " + key)
            meta[key] = value
        legacy = True
    return {"columns": cols, "metadata": meta, "raw_metadata": raw_meta,
            "legacy_metadata": legacy, "frames": len(rows), "events": [r[0] for r in rows],
            "omitted_optional": omitted_optional}


def validate_run(csv_path, log_path, *, tag, level, run_id, frames, cold, started_epoch, exit_code, world_path=None):
    errors = []
    result = {"schema": "forestspike.perf_completion/1", "status": "FAIL_FS_PERF", "tag": tag,
              "level": level, "run_id": run_id, "expected_frames": frames, "cold_frames": cold,
              "started_epoch": started_epoch, "exit_code": exit_code, "host_scope": "Intel UHD 770 only",
              "csv": str(csv_path), "log": str(log_path), "errors": errors}
    try:
        if exit_code is None:
            errors.append("process exit was not observed")
        for path in (Path(csv_path), Path(log_path)):
            if path.stat().st_mtime < started_epoch:
                errors.append("stale file: " + str(path))
        result["csv_sha256"], result["log_sha256"] = sha256(csv_path), sha256(log_path)
        data = read_csv(csv_path)
        meta, cols = data["metadata"], data["columns"]
        result["metadata"] = meta
        result["actual_frames"] = data["frames"]
        if data["legacy_metadata"]:
            errors.append("new capture used legacy mixed metadata")
        for key, expected in (("tag", tag), ("level", level), ("run_id", run_id),
                              ("targetframerate", "60"), ("vsyncenabled", "0"),
                              ("systemresolution.resx", "1920"), ("systemresolution.resy", "1080")):
            if meta.get(key) != expected:
                errors.append("metadata %s: %r != %r" % (key, meta.get(key), expected))
        if "UHD" not in meta.get("gpu", "") or "770" not in meta.get("gpu", ""):
            errors.append("unexpected GPU for UHD770-only preflight")
        if data["frames"] != frames:
            errors.append("frame count mismatch")
        if not 0 <= cold < frames:
            errors.append("invalid cold/warm window")
        else:
            for key in REQUIRED:
                if any(value <= 0 for value in cols[key][cold:]):
                    errors.append("nonpositive warm timing: " + key)
        log = Path(log_path).read_text(encoding="utf-8-sig", errors="replace")
        completed = re.findall(r"Capture Ended\. Writing CSV to file : (.+)", log)
        result["engine_csv_outputs"] = completed
        if len(completed) != 1 or Path(completed[0].strip()).name != Path(csv_path).name:
            # Copied outputs retain the original engine filename in a per-run directory.
            errors.append("engine output path missing/ambiguous/mismatched")
        count_matches = re.findall(r"LogCsvProfiler: Display:\s+Frames\s*:\s*(\d+)", log)
        if count_matches != [str(frames)]:
            errors.append("engine completed frame count mismatch")
        finalize = log.find("CSV finalize time")
        requested_exit = log.find("RequestExit(0, CsvProfiler.ExitAfterCsvProfiling)")
        if finalize < 0 or requested_exit <= finalize:
            errors.append("missing finalized profiler completion before exit")
        if not meta.get("csvid") or "Capture started. CSV ID: " + meta.get("csvid", "") not in log:
            errors.append("CSV capture ID does not match engine log")
        map_path = world_path or "/Game/ForestSpike/Perf/" + level
        result["expected_world_path"] = map_path
        if not re.search(r"Bringing World " + re.escape(map_path) + r"\." + re.escape(level) + r" up for play", log):
            errors.append("expected world not loaded")
        for key, value in (("tag", tag), ("level", level), ("run_id", run_id)):
            if 'Metadata set : %s="%s"' % (key, value) not in log:
                errors.append("log metadata mismatch: " + key)
        fatal = re.search(r"Fatal error:|Unhandled Exception:|Assertion failed:", log)
        if fatal and fatal.start() < requested_exit:
            errors.append("engine failure before completed profiling exit")
        result["shutdown_crash_after_completion"] = exit_code != 0 and not errors
        result["completion_scope"] = "CSV integrity only; LOD selection and full trajectory are separate gates"
        if not errors:
            result["status"] = "PASS_FS_PERF_CAPTURE"
    except Exception as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    return result


def main():
    import argparse
    import datetime
    ap = argparse.ArgumentParser()
    for name in ("csv", "log", "tag", "level", "run-id", "receipt"):
        ap.add_argument("--" + name, required=True)
    for name in ("frames", "cold"):
        ap.add_argument("--" + name, required=True, type=int)
    ap.add_argument("--exit-code", type=int, default=None)
    ap.add_argument("--started-epoch", required=True, type=float)
    ap.add_argument("--world-path", default=None)
    a = ap.parse_args()
    result = validate_run(a.csv, a.log, tag=a.tag, level=a.level, run_id=a.run_id, frames=a.frames,
                          cold=a.cold, started_epoch=a.started_epoch, exit_code=a.exit_code, world_path=a.world_path)
    result["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with Path(a.receipt).open("x", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    print(result["status"], result["errors"])
    raise SystemExit(0 if result["status"] == "PASS_FS_PERF_CAPTURE" else 2)


if __name__ == "__main__":
    main()
