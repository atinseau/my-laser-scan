"""Tests sur la fusion ARKit + GPS → trajectoire ENU."""

from __future__ import annotations

import math

import numpy as np
import pytest
from road2track_core.errors import InvalidSegmentError
from road2track_geo.fusion.trajectory import (
    find_origin_gps,
    fuse_trajectory,
    kabsch_align,
)

# ----------- find_origin_gps -----------


def test_find_origin_gps_picks_first_valid() -> None:
    times = np.array([0.0, 1.0, 2.0, 3.0])
    lats = np.array([45.0, 45.0, 45.0, 45.0])
    lons = np.array([6.0, 6.0, 6.0, 6.0])
    alts = np.array([100.0, 100.0, 100.0, 100.0])
    hdops = np.array([99.0, 99.0, 5.0, 3.0])  # premier valide à i=2

    t, lat, lon, alt = find_origin_gps(times, lats, lons, alts, hdops)
    assert t == 2.0
    assert lat == 45.0
    assert lon == 6.0
    assert alt == 100.0


def test_find_origin_gps_no_valid_raises() -> None:
    times = np.array([0.0, 1.0])
    lats = np.array([45.0, 45.0])
    lons = np.array([6.0, 6.0])
    alts = np.array([100.0, 100.0])
    hdops = np.array([99.0, 50.0])
    with pytest.raises(InvalidSegmentError, match="aucun fix GPS"):
        find_origin_gps(times, lats, lons, alts, hdops)


def test_find_origin_gps_empty_raises() -> None:
    empty = np.array([])
    with pytest.raises(InvalidSegmentError, match="vide"):
        find_origin_gps(empty, empty, empty, empty, empty)


# ----------- kabsch_align -----------


def test_kabsch_identity_pure_translation() -> None:
    src = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    tgt = src + np.array([10.0, 20.0, 30.0])
    rot, t, rmse = kabsch_align(src, tgt)
    np.testing.assert_array_almost_equal(rot, np.eye(3))
    np.testing.assert_array_almost_equal(t, [10.0, 20.0, 30.0])
    assert rmse == pytest.approx(0.0, abs=1e-9)


def test_kabsch_recovers_known_rotation() -> None:
    # Rotation 90° autour de Z
    src = np.random.default_rng(0).standard_normal((20, 3))
    cos90, sin90 = math.cos(math.pi / 2), math.sin(math.pi / 2)
    rot_known = np.array([[cos90, -sin90, 0], [sin90, cos90, 0], [0, 0, 1]])
    tgt = src @ rot_known.T

    rot, t, rmse = kabsch_align(src, tgt)
    np.testing.assert_array_almost_equal(rot, rot_known, decimal=6)
    np.testing.assert_array_almost_equal(t, np.zeros(3), decimal=6)
    assert rmse == pytest.approx(0.0, abs=1e-6)


def test_kabsch_too_few_points_raises() -> None:
    src = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    tgt = src.copy()
    with pytest.raises(InvalidSegmentError):
        kabsch_align(src, tgt)


# ----------- fuse_trajectory -----------


def test_fuse_trajectory_synthetic_aligned() -> None:
    """ARKit pose et GPS sont synthétiquement alignés : RMSE doit être quasi-nul."""
    n = 100

    arkit_t = np.linspace(0.0, 10.0, n) + 1700000000.0
    # Trajectoire ARKit dans le plan E-N : ligne droite + bruit faible
    arkit_pos = np.zeros((n, 3))
    arkit_pos[:, 0] = np.linspace(0, 50.0, n)  # X = est local ARKit
    arkit_quat = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (n, 1))

    # GPS échantillonné à 5 Hz, autour de (45.0, 6.0, 100.0).
    n_gps = 50
    gps_t = np.linspace(0.0, 10.0, n_gps) + 1700000000.0
    cos45 = math.cos(math.radians(45.0))
    deg_per_m_lon = 180.0 / (math.pi * 6371000.0 * cos45)
    gps_lats = np.full(n_gps, 45.0)
    gps_lons = np.linspace(6.0, 6.0 + 50.0 * deg_per_m_lon, n_gps)
    gps_alts = np.full(n_gps, 100.0)
    gps_hdops = np.full(n_gps, 5.0)

    fused = fuse_trajectory(
        arkit_t, arkit_pos, arkit_quat,
        gps_t, gps_lats, gps_lons, gps_alts, gps_hdops,
    )

    assert fused.times_s.size == n
    assert fused.positions_enu.shape == (n, 3)
    assert fused.origin_wgs84[0] == pytest.approx(45.0)
    assert fused.origin_wgs84[1] == pytest.approx(6.0)
    assert fused.n_gps_fixes_used == n_gps
    # Avec un alignement parfait théorique, RMSE ≈ 0 (à la précision flat-earth près)
    assert fused.rmse_m < 1.0


def test_fuse_trajectory_no_overlap_raises() -> None:
    arkit_t = np.array([1700000000.0, 1700000001.0])
    arkit_pos = np.zeros((2, 3))
    arkit_quat = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (2, 1))

    gps_t = np.array([1700000100.0, 1700000101.0, 1700000102.0])
    gps_lats = np.full(3, 45.0)
    gps_lons = np.full(3, 6.0)
    gps_alts = np.full(3, 100.0)
    gps_hdops = np.full(3, 5.0)

    with pytest.raises(InvalidSegmentError, match="chevauchent"):
        fuse_trajectory(
            arkit_t, arkit_pos, arkit_quat,
            gps_t, gps_lats, gps_lons, gps_alts, gps_hdops,
        )


def test_fuse_trajectory_arc_length_consistent() -> None:
    """Si l'alignement est presque l'identité, l'arc-length ENU ≈ arc-length ARKit."""
    n = 50
    arkit_t = np.linspace(0.0, 5.0, n) + 1700000000.0
    arkit_pos = np.zeros((n, 3))
    arkit_pos[:, 0] = np.linspace(0, 25.0, n)
    arkit_quat = np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (n, 1))

    n_gps = 20
    gps_t = np.linspace(0.0, 5.0, n_gps) + 1700000000.0
    gps_lats = np.full(n_gps, 45.0)
    cos45 = math.cos(math.radians(45.0))
    deg_per_m_lon = 180.0 / (math.pi * 6371000.0 * cos45)
    gps_lons = 6.0 + np.linspace(0, 25.0, n_gps) * deg_per_m_lon
    gps_alts = np.full(n_gps, 100.0)
    gps_hdops = np.full(n_gps, 5.0)

    fused = fuse_trajectory(
        arkit_t, arkit_pos, arkit_quat,
        gps_t, gps_lats, gps_lons, gps_alts, gps_hdops,
    )
    # Distance totale dans l'ENU doit être ~25 m ± un peu (alignement non parfait, bruit numérique)
    diffs = np.diff(fused.positions_enu, axis=0)
    arc = float(np.linalg.norm(diffs, axis=1).sum())
    assert arc == pytest.approx(25.0, rel=0.05)
