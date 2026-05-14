"""Génère une capture synthétique "Record3D + Sensor Logger" pour les tests E2E.

Crée un dossier complet avec :
- `record3d/video.mp4` (ffmpeg lavfi smptebars).
- `record3d/poses.json` : N poses ARKit le long d'une trajectoire (boucle fermée par défaut).
- `record3d/metadata.json` : intrinsics iPhone simulées.
- `sensor_logger/imu.json` : échantillons IMU à 100 Hz alignés sur la durée.
- `sensor_logger/gps.json` : fixes GPS à 5 Hz avec HDOP valide.

Permet de tester `ingest_session` → `fuse_sensors` → `detect_kind_and_trim` →
`select_keyframes` end-to-end sans avoir besoin d'une vraie capture iPhone.

Le résultat est déterministe (seed fixe) — utile pour des assertions reproductibles.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class SyntheticCaptureSpec:
    """Paramètres d'une capture synthétique."""

    duration_s: float = 5.0
    video_fps: int = 30
    video_width: int = 320
    video_height: int = 240
    n_arkit_poses: int = 150  # ARKit ≈ 30 Hz
    n_imu_samples: int = 500  # IMU ≈ 100 Hz
    n_gps_fixes: int = 25  # GPS ≈ 5 Hz
    trajectory_kind: str = "circuit"  # "circuit" | "speciale"
    arc_length_m: float = 60.0
    origin_lat: float = 45.0
    origin_lon: float = 6.0
    origin_alt: float = 100.0
    start_utc: float = 1_700_000_000.0
    seed: int = 0


def _generate_trajectory(
    n: int, length_m: float, *, kind: str
) -> np.ndarray:
    """Polyline 3D (Z = 0). 'circuit' = cercle fermé, 'speciale' = ligne droite."""
    if kind == "circuit":
        radius = length_m / (2.0 * math.pi)
        thetas = np.linspace(0.0, 2.0 * math.pi, n, endpoint=True)
        pts = np.zeros((n, 3))
        pts[:, 0] = radius * np.cos(thetas) - radius  # start at (0,0,0)
        pts[:, 1] = radius * np.sin(thetas)
        return pts
    if kind == "speciale":
        pts = np.zeros((n, 3))
        pts[:, 0] = np.linspace(0.0, length_m, n)
        return pts
    raise ValueError(f"trajectory_kind doit être 'circuit' | 'speciale' ; got {kind}")


def _identity_pose_matrix(translation: np.ndarray) -> list[float]:
    """4×4 row-major flatten : I_3 dans le bloc rotation + translation."""
    m = np.eye(4)
    m[0:3, 3] = translation
    return m.flatten().tolist()


def _write_video(path: Path, spec: SyntheticCaptureSpec) -> None:
    """ffmpeg lavfi → vidéo smptebars 5s. Lève RuntimeError si ffmpeg absent."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg requis pour générer la vidéo synthétique")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"smptebars=duration={spec.duration_s}"
            f":size={spec.video_width}x{spec.video_height}"
            f":rate={spec.video_fps}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def write_synthetic_capture(
    output_dir: Path, spec: SyntheticCaptureSpec | None = None
) -> Path:
    """Génère une capture complète dans `output_dir`. Retourne le chemin du dossier."""
    spec = spec or SyntheticCaptureSpec()
    output_dir.mkdir(parents=True, exist_ok=True)
    record3d_dir = output_dir / "record3d"
    sensor_logger_dir = output_dir / "sensor_logger"
    record3d_dir.mkdir(parents=True, exist_ok=True)
    sensor_logger_dir.mkdir(parents=True, exist_ok=True)

    _write_video(record3d_dir / "video.mp4", spec)

    # Trajectory dans le repère ARKit (X=est local, Y=nord, Z=0 pour POC).
    trajectory = _generate_trajectory(
        spec.n_arkit_poses, spec.arc_length_m, kind=spec.trajectory_kind
    )
    arkit_t = np.linspace(spec.start_utc, spec.start_utc + spec.duration_s, spec.n_arkit_poses)
    poses = {
        "frames": [
            {
                "timestamp": float(arkit_t[i]),
                "T_world_camera": _identity_pose_matrix(trajectory[i]),
            }
            for i in range(spec.n_arkit_poses)
        ]
    }
    (record3d_dir / "poses.json").write_text(
        json.dumps(poses), encoding="utf-8"
    )

    # metadata.json — intrinsics iPhone 14 Pro mises à l'échelle.
    fx = fy = 1500.0 * (spec.video_width / 1920)
    cx = spec.video_width / 2
    cy = spec.video_height / 2
    (record3d_dir / "metadata.json").write_text(
        json.dumps(
            {
                "fps": spec.video_fps,
                "w": spec.video_width,
                "h": spec.video_height,
                "K": [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0],
            }
        ),
        encoding="utf-8",
    )

    # IMU — accélération bruitée autour de g vertical.
    rng = np.random.default_rng(spec.seed)
    imu_t = np.linspace(
        spec.start_utc, spec.start_utc + spec.duration_s, spec.n_imu_samples
    )
    imu_samples = [
        {
            "time": float(imu_t[i]),
            "x": float(rng.normal(0.0, 0.1)),
            "y": float(rng.normal(0.0, 0.1)),
            "z": float(9.81 + rng.normal(0.0, 0.05)),
        }
        for i in range(spec.n_imu_samples)
    ]
    (sensor_logger_dir / "imu.json").write_text(
        json.dumps(imu_samples), encoding="utf-8"
    )

    # GPS — convertit trajectory ENU → WGS84 approximatif (flat-earth).
    cos_lat = math.cos(math.radians(spec.origin_lat))
    deg_per_m_lat = 180.0 / (math.pi * 6_371_000.0)
    deg_per_m_lon = deg_per_m_lat / max(cos_lat, 1e-6)
    gps_t = np.linspace(
        spec.start_utc, spec.start_utc + spec.duration_s, spec.n_gps_fixes
    )
    gps_traj_indices = np.linspace(
        0, spec.n_arkit_poses - 1, spec.n_gps_fixes
    ).astype(int)
    gps_samples = []
    for i in range(spec.n_gps_fixes):
        east, north, _up = trajectory[gps_traj_indices[i]]
        lat = spec.origin_lat + north * deg_per_m_lat
        lon = spec.origin_lon + east * deg_per_m_lon
        gps_samples.append(
            {
                "time": float(gps_t[i]),
                "latitude": float(lat),
                "longitude": float(lon),
                "altitude": float(spec.origin_alt),
                "horizontalAccuracy": 5.0,
            }
        )
    (sensor_logger_dir / "gps.json").write_text(
        json.dumps(gps_samples), encoding="utf-8"
    )

    return output_dir
