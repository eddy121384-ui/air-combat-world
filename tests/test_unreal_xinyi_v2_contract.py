import math

import numpy as np

from tools.unreal_xinyi_v2.build_contract import (
    COMPONENT_QUADS,
    COMPONENTS_PER_AXIS,
    HEIGHTMAP_SIZE,
    LANDSCAPE_SCALE_Z,
    TILE_SIZE_M,
    decode_landscape_height_m,
    encode_landscape_height_m,
    enu_to_ue_cm,
    validate_tile_grid,
)


def test_landscape_topology_is_one_component_per_500m_tile():
    assert COMPONENTS_PER_AXIS == 5
    assert COMPONENT_QUADS == 126
    assert HEIGHTMAP_SIZE == 631
    assert COMPONENTS_PER_AXIS * COMPONENT_QUADS + 1 == HEIGHTMAP_SIZE
    spacing_m = TILE_SIZE_M / COMPONENT_QUADS
    assert math.isclose(spacing_m * COMPONENT_QUADS, 500.0, abs_tol=1e-12)


def test_height_encoding_roundtrip_is_centimetre_class():
    values = np.asarray([-5.5, 0.0, 8.41, 277.66], dtype=np.float64)
    encoded = encode_landscape_height_m(values, LANDSCAPE_SCALE_Z)
    decoded = decode_landscape_height_m(encoded, LANDSCAPE_SCALE_Z)
    assert np.max(np.abs(decoded - values)) <= 0.01
    assert int(encoded[1]) == 32768


def test_validated_enu_to_unreal_mapping():
    # Existing UE spike measured ENU (-90.78, +77.92) m as
    # UE (-9078, -7792) cm in horizontal axes.
    assert enu_to_ue_cm(-90.78, 77.92, 508.0) == [-9078.0, -7792.0, 50800.0]


def test_shared_5x5_tile_grid_contract():
    rows = []
    for y in (-1000.0, -500.0, 0.0, 500.0, 1000.0):
        for x in (-1500.0, -1000.0, -500.0, 0.0, 500.0):
            rows.append({"origin_enu_m": [x, y]})
    extent = validate_tile_grid(rows, rows)
    assert extent == {
        "min_east_m": -1500.0,
        "max_east_m": 1000.0,
        "min_north_m": -1000.0,
        "max_north_m": 1500.0,
    }
