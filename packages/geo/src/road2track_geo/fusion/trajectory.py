"""Fusion ARKit + GPS → trajectoire ENU géoréférencée (POC).

Approche pragmatique pour l'It. 0 (cf. specs/04-pipeline-ml.md §2.2) :
- Choix de l'origine ENU : premier fix GPS valide (HDOP < seuil).
- Conversion GPS WGS84 → ENU local via approximation flat-earth.
- Alignement rigide (Kabsch) entre les positions ARKit (interpolées aux timestamps GPS)
  et les positions GPS-ENU correspondantes : trouve la rotation + translation qui
  minimise l'écart aux moindres carrés.
- Application de la transformation aux poses ARKit complètes → trajectoire fusionnée
  dans le repère ENU absolu.

Pas d'EKF complet ici : c'est suffisant pour démarrer l'aval (tuilage, sélection
keyframes). L'EKF avec biais IMU + RTS smoothing viendra en V1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from road2track_core.errors import InvalidSegmentError
from scipy.spatial.transform import Rotation

from road2track_geo.projections.wgs84 import wgs84_array_to_enu_flat

DEFAULT_HDOP_THRESHOLD_M: float = 10.0
MIN_GPS_FIXES_FOR_ALIGNMENT: int = 3


@dataclass(frozen=True)
class FusedTrajectory:
    """Sortie de fuse_trajectory.

    - times_s : timestamps UTC (secondes) des poses, taille N.
    - positions_enu : (N, 3), repère ENU centré sur origin_wgs84.
    - quaternions_wxyz : (N, 4) en convention w,x,y,z (cohérent avec FusedPose).
    - origin_wgs84 : (lat, lon, alt) de l'origine ENU choisie.
    - origin_t : timestamp UTC du fix GPS choisi comme origine.
    - rmse_m : erreur quadratique moyenne de l'alignement Kabsch.
    - n_gps_fixes_used : nombre de fixes GPS utilisés pour l'alignement.
    """

    times_s: NDArray[np.float64]
    positions_enu: NDArray[np.float64]
    quaternions_wxyz: NDArray[np.float64]
    origin_wgs84: tuple[float, float, float]
    origin_t: float
    rmse_m: float
    n_gps_fixes_used: int


def find_origin_gps(
    gps_times_s: NDArray[np.float64],
    gps_lats: NDArray[np.float64],
    gps_lons: NDArray[np.float64],
    gps_alts: NDArray[np.float64],
    gps_hdops: NDArray[np.float64],
    hdop_threshold_m: float = DEFAULT_HDOP_THRESHOLD_M,
) -> tuple[float, float, float, float]:
    """Sélectionne le **premier fix GPS valide** (HDOP < seuil).

    Retourne (t, lat, lon, alt). Lève InvalidSegmentError si aucun fix valide.
    """
    if gps_times_s.size == 0:
        raise InvalidSegmentError("flux GPS vide pour le choix de l'origine ENU")
    valid_mask = gps_hdops <= hdop_threshold_m
    if not valid_mask.any():
        raise InvalidSegmentError(
            f"aucun fix GPS avec HDOP < {hdop_threshold_m} m ; "
            "réessaie en environnement plus ouvert ou augmente le seuil."
        )
    idx = int(np.argmax(valid_mask))
    return (
        float(gps_times_s[idx]),
        float(gps_lats[idx]),
        float(gps_lons[idx]),
        float(gps_alts[idx]),
    )


def kabsch_align(
    src: NDArray[np.float64], tgt: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    """Calcule (R, t, rmse) tels que `R @ src.T + t` minimise ||R @ src + t - tgt||².

    Args:
        src : (N, 3) points source.
        tgt : (N, 3) points cible (même ordre/correspondance).

    Returns:
        rot : matrice 3x3 de rotation.
        translation : vecteur 3 de translation.
        rmse : erreur quadratique moyenne après alignement.
    """
    if src.shape != tgt.shape or src.shape[1] != 3:
        raise ValueError(f"src et tgt doivent être de forme (N, 3) ; got {src.shape}, {tgt.shape}")
    if src.shape[0] < MIN_GPS_FIXES_FOR_ALIGNMENT:
        raise InvalidSegmentError(
            f"alignement Kabsch nécessite ≥ {MIN_GPS_FIXES_FOR_ALIGNMENT} points "
            f"(got {src.shape[0]})"
        )

    src_centroid = src.mean(axis=0)
    tgt_centroid = tgt.mean(axis=0)
    src_centered = src - src_centroid
    tgt_centered = tgt - tgt_centroid

    # scipy.spatial.transform.Rotation.align_vectors : minimise ||R @ src_i - tgt_i||².
    # Sans `return_sensitivity=True` la signature retourne (Rotation, float),
    # mais le stub déclare une union. On extrait les deux premiers éléments.
    aligned = Rotation.align_vectors(tgt_centered, src_centered)
    rot, rmsd = aligned[0], float(aligned[1])
    rot_matrix = rot.as_matrix()
    translation = tgt_centroid - rot_matrix @ src_centroid
    return rot_matrix, translation, float(rmsd)


def _interp_positions(
    target_t: NDArray[np.float64],
    source_t: NDArray[np.float64],
    source_pos: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Interpolation linéaire d'une trajectoire 3D à des timestamps cibles."""
    return np.stack(
        [np.interp(target_t, source_t, source_pos[:, i]) for i in range(3)],
        axis=1,
    )


