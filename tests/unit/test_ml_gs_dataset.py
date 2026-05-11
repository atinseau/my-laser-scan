"""Tests sur le dataset de keyframes (loader pur Python)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from road2track_ml.gs import DEFAULT_IPHONE_14_PRO, KeyframesDataset


def _write_jpeg(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (64, 48)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(path, format="JPEG", quality=90)


def _make_manifest(local_dir: Path, n: int = 3) -> Path:
    keyframes_dir = local_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i in range(n):
        image_name = f"{i:04d}.jpg"
        _write_jpeg(keyframes_dir / image_name, color=(i * 50, 100, 200))
        entries.append(
            {
                "idx": i,
                "traj_idx": i * 10,
                "t": 1700000000.0 + i * 0.5,
                "video_t": i * 0.5,
                "pos": [float(i), 0.0, 0.0],
                "quat": [1.0, 0.0, 0.0, 0.0],
                "image_key": f"prj/seg/keyframes/{image_name}",
                "bytes": 1000,
            }
        )
    manifest = {
        "schema_version": 1,
        "project_id": "prj",
        "segment_id": "seg",
        "n_keyframes": n,
        "min_spacing_m": 0.5,
        "video_start_t": 1700000000.0,
        "arc_length_m": float(n - 1),
        "keyframes": entries,
    }
    manifest_path = local_dir / "keyframes.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_dataset_length(tmp_path: Path) -> None:
    _make_manifest(tmp_path, n=5)
    dataset = KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)
    assert len(dataset) == 5


def test_dataset_loads_image_and_pose(tmp_path: Path) -> None:
    _make_manifest(tmp_path, n=2)
    dataset = KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)
    sample = dataset[0]
    assert sample.idx == 0
    assert sample.image.shape == (48, 64, 3)
    assert sample.image.dtype == np.uint8
    # Pose : identity rotation (quat 1,0,0,0) + pos (0,0,0).
    np.testing.assert_array_almost_equal(sample.pose_world_from_camera[0:3, 0:3], np.eye(3))
    np.testing.assert_array_almost_equal(sample.pose_world_from_camera[0:3, 3], [0.0, 0.0, 0.0])


def test_dataset_pose_translation_index_1(tmp_path: Path) -> None:
    _make_manifest(tmp_path, n=2)
    dataset = KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)
    sample = dataset[1]
    np.testing.assert_array_almost_equal(sample.pose_world_from_camera[0:3, 3], [1.0, 0.0, 0.0])


def test_dataset_intrinsics_rescaled_to_image(tmp_path: Path) -> None:
    """Le dataset doit adapter les intrinsics à la taille réelle de l'image."""
    _make_manifest(tmp_path, n=1)
    dataset = KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)
    sample = dataset[0]
    # Image 64x48, intrinsics par défaut 1920x1440 → scale 1/30, 1/30.
    assert sample.intrinsics.width == 64
    assert sample.intrinsics.height == 48
    assert sample.intrinsics.fx == pytest.approx(DEFAULT_IPHONE_14_PRO.fx * 64 / 1920)


def test_dataset_positions_world(tmp_path: Path) -> None:
    _make_manifest(tmp_path, n=4)
    dataset = KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)
    positions = dataset.positions_world()
    assert positions.shape == (4, 3)
    np.testing.assert_array_almost_equal(positions[:, 0], [0.0, 1.0, 2.0, 3.0])


def test_dataset_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="manifest"):
        KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)


def test_dataset_empty_manifest_raises(tmp_path: Path) -> None:
    (tmp_path / "keyframes.json").write_text(
        json.dumps({"keyframes": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="aucune keyframe"):
        KeyframesDataset(tmp_path, intrinsics=DEFAULT_IPHONE_14_PRO)
