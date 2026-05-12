"""Tests sur l'UV unwrap (xatlas lazy)."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest
from road2track_ac_export.uv_unwrap import _check_xatlas_available, unwrap_mesh_uvs

_XATLAS_AVAILABLE = importlib.util.find_spec("xatlas") is not None


@pytest.mark.skipif(
    _XATLAS_AVAILABLE, reason="xatlas installé : on ne peut pas vérifier l'ImportError"
)
def test_check_xatlas_raises_when_missing() -> None:
    with pytest.raises(ImportError, match="xatlas"):
        _check_xatlas_available()


@pytest.mark.skipif(
    _XATLAS_AVAILABLE,
    reason="xatlas installé : `unwrap_mesh_uvs` ne lèvera pas ImportError",
)
def test_unwrap_mesh_uvs_raises_without_xatlas() -> None:
    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    with pytest.raises(ImportError, match="xatlas"):
        unwrap_mesh_uvs(vertices, faces)


def test_unwrap_mesh_uvs_wrong_vertices_shape_raises() -> None:
    with pytest.raises(ValueError, match="vertices"):
        unwrap_mesh_uvs(np.zeros((3,)), np.zeros((1, 3), dtype=np.int64))


def test_unwrap_mesh_uvs_wrong_faces_shape_raises() -> None:
    with pytest.raises(ValueError, match="faces"):
        unwrap_mesh_uvs(np.zeros((3, 3)), np.zeros((1, 4), dtype=np.int64))


def test_unwrap_mesh_uvs_empty_raises() -> None:
    with pytest.raises(ValueError, match="vides"):
        unwrap_mesh_uvs(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
