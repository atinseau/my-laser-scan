"""Tests sur l'initialisation du nuage de gaussiennes."""

from __future__ import annotations

import numpy as np
import pytest
from road2track_ml.gs import (
    average_nearest_neighbor_distance,
    init_around_trajectory,
)


def test_init_around_trajectory_shape() -> None:
    positions = np.zeros((10, 3))
    positions[:, 0] = np.arange(10)
    cloud = init_around_trajectory(positions, points_per_pose=5, radius_m=1.0)
    assert cloud.means.shape == (50, 3)
    assert cloud.colors.shape == (50, 3)


def test_init_around_trajectory_radius_bound() -> None:
    positions = np.zeros((3, 3))  # toutes en (0, 0, 0)
    cloud = init_around_trajectory(positions, points_per_pose=100, radius_m=2.0, seed=0)
    distances = np.linalg.norm(cloud.means, axis=1)
    # Tous les points doivent être dans la sphère de rayon 2 m.
    assert distances.max() <= 2.0 + 1e-6


def test_init_around_trajectory_color_grey() -> None:
    positions = np.zeros((1, 3))
    cloud = init_around_trajectory(positions, points_per_pose=10)
    np.testing.assert_array_almost_equal(cloud.colors, np.full((10, 3), 0.5))


def test_init_around_trajectory_wrong_shape_raises() -> None:
    with pytest.raises(ValueError, match="positions_world"):
        init_around_trajectory(np.zeros((10,)))


def test_average_nearest_neighbor_distance_uniform_grid() -> None:
    # Grille 1D : points à intervalle régulier de 1 m.
    points = np.zeros((10, 3))
    points[:, 0] = np.arange(10)
    nn = average_nearest_neighbor_distance(points)
    assert nn == pytest.approx(1.0, abs=0.1)


def test_average_nearest_neighbor_distance_single_point() -> None:
    nn = average_nearest_neighbor_distance(np.zeros((1, 3)))
    assert nn == 1.0  # fallback
