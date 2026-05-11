"""Tests sur les intrinsics caméra (parsing Record3D + défauts iPhone)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from road2track_ml.gs import (
    DEFAULT_IPHONE_14_PRO,
    CameraIntrinsics,
    load_intrinsics_or_default,
    parse_record3d_metadata,
)


def test_intrinsics_matrix_shape_and_values() -> None:
    intr = CameraIntrinsics(fx=1500.0, fy=1500.0, cx=960.0, cy=720.0, width=1920, height=1440)
    k = intr.matrix()
    assert k.shape == (3, 3)
    assert k[0, 0] == 1500.0
    assert k[1, 1] == 1500.0
    assert k[0, 2] == 960.0
    assert k[1, 2] == 720.0
    assert k[2, 2] == 1.0


def test_intrinsics_scale_to_half() -> None:
    intr = CameraIntrinsics(fx=1500.0, fy=1500.0, cx=960.0, cy=720.0, width=1920, height=1440)
    half = intr.scale_to(960, 720)
    assert half.fx == pytest.approx(750.0)
    assert half.fy == pytest.approx(750.0)
    assert half.cx == pytest.approx(480.0)
    assert half.cy == pytest.approx(360.0)


def test_default_iphone_14_pro_sane() -> None:
    assert DEFAULT_IPHONE_14_PRO.width > 0
    assert DEFAULT_IPHONE_14_PRO.height > 0
    assert DEFAULT_IPHONE_14_PRO.fx > 0


def test_parse_record3d_metadata_flat_k(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "fps": 30,
                "w": 1280,
                "h": 720,
                "K": [1000.0, 0.0, 640.0, 0.0, 1000.0, 360.0, 0.0, 0.0, 1.0],
            }
        ),
        encoding="utf-8",
    )
    intr = parse_record3d_metadata(metadata)
    assert intr.fx == 1000.0
    assert intr.fy == 1000.0
    assert intr.cx == 640.0
    assert intr.cy == 360.0
    assert intr.width == 1280
    assert intr.height == 720


def test_parse_record3d_metadata_nested_k(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "width": 800,
                "height": 600,
                "K": [[500, 0, 400], [0, 500, 300], [0, 0, 1]],
            }
        ),
        encoding="utf-8",
    )
    intr = parse_record3d_metadata(metadata)
    assert intr.width == 800
    assert intr.cx == 400


def test_parse_record3d_metadata_missing_fields_raises(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"fps": 30}), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplet"):
        parse_record3d_metadata(metadata)


def test_load_intrinsics_or_default_no_file_returns_default(tmp_path: Path) -> None:
    intr = load_intrinsics_or_default(tmp_path)
    assert intr.fx == DEFAULT_IPHONE_14_PRO.fx


def test_load_intrinsics_or_default_corrupt_returns_default(tmp_path: Path) -> None:
    (tmp_path / "metadata.json").write_text("not json", encoding="utf-8")
    intr = load_intrinsics_or_default(tmp_path)
    assert intr.fx == DEFAULT_IPHONE_14_PRO.fx


def test_load_intrinsics_or_default_valid_file(tmp_path: Path) -> None:
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {"w": 1920, "h": 1440, "K": np.eye(3).flatten().tolist()}
        ),
        encoding="utf-8",
    )
    intr = load_intrinsics_or_default(tmp_path)
    assert intr.width == 1920
