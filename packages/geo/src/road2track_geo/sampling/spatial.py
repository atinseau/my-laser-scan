"""Sampling spatial : sélectionne des indices le long d'une trajectoire ENU.

Critère : conserve un échantillon tous les `min_spacing_m` mètres parcourus.
Utilisé par `select_keyframes` pour le filtrage de diversité spatiale
(cf. specs/04-pipeline-ml.md §3.1).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

DEFAULT_MIN_SPACING_M: float = 0.5


def select_indices_by_spacing(
    positions_enu: NDArray[np.float64],
    *,
    min_spacing_m: float = DEFAULT_MIN_SPACING_M,
) -> NDArray[np.int64]:
    """Sélectionne les indices à intervalle ≥ `min_spacing_m` le long d'une trajectoire.

    Algorithme greedy : on retient le premier point puis chaque point dont la
    distance euclidienne au dernier retenu est ≥ `min_spacing_m`.

    Args:
        positions_enu : (N, 3) positions dans le repère ENU local.
        min_spacing_m : distance minimum entre deux échantillons retenus (m).

    Returns:
        Tableau croissant d'indices entiers (référents à `positions_enu`).
        Vide si l'entrée est vide.
    """
    if positions_enu.ndim != 2 or positions_enu.shape[1] != 3:
        raise ValueError(f"positions_enu doit être (N, 3) ; got {positions_enu.shape}")
    if positions_enu.shape[0] == 0:
        return np.array([], dtype=np.int64)

    selected: list[int] = [0]
    last_pos = positions_enu[0]
    for i in range(1, positions_enu.shape[0]):
        if float(np.linalg.norm(positions_enu[i] - last_pos)) >= min_spacing_m:
            selected.append(i)
            last_pos = positions_enu[i]
    return np.asarray(selected, dtype=np.int64)
