"""Tests sur la génération `fast_lane.ai` (format binaire AC simplifié)."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from road2track_ac_export.ai_line import (
    _AI_EXTRA_STRUCT,
    _AI_POINT_STRUCT,
    _resample_arc_length,
    write_fast_lane_ai,
)


def test_resample_arc_length_uniform_line() -> None:
    pts = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    out = _resample_arc_length(pts, target_spacing_m=2.0)
    # 10 m / 2 m → ≥ 6 points (incluant les extrémités).
    assert out.shape[0] >= 6
    assert out[0, 0] == pytest.approx(0.0)
    assert out[-1, 0] == pytest.approx(10.0)


def test_resample_arc_length_handles_short_input() -> None:
    pts = np.array([[1.0, 2.0, 3.0]])
    out = _resample_arc_length(pts, target_spacing_m=2.0)
    np.testing.assert_array_equal(out, pts)


def test_write_fast_lane_ai_header_and_count(tmp_path: Path) -> None:
    pts = np.zeros((100, 3))
    pts[:, 0] = np.linspace(0.0, 50.0, 100)
    out = tmp_path / "fast_lane.ai"
    result = write_fast_lane_ai(out, pts, target_spacing_m=2.0)
    assert out.is_file()
    raw = out.read_bytes()
    header_version, detail, lap_time_ms, sample_count = struct.unpack_from(
        "<4i", raw, 0
    )
    assert header_version == 7
    assert detail == sample_count == result.n_waypoints
    assert lap_time_ms == 0
    assert result.total_length_m == pytest.approx(50.0, rel=0.05)


def test_write_fast_lane_ai_payload_size(tmp_path: Path) -> None:
    pts = np.zeros((50, 3))
    pts[:, 0] = np.linspace(0.0, 20.0, 50)
    out = tmp_path / "fast_lane.ai"
    result = write_fast_lane_ai(out, pts, target_spacing_m=2.0)
    raw = out.read_bytes()
    header_size = 4 * 4
    expected_size = (
        header_size
        + result.n_waypoints * _AI_POINT_STRUCT.size
        + result.n_waypoints * _AI_EXTRA_STRUCT.size
    )
    assert len(raw) == expected_size


def test_write_fast_lane_ai_too_few_points_raises(tmp_path: Path) -> None:
    pts = np.zeros((1, 3))
    with pytest.raises(ValueError, match="au moins 2 points"):
        write_fast_lane_ai(tmp_path / "fast_lane.ai", pts)


def test_write_fast_lane_ai_wrong_shape_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positions"):
        write_fast_lane_ai(tmp_path / "fast_lane.ai", np.zeros((10,)))
