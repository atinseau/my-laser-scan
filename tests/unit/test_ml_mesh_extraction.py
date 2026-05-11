"""Tests sur l'extraction de mesh depuis un splat.

La logique de reconstruction Poisson elle-même requiert `open3d` (pas installé
en CI CPU-only). On teste ici :
- L'`ImportError` propre quand open3d manque.
- La fonction `_normals_from_gaussians` (numpy seul).
- `_sh_dc_to_rgb` (numpy seul).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from road2track_ml.gs import save_gaussian_splat_ply
from road2track_ml.mesh.extraction import (
    _check_open3d_available,
    _normals_from_gaussians,
    _sh_dc_to_rgb,
    extract_mesh_from_splat,
)

_OPEN3D_AVAILABLE = importlib.util.find_spec("open3d") is not None


def test_sh_dc_to_rgb_gray() -> None:
    sh_dc = np.zeros((5, 3), dtype=np.float32)
    rgb = _sh_dc_to_rgb(sh_dc)
    np.testing.assert_array_almost_equal(rgb, np.full((5, 3), 0.5))


def test_sh_dc_to_rgb_clips_to_unit_range() -> None:
    sh_dc = np.full((1, 3), 100.0, dtype=np.float32)
    rgb = _sh_dc_to_rgb(sh_dc)
    assert rgb.max() <= 1.0
    assert rgb.min() >= 0.0


def test_normals_from_identity_quaternion_takes_smallest_axis() -> None:
    """Avec une rotation identité, la normale = axe canonique du plus petit scale."""
    quats = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    # Scales en log : exp(log(0.01)) = 0.01 → c'est l'axe Y (idx=1) le plus petit.
    scales_log = np.array([[np.log(1.0), np.log(0.01), np.log(0.5)]], dtype=np.float32)
    normals = _normals_from_gaussians(quats, scales_log)
    np.testing.assert_array_almost_equal(np.abs(normals[0]), [0.0, 1.0, 0.0], decimal=6)


@pytest.mark.skipif(
    _OPEN3D_AVAILABLE, reason="open3d installé : on ne peut pas vérifier l'ImportError"
)
def test_check_open3d_raises_when_missing() -> None:
    with pytest.raises(ImportError, match="open3d"):
        _check_open3d_available()


@pytest.mark.skipif(
    _OPEN3D_AVAILABLE,
    reason="open3d installé : `extract_mesh_from_splat` ne lèvera pas",
)
def test_extract_mesh_raises_without_open3d(tmp_path: Path) -> None:
    splat_path = tmp_path / "scene.ply"
    n = 10
    save_gaussian_splat_ply(
        splat_path,
        sh_degree=3,
        means=np.zeros((n, 3), dtype=np.float32),
        sh_dc=np.zeros((n, 3), dtype=np.float32),
        sh_rest=np.zeros((n, 45), dtype=np.float32),
        opacities_logit=np.zeros(n, dtype=np.float32),
        scales_log=np.zeros((n, 3), dtype=np.float32),
        quats_wxyz=np.tile([1.0, 0.0, 0.0, 0.0], (n, 1)).astype(np.float32),
    )
    with pytest.raises(ImportError, match="open3d"):
        extract_mesh_from_splat(splat_path, tmp_path)
