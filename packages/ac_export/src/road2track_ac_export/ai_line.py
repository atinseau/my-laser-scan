"""Génération de `fast_lane.ai` pour Assetto Corsa.

Format propriétaire AC (rétro-engineered par la communauté) :

    int32   header_version  (= 7 chez AC, parfois 8)
    int32   detail (n_points)
    int32   lap_time_ms     (0 si inconnu)
    int32   sample_count (== detail)
    AiPoint[detail] {
        float3 pos_world             (12 bytes)
        float length_along           (4)
        float id                     (4) — interpolation t
    }
    AiExtra[detail] {
        float3 normal_or_direction   (12) — laissé à 0 pour POC
        float3 grass_left            (12)
        float3 grass_right           (12)
        float  side_left             (4)
        float  side_right            (4)
        float  unknown1              (4)  — souvent grip
        float  unknown2              (4)
        float  unknown3              (4)
    }

POC : on remplit `pos_world` + `length_along` + `id`. Le reste = 0.
ksEditor accepte cette version "dégradée" pour un AI minimal — la voiture
suivra une trajectoire mais sans informations de side bounds (les bots
peuvent sortir du circuit, OK pour POC mono-joueur).

Cf. https://www.assettocorsa.net/forum/index.php?threads/ai-line-format.30843/
et `pyfast_lane_ai` (open source) pour référence.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

_HEADER_VERSION: int = 7
_AI_POINT_STRUCT = struct.Struct("<3f f f")  # 20 bytes
_AI_EXTRA_STRUCT = struct.Struct("<3f 3f 3f f f f f f")  # 56 bytes


@dataclass(frozen=True)
class AiLineResult:
    fast_lane_path: Path
    n_waypoints: int
    total_length_m: float


def _resample_arc_length(
    positions: NDArray[np.float64], target_spacing_m: float
) -> NDArray[np.float64]:
    """Ré-échantillonne une polyline à pas constant en arc length."""
    if positions.shape[0] < 2:
        return positions.copy()
    diffs = np.diff(positions, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total = float(arc[-1])
    if total <= 0.0:
        return positions[:1].copy()
    n_samples = max(2, int(np.ceil(total / target_spacing_m)) + 1)
    target_arc = np.linspace(0.0, total, n_samples)
    return np.stack(
        [np.interp(target_arc, arc, positions[:, i]) for i in range(3)], axis=1
    )


def write_fast_lane_ai(
    output_path: Path,
    positions: NDArray[np.float64],
    *,
    target_spacing_m: float = 2.0,
) -> AiLineResult:
    """Sérialise un `fast_lane.ai` minimal depuis une polyline 3D.

    Args:
        output_path : chemin de sortie (typiquement `ai/fast_lane.ai`).
        positions : (N, 3) trajectoire ENU (y axe up, z avant pour AC).
        target_spacing_m : ré-échantillonnage uniforme tous les X mètres.

    Returns:
        AiLineResult avec le chemin produit + nombre de waypoints + longueur.
    """
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError(f"positions doit être (N, 3) ; got {positions.shape}")
    if positions.shape[0] < 2:
        raise ValueError("au moins 2 points requis pour une AI line")

    resampled = _resample_arc_length(positions, target_spacing_m)
    n = resampled.shape[0]
    seg = np.linalg.norm(np.diff(resampled, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    total_length = float(arc[-1])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    denom = max(1, n - 1)
    with output_path.open("wb") as f:
        f.write(struct.pack("<i", _HEADER_VERSION))
        f.write(struct.pack("<i", n))
        f.write(struct.pack("<i", 0))  # lap_time_ms inconnu
        f.write(struct.pack("<i", n))
        for i in range(n):
            x, y, z = resampled[i]
            f.write(
                _AI_POINT_STRUCT.pack(
                    float(x), float(y), float(z), float(arc[i]), float(i / denom)
                )
            )
        for _ in range(n):
            # Tous les champs extras à zéro (POC).
            f.write(_AI_EXTRA_STRUCT.pack(*([0.0] * 14)))

    return AiLineResult(
        fast_lane_path=output_path,
        n_waypoints=n,
        total_length_m=total_length,
    )
