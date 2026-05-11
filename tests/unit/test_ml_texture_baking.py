"""Tests sur le baking de textures par projection multi-vue.

`bake_textures_for_mesh` requiert open3d (pas installé en CI CPU-only). On
teste ici les helpers numpy pures + l'`ImportError` propre.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from road2track_ml.gs import DEFAULT_IPHONE_14_PRO
from road2track_ml.texture.baking import (
    _check_open3d_available,
    _pose_to_extrinsics,
    _project_vertices,
    _sample_bilinear,
    bake_textures_for_mesh,
)

_OPEN3D_AVAILABLE = importlib.util.find_spec("open3d") is not None


def test_pose_to_extrinsics_identity() -> None:
    pose = np.eye(4)
    rotation, translation = _pose_to_extrinsics(pose)
    np.testing.assert_array_almost_equal(rotation, np.eye(3))
    np.testing.assert_array_almost_equal(translation, np.zeros(3))


def test_pose_to_extrinsics_pure_translation() -> None:
    pose = np.eye(4)
    pose[0:3, 3] = [10.0, 20.0, 30.0]
    rotation, translation = _pose_to_extrinsics(pose)
    np.testing.assert_array_almost_equal(rotation, np.eye(3))
    np.testing.assert_array_almost_equal(translation, [-10.0, -20.0, -30.0])


def test_project_vertices_center_of_image() -> None:
    """Un vertex à (0, 0, 1) dans le repère caméra → (cx, cy) en pixel."""
    intrinsics = DEFAULT_IPHONE_14_PRO
    vertices = np.array([[0.0, 0.0, 1.0]])
    u, v, in_front = _project_vertices(vertices, np.eye(3), np.zeros(3), intrinsics)
    assert in_front[0]
    assert u[0] == pytest.approx(intrinsics.cx)
    assert v[0] == pytest.approx(intrinsics.cy)


def test_project_vertices_behind_camera() -> None:
    """Un vertex avec Z négatif est marqué hors champ avant."""
    intrinsics = DEFAULT_IPHONE_14_PRO
    vertices = np.array([[0.0, 0.0, -1.0]])
    _, _, in_front = _project_vertices(vertices, np.eye(3), np.zeros(3), intrinsics)
    assert not in_front[0]


def test_sample_bilinear_uniform_image() -> None:
    image = np.full((10, 10, 3), 200, dtype=np.uint8)
    rgb = _sample_bilinear(image, np.array([5.5]), np.array([4.5]))
    np.testing.assert_array_almost_equal(rgb[0], [200.0, 200.0, 200.0])


def test_sample_bilinear_interpolation() -> None:
    """Image en gradient horizontal : sample à mi-chemin = moyenne."""
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    image[:, 5, :] = 100
    image[:, 6, :] = 200
    rgb = _sample_bilinear(image, np.array([5.5]), np.array([5.0]))
    # bilinéaire à x=5.5 entre col 5 (100) et col 6 (200) → 150.
    np.testing.assert_array_almost_equal(rgb[0], [150.0, 150.0, 150.0])


@pytest.mark.skipif(
    _OPEN3D_AVAILABLE, reason="open3d installé : on ne peut pas vérifier l'ImportError"
)
def test_check_open3d_raises_when_missing() -> None:
    with pytest.raises(ImportError, match="open3d"):
        _check_open3d_available()


@pytest.mark.skipif(
    _OPEN3D_AVAILABLE, reason="open3d installé : `bake_textures_for_mesh` ne lèvera pas"
)
def test_bake_textures_raises_without_open3d(tmp_path: Path) -> None:
    fake_mesh = tmp_path / "mesh.obj"
    fake_mesh.write_text("")
    with pytest.raises(ImportError, match="open3d"):
        bake_textures_for_mesh(
            fake_mesh, tmp_path, tmp_path / "out", intrinsics=DEFAULT_IPHONE_14_PRO
        )
