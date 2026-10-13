"""ForestSpike B0 test world: deterministic analytic terrain + forest field (numpy only).

Everything here is a closed-form function of (east, north) in metres and a single integer seed, so the
terrain mesh, the field textures, the instance pool and any later analysis agree exactly and a re-run
reproduces byte-identical outputs. The world is a synthetic test fixture for the Issue #19 forest A/B
experiment: it is NOT Northern Taiwan terrain and not a land-use dataset.

ENU frame: x = east, y = north, z = up (metres). Core = 1 km x 1 km centred on the origin; context =
6 km x 6 km centred on the origin (cheap shared terrain, no variable content).
"""
from __future__ import annotations

import math

import numpy as np

SEED = 20261012
CORE_M = 1000.0
CTX_M = 6000.0
CORE_HALF = CORE_M / 2.0
CTX_HALF = CTX_M / 2.0

_rng = np.random.default_rng(SEED)

# ---- terrain: sum of plane waves (rolling hills) + radial uplift toward the context rim ---------------------
_K = 16
_lam = np.exp(_rng.uniform(math.log(150.0), math.log(2600.0), _K))
_ang = _rng.uniform(0.0, 2.0 * math.pi, _K)
_ph = _rng.uniform(0.0, 2.0 * math.pi, _K)
_amp = 11.0 * (_lam / 800.0) ** 0.9
_kx = np.cos(_ang) * 2.0 * math.pi / _lam
_ky = np.sin(_ang) * 2.0 * math.pi / _lam
BASE_ELEVATION_M = 120.0   # core valley floor sits above 0 so "AGL" is never confused with sea level


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def height_and_grad(e, n):
    """Terrain height (m) and (dh/de, dh/dn) at arrays e, n (same shape)."""
    e = np.asarray(e, np.float64)
    n = np.asarray(n, np.float64)
    h = np.full(e.shape, BASE_ELEVATION_M)
    he = np.zeros(e.shape)
    hn = np.zeros(e.shape)
    for k in range(_K):
        arg = _kx[k] * e + _ky[k] * n + _ph[k]
        h += _amp[k] * np.sin(arg)
        c = _amp[k] * np.cos(arg)
        he += c * _kx[k]
        hn += c * _ky[k]
    # radial uplift: the context rises to a ridge wall ~2.4-3 km from the centre (far/theater backdrop)
    r = np.hypot(e, n)
    t = (r - 1300.0) / 1700.0
    s = _smooth(t)
    ds = np.where((t > 0.0) & (t < 1.0), 6.0 * np.clip(t, 0, 1) * (1.0 - np.clip(t, 0, 1)), 0.0) / 1700.0
    up = 260.0
    h += up * s
    rr = np.maximum(r, 1e-9)
    he += up * ds * e / rr
    hn += up * ds * n / rr
    return h, he, hn


def height(e, n):
    return height_and_grad(e, n)[0]


def slope_deg(e, n):
    _, he, hn = height_and_grad(e, n)
    return np.degrees(np.arctan(np.hypot(he, hn)))


# ---- forest field ------------------------------------------------------------------------------------------
_rng2 = np.random.default_rng(SEED + 101)
_F = 12
_flam = np.exp(_rng2.uniform(math.log(260.0), math.log(1500.0), _F))
_fang = _rng2.uniform(0.0, 2.0 * math.pi, _F)
_fph = _rng2.uniform(0.0, 2.0 * math.pi, _F)
_fkx = np.cos(_fang) * 2.0 * math.pi / _flam
_fky = np.sin(_fang) * 2.0 * math.pi / _flam
_fw = (_flam / 600.0) ** 0.3
FOREST_THRESHOLD = -0.55   # tuned so ~75 % of the core is forest (build_inputs records the measured value)

# a road (always open), a power-line corridor and clearings: they carve the forest like the references show
ROAD_WIDTH_M = 9.0
CORRIDOR_WIDTH_M = 26.0
CLEARINGS = [  # (e, n, radius_e, radius_n, angle_deg)
    (-180.0, 150.0, 85.0, 55.0, 25.0),
    (240.0, -260.0, 70.0, 70.0, 0.0),
    (-1200.0, -900.0, 220.0, 140.0, 60.0),
    (1500.0, 1100.0, 260.0, 180.0, -30.0),
    (700.0, 1900.0, 300.0, 200.0, 10.0),
    (-1700.0, 1600.0, 240.0, 240.0, 0.0),
    (350.0, -1900.0, 280.0, 160.0, 0.0),
]


def _noise(e, n):
    v = np.zeros(np.shape(e))
    for k in range(_F):
        v += _fw[k] * np.sin(_fkx[k] * e + _fky[k] * n + _fph[k])
    return v / math.sqrt(0.5 * float(np.sum(_fw ** 2)))


def road_distance(e, n):
    """Distance (m) to the road centreline: a sinusoidal west-east road across the core and context."""
    cn = 70.0 * np.sin(e / 310.0) + 45.0 * np.sin(e / 97.0 + 1.3) - 60.0
    return np.abs(n - cn) * np.cos(np.arctan(70.0 / 310.0 * np.cos(e / 310.0)))


def corridor_distance(e, n):
    """Distance (m) to a straight power-line corridor running ~35 deg across the core and beyond."""
    a = math.radians(35.0)
    return np.abs(-math.sin(a) * (e - 120.0) + math.cos(a) * (n + 40.0))


def forest_binary(e, n):
    e = np.asarray(e, np.float64)
    n = np.asarray(n, np.float64)
    sl = slope_deg(e, n)
    h = height(e, n)
    score = _noise(e, n) + 0.035 * sl - 0.0035 * np.maximum(0.0, 175.0 - h) * 1.0
    f = score > FOREST_THRESHOLD
    f &= road_distance(e, n) > ROAD_WIDTH_M * 0.5
    f &= corridor_distance(e, n) > CORRIDOR_WIDTH_M * 0.5
    for ce, cn, ra, rb, ang in CLEARINGS:
        a = math.radians(ang)
        de, dn = e - ce, n - cn
        u = (math.cos(a) * de + math.sin(a) * dn) / ra
        v = (-math.sin(a) * de + math.cos(a) * dn) / rb
        f &= (u * u + v * v) > 1.0
    return f


def raster(extent_m, size_px, ss=4):
    """Forest coverage (0..1) per texel for a square raster centred on the origin; row j <-> north increasing.

    Returns (coverage float32 [size,size], binary float64 sampled at texel centres [size,size]).
    """
    half = extent_m / 2.0
    n_ss = size_px * ss
    c = (np.arange(n_ss) + 0.5) / n_ss * extent_m - half
    E, N = np.meshgrid(c, c)           # E varies along columns, N along rows (row 0 = south)
    b = forest_binary(E, N).astype(np.float32)
    cov = b.reshape(size_px, ss, size_px, ss).mean(axis=(1, 3))
    return cov.astype(np.float32)
