"""Phase 1C measurement: how far can the accepted Xinyi ENU frame be stretched, and what replaces it.

Compares, across the Northern Taiwan theater:
  (a) the accepted Xinyi frame: equirectangular tangent plane at (121.5654, 25.0330)
      x = R*dlon*cos(lat0), y = R*dlat   (tools/compiler/worldmodel.py::lonlat_to_enu)
  (b) NTW frame: EPSG:3826 minus a fixed origin
against geodesic truth (WGS84 ellipsoid, pyproj.Geod).
Also: the exact Xinyi-ENU -> NTW similarity transform (so accepted GLBs are instanced, never edited),
float32 precision vs distance, and flat-plane curvature drop.
Writes data/ntw/coordinate_study.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from pyproj import Geod, Proj

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler"))
from frame import NTW_ORIGIN_TM2, lonlat_to_ntw  # noqa: E402
from worldmodel import lonlat_to_enu, R_WGS84  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
O_LON, O_LAT = 121.5654, 25.0330  # cities/taipei/city.yaml enu_origin
GEOD = Geod(ellps="WGS84")
TM2 = Proj("EPSG:3826")

LANDMARKS = {
    "xinyi_origin": (121.5654, 25.0330), "taoyuan_city": (121.3010, 24.9936), "zhongli": (121.2250, 24.9653),
    "keelung": (121.7391, 25.1276), "ruifang_ne": (121.8100, 25.1000), "sanzhi_nw_coast": (121.5000, 25.2600),
    "hsinchu_city": (120.9686, 24.8138), "hsinchu_county_smw": (120.9500, 24.5500), "yilan_city": (121.7532, 24.7570),
    "su_ao_south": (121.8400, 24.6000), "taoyuan_airport": (121.2321, 25.0777), "wufeng_far_south": (121.1400, 24.4700),
}


def fit_similarity(src, dst):
    """2-D similarity (scale s, rotation theta, translation) src->dst by least squares (Umeyama)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    u, sig, vt = np.linalg.svd(b.T @ a / len(src))
    d = np.eye(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        d[1, 1] = -1
    r = u @ d @ vt
    s = np.trace(np.diag(sig) @ d) / (a ** 2).sum() * len(src)
    t = mu_d - s * (r @ mu_s)
    theta = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    resid = np.linalg.norm((s * (r @ src.T)).T + t - dst, axis=1)
    return s, theta, t, resid


def fit_affine(half_km, n=21):
    """Full 2-D affine ENU->NTW; reports axis scales (singular decomposition) and residual."""
    g = np.linspace(-half_km, half_km, n)
    lons, lats = [], []
    for dx in g:
        for dy in g:
            lons.append(O_LON + math.degrees(dx * 1000 / (R_WGS84 * math.cos(math.radians(O_LAT)))))
            lats.append(O_LAT + math.degrees(dy * 1000 / R_WGS84))
    lons, lats = np.array(lons), np.array(lats)
    enu = np.array([lonlat_to_enu(a, b, O_LON, O_LAT) for a, b in zip(lons, lats)])
    nx, ny = lonlat_to_ntw(lons, lats)
    A = np.column_stack([enu, np.ones(len(enu))])
    coef, *_ = np.linalg.lstsq(A, np.column_stack([nx, ny]), rcond=None)
    pred = A @ coef
    resid = np.linalg.norm(pred - np.column_stack([nx, ny]), axis=1)
    m = coef[:2].T  # 2x2 linear part
    sx, sy = float(np.linalg.norm(m[:, 0])), float(np.linalg.norm(m[:, 1]))
    return {"fit_extent_km": 2 * half_km, "linear_part": [[round(float(v), 9) for v in row] for row in m],
            "translation_m": [round(float(coef[2][0]), 4), round(float(coef[2][1]), 4)],
            "east_axis_scale": round(sx, 7), "north_axis_scale": round(sy, 7),
            "east_axis_rotation_deg": round(math.degrees(math.atan2(m[1, 0], m[0, 0])), 5),
            "north_axis_rotation_deg": round(math.degrees(math.atan2(-m[0, 1], m[1, 1])), 5),
            "max_residual_m": round(float(resid.max()), 5),
            "meaning": "ENU 500 m tile maps to %.1f m east-west x %.1f m north-south in true ground metres" % (500 * sx, 500 * sy)}


def main():
    rows = []
    for name, (lon, lat) in LANDMARKS.items():
        az, _, true_d = GEOD.inv(O_LON, O_LAT, lon, lat)
        ex, ey = lonlat_to_enu(lon, lat, O_LON, O_LAT)
        enu_d = math.hypot(ex, ey)
        enu_az = math.degrees(math.atan2(ex, ey)) % 360
        nx, ny = (float(v) for v in lonlat_to_ntw(lon, lat))
        ox, oy = (float(v) for v in lonlat_to_ntw(O_LON, O_LAT))
        tm2_d = math.hypot(nx - ox, ny - oy)
        k, conv = (lambda f: (f.meridional_scale, f.meridian_convergence))(TM2.get_factors(lon, lat))
        rows.append({
            "name": name, "geodesic_km": round(true_d / 1000, 2),
            "enu_flat_dist_error_m": round(enu_d - true_d, 1),
            "enu_flat_dist_error_pct": round(100 * (enu_d / true_d - 1), 4) if true_d > 1 else 0.0,
            "tm2_dist_error_m": round(tm2_d - true_d, 2),
            "tm2_dist_error_pct": round(100 * (tm2_d / true_d - 1), 5) if true_d > 1 else 0.0,
            "tm2_point_scale_k": round(k, 6), "grid_convergence_deg": round(conv, 4),
            "curvature_drop_m_flat_plane": round(true_d ** 2 / (2 * R_WGS84), 1),
        })
    out = {"enu_origin_lonlat": [O_LON, O_LAT], "landmarks": rows}
    out["worst_enu_flat_dist_error_m"] = max(abs(r["enu_flat_dist_error_m"]) for r in rows)
    out["worst_tm2_dist_error_m"] = max(abs(r["tm2_dist_error_m"]) for r in rows)

    # Exact Xinyi ENU -> NTW similarity, fitted on a 2.5 km Xinyi extent and checked on larger extents
    def fit_extent(half_km, n=21):
        g = np.linspace(-half_km, half_km, n)
        lons, lats = [], []
        for dx in g:
            for dy in g:
                lon = O_LON + math.degrees(dx * 1000 / (R_WGS84 * math.cos(math.radians(O_LAT))))
                lat = O_LAT + math.degrees(dy * 1000 / R_WGS84)
                lons.append(lon); lats.append(lat)
        lons, lats = np.array(lons), np.array(lats)
        enu = np.array([lonlat_to_enu(a, b, O_LON, O_LAT) for a, b in zip(lons, lats)])
        nx, ny = lonlat_to_ntw(lons, lats)
        s, th, t, resid = fit_similarity(enu, np.column_stack([nx, ny]))
        return s, th, t, resid
    s, th, t, resid = fit_extent(1.25)
    out["xinyi_enu_to_ntw_affine"] = fit_affine(1.25)
    out["xinyi_enu_to_ntw"] = {
        "fit_extent_km": 2.5, "scale": round(float(s), 9), "rotation_deg_ccw": round(float(th), 6),
        "translation_m": [round(float(t[0]), 4), round(float(t[1]), 4)],
        "max_residual_m": round(float(resid.max()), 4), "rms_residual_m": round(float(np.sqrt((resid ** 2).mean())), 4),
        "note": "ENU east/north axes are TRUE north/east; NTW axes are TM2 grid. The rotation is grid convergence. "
                "Without it a feature 2.5 km from the Xinyi origin is misplaced by ~2500*sin(theta) m.",
    }
    ign = 2500.0 * math.sin(math.radians(abs(th)))
    out["xinyi_enu_to_ntw"]["misplacement_if_rotation_ignored_at_2p5km_m"] = round(ign, 2)
    out["enu_frame_stretch_fit"] = {}
    for half in (5, 20, 50):
        s2, th2, _, r2 = fit_extent(half)
        out["enu_frame_stretch_fit"][f"{half}km_halfwidth"] = {
            "scale": round(float(s2), 7), "rotation_deg": round(float(th2), 5),
            "max_residual_m": round(float(r2.max()), 2), "rms_residual_m": round(float(np.sqrt((r2 ** 2).mean())), 2)}

    # float32 precision (GLB POSITION / GPU vertex) vs distance from a frame origin
    prec = []
    for label, d in (("xinyi tile-local (<=500 m)", 500.0), ("25 km", 25e3), ("60 km", 60e3), ("114 km (theater width)", 114e3)):
        ulp_m = float(np.spacing(np.float32(d)))
        prec.append({"coordinate_magnitude": label, "float32_ulp_m": ulp_m, "float32_ulp_cm_in_ue_units": ulp_m * 100})
    ue_cm = np.float32(114e3 * 100)
    prec.append({"coordinate_magnitude": "114 km in UE centimetres (float32)", "float32_ulp_m": float(np.spacing(ue_cm)) / 100})
    out["float32_precision"] = prec
    out["ntw_origin_epsg3826"] = NTW_ORIGIN_TM2
    p = REPO / "data/ntw/coordinate_study.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
