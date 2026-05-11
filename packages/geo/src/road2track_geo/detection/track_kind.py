"""Détection circuit vs spéciale à partir d'une trajectoire ENU.

Heuristique POC (cf. ADR-007) :
- CIRCUIT si la distance start→end est inférieure à `loop_closure_threshold_m`
  ET l'arc total ≥ `min_circuit_arc_length_m`.
- SPECIALE sinon.

Pour un CIRCUIT, on identifie un éventuel "lead-in" : segment initial pendant lequel
l'utilisateur s'approche de la boucle avant d'y entrer. On le tronque pour ne garder
que la boucle elle-même. Pour une SPECIALE, aucune troncature (ADR-016 : l'utilisateur
contrôle les bornes via start/stop).

EKF complet + détection multi-passages → V1.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from road2track_core.entities.track_kind import TrackKind

DEFAULT_LOOP_CLOSURE_THRESHOLD_M: float = 15.0
DEFAULT_MIN_CIRCUIT_ARC_LENGTH_M: float = 50.0
DEFAULT_LEAD_IN_THRESHOLD_M: float = 15.0


def _arc_length_m(positions_enu: NDArray[np.float64]) -> float:
    if positions_enu.shape[0] < 2:
        return 0.0
    diffs = np.diff(positions_enu, axis=0)
    return float(np.linalg.norm(diffs, axis=1).sum())


def detect_track_kind(
    positions_enu: NDArray[np.float64],
    *,
    loop_closure_threshold_m: float = DEFAULT_LOOP_CLOSURE_THRESHOLD_M,
    min_circuit_arc_length_m: float = DEFAULT_MIN_CIRCUIT_ARC_LENGTH_M,
) -> tuple[TrackKind, float]:
    """Classifie une trajectoire ENU en CIRCUIT ou SPECIALE.

    Args:
        positions_enu : (N, 3) positions dans le repère ENU local.
        loop_closure_threshold_m : seuil de proximité start↔end (m).
        min_circuit_arc_length_m : arc minimum pour considérer une boucle comme circuit (m).

    Returns:
        (kind, closure_distance_m) : la distance euclidienne entre la première
        et la dernière position. Pour SPECIALE on retourne quand même la distance
        observée (peut être utile pour les logs/métriques).
    """
    if positions_enu.ndim != 2 or positions_enu.shape[1] != 3:
        raise ValueError(f"positions_enu doit être (N, 3) ; got {positions_enu.shape}")
    if positions_enu.shape[0] < 2:
        return TrackKind.SPECIALE, 0.0

    closure_distance_m = float(np.linalg.norm(positions_enu[-1] - positions_enu[0]))
    arc_length_m = _arc_length_m(positions_enu)

    is_circuit = (
        closure_distance_m < loop_closure_threshold_m and arc_length_m >= min_circuit_arc_length_m
    )
    return (
        TrackKind.CIRCUIT if is_circuit else TrackKind.SPECIALE,
        closure_distance_m,
    )


def find_lead_in_index(
    positions_enu: NDArray[np.float64],
    *,
    lead_in_threshold_m: float = DEFAULT_LEAD_IN_THRESHOLD_M,
) -> int:
    """Premier index dont la position est proche du point final (entrée de la boucle).

    Pour un circuit, l'utilisateur peut commencer à capturer en s'approchant de la
    boucle (lead-in), puis fait un tour et revient près du point d'entrée. Le premier
    index dont la distance au point final est < `lead_in_threshold_m` marque l'entrée
    réelle de la boucle. Tout ce qui précède est lead-in à tronquer.

    Args:
        positions_enu : (N, 3) positions ENU.
        lead_in_threshold_m : rayon de proximité au point final (m).

    Returns:
        Index entier ≥ 0. Si la trajectoire commence déjà près du point final,
        retourne 0 (pas de lead-in à tronquer).
    """
    if positions_enu.ndim != 2 or positions_enu.shape[1] != 3:
        raise ValueError(f"positions_enu doit être (N, 3) ; got {positions_enu.shape}")
    if positions_enu.shape[0] == 0:
        return 0
    end = positions_enu[-1]
    distances = np.linalg.norm(positions_enu - end, axis=1)
    within = np.where(distances < lead_in_threshold_m)[0]
    if within.size == 0:
        return 0
    return int(within[0])
