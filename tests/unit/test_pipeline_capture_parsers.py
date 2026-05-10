"""Tests sur les parsers Record3D + Sensor Logger (POC)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from road2track_core.errors import InvalidSegmentError
from road2track_pipeline.activities._capture_parsers import (
    find_imu_file,
    parse_record3d_poses,
    parse_sensor_logger_imu,
)


def _identity_pose(tx: float, ty: float, tz: float) -> list[float]:
    """Matrice 4x4 row-major avec une translation donnée."""
    return [
        1.0, 0.0, 0.0, tx,
        0.0, 1.0, 0.0, ty,
        0.0, 0.0, 1.0, tz,
        0.0, 0.0, 0.0, 1.0,
    ]


def test_parse_record3d_poses_extracts_xyz(tmp_path: Path) -> None:
    poses = {
        "frames": [
            {"timestamp": 1700000000.0, "T_world_camera": _identity_pose(1.0, 2.0, 3.0)},
            {"timestamp": 1700000000.5, "T_world_camera": _identity_pose(1.5, 2.5, 3.5)},
        ]
    }
    path = tmp_path / "poses.json"
    path.write_text(json.dumps(poses), encoding="utf-8")

    times, positions = parse_record3d_poses(path)

    assert times.tolist() == [1700000000.0, 1700000000.5]
    np.testing.assert_array_almost_equal(positions[0], [1.0, 2.0, 3.0])
    np.testing.assert_array_almost_equal(positions[1], [1.5, 2.5, 3.5])


def test_parse_record3d_poses_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InvalidSegmentError, match="introuvable"):
        parse_record3d_poses(tmp_path / "nope.json")


def test_parse_record3d_poses_empty_frames(tmp_path: Path) -> None:
    path = tmp_path / "poses.json"
    path.write_text(json.dumps({"frames": []}), encoding="utf-8")
    with pytest.raises(InvalidSegmentError, match="sans frames"):
        parse_record3d_poses(path)


def test_parse_record3d_poses_missing_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "poses.json"
    path.write_text(
        json.dumps({"frames": [{"T_world_camera": _identity_pose(0, 0, 0)}]}),
        encoding="utf-8",
    )
    with pytest.raises(InvalidSegmentError, match="sans timestamp"):
        parse_record3d_poses(path)


def test_parse_sensor_logger_imu_top_level_array(tmp_path: Path) -> None:
    samples = [
        {"time": 1700000000.0, "x": 0.1, "y": 0.2, "z": 9.8},
        {"time": 1700000000.005, "x": 0.2, "y": 0.3, "z": 9.81},
    ]
    path = tmp_path / "imu.json"
    path.write_text(json.dumps(samples), encoding="utf-8")

    times, accels = parse_sensor_logger_imu(path)

    assert times.tolist() == [1700000000.0, 1700000000.005]
    np.testing.assert_array_almost_equal(accels[1], [0.2, 0.3, 9.81])


def test_parse_sensor_logger_imu_supports_timestamp_key(tmp_path: Path) -> None:
    samples = [{"timestamp": 1.0, "x": 0.0, "y": 0.0, "z": 0.0}]
    path = tmp_path / "imu.json"
    path.write_text(json.dumps(samples), encoding="utf-8")
    times, _ = parse_sensor_logger_imu(path)
    assert times.tolist() == [1.0]


def test_parse_sensor_logger_imu_empty(tmp_path: Path) -> None:
    path = tmp_path / "imu.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(InvalidSegmentError, match="vide"):
        parse_sensor_logger_imu(path)


def test_find_imu_file_imu_json(tmp_path: Path) -> None:
    sensor_dir = tmp_path / "sensor_logger"
    sensor_dir.mkdir()
    target = sensor_dir / "imu.json"
    target.write_text("[]", encoding="utf-8")
    assert find_imu_file(tmp_path) == target


def test_find_imu_file_accelerometer_fallback(tmp_path: Path) -> None:
    sensor_dir = tmp_path / "sensor_logger"
    sensor_dir.mkdir()
    target = sensor_dir / "accelerometer.json"
    target.write_text("[]", encoding="utf-8")
    assert find_imu_file(tmp_path) == target


def test_find_imu_file_missing(tmp_path: Path) -> None:
    (tmp_path / "sensor_logger").mkdir()
    with pytest.raises(InvalidSegmentError, match="aucun fichier IMU"):
        find_imu_file(tmp_path)
