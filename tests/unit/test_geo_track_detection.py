"""Tests sur la détection circuit/spéciale + trim du lead-in."""

from __future__ import annotations

import math

import numpy as np
import pytest
from road2track_core.entities.track_kind import TrackKind
from road2track_geo.detection import detect_track_kind, find_lead_in_index


def _circle(
    radius_m: float, n: int, *, offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> np.ndarray:
    """Cercle fermé dans le plan E-N (Z=offset[2])."""
    thetas = np.linspace(0.0, 2.0 * math.pi, n, endpoint=True)
    pts = np.zeros((n, 3))
    pts[:, 0] = offset[0] + radius_m * np.cos(thetas)
    pts[:, 1] = offset[1] + radius_m * np.sin(thetas)
    pts[:, 2] = offset[2]
    return pts


def test_detect_track_kind_closed_loop_is_circuit() -> None:
    positions = _circle(radius_m=20.0, n=100)
    kind, dist = detect_track_kind(positions)
    assert kind == TrackKind.CIRCUIT
    # endpoint == startpoint à epsilon près
    assert dist == pytest.approx(0.0, abs=1e-6)


def test_detect_track_kind_point_to_point_is_speciale() -> None:
    positions = np.zeros((100, 3))
    positions[:, 0] = np.linspace(0.0, 100.0, 100)  # ligne droite 100 m
    kind, dist = detect_track_kind(positions)
    assert kind == TrackKind.SPECIALE
    assert dist == pytest.approx(100.0, abs=1e-6)


def test_detect_track_kind_too_short_loop_is_speciale() -> None:
    # Boucle fermée mais arc total trop court (10 m < min 50 m).
    positions = _circle(radius_m=1.0, n=50)
    kind, _ = detect_track_kind(positions)
    assert kind == TrackKind.SPECIALE


def test_detect_track_kind_empty() -> None:
    positions = np.zeros((0, 3))
    kind, dist = detect_track_kind(positions)
    assert kind == TrackKind.SPECIALE
    assert dist == 0.0


def test_detect_track_kind_wrong_shape_raises() -> None:
    with pytest.raises(ValueError, match="positions_enu"):
        detect_track_kind(np.zeros((10,)))


# ----------- find_lead_in_index -----------


def test_find_lead_in_index_no_lead_in() -> None:
    """Trajectoire qui démarre déjà sur la boucle → trim à 0."""
    positions = _circle(radius_m=20.0, n=100)
    idx = find_lead_in_index(positions)
    assert idx == 0


def test_find_lead_in_index_detects_lead_in() -> None:
    """Lead-in linéaire de 30 m puis boucle fermée."""
    n_lead = 30
    lead = np.zeros((n_lead, 3))
    lead[:, 0] = np.linspace(-30.0, -1.0, n_lead)  # arrivée vers (0, 0)

    loop = _circle(radius_m=20.0, n=100, offset=(20.0, 0.0, 0.0))
    # La boucle commence à (40, 0, 0), revient à (40, 0, 0).
    # On veut que la fin de la trajectoire soit ~(40, 0, 0).
    positions = np.vstack([lead, loop])
    # Le point final est loop[-1] = (40, 0, 0).
    # Lead-in à -30..-1 → distance à (40, 0, 0) > 15 m partout.
    # Loop commence à index 30 (point (40, 0, 0)), distance = 0.
    idx = find_lead_in_index(positions, lead_in_threshold_m=15.0)
    assert idx == n_lead


def test_find_lead_in_index_empty() -> None:
    positions = np.zeros((0, 3))
    assert find_lead_in_index(positions) == 0