def fuse_trajectory(
    arkit_times_s: NDArray[np.float64],
    arkit_positions: NDArray[np.float64],
    arkit_quaternions_wxyz: NDArray[np.float64],
    gps_times_s: NDArray[np.float64],
    gps_lats: NDArray[np.float64],
    gps_lons: NDArray[np.float64],
    gps_alts: NDArray[np.float64],
    gps_hdops: NDArray[np.float64],
    hdop_threshold_m: float = DEFAULT_HDOP_THRESHOLD_M,
) -> FusedTrajectory:
    """Fusion ARKit + GPS → trajectoire ENU géoréférencée.

    Stratégie :
    1. Trouve l'origine ENU (premier fix GPS valide).
    2. Filtre les fixes GPS valides qui chevauchent ARKit dans le temps.
    3. Convertit GPS → ENU local centré sur l'origine.
    4. Interpole les positions ARKit aux timestamps GPS pour obtenir des correspondances.
    5. Calcule la transformation rigide (Kabsch) qui aligne ARKit → GPS-ENU.
    6. Applique la transformation à toutes les poses ARKit (positions + rotations).
    """
    if arkit_times_s.size == 0:
        raise InvalidSegmentError("flux ARKit vide pour la fusion")

    origin_t, origin_lat, origin_lon, origin_alt = find_origin_gps(
        gps_times_s, gps_lats, gps_lons, gps_alts, gps_hdops, hdop_threshold_m
    )

    # 2. Garde les fixes GPS valides ET dans la fenêtre ARKit.
    valid = gps_hdops <= hdop_threshold_m
    in_window = (gps_times_s >= float(arkit_times_s.min())) & (
        gps_times_s <= float(arkit_times_s.max())
    )
    keep = valid & in_window
    n_keep = int(keep.sum())
    if n_keep < MIN_GPS_FIXES_FOR_ALIGNMENT:
        raise InvalidSegmentError(
            f"seulement {n_keep} fixes GPS valides chevauchent les poses ARKit "
            f"(< {MIN_GPS_FIXES_FOR_ALIGNMENT} requis pour l'alignement Kabsch)"
        )

    gps_t_keep = gps_times_s[keep]
    gps_enu = wgs84_array_to_enu_flat(
        gps_lats[keep], gps_lons[keep], gps_alts[keep], origin_lat, origin_lon, origin_alt
    )

    # 4. Interpoler les positions ARKit aux timestamps GPS.
    arkit_at_gps = _interp_positions(gps_t_keep, arkit_times_s, arkit_positions)

    # 5. Kabsch.
    rot_matrix, translation, rmse = kabsch_align(arkit_at_gps, gps_enu)

    # 6. Application aux poses complètes.
    fused_positions = arkit_positions @ rot_matrix.T + translation

    # Rotations : composition globale × rotations ARKit.
    # Convention scipy : quat = (x, y, z, w), nous stockons (w, x, y, z).
    rot_global = Rotation.from_matrix(rot_matrix)
    arkit_quat_xyzw = arkit_quaternions_wxyz[:, [1, 2, 3, 0]]
    arkit_rot = Rotation.from_quat(arkit_quat_xyzw)
    fused_rot = rot_global * arkit_rot
    fused_quat_xyzw = fused_rot.as_quat()
    fused_quat_wxyz = fused_quat_xyzw[:, [3, 0, 1, 2]]

    return FusedTrajectory(
        times_s=arkit_times_s.copy(),
        positions_enu=fused_positions,
        quaternions_wxyz=fused_quat_wxyz,
        origin_wgs84=(origin_lat, origin_lon, origin_alt),
        origin_t=origin_t,
        rmse_m=rmse,
        n_gps_fixes_used=n_keep,
    )
