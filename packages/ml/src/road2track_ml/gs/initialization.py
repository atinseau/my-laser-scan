"""Initialisation du nuage de gaussiennes.

POC : sans dense LiDAR mesh, on initialise via une grille bruitée le long de
la trajectoire des keyframes. Chaque pose génère N points dans une sphère
autour d'elle.

V1 : remplacement par init depuis le nuage LiDAR dense (point cloud Record3D
ou Polycam), cf. specs/04-pipeline-ml.md §3.3 ("Random init : Non").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class InitialPointCloud:
    """Nuage initial des centres de gaussiennes + couleurs RGB ∈ [0, 1]."""

    means: NDArray[np.float64]  # (N, 3)
    colors: NDArray[np.float64]  # (N, 3) ∈ [0, 1]


def init_around_trajectory(
    positions_world: NDArray[np.float64],
    *,
    points_per_pose: int = 50,
    radius_m: float = 2.0,
    seed: int = 0,
) -> InitialPointCloud:
    """Initialise N×K points dans une sphère de rayon `radius_m` autour de chaque pose.

    Couleur initialisée en gris moyen (0.5). Les couleurs RGB seront raffinées
    par le training via les SH coefficients.
    """
    if positions_world.ndim != 2 or positions_world.shape[1] != 3:
        raise ValueError(
            f"positions_world doit être (N, 3) ; got {positions_world.shape}"
        )
    rng = np.random.default_rng(seed)
    n_poses = positions_world.shape[0]
    n_points = n_poses * points_per_pose
    # Échantillonnage uniforme dans une boule de rayon r.
    radii = radius_m * rng.uniform(0.0, 1.0, size=n_points) ** (1.0 / 3.0)
    directions = rng.normal(size=(n_points, 3))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True) + 1e-9
    offsets = directions * radii[:, None]

    pose_indices = np.repeat(np.arange(n_poses), points_per_pose)
    means = positions_world[pose_indices] + offsets

    colors = np.full((n_points, 3), 0.5, dtype=np.float64)
    return InitialPointCloud(means=means, colors=colors)


def average_nearest_neighbor_distance(
    points: NDArray[np.float64], sample: int = 1000, seed: int = 0
) -> float:
    """Distance moyenne au plus proche voisin (utile pour scale_init).

    Pour limiter le coût en O(N²), on échantillonne `sample` points.
    """
    if points.shape[0] < 2:
        return 1.0
    rng = np.random.default_rng(seed)
    idx = rng.choice(points.shape[0], size=min(sample, points.shape[0]), replace=False)
    sub = points[idx]
    diffs = sub[:, None, :] - sub[None, :, :]
    dist_sq = np.sum(diffs * diffs, axis=-1)
    np.fill_diagonal(dist_sq, np.inf)
    nn_dist = np.sqrt(np.min(dist_sq, axis=1))
    return float(np.mean(nn_dist))
