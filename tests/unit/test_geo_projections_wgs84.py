"""Tests sur la projection WGS84 ↔ ENU flat-earth."""

from __future__ import annotations

import numpy as np
import pytest
from road2track_geo.projections.wgs84 import (
    enu_to_wgs84_flat,
    wgs84_array_to_enu_flat,
    wgs84_to_enu_flat,
)


def test_origin_maps_to_enu_zero() -> None:
    e, n, u = wgs84_to_enu_flat(45.0, 6.0, 100.0, 45.0, 6.0, 100.0)
    assert e == pytest.approx(0.0, abs=1e-9)
    assert n == pytest.approx(0.0, abs=1e-9)
    assert u == pytest.approx(0.0, abs=1e-9)


def test_one_degree_north_is_about_111km() -> None:
    e, n, _ = wgs84_to_enu_flat(46.0, 6.0, 0.0, 45.0, 6.0, 0.0)
    assert e == pytest.approx(0.0, abs=0.1)
    assert n == pytest.approx(111195.0, rel=0.01)


def test_one_degree_east_at_45deg_is_about_78km() -> None:
    e, n, _ = wgs84_to_enu_flat(45.0, 7.0, 0.0, 45.0, 6.0, 0.0)
    # cos(45°) × 111195 ≈ 78626 m
    assert e == pytest.approx(78626.0, rel=0.01)
    assert n == pytest.approx(0.0, abs=0.1)


def test_alt_diff_is_up() -> None:
    _, _, u = wgs84_to_enu_flat(45.0, 6.0, 250.0, 45.0, 6.0, 100.0)
    assert u == pytest.approx(150.0)


def test_array_consistent_with_scalar() -> None:
    lats = np.array([45.0, 45.001, 45.002])
    lons = np.array([6.0, 6.0, 6.001])
    alts = np.array([100.0, 110.0, 120.0])
    enu = wgs84_array_to_enu_flat(lats, lons, alts, 45.0, 6.0, 100.0)
    for i in range(3):
        e, n, u = wgs84_to_enu_flat(
            float(lats[i]), float(lons[i]), float(alts[i]), 45.0, 6.0, 100.0
        )
        assert enu[i, 0] == pytest.approx(e, abs=1e-6)
        assert enu[i, 1] == pytest.approx(n, abs=1e-6)
        assert enu[i, 2] == pytest.approx(u, abs=1e-6)


def test_round_trip_enu_wgs84() -> None:
    origin = (45.0, 6.0, 100.0)
    lat0, lon0, alt0 = 45.005, 6.003, 250.0
    e, n, u = wgs84_to_enu_flat(lat0, lon0, alt0, *origin)
    lat1, lon1, alt1 = enu_to_wgs84_flat(e, n, u, *origin)
    assert lat1 == pytest.approx(lat0, abs=1e-9)
    assert lon1 == pytest.approx(lon0, abs=1e-9)
    assert alt1 == pytest.approx(alt0, abs=1e-6)
