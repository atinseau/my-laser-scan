"""Tests sur le sampling spatial le long d'une trajectoire ENU."""

from __future__ import annotations

import numpy as np
import pytest
from road2track_geo.sampling import (
    DEFAULT_MIN_SPACING_M,
    select_indices_by_spacing,
)


def test_select_indices_by_spacing_uniform_line() -> None:
    """Ligne droite à pas constant : on doit retenir 1 sur N."""
    n = 100
    positions = np.zeros((n, 3))
    positions[:, 0] = np.linspace(0.0, 10.0, n)  # 10 cm entre chaque point
    indices = select_indices_by_spacing(positions, min_spacing_m=1.0)
    # On garde index 0, puis ~1 m plus loin → ~10 indices, etc.
    # Distance 10 m, spacing 1 m → ~11 keyframes (incluant départ).
    assert indices.size == pytest.approx(11, abs=1)
    assert indices[0] == 0
    # Distances entre points retenus ≥ 1 m
    diffs = np.diff(positions[indices], axis=0)
    distances = np.linalg.norm(diffs, axis=1)
    assert np.all(distances >= 1.0)


def test_select_indices_by_spacing_keeps_first() -> None:
    positions = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.2, 0.0, 0.0]])
    indices = select_indices_by_spacing(positions, min_spacing_m=1.0)
    # Seul le premier passe le filtre (les autres sont à < 1 m du dernier retenu).
    assert indices.tolist() == [0]


def test_select_indices_by_spacing_default_constant() -> None:
    """Vérifie qu'on expose bien la constante par défaut (0.5 m)."""
    assert DEFAULT_MIN_SPACING_M == 0.5


def test_select_indices_by_spacing_empty() -> None:
    indices = select_indices_by_spacing(np.zeros((0, 3)))
    assert indices.size == 0


def test_select_indices_by_spacing_wrong_shape_raises() -> None:
    with pytest.raises(ValueError, match="positions_enu"):
        select_indices_by_spacing(np.zeros((10,)))


def test_select_indices_by_spacing_zero_spacing_keeps_all() -> None:
    n = 50
    positions = np.zeros((n, 3))
    positions[:, 0] = np.linspace(0.0, 5.0, n)
    indices = select_indices_by_spacing(positions, min_spacing_m=0.0)
    assert indices.tolist() == list(range(n))
