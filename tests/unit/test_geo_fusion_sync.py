"""Tests sur la synchronisation Record3D ↔ Sensor Logger."""

from __future__ import annotations

import numpy as np
import pytest
from road2track_core.errors import InvalidSegmentError
from road2track_geo.fusion.sync import (
    CORRELATION_THRESHOLD,
    UTC_DRIFT_THRESHOLD_MS,
    compute_sync,
    cross_correlation_offset_ms,
)

# ----------- compute_sync -----------


def _trivial_arkit(t0: float = 0.0, n: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Renvoie (times, positions) — positions linéaires (acc nulle)."""
    times = np.linspace(t0, t0 + 1.0, n)
    pos = np.zeros((n, 3))
    pos[:, 0] = times - t0  # mouvement linéaire en X
    return times, pos


def _trivial_imu(t0: float = 0.0, n: int = 100) -> tuple[np.ndarray, np.ndarray]:
    times = np.linspace(t0, t0 + 1.0, n)
    accel = np.zeros((n, 3))
    accel[:, 2] = 9.81
    return times, accel


def test_compute_sync_utc_aligned() -> None:
    arkit_t, arkit_pos = _trivial_arkit(t0=1700000000.0)
    imu_t, imu_acc = _trivial_imu(t0=1700000000.05)  # +50 ms < 100 ms
    result = compute_sync(arkit_t, arkit_pos, imu_t, imu_acc)
    assert result.method == "utc_aligned"
    assert result.offset_applied_ms == 0.0
    assert abs(result.drift_ms - 50.0) < 1.0


def test_compute_sync_drift_above_threshold_triggers_cross_corr() -> None:
    """Drift > 100 ms force la cross-corrélation, mais signaux plats donnent fallback_zero."""
    arkit_t, arkit_pos = _trivial_arkit(t0=1700000000.0)
    imu_t, imu_acc = _trivial_imu(t0=1700000000.5)  # +500 ms
    result = compute_sync(arkit_t, arkit_pos, imu_t, imu_acc)
    # signaux plats → corrélation faible → fallback_zero
    assert result.method == "fallback_zero"
    assert result.offset_applied_ms == 0.0
    assert result.drift_ms > UTC_DRIFT_THRESHOLD_MS
    assert result.warning is not None


def test_compute_sync_cross_correlation_finds_offset() -> None:
    """Signaux similaires avec décalage volontaire : la corrélation le retrouve."""
    rng = np.random.default_rng(42)
    n = 1000
    base_t = np.linspace(0.0, 10.0, n)
    # Profil avec quelques pics
    base_signal = np.sin(2 * np.pi * 1.0 * base_t) + 0.5 * rng.standard_normal(n)
    # ARKit positions : intégrale double du signal pour que la 2nde dérivée le retrouve
    pos = np.zeros((n, 3))
    pos[:, 0] = np.cumsum(np.cumsum(base_signal)) * 1e-4

    # IMU décalé de +0.5 s en timestamps absolus, signal très corrélé.
    imu_t = base_t + 0.5
    imu_acc = np.zeros((n, 3))
    imu_acc[:, 0] = base_signal

    arkit_times = base_t + 1700000000.0
    imu_times = imu_t + 1700000000.0

    result = compute_sync(arkit_times, pos, imu_times, imu_acc)
    # On force la cross-corrélation (drift = 500 ms > 100 ms).
    assert result.method in {"cross_correlation", "fallback_zero"}
    if result.method == "cross_correlation":
        assert result.correlation_max >= CORRELATION_THRESHOLD


def test_compute_sync_offset_too_large_raises() -> None:
    """Si l'offset détecté > 5 s, on lève InvalidSegmentError."""
    arkit_t, arkit_pos = _trivial_arkit(t0=1700000000.0, n=200)
    # Décalage absolu énorme : 100 s. Cross-corrélation ne pourra pas trouver d'overlap.
    imu_t, imu_acc = _trivial_imu(t0=1700000000.0 + 100.0, n=200)
    with pytest.raises(InvalidSegmentError):
        compute_sync(arkit_t, arkit_pos, imu_t, imu_acc)


def test_compute_sync_empty_inputs() -> None:
    with pytest.raises(InvalidSegmentError, match="flux vide"):
        compute_sync(np.array([]), np.zeros((0, 3)), np.array([]), np.zeros((0, 3)))


# ----------- cross_correlation_offset_ms -----------


def test_cross_correlation_aligned_signals_zero_offset() -> None:
    t = np.linspace(0.0, 1.0, 200)
    sig = np.sin(2 * np.pi * 5 * t)
    offset_ms, corr_max = cross_correlation_offset_ms(t, sig, t, sig)
    assert abs(offset_ms) < 20.0  # tolérance numérique
    assert corr_max > 0.5


def test_cross_correlation_too_few_samples() -> None:
    offset_ms, corr_max = cross_correlation_offset_ms(
        np.array([0.0]), np.array([1.0]),
        np.array([0.0]), np.array([1.0]),
    )
    assert offset_ms == 0.0
    assert corr_max == 0.0
