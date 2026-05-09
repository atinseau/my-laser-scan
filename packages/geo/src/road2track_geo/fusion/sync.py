"""Synchronisation Record3D ARKit ↔ Sensor Logger IMU.

Cf. specs/04-pipeline-ml.md §2.1 (étape 2) et ADR-017.

Stratégie :
1. Si l'écart UTC entre les premiers timestamps est < 100 ms → on assume aligné.
2. Sinon, cross-corrélation entre la magnitude de l'accélération IMU et la magnitude
   de la dérivée seconde de la position ARKit.
   - Amplitude max < 0.3 → fallback offset = 0 (warning).
   - Offset > 5 s → erreur fatale (incohérence majeure).
   - Sinon → on retourne l'offset à appliquer.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from road2track_core.entities.refs import SyncResult
from road2track_core.errors import InvalidSegmentError
from scipy.signal import correlate

# Seuils par défaut, alignés avec specs/04-pipeline-ml.md §2.1bis.
UTC_DRIFT_THRESHOLD_MS: float = 100.0
CORRELATION_THRESHOLD: float = 0.3
MAX_OFFSET_S: float = 5.0
RESAMPLE_HZ: float = 100.0


def cross_correlation_offset_ms(
    sig_a_t: NDArray[np.float64],
    sig_a_v: NDArray[np.float64],
    sig_b_t: NDArray[np.float64],
    sig_b_v: NDArray[np.float64],
    target_hz: float = RESAMPLE_HZ,
) -> tuple[float, float]:
    """Cross-corrèle deux signaux scalaires irréguliers.

    Étapes :
    1. Détermine la fenêtre temporelle commune.
    2. Rééchantillonne les deux signaux sur une grille `target_hz` par interpolation linéaire.
    3. Centre et normalise.
    4. Cross-corrèle (`scipy.signal.correlate`, mode 'same').
    5. Le pic donne l'offset à appliquer à `sig_b` pour l'aligner sur `sig_a`.

    Retourne (offset_ms, correlation_max). `correlation_max` est dans [0, 1] après normalisation.
    """
    if sig_a_t.size < 2 or sig_b_t.size < 2:
        return 0.0, 0.0

    t_start = float(max(sig_a_t.min(), sig_b_t.min()))
    t_end = float(min(sig_a_t.max(), sig_b_t.max()))
    if t_end <= t_start:
        return 0.0, 0.0

    n_samples = int((t_end - t_start) * target_hz)
    if n_samples < 4:
        return 0.0, 0.0

    t_grid = np.linspace(t_start, t_end, n_samples)
    a = np.interp(t_grid, sig_a_t, sig_a_v)
    b = np.interp(t_grid, sig_b_t, sig_b_v)

    # Centrage + normalisation pour avoir une corrélation entre [-1, 1].
    a_n = (a - a.mean()) / (a.std() + 1e-9)
    b_n = (b - b.mean()) / (b.std() + 1e-9)

    corr = correlate(a_n, b_n, mode="same")
    corr_normalized = corr / max(len(a_n), 1)

    abs_corr = np.abs(corr_normalized)
    peak_idx = int(np.argmax(abs_corr))
    n_center = len(corr_normalized) // 2
    offset_samples = peak_idx - n_center
    offset_seconds = offset_samples / target_hz
    return offset_seconds * 1000.0, float(abs_corr.max())


def compute_sync(
    arkit_times_s: NDArray[np.float64],
    arkit_positions: NDArray[np.float64],
    imu_times_s: NDArray[np.float64],
    imu_accelerations: NDArray[np.float64],
) -> SyncResult:
    """Calcule la synchro entre les flux Record3D ARKit et Sensor Logger IMU.

    Args:
        arkit_times_s : timestamps UTC des poses ARKit, shape (N,).
        arkit_positions : positions XYZ extraites des poses, shape (N, 3).
        imu_times_s : timestamps UTC IMU, shape (M,).
        imu_accelerations : accélérations XYZ IMU, shape (M, 3).

    Returns:
        SyncResult.

    Raises:
        InvalidSegmentError : si l'offset détecté > MAX_OFFSET_S.
    """
    if arkit_times_s.size == 0 or imu_times_s.size == 0:
        raise InvalidSegmentError("flux vide pour la synchronisation")

    drift_ms = float((imu_times_s[0] - arkit_times_s[0]) * 1000.0)

    if abs(drift_ms) <= UTC_DRIFT_THRESHOLD_MS:
        return SyncResult(
            drift_ms=drift_ms,
            offset_applied_ms=0.0,
            method="utc_aligned",
            correlation_max=0.0,
            warning=None,
        )

    # Vérification d'overlap temporel : si les deux flux ne se chevauchent pas du
    # tout, on ne peut rien synchroniser. C'est plus grave qu'un mauvais
    # offset — l'utilisateur a probablement enregistré les deux apps à des moments
    # disjoints.
    overlap_start = float(max(arkit_times_s[0], imu_times_s[0]))
    overlap_end = float(min(arkit_times_s[-1], imu_times_s[-1]))
    if overlap_end <= overlap_start:
        raise InvalidSegmentError(
            "aucun chevauchement temporel entre les flux Record3D et Sensor Logger "
            f"(drift {drift_ms:.0f} ms) ; vérifie que les deux apps tournent au "
            "même moment sur l'iPhone."
        )

    # Cross-corrélation : magnitude de la dérivée seconde des positions ARKit
    # vs magnitude de l'accélération IMU.
    if arkit_positions.shape[0] < 3:
        # Pas assez de points pour calculer la 2nde dérivée.
        return SyncResult(
            drift_ms=drift_ms,
            offset_applied_ms=0.0,
            method="fallback_zero",
            correlation_max=0.0,
            warning="trop peu de poses ARKit pour cross-corrélation",
        )

    arkit_accel = np.linalg.norm(np.diff(arkit_positions, n=2, axis=0), axis=1)
    arkit_accel_t = arkit_times_s[1:-1]
    imu_mag = np.linalg.norm(imu_accelerations, axis=1)

    offset_ms, corr_max = cross_correlation_offset_ms(
        arkit_accel_t, arkit_accel, imu_times_s, imu_mag
    )

    if abs(offset_ms) > MAX_OFFSET_S * 1000.0:
        raise InvalidSegmentError(
            f"sync offset {offset_ms:.0f} ms > {MAX_OFFSET_S} s, "
            "incohérence majeure entre Record3D et Sensor Logger ; "
            "vérifie que tu as démarré les deux apps simultanément."
        )

    if corr_max < CORRELATION_THRESHOLD:
        return SyncResult(
            drift_ms=drift_ms,
            offset_applied_ms=0.0,
            method="fallback_zero",
            correlation_max=corr_max,
            warning=(
                f"corrélation max {corr_max:.2f} < seuil {CORRELATION_THRESHOLD} "
                "(probablement utilisateur statique au début) ; on assume UTC alignés"
            ),
        )

    return SyncResult(
        drift_ms=drift_ms,
        offset_applied_ms=offset_ms,
        method="cross_correlation",
        correlation_max=corr_max,
        warning=None,
    )
