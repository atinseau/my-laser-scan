"""Parsers JSON pour les formats Record3D et Sensor Logger (POC).

Tolérants : on cherche les champs principaux et on ignore le reste. Le format exact
de ces apps n'est pas formellement documenté, on s'appuie sur observation et
on documentera les écarts observés sur de vraies captures.

Au passage à l'app native (It. 2), un seul flux unifié remplacera ces parsers.

Cf. specs/06-modele-donnees.md §4.2 et ADR-017.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from road2track_core.errors import InvalidSegmentError


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as e:
        raise InvalidSegmentError(f"valeur non numérique: {value!r}") from e


def parse_record3d_poses(
    path: Path,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Parse `record3d/poses.json`.

    Format attendu (tolérant) :
        {
          "frames": [
            {
              "timestamp": 1700000000.123,         # seconds since epoch (UTC)
              "T_world_camera": [16 floats]         # matrice 4x4 row-major
            },
            ...
          ]
        }

    Retourne (timestamps_s, positions_xyz). Position extraite de la 4e colonne
    de la matrice 4x4.
    """
    if not path.is_file():
        raise InvalidSegmentError(f"poses.json introuvable: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    frames = data.get("frames", []) if isinstance(data, dict) else []
    if not frames:
        raise InvalidSegmentError(f"poses.json sans frames: {path}")

    times_list: list[float] = []
    positions_list: list[list[float]] = []
    for f in frames:
        if not isinstance(f, dict):
            continue
        ts_raw = f.get("timestamp", f.get("time"))
        if ts_raw is None:
            raise InvalidSegmentError(f"frame sans timestamp dans {path}")
        transform_raw = f.get("T_world_camera", f.get("transform"))
        if transform_raw is None:
            raise InvalidSegmentError(f"frame sans T_world_camera dans {path}")
        transform = np.asarray(transform_raw, dtype=float).reshape(4, 4)
        times_list.append(_as_float(ts_raw))
        positions_list.append(
            [float(transform[0, 3]), float(transform[1, 3]), float(transform[2, 3])]
        )

    return (
        np.asarray(times_list, dtype=np.float64),
        np.asarray(positions_list, dtype=np.float64),
    )


def parse_sensor_logger_imu(
    path: Path,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Parse `sensor_logger/imu.json` ou `accelerometer.json`.

    Format attendu (tolérant) :
        [
          {"time": 1700000000.123, "x": 0.1, "y": 0.2, "z": 9.8},
          ...
        ]

    Le champ temps peut s'appeler `time`, `timestamp` ou `t`. Les champs
    accélération sont `x`/`y`/`z`. Retourne (timestamps_s, accels_xyz).
    """
    if not path.is_file():
        raise InvalidSegmentError(f"imu file introuvable: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    samples = data if isinstance(data, list) else data.get("samples", [])
    if not samples:
        raise InvalidSegmentError(f"flux IMU vide: {path}")

    times_list: list[float] = []
    accels_list: list[list[float]] = []
    for s in samples:
        if not isinstance(s, dict):
            continue
        ts_raw = s.get("time", s.get("timestamp", s.get("t")))
        if ts_raw is None:
            raise InvalidSegmentError(f"échantillon IMU sans timestamp dans {path}")
        times_list.append(_as_float(ts_raw))
        accels_list.append(
            [
                _as_float(s.get("x", 0.0)),
                _as_float(s.get("y", 0.0)),
                _as_float(s.get("z", 0.0)),
            ]
        )

    return (
        np.asarray(times_list, dtype=np.float64),
        np.asarray(accels_list, dtype=np.float64),
    )


def find_imu_file(local_dir: Path) -> Path:
    """Localise le fichier IMU Sensor Logger (variante imu.json / accelerometer.json)."""
    sensor_dir = local_dir / "sensor_logger"
    for name in ("imu.json", "accelerometer.json"):
        candidate = sensor_dir / name
        if candidate.is_file():
            return candidate
    raise InvalidSegmentError(
        f"aucun fichier IMU (imu.json ou accelerometer.json) dans {sensor_dir}"
    )
