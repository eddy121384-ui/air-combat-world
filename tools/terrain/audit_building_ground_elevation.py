"""Audit surveyed building ground elevations already present in projected WFS source.

The Taipei WFS semantics probe established:
  building height = roof elevation - entrance elevation
where available. This audit determines whether entrance/ground elevation is
sufficiently complete and internally consistent to serve as the building-Z
anchor independently of the terrain raster.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
OUT = REPO / "data/generated/taipei/terrain/building_ground_elevation_audit.json"


def finite(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


fc = json.loads(SOURCE.read_text(encoding="utf-8"))
rows = []
anomalies = []
by_height_source = Counter()

for f in fc.get("features", []):
    p = f.get("properties") or {}
    bid = str(f.get("id", ""))
    h = p.get("height_m")
    ground = p.get("ground_elev_m")
    top = p.get("top_elev_m")
    source = p.get("height_source")
    by_height_source[str(source)] += 1

    row = {
        "building_id": bid,
        "height_m": h,
        "ground_elev_m": ground,
        "top_elev_m": top,
        "height_source": source,
    }
    rows.append(row)

    if finite(ground) and finite(top) and finite(h):
        diff = float(top) - float(ground)
        error = abs(diff - float(h))
        if error > 0.01:
            anomalies.append({
                **row,
                "top_minus_ground_m": diff,
                "height_identity_error_m": error,
                "reason": "top-ground differs from height by >1 cm",
            })
    if finite(ground) and finite(top) and float(top) < float(ground):
        anomalies.append({**row, "reason": "top below ground"})


grounds = [float(r["ground_elev_m"]) for r in rows if finite(r["ground_elev_m"])]
tops = [float(r["top_elev_m"]) for r in rows if finite(r["top_elev_m"])]
heights = [float(r["height_m"]) for r in rows if finite(r["height_m"])]
identity = [
    abs((float(r["top_elev_m"]) - float(r["ground_elev_m"])) - float(r["height_m"]))
    for r in rows
    if finite(r["top_elev_m"]) and finite(r["ground_elev_m"]) and finite(r["height_m"])
]


def stats(values):
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "p05": ordered[max(0, int((len(ordered)-1) * 0.05))],
        "p95": ordered[min(len(ordered)-1, int((len(ordered)-1) * 0.95))],
        "max": max(values),
    }


count = len(rows)
ground_count = len(grounds)
top_count = len(tops)
identity_count = len(identity)
ground_coverage = ground_count / count if count else 0.0

# Candidate decision is conservative: this does not declare vertical-datum
# compatibility with DTM; that requires cross-checking the terrain source later.
candidate_ok = (
    count > 0
    and ground_coverage >= 0.95
    and identity_count >= int(count * 0.95)
    and (max(identity) if identity else math.inf) <= 0.01
)

report = {
    "gate": "Xinyi WFS surveyed ground-elevation audit",
    "source_path": str(SOURCE.relative_to(REPO)),
    "feature_count": count,
    "ground_elevation": {
        "coverage_count": ground_count,
        "coverage_ratio": ground_coverage,
        "missing_count": count - ground_count,
        "stats_m": stats(grounds),
    },
    "top_elevation": {
        "coverage_count": top_count,
        "coverage_ratio": top_count / count if count else 0.0,
        "missing_count": count - top_count,
        "stats_m": stats(tops),
    },
    "height": {
        "coverage_count": len(heights),
        "stats_m": stats(heights),
        "source_counts": dict(by_height_source),
    },
    "survey_identity": {
        "checked_count": identity_count,
        "max_abs_error_m": max(identity) if identity else None,
        "median_abs_error_m": statistics.median(identity) if identity else None,
        "anomaly_count": len(anomalies),
        "anomalies_preview": anomalies[:100],
        "definition": "height_m ~= top_elev_m - ground_elev_m",
    },
    "candidate_building_z_policy": {
        "pass_for_further_validation": candidate_ok,
        "policy": "use WFS ground_elev_m as surveyed building base elevation where finite",
        "important_limit": (
            "Do not production-lock until vertical datum and spatial agreement are cross-checked "
            "against the selected terrain source."
        ),
        "fallback_not_yet_defined": True,
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({
    "feature_count": count,
    "ground_coverage_count": ground_count,
    "ground_coverage_ratio": ground_coverage,
    "ground_stats_m": stats(grounds),
    "identity_checked_count": identity_count,
    "identity_max_abs_error_m": max(identity) if identity else None,
    "anomaly_count": len(anomalies),
    "candidate_pass": candidate_ok,
    "report": str(OUT.relative_to(REPO)),
}, ensure_ascii=False, indent=2))

if not candidate_ok:
    raise SystemExit(2)
