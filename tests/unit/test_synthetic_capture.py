"""Tests sur la fixture `synthetic_capture`."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from tests.fixtures.synthetic_capture import (
    SyntheticCaptureSpec,
    _generate_trajectory,
    _identity_pose_matrix,
    write_synthetic_capture,
)

_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def test_generate_trajectory_circuit_is_closed() -> None:
    pts = _generate_trajectory(100, length_m=60.0, kind="circuit")
    assert pts.shape == (100, 3)
    # endpoint == startpoint (boucle).
    np.testing.assert_array_almost_equal(pts[0], pts[-1], decimal=5)
    # arc length ≈ 60 m.
    arc = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    assert arc == pytest.approx(60.0, rel=0.05)


def test_generate_trajectory_speciale_is_straight() -> None:
    pts = _generate_trajectory(50, length_m=30.0, kind="speciale")
    assert pts[0, 0] == pytest.approx(0.0)
    assert pts[-1, 0] == pytest.approx(30.0)
    # ligne droite : tous les Y et Z = 0.
    assert np.all(pts[:, 1] == 0.0)
    assert np.all(pts[:, 2] == 0.0)


def test_generate_trajectory_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="trajectory_kind"):
        _generate_trajectory(10, length_m=10.0, kind="banana")


def test_identity_pose_matrix_translation_only() -> None:
    flat = _identity_pose_matrix(np.array([1.5, 2.5, 3.5]))
    assert len(flat) == 16
    m = np.asarray(flat).reshape(4, 4)
    np.testing.assert_array_almost_equal(m[0:3, 0:3], np.eye(3))
    np.testing.assert_array_almost_equal(m[0:3, 3], [1.5, 2.5, 3.5])


@pytest.mark.skipif(not _FFMPEG_AVAILABLE, reason="ffmpeg indisponible")
def test_write_synthetic_capture_layout(tmp_path: Path) -> None:
    spec = SyntheticCaptureSpec(n_arkit_poses=20, n_imu_samples=50, n_gps_fixes=10)
    out = write_synthetic_capture(tmp_path / "cap", spec)
    assert (out / "record3d" / "video.mp4").is_file()
    assert (out / "record3d" / "poses.json").is_file()
    assert (out / "record3d" / "metadata.json").is_file()
    assert (out / "sensor_logger" / "imu.json").is_file()
    assert (out / "sensor_logger" / "gps.json").is_file()

    poses = json.loads((out / "record3d" / "poses.json").read_text(encoding="utf-8"))
    assert len(poses["frames"]) == 20
    assert "timestamp" in poses["frames"][0]
    assert len(poses["frames"][0]["T_world_camera"]) == 16

    metadata = json.loads((out / "record3d" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["w"] == spec.video_width

    imu = json.loads((out / "sensor_logger" / "imu.json").read_text(encoding="utf-8"))
    assert len(imu) == 50
    # Accélération autour de g vertical (Z).
    assert abs(imu[0]["z"] - 9.81) < 0.5

    gps = json.loads((out / "sensor_logger" / "gps.json").read_text(encoding="utf-8"))
    assert len(gps) == 10
    # HDOP valide (< 10).
    assert gps[0]["horizontalAccuracy"] < 10.0
    # Latitude proche de l'origine.
    assert abs(gps[0]["latitude"] - 45.0) < 0.01


@pytest.mark.skipif(not _FFMPEG_AVAILABLE, reason="ffmpeg indisponible")
def test_synthetic_capture_speciale_kind(tmp_path: Path) -> None:
    spec = SyntheticCaptureSpec(
        n_arkit_poses=10,
        n_imu_samples=20,
        n_gps_fixes=5,
        trajectory_kind="speciale",
        arc_length_m=50.0,
    )
    out = write_synthetic_capture(tmp_path / "cap", spec)
    poses = json.loads((out / "record3d" / "poses.json").read_text(encoding="utf-8"))
    # Premier et dernier T_world_camera : translation différente (pas une boucle).
    first_t = poses["frames"][0]["T_world_camera"][3]
    last_t = poses["frames"][-1]["T_world_camera"][3]
    assert math.isclose(first_t, 0.0)
    assert math.isclose(last_t, 50.0, rel_tol=1e-3)
